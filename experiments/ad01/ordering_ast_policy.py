"""The typed-AST representation on the ordering-constraints world.

`boolean_ast_policy` is refused on this world, and the refusal is real:

    probe target must be schedule.compare

What that refusal does not settle is *why*. The Boolean executor hardcodes
the Boolean world's action targets in `_validate_action`, so a document
written for a second instrument is rejected by the world binding whether
or not the node set could express it. Those are different findings. One is
a property of the representation and no policy on any world could get
past it; the other is a property of one executor, and the same document
would run unchanged somewhere else.

This module settles it. It supplies a view projection and the world's own
action rules, and then borrows the frozen loader, the frozen executor and
the frozen node set unchanged:

    * `make_ordering_ast_record` emits the record shape
      `boolean_ast_policy.load_policy` already accepts;
    * `choose_action` and `ast_step` run it through that module's
      `_run_step`, so the program is parsed, type-checked, budgeted and
      run by the frozen interpreter.

There is deliberately no interpreter here. The finding is that the node
set *can* express "probe one pair, then commit a four-job order" on this
world, and the only honest way to show it is to run the real frozen
interpreter on a real `second_active` episode. A substitute evaluator
would have proved a fact about the substitute.

The one limit that is genuinely a node-set limit is recorded in
`ordering_expressivity`: the node set has no symbolic `lt`, so a policy
cannot turn a comparison into an order. It can only choose among orders
it already wrote down, which is a weaker claim than it first reads.
"""

from __future__ import annotations

import hashlib
from typing import Any

from . import boolean_ast_policy as frozen
from . import policy_action
from . import policy_step
from . import second_active

JOB_IDS = tuple(second_active.JOB_IDS)
COMPARED_PAIR = (JOB_IDS[0], JOB_IDS[1])
COMMITTED_ORDER = tuple(second_active.JOB_IDS)
DEFAULT_POLICY_ID = "e1-ordering-ast"


def _const(value: Any) -> dict:
    return {"op": "const", "value": value}


def _field(scope: str, name: str) -> dict:
    return {"op": "field", "scope": scope, "name": name}


def _index(value: dict, key: dict) -> dict:
    return {"op": "index", "value": value, "key": key}


def _eq(left: dict, right: dict) -> dict:
    return {"op": "eq", "left": left, "right": right}


def _if(condition: dict, then: dict, otherwise: dict) -> dict:
    return {"op": "if", "cond": condition, "then": then, "else": otherwise}


def _obj_expr(fields: dict) -> dict:
    """Lift Python values into an `obj` node, field by field.

    Wrapping the dict in one `const` would hand the world a node where a
    table belongs, and the refusal would name the notation rather than the
    behaviour.
    """
    return {"op": "obj", "fields": {name: _const(value)
                                    for name, value in fields.items()}}


def _return_action(kind: str, target: str, inputs: dict,
                   resources: dict | None = None) -> dict:
    return {
        "op": "return_action",
        "kind": kind,
        "target": target,
        "inputs": _obj_expr(inputs),
        "evidence_refs": [],
        "requested_resources": {} if resources is None else resources,
        "state": _const({}),
    }


def _nothing_observed() -> dict:
    """Whether the world has yet to show the program a comparison.

    Rebranching on the view each step is what keeps the program
    contingent without keeping any state, and it is also the guard
    against re-probing: the program asks only while the view is empty, so
    the pair it probes can never be one the world has already answered.
    """
    return _eq(_field("view", "observed"), _const([]))


def ordering_document(policy_id: str = DEFAULT_POLICY_ID) -> dict:
    """The ordering decision in the frozen grammar.

    No state, four nodes, and no world name in it: the two action targets
    are the only thing that tie this document to this instrument.
    """
    return {
        "policy_id": policy_id,
        "entry": _if(
            _nothing_observed(),
            _return_action("probe", "schedule.compare",
                           {"left": COMPARED_PAIR[0],
                            "right": COMPARED_PAIR[1]},
                           {"queries": 1}),
            _return_action("construct", "schedule.commit",
                           {"order": list(COMMITTED_ORDER)}),
        ),
    }


def _record(policy_id: str, document: dict) -> dict:
    return {
        "artifact": {
            "kind": "learning-policy",
            "representation": "typed-ast",
            "version": frozen._REPRESENTATION,
            "policy_id": policy_id,
            "ast_digest": hashlib.sha256(
                frozen._canonical(document)).hexdigest(),
        },
        "policy_ast": document,
    }


def make_ordering_ast_record(policy_id: str = DEFAULT_POLICY_ID) -> dict:
    """A record in the shape the frozen loader accepts.

    Loaded before it is returned, so a record that no longer parses is
    refused at construction rather than at the first step.
    """
    record = _record(policy_id, ordering_document(policy_id))
    frozen.load_policy(record, policy_id)
    return record


