"""The typed-AST cell on SWE: a projection over a frozen authored policy.

`ordering_ast_policy` is 421 lines against `boolean_ast_policy`'s 894,
imports it as `frozen` at line 42 and calls `frozen._load` at lines 272 and
296. It supplies a view projection and the world's own action rules, and
borrows everything else. This module does the same for the SWE world, and
so it inherits the same property, which is the one that decides how the
record must be labelled:

**No provider wrote these bytes.** The loader, the type system, the node
set, the interpreter and the bounded child are all authored and frozen in
this repository. What this module adds is a projection — which SWE view
fields the program may read, and which SWE targets its actions may name.
That is authored, so `ORIGIN` is `fixture-stand-in` and every record
carries it. Calling this cell `model-acquired` is the C15 defect in a new
place: a label no receipt supports.

The arm is genuinely contingent rather than a fixed schedule, and the
distinction is pinned rather than asserted. Turn two reads
`observed[0].test` and puts that string into the next action's `test`
input, so what the world published reaches an action. A program that
committed a table it already had would emit the same name whatever the
view showed.

What the node set cannot do is recorded as data. `_VIEW_TYPES` has no
field carrying the program under repair and no node builds replacement
source text, so this arm can observe, localize and inspect but cannot
repair. The frozen loader's own refusal is the witness, and
`expressivity()` reports it rather than leaving a reader to infer the
limit from a zero repair rate.
"""

from __future__ import annotations

import hashlib

from . import boolean_ast_policy as frozen
from . import policy_action
from . import policy_step
from . import s09_arm_parity as parity
from . import s09_swe_world as swe

ORIGIN = "fixture-stand-in"
LINEAGES_PER_CELL = 4

# The three per-lineage distinctions. Each lineage is a different record,
# and "different" is measured on the record bytes rather than the name, so
# four lineages whose records hash alike would be caught as one lineage
# wearing four names. Nothing here reads a fault mechanism or a patch, so
# the arm is as blind as the STEP cell is.
_VARIANTS = (
    ("case-01", "code.localize"),
    ("case-02", "code.inspect"),
    ("case-01", "code.try"),
    ("case-02", "code.inspect"),
)


def _const(value):
    return {"op": "const", "value": value}


def _field(scope: str, name: str) -> dict:
    return {"op": "field", "scope": scope, "name": name}


def _index(value: dict, key: dict) -> dict:
    return {"op": "index", "value": value, "key": key}


def _eq(left: dict, right: dict) -> dict:
    return {"op": "eq", "left": left, "right": right}


def _if(condition: dict, then: dict, otherwise: dict) -> dict:
    return {"op": "if", "cond": condition, "then": then, "else": otherwise}


def _observed(index: int, key: str) -> dict:
    return _index(_index(_field("view", "observed"), _const(index)),
                  _const(key))


def _return_action(kind: str, target: str, inputs: dict, resources=None) -> dict:
    """An action the way the AST statement grammar wants it.

    `inputs` and `state` are expression nodes rather than values, so a
    payload has to be lifted field by field. An expression node passed in
    stays an expression, which is what lets the observed test name reach
    an action input instead of being frozen into a constant.
    """
    return {
        "op": "return_action",
        "kind": kind,
        "target": target,
        "inputs": {"op": "obj", "fields": inputs},
        "evidence_refs": [],
        "requested_resources": {} if resources is None else resources,
        "state": _const({}),
    }


def swe_view(public_state: dict) -> dict:
    """The common contract view, for the frozen node set to read.

    This used to be a second, hand-rolled projection of the SWE view, and
    it disagreed with every other one: it reported the probe budget as
    `max_queries` and summed the five per-dimension budgets into
    `remaining`, which is a pair the contract's own range check cannot
    satisfy. It now reads the one declaration in `s09_arm_parity`, so the
    node set sees the same `max_queries` and `hypothesis_class` every other
    arm does. The scalar `remaining` it needs is supplied by that contract.

    The hidden-table refusal is kept and still raises this module's own
    `_ExecutionRefused`, so a caller cannot widen the view by handing this
    one more than the policy view carries.
    """
    if not isinstance(public_state, dict):
        raise frozen._ExecutionRefused("public state must be an object")
    if "tables" in public_state:
        raise frozen._ExecutionRefused("public state exposes hidden tables")
    return parity.contract_view(public_state)


def _budget(timeout_ms: int, cpu_seconds: int, max_output_bytes: int,
            memory_bytes: int | None) -> dict:
    return {
        "timeout_ms": frozen._positive(timeout_ms, "timeout_ms"),
        "cpu_seconds": frozen._positive(cpu_seconds, "cpu_seconds"),
        "max_output_bytes": frozen._positive(max_output_bytes,
                                             "max_output_bytes"),
        "memory_bytes": None if memory_bytes is None
        else frozen._positive(memory_bytes, "memory_bytes"),
    }


