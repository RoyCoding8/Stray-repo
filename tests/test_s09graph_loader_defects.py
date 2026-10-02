"""Two defects in the action-graph loader, found while qualifying it.

Neither is a representation claim. The first is a way a record that was
admitted once could keep steering a policy after admission, which is the
property the sibling suite assumes when it varies a graph and reads the
episode. The second is a guard operator that is advertised and then refused
for every possible value. A graph that leaks its own record is not a graph
interpreter in the sense the other suite needs, and an advertised operator
that never loads is a label a reader will trust and a loader will refuse.

The first is fixed in `boolean_graph_policy._parse_action`. The second is
not, because fixing it changes which graphs the representation admits and
that is a scope call for the owning lane.
"""

from __future__ import annotations

import copy
import itertools

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_graph_policy as graph
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action

ALWAYS = {"always": True}


def _stop():
    return {"kind": "stop", "target": "boolean.task", "inputs": {},
            "evidence_refs": [], "requested_resources": {}}


def _probe(x):
    return {"kind": "probe", "target": "boolean.query", "inputs": {"x": x},
            "evidence_refs": [], "requested_resources": {"queries": 1}}


def _arm(guard, action, next_node, progress=1):
    return {"guard": guard, "action": action, "next": next_node,
            "progress": progress}


def _graph(start, nodes):
    return {"policy_id": "defect", "start": start, "nodes": nodes}


def _public():
    return active.public_state(
        rules.RuleSession(rules.make_task("dev", 4)))


def _single(guard, action, progress=1):
    return {"kind": "action", "arms": [
        _arm(guard, action, "s", progress),
        _arm(ALWAYS, _stop(), "s", 0)]}


def test_loading_snapshots_the_action_payload_out_of_the_caller_record():
    """Guards were deep-copied at load and actions were not, so an edit to
    the caller's record reached into the loaded policy and steered it."""
    record = _graph("s", {
        "s": _single({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(3))})
    loaded = graph.load_policy(record)

    assert loaded.nodes["s"].arms[0].action.inputs == {"x": 3}

    record["nodes"]["s"]["arms"][0]["action"]["inputs"]["x"] = 12

    assert loaded.nodes["s"].arms[0].action.inputs == {"x": 3}


def test_loading_snapshots_the_requested_resources_out_of_the_caller_record():
    record = _graph("s", {
        "s": _single({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(3))})
    loaded = graph.load_policy(record)

    record["nodes"]["s"]["arms"][0]["action"]["requested_resources"] = {
        "queries": 99}

    assert loaded.nodes["s"].arms[0].action.requested_resources == {
        "queries": 1}


def test_a_snapshot_policy_ignores_a_later_edit_and_still_runs_the_episode():
    record = _graph("p", {
        "p": {"kind": "action", "arms": [
            _arm({"field": "observed.count", "op": "eq", "value": 0},
                 _probe(3), "d", 1),
            _arm(ALWAYS, _stop(), "s", 0)]},
        "d": {"kind": "action", "arms": [
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 {"kind": "construct", "target": "boolean.commit",
                  "inputs": {"specs": [
                      {"const": 1, "mask": 0, "pair": None},
                      {"const": 0, "mask": 0, "pair": None},
                      {"const": 0, "mask": 0, "pair": None},
                      {"const": 1, "mask": 0, "pair": None}]},
                  "evidence_refs": [], "requested_resources": {}},
                 "s", 1),
            _arm(ALWAYS, _stop(), "s", 0)]},
        "s": {"kind": "action", "arms": [_arm(ALWAYS, _stop(), "s", 0)]},
    })
    decide = graph.choose_action(record)

    for arm in record["nodes"]["p"]["arms"]:
        arm["action"] = _probe(12)

    result = active.run_episode(decide, split="dev", seed=4)
    emitted = [turn["action"] for turn in result["trace"]]

    assert result["queried"] == [3]
    assert emitted[0]["inputs"]["x"] == 3
    assert result["final"]["overall"] == 0.1875


def test_a_guard_snapshot_survives_the_same_edit_to_the_guard():
    record = _graph("s", {
        "s": _single({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(3))})
    loaded = graph.load_policy(record)

    record["nodes"]["s"]["arms"][0]["guard"]["value"] = 1

    assert loaded.nodes["s"].arms[0].guard == {
        "field": "observed.count", "op": "eq", "value": 0}


def test_the_in_and_not_in_operators_are_advertised_but_cannot_be_loaded():
    """`GUARD_OPS` offers four operators. The value type check at
    `_parse_guard` runs after the list branch has already accepted the value,
    and it then demands a scalar, so every list value is refused. Across
    every declared field and every plausible value shape, no `in` or
    `not_in` guard is loadable, and both evaluator branches are
    unreachable. Pinned here so nobody writes a graph using them and then
    wonders why it refuses."""
    assert graph.GUARD_OPS == frozenset({"eq", "ne", "in", "not_in"})

    fields = list(graph.FIELD_TYPES) + ["observed.0.y.0"]
    values = [["a"], [0], ["a", 0], [], ["a", "b"], ["a", 1], "a", 0, None,
              True, [None]]
    loadable = []
    for field, value, operator in itertools.product(
            fields, values, ("in", "not_in")):
        record = _graph("s", {"s": _single(
            {"field": field, "op": operator, "value": value}, _stop(), 0)})
        try:
            graph.load_policy(record)
        except graph.GraphPolicyRefused:
            continue
        loadable.append((field, operator, value))

    assert loadable == []


def test_the_two_operators_that_are_loadable_carry_typed_fields():
    """The control for the test above, so the sweep above is measuring the
    refusal and not a broken fixture."""
    for guard in ({"field": "observed.count", "op": "eq", "value": 0},
                  {"field": "observed.count", "op": "ne", "value": 3},
                  {"field": "instrument", "op": "eq",
                   "value": rules.INSTRUMENT_ID},
                  {"field": "observed.0.y.0", "op": "ne", "value": 1}):
        graph.load_policy(_graph("s", {"s": _single(guard, _stop(), 0)}))


def test_a_guard_that_is_true_selects_its_arm_and_a_false_one_does_not():
    """The same evaluator a list guard would have used, on guards that
    actually load. Two calls, the same graph, the only difference being how
    many inputs have been observed. `observed.count` is zero with nothing
    observed and one after a probe, so `ne 1` holds first and fails second."""
    record = _graph("d", {
        "d": {"kind": "action", "arms": [
            _arm({"field": "observed.count", "op": "ne", "value": 1},
                 _probe(3), "s", 1),
            _arm(ALWAYS, _stop(), "s", 0)]},
        "s": {"kind": "action", "arms": [_arm(ALWAYS, _stop(), "s", 0)]}})

    nothing_observed = _public()
    nothing_observed["observed"] = []
    something_observed = _public()
    something_observed["observed"] = [{"x": 3, "y": [1, 0, 0, 1]}]

    with_none = graph.choose_action(copy.deepcopy(record))(
        copy.deepcopy(nothing_observed))
    with_one = graph.choose_action(copy.deepcopy(record))(
        copy.deepcopy(something_observed))

    assert with_none["kind"] == policy_action.PROBE
    assert with_none["inputs"]["x"] == 3
    assert with_one["kind"] == policy_action.STOP