# --- the world binding ---------------------------------------------------


def ordering_view(public_state: dict) -> dict:
    """Project an ordering-world state onto the contract view.

    The projection is this module's only added surface, and it is the
    frozen one: the program still sees exactly the six fields the Boolean
    arm sees on its own world, and a state carrying hidden tables is
    refused rather than projected.
    """
    return frozen._shared_view(public_state)


def _session_from_view(view: dict):
    """Rebuild the world's view of itself from the contract view.

    `ScheduleSession` has no public way to seed prior comparisons —
    `compare` only appends, and the order it would need is the answer —
    so `_comparisons` is written directly. That is the one private field
    this module touches, and it is touched to reuse the world's rule
    rather than to restate it; a hand-written duplicate-pair check here
    would be a second copy of `second_active`'s logic to drift.

    The job order is unknown to the view by construction, so the task
    carries the canonical one. Nothing reads it: neither the validators
    called from here nor `remaining`, which the session derives from the
    comparison count rather than from any claimed budget, so a caller
    cannot widen its own budget by asserting a different one.
    """
    task = {
        "task_id": view["task_id"],
        "split": view["public_world"]["split"],
        "seed": 0,
        "order": tuple(JOB_IDS),
    }
    session = second_active.ScheduleSession(task)
    session._comparisons = {
        (item.get("left"), item.get("right")): item.get("earlier")
        for item in view["observed"]
    }
    return session


def _validate_action(action: policy_action.Action, view: dict) -> None:
    """Admit one action under the ordering world's rules.

    The targets are this world's own spellings, which is the whole
    difference from `boolean_ast_policy._validate_action`. Legality is
    the world's call, not a restatement of it here: a repeated pair, a
    foreign job id, an exhausted budget and a non-permutation are all
    refused by `second_active` with its own text.
    """
    if action.kind == policy_action.PROBE:
        if action.target != "schedule.compare":
            raise policy_action.ActionRefused(
                "probe target must be schedule.compare")
        _refuse_from_world(
            lambda: second_active._validate_comparison(
                _session_from_view(view), action))
    elif action.kind == policy_action.CONSTRUCT:
        if action.target != "schedule.commit":
            raise policy_action.ActionRefused(
                "construct target must be schedule.commit")
        _refuse_from_world(lambda: second_active._validate_order(action))
    elif action.kind == policy_action.STOP:
        if action.target != "schedule.task":
            raise policy_action.ActionRefused(
                "stop target must be schedule.task")
    else:
        raise policy_action.ActionRefused(
            "action %r is not available in the ordering world" % action.kind)


def _refuse_from_world(rule) -> None:
    try:
        rule()
    except second_active.ActionRefused as exc:
        raise policy_action.ActionRefused(str(exc)) from exc


def _refusal(exc: Exception) -> dict:
    return {
        "kind": policy_action.STOP,
        "target": "schedule.task",
        "inputs": {"bridge_refusal": {
            "stage": "ordering-ast-policy-step",
            "reason": (str(exc) or type(exc).__name__)[:500],
        }},
        "evidence_refs": [],
        "requested_resources": {},
    }


def _limits(timeout_ms: int, cpu_seconds: int, max_output_bytes: int,
            memory_bytes: int | None) -> dict:
    return {
        "timeout_ms": frozen._positive(timeout_ms, "timeout_ms"),
        "cpu_seconds": frozen._positive(cpu_seconds, "cpu_seconds"),
        "max_output_bytes": frozen._positive(max_output_bytes,
                                             "max_output_bytes"),
        "memory_bytes": None if memory_bytes is None
        else frozen._positive(memory_bytes, "memory_bytes"),
    }


def ast_step(record: dict, public_state: dict, state: dict | None = None, *,
             timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
             cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
             max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
             memory_bytes: int | None = None) -> dict:
    """Run one ordering-world step and return the action and next state.

    Same shape and same promise as `boolean_ast_policy.ast_step`: the
    caller owns the state, so a fresh interpreter resumes mid-episode
    from it. Raises on refusal rather than converting a failure into a
    recorded `stop`, so a caller retrying a step sees the failure instead
    of a policy that looks like it chose to stop.
    """
    document, _ = frozen._load(record)
    budget = _limits(timeout_ms, cpu_seconds, max_output_bytes, memory_bytes)
    if state is None:
        state = {}
    policy_step.validate_state(state)
    view = ordering_view(public_state)
    result = frozen._run_step(
        document, view, state,
        timeout_ms=budget["timeout_ms"], cpu_seconds=budget["cpu_seconds"],
        max_output_bytes=budget["max_output_bytes"],
        memory_bytes=budget["memory_bytes"],
    )
    action, next_state = policy_action.parse_step_result(result)
    _validate_action(action, view)
    policy_step.validate_state(next_state)
    return {"action": action.as_dict(), "state": next_state}


