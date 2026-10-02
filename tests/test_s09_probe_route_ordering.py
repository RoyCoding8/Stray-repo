"""C12: the E3 probe's route is resolved before its operation is admitted.

`e3_ladder.probe_gateway` resolved the route inside `_admitted_probe`, after
`authority.admit_study_call` had already taken the reservation. A process
with a credential, a dsn and no `SETTLEMENT_GATEWAY_ENDPOINT` therefore came
back `no-route` with `admitted: True` and one `max_calibration` unit spent
for a send that never went on the wire. That ceiling is 1 for this study, so
the one confirmation the cap sheet authorizes was gone and a route that
appeared later could never be confirmed.

`no_route_probe` covers only the study's own `build` path, which is why the
direct-caller shape kept the defect after that repair.

These tests call `probe_gateway` the way its callers do and read the store,
so they hold whatever order the resolution is written in. None of them reads
`probe_gateway`'s source, so putting the admission back ahead of the route
fails them rather than satisfying them.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import e3_ladder  # noqa: E402


@contextlib.contextmanager
def _credential_present():
    previous = os.environ.get("SETTLEMENT_GATEWAY_KEY")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = "v5-route-ordering-key"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
        else:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous


@contextlib.contextmanager
def _endpoint(state: str):
    previous = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT")
    if state is None:
        os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
    else:
        os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = state
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
        else:
            os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = previous


@contextlib.contextmanager
def _bound_study(dsn: str):
    from settlement import authority, db

    handle = authority.authorize_study(
        dsn, e3_ladder.STUDY_ROOT, authorized=100_000,
        allocation_id=e3_ladder.STUDY_ALLOCATION,
        ceilings=e3_ladder.study_ceilings({"max_operations": 4_096}))
    try:
        yield handle.study_root
    finally:
        with contextlib.suppress(Exception):
            with db.connect(dsn) as conn:
                conn.execute(
                    "DELETE FROM operations WHERE id LIKE %s"
                    " OR allocation_id LIKE %s",
                    (e3_ladder.STUDY_ROOT + "-op-%",
                     e3_ladder.STUDY_ALLOCATION + "/%"))
                conn.execute("DELETE FROM allocations WHERE id LIKE %s",
                             (e3_ladder.STUDY_ALLOCATION + "/%",))
                conn.execute(
                    "DELETE FROM study_authority WHERE study_root = %s",
                    (e3_ladder.STUDY_ROOT,))
                conn.commit()


def _calibration_operations(dsn: str, study_root: str) -> list:
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.id, o.payload->>'kind' AS kind"
                " FROM operations o WHERE o.id LIKE %s ORDER BY o.id",
                (study_root + "-op-%",))
            rows = [dict(row) for row in cur.fetchall()]
        conn.commit()
    return [row for row in rows if row["kind"] == e3_ladder.PROBE_KIND]


def test_a_direct_caller_with_no_route_spends_no_calibration(migrated_db):
    """The defect, as behaviour, on the path `no_route_probe` never covered.

    A credential, a dsn, a bound study and no endpoint is the exact shape of
    a direct `probe_gateway` call, and it is the shape `build` does not have.
    Break by moving the route resolution back behind `admit_study_call`.
    """
    with _bound_study(migrated_db) as study_root, _credential_present(), \
            _endpoint(None):
        assert e3_ladder._probe_gateway_from_env() is None, (
            "the environment named an endpoint, so this is not the no-route "
            "case the test claims")

        record = e3_ladder.probe_gateway(
            migrated_db, study_root=study_root)
        spent = _calibration_operations(migrated_db, study_root)

    assert record["status"] == "no-route", (
        "a credential with no endpoint did not report a missing route: %r"
        % record)
    assert record["admitted"] is False, (
        "the probe admitted an operation for a send it could not make, so "
        "the study spent its one calibration on nothing: %r" % record)
    assert record["exposure_units"] == 0, (
        "an unadmitted probe reported exposure: %r" % record)
    assert record["operation_id"] is None, (
        "an unadmitted probe named an operation: %r" % record)
    assert "dispatch_state" not in record, (
        "the probe dispatched with no route: %r" % record)
    assert spent == [], (
        "the store holds calibration operations for a send that never "
        "happened: %r" % spent)


def test_the_ceiling_is_still_whole_after_a_probe_that_could_not_route(
        migrated_db):
    """What the reservation was worth. `max_calibration` is 1, so spending
    it on an unroutable probe leaves no way to confirm a route that appears
    later in the same run.

    Break by admitting before resolving the route, which is the only way the
    first admission in this test can consume the ceiling.
    """
    from settlement import authority, loop

    with _bound_study(migrated_db) as study_root, _credential_present(), \
            _endpoint(None):
        e3_ladder.probe_gateway(migrated_db, study_root=study_root)
        granted = authority.admit_study_call(
            migrated_db, study_root, kind=e3_ladder.PROBE_KIND,
            operation_id=study_root + "-op-probe-second",
            effect="model-inference",
            payload={"model": e3_ladder.GATEWAY_MODEL,
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": e3_ladder.PROBE_MAX_TOKENS,
                     "deadline_ms": e3_ladder.PROBE_DEADLINE_MS})

    assert isinstance(granted, loop.Grant), (
        "the unroutable probe spent the study's one calibration, so no later "
        "probe can be admitted at all: %r" % granted)


def test_a_caller_with_a_route_still_reaches_the_admission(migrated_db):
    """The other side, so a free no-route cannot be bought by never sending.

    Break by returning before the admission whenever the route is resolved
    from the environment rather than handed in by the caller.
    """
    from settlement.gateway import FakeGatewayAdapter

    with _bound_study(migrated_db) as study_root, _credential_present(), \
            _endpoint("http://localhost:4000/v1"):
        record = e3_ladder.probe_gateway(
            migrated_db, study_root=study_root,
            gateway=FakeGatewayAdapter(text="OK"))
        spent = _calibration_operations(migrated_db, study_root)

    assert record["status"] == "reachable", (
        "a route was available and the probe did not confirm it: %r" % record)
    assert record["admitted"] is True, (
        "a routed probe was not admitted through the study: %r" % record)
    assert record["exposure_units"] > 0, (
        "an admitted model-inference took no exposure, so no reservation "
        "happened: %r" % record)
    assert len(spent) == 1, (
        "the routed probe left %d calibration operations in the store, so "
        "the admission is not the one the ceiling counts: %r"
        % (len(spent), spent))
