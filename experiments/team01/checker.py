from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.team01 import barrier, freeze, oracle
from experiments.team01 import panel as panel_mod

TEAM01 = ROOT / "experiments" / "team01"
RATIO = 1.25
DEV_PROBES = ("template-use", "diagnostic", "incompatible",
              "template-validation", "continuity", "substitution",
              "disconnect")
# Panels renamed across campaigns: the live2 vertical path wrote "dev"
# calibration under its own panel name; read it as dev evidence without
# rewriting committed records.
PANEL_ALIAS = {"live2-repair": "dev"}
DEV_ARMS = ("S", "P", "T", "cold-T", "warm-T")


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_manifest() -> tuple:
    try:
        raw = (TEAM01 / "manifest.json").read_bytes()
    except OSError:
        return None, "", ["missing-manifest"]
    try:
        pinned = (TEAM01 / "manifest.sha256").read_text().strip()
    except OSError:
        return None, "", ["missing-manifest-hash"]
    if _digest(raw) != pinned:
        return None, "", ["manifest-hash-mismatch"]
    problems = list(freeze.verify_committed())
    return json.loads(raw), pinned, problems


def _expected(panel_name: str) -> set:
    if panel_name == "eval":
        return {(panel_name, arm, task, rep) for arm in panel_mod.ARMS
                for task in oracle.SPLITS["evaluation"]
                for rep in panel_mod.REPEATS}
    if panel_name == "transfer":
        return {(panel_name, arm, task, rep)
                for arm in panel_mod.TRANSFER_MODES
                for task in oracle.SPLITS["transfer"]
                for rep in panel_mod.REPEATS}
    if panel_name == "dev":
        # Development calibration: every dev task through the scored
        # arms. Diagnostic probes are schema-checked extras, not cells.
        return {(panel_name, arm, task, None)
                for arm in panel_mod.ARMS
                for task in oracle.SPLITS["development"]}
    return set()


def _quote(failure: dict) -> str:
    return "input=%s expected=%s got=%s error=%s" % (
        json.dumps(failure.get("input"), sort_keys=True),
        json.dumps(failure.get("expected"), sort_keys=True),
        json.dumps(failure.get("got"), sort_keys=True),
        json.dumps(failure.get("error", "")))


def check_evidence(evidence_root, manifest, manifest_sha: str) -> tuple:
    problems: list = []
    records: dict = {}
    root = Path(evidence_root) / "episodes"
    paths = sorted(root.glob("*.json")) if root.is_dir() else []
    for path in paths:
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-record %s" % path.name)
            continue
        panel = PANEL_ALIAS.get(record.get("panel"), record.get("panel"))
        rep = record.get("repeat") if panel != "dev" \
            else record.get("probe")
        key = (panel, record.get("arm"), record.get("task_id"), rep)
        if key in records:
            problems.append("duplicate-record %s" % path.name)
        records[key] = record
    present = {key[0] for key in records}
    if not ({"eval", "transfer"} & present):
        problems.append("missing-panel-evidence eval+transfer")
    expected: set = set()
    for name in present:
        cells = _expected(name)
        if not cells:
            problems.append("unbound-panel %s" % name)
            continue
        expected |= cells
    extras: set = set()
    for key in sorted(set(records) - expected):
        panel, arm, task, rep = key
        if panel == "dev" and rep in DEV_PROBES and arm in DEV_ARMS:
            extras.add(key)
            continue
        problems.append("unbound-record %s-%s-%s-%s" % key)
    for key in sorted(set(records) & expected):
        _check_record(records[key], key, manifest_sha, problems)
    for key in sorted(extras):
        _check_record(records[key], key, manifest_sha, problems)
    return records, problems


