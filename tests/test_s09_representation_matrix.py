"""The three representations have never been compared against each other.

Expansion question 1 asks which representations a model can acquire and
execute. `s09_arm_parity` registers all three and `compare_arms` refuses
three arms of one kind, so the only comparison it offers is a pair, and only
the STEP arm had ever been paired with a test double. Two real arms had
never run in the same comparison; the third had no record constructor
outside its own test file.

These are the assertions that the fold holds: same decision in three
notations, same task, one query each, and any failure reported as its own
incomparability rather than as a zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import boolean_ast_policy
from experiments.ad01 import boolean_graph_policy
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_representation_matrix as matrix


def _conditions() -> parity.ComparisonConditions:
    return parity.ComparisonConditions(split="dev", seed=4, max_queries=8)


def test_the_three_records_carry_the_three_representations():
    registry = matrix.build_registry()

    assert registry.real_arm_names() == ("step", "ast", "graph")
    kinds = {arm.representation_kind for arm in
             (registry._arms[name] for name in registry.names)}
    assert kinds == set(parity.REAL_REPRESENTATION_KINDS)
    assert not any(registry._arms[name].is_test_double
                   for name in registry.names)


def test_the_ast_record_is_the_shape_its_own_loader_accepts():
    record = matrix.typed_ast_record()
    document, _root = boolean_ast_policy.load_policy(
        record, expected_policy_id="e1-typed-ast")

    assert document["policy_id"] == "e1-typed-ast"
    assert record["artifact"]["representation"] == "typed-ast"
    assert record["artifact"]["version"] == boolean_ast_policy._REPRESENTATION


def test_the_graph_record_is_the_shape_its_own_loader_accepts():
    boolean_graph_policy.load_policy(
        matrix.graph_policy_record(), expected_policy_id="e1-action-graph")

    with pytest.raises(boolean_graph_policy.GraphPolicyRefused):
        boolean_graph_policy.load_policy(
            {"policy_id": "x", "start": "nowhere", "nodes": {}},
            expected_policy_id="x")


def test_each_representation_runs_the_same_decision_under_one_budget():
    result = matrix.run_matrix(conditions=_conditions())

    assert result.comparable_arms == ("step", "ast", "graph"), \
        result.failed_reasons
    assert {c.representation_kind for c in result.cells} \
        == set(parity.REAL_REPRESENTATION_KINDS)
    for cell in result.cells:
        assert cell.queries_spent == 1, cell.as_dict()
        assert cell.turns_taken == 2, cell.as_dict()
        assert cell.score["n_queried"] == 1, cell.as_dict()


def test_the_three_representations_reach_the_same_score_on_the_same_task():
    """The point of the module: one decision, three notations, one outcome.

    Probe x=3, read the output, commit it. Each representation has to
    express that, and the world is seeded so the answer is the same either
    way. If the three disagree, the finding is which one and by how much,
    so the assertion is on the whole set agreeing and the test above names
    the cell that broke it.
    """
    result = matrix.run_matrix(conditions=_conditions())

    assert result.agreeing() == ("ast", "graph", "step"), \
        {c.arm_name: c.overall for c in result.cells}


def test_an_arm_that_cannot_execute_reports_its_own_reason():
    """A failed representation is a different finding from a low score.

    A graph whose node names an unknown field fails to load. It must come
    back as `incomparable` on that arm, carrying the loader's own reason,
    and it must not appear as an arm that ran and scored zero.
    """
    broken = matrix.graph_policy_record()
    broken["nodes"]["probe"]["arms"][0]["guard"] = {
        "field": "observed.nonexistent", "op": "eq", "value": 0}
    registry = matrix.build_registry({
        "step": matrix.step_policy_record(),
        "ast": matrix.typed_ast_record(),
        "graph": broken})

    result = matrix.run_matrix(registry=registry, conditions=_conditions())

    graph_cell = next(c for c in result.cells if c.arm_name == "graph")
    assert not graph_cell.comparable
    assert graph_cell.overall is None
    assert graph_cell.queries_spent is None
    assert graph_cell.reason
    assert result.failed_arms == ("graph",)
    assert set(result.comparable_arms) == {"step", "ast"}
    assert "graph" not in result.agreeing(), \
        "a failed cell must not join the agreement"
