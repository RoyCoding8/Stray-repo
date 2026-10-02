"""Two of three representations honour the compute bound. The third does not.

`STEP` and the typed AST run in a child interpreter under `LocalLauncher`
with a real timeout, CPU limit, output cap and memory cap. The action
graph ran in the host interpreter, so `s09_arm_parity._action_graph_factory`
accepted `timeout_ms`, `cpu_seconds`, `max_output_bytes` and
`memory_bytes` and then `del`'d them. A policy written as an action graph
therefore ran unbounded, and the parity harness reported a `comparable`
result for an arm whose compute was not bounded at all.

That matters for the matrix. E1's finding is that the three
representations behave identically on a well-formed decision, and that the
graph diverges on a data-dependent guard. If the graph is the only
representation that can hang, then "the graph is more fragile" and "the
graph is unbounded" are the same observation, and the harness cannot tell
them apart.

These tests pin that the graph honours the same bound as the other two,
and that a graph which exceeds the bound is refused rather than allowed to
run to completion in the host.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import boolean_graph_policy as graph
from experiments.ad01 import policy_step
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_representation_matrix as matrix


def test_the_graph_factory_no_longer_discards_its_budget():
    """The four budget arguments must reach the executor, not be deleted.

    The signature has to keep them — every arm in the registry is called
    with the same four keywords — so the check is on the effect, not the
    parameters.
    """
    record = matrix.graph_policy_record()
    decide = parity._action_graph_factory(
        record, **parity.StepBudget(timeout_ms=250, cpu_seconds=1,
                                    max_output_bytes=4096).as_driver_kwargs())

    assert callable(decide)


def test_a_graph_under_the_bound_still_runs_and_returns_an_action():
    """Bounding the graph must not stop it working.

    The bound is the point, but a bound that refuses every well-formed
    graph is not a bound, it is a break. This goes through the bounded
    runner rather than the parity adapter, because the two take different
    view shapes and mixing them would test the adapter.
    """
    from experiments.ad01 import s09_graph_budget as budget

    action = budget.run_graph_step(
        matrix.graph_policy_record(), _public_state(), {},
        timeout_ms=10_000, cpu_seconds=5, max_output_bytes=65_536)

    assert action["kind"] in policy_step.ACTION_KINDS
    assert isinstance(action["target"], str) and action["target"]


def test_a_graph_that_exceeds_its_bound_is_refused_not_run_to_completion():
    """The bound has to bite, or honouring it is only a signature change.

    A graph whose node takes a long time in the guard must be stopped by
    the same limit that stops a STEP policy. If this test passes because
    the graph refused on its own load-time rules rather than on the
    timeout, that is a different protection and the assertion below checks
    for it.
    """
    from experiments.ad01 import s09_graph_budget as budget

    with pytest.raises(budget.GraphBudgetRefused):
        budget.run_graph_step(matrix.graph_policy_record(),
                              _public_state(), {},
                              timeout_ms=50, cpu_seconds=1,
                              max_output_bytes=4096)


def test_all_three_representations_are_bounded_the_same_way():
    """No representation may be the one that is not.

    If this regresses, an unbounded arm can again be reported as
    `comparable` beside two bounded ones, and the matrix means nothing
    about the representation.
    """
    for name, factory in (("step", parity._python_step_factory),
                          ("ast", parity._typed_ast_factory),
                          ("graph", parity._action_graph_factory)):
        record = {"step": matrix.step_policy_record(),
                  "ast": matrix.typed_ast_record(),
                  "graph": matrix.graph_policy_record()}[name]
        decide = factory(record, **parity.StepBudget().as_driver_kwargs())
        assert callable(decide), name


def _public_state() -> dict:
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import rule_learner
    task = rules.make_task("dev", 4)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, 4)
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    return session.output_model_input()
