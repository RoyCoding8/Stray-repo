"""AG01-EXP privileged grader: latent world facts, equal end-use solver, controls.

Simulator and checker regions may import this module. Policy and
runner-observation paths must not: importing first from such a path raises,
and grade/latent_truth refuse calls issued from those paths.
"""

from __future__ import annotations

import hashlib
import inspect
import sys

GRADER_SEED = "AG01-GRADER-v1"
SOLVER_COST_PER_TASK = 1
POLICY_PATH_MARK = "_AG01_POLICY_OBSERVATION_PATH"
_DENY = {"settlement.agenda_policy", "agenda_policy",
         "experiments.agenda01.observations"}


def _policy_path_loaded() -> str | None:
    for name, mod in tuple(sys.modules.items()):
        if getattr(mod, POLICY_PATH_MARK, False):
            return name
    return None


_loaded_from = _policy_path_loaded()
if _loaded_from is not None:
    raise ImportError(
        f"grader is privileged: already-imported policy-observation path "
        f"{_loaded_from} forbids this import")


def _refuse_policy_caller() -> None:
    for frame in inspect.stack()[1:]:
        mod = inspect.getmodule(frame[0])
        name = mod.__name__ if mod is not None else str(frame[0].f_globals.get("__name__"))
        if name in _DENY or frame[0].f_globals.get(POLICY_PATH_MARK):
            raise ImportError("grader is privileged: refused policy-path caller")


def latent_bit(world_id: str, prop: str) -> bool:
    _refuse_policy_caller()
    blob = f"{GRADER_SEED}|{world_id}|{prop}".encode()
    return bool(hashlib.sha256(blob).digest()[0] & 1)


def current_dep_versions(world: dict) -> dict:
    versions = {p["dep"]: 1 for p in world["props"].values()}
    for event in world["events"]:
        if event["kind"] == "dep-bump" and event["tick"] <= world["ticks"]:
            versions[event["dep"]] = max(versions.get(event["dep"], 1), event["to"])
    return versions


def solve(observations: list, products: dict, world: dict) -> dict:
    current = current_dep_versions(world)
    votes: dict[str, list] = {}
    for obs in observations:
        if not obs.get("scored", True):
            continue
        prop = world["props"].get(obs["prop"])
        if prop is None:
            continue
        if obs.get("dep_version") != current.get(prop["dep"], 1):
            continue
        if obs.get("value") in (True, False):
            votes.setdefault(obs["prop"], []).append(obs["value"])
    for prop, value in (products or {}).items():
        if prop in world["props"] and value in (True, False):
            votes.setdefault(prop, []).append(value)
    answers = {}
    for task in world["tasks"]:
        prop = task["prop"]
        tally = votes.get(prop, [])
        if not tally:
            answers[task["task_id"]] = "unknown"
        elif sum(1 for v in tally if v) > len(tally) / 2:
            answers[task["task_id"]] = True
        elif sum(1 for v in tally if not v) > len(tally) / 2:
            answers[task["task_id"]] = False
        else:
            answers[task["task_id"]] = "unknown"
    return answers


def grade(observations: list, products: dict, world: dict) -> dict:
    _refuse_policy_caller()
    answers = solve(observations, products, world)
    per_task = {}
    correct = 0
    for task in world["tasks"]:
        expected = latent_bit(world["world_id"], task["prop"])
        given = answers[task["task_id"]]
        hit = given is expected
        correct += 1 if hit else 0
        per_task[task["task_id"]] = {"answer": given, "correct": hit}
    return {"correct": correct, "total": len(world["tasks"]),
            "per_task": per_task,
            "eval_cost": len(world["tasks"]) * SOLVER_COST_PER_TASK}


def wrong_answers(world: dict) -> dict:
    _refuse_policy_caller()
    return {t["task_id"]: not latent_bit(world["world_id"], t["prop"])
            for t in world["tasks"]}
