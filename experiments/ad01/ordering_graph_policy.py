"""Execute a guarded decision graph as an ordering-world policy.

`boolean_graph_policy` is the executor for the action-graph
representation, and it is Boolean-typed for one reason: `_parse_action`
calls `boolean_policy._validate_boolean_action`, whose probe branch demands
`boolean.query` and whose stop branch demands `boolean.task`. Everything
else in that executor — the node grammar, the guard vocabulary, the
reachability and terminal checks, the cursor seam — is world-agnostic. The
constants that make it Boolean are three target strings, a validator call
and a field table.

So `s09_representation_matrix.ordering_graph_record()` is refused at load
with `node probe arm 0 action: probe target must be boolean.query`, and the
refusal names the executor rather than the record. That is a real measured
limit of the executor — the AST's equivalent is recorded in
`boolean_ast_policy.expressivity_limits()` — but it is one constant, not a
property of the notation, and the ordering world's validator already
exists in `second_active`. This module is the same executor with the world
as a parameter, so the limit is closed rather than recorded as permanent.

The world is a `World` value. Everything the executor needs to know about
an instrument arrives in one: its action targets, which action kinds it
offers, which fields a guard may name and of what type, how an observation
is indexed, what it derives, which exceptions mean "refused", and how a
public state becomes a view. Nothing above names a target string.

Two things are deliberately *not* reimplemented. The ordering world's rules
stay in `second_active`: `_validate_comparison` and `_validate_order` are
asked the question rather than restated, and `_ViewSession` supplies the two
attributes they read. And the view normaliser is `boolean_policy._shared_view`,
whose name is Boolean-flavored but whose body only reshapes the eight-field
public-state contract both worlds already publish.

The cursor seam — `at_cursor` in, `decide.s09_cursor()` out — is carried
over unchanged and for the same reason. `s09_graph_budget` runs one graph
turn per child process, so no closure outlives a turn. See
`test_the_cursor_survives_a_fresh_executor_every_turn`.

One arm can carry a value it read. `FIELD_BINDING` binds an action input to
a view field instead of a literal, and the bound value is resolved at turn
time. It used to be unreadable: `_parse_action` copied the raw action node,
so the value `_evaluate_guard` had just read was discarded and the emitted
action was the literal the record spelled. A graph arm could then only act
on something it already knew, which is what made a zero repair rate a
property of the record shape rather than of the binding. A bound field is
gated by the same world field table a guard is, so a record cannot bind a
field the guard grammar has never heard of.
"""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from . import boolean_policy
from . import policy_action
from . import policy_step
from . import second_active


FORMAT_POLICY_ID = "ordering-policy-graph/1"
GRAPH_NODE_KIND = "action"
GUARD_OPS = frozenset({"eq", "ne", "in", "not_in"})

MAX_NODES = 64
MAX_ARMS_PER_NODE = 16

_STATE_FIELDS = {"state.at": "string", "state.progress": "integer"}

_ORDERING_OBSERVATION_FIELD = re.compile(
    r"observed\.(?P<x>[0-9]+)\.(?P<key>left|right|earlier)"
)


class GraphPolicyRefused(ValueError):
    pass


@dataclass(frozen=True)
class Arm:
    guard: dict
    action: policy_action.Action
    next: str
    progress: int


@dataclass(frozen=True)
class Node:
    kind: str
    arms: tuple[Arm, ...]


@dataclass(frozen=True)
class GraphPolicy:
    policy_id: str
    start: str
    nodes: dict[str, Node]


@dataclass(frozen=True)
class World:
    """Everything the executor needs to know about one instrument.

    A field named here is a constant the Boolean executor had baked in.
    Adding a world is a value, not a subclass, which is what lets
    `test_a_world_other_than_ordering_can_be_passed_in` invent a third one.
    """

    name: str
    probe_target: str
    construct_target: str
    stop_target: str
    allowed_kinds: frozenset
    field_types: dict
    observation_paths: frozenset
    derived_fields: dict
    refusals: tuple
    validate_action: Callable[..., None]
    make_view: Callable[[dict], dict]
    static_view: dict

    def field_type(self, field: str) -> str | None:
        if field in self.field_types:
            return self.field_types[field]
        match = _ORDERING_OBSERVATION_FIELD.fullmatch(field)
        if match and match.group("key") in self.observation_paths:
            return "string"
        return None

    def observation_at(self, view: dict, field: str):
        match = _ORDERING_OBSERVATION_FIELD.fullmatch(field)
        return view["observed"][int(match.group("x"))][match.group("key")]


