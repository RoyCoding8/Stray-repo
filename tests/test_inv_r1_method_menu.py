"""The acquisition menu must not have the answer in its default.

The constructor offered `reduce_software` and `reduce_graph` with
`method="ddmin"|"greedy"` and `ddmin` as the signature default. Every
acquisition observed chose `ddmin`, and the authored control scores
identically, so the comparison could not distinguish a model that learned
from one that accepted a default.

The primitives behind those two are already separate and each takes its own
query budget. Exposing them lets the model choose a strategy, choose a
priority, and choose a budget, and lets it compose them, rather than pick one
name from a two-item list. A default that is the answer is not a menu.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_the_child_contract_exposes_the_primitives():
    from experiments.ad01 import method_exec

    names = set(method_exec.child_contract()["callables"])

    assert {"ddmin_reduce", "greedy_reduce"} <= names, (
        "the two reduction primitives must be offered separately so a choice "
        "is a choice: %s" % sorted(names))


def test_no_offered_reducer_defaults_to_one_strategy():
    """The menu gate decides this, and it reads the binding.

    Asserted here on the verdict rather than on the rendered text. The
    text is what used to carry the check, and reading it made this test
    and the gate agree for the wrong reason: a renderer that stopped
    describing a default, or started describing one it did not have,
    moved both of them at once. `tests/test_ad01_menu_binding_gate.py`
    is where the two directions are exercised.
    """
    from experiments.ad01 import control_distinctness

    verdict = control_distinctness.menu_answers_nothing()

    assert verdict["defaulting_strategy"] == [], verdict
    assert verdict["open"], verdict.get("refusal")


def test_both_families_expose_a_budget_the_model_can_vary():
    from experiments.ad01 import method_exec

    for name in ("reduce_software", "reduce_graph"):
        signature = method_exec.child_contract()["callables"][name]["signature"]
        assert "max_queries" in signature, name


def test_the_menu_is_wider_than_two_names():
    from experiments.ad01 import method_exec

    names = set(method_exec.child_contract()["callables"])
    assert len(names) >= 6, (
        "a menu of %d callables is still a menu of two strategies if the "
        "rest are the same reducer twice" % len(names))