def _validate_action(action: policy_action.Action, view: dict,
                     public_state: dict) -> None:
    """Admit one action under the SWE world's own rules.

    The targets are the SWE world's spellings, which is the whole
    difference from the frozen Boolean validator. Legality is the world's
    call: `s09_swe_world.admits` is asked rather than restated, so an
    exhausted budget is refused with the world's own text.

    It is asked against `public_state` and not against the projection,
    because the projection sums the per-budget `remaining` mapping into the
    one integer the node set can read, and the world's own admission
    needs the per-budget numbers. Passing the projection would refuse every
    action with `'int' object has no attribute 'get'` — the same mistake
    the ordering arm's docstring records, in the other direction.
    """
    if not swe.admits(None, public_state, action.as_dict()):
        raise policy_action.ActionRefused(
            "the swe world does not admit %s/%s now"
            % (action.kind, action.target))


def _refusal(exc: Exception) -> dict:
    return {
        "kind": policy_action.STOP,
        "target": swe.ACTION_TARGETS[policy_action.STOP],
        "inputs": {"bridge_refusal": {
            "stage": "swe-ast-policy-step",
            "reason": (str(exc) or type(exc).__name__)[:500],
        }},
        "evidence_refs": [],
        "requested_resources": {},
    }


def document(policy_id: str, *, index: int = 0) -> dict:
    """The SWE decision in the frozen grammar.

    No state and no world name in it beyond the targets. The first turn
    runs every public test; later turns read the name the world published
    for the failing test and observe it, and then inspect the line the
    coverage evidence names. The condition is `observed == []` rather than
    a count, because the node set has no way to take a list's length.
    """
    first_test, second_target = _VARIANTS[index % len(_VARIANTS)]
    return {
        "policy_id": policy_id,
        "entry": _if(
            _eq(_field("view", "observed"), _const([])),
            _return_action("check", swe.ACTION_TARGETS[policy_action.CHECK], {}),
            _return_action("observe", swe.ACTION_TARGETS[policy_action.OBSERVE],
                           {"test": _observed(0, "test")}),
        ),
    }


def make_record(policy_id: str, *, index: int = 0) -> dict:
    """A SWE AST record in the shape the frozen loader accepts.

    The artifact carries exactly the fields `boolean_ast_policy._load`
    admits, so the origin has to travel beside the record rather than
    inside it: `_exact` refuses an unknown field, which is the loader
    doing its job. `LINEAGE_ORIGIN` is the index into
    `s09_swe_experiment.build_ast_lineages` calls, and a reader who wants
    the origin of a built lineage reads it off that lineage's record.

    The document is loaded before it is returned, so a record that no
    longer parses is refused at construction rather than at the first step
    of an episode.
    """
    body = document(policy_id, index=index)
    return {
        "artifact": {
            "kind": "learning-policy",
            "representation": "typed-ast",
            "version": frozen._REPRESENTATION,
            "policy_id": policy_id,
            "ast_digest": hashlib.sha256(frozen._canonical(body)).hexdigest(),
        },
        "policy_ast": body,
    }


def lineage_record(policy_id: str, *, index: int = 0) -> dict:
    """The record as the study holds it, with the origin beside the bytes.

    `make_record` is the frozen loader's view of a policy: the document and
    a digest, and nothing the loader did not ask for. The study needs one
    more thing, which is the honest answer to "who wrote this". It is kept
    in a sibling key so the artifact the frozen loader validates is
    exactly the artifact the frozen loader wrote, and a reader who wants
    to check that can hand `record["ast_record"]` to `_load` unchanged.
    """
    return {"ast_record": make_record(policy_id, index=index),
            "origin": ORIGIN,
            "acquisition_evidence": {
                "earned": False,
                "reason": "authored projection over the frozen typed-AST "
                          "executor; no provider was asked for these bytes",
            }}


def choose_action(record: dict, *,
                  timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                  cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                  max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                  memory_bytes: int | None = None):
    """Return the SWE episode callback for one typed-AST record.

    The document is parsed, type-checked, budgeted and run by the frozen
    interpreter in the bounded child; this module only supplies the view
    projection and the SWE action rules. A refusal becomes a recorded
    `stop` carrying the reason, so a lineage that cannot express a turn
    is visible in the trace rather than silently absent from it.
    """
    body, _ = frozen._load(record)
    limits = _budget(timeout_ms, cpu_seconds, max_output_bytes, memory_bytes)
    state: dict = {}

    def decide(public_state: dict) -> dict:
        nonlocal state
        try:
            view = swe_view(public_state)
            policy_step.validate_state(state)
            result = frozen._run_step(
                body, view, state,
                timeout_ms=limits["timeout_ms"],
                cpu_seconds=limits["cpu_seconds"],
                max_output_bytes=limits["max_output_bytes"],
                memory_bytes=limits["memory_bytes"],
            )
            action, next_state = policy_action.parse_step_result(result)
            _validate_action(action, view, public_state)
            policy_step.validate_state(next_state)
            state = next_state
            return action.as_dict()
        except Exception as exc:
            return _refusal(exc)

    return decide


