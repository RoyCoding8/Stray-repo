"""N-206: the E3 gateway probe spent money with no reservation behind it.

`e3_ladder.probe_gateway` opened `GATEWAY + "/chat/completions"` through
`urllib.request.urlopen` directly. The study around it admits every decision
through `authority.admit_study_call` and settles it through
`broker.dispatch_operation`, so the probe was the one send in the module with
no reservation, no exposure taken, and no receipt: a call that no ceiling
could reach. This is not N-81's bypassed owner, where an operation existed and
the owner was skipped. Here there was no operation at all.

The sibling module already carries the repair for the identical probe:
`e2_replication.probe_route` is the same "confirm the route before planning
any effect" call, at the same `PROBE_MAX_TOKENS = 8`, and it goes through
`broker.ensure_operation` and `broker.dispatch_operation` and is charged in
its cap sheet. Two modules, one defect, one precedent. Routing is the
repair; documenting the bare call as correct would assert the same shape is
a defect in one file and correct in the other.

Two tests, one per claim:

1. A credential-bearing probe with no durable authority contacts nothing.
   This is the regression: it fails while the `urlopen` is in place, and it
   fails by making the network call rather than by inspecting the source.
2. With a bound study the probe is admitted through `admit_study_call` and
   settled through the broker, so the send is bounded by authority and the
   store holds the operation and its receipt.

`max_calibration` is 1 for this study, so the probe's route is resolved
before anything is admitted. The fixture that covers that ordering hands
`probe_gateway` its own gateway rather than relying on an endpoint in the
environment, because a test process has none, and it counts the store
rows on both sides of the ceiling instead of reading the returned record.

The third is the ledger's claim about the other file: `experiments/coord02`
contains no direct URL-opening call at all, so there is nothing to route
there.
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

COORD02 = ROOT / "experiments" / "coord02"


@contextlib.contextmanager
def _credential_present():
    previous = os.environ.get("SETTLEMENT_GATEWAY_KEY")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = "n206-probe-key"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
        else:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous


def _tripwire(monkeypatch):
    """Record any HTTP escape from the probe.

    Raising is not enough here: `probe_gateway` wraps its send in
    `except Exception` and reports, so a raised `AssertionError` is
    swallowed and the probe returns `unreachable` either way. Counting the
    attempt is the only way to see the send that actually happened.
    """
    import socket
    import urllib.request

    contact = []

    def _record(*_args, **_kwargs):
        contact.append(True)
        raise OSError("the probe reached the network")

    monkeypatch.setattr(urllib.request, "urlopen", _record)
    monkeypatch.setattr(socket.socket, "connect", _record)
    return contact


@contextlib.contextmanager
def _endpoint(state: str | None):
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
    from settlement import authority

    handle = authority.authorize_study(
        dsn, e3_ladder.STUDY_ROOT, authorized=100_000,
        allocation_id=e3_ladder.STUDY_ALLOCATION,
        ceilings=e3_ladder.study_ceilings(
            {"max_operations": 4_096, "max_development": 4_096,
             "max_calibration": 1}))
    try:
        yield handle.study_root
    finally:
        with contextlib.suppress(Exception):
            from settlement import db

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


def test_a_credential_bearing_probe_with_no_authority_contacts_nothing(
        migrated_db, monkeypatch):
    """The defect, as behaviour: no reservation, so no send.

    Break by restoring the `urllib.request.urlopen` call, which reaches the
    tripwire instead of returning.
    """
    contact = _tripwire(monkeypatch)

    with _credential_present():
        record = e3_ladder.probe_gateway()

    assert not contact, (
        "the probe opened a URL with no reservation behind it, so the send "
        "no ceiling could reach: %r" % record)
    assert record["credential_present"] is True, (
        "the probe did not see the credential, so it proved nothing about "
        "the send: %r" % record)
    assert record["admitted"] is False, (
        "the probe reported a send it never admitted: %r" % record)
    assert record["exposure_units"] == 0, (
        "an unadmitted probe spent exposure: %r" % record)
    assert record["status"] != "reachable", (
        "a probe with no admitted operation reported the route as reachable")


def test_the_study_binds_a_ceiling_that_bounds_the_probe(migrated_db):
    """The probe's send has to be inside a ceiling, or routing moves the
    defect rather than fixing it.

    `max_operations` is always spent, so the probe's operation is counted
    there; `max_calibration` is the counter this study's own probe kind
    moves, and binding it at one is what makes "exactly one probe" a bound
    rather than a claim.
    """
    from settlement import store

    ceilings = e3_ladder.study_ceilings({"max_operations": 4_096})

    assert ceilings.get("max_calibration") == 1, (
        "the probe's model call is bounded only by the operation count, so "
        "nothing states that it happens once: %r" % ceilings)
    for name, value in ceilings.items():
        assert store.is_ceiling_name(name), (
            "authorize_study refuses %r outright" % name)
        assert store.is_ceiling_enforced(name), (
            "%r is declared-only, so the store records it and never checks "
            "it, which is a comment standing in for a bound" % name)
        assert isinstance(value, int) and value > 0


def test_the_probe_routes_through_the_durable_owner(migrated_db):
    """The repair: the send is admitted, dispatched, and receipted.

    Break by passing `dsn=None`, which returns the unadmitted record the
    first test demands.
    """
    from settlement.gateway import FakeGatewayAdapter

    with _bound_study(migrated_db) as study_root:
        with _credential_present():
            record = e3_ladder.probe_gateway(
                migrated_db, study_root=study_root,
                gateway=FakeGatewayAdapter(text="OK"))

        assert record["admitted"] is True, (
            "the probe was not admitted through the study: %r" % record)
        assert record["operation_id"], (
            "an admitted probe names no operation: %r" % record)
        assert record["exposure_units"] > 0, (
            "an admitted model-inference took no exposure, so the "
            "reservation never happened: %r" % record)
        assert record["status"] == "reachable", (
            "the routed probe did not reach the route: %r" % record)

        operations = [
            row for row in e3_ladder._operation_rows(
                migrated_db, e3_ladder.STUDY_ROOT)
            if row["id"] == record["operation_id"]]
        assert len(operations) == 1, (
            "the store holds %d rows for the probe's operation, so the "
            "operation was never written: %r" % (len(operations), operations))
        assert operations[0]["kind"] == "calibration", (
            "the probe was admitted under %r, which is not the kind the "
            "study bounds" % operations[0]["kind"])

        from settlement import db

        with db.read_connect(migrated_db) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT outcome, receipt_identity FROM receipts"
                    " WHERE operation_id = %s", (record["operation_id"],))
                rows = cur.fetchall()
            conn.commit()
        assert [r[0] for r in rows] == ["success"], (
            "the routed probe left no success receipt: %r" % rows)
        assert rows[0][1] == "gw:%s" % record["operation_id"], (
            "the receipt is not the gateway's own, so the send was not "
            "settled through the broker: %r" % rows)


def test_the_study_admits_exactly_one_probe_under_its_own_ceilings(
        migrated_db):
    """`max_calibration: 1` is a bound, so a second probe is refused.

    Both halves are counted, not inferred from the first. The first probe
    has to reach `reachable` and leave one `calibration` row behind, so a
    refusal cannot pass as an admission; and the second call has to come
    back naming the ceiling, so a refusal for any other reason
    (malformed payload, exhausted units, missing authority) cannot pass as
    the ceiling holding. The old fixture asserted only `admitted is True`
    on a probe that could not route, so it counted nothing and proved
    nothing.

    Break by raising `max_calibration`, or by admitting the probe as
    `development`, which `max_calibration` never sees.
    """
    from settlement import authority, db, loop

    from settlement.gateway import FakeGatewayAdapter

    with _bound_study(migrated_db) as study_root:
        with _credential_present():
            first = e3_ladder.probe_gateway(
                migrated_db, study_root=study_root,
                gateway=FakeGatewayAdapter(text="OK"))
        admitted = [row for row in e3_ladder._operation_rows(
            migrated_db, study_root)
            if row["kind"] == e3_ladder.PROBE_KIND]
        second = authority.admit_study_call(
            migrated_db, study_root, kind="calibration",
            operation_id=study_root + "-op-probe-second",
            effect="model-inference",
            payload={"model": e3_ladder.GATEWAY_MODEL,
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": e3_ladder.PROBE_MAX_TOKENS,
                     "deadline_ms": 120_000})
        with db.read_connect(migrated_db) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM operations WHERE id = %s",
                    (study_root + "-op-probe-second",))
                refused_rows = cur.fetchone()[0]
            conn.commit()

    assert first["admitted"] is True, (
        "the study did not admit its one probe, so nothing was spent and the "
        "second refusal below proves nothing: %r" % first)
    assert first["status"] == "reachable", (
        "the admitted probe never reached the route, so the ceiling this "
        "test exists to check was never spent by a send: %r" % first)
    assert first["operation_id"] == study_root + "-op-probe-route", (
        "the admitted probe is not the one the ceiling counts: %r" % first)
    assert [row["id"] for row in admitted] == [first["operation_id"]], (
        "the store holds %d calibration operations for a ceiling of one: %r"
        % (len(admitted), admitted))

    assert second == loop.Refusal(
        reason="insufficient-authority",
        detail="study e3ladder-root ceiling max_calibration=1 reached at 1"), (
        "the second probe was refused for a reason other than the ceiling, "
        "so max_calibration=1 is not what bounds this send: %r" % (second,))
    assert not isinstance(second, loop.Grant), (
        "max_calibration=1 admitted a second probe, so the ceiling is not "
        "what bounds this send: %r" % second)
    assert refused_rows == 0, (
        "a refused admission still wrote %d operation row(s), so the "
        "refusal above is not the one that stopped the send"
        % refused_rows)


def test_a_credential_with_no_endpoint_spends_no_calibration(migrated_db):
    """The case the replaced fixture covered by accident, now on purpose.

    The old fixture called `probe_gateway` with a dsn, a study_root and no
    gateway, so it spent a calibration on a send that never went on the
    wire, and it asserted that spending as correct. `max_calibration` is 1,
    so a probe that admits and then discovers it has no endpoint burns the
    one confirmation the cap sheet authorizes. `probe_gateway` now resolves
    the route before it admits, and this is the test that says so against
    the store.

    The endpoint is popped rather than set, so the test is the honest case:
    a process that simply has no route configured, rather than one pointed
    somewhere that happens to be empty.

    Break by moving the route resolution back behind `admit_study_call`.
    """
    from settlement import authority, db, loop

    with _bound_study(migrated_db) as study_root, _credential_present(), \
            _endpoint(None):
        assert e3_ladder._probe_gateway_from_env() is None, (
            "the environment named an endpoint, so this is not the "
            "no-endpoint case the test claims")
        record = e3_ladder.probe_gateway(migrated_db, study_root=study_root)
        spent = [row for row in e3_ladder._operation_rows(
            migrated_db, study_root)
            if row["kind"] == e3_ladder.PROBE_KIND]
        # A later probe in the same study, with a route by then, must still
        # fit. If the unroutable call above spent the ceiling, this is where
        # it shows.
        granted = authority.admit_study_call(
            migrated_db, study_root, kind=e3_ladder.PROBE_KIND,
            operation_id=study_root + "-op-probe-later",
            effect="model-inference",
            payload={"model": e3_ladder.GATEWAY_MODEL,
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": e3_ladder.PROBE_MAX_TOKENS,
                     "deadline_ms": 120_000})
        with db.read_connect(migrated_db) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM allocations"
                    " WHERE id LIKE %s",
                    (e3_ladder.STUDY_ALLOCATION + "/calibration/%",))
                children = cur.fetchone()[0]
            conn.commit()

    assert record["credential_present"] is True, (
        "the probe did not see the credential, so it proved nothing about "
        "the admission: %r" % record)
    assert record["status"] == "no-route", (
        "a credential with no endpoint did not report the missing route: %r"
        % record)
    assert record["admitted"] is False, (
        "the probe admitted an operation for a send it could not make: %r"
        % record)
    assert record["exposure_units"] == 0, (
        "an unadmitted probe reported exposure: %r" % record)
    assert record["operation_id"] is None, (
        "an unadmitted probe named an operation: %r" % record)
    assert "dispatch_state" not in record, (
        "the probe dispatched with no route: %r" % record)
    assert spent == [], (
        "the store holds %d calibration operation(s) for a send that never "
        "happened: %r" % (len(spent), spent))
    assert isinstance(granted, loop.Grant), (
        "the unroutable probe spent the study's one calibration, so no probe "
        "can be admitted afterwards even once a route exists: %r"
        % (granted,))
    assert children == 1, (
        "the study holds %d calibration child allocation(s); only the probe "
        "granted above should have reserved one" % children)


def test_the_probe_reports_every_outcome_it_can_reach():
    """`probe_gateway` is the run's only availability evidence, so every
    branch it can take has to be one the evidence vocabulary names.

    A routed probe that is admitted but cannot settle says
    `no-settled-response`, which is neither "reachable" nor "unreachable":
    the send was bounded and it still taught nothing. Break by returning
    a status outside this set from any branch.
    """
    import os

    from experiments.ad01 import e3_ladder as module

    with _credential_present():
        assert module.probe_gateway()["status"] == "unadmitted-no-authority"
    previous = os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
    try:
        assert module.probe_gateway()["status"] == "no-credential"
    finally:
        if previous is not None:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous

    assert {
        "no-credential", "unadmitted-no-authority", "unadmitted",
        "no-route", "no-settled-response", "reachable",
    } == set(module.PROBE_STATUSES), (
        "the probe's documented vocabulary and the statuses it can return "
        "have drifted: %r" % sorted(module.PROBE_STATUSES))


def test_coord02_opens_no_url_of_its_own():
    """The ledger's other row: there is no call site to route.

    Every model call in `experiments/coord02` goes through
    `broker.ensure_operation` then `broker.dispatch_operation`
    (`entry.py:274-288` and `entry.py:380-413`); `entry.py:823` is the
    `HttpGatewayAdapter` import inside `gateway_factory`, not a `urlopen`.
    """
    offenders = []
    for path in sorted(COORD02.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("urlopen", "urllib.request", "http.client"):
            if marker in text:
                offenders.append("%s: %s" % (
                    path.relative_to(ROOT), marker))
    assert not offenders, (
        "experiments/coord02 opens a URL directly, with no reservation "
        "behind it: %r" % offenders)

