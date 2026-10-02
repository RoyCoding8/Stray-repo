"""N-51: E3's decisions reach admitted operations the store settled.

The handoff (WORKER-STAGE-09-PARALLEL-EXPANSION.md line 73) requires
decisions to reach real admitted operations rather than appear only in
an agenda log. They did not. `run_investigations` took no dsn, so
`selection._run_development` built a `DecisionConsumer` with no store,
and `operations_in_store` counted nothing a run of the study wrote. A
full connected run at budget 40 opened zero database connections and
wrote zero rows.

This file covers the wiring itself, one link at a time, so a regression
names the link that broke. `tests/test_s09_e3_sever.py` keeps the
control-condition half: that a severed run still admits nothing.

Every assertion here is proved to fail by breaking the link it guards.
The links are, in order: the run receives a store; the run is given
none; the recorder admits an operation; the operation is dispatched;
the receipt is read back by SELECT rather than recomputed; and the
receipt carries the decision the policy actually made.

What is deliberately not asserted: that the numbers change. Wiring the
store does not move a single one of the four frozen measures, and a test
that required it to would be asserting a bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import agenda_policy, selection
from experiments.ad01 import s09_e3_selection as e3


def _operations(dsn: str) -> int:
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM operations")
            total = cur.fetchone()[0]
        conn.commit()
    return int(total)


def _receipt_rows(dsn: str) -> int:
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM receipts")
            total = cur.fetchone()[0]
        conn.commit()
    return int(total)


def _connected(dsn: str, budget: int = 40) -> selection.InvestigationRun:
    return selection.run_investigations(
        selection.portfolio_for_world(0), agenda_policy.agenda_policy(),
        selection.Allocation(authorized=budget), world=0, dsn=dsn)


# --- the store is inside the run ------------------------------------------


def test_a_run_given_no_store_writes_nothing(migrated_db):
    """The no-dsn caller still gets the run it asked for.

    `dsn` is optional on purpose, so this is the case a regression in
    the default path would break first. Fails if the recorder starts
    building itself without a dsn, or if a store-free run begins
    opening connections it was never given.
    """
    before = _operations(migrated_db)

    run = selection.run_investigations(
        selection.portfolio_for_world(0), agenda_policy.agenda_policy(),
        selection.Allocation(authorized=40), world=0)

    assert _operations(migrated_db) == before, (
        "a run given no dsn still wrote %d operations"
        % (_operations(migrated_db) - before))
    assert run.operations == ()
    assert run.recorder is None


def test_a_run_given_a_store_records_one_operation_per_decision(migrated_db):
    """The link the defect was: the store is reachable from the run.

    Fails if `run_investigations` stops threading `dsn` into
    `_run_development`, or if a decision is charged and executed without
    ever reaching `DecisionRecorder.record`.
    """
    run = _connected(migrated_db)

    assert run.choices, "the run made no decisions to record"
    assert len(run.operations) == len(run.choices), (
        "E3 made %d decisions and recorded %d operations"
        % (len(run.choices), len(run.operations)))
    assert [record["seq"] for record in run.operations] == \
        list(range(len(run.choices))), (
        "the recorded sequence is %r against %d decisions"
        % ([r["seq"] for r in run.operations], len(run.choices)))


def test_a_refused_operation_is_recorded_rather_than_dropped(migrated_db,
                                                             monkeypatch):
    """A decision the store rejects is a result, not a silence.

    An unrecorded refusal would let a run report decisions that no
    operation carries, which is the defect in a thinner form. Fails if
    `record` swallows a non-admitted `ensure_operation` result, or if
    the run's operation count stops accounting for refusals.
    """
    from settlement import broker
    from settlement.common import CommandResult, ResultCode

    def refused(dsn, **kwargs):
        return CommandResult(code=ResultCode.INVALID_INPUT,
                             request_id=kwargs.get("operation_id", ""),
                             detail="refused for the test", data={})

    monkeypatch.setattr(broker, "ensure_operation", refused)
    run = _connected(migrated_db)

    assert run.refusals, (
        "the store refused every operation and the run recorded no "
        "refusal; a decision nobody admitted must still be reported")
    assert run.operations == (), (
        "a refused operation was recorded as settled: %r"
        % (run.operations,))
    assert len(run.refusals) == len(run.choices)
    assert all("refused for the test" in row["detail"]
               for row in run.refusals), (
        "the refusals do not carry the store's reason: %r"
        % (run.refusals,))
    assert all(row["settled"] is False for row in run.refusals)


# --- the receipt is read back, not recomputed -----------------------------


def test_the_receipt_comes_out_of_the_database_by_select(migrated_db):
    """The strongest available check that a receipt is evidence.

    Empty the receipts table after the run and the readback reports
    nothing. A readback that recomputed what the admission call was
    handed would still report five receipts against an empty table.
    """
    from settlement import db

    dsn = migrated_db
    run = _connected(dsn)
    operation_ids = [record["operation_id"] for record in run.operations]
    assert operation_ids, "the run recorded no operations"
    assert e3.read_back(dsn, operation_ids), (
        "nothing was read back before the table was emptied")

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE receipts CASCADE")
        conn.commit()

    assert e3.read_back(dsn, operation_ids) == [], (
        "the readback still reports receipts against an emptied "
        "receipts table")


def test_the_stored_receipt_carries_the_policy_s_own_decision(migrated_db):
    """The row in the store names what the policy chose.

    Compared against `run.choices`, which comes off the policy and is
    never written to the store, and never against the record that
    produced the receipt. Comparing a receipt to the binding that made
    it is a row against itself, and would pass with the wrong decision
    stored.
    """
    dsn = migrated_db
    run = _connected(dsn)
    operation_ids = [record["operation_id"] for record in run.operations]
    rows = {row["operation_id"]: row
            for row in e3.read_back(dsn, operation_ids)}

    assert rows, "no receipt came back from the store"
    for record in run.operations:
        row = rows.get(record["operation_id"])
        assert row is not None, (
            "operation %s settled with no receipt in the store"
            % record["operation_id"])
        assert row["outcome"] == "success", (
            "operation %s settled %r"
            % (record["operation_id"], row["outcome"]))
        stored = row["content"]["payload"]["decision"]
        chosen = run.choices[record["seq"]].candidate
        assert (stored["target"], stored["capability_id"],
                stored["max_queries"]) == (
                    chosen.target, chosen.capability_id,
                    chosen.max_queries), (
            "receipt for %s names %r while the policy chose %s/%s"
            % (record["operation_id"], stored, chosen.capability_id,
               chosen.max_queries))


def test_two_runs_do_not_read_each_other_s_receipts(migrated_db):
    """Each run's operations are its own.

    Two runs sharing one campaign name would give them the same
    operation ids, and the second would read the first's receipts as
    though they were its own. Fails if the default campaign name stops
    being unique per run.
    """
    dsn = migrated_db
    first = _connected(dsn, budget=14)
    second = _connected(dsn, budget=14)

    first_ids = {r["operation_id"] for r in first.operations}
    second_ids = {r["operation_id"] for r in second.operations}

    assert first_ids and second_ids, "a run recorded no operations"
    assert not (first_ids & second_ids), (
        "two runs share %d operation ids: %r"
        % (len(first_ids & second_ids), sorted(first_ids & second_ids)))
    read = e3.read_back(dsn, sorted(second_ids))
    assert {row["operation_id"] for row in read} == second_ids


# --- the science did not move --------------------------------------------


def test_wiring_the_store_leaves_the_frozen_measures_alone(migrated_db):
    """The same four numbers with and without a store.

    This is the constraint that makes the repair safe. The defect was
    about where execution is recorded, so a store must not change what
    is decided. Fails if the recorder alters a charge, a target, a
    depth or an episode disposition, and it is the test that would
    catch a store that quietly changed the study.
    """
    dsn = migrated_db
    with_store = _connected(dsn, budget=40)
    without_store = selection.run_investigations(
        selection.portfolio_for_world(0), agenda_policy.agenda_policy(),
        selection.Allocation(authorized=40), world=0)

    assert with_store.yield_.as_dict() == without_store.yield_.as_dict(), (
        "the frozen measures moved when a store was attached: %r against %r"
        % (with_store.yield_.as_dict(), without_store.yield_.as_dict()))
    assert [c.candidate.identity for c in with_store.choices] == \
        [c.candidate.identity for c in without_store.choices], (
        "the store changed which investigations were chosen")
    assert with_store.stop_reason == without_store.stop_reason
    assert with_store.measure_digest == without_store.measure_digest == \
        selection.FROZEN_MEASURE_DIGEST


def test_the_recorded_decision_is_the_one_the_run_made(migrated_db):
    """The store holds the decision, not a variant of it.

    Yield equality is a weak guard here, because a store attached after
    a decision is made cannot change what that decision produced, so a
    recorder that quietly altered the candidate would pass every
    measurement unchanged. This compares each record against the
    candidate the run actually charged and executed.

    Fails if the recorder edits a candidate before admitting it, or if
    the record's charge stops being the charge the envelope saw.
    """
    run = _connected(migrated_db, budget=40)

    assert run.operations, "the run recorded no operations"
    for record, choice in zip(run.operations, run.choices):
        candidate = choice.candidate
        assert record["target"] == candidate.target, (
            "seq %d recorded target %r but the run chose %r"
            % (record["seq"], record["target"], candidate.target))
        assert record["capability_id"] == candidate.capability_id, (
            "seq %d recorded capability %r but the run chose %r"
            % (record["seq"], record["capability_id"],
               candidate.capability_id))
        assert record["max_queries"] == candidate.max_queries, (
            "seq %d recorded max_queries %r but the run used %r; the store "
            "must hold the decision the envelope was charged for"
            % (record["seq"], record["max_queries"], candidate.max_queries))
        assert record["charge"] == choice.charge == candidate.cost(), (
            "seq %d recorded charge %r against the run's %r"
            % (record["seq"], record["charge"], choice.charge))


def test_the_study_still_writes_no_operations_of_its_own_evidence(
        migrated_db, tmp_path):
    """The ladder and the sever control are measurements, not runs.

    `crossover` reads the frozen measure set across the budget ladder
    and `sever_control` runs both arms. Neither is an E3 execution, so
    neither may open a store or leave a row, and a reviewer reading
    `e3-crossover.json` must be able to trust it says only what it ran.

    Fails if the study's measurement functions acquire a dsn they were
    never given, or start recording decisions of their own.
    """
    dsn = migrated_db
    before_ops, before_receipts = _operations(dsn), _receipt_rows(dsn)

    control = e3.sever_control(worlds=(0,), budgets=(14,))

    assert control["cells"], "the control recorded no cells"
    assert _operations(dsn) == before_ops, (
        "the sever control wrote %d operations"
        % (_operations(dsn) - before_ops))
    assert _receipt_rows(dsn) == before_receipts, (
        "the sever control wrote %d receipts"
        % (_receipt_rows(dsn) - before_receipts))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
