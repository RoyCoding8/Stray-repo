"""The SWE `World`: the one value the graph executor was missing.

`s09_e1_world_fit_probe` measured that a `World` value carrying SWE is
sufficient — the real `load_policy` admits the record and the real
`_evaluate_guard` steers an arm on 30 of 30 held-out instances — and then
stopped without writing the value into the study. The measured conclusion
was right and the seam was real; what was missing was the twelve fields.

Nothing above the executor changed. `ordering_graph_policy.World` was
always a value rather than a subclass, which is what makes this a binding
and not a re-shape, and the executor is the same one that runs the
ordering and Boolean graphs.

Two fields carry the weight and are worth naming:

`make_view` has to *project*. `s09_swe_world.public_state` takes a
`SweSession` and returns its policy view unaltered, so it projects
nothing, and the guard evaluator — which walks a dotted remainder against
the view mapping — then raises `KeyError: 'observed'` on every SWE
observation field. That is a hole in the caller, not a property of SWE.
The projection below re-publishes what the world already shows at
`symptom.observed` under the key the evaluator reads. It moves the world's
own data and invents nothing, and it refuses a state carrying `tables`
exactly as the Boolean projection does.

`validate_action` is the world's own `admits`, so a refusal at run time is
a SWE refusal naming a SWE budget rather than a graph-executor refusal
naming a target string.
"""

from __future__ import annotations

from . import ordering_graph_policy as graph
from . import policy_action
from . import s09_swe_tasks as tasks
from . import s09_swe_world as swe


def swe_observation_keys() -> frozenset:
    """Every key a SWE observation carries, read off the real panel.

    Written into `field_types` so the loader admits a guard on one. A
    key that the world never publishes would pass at load and raise at
    run, and this is measured rather than typed in so a change to the
    observation shape cannot leave the vocabulary behind.
    """
    keys: set = set()
    for split in tasks.SPLITS:
        for record in tasks.enumerate_instances(split):
            session = swe.SweSession(record)
            session.run_public_test(record["public_tests"][0]["name"])
            for item in session.policy_view()["symptom"]["observed"]:
                keys |= set(item)
    return frozenset(keys)


OBSERVATION_KEYS = swe_observation_keys()

# The guard evaluator reads `observed.<n>.<key>` for an index no episode
# has reached yet, so the vocabulary is declared for the first index and
# the world's own count field covers the rest. `observed.count` needs no
# declaration: `_field_value` answers it before the world is consulted.
_FIELD_TYPES = {"observed.0.%s" % key: "string" for key in OBSERVATION_KEYS}
_FIELD_TYPES.update({"remaining.%s" % name: "integer"
                     for name in swe.BUDGET_LIMITS})


def project_swe_view(public_state: dict) -> dict:
    """Re-publish SWE's observations where the guard evaluator reads.

    `_field_value` walks a dotted remainder against the view mapping, so
    `observed.0.actual` needs `view["observed"]["0"]["actual"]` while the
    SWE world publishes `view["symptom"]["observed"][0]["actual"]`.

    This is a re-shape of a published view, not new evidence: it moves
    what the world already shows. The hidden-table refusal is the
    Boolean projection's own, kept so a caller cannot widen the view by
    handing this one more than the policy view carries.
    """
    if not isinstance(public_state, dict):
        raise swe.ActionRefused("public state must be an object")
    if "tables" in public_state:
        raise swe.ActionRefused("public state exposes hidden tables")
    view = dict(public_state)
    view["observed"] = {
        str(index): item for index, item in
        enumerate(public_state.get("symptom", {}).get("observed", []))}
    return view


def validate_swe_action(action: policy_action.Action, view: dict | None = None
                        ) -> None:
    """Admit one action under the SWE world's own rules.

    `s09_swe_world.admits` is the question asked, not restated: it reads
    the remaining budget and the tests already observed, so an exhausted
    budget is refused with the world's own text. The session argument it
    takes is unused by every branch it reaches, so the static load-time
    call is the same call.
    """
    if not swe.admits(None, view or {}, action.as_dict()):
        raise policy_action.ActionRefused(
            "the swe world does not admit %s/%s now"
            % (action.kind, action.target))


SWE_WORLD = graph.World(
    name="swe",
    probe_target=swe.ACTION_TARGETS[policy_action.OBSERVE],
    construct_target=swe.CONSTRUCT_TARGETS[0],
    stop_target=swe.ACTION_TARGETS[policy_action.STOP],
    allowed_kinds=frozenset(swe.ACTION_TARGETS),
    field_types=dict(_FIELD_TYPES),
    observation_paths=OBSERVATION_KEYS,
    derived_fields={},
    refusals=(policy_action.ActionRefused, swe.ActionRefused),
    validate_action=validate_swe_action,
    make_view=project_swe_view,
    static_view={"observed": {}, "remaining": dict(swe.BUDGET_LIMITS)},
)


def _action(kind: str, target: str, inputs: dict | None = None) -> dict:
    return {"kind": kind, "target": target,
            "inputs": {} if inputs is None else inputs,
            "evidence_refs": [], "requested_resources": {}}


def _arm(guard: dict, action: dict, next_node: str, progress: int) -> dict:
    return {"guard": guard, "action": action, "next": next_node,
            "progress": progress}


def _node(*arms: dict) -> dict:
    return {"kind": graph.GRAPH_NODE_KIND, "arms": list(arms)}


ALWAYS = {"always": True}


def swe_graph_record(policy_id: str = "swe-observation-guard") -> dict:
    """One SWE decision in the graph record shape `load_policy` admits.

    The first arm branches on a field the SWE observation actually
    publishes, and the fallback is the always arm the loader requires to
    be last. It is the record `s09_e1_world_fit_probe` measured: on all
    thirty held-out instances the guard is decided and an arm is chosen.
    """
    return {
        "policy_id": policy_id,
        "start": "observe",
        "nodes": {
            "observe": _node(
                _arm({"field": "observed.0.kind", "op": "ne", "value": ""},
                     _action("construct", swe.CONSTRUCT_TARGETS[0],
                             {"line": 1}), "done", 1),
                _arm(ALWAYS,
                     _action("stop", swe.ACTION_TARGETS[policy_action.STOP]),
                     "done", 0)),
            "done": _node(
                _arm(ALWAYS,
                     _action("stop", swe.ACTION_TARGETS[policy_action.STOP]),
                     "done", 0)),
        },
    }