def _check_record(record: dict, key: tuple, manifest_sha: str,
                  problems: list) -> None:
    where = "%s-%s-%s-%s" % key
    for field in ("outcome", "plan_id", "manifest_sha256", "receipts"):
        if not record.get(field):
            problems.append("incomplete-%s %s" % (field, where))
    if record.get("manifest_sha256") != manifest_sha:
        problems.append("manifest-drift %s" % where)
    for block in ("public", "protected"):
        result = record.get(block) or {}
        if not isinstance(result.get("passed"), int) \
                or not isinstance(result.get("failed"), int):
            problems.append("incomplete-outcome-%s %s" % (block, where))
    join = record.get("join") or {}
    # Suspend/resume probe records carry no join block by design (their
    # verification is the phase1 suspension plus the phase2 resume); the
    # join checks below do not apply to them.
    if record.get("probe") != "continuity":
        if not join.get("join_receipt") or not join.get("check_operation"):
            problems.append("unbound-join-receipt %s" % where)
        if not isinstance(join.get("passed"), bool):
            problems.append("incomplete-join-verdict %s" % where)
    costs = record.get("costs") or {}
    tokens = costs.get("model_tokens") or {}
    for field in ("tool_executions", "model_invocations"):
        if field not in costs or not _num(costs[field]) or costs[field] < 0:
            problems.append("omitted-cost-%s %s" % (field, where))
    for side in ("in", "out"):
        if side not in tokens or not _num(tokens[side]) or tokens[side] < 0:
            problems.append("omitted-cost-model_tokens-%s %s" % (side, where))
    protected = record.get("protected") or {}
    failures = protected.get("failures") or []
    if record.get("outcome") == "failure" and not failures:
        problems.append("unquoted-failure %s" % where)
    if record.get("outcome") == "success":
        if protected.get("failed"):
            problems.append("validity-override %s: success with %d"
                            " protected failures" % (where,
                                                     protected["failed"]))
        if not record.get("frozen_digest"):
            problems.append("unfrozen-success %s" % where)


def failure_quotes(records: dict) -> list:
    quotes = []
    # Keys mix dev cells (probe rep, possibly None) with eval/transfer
    # cells (integer reps); sort by repr so a multi-panel evidence root
    # does not raise TypeError.
    for key in sorted(records, key=repr):
        record = records[key]
        if record.get("outcome") != "failure":
            continue
        where = "%s-%s-%s-%s" % key
        for failure in (record.get("protected") or {}).get("failures") or []:
            quotes.append("episode-failed %s: %s" % (where, _quote(failure)))
    return quotes


def check_controls(problems: list) -> dict:
    summary = {}
    try:
        outcome = oracle.selftest()
    except Exception as exc:
        problems.append("oracle-selftest-error %s" % exc)
        return {"oracle": False, "barrier": False}
    bad = [fam for fam, entry in outcome.items()
           if entry["valid"]["failed"] != 0
           or entry["invalid"]["failed"] == 0]
    for fam in bad:
        problems.append("control-failed oracle-%s valid=%s invalid=%s" % (
            fam, outcome[fam]["valid"], outcome[fam]["invalid"]))
    summary["oracle"] = not bad
    barrier_problems = barrier.audit_barrier()
    for item in barrier_problems:
        problems.append("barrier-breach %s" % item)
    summary["barrier"] = not barrier_problems
    return summary


def _solved(record: dict) -> bool | None:
    protected = record.get("protected") or {}
    if record.get("outcome") == "success":
        return protected.get("failed") == 0 and bool(record.get("frozen_digest"))
    if record.get("outcome") == "failure":
        return False
    return None


def _tokens(record: dict):
    tokens = (record.get("costs") or {}).get("model_tokens") or {}
    if not _num(tokens.get("in")) or not _num(tokens.get("out")) \
            or tokens["in"] < 0 or tokens["out"] < 0:
        return None
    return tokens["in"] + tokens["out"]


def _tools(record: dict):
    value = (record.get("costs") or {}).get("tool_executions")
    return value if _num(value) and value >= 0 else None


def _within(value, base) -> bool:
    if base == 0:
        return value == 0
    return value <= RATIO * base


