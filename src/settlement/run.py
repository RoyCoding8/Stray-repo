"""Versioned typed composition algebra and recorded-continuation interpreter.

Compositions are data: sequence, conditional choice, bounded repetition,
parallel alternatives, dependency join, suspension. The interpreter advances
recorded continuations only — it never asks a model to recall intent. Model
inference enters as an invocable op through the broker. Dynamic revisions are
validated data; generated Python never enters the trusted process.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from . import db, store
from .common import Command

COMPOSITION_VERSION = "run/v1"


class InvalidComposition(ValueError):
    pass


class InvokeNode(BaseModel):
    kind: Literal["invoke"] = "invoke"
    node_id: str
    effect: str = "sandbox-exec"
    payload: dict[str, Any] = Field(default_factory=dict)
    expects: str = ""
    retry_max: int = 0

    model_config = {"extra": "forbid"}


class SequenceNode(BaseModel):
    kind: Literal["sequence"] = "sequence"
    node_id: str
    steps: list["Node"]

    model_config = {"extra": "forbid"}


class ChoiceNode(BaseModel):
    kind: Literal["choice"] = "choice"
    node_id: str
    on: str
    equals: Any = None
    then: "Node"
    otherwise: "Node"

    model_config = {"extra": "forbid"}


class RepeatNode(BaseModel):
    kind: Literal["repeat"] = "repeat"
    node_id: str
    body: "Node"
    max_iterations: int
    until: str | None = None

    model_config = {"extra": "forbid"}


class ParallelNode(BaseModel):
    kind: Literal["parallel"] = "parallel"
    node_id: str
    branches: list["Node"]

    model_config = {"extra": "forbid"}


class JoinNode(BaseModel):
    kind: Literal["join"] = "join"
    node_id: str
    needs: dict[str, str]

    model_config = {"extra": "forbid"}


class SuspendNode(BaseModel):
    kind: Literal["suspend"] = "suspend"
    node_id: str
    pending_observation: str

    model_config = {"extra": "forbid"}


Node = Union[InvokeNode, SequenceNode, ChoiceNode, RepeatNode, ParallelNode,
             JoinNode, SuspendNode]

for _cls in (SequenceNode, ChoiceNode, RepeatNode, ParallelNode):
    _cls.model_rebuild()


class Composition(BaseModel):
    version: str = COMPOSITION_VERSION
    revision: int = 1
    root: Node
    allocation_id: str = ""
    authority_version: int = 1
    budget: dict[str, Any] = Field(default_factory=dict)
    max_depth: int = 4

    model_config = {"extra": "forbid"}


class Continuation(BaseModel):
    attempt_id: str
    composition_version: str = COMPOSITION_VERSION
    composition_revision: int = 1
    position: list[str] = Field(default_factory=list)
    completed: dict[str, str] = Field(default_factory=dict)
    observations: dict[str, Any] = Field(default_factory=dict)
    unresolved_ops: list[str] = Field(default_factory=list)
    obligations: dict[str, str] = Field(default_factory=dict)
    next: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


def _walk(node: Node):
    yield node
    if isinstance(node, (SequenceNode, ParallelNode)):
        for child in (node.steps if isinstance(node, SequenceNode) else node.branches):
            yield from _walk(child)
    elif isinstance(node, ChoiceNode):
        yield from _walk(node.then)
        yield from _walk(node.otherwise)
    elif isinstance(node, RepeatNode):
        yield from _walk(node.body)


def node_index(comp: Composition) -> dict[str, Node]:
    return {node.node_id: node for node in _walk(comp.root)}


def validate_composition(comp: Composition) -> Composition:
    if _depth(comp.root) > comp.max_depth:
        raise InvalidComposition(
            f"composition depth exceeds max depth {comp.max_depth}")
    seen: set[str] = set()
    for node in _walk(comp.root):
        if node.node_id in seen:
            raise InvalidComposition(f"duplicate node id {node.node_id!r}")
        seen.add(node.node_id)
    for node in _walk(comp.root):
        if isinstance(node, JoinNode):
            for obligation, target in node.needs.items():
                if target not in seen:
                    raise InvalidComposition(
                        f"join {node.node_id} obligation {obligation!r} targets unknown node {target!r}")
    return comp


def referenced_ids(comp: Composition) -> set[str]:
    refs = set()
    for node in _walk(comp.root):
        if isinstance(node, JoinNode):
            refs.update(node.needs.values())
    return refs


def _repeat_bodies(comp: Composition) -> dict[str, str]:
    return {node.body.node_id: node.node_id for node in _walk(comp.root)
            if isinstance(node, RepeatNode)}


def _iters(cont: Continuation, repeat_id: str, body_id: str) -> int:
    return sum(1 for key in cont.completed if key.startswith(f"{repeat_id}:{body_id}:"))


def _unresolved_node(cont: Continuation, node_id: str) -> str | None:
    for entry in cont.unresolved_ops:
        if entry == node_id or entry.startswith(f"{node_id}:"):
            return entry
    return None


def _frontier(comp: Composition, node: Node, cont: Continuation,
              path: list[str]) -> tuple[str, Any, list[str]]:
    here = path + [node.node_id]
    if isinstance(node, InvokeNode):
        if node.node_id in cont.completed:
            return "done", "invoke-complete", here
        pending = _unresolved_node(cont, node.node_id)
        if pending is not None:
            return "awaiting-op", pending, here
        return "invoke", node.node_id, here
    if isinstance(node, SequenceNode):
        for step in node.steps:
            decision, detail, pos = _frontier(comp, step, cont, here)
            if decision != "done":
                return decision, detail, pos
        return "done", "sequence-complete", here
    if isinstance(node, ChoiceNode):
        if node.on not in cont.observations:
            return "await-observation", node.on, here
        branch = node.then if cont.observations[node.on] == node.equals else node.otherwise
        return _frontier(comp, branch, cont, here)
    if isinstance(node, RepeatNode):
        if node.until is not None and cont.observations.get(node.until):
            return "done", "repeat-until", here
        if _iters(cont, node.node_id, node.body.node_id) >= node.max_iterations:
            return "done", "repeat-exhausted", here
        return _frontier(comp, node.body, cont, here)
    if isinstance(node, ParallelNode):
        pending: list[str] = []
        for branch in node.branches:
            decision, detail, _ = _frontier(comp, branch, cont, here)
            if decision != "done":
                pending.append(branch.node_id)
        if pending:
            return "fork", pending, here
        return "done", "parallel-complete", here
    if isinstance(node, JoinNode):
        missing = [obl for obl, nid in node.needs.items() if nid not in cont.completed]
        if missing:
            return "await-join", missing, here
        return "done", "join-satisfied", here
    if node.pending_observation in cont.observations:
        return "done", "suspend-released", here
    return "await-observation", node.pending_observation, here


def fresh_continuation(comp: Composition, attempt_id: str,
                       obligations: dict[str, str] | None = None) -> Continuation:
    cont = Continuation(attempt_id=attempt_id, composition_version=comp.version,
                        composition_revision=comp.revision,
                        obligations=dict(obligations or {}))
    return _refresh(comp, cont)


def _refresh(comp: Composition, cont: Continuation) -> Continuation:
    decision, detail, position = _frontier(comp, comp.root, cont, [])
    cont.position = position
    cont.next = {"decision": decision, "detail": detail}
    return cont


def advance(comp: Composition, cont: Continuation, event: dict[str, Any]) -> Continuation:
    known = set(node_index(comp)) | referenced_ids(comp)
    etype = event.get("type")
    if etype == "node_completed":
        node_id = event.get("node_id", "")
        ref = event.get("result_ref", "")
        if node_id not in known:
            raise InvalidComposition(f"unknown node {node_id!r}")
        if not isinstance(ref, str) or not ref:
            raise InvalidComposition("result_ref must be a non-empty string")
        bodies = _repeat_bodies(comp)
        if node_id in bodies:
            repeat_id = bodies[node_id]
            cont.completed[f"{repeat_id}:{node_id}:{_iters(cont, repeat_id, node_id)}"] = ref
        else:
            cont.completed[node_id] = ref
        cont.unresolved_ops = [e for e in cont.unresolved_ops
                               if e != node_id and not e.startswith(f"{node_id}:")]
    elif etype == "observation":
        key = event.get("key", "")
        if not isinstance(key, str) or not key:
            raise InvalidComposition("observation needs a non-empty key")
        cont.observations[key] = event.get("value")
    else:
        raise InvalidComposition(f"unknown event type {etype!r}")
    return _refresh(comp, cont)


def register_ops(comp: Composition, cont: Continuation,
                 mapping: dict[str, str]) -> Continuation:
    known = set(node_index(comp))
    for node_id, op_id in mapping.items():
        if node_id not in known:
            raise InvalidComposition(f"unknown node {node_id!r}")
        entry = f"{node_id}:{op_id}"
        if entry not in cont.unresolved_ops:
            cont.unresolved_ops.append(entry)
    return _refresh(comp, cont)


def pending_invokes(comp: Composition, cont: Continuation) -> list[InvokeNode]:
    return [node for node in _walk(comp.root)
            if isinstance(node, InvokeNode)
            and node.node_id not in cont.completed
            and _unresolved_node(cont, node.node_id) is None
            and _on_path(comp, cont, node.node_id)]


def _on_path(comp: Composition, cont: Continuation, node_id: str) -> bool:
    decision, detail, position = _frontier(comp, comp.root, cont, [])
    if decision == "invoke":
        return node_id == detail
    if decision == "fork":
        return node_id in detail
    return False


def iteration_of(comp: Composition, cont: Continuation, node_id: str) -> int | None:
    for node in _walk(comp.root):
        if isinstance(node, RepeatNode) and node.body.node_id == node_id:
            return _iters(cont, node.node_id, node_id)
    return None


def invoke_to_broker_args(node: InvokeNode, *, attempt_id: str, allocation_id: str,
                          execution_version: str = COMPOSITION_VERSION,
                          iteration: int | None = None) -> dict[str, Any]:
    operation_id = f"{attempt_id}:{node.node_id}" if iteration is None else \
        f"{attempt_id}:{node.node_id}:i{iteration}"
    return {"operation_id": operation_id, "effect": node.effect, "payload": node.payload,
            "allocation_id": allocation_id, "attempt_id": attempt_id,
            "execution_version": execution_version}


_FORBIDDEN_KEYS = {"exec", "eval", "code"}


def _depth(node: Node) -> int:
    if isinstance(node, (InvokeNode, SuspendNode, JoinNode)):
        return 1
    if isinstance(node, (SequenceNode, ParallelNode)):
        children = node.steps if isinstance(node, SequenceNode) else node.branches
        return 1 + max([_depth(c) for c in children] + [0])
    if isinstance(node, ChoiceNode):
        return 1 + max(_depth(node.then), _depth(node.otherwise))
    return 1 + _depth(node.body)


def _scan_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_KEYS or (isinstance(key, str) and key.startswith("__")):
                raise InvalidComposition(f"forbidden key {key!r} in proposed revision")
            _scan_keys(item)
    elif isinstance(value, list):
        for item in value:
            _scan_keys(item)


def revise(comp: Composition, proposal: dict[str, Any]) -> Composition:
    _scan_keys(proposal)
    try:
        root = _validate_node(proposal)
    except Exception as exc:
        raise InvalidComposition(f"proposed revision is not a valid composition: {exc}") from exc
    if _depth(root) > comp.max_depth:
        raise InvalidComposition(f"proposed revision exceeds max depth {comp.max_depth}")
    from .broker import validate_effect

    for node in _walk(root):
        if isinstance(node, InvokeNode):
            try:
                validate_effect(node.effect, node.payload)
            except Exception as exc:
                raise InvalidComposition(f"invoke {node.node_id}: {exc}") from exc
    return validate_composition(Composition(
        version=comp.version, revision=comp.revision + 1, root=root,
        allocation_id=comp.allocation_id, authority_version=comp.authority_version,
        budget=dict(comp.budget), max_depth=comp.max_depth))


def _validate_node(proposal: dict[str, Any]) -> Node:
    kind = proposal.get("kind") if isinstance(proposal, dict) else None
    table = {"invoke": InvokeNode, "sequence": SequenceNode, "choice": ChoiceNode,
             "repeat": RepeatNode, "parallel": ParallelNode, "join": JoinNode,
             "suspend": SuspendNode}
    if kind not in table:
        raise InvalidComposition(f"unknown node kind {kind!r}")
    return table[kind].model_validate(proposal)


def check_eligibility(dsn: str, attempt_id: str, comp: Composition) -> dict[str, Any]:
    from psycopg.rows import dict_row

    reasons: list[str] = []
    authority = store.get_control(dsn)["authority_version"]
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT lifecycle, investigation_id FROM attempts WHERE id = %s",
                        (attempt_id,))
            attempt = cur.fetchone()
            disposition = ""
            if attempt is not None:
                cur.execute("SELECT disposition FROM investigations WHERE id = %s",
                            (attempt["investigation_id"],))
                found = cur.fetchone()
                disposition = found["disposition"] if found else ""
            conn.commit()
    if int(authority) != int(comp.authority_version):
        reasons.append(f"authority {comp.authority_version} != current {authority}")
    if attempt is None:
        reasons.append(f"unknown attempt {attempt_id}")
    elif attempt["lifecycle"] not in ("running", "suspended"):
        reasons.append(f"attempt is {attempt['lifecycle']}")
    if disposition in ("withdrawn", "fulfilled"):
        reasons.append(f"investigation is {disposition}")
    from psycopg import errors as _pgerrors

    from . import capabilities as _capabilities

    try:
        quarantined = _capabilities.pinned_quarantines(dsn, attempt_id)
    except _pgerrors.UndefinedTable:
        quarantined = []
    for hit in quarantined:
        reasons.append(
            f"quarantined capability {hit['version_id']}: {hit['reason']}")
    return {"eligible": not reasons, "reasons": reasons}


def record_continuation(dsn: str, attempt_id: str, cont: Continuation, ref: str,
                        ownership_generation: int | None = None) -> Any:
    import json

    payload: dict[str, Any] = {"attempt_id": attempt_id,
                               "continuation_ref": json.dumps(
                                   {"ref": ref, "continuation": cont.model_dump()})}
    if ownership_generation is not None:
        payload["ownership_generation"] = ownership_generation
    return store.install_continuation(dsn, Command(request_id=f"run-cont-{ref}", payload=payload))


def migrate_continuation(dsn: str, attempt_id: str, old_ref: str, cont: Continuation,
                         ownership_generation: int | None = None) -> Any:
    import json

    payload: dict[str, Any] = {"attempt_id": attempt_id,
                               "continuation_ref": json.dumps(
                                   {"supersedes": old_ref, "continuation": cont.model_dump()})}
    if ownership_generation is not None:
        payload["ownership_generation"] = ownership_generation
    return store.install_continuation(
        dsn, Command(request_id=f"run-migrate-{old_ref}", payload=payload))


def operation_outcome(dsn: str, operation_id: str) -> dict[str, Any]:
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT dispatch_state, reconcile_state, cancel_state, settled,"
                        " attempt_id FROM operations WHERE id = %s", (operation_id,))
            row = cur.fetchone()
            receipts: list[dict[str, Any]] = []
            lifecycle = ""
            if row is not None:
                cur.execute("SELECT receipt_identity, outcome FROM receipts"
                            " WHERE operation_id = %s ORDER BY receipt_identity",
                            (operation_id,))
                receipts = [dict(r) for r in cur.fetchall()]
                if row["attempt_id"] is not None:
                    cur.execute("SELECT lifecycle FROM attempts WHERE id = %s",
                                (row["attempt_id"],))
                    found = cur.fetchone()
                    lifecycle = found["lifecycle"] if found else ""
            conn.commit()
    if row is None:
        return {"found": False, "outcome": "unresolved", "dispatch_state": "unknown",
                "receipts": []}
    outcomes = {r["outcome"] for r in receipts}
    if row["reconcile_state"] == "conflict":
        typed = "conflict"
    elif row["dispatch_state"] == "unresolved" or row["reconcile_state"] == "unresolved":
        typed = "unresolved"
    elif "success" in outcomes and "failure" not in outcomes:
        typed = "success"
    elif "failure" in outcomes and "success" not in outcomes:
        typed = "failure"
    elif outcomes:
        typed = "unknown"
    elif (row["cancel_state"] or "none") == "confirmed":
        typed = "cancelled"
    elif lifecycle == "suspended":
        typed = "suspended"
    else:
        typed = "unresolved"
    return {"found": True, "outcome": typed, "dispatch_state": row["dispatch_state"],
            "reconcile_state": row["reconcile_state"], "cancel_state": row["cancel_state"],
            "settled": bool(row["settled"]), "receipts": receipts}


def _tries_key(node_id: str, iteration: int | None) -> str:
    return f"{node_id}:tries" if iteration is None else f"{node_id}:i{iteration}:tries"


def retry_tries(cont: Continuation, node_id: str,
                iteration: int | None = None) -> list[str]:
    seen = cont.observations.get(_tries_key(node_id, iteration), [])
    return list(seen) if isinstance(seen, list) else []


def retry_operation_id(base_operation_id: str, cont: Continuation, node_id: str,
                       iteration: int | None = None) -> str:
    used = len(retry_tries(cont, node_id, iteration))
    if used <= 0:
        return base_operation_id
    return f"{base_operation_id}:retry{used}"


def retry_allowed(comp: Composition, node_id: str) -> int:
    node = node_index(comp).get(node_id)
    if isinstance(node, InvokeNode):
        return max(int(node.retry_max), 0)
    return 0


def record_failed_try(comp: Composition, cont: Continuation, node_id: str,
                      operation_id: str, iteration: int | None = None) -> Continuation:
    key = _tries_key(node_id, iteration)
    tries = retry_tries(cont, node_id, iteration)
    if operation_id not in tries:
        tries.append(operation_id)
    cont.observations[key] = tries
    cont.unresolved_ops = [e for e in cont.unresolved_ops
                           if e != node_id and not e.startswith(f"{node_id}:")]
    if len(tries) > retry_allowed(comp, node_id):
        cont.observations[f"{node_id}:outcome"] = "failure"
        return advance(comp, cont, {"type": "node_completed", "node_id": node_id,
                                   "result_ref": f"op:{operation_id}:failed"})
    return _refresh(comp, cont)


def consume_operation_outcome(comp: Composition, cont: Continuation, node_id: str,
                              operation_id: str, outcome: str) -> Continuation:
    if outcome == "success":
        return advance(comp, cont, {"type": "node_completed", "node_id": node_id,
                                   "result_ref": f"op:{operation_id}"})
    if outcome in ("failure", "cancelled", "suspended"):
        cont.observations[f"{node_id}:outcome"] = outcome
    if outcome == "failure":
        cont.unresolved_ops = [e for e in cont.unresolved_ops
                               if e != node_id and not e.startswith(f"{node_id}:")]
        return _refresh(comp, cont)
    return register_ops(comp, cont, {node_id: operation_id})