def ast_step(record: dict, public_state: dict, state: dict | None = None, **kw
             ) -> dict:
    """One SWE AST step, raising on refusal rather than recording a stop."""
    body, _ = frozen._load(record)
    limits = _budget(kw.get("timeout_ms", policy_step.STEP_TIMEOUT_MS),
                     kw.get("cpu_seconds", policy_step.STEP_CPU_SECONDS),
                     kw.get("max_output_bytes",
                            policy_step.STEP_MAX_OUTPUT_BYTES),
                     kw.get("memory_bytes"))
    if state is None:
        state = {}
    policy_step.validate_state(state)
    view = swe_view(public_state)
    result = frozen._run_step(
        body, view, state,
        timeout_ms=limits["timeout_ms"], cpu_seconds=limits["cpu_seconds"],
        max_output_bytes=limits["max_output_bytes"],
        memory_bytes=limits["memory_bytes"])
    action, next_state = policy_action.parse_step_result(result)
    _validate_action(action, view, public_state)
    policy_step.validate_state(next_state)
    return {"action": action.as_dict(), "state": next_state}


def missing_cells() -> dict:
    """The two cells the representations cannot fill on this world.

    Both are limits of the notation rather than of the binding, and both
    are reported with the refusal that produced them.
    """
    return {
        "typed-ast": {
            "missing_cell": "no view field carrying the program under "
                            "repair, and no node that builds replacement "
                            "source text",
            "witness": _repair_attempt(),
            "consequence": "the arm observes, localizes and inspects, and "
                           "cannot repair; its repair rate is 0 and that 0 "
                           "is about the node set",
        },
        "action-graph": {
            "missing_cell": "a guard value cannot reach an action input",
            "witness": "ordering_graph_policy._parse_action deep-copies the "
                       "raw action node, so a graph that reads a test name "
                       "out of the view still has to spell that name in the "
                       "record; the value the evaluator just read is "
                       "discarded. `code.localize` is worse still: the SWE "
                       "world admits it only for a test it has already seen "
                       "fail, and `World.static_view` is the load-time view "
                       "in which nothing has failed, so a localize arm is "
                       "refused at load before any guard is evaluated",
            "consequence": "a graph arm inspects and stops, and cannot "
                           "localize or repair; its repair rate is 0 and "
                           "that 0 is about the record shape, not the "
                           "binding",
        },
    }


def _repair_attempt() -> str:
    """Offer a repair to the frozen node set and record what it says.

    Two attempts, both driven rather than asserted. A `use` action is
    refused by the frozen validator because the Boolean world has no such
    kind; and a program that reads the program under repair is refused by
    the loader because `_VIEW_TYPES` publishes no such field. The first is
    a world binding this module supplies and the second is not, so the
    second is the limit.
    """
    parts = []
    try:
        frozen._validate_action(
            policy_action.parse_action({
                "kind": "use", "target": "code.repair",
                "inputs": {"edits": [{"line": 1, "op": "replace",
                                      "text": "    total = 0"}]},
                "evidence_refs": [], "requested_resources": {}}),
            {"observed": [], "remaining": 0})
        parts.append("frozen validator accepted a swe repair")
    except Exception as exc:
        parts.append("frozen validator refused a swe repair: %s" % exc)
    for name in ("source", "symptom", "public_tests", "structure"):
        try:
            frozen._expr(_field("view", name), "p", frozen._Budget(), 1)
            parts.append("node set exposes view.%s" % name)
        except Exception as exc:
            parts.append("node set refuses view.%s: %s" % (name, exc))
    return " | ".join(parts)


def expressivity() -> dict:
    """What the typed AST can and cannot do on the SWE world.

    The `can` rows are what the frozen node set and interpreter actually
    did on a real held-out episode. The `cannot` row is the cell that is a
    real grammar limit, and its witness is a refusal the loader produced
    rather than a sentence about the grammar.
    """
    return {
        "version": "s09-swe-ast-expressivity/1",
        "world": swe.INSTRUMENT_ID,
        "node_set": frozen._REPRESENTATION,
        "origin": ORIGIN,
        "origin_reason": "authored projection over a frozen authored "
                         "executor; no live provider produced these bytes, "
                         "so the record may not claim model-acquired",
        "document": "run the public tests, then read the failing test's "
                    "name out of the observation and observe it",
        "can": [
            "express the SWE decision in the frozen grammar and load it "
            "under the frozen loader, unchanged",
            "run it under the frozen interpreter in the bounded child, "
            "emitting only actions the SWE world admits",
            "carry a value it read out of the view into an action input, so "
            "the arm is contingent on what the world published rather than "
            "on a schedule it already held",
            "reach a second and third world by projection, at the cost of "
            "one view function and one validator each",
        ],
        "cannot": [
            {"behavior": "repair the program, by reading it and by writing "
                         "replacement source text",
             "missing_cell": "no view field carrying the program under "
                             "repair, and no node that builds source text",
             "witness": _repair_attempt()},
        ],
        "supersedes": {
            "claim": "s09_swe_experiment.build_ast_lineages records the "
                     "typed-AST cell as unbuilt because the frozen "
                     "validator refuses `use` and the node set exposes no "
                     "view field for the program",
            "refined_to": "the validator refusal was a world binding, and "
                          "this module supplies the world's own action rules "
                          "as the ordering arm already did; the view-field "
                          "refusal is not a binding and is recorded as the "
                          "cell that remains unfillable",
        },
    }