def finite_panel_rule(records: dict, controls: dict,
                      panel_name: str = "eval") -> dict:
    cells = {key: record for key, record in records.items()
             if key[0] == panel_name}
    if panel_name == "eval":
        focus, comparators = "T", ["S", "P"]
    else:
        focus, comparators = "warm-T", ["cold-T", "S"]
    ceilings = (freeze.CEILINGS if isinstance(freeze.CEILINGS, dict) else {})
    clauses: dict = {}
    clauses["complete-records"] = bool(cells) and all(
        _solved(record) is not None for record in cells.values())
    clauses["controls-pass"] = bool(controls) and all(controls.values())
    clauses["ceilings-hold"] = bool(cells) and all(
        (record.get("costs") or {}).get("model_invocations", 0)
        <= ceilings.get("model_invocations", 8)
        and ((record.get("costs") or {}).get("model_tokens") or {})
        .get("in", 0) <= ceilings.get("input_tokens", 96000)
        and ((record.get("costs") or {}).get("model_tokens") or {})
        .get("out", 0) <= ceilings.get("output_tokens", 24000)
        and (record.get("costs") or {}).get("tool_executions", 0)
        <= ceilings.get("tool_executions", 16)
        for record in cells.values())
    vectors: dict = {}
    families: dict = {}
    for comparator in comparators:
        mine = {key[2:]: record for key, record in cells.items()
                if key[1] == focus}
        theirs = {key[2:]: record for key, record in cells.items()
                  if key[1] == comparator}
        paired = set(mine) & set(theirs)
        whole = {(key[2], key[3]) for key in cells if key[1] in (focus,
                                                                comparator)}
        clauses["paired-%s" % comparator] = bool(paired) and paired == whole
        my_solves = sum(1 for r in mine.values() if _solved(r) is True)
        their_solves = sum(1 for r in theirs.values() if _solved(r) is True)
        my_tokens = [_tokens(r) for r in mine.values()]
        their_tokens = [_tokens(r) for r in theirs.values()]
        my_tools = [_tools(r) for r in mine.values()]
        their_tools = [_tools(r) for r in theirs.values()]
        unknown = any(v is None for v in my_tokens + their_tokens + my_tools
                      + their_tools)
        vectors[comparator] = {"focus_solves": my_solves,
                               "comparator_solves": their_solves,
                               "focus_tokens": sum(v for v in my_tokens
                                                   if v is not None),
                               "comparator_tokens": sum(v for v in their_tokens
                                                        if v is not None),
                               "focus_tools": sum(v for v in my_tools
                                                  if v is not None),
                               "comparator_tools": sum(v for v in their_tools
                                                       if v is not None),
                               "unknown": unknown}
        if unknown or not clauses["paired-%s" % comparator]:
            clauses["beats-%s" % comparator] = False
            continue
        row = vectors[comparator]
        ahead = my_solves > their_solves and _within(
            row["focus_tokens"], row["comparator_tokens"]) and _within(
            row["focus_tools"], row["comparator_tools"])
        level = my_solves == their_solves and row["focus_tokens"] <= row[
            "comparator_tokens"] and row["focus_tools"] <= row[
            "comparator_tools"] and row["focus_tokens"] < row[
            "comparator_tokens"]
        clauses["beats-%s" % comparator] = ahead or level
        cap = 0 if panel_name == "transfer" else 1
        fam_losses = {}
        for cell in paired:
            fam = mine[cell].get("family", "")
            lost = _solved(theirs[cell]) is True and _solved(mine[cell]) is not True
            fam_losses[fam] = fam_losses.get(fam, 0) + (1 if lost else 0)
        families[comparator] = fam_losses
        clauses["family-cap-%s" % comparator] = all(
            lost <= cap for lost in fam_losses.values())
    promising = all(clauses.values())
    reasons = [name for name, held in clauses.items() if not held]
    return {"panel": panel_name, "focus": focus,
            "comparators": comparators, "clauses": clauses,
            "vectors": vectors, "families": families, "reasons": reasons,
            "promising": promising, "release_eligible": False,
            "release_note": "a promising pilot warrants a broader frozen"
                            " trial; it does not authorize a general"
                            " team-capability release"}


