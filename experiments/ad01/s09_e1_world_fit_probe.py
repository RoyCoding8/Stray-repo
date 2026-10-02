"""Can a `World` *value* carry SWE, or does the executor need a re-shape?

E1's two missing cells are refused before an episode begins, so the
question is cheap to answer and worth answering exactly. Lane W1 measured
that the refusal reproduces. This module measures *why*, and it is the
decision input for whether the blocker is a missing binding or a missing
shape.

The fork report and the W1 record both describe a `World` as a value a SWE
world could supply. This module tests that rather than assuming it, by
building the most favourable value a caller could write, every field
taken from the SWE world's own published constants, and then running the
real `load_policy` and the real guard evaluator over a real SWE view. The
seam that matters is `make_view`: it is a `World` field, and the executor
calls it at line 501 before it evaluates any guard, so a value that
projects the SWE view into the shape the evaluator reads is a legitimate
way to close the cell, and a value that does not is a hole in the probe
rather than a fact about SWE.

Nothing here dispatches, opens a database, or writes. The SWE world is a
local oracle.

    .venv/bin/python -m experiments.ad01.s09_e1_world_fit_probe
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _entry in (ROOT, ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from experiments.ad01 import boolean_ast_policy  # noqa: E402
from experiments.ad01 import ordering_ast_policy  # noqa: E402
from experiments.ad01 import ordering_graph_policy as graph  # noqa: E402
from experiments.ad01 import policy_action  # noqa: E402
from experiments.ad01 import s09_swe_tasks as tasks  # noqa: E402
from experiments.ad01 import s09_swe_world as swe  # noqa: E402


def _observed_record() -> tuple[dict, dict, list]:
    """A held-out instance with a real observation already in it.

    The keys are read from an observation the world produced, not from a
    remembered list, because the whole argument is about which keys a SWE
    observation names.
    """
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    session = swe.SweSession(record)
    session.run_public_test(record["public_tests"][0]["name"])
    return record, session.policy_view(), sorted(
        session.policy_view()["symptom"]["observed"][0])


def swe_world_value(keys: list, **overrides):
    """The most favourable `World` a caller could write today.

    Every field is filled from the SWE world's own published constants and
    the observation keys are enumerated into `field_types` so the loader
    admits them. `make_view` projects the SWE view into the shape the
    evaluator reads, because the executor calls `world.make_view` before
    it evaluates any guard and a value that does not project would be
    measuring this probe's own omission rather than SWE.
    """
    value = {
        "name": "swe",
        "probe_target": swe.ACTION_TARGETS[policy_action.OBSERVE],
        "construct_target": swe.CONSTRUCT_TARGETS[0],
        "stop_target": swe.ACTION_TARGETS[policy_action.STOP],
        "allowed_kinds": frozenset(swe.ACTION_TARGETS),
        "field_types": {"observed.0.%s" % key: "string" for key in keys},
        "observation_paths": frozenset(keys),
        "derived_fields": {},
        "refusals": (policy_action.ActionRefused, swe.ActionRefused),
        "validate_action": lambda action, view=None: None,
        "make_view": project_swe_view,
        "static_view": {},
    }
    value.update(overrides)
    return graph.World(**value)


def project_swe_view(public_state: dict) -> dict:
    """Re-expose SWE's observations where the executor's evaluator reads.

    `_field_value` walks a dotted remainder against the view mapping, so
    `observed.0.actual` needs `view["observed"]["0"]["actual"]` while the
    SWE world publishes `view["symptom"]["observed"][0]["actual"]`. This
    is a re-shape of a published view, not new evidence: it moves what the
    world already shows, and it invents nothing.
    """
    view = dict(public_state)
    view["observed"] = {
        str(index): item for index, item in
        enumerate(public_state.get("symptom", {}).get("observed", []))}
    return view


def _unprojected_field_resolution(view: dict, keys: list) -> dict:
    """The evaluator's answer when `make_view` is the world's own.

    `swe.public_state` takes a `SweSession` and returns its policy view
    unaltered, so it projects nothing. This records what a value that
    failed to project looks like, because that was the first thing this
    module measured and it looked like a property of SWE.
    """
    world = swe_world_value(keys, make_view=lambda public_state: public_state)
    field = "observed.0.%s" % keys[0]
    loaded = graph._field_type(field, "guard", world)
    try:
        evaluated, failure = graph._field_value(view, {}, field, world), None
    except Exception as exc:
        evaluated, failure = None, "%s: %s" % (type(exc).__name__, exc)
    return {
        "field": field,
        "loader_admits": loaded is not None,
        "loader_says_type": loaded,
        "evaluator_returns": evaluated,
        "evaluator_failure": failure,
    }


def _arm(guard: dict, action: dict, next_node: str) -> dict:
    return {"guard": guard, "action": action, "next": next_node, "progress": 0}


def _node(*arms: dict) -> dict:
    return {"kind": graph.GRAPH_NODE_KIND, "arms": list(arms)}


def swe_graph_policy(field: str) -> dict:
    """A minimal graph that branches on one SWE observation field.

    It is written in the record shape `load_policy` admits, so admitting it
    and evaluating its guard exercises the executor rather than a
    reconstruction of it.
    """
    return {
        "policy_id": "swe-observation-guard",
        "start": "n0",
        "nodes": {
            "n0": _node(
                _arm({"field": field, "op": "ne", "value": ""},
                     {"kind": policy_action.CONSTRUCT,
                      "target": swe.CONSTRUCT_TARGETS[0],
                      "inputs": {"line": 1}}, "n1"),
                _arm({"always": True},
                     {"kind": policy_action.STOP,
                      "target": swe.ACTION_TARGETS[policy_action.STOP],
                      "inputs": {}}, "n1")),
            "n1": _node(_arm(
                {"always": True},
                {"kind": policy_action.STOP,
                 "target": swe.ACTION_TARGETS[policy_action.STOP],
                 "inputs": {}}, "n1")),
        },
    }


def field_resolution(view: dict, keys: list) -> dict:
    """Does a SWE guard field load, and does the executor then act on it?

    Both stages run for real: the record goes through `load_policy`, the
    view through `make_view`, and the guard through `_evaluate_guard`. A
    field that loads and then steers an action is the only thing that
    closes the cell, so anything less is reported as it is.
    """
    world = swe_world_value(keys)
    field = "observed.0.%s" % keys[0]
    record = swe_graph_policy(field)
    loaded = graph._field_type(field, "guard", world)
    unprojected = _unprojected_field_resolution(view, keys)
    result = {
        "field": field,
        "loader_admits": loaded is not None,
        "loader_says_type": loaded,
        "policy_admitted": False,
        "guard_evaluated": False,
        "chosen_action": None,
        "unprojected_make_view": unprojected,
    }
    try:
        policy = graph.load_policy(record, world=world)
        result["policy_admitted"] = True
        projected = graph.make_view(view, world=world)
        node = policy.nodes[policy.start]
        arm = next(candidate for candidate in node.arms
                   if graph._evaluate_guard(candidate.guard, projected, {},
                                            world))
        result["guard_evaluated"] = True
        result["chosen_action"] = "%s/%s" % (arm.action.kind, arm.action.target)
    except Exception as exc:
        result["failure"] = "%s: %s" % (type(exc).__name__, exc)
    result["both_stages_agree"] = (result["policy_admitted"]
                                   and result["guard_evaluated"])
    return result


def field_type_fallback(keys: list) -> dict:
    """Whether `observation_paths` can rescue a SWE key.

    The brief and the W1 record both say `field_type` falls back to the
    ordering regex "regardless of `observation_paths`". That is not what
    the code does, and the difference matters for anyone writing the fix.
    The code consults `observation_paths`, but only after the regex has
    already matched, and the regex hard-codes the ordering key names, so it
    never matches a SWE key and the `observation_paths` check is never
    reached. The conclusion survives; the mechanism in the brief does not.
    """
    world = swe_world_value(keys, field_types={})
    regex = graph._ORDERING_OBSERVATION_FIELD
    ordering = graph.ORDERING_WORLD
    return {
        "regex_pattern": regex.pattern,
        "regex_matches_an_ordering_field": bool(
            regex.fullmatch("observed.0.left")),
        "regex_matches_a_swe_field": bool(
            regex.fullmatch("observed.0.%s" % keys[0])),
        "ordering_field_type_via_paths": ordering.field_type("observed.0.left"),
        "ordering_field_type_via_regex_only": _ordering_field_type_no_paths(),
        "swe_paths_supplied": sorted(world.observation_paths),
        "field_type_with_paths_and_no_field_types": world.field_type(
            "observed.0.%s" % keys[0]),
        "reading": ("the ordering regex is tested first and its key"
                    " alternation is fixed at module scope, so a SWE key"
                    " never reaches the observation_paths check and the"
                    " paths cannot make it resolvable"),
    }


def _ordering_field_type_no_paths() -> str | None:
    """The ordering world's answer for its own field, with paths withheld.

    A world that resolved `observed.0.left` without its `observation_paths`
    would be reading the regex alone, and a world that stops resolving it
    with the paths withheld shows the check is live. Either answer locates
    where `observation_paths` acts, without reading the source to find out.
    """
    withheld = graph.dataclasses.replace(
        graph.ORDERING_WORLD, observation_paths=frozenset())
    return withheld.field_type("observed.0.left")


def observation_index_is_finite(view: dict, keys: list) -> dict:
    """Whether `derived_fields` can cover `observed.<N>.<key>` for all N.

    `derived_fields` is an exact-match dict, so a guard field is only
    covered if its whole string is a key at load time. That is only
    possible if the observation count is known when the policy is
    admitted. It is not: the list grows with the episode's probe
    allowance, which is 303 on this world, against 2 observations present
    after the public tests run.
    """
    allowance = swe.BUDGET_LIMITS.get("probe")
    return {
        "observations_after_one_public_test": len(
            view["symptom"]["observed"]),
        "public_cases_in_the_world": tasks.PUBLIC_CASES,
        "probe_allowance": allowance,
        "derived_fields_reach_the_loader": _derived_fields_reach_loader(keys),
        "reading": ("a guard names the index it reads, and derived_fields"
                    " is consulted by the evaluator but not by the loader,"
                    " so an index no episode has reached yet cannot be"
                    " admitted at load time"),
    }


def _derived_fields_reach_loader(keys: list) -> bool:
    """Whether a `derived_fields` entry can make a field load at all.

    The escape hatch is a dict on the world, and the evaluator consults it.
    The loader consults `field_types` instead, so an entry there covers
    evaluation and not admission. This asks the loader, because the answer
    decides whether the hatch is usable for a field the world does not
    publish.
    """
    world = swe_world_value(keys, field_types={}, derived_fields={
        "observed.0.%s" % keys[0]: lambda view: "value"})
    try:
        return graph._field_type("observed.0.%s" % keys[0], "guard", world) \
            is not None
    except Exception:
        return False


def fixed_target_fields() -> dict:
    """How much of the three-target shape is load-bearing.

    The brief calls the three targets the reason the shape does not fit.
    Two of the three are never read anywhere in production, so they are
    not the constraint. The third is read, and it is read from the module
    global rather than from the world the validator was handed, which is a
    separate finding.
    """
    source = Path(graph.__file__).read_text(encoding="utf-8").splitlines()
    reads = {}
    for field in ("probe_target", "construct_target", "stop_target"):
        reads[field] = [
            line.strip() for line in source
            if field in line
            and not line.strip().startswith(field + ":")
            and (field + "=") not in line]
    validator = "\n".join(reads["stop_target"])
    return {
        "production_reads": {name: len(lines)
                             for name, lines in reads.items()},
        "stop_target_reads_name_the_module_global": (
            "ORDERING_WORLD.stop_target" in validator),
        "validate_action_signature_takes_a_world": _validate_action_takes_a_world(),
        "reading": ("probe_target and construct_target are declared and"
                    " assigned but never read, so the three-target shape is"
                    " not what blocks SWE; stop_target is read from"
                    " ORDERING_WORLD rather than from a world the"
                    " validator is handed, because it is handed none"),
    }


def _validate_action_takes_a_world() -> bool:
    """Whether the `validate_action` a world supplies can see that world.

    `World.validate_action` is a field a caller fills, so the caller
    supplies the callable too. The question is only whether the ordering
    world's own callable has any way to reach the world it was chosen
    for, which its signature answers.
    """
    parameters = inspect.signature(
        graph.ORDERING_WORLD.validate_action).parameters
    return "world" in parameters


def ast_seam() -> dict:
    """Whether the AST executor has a world seam at all.

    The graph takes a `World`; the AST does not. It gates view field names
    on a module-level `_VIEW_TYPES` and hard-codes its three action
    targets in the validator. How a second world is reached is measured
    rather than assumed, because the two answers imply different costs:
    a second arm that delegates to the frozen loader leaves one loader to
    change for a third world, and one that redefines it leaves two.
    """
    source = Path(boolean_ast_policy.__file__).read_text(encoding="utf-8")
    signatures = [line for line in source.splitlines()
                  if line.startswith("def ") and "world" in line]
    return {
        "ast_takes_a_world_parameter": bool(signatures),
        "ast_world_signatures": signatures,
        "view_types_is_module_level": "_VIEW_TYPES = {" in source,
        "view_type_names": sorted(boolean_ast_policy._VIEW_TYPES),
        "hardcoded_targets_in_validator": sorted(
            target for target in ("boolean.query", "boolean.commit",
                                  "boolean.task") if target in source),
    }


def second_world_reach() -> dict:
    """How `ordering_ast_policy` reaches a second world.

    The question is whether it redefines the frozen executor or borrows
    it, because the first means a third world costs another module and the
    second means it costs a projection. The module's own docstring claims
    the second, so the delegation is read off the imports and calls rather
    than taken from the prose.
    """
    second = Path(ordering_ast_policy.__file__).read_text(encoding="utf-8")
    first = Path(boolean_ast_policy.__file__).read_text(encoding="utf-8")
    return {
        "second_world_module": ordering_ast_policy.__name__,
        "lines_second": len(second.splitlines()),
        "lines_first": len(first.splitlines()),
        "imports_first_as_frozen": "as frozen" in second,
        "delegates_the_frozen_loader": "frozen._load" in second,
        "redefines_validate_action": "def _validate_action" in second,
        "reach": "delegates" if "as frozen" in second else "redefines",
        "reading": ("the second world is reached by projecting the view and"
                    " borrowing the frozen loader and node set, so a third"
                    " world costs a projection rather than a copied module"),
    }


def closes_across_held_out() -> dict:
    """Whether the closing `World` value is a one-instance accident.

    One instance closing proves a seam exists, not that the seam holds. The
    value is rebuilt per instance from that instance's own observation
    keys, and the record is re-admitted and re-evaluated for every held-out
    task, which is the grid the ceiling matrix ran.
    """
    closed, failures = 0, []
    for template in tasks.HELD_OUT_TEMPLATES:
        for mechanism in tasks.HELD_OUT_MECHANISMS:
            record = tasks.instance("held_out", template, mechanism)
            session = swe.SweSession(record)
            session.run_public_test(record["public_tests"][0]["name"])
            view = session.policy_view()
            keys = sorted(view["symptom"]["observed"][0])
            world = swe_world_value(keys)
            try:
                policy = graph.load_policy(
                    swe_graph_policy("observed.0.%s" % keys[0]), world=world)
                projected = graph.make_view(view, world=world)
                node = policy.nodes[policy.start]
                next(arm for arm in node.arms
                     if graph._evaluate_guard(arm.guard, projected, {}, world))
                closed += 1
            except Exception as exc:
                failures.append({"template": template, "mechanism": mechanism,
                                 "failure": "%s: %s"
                                            % (type(exc).__name__, exc)})
    return {
        "held_out_instances": len(tasks.HELD_OUT_TEMPLATES)
        * len(tasks.HELD_OUT_MECHANISMS),
        "closed": closed,
        "failures": failures,
        "closes_everywhere": not failures,
    }


def probe() -> dict:
    record, view, keys = _observed_record()
    resolution = field_resolution(view, keys)
    reach = second_world_reach()
    return {
        "version": "ad01-e1-world-fit-probe/2",
        "lane": "AA1",
        "instrument": swe.INSTRUMENT_ID,
        "live_dispatches": {"count": 0, "currencies": {}},
        "swe_observation_keys": keys,
        "swe_action_kinds": sorted(swe.ACTION_TARGETS),
        "swe_targets": {kind: list(target) if isinstance(target, tuple)
                        else target
                        for kind, target in swe.ACTION_TARGETS.items()},
        "ordering_allowed_kinds": sorted(
            graph.ORDERING_WORLD.allowed_kinds),
        "field_resolution": resolution,
        "field_type_fallback": field_type_fallback(keys),
        "observation_index": observation_index_is_finite(view, keys),
        "fixed_target_fields": fixed_target_fields(),
        "ast_seam": ast_seam(),
        "second_world_reach": reach,
        "closes_across_held_out": closes_across_held_out(),
        "verdict": _verdict(resolution, reach),
    }


def _verdict(resolution: dict, reach: dict) -> dict:
    """What the measurements support, per representation.

    The graph and the AST are not one answer. The graph takes a `World`
    and the graph cell is decided by whether a value can carry SWE. The
    AST takes no `World` at all, so no value can carry SWE into it and the
    AST cell is decided by whether its loader is reachable another way,
    which the second-world arm demonstrates. Reporting one verdict for
    both is what made the first version of this module wrong.
    """
    graph_closed = resolution["both_stages_agree"]
    return {
        "graph": {
            "a_world_value_is_sufficient": graph_closed,
            "reason": (
                "a World value whose make_view projects the SWE view into"
                " the shape the evaluator reads is admitted by the real"
                " load_policy and steers a real arm through the real guard"
                " evaluator, so the graph cell is a binding and not a"
                " re-shape" if graph_closed else
                "no World value carried a SWE guard field through both the"
                " loader and the guard evaluator"),
        },
        "ast": {
            "a_world_value_is_sufficient": False,
            "reason": ("boolean_ast_policy takes no World, so a value"
                       " cannot reach it; the second world is reached by %s"
                       " instead, so a SWE AST arm costs the same shape of"
                       " work that arm already did" % reach["reach"]),
        },
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
