r"""The menu gate has to be able to refuse.

`menu_answers_nothing` is live in four entry points, and three of them
stop a study before anything is dispatched. It decided `open` by
matching `method\s*=\s*[^,\n)]+` against the contract's rendered
prose, so it was grading a description of the binding rather than the
binding. `b9b7b4d` made that prose derived: it is now built from the
child's wrappers and read back with `inspect.signature`. The two
primitives `ddmin_reduce` and `greedy_reduce` declare `method=None` only
to check the name matches the strategy the entry is already named for,
and the renderer leaves that parameter unrendered and explains the
consequence in a note. The regex therefore did not match, and the menu
read `open: True` for the wrong reason. Render that parameter faithfully
as `method=None` and the gate refuses every study while the wrappers
genuinely supply no strategy.

These tests fix the direction of the error. A wrapper that answers the
strategy must be caught. One that does not must be let through, and the
real menu is that second case, so a gate that refuses everything passes
none of this.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import control_distinctness, method_exec

# A callee that takes the strategy the model is supposed to choose. It is
# the shape of `reducers.reduce_software` without the import, so the
# failure it produces is a gate failure and not a module failure.
STRATEGY_CALLEE = (
    "def reduce_software(task, oracle, method, max_queries=16):\n"
    "    return {'candidate': method, 'queries': max_queries}\n")


def _reducer_module() -> object:
    import types

    module = types.ModuleType("menu_gate_reducers")
    exec(compile(STRATEGY_CALLEE, "<menu-gate-reducers>", "exec"),
         module.__dict__)
    return module


def _with_callee(monkeypatch) -> None:
    """Make the child namespace resolve to the callee under test."""
    monkeypatch.setattr(method_exec, "_CHILD_NAMESPACE",
                        {"reducers": "menu_gate_reducers"})
    monkeypatch.setitem(sys.modules, "menu_gate_reducers",
                        _reducer_module())


def _contract(binding: str) -> dict:
    return {"version": method_exec.CHILD_CONTRACT_VERSION,
            "callables": {"reduce_software": {
                "returns": "dict with candidate and queries used",
                "origin": "test-supplied",
                "binding": binding}}}


def test_a_wrapper_that_supplies_the_strategy_is_refused(monkeypatch):
    """The defect: a binding whose wrapper answers the model.

    A callee that requires `method`, with a wrapper that gives it a
    default, is the menu answering itself. This is the direction the
    regex could not see, because the prose the renderer produces for
    this binding is a forwarded choice and mentions no default.
    """
    _with_callee(monkeypatch)
    source = ("def reduce_software(task, oracle, *, method='ddmin',"
              " max_queries=16):\n"
              "    return reduce_software(task, oracle, method, max_queries)\n")
    monkeypatch.setattr(
        method_exec, "_child_wrapper_source", lambda contract: source)

    verdict = control_distinctness.menu_answers_nothing(
        _contract("reducers.reduce_software"))

    assert verdict["defaulting_strategy"] == ["reduce_software"], verdict
    assert not verdict["open"], verdict
    assert "reduce_software" in verdict["refusal"], verdict


def test_the_same_wrapper_without_a_strategy_default_is_open(monkeypatch):
    """The other direction, on the same callee and the same binding.

    Without this, the test above passes for a gate that refuses
    everything. The only difference between the two wrappers is whether
    one supplies a value the model never chose.
    """
    _with_callee(monkeypatch)
    source = ("def reduce_software(task, oracle, *, max_queries=16,"
              " **kwargs):\n"
              "    return reduce_software(task, oracle, **kwargs)\n")
    monkeypatch.setattr(
        method_exec, "_child_wrapper_source", lambda contract: source)

    verdict = control_distinctness.menu_answers_nothing(
        _contract("reducers.reduce_software"))

    assert verdict["defaulting_strategy"] == [], verdict
    assert verdict["open"], verdict.get("refusal")
    assert "refusal" not in verdict, verdict


def test_a_strategy_defaulting_to_none_refuses_when_the_callee_requires_it(
        monkeypatch):
    """`None` is a value, not an absence, where the callee runs on it.

    This is the shape an honest rendering of a guarded parameter takes,
    and it is the one that decides whether a renderer change can stop
    every study. A callee that requires `method` runs on `None`, so the
    model never chose the strategy and the gate refuses.
    """
    _with_callee(monkeypatch)
    source = ("def reduce_software(task, oracle, *, method=None,"
              " max_queries=16):\n"
              "    return reduce_software(task, oracle, method, max_queries)\n")
    monkeypatch.setattr(
        method_exec, "_child_wrapper_source", lambda contract: source)

    verdict = control_distinctness.menu_answers_nothing(
        _contract("reducers.reduce_software"))

    assert verdict["defaulting_strategy"] == ["reduce_software"], verdict
    assert not verdict["open"], verdict


def test_the_real_menu_is_open_and_reads_no_prose():
    """The shipped tree, and proof the verdict came from the binding.

    The other three here substitute `_child_wrapper_source`, so nothing
    in this file is asserting that the real menu is open. This one is:
    a gate that refused every binding would be caught by the two above
    only if they are read together with it.
    """
    verdict = control_distinctness.menu_answers_nothing()

    assert verdict["open"], verdict.get("refusal")
    assert verdict["defaulting_strategy"] == [], verdict
    assert verdict["bound"], "the gate decided on an empty menu"
    # The prose is made to name a defaulted strategy for every entry. A
    # gate reading the binding is unmoved by it; the regex gate this
    # replaced refused on the strength of the text alone.
    poisoned = copy.deepcopy(method_exec.child_contract())
    for spec in poisoned["callables"].values():
        spec["signature"] = "reduce_software(task, oracle, method='ddmin')"
    assert control_distinctness.menu_answers_nothing(poisoned)["open"], (
        "the gate is still reading the rendered prose")