def _receipt_identity_exists(dsn: str, identity: str) -> bool:
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM receipts WHERE receipt_identity = %s",
                        (identity,))
            row = cur.fetchone()
            conn.commit()
            return row is not None


def replay_panel(dsn: str, evidence_root) -> dict:
    from settlement import store, team
    root = Path(evidence_root) / "episodes"
    paths = sorted(root.glob("*.json")) if root.is_dir() else []
    records = [json.loads(path.read_bytes()) for path in paths]
    mismatches: list = []
    seen: set = set()
    for record in records:
        if record.get("probe") == "continuity":
            # Suspend/resume probe records are not repair episodes: they
            # carry no join block by design, so there is nothing to rebound.
            continue
        key = (record.get("panel"), record.get("arm"), record.get("task_id"),
               record.get("repeat"))
        seen.add(key)
        where = "%s-%s-%s-%s" % key
        try:
            plan = team.plan_summary(dsn, record.get("plan_id", ""))
        except LookupError:
            mismatches.append("unbound-plan %s: no such plan %r" % (
                where, record.get("plan_id")))
            continue
        rev = record.get("revision", 1)
        if rev is None:
            # Refused episodes never reached a join revision; record the
            # gap as a mismatch instead of crashing on int(None).
            mismatches.append("unbound-revision %s" % where)
            continue
        try:
            join = team.join_record(dsn, record["plan_id"], int(rev))
        except LookupError:
            mismatches.append("unbound-join %s" % where)
            continue
        join_rec = record.get("join") or {}
        if join.get("candidate_digest") != join_rec.get(
                "candidate_digest"):
            mismatches.append("rebound-artifact %s: record %r != join %r" % (
                where, join_rec.get("candidate_digest"),
                join.get("candidate_digest")))
        if bool(join.get("passed")) != bool(join_rec.get("passed")):
            mismatches.append("rebound-verdict %s" % where)
        if record.get("frozen_digest") and record["frozen_digest"] != join.get(
                "candidate_digest"):
            mismatches.append("rebound-freeze %s" % where)
        if not record.get("frozen_digest") and join.get("passed"):
            mismatches.append("unfrozen-pass %s" % where)
        for node in team.child_nodes(dsn, record["plan_id"]):
            try:
                team.submission_tuple(dsn, record["plan_id"],
                                      int(record.get("revision", 1)), node)
            except LookupError:
                mismatches.append("unbound-submission %s %s" % (where, node))
        listed = record.get("receipts") or {}
        if isinstance(listed, dict):
            pairs = [("%s:r%s:%s:work" % (
                record["plan_id"], int(rev), node), refs)
                for node, refs in listed.items()]
            for op_id, refs in pairs:
                have = {r["receipt_identity"]
                        for r in store.operation_receipts(dsn, op_id)}
                for ref in refs:
                    if ref not in have:
                        mismatches.append("effect-without-receipt %s %s" % (
                            where, ref))
        else:
            # Live solver records carry a flat list of receipt
            # identities; each must exist in the receipts table.
            for ref in listed:
                if not _receipt_identity_exists(dsn, ref):
                    mismatches.append("effect-without-receipt %s %s" % (
                        where, ref))
        check_op = (record.get("join") or {}).get("check_operation", "")
        if check_op and not store.operation_receipts(dsn, check_op):
            mismatches.append("effect-without-receipt %s %s" % (where,
                                                                check_op))
        protected = record.get("protected") or {}
        solved = protected.get("failed") == 0 and bool(record.get(
            "frozen_digest"))
        if (record.get("outcome") == "success") != solved and record.get(
                "outcome") in ("success", "failure"):
            mismatches.append("hidden-answer-selection %s: outcome %r"
                              " disagrees with frozen protected evidence"
                              % (where, record.get("outcome")))
    present = {(record.get("panel"), record.get("task_id"),
                record.get("repeat")) for record in records}
    for panel_name, task, rep in sorted(present, key=repr):
        if panel_name == "dev":
            continue
        arms = panel_mod.ARMS if panel_name == "eval" \
            else panel_mod.TRANSFER_MODES
        for arm in arms:
            if (panel_name, arm, task, rep) not in seen:
                mismatches.append("missing-pair %s-%s-%s-r%s" % (
                    panel_name, arm, task, rep))
    return {"replayed": len(records), "mismatches": sorted(set(mismatches))}


