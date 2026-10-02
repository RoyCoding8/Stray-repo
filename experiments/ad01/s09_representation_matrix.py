"""Three representations, one task, one query budget, one verdict.

Expansion question 1 asks which representations a model can acquire and
execute, and which fail for language, construction or runtime reasons. The
three registrations in `s09_arm_parity` each ran a different policy and each
answered only for itself. This module puts the same decision — probe once,
then commit a predictor — into all three, so the only thing that varies is
how the decision is written down.

`compare_arms` compares two arms at a time and refuses three of one kind, so
the three-way result is built by a fold: each arm runs under the identical
`ComparisonConditions`, and a disagreement is recorded rather than resolved.
An arm that fails to run does not get a zero. It gets its own incomparability
reason, because "the AST could not express this" and "the AST expressed it
and scored 0.5" are different findings and the matrix has to keep them apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from . import boolean_ast_policy
from . import boolean_policy
from . import boolean_graph_policy
from . import policy_action
from . import policy_step
from . import s09_arm_parity as parity


def _action(kind: str, target: str, inputs: dict | None = None,
            resources: dict | None = None) -> dict:
    return {"kind": kind, "target": target,
            "inputs": {} if inputs is None else inputs,
            "evidence_refs": [],
            "requested_resources": {} if resources is None else resources}


PROBE_X = 3
# The predictor all three commit: four constant class members. It is a
# fixed guess, not one derived from the observation, and the reason is a
# finding rather than a simplification. A spec is `(const, mask, pair)`
# and expands to a whole 16-bit table, so it is a function of all sixteen
# inputs; an observation is one bit of one input. No representation can
# turn the observation at x=3 into a table, so any policy that claims to
# commit what it saw is committing a table it already had. The graph's
# first draft did exactly that and scored 0.1875 — the constant happened
# to equal the row at x=3 on this task, which is not evidence of
# learning. The three arms below commit the same constants so the
# comparison is about notation and not about what the author knew.
COMMIT_Y = (1, 0, 0, 1)


def _index(node: dict, key: Any) -> dict:
    return {"op": "index", "value": node, "key": key}


def _const(value: Any) -> dict:
    return {"op": "const", "value": value}


def _eq(left: dict, right: dict) -> dict:
    return {"op": "eq", "left": left, "right": right}


def _field(scope: str, name: str) -> dict:
    return {"op": "field", "scope": scope, "name": name}


def _list(*items: dict) -> dict:
    return {"op": "list", "items": list(items)}


def _obj(**fields: Any) -> dict:
    return {"op": "obj", "fields": fields}


def _if(cond: dict, then: dict, otherwise: dict) -> dict:
    return {"op": "if", "cond": cond, "then": then, "else": otherwise}


def _observed_field(index: int, output: int) -> dict:
    return _index(_index(_index(_field("view", "observed"),
                                 _const(0)), _const("y")), _const(output))


def _constant_specs() -> dict:
    return _list(*[_obj(const=_const(bit), mask=_const(0), pair=_const(None))
                   for bit in COMMIT_Y])


def _specs_from_constants(bits: tuple[int, ...]) -> str:
    return "[{'const': %d, 'mask': 0, 'pair': None}, " \
           "{'const': %d, 'mask': 0, 'pair': None}, " \
           "{'const': %d, 'mask': 0, 'pair': None}, " \
           "{'const': %d, 'mask': 0, 'pair': None}]" % bits


def step_policy_source() -> str:
    """The same decision as `typed_ast_document` and `graph_policy_record`."""
    return (
        "def STEP(view, state):\n"
        "    if view['observed']:\n"
        "        return {'action': {'kind': 'construct',\n"
        "                         'target': 'boolean.commit',\n"
        "                         'inputs': {'specs': %s},\n"
        "                         'evidence_refs': [],\n"
        "                         'requested_resources': {}},\n"
        "                'state': {}}\n"
        "    return {'action': {'kind': 'probe',\n"
        "                     'target': 'boolean.query',\n"
        "                     'inputs': {'x': %d},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {'queries': 1}},\n"
        "            'state': {}}\n"
        % (_specs_from_constants(COMMIT_Y), PROBE_X))


def _return_action(kind: str, target: str, inputs: dict | None = None,
                   resources: dict | None = None) -> dict:
    """An action the way the AST statement grammar wants it.

    `inputs` and `state` are expression nodes, not values, so a dict of
    real Python values has to be lifted into the grammar field by field.
    Wrapping the dict in a single `const` is the mistake this avoids: the
    program then reads `{"specs": {"op": "list", ...}}` and hands
    `rules.execute_all` a node where a table belongs, which it reports as
    `illegal-hypothesis` with nothing pointing at the notation.
    """
    return {"op": "return_action", "kind": kind, "target": target,
            "inputs": _obj_expr(inputs or {}),
            "evidence_refs": [],
            "requested_resources": {} if resources is None else resources,
            "state": _const({})}


def _obj_expr(fields: dict) -> dict:
    """Lift a Python dict into `{"op": "obj"}` one field at a time.

    A value that is already an expression node is passed through, so
    `{"specs": _list(...)}` stays a list and `{"x": 3}` becomes a constant.
    """
    return _obj(**{name: value if _is_expr(value) else _const(value)
                   for name, value in fields.items()})


def _is_expr(value: object) -> bool:
    return type(value) is dict and "op" in value \
        and value["op"] in _EXPRESSION_OPS


_EXPRESSION_OPS = frozenset({"const", "list", "obj", "field", "index",
                             "add", "eq", "lt", "not"})


def typed_ast_document(policy_id: str = "e1-typed-ast") -> dict:
    probe = _return_action("probe", "boolean.query", {"x": PROBE_X},
                           {"queries": 1})
    commit = _return_action("construct", "boolean.commit",
                            {"specs": _constant_specs()})
    return {"policy_id": policy_id, "entry": _if(
        _eq(_field("view", "observed"), _const([])), probe, commit)}


def typed_ast_record(policy_id: str = "e1-typed-ast") -> dict:
    import hashlib
    import json
    document = typed_ast_document(policy_id)
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True).encode()
    return {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": boolean_ast_policy._REPRESENTATION,
        "policy_id": policy_id,
        "ast_digest": hashlib.sha256(encoded).hexdigest()},
        "policy_ast": document}


def _arm(guard: dict, action: dict, next_node: str, progress: int) -> dict:
    return {"guard": guard, "action": action, "next": next_node,
            "progress": progress}


_ALWAYS = {"always": True}


def graph_policy_record(policy_id: str = "e1-action-graph") -> dict:
    return {
        "policy_id": policy_id, "start": "probe",
        "nodes": {
            "probe": {"kind": "action", "arms": [
                _arm({"field": "observed.count", "op": "eq", "value": 0},
                     _action("probe", "boolean.query", {"x": PROBE_X},
                             {"queries": 1}), "commit", 1),
                _arm(_ALWAYS, _action("stop", "boolean.task"), "probe", 0)]},
            "commit": {"kind": "action", "arms": [
                _arm({"field": "observed.0.y.0", "op": "eq",
                      "value": COMMIT_Y[0]},
                     _action("construct", "boolean.commit", {"specs": [
                         {"const": bit, "mask": 0, "pair": None}
                         for bit in COMMIT_Y]}), "stop", 1),
                _arm(_ALWAYS, _action("stop", "boolean.task"), "probe", 0)]},
            "stop": {"kind": "action", "arms": [
                _arm(_ALWAYS, _action("stop", "boolean.task"), "stop", 0)]},
        }}


@dataclass(frozen=True)
class MatrixCell:
    arm_name: str
    representation_kind: str
    policy_record_digest: str
    comparable: bool
    reason: str = ""
    queries_spent: int | None = None
    turns_taken: int | None = None
    overall: float | None = None
    score: Mapping[str, Any] | None = None

    def as_dict(self) -> dict:
        return {
            "arm_name": self.arm_name,
            "representation_kind": self.representation_kind,
            "policy_record_digest": self.policy_record_digest,
            "comparable": self.comparable,
            "reason": self.reason,
            "queries_spent": self.queries_spent,
            "turns_taken": self.turns_taken,
            "overall": self.overall,
            "score": dict(self.score) if self.score else None,
        }


@dataclass(frozen=True)
class RepresentationMatrix:
    conditions: parity.ComparisonConditions
    cells: tuple[MatrixCell, ...] = ()
    incompatibilities: tuple[parity.Incomparability, ...] = ()

    @property
    def comparable_arms(self) -> tuple[str, ...]:
        return tuple(c.arm_name for c in self.cells if c.comparable)

    @property
    def failed_arms(self) -> tuple[str, ...]:
        return tuple(c.arm_name for c in self.cells if not c.comparable)

    @property
    def failed_reasons(self) -> Mapping[str, str]:
        return {c.arm_name: c.reason for c in self.cells if not c.comparable}

    def agreeing(self) -> tuple[str, ...]:
        """Arms that ran and reached the same score, if any two did.

        A single number per arm, because the three representations are
        graded on the same world and a difference in `overall` is the
        finding. `None` when they do not agree, which is not a failure of
        the matrix.
        """
        totals = {c.arm_name: c.overall for c in self.cells
                  if c.comparable and c.overall is not None}
        if len(totals) < 2 or len(set(totals.values())) != 1:
            return ()
        return tuple(sorted(totals))

    def as_dict(self) -> dict:
        return {
            "conditions": {"split": self.conditions.split,
                           "seed": self.conditions.seed,
                           "max_queries": self.conditions.max_queries},
            "cells": [c.as_dict() for c in self.cells],
            "incompatibilities": [i.as_dict() for i in self.incompatibilities],
        }


def build_registry(specs: Mapping[str, dict] | None = None
                   ) -> parity.ArmRegistry:
    """Register one arm per representation, all non-double.

    A test double would make `compare_arms` return `incomparable` on its own,
    so a matrix built out of them could not report agreement even if the
    representations did agree. These are the three real executors.
    """
    specs = {
        "step": step_policy_record(),
        "ast": typed_ast_record(),
        "graph": graph_policy_record(),
    } if specs is None else dict(specs)
    registry = parity.ArmRegistry()
    outcomes = [
        parity.register_python_step(registry, name="step",
                                    policy_record=specs["step"]),
        parity.register_typed_ast(registry, name="ast",
                                  policy_record=specs["ast"]),
        parity.register_action_graph(registry, name="graph",
                                     policy_record=specs["graph"]),
    ]
    for outcome in outcomes:
        if isinstance(outcome, parity.Incomparability):
            raise ValueError("matrix arm refused registration: %s"
                             % outcome.as_dict())
    return registry


def step_policy_record() -> dict:
    return policy_step.make_policy_artifact(
        step_policy_source(), origin="authored-control",
        applicability={"world": 0, "arm": "I"})


def run_matrix(registry: parity.ArmRegistry | None = None,
               conditions: parity.ComparisonConditions | None = None
               ) -> RepresentationMatrix:
    """One arm per representation, one task, one budget each.

    Each arm is run by `compare_arms` against a second arm, because that is
    the only runner the harness offers and it refuses a single arm. The
    partner differs; the conditions, the world and the query budget do not,
    and those are what the parity checks compare.
    """
    registry = build_registry() if registry is None else registry
    conditions = parity.ComparisonConditions(
        split="dev", seed=4, max_queries=8) if conditions is None \
        else conditions
    names = list(registry.names)
    cells: dict[str, MatrixCell] = {}
    issues: list[parity.Incomparability] = []
    for index, name in enumerate(names):
        partner = names[(index + 1) % len(names)]
        result = parity.compare_arms(registry, (name, partner), conditions)
        record = next((r for r in result.records if r.arm_name == name), None)
        if record is None:
            reason = next((str(i.reason) for i in result.incompatibilities
                           if name in i.arm_names), "no-record")
            cells[name] = MatrixCell(
                arm_name=name,
                representation_kind=registry._arms[name].representation_kind,
                policy_record_digest=registry._arms[name].policy_record_digest,
                comparable=False, reason=reason)
            issues.extend(i for i in result.incompatibilities
                          if name in i.arm_names)
            continue
        score = record.score if isinstance(record.score, dict) else {}
        cells[name] = MatrixCell(
            arm_name=name,
            representation_kind=record.representation_kind,
            policy_record_digest=record.policy_record_digest,
            comparable=True, queries_spent=record.queries_spent,
            turns_taken=record.turns_taken,
            overall=score.get("overall"), score=record.score)
    ordered = tuple(cells[name] for name in names)
    return RepresentationMatrix(conditions, ordered, tuple(issues))


# --- the ordering-constraints world -------------------------------------
#
# The same three-representation question on a second instrument. Its
# action vocabulary differs from the Boolean world's in every field, so an
# arm written for one is refused by the other rather than mis-scored: the
# Boolean arms are refused with `probe target must be schedule.compare`.
# That refusal is a real answer to the handoff's first question - the
# representation is portable, the *policy* is not - and this is the
# concrete attempted behaviour that demonstrates it.

ORDERING_JOBS = ("verify", "build", "analysis", "deploy")
ORDERING_ORDER = ("build", "analysis", "verify", "deploy")


def ordering_graph_record(policy_id: str = "e1-ordering-graph") -> dict:
    """A graph for the ordering world, which its executor cannot load.

    Kept as the concrete attempted behaviour the handoff asks for. The
    graph executor validates every action against the *Boolean* world, so
    this record is refused at load with

        node probe arm 0 action: probe target must be boolean.query

    which is a real expressivity limit of the executor rather than of the
    graph notation: the same decision is loadable on the Boolean world.
    `expressivity_limits()` in `boolean_ast_policy` already records the
    equivalent limit for the typed AST, and this is the graph's.
    """
    return {
        "policy_id": policy_id, "start": "probe",
        "nodes": {
            "probe": {"kind": "action", "arms": [
                _arm({"field": "observed.count", "op": "eq", "value": 0},
                     _action("probe", "schedule.compare",
                             {"left": ORDERING_JOBS[0],
                              "right": ORDERING_JOBS[1]},
                             {"queries": 1}), "decide", 1),
                _arm(_ALWAYS, _action("stop", "schedule.task"), "probe", 0)]},
            "decide": {"kind": "action", "arms": [
                _arm(_ALWAYS,
                     _action("construct", "schedule.commit",
                             {"order": list(ORDERING_ORDER)}), "stop", 1),
                ]},
            "stop": {"kind": "action", "arms": [
                _arm(_ALWAYS, _action("stop", "schedule.task"), "stop", 0)]},
        }}


def ordering_step_source() -> str:
    return (
        "def STEP(view, state):\n"
        "    if view['observed']:\n"
        "        return {'action': {'kind': 'construct',\n"
        "                         'target': 'schedule.commit',\n"
        "                         'inputs': {'order': %r},\n"
        "                         'evidence_refs': [],\n"
        "                         'requested_resources': {}},\n"
        "                'state': {}}\n"
        "    return {'action': {'kind': 'probe',\n"
        "                     'target': 'schedule.compare',\n"
        "                     'inputs': {'left': %r, 'right': %r},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {'queries': 1}},\n"
        "            'state': {}}\n"
        % (list(ORDERING_ORDER), ORDERING_JOBS[0], ORDERING_JOBS[1]))


def ordering_step_record() -> dict:
    return policy_step.make_policy_artifact(
        ordering_step_source(), origin="authored-control",
        applicability={"world": 1, "arm": "I"})


def ordering_step_decider(record: dict):
    """The ordering world's own STEP arm, validated by the world.

    `boolean_policy.choose_action` runs the bounded child and then checks
    the action with `_validate_boolean_action`, so an ordering STEP program
    — whose source is arbitrary Python and perfectly expressible — is
    refused with `probe target must be boolean.query`. That is a *world
    binding*, not an expressivity limit: the same refusal turned out to be
    the whole story for the typed AST and the action graph, and Jev scored
    the binding reading 0.90 against 0.10 for a limit.

    The fix is not to teach the Boolean executor about a second world. It
    is for the second world to validate its own actions — which is what
    `ordering_graph_policy.ORDERING_WORLD` already does for the graph, and
    reusing it here means there is one description of the ordering world's
    rules rather than two. The step itself is the shared bounded child
    every representation runs.
    """
    from . import ordering_graph_policy

    state: dict = {}
    world = ordering_graph_policy.ORDERING_WORLD

    def decide(view: dict) -> dict:
        """Takes the contract view as the harness delivers it.

        `contract_view` already publishes the shared contract with this
        world's own targets — `schedule.compare`, `schedule.commit`,
        `schedule.task` — so converting it *into* a Boolean world state
        first was both unnecessary and wrong: it renamed construct to
        `commit` and dropped `hypothesis_class`, `max_queries` and `split`,
        and the step then refused the state for missing them. The ordering
        executors read the shared view the harness already hands them.
        """
        nonlocal state
        result = boolean_policy._run_shared_policy_step(
            record, dict(view), state,
            timeout_ms=policy_step.STEP_TIMEOUT_MS,
            cpu_seconds=policy_step.STEP_CPU_SECONDS,
            max_output_bytes=policy_step.STEP_MAX_OUTPUT_BYTES,
            memory_bytes=None)
        action, state = policy_action.parse_step_result(result)
        # The world checks the action under its own rules, so a refusal
        # here is a world refusal and not a representation failure.
        world.validate_action(action, view=view)
        policy_step.validate_state(state)
        return action.as_dict()

    return decide


def ordering_step_factory(record: dict, *,
                          timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                          cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                          max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                          memory_bytes: int | None = None):
    del timeout_ms, cpu_seconds, max_output_bytes, memory_bytes
    return ordering_step_decider(record)


def build_ordering_registry() -> parity.ArmRegistry:
    """All three representations, each validated by the world that owns it.

    Two of the three are registered through `s09_arm_parity`'s factories and
    the third is the world's own driver, because the harness's STEP factory
    is Boolean-typed. Mixing them is the point: the comparison is between
    representations on one world, and the world is what adjudicates the
    actions, so a refusal is attributable to the representation rather than
    to whichever executor happened to run it.
    """
    from . import ordering_ast_policy
    registry = parity.ArmRegistry()
    for name, kind, factory, record in (
            ("graph", parity.ACTION_GRAPH, None, ordering_graph_record()),
            ("step", parity.PYTHON_STEP, None, ordering_step_record()),
            ("ast", parity.TYPED_AST, None, ordering_ast_policy
             .make_ordering_ast_record())):
        if factory is not None:
            outcome = factory(registry, name=name, policy_record=record)
        else:
            driver = (ordering_step_factory if name == "step"
                      else ordering_ast_driver_factory)
            if name == "graph":
                driver = lambda rec, **kw: parity._action_graph_factory(
                    rec, world="ordering", **kw)
            outcome = registry.register(
                name=name, representation_kind=kind,
                driver_factory=driver, policy_record=record)
        if isinstance(outcome, parity.Incomparability):
            raise ValueError("ordering %s refused: %s"
                             % (name, outcome.as_dict()))
    return registry


def ordering_ast_driver_factory(record: dict, *,
                                timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                                cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                                max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                                memory_bytes: int | None = None):
    """The typed AST on the ordering world, through its own executor.

    `ordering_ast_policy` supplies a view projection and the world's own
    action rules, then borrows `boolean_ast_policy`'s frozen loader and
    bounded child unchanged — so a pass here is evidence about the frozen
    node set rather than about a substitute interpreter.
    """
    from . import ordering_ast_policy
    del timeout_ms, cpu_seconds, max_output_bytes, memory_bytes
    return ordering_ast_policy.choose_action(record)