def choose_action(record: dict, *,
                  timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                  cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                  max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                  memory_bytes: int | None = None):
    """Return the ordering-world episode callback for one AST record."""
    document, _ = frozen._load(record)
    budget = _limits(timeout_ms, cpu_seconds, max_output_bytes, memory_bytes)
    state: dict = {}

    def decide(public_state: dict) -> dict:
        nonlocal state
        try:
            view = ordering_view(public_state)
            policy_step.validate_state(state)
            result = frozen._run_step(
                document, view, state,
                timeout_ms=budget["timeout_ms"],
                cpu_seconds=budget["cpu_seconds"],
                max_output_bytes=budget["max_output_bytes"],
                memory_bytes=budget["memory_bytes"],
            )
            action, next_state = policy_action.parse_step_result(result)
            _validate_action(action, view)
            policy_step.validate_state(next_state)
            state = next_state
            return action.as_dict()
        except Exception as exc:
            return _refusal(exc)

    return decide


# --- the recorded finding ------------------------------------------------


def _observed(name: str) -> dict:
    return _index(_index(_field("view", "observed"), _const(0)),
                  _const(name))


def symbolic_order_document(policy_id: str = DEFAULT_POLICY_ID,
                            comparison: str = "lt") -> dict:
    """The document a comparison-sorting policy would want to write.

    It asks which of the two probed jobs came back earlier, so it can put
    the earlier one first. With `comparison="lt"` that question is asked
    the way a programmer would ask it, and the frozen loader refuses it:

        lt requires two numeric operands

    The same document with `comparison="eq"` loads, because `eq` accepts
    any two operands of one type. That contrast is the finding: the node
    set can *identify* a job the world named but cannot *order* two
    unnamed ones, so a program may choose among orders it wrote down and
    never derive one from the comparison it just paid for.
    """
    left = _observed("earlier")
    right = _index(_observed("left"), _const("earlier"))
    if comparison == "lt":
        condition = {"op": "lt", "left": left, "right": right}
    elif comparison == "eq":
        condition = _eq(left, right)
    else:
        raise ValueError("unknown comparison %r" % (comparison,))
    return {
        "policy_id": policy_id,
        "entry": _if(
            condition,
            _return_action("construct", "schedule.commit",
                           {"order": list(COMMITTED_ORDER)}),
            _return_action("probe", "schedule.compare",
                           {"left": COMPARED_PAIR[0],
                            "right": COMPARED_PAIR[1]},
                           {"queries": 1}),
        ),
    }


def ordering_expressivity() -> dict:
    """What the node set can and cannot do on the ordering world.

    The `can` row is the finding the handoff asked for: the Boolean arms
    are refused on this world, and the refusal is the frozen executor's
    world binding rather than a limit of the node set, so the typed AST
    has a second-world arm after all. The `cannot` row is the cell that
    is a real grammar limit, and it is about ordering rather than action.
    """
    return {
        "version": "s09-ordering-ast-expressivity/1",
        "world": second_active.INSTRUMENT_ID,
        "node_set": frozen._REPRESENTATION,
        "document": "probe one pair, then commit a four-job order",
        "can": [
            "express the ordering decision in the frozen grammar and load "
            "it under the frozen loader, unchanged",
            "run it under the frozen executor against a real "
            "second_active episode, emitting only actions the world applies",
            "rebranch on the view each step instead of keeping state, so "
            "the program is contingent on the comparisons it has seen and "
            "cannot re-probe a pair the world already answered",
        ],
        "cannot": [
            {"behavior": "derive the committed order from the comparison "
                         "it just paid for, so a policy that sorts rather "
                         "than guesses",
             "missing_cell": "no `lt` over two job ids",
             "witness": "the frozen loader refuses the `lt` in "
                        "`symbolic_order_document(policy_id)` with 'lt "
                        "requires two numeric operands', while the same "
                        "document with `comparison=\"eq\"` loads; `eq` "
                        "identifies a job the world named and `lt` cannot "
                        "order two the world has not"},
        ],
        "note": "the committed order in this module is fixed, so the arm "
                "reproduces what the Boolean matrix already found: a "
                "representation that cannot compute a function of its own "
                "observation is committing a table it already had. The "
                "missing cell is what stops it computing one here.",
        "supersedes": {
            "claim": "boolean_ast_policy.expressivity_limits() records the "
                     "typed AST as unable to act on the ordering world at all",
            "refined_to": "that executor is bound to the Boolean world's "
                          "action targets; the node set is not. This module "
                          "runs the same document on this world, so the "
                          "matrix cell should read as a world binding rather "
                          "than an inexpressive representation.",
            "note": "the frozen claim is left in place and is still true of "
                    "boolean_ast_policy; it is only the generalisation from "
                    "one executor to the whole node set that this corrects",
        },
    }
