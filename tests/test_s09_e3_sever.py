"""E3's severing counterexample, run for real, and the store it does not reach.

Two claims, and the second is the one that costs E3 its wording.

The first is that severing the decision consumer removes the effect. It
does, at every world, budget and policy, and the severed trajectory is a
strict prefix of the connected one, so the control differs from the
treatment in what ran and not in what was decided. A control that changed
the decisions would be measuring something else.

The second is the load-bearing one. E3's decisions now reach a real
admitted operation. `run_investigations` takes a dsn, so
`selection._run_development` builds its `DecisionConsumer` against a
store and admits each decision as a broker operation, and the receipt
comes back out of the receipts table by SELECT.

`test_every_e3_decision_reaches_an_admitted_operation` pins that. It
ran the other way for a while, asserting the operations table stayed
empty, and it was inverted when the store was wired in. A study that
reported "decisions reach real admitted operations" while the store
stayed empty would be reporting a code path.

The store tests below separate the two claims. The bindings show the
store admits an E3 decision and hands back an operation id and a
receipt identity. The inverted test above is what keeps the
distinction honest, by counting only what the run itself wrote.
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


WORLDS = selection.WORLDS
GRID_BUDGETS = (14, 20, 40, 60)


def _run(policy, world, budget, *, sever=False):
    return selection.run_investigations(
        selection.portfolio_for_world(world), policy(),
        selection.Allocation(authorized=budget), world=world, sever=sever)


def _arms():
    return {"agenda": agenda_policy.agenda_policy,
            "control": agenda_policy.fixed_policy}


def _identities(run):
    return [choice.candidate.identity for choice in run.choices]


# --- the severing counterexample ------------------------------------------


def test_severing_the_consumer_removes_every_retained_behavior():
    """The treatment's retained behaviours are the effect that must vanish.

    Fails if the `if agenda.sever:` branch in `_run_development` stops
    swapping in the disconnected consumer, or if a severed episode ever
    reaches `dev_episode` and retains. Measured across the whole grid
    rather than at one budget, because an effect that survives at one
    budget is an effect the treatment can still claim.
    """
    for name, make in _arms().items():
        for world in WORLDS:
            for budget in GRID_BUDGETS:
                connected = _run(make, world, budget)
                severed = _run(make, world, budget, sever=True)
                if connected.yield_.retained_behaviors:
                    assert severed.yield_.retained_behaviors == 0, (
                        "%s world %d budget %d: severing left %d retained "
                        "behaviors out of the connected arm's %d"
                        % (name, world, budget,
                           severed.yield_.retained_behaviors,
                           connected.yield_.retained_behaviors))


def test_severing_empties_the_held_out_ledger_and_the_diagnoses():
    """Held-out quality and diagnosis are the other two yields.

    A severed run that kept its ledger would be scoring retained
    behaviours it never built. Fails if `_run_development` returns an
    observation for a refused decision, which is what populates both.
    """
    for name, make in _arms().items():
        for world in WORLDS:
            for budget in GRID_BUDGETS:
                severed = _run(make, world, budget, sever=True)
                assert severed.held_out_ledger == (), (
                    "%s world %d budget %d: a severed run still holds a "
                    "held-out ledger" % (name, world, budget))
                assert severed.yield_.held_out_reduction == 0.0
                assert severed.yield_.diagnoses_correct == 0, (
                    "%s world %d budget %d: a severed run diagnosed %d times "
                    "with no operation to diagnose"
                    % (name, world, budget, severed.yield_.diagnoses_correct))
                for execution in severed.executions:
                    assert execution.episode["disposition"] == "no-candidate"
                    assert execution.episode["fallback"] == "incumbent"
                    assert "disconnected" in execution.episode[
                        "fallback_reason"], (
                        "a severed episode refused for a reason other than the "
                        "severed consumer: %r"
                        % (execution.episode["fallback_reason"],))


def test_the_severed_trajectory_is_a_prefix_of_the_connected_one():
    """The control changes what ran, not what was decided.

    This is what makes the counterexample a control rather than a second
    experiment. If severing altered the policy's choices, a difference in
    yield would be a difference in policy rather than a difference in
    execution. Fails if `_run_development` mutates the candidate, or if a
    refused decision changes what the policy observed next.
    """
    for name, make in _arms().items():
        for world in WORLDS:
            for budget in GRID_BUDGETS:
                connected = _identities(_run(make, world, budget))
                severed = _identities(
                    _run(make, world, budget, sever=True))
                assert severed == connected[:len(severed)], (
                    "%s world %d budget %d: the severed run chose something the "
                    "connected run did not choose at the same step"
                    % (name, world, budget))


def test_a_severed_decision_is_still_charged():
    """Refusing must not be free, or the envelope stops binding.

    A severed run that under-charged would let a policy propose past the
    point the connected one stops, and the two would no longer share a
    trajectory. Fails if the charge moves out of `run_investigations` into
    the admitted path, or if a refusal is treated as costing nothing.
    """
    for world in WORLDS:
        for budget in GRID_BUDGETS:
            severed = _run(agenda_policy.agenda_policy, world, budget,
                           sever=True)
            connected = _run(agenda_policy.agenda_policy, world, budget)
            assert severed.yield_.resources_used == sum(
                choice.charge for choice in severed.choices)
            shared = min(len(severed.choices), len(connected.choices))
            assert severed.yield_.resources_used == sum(
                choice.charge for choice in connected.choices[:shared]), (
                "world %d budget %d: the severed arm spent %d over its %d "
                "shared decisions against the connected arm's %d"
                % (world, budget, severed.yield_.resources_used, shared,
                   sum(choice.charge
                       for choice in connected.choices[:shared])))


def test_the_recorded_control_reports_what_was_run():
    """The evidence is a record of an executed run, not a claim.

    Fails if `sever_control` recomputes a severed arm from a connected
    run, which is the failure mode that would have let the original
    retracted sentence stand. The severed arm's own yields are the
    check: a control that ran the connected policy twice would report
    the connected numbers, and those differ.
    """
    control = e3.sever_control(worlds=(0,), budgets=(14, 40))

    assert control["cells"], "the control recorded no cells"
    for row in control["cells"]:
        assert row["severed"]["executed"] is True, (
            "cell %s records a severed arm that was not executed"
            % (row["cell"],))
        assert row["severed"]["severed"] is True
        assert row["connected"]["severed"] is False
        assert set(row["connected"]) >= {"yield", "dispositions",
                                          "stop_reason", "choices"}
        assert set(row["severed"]) >= {"yield", "dispositions",
                                       "stop_reason", "choices"}
    effectful = [row for row in control["cells"]
                 if row["connected_had_an_effect"]]
    assert effectful, (
        "no cell had an effect to vanish, so the control is vacuous")
    for row in effectful:
        assert row["vanished"], (
            "cell %s: the effect survived severing" % row["cell"])
        assert row["severed_is_prefix"], (
            "cell %s: the severed run diverged from the connected one"
            % row["cell"])
    assert control["effect_vanished_in_every_cell"]
    assert control["severed_is_prefix_in_every_cell"]


def test_the_control_reports_a_severed_arm_the_connected_arm_could_not_be():
    """The severed yields differ from the connected ones where it matters.

    Guards against a control whose two arms are the same run recorded
    twice. Where the connected arm retained something, the severed arm
    must report none, and a run that kept the ledger must report none.
    Fails if the severed arm's numbers are copied from the connected one.
    """
    control = e3.sever_control(worlds=(0,), budgets=(40,))

    for row in control["cells"]:
        severed = row["severed"]["yield"]
        if row["connected_had_an_effect"]:
            assert severed["retained_behaviors"] == 0
            assert severed["held_out_reduction"] == 0.0
            assert row["severed"]["held_out_rows"] == 0
        assert row["severed"]["choices"] <= row["connected"]["choices"]


# --- the store E3 does not reach ------------------------------------------


def test_every_e3_decision_reaches_an_admitted_operation(migrated_db):
    """E3's decisions land in the store. This is the inverted pin.

    It ran the other way for a reason. `run_investigations` took no
    dsn, so `_run_development` built a `DecisionConsumer` with no store
    and every candidate it could offer was a `SEED_CAPABILITIES` id, so
    `trajectory._run_member` short-circuited to `seeds.run_seed` and a
    full E3 run left the operations table empty. That was a defect, and
    the handoff forbids "an agenda log" in its place.

    It now guards the opposite and stronger claim: the operations are
    written by the E3 path itself, not by a witness that bound the
    decisions afterwards. `operations_written_by_the_run` is measured
    across the run, so a counterfactual that admits the same decisions
    outside `run_investigations` scores zero here.

    Fails if `run_investigations` stops threading the store, if the
    broker refuses the operation payload, or if a run is credited with
    operations some other code path wrote.
    """
    run = e3.store_witness(migrated_db, world=0, budget=40)
    decided = run["run_decisions"]

    assert decided, (
        "the run made no decisions, so the test is asserting nothing about "
        "a path that never ran")
    assert run["operations_written_by_the_run"] == len(decided), (
        "E3 made %d decisions and wrote %d operations; every decision must "
        "reach one admitted operation, written by the E3 path itself"
        % (len(decided), run["operations_written_by_the_run"]))

    receipts = {row["operation_id"] for row in run["receipts"]
                if row["outcome"] == "success"}
    unsettled = [record["operation_id"] for record in run["bindings"]
                 if record["operation_id"] not in receipts]
    assert not unsettled, (
        "%d admitted operations never settled with a receipt: %r. A prepared "
        "operation is not a decision that reached the store; only a "
        "dispatched one leaves a receipt behind"
        % (len(unsettled), unsettled))
    assert len(run["receipts"]) == len(decided), (
        "E3 made %d decisions and the receipts table holds %d for them; one "
        "receipt per decision is the claim"
        % (len(decided), len(run["receipts"])))


def test_every_admitted_decision_becomes_a_store_operation(migrated_db):
    """The store admits what the agenda decided, and names it.

    Fails if the operation payload is refused by the broker's own effect
    validation, or if the readback returns no receipt for a decision the
    store accepted.
    """
    run = e3.store_witness(migrated_db, world=0, budget=40)

    assert run["admitted_decisions"], "the run made no decisions"
    assert run["refused_operations"] == [], (
        "the store refused %d decisions: %r"
        % (len(run["refused_operations"]), run["refused_operations"]))
    for bound in run["bindings"]:
        assert bound["operation_id"], "a decision was bound to no operation"
        assert bound["receipt_identity"], (
            "operation %s settled with no receipt identity"
            % bound["operation_id"])
        assert bound["dispatch_state"] == "observed", (
            "operation %s is %r, not observed"
            % (bound["operation_id"], bound["dispatch_state"]))
        assert bound["settled"] is True


def test_the_receipt_read_back_carries_the_decision_the_policy_made(
        migrated_db):
    """The receipt content, not the intent, names the decision.

    Compared against `run_decisions`, which comes off the policy's own
    choices, and not against the binding that produced the receipt. A
    test that compared a receipt with its own binding would pass even
    when the store holds the wrong decision, because both would be
    derived from the same call.

    Fails if the binding is recomputed from the run rather than read out
    of the receipts table, and fails if the bound operation names a
    decision the policy did not make.
    """
    run = e3.store_witness(migrated_db, world=0, budget=40)

    by_receipt = {row["receipt_identity"]: row for row in run["receipts"]}
    assert by_receipt, "no receipt was read back from the store"
    assert run["bindings"], "no decision was bound to an operation"
    for bound in run["bindings"]:
        row = by_receipt.get(bound["receipt_identity"])
        assert row is not None, (
            "receipt %s was reported bound but is not in the store"
            % bound["receipt_identity"])
        assert row["operation_id"] == bound["operation_id"]
        decided = row["content"]["payload"]["decision"]
        original = run["run_decisions"][bound["seq"]]
        assert (decided["target"], decided["capability_id"],
                decided["max_queries"]) == (
                    original["target"], original["capability_id"],
                    original["max_queries"]), (
            "receipt %s names %r while the policy chose %r"
            % (bound["receipt_identity"], decided, original))


def test_every_sequenced_decision_is_bound_to_its_own_receipt(migrated_db):
    """The binding is one-to-one and in order, not just existent.

    A witness that bound every decision to the first operation would
    satisfy every other assertion in this file. Fails if the binding
    loses a decision, duplicates one, or reorders them.
    """
    run = e3.store_witness(migrated_db, world=0, budget=40)

    assert run["run_decisions"], "the run made no decisions"
    assert [b["seq"] for b in run["bindings"]] == \
        list(range(len(run["run_decisions"]))), (
        "the bound sequence is %r against %d decisions"
        % ([b["seq"] for b in run["bindings"]], len(run["run_decisions"])))
    assert len({b["operation_id"] for b in run["bindings"]}) == \
        len(run["bindings"]), "two decisions share one operation id"
    for bound, decided in zip(run["bindings"], run["run_decisions"]):
        assert bound["target"] == decided["target"], (
            "seq %d was bound to %r but the policy chose %r"
            % (decided["seq"], bound["target"], decided["target"]))


def test_a_severed_run_leaves_no_store_operation(migrated_db):
    """Ties the two halves: the severed arm has nothing to bind.

    It counts the operations table across the run rather than reading
    the witness's own report of itself. A witness that filtered a
    severed run's rows out of its own return value would satisfy a
    check on that return value, so the count here is what the store
    holds afterwards.

    Fails if a severed decision leaks an operation, which would mean the
    sever counterexample and the store witness are measuring different
    things. The severed run's decisions are recorded as refused, not
    bound, so the two files agree on which decisions happened.
    """
    from settlement import db

    def _operations() -> int:
        with db.connect(migrated_db) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM operations")
                total = cur.fetchone()[0]
            conn.commit()
        return int(total)

    before = _operations()
    run = e3.store_witness(migrated_db, world=0, budget=40, sever=True)
    after = _operations()

    assert after == before, (
        "a severed run wrote %d operations into the store; the control "
        "condition must admit nothing" % (after - before))
    assert run["operations_written_by_the_run"] == 0
    assert run["admitted_decisions"] == [], (
        "a severed run reported %d admitted decisions"
        % len(run["admitted_decisions"]))
    assert run["bindings"] == []
    assert run["receipts"] == [], (
        "a severed run read back %d receipts" % len(run["receipts"]))
    assert run["refused_decisions"], (
        "the severed run recorded no refused decisions either, so the "
        "control condition was not exercised")
    for refused in run["refused_decisions"]:
        assert refused["operation_id"] == "", (
            "a refused decision was given an operation id: %r" % (refused,))
        assert "disconnected" in refused["fallback_reason"]


def test_the_witness_reads_the_store_rather_than_recomputing(migrated_db):
    """Delete the rows and the witness reports nothing.

    The strongest available check that the evidence is a readback. A
    witness built from the run object alone would still report operation
    ids and receipt identities after the store was emptied.
    """
    from settlement import db

    dsn = migrated_db
    run = e3.store_witness(dsn, world=0, budget=40)
    assert run["receipts"], "nothing to read back"

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE receipts CASCADE")
        conn.commit()
    after = e3.read_back(dsn, [bound["operation_id"]
                               for bound in run["bindings"]])

    assert after == [], (
        "the readback still reports %d receipts against an emptied store"
        % len(after))


def test_measure_freeze_still_holds_for_the_control(migrated_db):
    """A control run is under the same frozen measure set as the ladder.

    Fails if the sever control reports a yield the frozen digest does not
    cover, which is how a second, unfrozen column would enter the study.
    """
    control = e3.sever_control(worlds=(0,), budgets=(14,))
    run = e3.store_witness(migrated_db, world=0, budget=14)

    assert control["measure_digest"] == selection.FROZEN_MEASURE_DIGEST
    assert run["measure_digest"] == selection.FROZEN_MEASURE_DIGEST
    for cell in control["cells"]:
        for arm in ("connected", "severed"):
            assert set(cell[arm]["yield"]) == set(selection.YIELD_MEASURES), (
                "the %s arm reports %r against the frozen %r"
                % (arm, sorted(cell[arm]["yield"]),
                   sorted(selection.YIELD_MEASURES)))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
