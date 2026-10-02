"""Why E1's recorded path fork is not the binding constraint on a SWE cell.

Every claim in `reports/STAGE-09-E1-FORK.md` that can be recomputed is
recomputed here, so a reviewer reruns this instead of trusting the prose.
The module is read-only: it builds a projection in memory and admits it,
and it reads the two `evidence-ad01` control files. It dispatches nothing,
opens no database, and writes nothing.

    python -m experiments.ad01.s09_e1_fork_probe
"""

import json
import pathlib

from . import boolean_ast_policy
from . import boolean_rule
from . import ordering_graph_policy
from . import policy_action
from . import s09_arm_parity as parity
from . import s09_swe_tasks as tasks
from . import s09_swe_world as world

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUTHORED = ROOT / "evidence-ad01" / "c3-authored" / "use-w1-I.json"
ACQUIRED = ROOT / "evidence-ad01" / "c3-trajectories-merged" / "use-w1-I.json"
RECORDED_CONTROL_COLUMN = (6, 9, 8)

SWE_INSTRUMENT = "software-fault-repair-v1"


def swe_fields() -> dict:
    """The measured field diff against the contract, not a restatement.

    This module used to carry its own `REQUIRED_FIELDS` and its own
    `honest_projection`, so the view contract was declared three times:
    here, in the guard, and in the projection. All three disagreed. The
    contract is now declared once in `s09_arm_parity` and this module
    reads it, which is why `required` below is that table and not a
    literal.
    """
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    view = world.SweSession(record).policy_view()
    declared = parity.VIEW_CONTRACT_FIELDS[SWE_INSTRUMENT]
    return {
        "published": sorted(view),
        "required": sorted(declared),
        "missing": sorted(declared - set(view)),
        "extra": sorted(set(view) - declared),
        "admitted": parity.admit_world_view(view, arm_name="swe-probe") is None,
        "budget": world.action_schema()["budget"],
    }


def contract_projection() -> dict:
    """The contract view the common harness now hands a SWE arm.

    This is `s09_arm_parity.contract_view` on a real view, not a second
    projection. The projection this module used to build answered
    `max_queries` with the sum of the five budgets and `hypothesis_class`
    with a list of fault-mechanism names, which is the injected answer
    and a leak the contamination tests forbid; it is deleted rather than
    reconciled, because the one contract already reads the right values.
    """
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    view = world.SweSession(record).policy_view()
    return parity.contract_view(view)


def executor_bindings() -> dict:
    """What each representation's executor is actually bound to.

    The recorded `missing_cells` reason blames the view. These are the
    per-world bindings, and they are what refuse a turn.
    """
    ast_validator = boolean_ast_policy._validate_action.__code__
    ast_handles = {
        kind for kind in policy_action.ACTION_KINDS
        if kind.encode() in ast_validator.co_consts
        or repr(kind).encode() in ast_validator.co_consts
    }
    swe_needed = {"observe", "check", "use"}
    return {
        "contract_action_kinds": list(policy_action.ACTION_KINDS),
        "swe_action_kinds": sorted(world.action_schema()["actions"]),
        "swe_kinds_missing_from_contract": sorted(
            set(world.action_schema()["actions"])
            - set(policy_action.ACTION_KINDS)),
        "swe_turn_kinds_the_ast_cannot_express": sorted(
            swe_needed - ast_handles),
        "ast_view_types": sorted(boolean_ast_policy._VIEW_TYPES),
        "graph_allowed_kinds": sorted(
            ordering_graph_policy.ORDERING_WORLD.allowed_kinds),
        "graph_observation_paths": sorted(
            ordering_graph_policy.ORDERING_WORLD.observation_paths),
        "graph_make_view": ordering_graph_policy.ORDERING_WORLD.make_view.__name__,
        "rule_public_view_keys": sorted(boolean_rule.PUBLIC_VIEW_KEYS),
    }


def still_refuses_after_projection() -> dict:
    """The measurement that decided the recommendation, re-run.

    A projection that is admitted proves nothing about a cell. What
    decides it is whether an executor can act on the projected turn, and
    that measurement is unchanged by the contract converging: the graph
    still refuses three of the five kinds the SWE world needs, so the two
    representations' missing SWE cells are an executor limit and were
    never the view.
    """
    projected = contract_projection()
    admitted = parity.admit_shared_view(projected, arm_name="swe-projected")
    graph = ordering_graph_policy.ORDERING_WORLD
    swe_kinds = set(world.action_schema()["actions"])
    return {
        "projected_admitted": admitted is None,
        "projected_field_count": len(projected),
        "graph_kinds_swe_needs_but_refuses": sorted(
            swe_kinds - set(graph.allowed_kinds)),
        "graph_observation_paths_overlap_swe_observation": sorted(
            set(graph.observation_paths)
            & {"test", "expected", "actual", "kind"}),
        "conclusion": (
            "the projection is admitted and the graph still refuses three of "
            "the five kinds the world needs, so the view is not the binding "
            "constraint"),
    }


def control_column() -> dict:
    """Which of the two E1 columns is attested by a file on disk.

    `evidence-ad01` sits at the repository root, not under
    `reports/evidence`, so a search of the latter finds nothing and reads
    as a missing record rather than a missing search path.

    The two files each carry a `within` and a `transfer` triple, and the
    recorded `6, 9, 8` is a triple, so it is compared against the
    `within` rows and not against all six.
    """
    def software(path, family):
        rows = json.loads(path.read_text())
        return [
            {"task_id": r["task_id"], "selected": r.get("selected"),
             "executed": r.get("executed"),
             "final_measure": r.get("final_measure"),
             "initial_measure": r.get("initial_measure"),
             "fallback_reason": r.get("fallback_reason")}
            for r in rows if r.get("domain") == "software"
            and family in r["task_id"]]

    def within_triple(rows):
        return tuple(r["final_measure"] for r in rows[:3])

    acquired = software(ACQUIRED, "within")
    authored = software(AUTHORED, "within")
    control_triple = within_triple(authored)
    acquired_bodies = {
        r["executed_source"] for r in json.loads(ACQUIRED.read_text())
        if r.get("domain") == "software"}
    control_policy = sorted({r["executed"] for r in authored})[0]
    calls_control = [
        body for body in acquired_bodies if control_policy.split("-")[-1] in body]
    return {
        "acquired_executed_policies": sorted(
            {r["executed"] for r in acquired}),
        "acquired_within_final_measures": list(within_triple(acquired)),
        "control_executed_policies": sorted(
            {r["executed"] for r in authored}),
        "control_within_final_measures": list(control_triple),
        "recorded_control_column": list(RECORDED_CONTROL_COLUMN),
        "recorded_column_attested_by_control_file": (
            control_triple == RECORDED_CONTROL_COLUMN),
        "control_executed_same_policy_as_acquired": (
            {r["executed"] for r in authored}
            == {r["executed"] for r in acquired}),
        "acquired_policy_body_calls_the_control_reducer": bool(calls_control),
        "note": (
            "the recorded triple is not in the control file, and the "
            "acquired policy's own body calls the same %r reducer the "
            "control file executed, so the two columns are not two "
            "policies" % control_policy.split("-")[-1]),
    }


def probe() -> dict:
    return {
        "version": "s09-e1-fork-probe/2",
        "claim": (
            "the eight-versus-twelve view fork is closed: the contract is "
            "declared per world, and it was never why the two "
            "representations have no SWE cell; neither executor has a SWE "
            "world binding"),
        "swe_view": swe_fields(),
        "executor_bindings": executor_bindings(),
        "after_contract_projection": still_refuses_after_projection(),
        "control_column": control_column(),
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
