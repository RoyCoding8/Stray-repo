"""Lane K: the budget binds, and the decision reaches a real operation.

Two independent claims. The budget is finite and exceeding it is refused,
with exhaustion forcing a stop rather than a free pass. And the decision
travels: the target a policy names is the target that runs, and severing
the gate removes the effect, which is the only way to show the effect came
from the decision rather than from the schedule.
"""

from __future__ import annotations

import pytest

from experiments.ad01 import agenda_policy, selection


WORLD = 0


def _run(policy, authorized, **kwargs):
    return selection.run_investigations(
        selection.portfolio_for_world(WORLD), policy,
        selection.Allocation(authorized=authorized), world=WORLD, **kwargs)


def test_budget_cannot_be_exceeded():
    allocation = selection.Allocation(authorized=5)
    allocation.charge(4)
    assert allocation.remaining() == 1
    with pytest.raises(selection.BudgetExhausted):
        allocation.charge(2)
    assert allocation.spent == 4, "a refused charge still moved the spend"
    allocation.charge(1)
    assert allocation.remaining() == 0
    with pytest.raises(selection.BudgetExhausted):
        allocation.charge(1)


def test_a_refused_charge_leaves_the_envelope_untouched():
    allocation = selection.Allocation(authorized=10)
    for _ in range(3):
        with pytest.raises(selection.BudgetExhausted):
            allocation.charge(11)
    assert allocation.spent == 0
    assert allocation.remaining() == 10


def test_exhausting_the_budget_forces_a_stop():
    run = _run(agenda_policy.agenda_policy(), 40)

    assert run.stop_reason == "budget exhausted"
    assert run.yield_.resources_used <= 40
    assert run.yield_.resources_used > 40 - run.choices[-1].charge, (
        "the run stopped with %d of 40 units spent, so the budget did not "
        "actually bind" % run.yield_.resources_used)


def test_a_tighter_budget_yields_fewer_investigations():
    small = _run(agenda_policy.agenda_policy(), 20)
    large = _run(agenda_policy.agenda_policy(), 60)

    assert len(small.choices) < len(large.choices)
    assert small.yield_.resources_used <= 20
    assert large.yield_.resources_used > small.yield_.resources_used


def test_a_zero_budget_stops_immediately():
    run = _run(agenda_policy.agenda_policy(), 0)

    assert run.choices == ()
    assert run.executions == ()
    assert run.yield_.retained_behaviors == 0
    assert run.stop_reason == "budget exhausted"


def test_the_run_never_spends_past_the_envelope():
    for budget in (0, 1, 5, 13, 14, 20, 40):
        run = _run(agenda_policy.agenda_policy(), budget)
        assert run.yield_.resources_used <= budget, (
            "budget %d was exceeded: spent %d"
            % (budget, run.yield_.resources_used))
        assert run.yield_.resources_used == sum(c.charge for c in run.choices)


def test_decision_reaches_the_executed_operation():
    run = _run(agenda_policy.agenda_policy(), 40)

    assert run.executions, "no investigation was executed"
    for execution in run.executions:
        candidate = execution.choice.candidate
        assert execution.episode["task_id"] == candidate.target, (
            "the policy named %r but %r ran"
            % (candidate.target, execution.episode["task_id"]))
        lineage = execution.episode.get("lineage") or []
        assert lineage, "a development episode with no lineage ran nothing"
        assert lineage[0]["capability_id"] == candidate.capability_id
        assert execution.episode["check"]["verdict"] in (
            "preserved", "not_preserved", "invalid", "unknown")


def test_a_proposal_outside_the_portfolio_is_refused():
    """A policy cannot widen the portfolio by wishing."""
    class Rogue(agenda_policy.PortfolioPolicy):
        def propose(self, agenda):
            row = selection.Candidate("ad01-w0-transfer-sw-00", "software",
                                      "seed-sw-greedy", 2, 4)
            return self._proposal(row, "smuggled a protected-use target")

    run = _run(Rogue(), 40)

    assert run.choices == ()
    assert run.executions == ()
    assert run.stop_reason == "proposal outside the portfolio"


def test_severing_the_decision_removes_the_effect():
    live = _run(agenda_policy.agenda_policy(), 40)
    severed = _run(agenda_policy.agenda_policy(), 40, sever=True)

    assert live.yield_.retained_behaviors > 0
    assert live.yield_.held_out_reduction > 0
    assert severed.yield_.retained_behaviors == 0, (
        "severing the decision consumer left the retained behaviors intact, "
        "so they were not caused by the decision")
    assert severed.yield_.held_out_reduction == 0.0
    assert severed.held_out_ledger == ()
    for execution in severed.executions:
        assert execution.episode["disposition"] == "no-candidate"
        assert execution.episode["fallback"] == "incumbent"


def test_severing_still_charges_the_envelope():
    """A refused decision costs its unit. Otherwise refusing is free."""
    severed = _run(agenda_policy.agenda_policy(), 40, sever=True)

    assert severed.yield_.resources_used == sum(c.charge
                                                for c in severed.choices)
    assert severed.yield_.resources_used > 0