class _ViewSession:
    """The slice of `ScheduleSession` the ordering validators read.

    `_validate_comparison` consults `comparisons` and `remaining` and
    nothing else, and the public view already carries both. Supplying them
    lets the world's own rules answer the turn-time question without the
    graph holding a session or holding a copy of the rules. With no view —
    the load-time case — the session looks untouched and holds the full
    budget, so a load-time pass checks the part of the rule that does not
    depend on what has happened yet.
    """

    def __init__(self, view: dict | None):
        self.comparisons = {} if view is None else {
            (item["left"], item["right"]): item["earlier"]
            for item in view["observed"]
        }
        self.remaining = (second_active.MAX_QUERIES if view is None
                          else view["remaining"])


def _validate_ordering_action(action: policy_action.Action, *,
                              view: dict | None = None) -> None:
    if action.kind == policy_action.PROBE:
        second_active._validate_comparison(_ViewSession(view), action)
        return
    if action.kind == policy_action.CONSTRUCT:
        second_active._validate_order(action)
        return
    if action.kind == policy_action.STOP:
        if action.target != ORDERING_WORLD.stop_target:
            raise policy_action.ActionRefused(
                "stop target must be %s" % ORDERING_WORLD.stop_target)
        return
    raise policy_action.ActionRefused(
        "action %r is not available in the ordering world" % action.kind)


def _job_count(view: dict) -> int:
    return len(view["public_world"]["hypothesis_class"]["job_ids"])


# The targets are read out of the schema the world publishes rather than
# written here, so a change to `second_active.action_schema` cannot leave
# this executor validating against targets the world no longer offers.
_ORDERING_SCHEMA = second_active.action_schema(second_active.MAX_QUERIES)

ORDERING_WORLD = World(
    name="ordering",
    probe_target=_ORDERING_SCHEMA["actions"][policy_action.PROBE]["target"],
    construct_target=(
        _ORDERING_SCHEMA["actions"][policy_action.CONSTRUCT]["target"]),
    stop_target=_ORDERING_SCHEMA["actions"][policy_action.STOP]["target"],
    allowed_kinds=frozenset({policy_action.PROBE, policy_action.CONSTRUCT,
                             policy_action.STOP}),
    field_types={
        "instrument": "string",
        "task_id": "string",
        "remaining": "integer",
        "public_world.split": "string",
        "public_world.max_queries": "integer",
        "observed.count": "integer",
        "public_world.hypothesis_class.job_count": "integer",
        **_STATE_FIELDS,
    },
    observation_paths=frozenset({"left", "right", "earlier"}),
    derived_fields={"public_world.hypothesis_class.job_count": _job_count},
    refusals=(policy_action.ActionRefused, second_active.ActionRefused),
    validate_action=_validate_ordering_action,
    make_view=boolean_policy._shared_view,
    static_view={"observed": [], "remaining": second_active.MAX_QUERIES},
)


