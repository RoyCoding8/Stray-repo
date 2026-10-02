"""The ordering world has a STEP arm, and the world validates it.

`boolean_policy.choose_action` runs the bounded child and then checks the
action with `_validate_boolean_action`, so an ordering STEP program — whose
source is arbitrary Python and perfectly expressible — came back refused
with `probe target must be boolean.query`. Jev scored that a world binding
rather than an expressivity limit at 0.90, and the fix was for the second
world to validate its own actions rather than for the Boolean executor to
learn a second world.

So the ordering STEP arm is the world's, driven through the same `World`
value the graph uses. Two things are worth pinning: that it runs, and that
the binding is still real — `test_the_ordering_step_control_is_still_
refused_by_the_step_executor` in the graph module covers the second, and
this covers the first plus the balance of the matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_representation_matrix as matrix


def _conditions(seed: int = 4):
    return parity.ComparisonConditions(
        split="dev", seed=seed, max_queries=8, world="ordering")


def test_the_ordering_registry_carries_all_three_representations():
    registry = matrix.build_ordering_registry()

    assert set(registry.names) == {"step", "ast", "graph"}
    assert set(registry.real_arm_names()) == {"step", "ast", "graph"}
    assert {registry._arms[n].representation_kind for n in registry.names} \
        == set(parity.REAL_REPRESENTATION_KINDS)
    assert not any(registry._arms[n].is_test_double for n in registry.names)


def test_the_ordering_step_arm_runs_against_the_orders_own_rules():
    """A step arm that loads is not one that runs.

    Every pair of the three is compared, because `compare_arms` refuses
    three arms of one kind and a matrix where one arm silently fails would
    still report the other two agreeing.
    """
    registry = matrix.build_ordering_registry()

    for pair in (("step", "ast"), ("step", "graph"), ("ast", "graph")):
        result = parity.compare_arms(registry, pair, _conditions())

        assert result.status == "comparable", (
            pair, [i.as_dict() for i in result.incompatibilities])
        records = {r.arm_name: r for r in result.records}
        for name, record in records.items():
            assert record.queries_spent == 1, (pair, name)
            assert record.score is not None, (pair, name)


def test_all_three_agree_on_the_ordering_world():
    """Parity on a second world, which is the point of the whole exercise."""
    registry = matrix.build_ordering_registry()
    results = {}
    for pair in (("step", "ast"), ("step", "graph"), ("ast", "graph")):
        for record in parity.compare_arms(
                registry, pair, _conditions()).records:
            results[record.arm_name] = record.score["overall"]

    assert len(set(results.values())) == 1, results
