"""R6: three small defects, each pinned against the behaviour it claims.

The first is a status vocabulary the probe retired two values from and the
test kept, so the assertion passed on a branch it does not name. The second
is a probe that admits an operation before it knows there is a route to send
it on, spending `max_calibration` for a send that never happens. The third
is `LiveGuard.already_spent`, whose unit the N-203 repair left implicit, and
which two callers read in two different currencies.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import e3_ladder  # noqa: E402
from experiments.ad01 import live_construct as live  # noqa: E402
from settlement.gateway import ModelRequest, ModelResponse, Usage  # noqa: E402


@contextlib.contextmanager
def _credential_present():
    previous = os.environ.get("SETTLEMENT_GATEWAY_KEY")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = "r6-probe-key"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
        else:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous


@contextlib.contextmanager
def _endpoint_present():
    previous = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT")
    os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = e3_ladder.GATEWAY
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
        else:
            os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = previous


@contextlib.contextmanager
def _endpoint_absent():
    previous = os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
    try:
        yield
    finally:
        if previous is not None:
            os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = previous


@contextlib.contextmanager
def _bound_study(dsn: str):
    from settlement import authority, db

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
            with db.connect(dsn) as conn:
                conn.execute(
                    "DELETE FROM operations"
                    " WHERE allocation_id LIKE %s OR id LIKE %s",
                    (e3_ladder.STUDY_ALLOCATION + "/%",
                     e3_ladder.STUDY_ROOT + "-op-%"))
                conn.execute("DELETE FROM allocations WHERE id LIKE %s",
                             (e3_ladder.STUDY_ALLOCATION + "/%",))
                conn.execute(
                    "DELETE FROM study_authority WHERE study_root = %s",
                    (e3_ladder.STUDY_ROOT,))
                conn.commit()


@contextlib.contextmanager
def _run_store_survives_build():
    """Let the test read the store `build` opened, before it is dropped.

    `build` runs inside `iso.disposable_db`, which drops the database on
    exit, so a read taken after `build` returns is a read of a store that
    no longer exists. The name is not a substitute: the evidence this
    test wants is what the store held at the moment the run finished.

    The replacement refuses any store that `iso` does not mark
    disposable, so this cannot be aimed at a shared or live database.
    """
    from experiments.ad01 import s09_run_isolation as iso

    real = iso.drop_disposable_db
    kept: list = []
    seen: dict = {}

    def _hold(database, **kwargs):
        assert isinstance(database, iso.DisposableDatabase) and \
            database.name.startswith(iso.DB_PREFIX + "_"), (
            "refusing to hold a store that is not marked disposable: %r"
            % getattr(database, "name", database))
        seen.update(kwargs)
        kept.append(database)

    iso.drop_disposable_db = _hold
    try:
        yield kept
    finally:
        iso.drop_disposable_db = real
        for database in kept:
            real(database, **seen)


def _calibration_operations(dsn: str, study_root: str) -> list:
    """Operations the store holds under the probe's own kind, by SELECT.

    Break by admitting the probe under another kind, which is what
    `max_calibration` never sees.
    """
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.id, o.payload->>'kind' AS kind"
                " FROM operations o WHERE o.id LIKE %s",
                (study_root + "-op-%",))
            rows = [dict(row) for row in cur.fetchall()]
        conn.commit()
    return [row for row in rows if row["kind"] == e3_ladder.PROBE_KIND]


# --- defect 1: the retired status vocabulary ------------------------------


def test_the_status_vocabulary_matches_the_one_the_probe_can_return(
        migrated_db):
    """The allowlist in `tests/test_s09_e3_ladder.py` was pinned at four
    statuses and commit `80582d8` retired two of them.

    `http-error` and `unreachable` are gone from `probe_gateway`: a send now
    goes through `broker.dispatch_operation`, and the two outcomes that can
    still follow a send are `no-settled-response` and `reachable`. The old
    assertion kept passing only because its reachable branch is
    `no-credential`, which a test that pops the credential always reaches.
    It was true by accident and false about the thing it names.

    Break by narrowing this to the two retired statuses, or by widening
    `PROBE_STATUSES` to include a value no branch can return.
    """
    assert set(e3_ladder.PROBE_STATUSES) == {
        "no-credential", "unadmitted-no-authority", "unadmitted", "no-route",
        "no-settled-response", "reachable"}, (
        "the probe's status vocabulary and this pin have drifted: %r"
        % sorted(e3_ladder.PROBE_STATUSES))

    previous = os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
    try:
        record = e3_ladder.probe_gateway()
    finally:
        if previous is not None:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous

    assert record["status"] == "no-credential"
    assert record["status"] in e3_ladder.PROBE_STATUSES


# --- defect 2: exposure spent for a send that never happens --------------


def test_build_does_not_spend_a_calibration_on_a_send_it_cannot_make():
    """The defect, as behaviour: a credential, no endpoint, and a study that
    admits the probe's operation and burns `max_calibration` for a send it
    never makes.

    `build` called `probe_gateway`, which resolves its route only after
    `admit_study_call`, so `no-route` came back with `admitted: True` and
    one calibration already spent. `max_calibration` is 1 for this study,
    so the one probe the cap sheet authorizes is gone and the study has no
    second chance to confirm a route that appears later.

    Break by dropping the route check from `probe_gateway`, which puts the
    admission back ahead of the route lookup.
    """
    with _credential_present(), _endpoint_absent():
        assert e3_ladder._probe_gateway_from_env() is None, (
            "the environment named an endpoint, so this is not the no-route "
            "case the test claims")
        record = e3_ladder.no_route_probe()

    assert record["status"] == "no-route", (
        "a credential with no endpoint did not report a missing route: %r"
        % record)
    assert record["admitted"] is False, (
        "the study spent a calibration for a send it could not make: %r"
        % record)
    assert record["exposure_units"] == 0, (
        "an unadmitted probe took exposure: %r" % record)
    assert "dispatch_state" not in record, (
        "the probe dispatched with no route: %r" % record)
    assert record["status"] in e3_ladder.PROBE_STATUSES


def test_no_route_is_reached_by_a_study_that_admits_it(migrated_db):
    """The same property through the real store, with a bound study.

    The cap sheet's `max_calibration` is 1, so this is the consequence that
    matters: a probe that admitted here would leave no second probe for a
    route that appears later. With the route checked first, the ceiling is
    untouched and a second probe still gets the grant.

    Break by admitting before resolving the route.
    """
    from settlement import authority, loop

    with _bound_study(migrated_db) as study_root, _credential_present(), \
            _endpoint_absent():
        record = e3_ladder.no_route_probe()
        before = _calibration_operations(migrated_db, study_root)
        granted = authority.admit_study_call(
            migrated_db, study_root, kind=e3_ladder.PROBE_KIND,
            operation_id=study_root + "-op-probe-after-no-route",
            effect="model-inference",
            payload={"model": e3_ladder.GATEWAY_MODEL,
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": e3_ladder.PROBE_MAX_TOKENS,
                     "deadline_ms": 120_000})

        assert record["admitted"] is False
        assert before == [], (
            "the no-route probe left a calibration operation in the store "
            "for a send that never happened: %r" % before)
        assert isinstance(granted, loop.Grant), (
            "the no-route probe spent the study's one calibration, so no "
            "later probe can be admitted at all: %r" % granted)


def test_build_spends_no_calibration_when_no_route_is_configured(tmp_path):
    """What `build` does, read out of the store it built.

    The predecessor of this test read `build`'s own source for two
    substrings. It guarded a string, so a harmless reflow broke it and
    deleting the branch while leaving the two literals somewhere in the
    source kept it green. `probe_gateway` resolves the route itself
    (`c344400`) and `build` now has no route check of its own, so the
    property to pin is the one that lives at the boundary every caller
    passes through: a study with no endpoint spends none of its
    `max_calibration` allowance, and the run it reports still says it
    spent the whole matrix.

    `build` runs the whole ladder against a store of its own and drops it
    on exit, so the read happens while that store is still there and the
    snapshot is taken by a wrapper rather than reconstructed afterwards.

    Break by moving the route check in `probe_gateway` after
    `_admitted_probe`, or by returning from the check without its record.
    """
    with _run_store_survives_build() as kept, _credential_present(), \
            _endpoint_absent():
        assert e3_ladder._probe_gateway_from_env() is None, (
            "the environment named an endpoint, so this is not the no-route "
            "case the test claims")
        payload = e3_ladder.build(tmp_path)
        assert len(kept) == 1, (
            "build opened %d stores, so which one this test read is "
            "ambiguous" % len(kept))
        left_behind = _calibration_operations(
            kept[0].dsn, e3_ladder.STUDY_ROOT)

    probe = payload["gateway_probe"]

    assert probe["status"] == "no-route", (
        "a study with no endpoint reported a routed probe: %r" % probe)
    assert probe["admitted"] is False, (
        "build spent a calibration for a send it could not make: %r" % probe)
    assert probe["operation_id"] is None, (
        "an unadmitted probe names an operation: %r" % probe)
    assert probe["exposure_units"] == 0, (
        "an unadmitted probe took exposure: %r" % probe)
    assert "dispatch_state" not in probe, (
        "the probe dispatched with no route: %r" % probe)
    assert probe["credential_recorded"] is False

    assert payload["authority"]["ceilings"]["max_calibration"] == 1, (
        "the ceiling this property is about is no longer one: %r"
        % payload["authority"]["ceilings"])
    assert payload["store_verdict"]["operations_in_store"] > 0, (
        "the run admitted nothing at all, so the probe being absent is not "
        "evidence: %r" % payload["store_verdict"])
    assert left_behind == [], (
        "the no-route probe left a calibration operation in the store for a "
        "send that never happened: %r" % left_behind)


def test_a_resolved_route_still_reaches_the_admission(migrated_db):
    """The other side of the fix, so a free no-route cannot be bought by
    never sending: with a route in the environment the probe admits,
    dispatches, and settles exactly as before.

    Break by returning before the admission whenever the route came from the
    environment rather than from the caller.
    """
    from settlement.gateway import FakeGatewayAdapter

    with _bound_study(migrated_db) as study_root, _credential_present(), \
            _endpoint_present():
        record = e3_ladder.probe_gateway(
            migrated_db, study_root=study_root,
            gateway=FakeGatewayAdapter(text="OK"))

        assert record["admitted"] is True, (
            "a route was available and the probe still did not use it: %r"
            % record)
        assert record["status"] == "reachable", (
            "the routed probe did not confirm the route: %r" % record)
        assert record["exposure_units"] > 0, (
            "an admitted model-inference took no exposure, so no "
            "reservation happened: %r" % record)
        assert _calibration_operations(migrated_db, study_root), (
            "the admitted probe left no operation in the store")


# --- defect 3: the unit of `already_spent` --------------------------------


def _request(operation_id: str) -> ModelRequest:
    return ModelRequest(model="pinned-model",
                        messages=({"role": "user", "content": "x"},),
                        max_output_tokens=8, deadline_ms=1000,
                        operation_id=operation_id)


class _RefusingFirst:
    """Refuses at the store for `fail`, then really sends.

    A `PreGatewayRefusal` is the guard's marker for a request its delegate
    never put on the wire, so it is the one attempt that costs nothing.
    """

    def __init__(self, fail=("op-refused-a", "op-refused-b")):
        self.fail = set(fail)
        self.sent: list[str] = []

    def infer(self, request):
        if request.operation_id in self.fail:
            raise live.PreGatewayRefusal(
                "store refused %s" % request.operation_id)
        self.sent.append(request.operation_id)
        return ModelResponse(
            request.operation_id, "ok",
            {"providerMetadata": {"gateway": {"cost": 0}}},
            Usage(), "stop")


def test_a_refusal_that_never_reached_the_gateway_does_not_spend(
        migrated_db):
    """The unit, measured rather than read off the name.

    Both callers that pass `already_spent` pass a number derived by counting
    rows: `scripts/invl02_live.py:_output_already_spent` runs
    `SELECT COUNT(*) FROM operations WHERE id = ANY(...)`, and a prepare the
    store refuses inserts nothing, which is why the count the store takes
    and the count of attempts the guard keeps are not the same number.

    So `already_spent` counts store operations that went on the wire, and
    the property to pin is that a refusal which never reached the gateway
    does not move the counter the ceiling reads.

    Break by folding the refund into `dispatch_count` and letting the
    ceiling compare against attempts.
    """
    delegate = _RefusingFirst()
    guard = live.LiveGuard(delegate, pinned_model="pinned-model", ceiling=10,
                           already_spent=2, automatic_retries=0)

    for operation_id in ("op-refused-a", "op-refused-b", "op-sent"):
        try:
            guard.infer(_request(operation_id), evidence={"arm": "P1"})
        except live.PreGatewayRefusal:
            pass

    assert delegate.sent == ["op-sent"], (
        "the delegate reached the gateway for a request it refused: %r"
        % delegate.sent)
    assert guard.spent_dispatches == 3, (
        "two store refusals that never reached the gateway moved the "
        "counter the ceiling reads, so it is counting attempts and not "
        "sends: %r" % guard.guard_status())
    assert guard.is_ceiling_reached() is False, (
        "a ceiling of 10 was reached by 3 dispatches and 2 refusals")


def test_the_already_spent_seed_and_the_ceiling_share_one_currency(
        migrated_db):
    """The two ends of the counter, and the arithmetic that depends on them.

    `already_spent` seeds `dispatch_count` and `spent_dispatches` is what
    the ceiling compares against, so a seed and a ceiling in different units
    would not be comparable at all. With a ceiling of 3 and `already_spent`
    of 1, exactly two real sends remain and the third is refused. That is the
    arithmetic `s09_study_preflight.Budget` performs, and it is why the seed
    has to be a dispatch count.

    Break by making the ceiling compare against attempts, which lets a
    refusal cost budget the run never spent.
    """
    delegate = _RefusingFirst(fail=("op-refused-a",))
    guard = live.LiveGuard(delegate, pinned_model="pinned-model", ceiling=3,
                           already_spent=1, automatic_retries=0)

    for operation_id in ("op-refused-a", "op-sent-1", "op-sent-2"):
        try:
            guard.infer(_request(operation_id), evidence={"arm": "P1"})
        except live.PreGatewayRefusal:
            pass

    assert guard.is_ceiling_reached() is True, (
        "one prior send plus two real sends reached a ceiling of 3 and the "
        "guard says otherwise: %r" % guard.guard_status())

    with pytest.raises(live.LiveRefused) as caught:
        guard.infer(_request("op-sent-3"), evidence={"arm": "P1"})
    assert caught.value.reason == "study model-call ceiling 3 reached"
    assert delegate.sent == ["op-sent-1", "op-sent-2"], (
        "a refused send was dispatched against a reached ceiling: %r"
        % delegate.sent)


def test_a_replay_spends_nothing_in_that_currency(migrated_db):
    """The other half of the unit: a replay is an operation the store
    already holds, so re-reading it spends nothing.

    `_OutputGuard` refunds a replay by restoring `dispatch_count` to the
    value it held before the call. That refund is only correct because
    `dispatch_count` and `spent_dispatches` are the same currency at the
    moment of the restore; in different units the two would drift apart
    across a resume.

    Break by dropping the restore, which turns every replay into a fresh
    send against the ceiling.
    """
    from scripts import invl02_live as driver

    delegate = _RefusingFirst(fail=())
    delegate.replayed_operation_ids = {"op-replayed"}
    guard = driver._OutputGuard(
        delegate, pinned_model="pinned-model", ceiling=10, already_spent=0,
        automatic_retries=0)

    before = guard.spent_dispatches
    guard.infer(_request("op-replayed"), evidence={"arm": "P1"})
    guard.infer(_request("op-fresh"), evidence={"arm": "P1"})

    assert guard.spent_dispatches == before + 1, (
        "a replay and a fresh send should cost one dispatch between them: %r"
        % guard.guard_status())
    assert delegate.sent == ["op-replayed", "op-fresh"], (
        "the delegate was not called for both: %r" % delegate.sent)
    assert guard.guard_status()["replay_count"] == 1


def test_the_resume_evidence_path_counts_only_sends(tmp_path, migrated_db):
    """The concrete divergence, and the unit that settles it.

    `already_spent` has two derivations and they disagree. The store path
    runs `SELECT COUNT(*) FROM operations`, and a prepare the store refuses
    inserts no row, so it counts sends. The evidence fallback
    `_output_evidence_spent` counts ledger entries, and the ledger keeps a
    pre-gateway refusal as a record, so it counted refusals too. The entry
    carried `pre_gateway_refusal: True` from the N-203 repair and nothing
    ever read the flag, which is how the two paths drifted instead of the
    flag being load-bearing.

    So the unit is store operations that reached the wire, and a resume that
    seeds one more than the store holds burns ceiling the run never spent.
    Break by counting the refusal again.

    The two derivations are pinned to one literal rather than compared to
    each other, because a test that equates two derivations of a quantity
    passes when both are wrong together.
    """
    from scripts import invl02_live as driver

    freeze = driver.freeze_output(tmp_path)
    _write_prior_with_one_refusal_and_one_send(tmp_path, freeze)

    assert driver._output_evidence_spent(tmp_path, freeze) == 1, (
        "the resume evidence path counted a store refusal that never went "
        "on the wire, so it seeds already_spent above what the store holds "
        "and every later dispatch is refused early")


def _write_prior_with_one_refusal_and_one_send(out, freeze) -> None:
    """A prior bundle holding one refusal the store never recorded."""
    import json

    from experiments.ad01 import frontier
    from experiments.ad01 import live_construct as live

    def _entry(operation_id, refusal):
        record = frontier.make_evidence_record(
            "gateway-dispatch", operation_id, "unresolved", attempt=1,
            arm="P1", task_id="qual",
            input_digest=live.source_digest("x"),
            parse_outcome="transport-error")
        record.update({"operation_id": operation_id, "replay": False,
                       "durable_receipt": None,
                       "durable_receipt_identity": None,
                       "raw_response": None,
                       "pre_gateway_refusal": True if refusal else False})
        return record

    bundle = {
        "protocol": freeze,
        "protocol_id": freeze["protocol"],
        "study": freeze["study"],
        "study_root": freeze["study_root"],
        "run_id": freeze["run_id"],
        "source_identity": freeze["source_identity"],
        "freeze_digest": freeze["freeze_digest"],
        "status": "incomplete",
        "candidate_view": {
            "protocol": freeze["protocol"],
            "route": dict(freeze["route"]),
            "incumbent_control": None,
            "dispatch_count": 2,
            "physical_dispatch_count": 1,
            "replay_count": 0,
            "dispatches": [_entry("op-refused", True),
                           _entry("op-sent", False)],
            "durable_receipts": [],
        },
    }
    (out / "output-run.json").write_text(
        json.dumps(bundle, sort_keys=True, indent=1) + "\n")
