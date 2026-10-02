"""Independent checker for AD01 use records (§§5-7).

Reproduces world membership, freeze identity, and quality from the frozen
tasks plus the independent witness checkers. Rejects altered, missing and
duplicate records, wrong freeze references, inconsistent measures, and
unknown measurements scored as numeric zero. Explicit ``"unknown"``
markers are accepted and reported as unevaluable, never silently zeroed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.representation import checkers, graphs, software

from . import worlds

ARMS = ("I", "R")
USE_KINDS = ("within", "transfer")
VERDICTS = ("preserved", "not_preserved", "invalid", "unknown")
COST_KEYS = ("tokens", "witness_queries", "sandbox_ops")
UNKNOWN = "unknown"


def freeze_digest(root) -> str:
    raw = (Path(root) / "manifest.json").read_bytes()
    return hashlib.sha256(raw).hexdigest()


def _check(task: dict, candidate: dict) -> dict:
    if task["family"] == "software":
        return checkers.check_software(task, candidate)
    return checkers.check_graph(task, candidate)


def _measure(task: dict, candidate: dict) -> int:
    if task["family"] == "software":
        return software.measure(candidate["ops"])
    return graphs.measure(candidate)


def _expected_cells(root) -> set:
    membership = worlds.world_membership(root)
    cells = set()
    for world, kinds in membership.items():
        for arm in ARMS:
            for kind in USE_KINDS:
                for domain, task_ids in kinds[kind].items():
                    for task_id in task_ids:
                        cells.add((int(world), arm, task_id))
    return cells


def verify_use_records(records: list, root) -> dict:
    problems: list = []
    unevaluable: list = []
    seen: set = {}
    for record in records:
        key = (record.get("world"), record.get("arm"),
               record.get("task_id"))
        if key in seen:
            problems.append("duplicate-record %s" % (key,))
            continue
        seen[key] = record
        problems.extend(_verify_record(record, root, unevaluable))
    for cell in sorted(_expected_cells(root) - set(seen)):
        problems.append("missing-record world=%s arm=%s task=%s" % cell)
    return {"problems": problems, "unevaluable": unevaluable}


def _verify_record(record: dict, root, unevaluable: list) -> list:
    problems = []
    rid = record.get("record_id", "?")
    if record.get("freeze") != worlds.FREEZE_ID:
        problems.append("wrong-freeze-reference %s" % rid)
        return problems
    if record.get("freeze_digest") != freeze_digest(root):
        problems.append("wrong-freeze-reference %s" % rid)
        return problems
    try:
        task = worlds.load_task(root, record["task_id"])
    except KeyError:
        problems.append("membership-unknown-task %s" % rid)
        return problems
    membership = worlds.world_membership(root)
    world = str(record.get("world"))
    kinds = membership.get(world, {})
    members = {t for kind in USE_KINDS for domain_tasks in
               kinds.get(kind, {}).values() for t in domain_tasks}
    if record["task_id"] not in members:
        problems.append("membership-not-use %s" % rid)
        return problems
    family = record.get("domain")
    if family not in ("software", "graph"):
        problems.append("domain-mismatch %s" % rid)
        return problems
    if task["family"] != family:
        problems.append("domain-mismatch %s" % rid)
        return problems
    if record.get("verdict") not in VERDICTS:
        problems.append("bad-verdict %s" % rid)
        return problems
    return problems + _verify_quality(record, task, unevaluable)


def _verify_quality(record: dict, task: dict, unevaluable: list) -> list:
    problems = []
    rid = record.get("record_id", "?")
    initial, final = record.get("initial_measure"), record.get("final_measure")
    if record["verdict"] == UNKNOWN:
        if not (initial == UNKNOWN or final == UNKNOWN):
            problems.append("unknown-scored-as-zero %s" % rid)
            return problems
        if record.get("normalized_reduction") != 0.0:
            problems.append("unknown-scored-nonzero %s" % rid)
            return problems
        unevaluable.append("unknown-measure %s" % rid)
        return problems + _verify_costs(record, unevaluable)
    for name, value in (("initial", initial), ("final", final)):
        if value == UNKNOWN:
            problems.append("unknown-measure-preserved %s" % rid)
            return problems
        if not isinstance(value, int) or value < 1:
            problems.append("degenerate-%s-measure %s" % (name, rid))
            return problems
    output = record.get("output")
    if not isinstance(output, dict):
        problems.append("missing-output %s" % rid)
        return problems
    try:
        report = _check(task, output)
    except Exception:
        problems.append("checker-failure %s" % rid)
        return problems
    if report["verdict"] != record["verdict"]:
        problems.append("quality-mismatch %s recomputed=%s" %
                        (rid, report["verdict"]))
        return problems
    if _measure(task, output) != final:
        problems.append("measure-mismatch %s" % rid)
        return problems
    if record["verdict"] == "preserved":
        want = (initial - final) / initial
    else:
        want = 0.0
    if abs(record.get("normalized_reduction", -1) - want) > 1e-9:
        problems.append("reduction-mismatch %s" % rid)
    return problems + _verify_costs(record, unevaluable)


def _verify_costs(record: dict, unevaluable: list) -> list:
    problems = []
    rid = record.get("record_id", "?")
    costs = record.get("costs", {})
    for key in COST_KEYS:
        value = costs.get(key)
        if value == UNKNOWN:
            unevaluable.append("unknown-cost %s %s" % (rid, key))
        elif not isinstance(value, int) or value < 0:
            problems.append("bad-cost %s %s" % (rid, key))
    return problems
