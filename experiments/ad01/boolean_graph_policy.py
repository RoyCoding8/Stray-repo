"""Execute a guarded decision graph as a Boolean policy representation."""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from . import boolean_policy
from . import policy_action
from . import policy_step


FORMAT_POLICY_ID = "boolean-policy-graph/1"
GRAPH_NODE_KIND = "action"
ALLOWED_BOOLEAN_ACTIONS = frozenset({
    policy_action.PROBE, policy_action.CONSTRUCT, policy_action.STOP,
})
GUARD_OPS = frozenset({"eq", "ne", "in", "not_in"})
FIELD_TYPES = {
    "instrument": "string",
    "task_id": "string",
    "remaining": "integer",
    "public_world.split": "string",
    "public_world.max_queries": "integer",
    "public_world.hypothesis_class.class_size": "integer",
    "observed.count": "integer",
    "state.at": "string",
    "state.progress": "integer",
}
OBSERVED_FIELD = re.compile(
    r"observed\.(?P<x>[0-3])\.y\.(?P<output>[0-3])"
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


def _field_type(field: Any, name: str) -> str:
    if not isinstance(field, str) or not field:
        raise GraphPolicyRefused("%s field must be a non-empty string" % name)
    if field in FIELD_TYPES:
        return FIELD_TYPES[field]
    if OBSERVED_FIELD.fullmatch(field):
        return "integer"
    raise GraphPolicyRefused("%s references unknown field %r" % (name, field))


def _parse_guard(raw: Any, name: str) -> dict:
    guard = _require_dict(raw, name)
    if set(guard) == {"always"}:
        if type(guard["always"]) is not bool:
            raise GraphPolicyRefused("%s always must be boolean" % name)
        return dict(guard)
    _require_exact_fields(guard, {"field", "op", "value"}, name)
    field_type = _field_type(guard["field"], name)
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


def _parse_action(raw: Any, name: str) -> policy_action.Action:
    try:
        action = policy_action.parse_action(raw)
        boolean_policy._validate_boolean_action(action, {
            "observed": [], "remaining": 8,
        })
    except (policy_action.ActionRefused, ValueError) as exc:
        raise GraphPolicyRefused("%s: %s" % (name, exc)) from exc
    if action.kind not in ALLOWED_BOOLEAN_ACTIONS:
        raise GraphPolicyRefused(
            "%s action %r is not available in the Boolean world"
            % (name, action.kind))
    return dataclasses.replace(
        action,
        inputs=deepcopy(action.inputs),
        evidence_refs=tuple(action.evidence_refs),
        requested_resources=deepcopy(action.requested_resources),
    )


def _parse_nodes(raw: Any) -> dict[str, Node]:
    values = _require_dict(raw, "nodes")
    if not 1 <= len(values) <= 64:
        raise GraphPolicyRefused("nodes must hold between 1 and 64 entries")
    parsed: dict[str, Node] = {}
    for raw_name, raw_node in values.items():
        name = _require_node_id(raw_name, "node name")
        node = _require_dict(raw_node, "node %s" % name)
        _require_exact_fields(node, {"kind", "arms"}, "node %s" % name)
        if node["kind"] != GRAPH_NODE_KIND:
            raise GraphPolicyRefused(
                "node %s kind must be %r" % (name, GRAPH_NODE_KIND))
        if (not isinstance(node["arms"], list)
                or not 1 <= len(node["arms"]) <= 16):
            raise GraphPolicyRefused(
                "node %s arms must hold between 1 and 16 entries" % name)
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
                guard=_parse_guard(arm["guard"], arm_name + " guard"),
                action=_parse_action(arm["action"], arm_name + " action"),
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


def load_policy(record: dict, *, expected_policy_id: str | None = None) -> GraphPolicy:
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
    nodes = _parse_nodes(raw["nodes"])
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


def make_view(public_state: dict) -> dict:
    return boolean_policy._shared_view(public_state)


def _field_value(view: dict, state: dict, field: str) -> str | int:
    if field == "observed.count":
        return len(view["observed"])
    match = OBSERVED_FIELD.fullmatch(field)
    if match:
        return view["observed"][int(match.group("x"))]["y"][
            int(match.group("output"))]
    # `public_world.split` and `public_world.hypothesis_class.class_size` name
    # a field *inside* the view's `public_world` entry, not a walk from the
    # view root: the shared view already nests split, max_queries and
    # hypothesis_class under that one key. So the first segment is the view
    # key and the rest is a lookup within its value - which may itself be
    # nested, as `hypothesis_class.class_size` is. `state.*` is the only
    # family that walks, because the cursor is separate from the view.
    if field.startswith("state."):
        cursor = state
        for part in field.split(".")[1:]:
            cursor = cursor[part]
        return cursor
    root, _, rest = field.partition(".")
    try:
        value = view[root] if rest else view[field]
        for part in rest.split(".") if rest else ():
            value = value[part]
        return value
    except (KeyError, IndexError, TypeError) as exc:
        raise GraphPolicyRefused(
            "field %r is admitted by the loader but absent from the view"
            % (field,)) from exc


def _evaluate_guard(guard: dict, view: dict, state: dict) -> bool:
    if "always" in guard:
        return guard["always"]
    left = _field_value(view, state, guard["field"])
    right = guard["value"]
    if guard["op"] == "eq":
        return left == right
    if guard["op"] == "ne":
        return left != right
    if guard["op"] == "in":
        return left in right
    return left not in right


def _refusal(exc: Exception) -> dict:
    reason = str(exc) or type(exc).__name__
    return {
        "kind": policy_action.STOP,
        "target": "boolean.task",
        "inputs": {
            "bridge_refusal": {
                "stage": "graph-step",
                "reason": reason[:500],
            }
        },
        "evidence_refs": [],
        "requested_resources": {},
    }


def choose_action(record: dict, *, expected_policy_id: str | None = None,
                  at_cursor: dict | None = None):
    """The episode callback for one graph record.

    `at_cursor` seeds and the returned callback exposes the live cursor as
    `decide.s09_cursor()`. Both exist because an out-of-process step cannot
    keep a closure alive between turns: `s09_graph_budget` runs one turn per
    child so the graph can honour the same compute bound the STEP and AST
    paths do, and without this seam every turn restarted at the start node.
    A graph that loops through nodes would then replay its first turn
    forever, and a graph that had already advanced would answer as though it
    had not.
    """
    policy = load_policy(record, expected_policy_id=expected_policy_id)
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
            view = make_view(public_state)
            node = policy.nodes[state["at"]]
            arm = next(
                candidate for candidate in node.arms
                if _evaluate_guard(candidate.guard, view, state)
            )
            boolean_policy._validate_boolean_action(arm.action, view)
            next_state = {
                "at": arm.next,
                "progress": state["progress"] + arm.progress,
            }
            policy_step.validate_state(next_state)
            state = next_state
            return arm.action.as_dict()
        except Exception as exc:
            return _refusal(exc)

    decide.s09_cursor = s09_cursor
    return decide


__all__ = [
    "Arm",
    "FORMAT_POLICY_ID",
    "GraphPolicy",
    "GraphPolicyRefused",
    "Node",
    "choose_action",
    "load_policy",
    "make_view",
]