def _require_dict(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise GraphPolicyRefused("%s must be an object" % name)
    return value


def _require_exact_fields(value: dict, expected: set[str], name: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise GraphPolicyRefused(
            "%s missing fields: %s" % (name, ", ".join(sorted(missing))))
    if unknown:
        raise GraphPolicyRefused(
            "%s has unknown fields: %s" % (name, ", ".join(sorted(unknown))))


def _require_node_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphPolicyRefused("%s must be a non-empty string" % name)
    return value


# A binding: an action input holding a field rather than a value.
#
# A guard already reads a field, and the value it read was thrown away --
# `_parse_action` copied the raw node, so the emitted action was the
# literal the record spelled and an arm could act on nothing it had seen.
# This is the seam that carries the read value into the action.
#
# It resolves at turn time, not at load, because the load-time view is
# `World.static_view` -- the view in which nothing has been observed. A
# field bound to an observation has no value there, and a value invented
# for the load-time check would be one the world never published. The cost
# of that is that a bound action cannot be fully validated at load either,
# and `_parse_action` names the check it defers rather than skipping it
# quietly.
#
# The key is namespaced rather than a bare magic string so no literal the
# record spells can be mistaken for a binding, and it is a key rather than
# a second action grammar so a bound action is still the shared `Action`
# every other representation emits.
FIELD_BINDING = "$field"


def _is_binding(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {FIELD_BINDING}
            and isinstance(value[FIELD_BINDING], str))


def _binds(action: policy_action.Action) -> bool:
    return any(_is_binding(value) for value in action.inputs.values())


def _bound_value(view: dict, state: dict, field: str,
                 world: World = ORDERING_WORLD) -> str | int:
    """The value a binding names, read the way a guard reads it.

    A guard on an absent observation fails inside the evaluator, where the
    path is already known. A binding fails here instead, so the refusal has
    to name the field: an unbound action carrying `None` where a test name
    belongs would be refused by the world with a message about a missing
    value rather than about an unreadable field.
    """
    try:
        return _field_value(view, state, field, world)
    except (KeyError, IndexError, TypeError, GraphPolicyRefused) as exc:
        raise GraphPolicyRefused(
            "bound field %r is not readable from this view: %s"
            % (field, exc)) from exc


def _resolve_bindings(action: policy_action.Action, view: dict, state: dict,
                      world: World = ORDERING_WORLD
                      ) -> policy_action.Action:
    """Carry the field's value into the action, for the inputs that asked.

    Returns the action unchanged when it binds nothing, so every record
    written in literals takes the path it took before.
    """
    bound = {
        key: _bound_value(view, state, value[FIELD_BINDING], world)
        for key, value in action.inputs.items() if _is_binding(value)
    }
    if not bound:
        return action
    return dataclasses.replace(action, inputs={**action.inputs, **bound})


def _field_type(field: Any, name: str, world: World) -> str:
    if not isinstance(field, str) or not field:
        raise GraphPolicyRefused("%s field must be a non-empty string" % name)
    found = world.field_type(field)
    if found is None:
        raise GraphPolicyRefused("%s references unknown field %r" % (name, field))
    return found


def _parse_guard(raw: Any, name: str, world: World) -> dict:
    guard = _require_dict(raw, name)
    if set(guard) == {"always"}:
        if type(guard["always"]) is not bool:
            raise GraphPolicyRefused("%s always must be boolean" % name)
        return dict(guard)
    _require_exact_fields(guard, {"field", "op", "value"}, name)
    field_type = _field_type(guard["field"], name, world)
    if guard["op"] not in GUARD_OPS:
        raise GraphPolicyRefused("%s has unknown op %r" % (name, guard["op"]))
    value = guard["value"]
    if guard["op"] in {"in", "not_in"}:
        if (not isinstance(value, list) or not value
                or any(type(item) not in (str, int) for item in value)):
            raise GraphPolicyRefused(
                "%s in/not_in value must be a non-empty scalar list" % name)
    elif type(value) not in (str, int):
        raise GraphPolicyRefused(
            "%s eq/ne value must be a string or integer" % name)
    if field_type == "integer" and type(value) is not int:
        raise GraphPolicyRefused("%s value type does not match field" % name)
    if field_type == "string" and not isinstance(value, str):
        raise GraphPolicyRefused("%s value type does not match field" % name)
    return deepcopy(guard)


def _parse_bound_fields(action: policy_action.Action, name: str,
                        world: World) -> None:
    """Gate every bound field against the world's own field vocabulary.

    A binding is a claim about a field, so it is refused by the same table
    that refuses a guard naming one. Without this a record could bind
    `private.tables`, which no guard may name, and the arm would resolve it
    by walking the view -- the one path out of the declared contract.
    """
    for key, value in action.inputs.items():
        if not _is_binding(value):
            continue
        field = value[FIELD_BINDING]
        if world.field_type(field) is None:
            raise GraphPolicyRefused(
                "%s input %r references unknown field %r" % (name, key, field))


def _parse_action(raw: Any, name: str, world: World) -> policy_action.Action:
    try:
        action = policy_action.parse_action(raw)
        _parse_bound_fields(action, name, world)
        if not _binds(action):
            world.validate_action(action, view=world.static_view)
    except (policy_action.ActionRefused, ValueError) + world.refusals as exc:
        raise GraphPolicyRefused("%s: %s" % (name, exc)) from exc
    if action.kind not in world.allowed_kinds:
        raise GraphPolicyRefused(
            "%s action %r is not available in the %s world"
            % (name, action.kind, world.name))
    # A bound action is not validated against `static_view` above. That view
    # is the one in which nothing has been observed, so a field bound to an
    # observation has no value there and the world's own rule would be asked
    # about an input the record has not yet filled in. The claim about the
    # field is gated by `_parse_bound_fields`; the resolved action is
    # validated at turn time against the view that carries the value.
    return dataclasses.replace(
        action,
        inputs=deepcopy(action.inputs),
        evidence_refs=tuple(action.evidence_refs),
        requested_resources=deepcopy(action.requested_resources),
    )


def _parse_nodes(raw: Any, world: World) -> dict[str, Node]:
    values = _require_dict(raw, "nodes")
    if not 1 <= len(values) <= MAX_NODES:
        raise GraphPolicyRefused(
            "nodes must hold between 1 and %d entries" % MAX_NODES)
    parsed: dict[str, Node] = {}
    for raw_name, raw_node in values.items():
        name = _require_node_id(raw_name, "node name")
        node = _require_dict(raw_node, "node %s" % name)
        _require_exact_fields(node, {"kind", "arms"}, "node %s" % name)
        if node["kind"] != GRAPH_NODE_KIND:
            raise GraphPolicyRefused(
                "node %s kind must be %r" % (name, GRAPH_NODE_KIND))
        if (not isinstance(node["arms"], list)
                or not 1 <= len(node["arms"]) <= MAX_ARMS_PER_NODE):
            raise GraphPolicyRefused(
                "node %s arms must hold between 1 and %d entries"
                % (name, MAX_ARMS_PER_NODE))
        arms = []
        for index, raw_arm in enumerate(node["arms"]):
            arm_name = "node %s arm %d" % (name, index)
            arm = _require_dict(raw_arm, arm_name)
            _require_exact_fields(
                arm, {"guard", "action", "next", "progress"}, arm_name)
            next_node = _require_node_id(arm["next"], arm_name + " next")
            progress = arm["progress"]
            if type(progress) is not int or progress < 0:
                raise GraphPolicyRefused(
                    "%s progress must be a nonnegative integer" % arm_name)
            arms.append(Arm(
                guard=_parse_guard(arm["guard"], arm_name + " guard", world),
                action=_parse_action(arm["action"], arm_name + " action", world),
                next=next_node,
                progress=progress,
            ))
        if sum(1 for arm in arms if arm.guard == {"always": True}) != 1:
            raise GraphPolicyRefused("node %s has a bad fallback" % name)
        if arms[-1].guard != {"always": True}:
            raise GraphPolicyRefused("node %s fallback must be last" % name)
        parsed[name] = Node(kind=node["kind"], arms=tuple(arms))
    for name, node in parsed.items():
        for index, arm in enumerate(node.arms):
            if arm.next not in parsed:
                raise GraphPolicyRefused(
                    "node %s arm %d references unknown next node %r"
                    % (name, index, arm.next))
    return parsed


def _reachable(start: str, nodes: dict[str, Node]) -> set[str]:
    edges = {
        name: [arm.next for arm in node.arms]
        for name, node in nodes.items()
    }
    reached = {start}
    pending = [start]
    while pending:
        source = pending.pop()
        for target in edges[source]:
            if target not in reached:
                reached.add(target)
                pending.append(target)
    return reached


def _has_cycle_without_terminal(start: str, nodes: dict[str, Node]) -> bool:
    edges = {
        name: [arm.next for arm in node.arms]
        for name, node in nodes.items()
    }
    reverse: dict[str, list[str]] = defaultdict(list)
    for source, targets in edges.items():
        for target in targets:
            reverse[target].append(source)
    can_reach_stop = {
        name for name, node in nodes.items()
        if any(arm.action.kind == policy_action.STOP
               or arm.action.kind == policy_action.CONSTRUCT
               for arm in node.arms)
    }
    pending = list(can_reach_stop)
    while pending:
        target = pending.pop()
        for source in reverse[target]:
            if source not in can_reach_stop:
                can_reach_stop.add(source)
                pending.append(source)
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(source: str) -> bool:
        visiting.add(source)
        for target in edges[source]:
            if target in visiting and source not in can_reach_stop:
                return True
            if target not in done and target not in visiting and visit(target):
                return True
        visiting.remove(source)
        done.add(source)
        return False

    return any(name not in done and visit(name) for name in sorted(nodes))


def load_policy(record: dict, *, world: World = ORDERING_WORLD,
                expected_policy_id: str | None = None) -> GraphPolicy:
    raw = _require_dict(record, "policy")
    _require_exact_fields(raw, {"policy_id", "start", "nodes"}, "policy")
    policy_id = raw["policy_id"]
    if not isinstance(policy_id, str) or not policy_id:
        raise GraphPolicyRefused("policy_id must be a non-empty string")
    if expected_policy_id is not None and policy_id != expected_policy_id:
        raise GraphPolicyRefused(
            "policy id mismatch: expected %r, got %r"
            % (expected_policy_id, policy_id))
    start = _require_node_id(raw["start"], "start")
    nodes = _parse_nodes(raw["nodes"], world)
    if start not in nodes:
        raise GraphPolicyRefused("start references unknown node %r" % start)
    reachable = _reachable(start, nodes)
    unreachable = set(nodes) - reachable
    if unreachable:
        raise GraphPolicyRefused(
            "unreachable node: %s" % ", ".join(sorted(unreachable)))
    if _has_cycle_without_terminal(start, nodes):
        raise GraphPolicyRefused("cycle cannot reach a terminal")
    return GraphPolicy(
        policy_id=policy_id, start=start, nodes=nodes)


def make_view(public_state: dict, *, world: World = ORDERING_WORLD) -> dict:
    return world.make_view(public_state)


def _field_value(view: dict, state: dict, field: str,
                 world: World = ORDERING_WORLD) -> str | int:
    if field == "observed.count":
        return len(view["observed"])
    if field in world.derived_fields:
        return world.derived_fields[field](view)
    if world.field_type(field) is not None \
            and _ORDERING_OBSERVATION_FIELD.fullmatch(field):
        return world.observation_at(view, field)
    parts = field.split(".")
    if parts[0] == "state":
        source, parts = state, parts[1:]
    elif parts[0] == "public_world":
        source, parts = view["public_world"], parts[1:]
    else:
        source = view
    # A single-segment field is a key of the source mapping. Walking an
    # empty remainder would return the mapping itself, so without this a
    # guard on `remaining` compares a dict to an integer and is silently
    # always false — a field the loader admits, types, and then cannot
    # read.
    for part in parts:
        source = source[part]
    return source


def _evaluate_guard(guard: dict, view: dict, state: dict,
                    world: World = ORDERING_WORLD) -> bool:
    if "always" in guard:
        return guard["always"]
    left = _field_value(view, state, guard["field"], world)
    right = guard["value"]
    if guard["op"] == "eq":
        return left == right
    if guard["op"] == "ne":
        return left != right
    if guard["op"] == "in":
        return left in right
    return left not in right


def _refusal(exc: Exception, world: World) -> dict:
    reason = str(exc) or type(exc).__name__
    return {
        "kind": policy_action.STOP,
        "target": world.stop_target,
        "inputs": {
            "bridge_refusal": {
                "stage": "graph-step",
                "reason": reason[:500],
            }
        },
        "evidence_refs": [],
        "requested_resources": {},
    }


def choose_action(record: dict, *, world: World = ORDERING_WORLD,
                  expected_policy_id: str | None = None,
                  at_cursor: dict | None = None):
    """The episode callback for one ordering graph record.

    `at_cursor` seeds and the returned callback exposes the live cursor as
    `decide.s09_cursor()`. Both exist because an out-of-process step cannot
    keep a closure alive between turns: `s09_graph_budget` runs one turn per
    child so the graph can honour the same compute bound the STEP and AST
    paths do, and without this seam every turn restarted at the start node.
    A graph that had already advanced would answer as though it had not.
    """
    policy = load_policy(record, world=world,
                         expected_policy_id=expected_policy_id)
    if at_cursor is not None:
        if not isinstance(at_cursor, dict) or "at" not in at_cursor:
            raise GraphPolicyRefused("at_cursor must name a node")
        if at_cursor["at"] not in policy.nodes:
            raise GraphPolicyRefused(
                "at_cursor names unknown node %r" % (at_cursor["at"],))
        state = {"at": at_cursor["at"],
                 "progress": int(at_cursor.get("progress", 0))}
    else:
        state = {"at": policy.start, "progress": 0}

    def s09_cursor() -> dict:
        return dict(state)

    def decide(public_state: dict) -> dict:
        nonlocal state
        try:
            view = make_view(public_state, world=world)
            node = policy.nodes[state["at"]]
            arm = next(
                candidate for candidate in node.arms
                if _evaluate_guard(candidate.guard, view, state, world)
            )
            # Validate the action the world will actually see, and only
            # once. A bound input is a placeholder until `_resolve_bindings`
            # fills it, so validating before that hands the world's own
            # admission check a dict where a test name belongs: the SWE
            # world raises `cannot use 'dict' as a set element` from inside
            # its `code.localize` gate, and the arm refuses for a typing
            # accident rather than for anything about the world.
            #
            # Nothing is lost by dropping the earlier call. For a record
            # that binds nothing `_resolve_bindings` returns the same
            # action object, so the two calls were one call. The field a
            # binding names is still gated at load by `_parse_bound_fields`
            # against the same world table a guard is gated by, so a record
            # still cannot bind a field the guard grammar has never heard
            # of.
            action = _resolve_bindings(arm.action, view, state, world)
            world.validate_action(action, view=view)
            next_state = {
                "at": arm.next,
                "progress": state["progress"] + arm.progress,
            }
            policy_step.validate_state(next_state)
            state = next_state
            return action.as_dict()
        except Exception as exc:
            return _refusal(exc, world)

    decide.s09_cursor = s09_cursor
    return decide


def expressivity_limits() -> dict:
    """What the ordering executor can and cannot express, per world.

    The counterpart of `boolean_ast_policy.expressivity_limits()`, and
    recorded for the same reason: an expressivity limit is a measured
    refusal, so a limit that stops being true has to fail the suite rather
    than quietly become a claim. Every `cannot` row is a refusal the two
    executors still produce, and
    `test_the_boolean_executor_still_refuses_the_ordering_record` and
    `test_the_ordering_executor_refuses_the_boolean_record` drive the
    cross-world pair back through the loaders.
    """
    return {
        "version": "s09-ordering-graph-expressivity/1",
        "worlds": {
            "boolean-rule": {
                "cannot": [
                    "a graph naming schedule.compare, refused at load by "
                    "the Boolean executor's validator",
                ],
            },
            "ordering": {
                "cannot": [
                    "a graph naming boolean.query, refused at load by the "
                    "ordering executor's validator",
                ],
                "can": [
                    "probe schedule.compare on two named job ids",
                    "construct schedule.commit with a four-job permutation",
                    "stop on schedule.task",
                    "guard on observed.count, observed.<i>.earlier, and the "
                    "derived hypothesis_class.job_count",
                ],
            },
        },
        "frozen_limits": {
            "max_nodes": MAX_NODES,
            "max_arms_per_node": MAX_ARMS_PER_NODE,
            "state_byte_cap": policy_step.STATE_LIMIT_BYTES,
            "step_timeout_ms": policy_step.STEP_TIMEOUT_MS,
            "step_cpu_seconds": policy_step.STEP_CPU_SECONDS,
            "step_max_output_bytes": policy_step.STEP_MAX_OUTPUT_BYTES,
        },
    }


__all__ = [
    "Arm",
    "FIELD_BINDING",
    "FORMAT_POLICY_ID",
    "GraphPolicy",
    "GraphPolicyRefused",
    "MAX_ARMS_PER_NODE",
    "MAX_NODES",
    "Node",
    "ORDERING_WORLD",
    "World",
    "choose_action",
    "expressivity_limits",
    "load_policy",
    "make_view",
]