def operator_view(dsn: str, evidence_root) -> dict:
    from settlement import team
    root = Path(evidence_root) / "episodes"
    paths = sorted(root.glob("*.json")) if root.is_dir() else []
    records = [json.loads(path.read_bytes()) for path in paths]
    graph, pending, selected, joins = [], [], {}, []
    costs: dict = {}
    for record in records:
        try:
            nodes = team.child_nodes(dsn, record.get("plan_id", ""))
        except LookupError:
            nodes = []
        graph.append({"episode_id": record.get("episode_id"),
                      "plan_id": record.get("plan_id"),
                      "shape": record.get("shape"), "children": nodes,
                      "frozen": bool(record.get("frozen_digest"))})
        if record.get("outcome") != "success":
            pending.append(record.get("episode_id"))
        selected[record.get("episode_id")] = record.get("frozen_digest")
        joins.append({"episode_id": record.get("episode_id"),
                      "passed": record["join"].get("passed"),
                      "join_receipt": record["join"].get("join_receipt"),
                      "candidate_digest": record["join"].get(
                          "candidate_digest")})
        cell = costs.setdefault(record.get("arm", ""), {"tokens": 0,
                                                        "tools": 0,
                                                        "calls": 0})
        tokens = (record.get("costs") or {}).get("model_tokens") or {}
        cell["tokens"] += tokens.get("in", 0) + tokens.get("out", 0)
        cell["tools"] += (record.get("costs") or {}).get("tool_executions", 0)
        cell["calls"] += (record.get("costs") or {}).get("model_invocations",
                                                         0)
    return {"graph": graph, "pending": pending, "selected": selected,
            "joins": joins, "costs": costs}


def check_all(evidence_root, dsn: str = "") -> dict:
    manifest, sha, problems = load_manifest()
    records: dict = {}
    controls: dict = {}
    rules: dict = {}
    if manifest is not None:
        records, more = check_evidence(evidence_root, manifest, sha)
        problems.extend(more)
        controls = check_controls(problems)
        for name in ("eval", "transfer"):
            if any(key[0] == name for key in records):
                rules[name] = finite_panel_rule(records, controls, name)
        if dsn:
            try:
                replayed = replay_panel(dsn, evidence_root)
                for item in replayed["mismatches"]:
                    problems.append("replay-%s" % item)
            except Exception as exc:
                problems.append("db-cross-check-failed %s" % exc)
    return {"problems": problems, "clean": not problems,
            "records": len(records), "controls": controls,
            "failure_quotes": failure_quotes(records),
            "pilot_rule": rules}


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Team 01 evidence checker")
    parser.add_argument("--evidence-root", default=str(TEAM01 / "evidence"))
    parser.add_argument("--dsn", default="")
    parser.add_argument("--panel", default="")
    args = parser.parse_args(argv)
    report = check_all(Path(args.evidence_root), dsn=args.dsn)
    if args.panel and args.panel not in report["pilot_rule"]:
        print(json.dumps({"clean": False, "problems": report["problems"] + [
            "missing-panel %s" % args.panel]}))
        return 1
    print(json.dumps({"clean": report["clean"],
                      "problems": report["problems"],
                      "records": report["records"],
                      "controls": report["controls"],
                      "pilot_rule": {name: {"promising": rule["promising"],
                                            "reasons": rule["reasons"]}
                                     for name, rule in
                                     report["pilot_rule"].items()}},
                     sort_keys=True, indent=2))
    return 0 if report["clean"] else 1
