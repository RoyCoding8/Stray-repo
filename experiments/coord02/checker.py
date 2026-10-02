from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

from . import freeze as freeze_mod
from . import oracle

COST_FIELDS = ("model_calls", "tool_invocations", "sandbox_ops")


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def candidate_digest_of(tree: Path) -> str:
    tree = Path(tree)
    parts = []
    for path in sorted(tree.rglob("*")):
        if path.is_file():
            parts.append(path.relative_to(tree).as_posix())
            parts.append(_digest(path.read_bytes()))
    return _digest("\n".join(parts).encode())


DEFAULT_COSTS = {"model_tokens": {"in": 100, "out": 20}, "model_calls": 1,
                 "tool_invocations": 2, "sandbox_ops": 5}


def make_record(freeze: dict, evidence_root, *, panel: str, task: str,
                repeat: int, arm: str, kind: str = "valid",
                costs: dict | None = None,
                receipts: list | None = None) -> dict:
    root = Path(evidence_root)
    with tempfile.TemporaryDirectory(prefix="coord02-cand-") as tmp:
        src = oracle.prepare_tree(task, kind, Path(tmp) / "tree")
        digest = candidate_digest_of(Path(tmp) / "tree")
        protected = oracle.evaluate_tree(
            src, oracle.protected_cases(task))
        dest = root / "candidates" / digest
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(Path(tmp) / "tree", dest)
    solved = protected["failed"] == 0
    package = freeze.get("package", {})
    procedure = package.get("digest", "none") if package.get("kind") != "none" \
        else "none"
    pair = "%s-%s-%s-%s-r%d" % (freeze["freeze_id"], panel, arm, task, repeat)
    record = {
        "freeze_id": freeze["freeze_id"], "panel": panel, "task_id": task,
        "repeat": repeat, "arm": arm,
        "procedure_digest": procedure,
        "input_digest": oracle.task_input_digest(task),
        "outcome": "success" if solved else "failure",
        "protected": {"passed": protected["passed"],
                      "failed": protected["failed"],
                      "total": protected["total"]},
        "failures": protected["failures"] if not solved else [],
        "costs": costs or dict(DEFAULT_COSTS),
        "receipts": receipts if receipts is not None
        else ["%s-w%d" % (pair, i) for i in range(2)],
        "candidate_digest": digest, "frozen_digest": digest if solved else "",
    }
    episodes = root / "episodes"
    episodes.mkdir(parents=True, exist_ok=True)
    (episodes / ("%s.json" % pair)).write_text(
        json.dumps(record, indent=2) + "\n")
    return record


def _load_records(evidence_root) -> tuple:
    root = Path(evidence_root) / "episodes"
    records, problems = {}, []
    paths = sorted(root.glob("*.json")) if root.is_dir() else []
    for path in paths:
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-record %s" % path.name)
            continue
        key = (record.get("freeze_id"), record.get("panel"),
               record.get("task_id"), record.get("repeat"),
               record.get("arm"))
        if None in key:
            problems.append("incomplete-identity %s" % path.name)
            continue
        if key in records:
            problems.append("duplicate-pair %s-%s-%s-r%s-%s" % (key[0], key[1],
                                                                key[2], key[3],
                                                                key[4]))
        records[key] = record
    return records, problems


def _check_record(record: dict, where: str, freeze: dict,
                  evidence_root, problems: list) -> None:
    if record.get("panel") not in freeze_mod.PANELS:
        problems.append("unbound-panel %s" % where)
    task = record.get("task_id")
    if task not in oracle.TASK_FAMILY:
        problems.append("unbound-task %s" % where)
    elif task not in freeze["corpus"]["membership"]:
        problems.append("unfrozen-task %s" % where)
    if record.get("arm") not in freeze_mod.ARMS:
        problems.append("unbound-arm %s" % where)
    if record.get("repeat") not in list(freeze_mod.REPEATS):
        problems.append("unbound-repeat %s" % where)
    package = freeze.get("package", {})
    want_proc = package.get("digest", "none") \
        if package.get("kind") != "none" else "none"
    if record.get("procedure_digest") != want_proc:
        problems.append("wrong-procedure-digest %s" % where)
    try:
        want_input = oracle.task_input_digest(task)
    except (OSError, ValueError, KeyError):
        want_input = None
    if want_input is not None and record.get("input_digest") != want_input:
        problems.append("wrong-input-digest %s" % where)
    protected = record.get("protected") or {}
    if not all(isinstance(protected.get(k), int)
               for k in ("passed", "failed", "total")):
        problems.append("incomplete-outcome %s" % where)
    elif protected["passed"] + protected["failed"] != protected["total"]:
        problems.append("outcome-arithmetic %s" % where)
    failures = record.get("failures") or []
    if record.get("outcome") == "failure" and not failures:
        problems.append("unquoted-failure %s" % where)
    if isinstance(protected.get("failed"), int) and \
            len(failures) != (protected["failed"] if record.get("outcome")
                              == "failure" else 0):
        problems.append("failure-quote-mismatch %s" % where)
    if record.get("outcome") == "success":
        if protected.get("failed"):
            problems.append("validity-override %s" % where)
        if not record.get("frozen_digest"):
            problems.append("unfrozen-success %s" % where)
    costs = record.get("costs") or {}
    tokens = costs.get("model_tokens") or {}
    ok_costs = True
    for field in COST_FIELDS:
        if field not in costs or not _num(costs[field]) or costs[field] < 0:
            problems.append("omitted-cost-%s %s" % (field, where))
            ok_costs = False
    for side in ("in", "out"):
        if side not in tokens or not _num(tokens[side]) or tokens[side] < 0:
            problems.append("omitted-cost-model_tokens-%s %s" % (side, where))
            ok_costs = False
    if ok_costs:
        if costs["model_calls"] > freeze["budgets"]["model_calls"]:
            problems.append("ceiling-breach-model_calls %s" % where)
        if tokens["in"] > freeze["budgets"]["input_tokens"]:
            problems.append("ceiling-breach-input_tokens %s" % where)
        if tokens["out"] > freeze["budgets"]["output_tokens"]:
            problems.append("ceiling-breach-output_tokens %s" % where)
        if costs["tool_invocations"] > freeze["budgets"]["tool_invocations"]:
            problems.append("ceiling-breach-tool_invocations %s" % where)
        if costs["sandbox_ops"] > freeze["budgets"]["sandbox_ops"]:
            problems.append("ceiling-breach-sandbox_ops %s" % where)
    receipts = record.get("receipts")
    if not isinstance(receipts, list) or not receipts \
            or not all(isinstance(r, str) and r for r in receipts):
        problems.append("unattributed-cost %s" % where)
    digest = record.get("candidate_digest", "")
    cand = Path(evidence_root) / "candidates" / digest if digest else None
    if record.get("outcome") == "success":
        if not digest or cand is None or not (cand / "src" / "app.py").is_file():
            problems.append("unverifiable-success %s" % where)
        else:
            try:
                rederived = oracle.evaluate_tree(
                    cand / "src", oracle.protected_cases(task))
            except (OSError, ValueError, KeyError) as exc:
                problems.append("rederivation-error %s %s" % (where, exc))
            else:
                if (rederived["failed"] == 0) != \
                        (record.get("outcome") == "success"):
                    problems.append("verdict-mismatch %s" % where)
                if rederived["failed"] != protected.get("failed") or \
                        rederived["passed"] != protected.get("passed"):
                    problems.append("tally-mismatch %s" % where)
            if record.get("frozen_digest") != digest:
                problems.append("freeze-digest-mismatch %s" % where)


def check_evidence(evidence_root, freeze_path, dsn: str = "",
                   receipt_table: str = "",
                   panels=("evaluation", "transfer")) -> dict:
    freeze_path = Path(freeze_path)
    problems = list(freeze_mod.verify_freeze(freeze_path))
    try:
        freeze = json.loads(freeze_path.read_bytes())
    except (OSError, ValueError):
        return {"problems": problems, "clean": False, "records": 0,
                "summary": {}}
    records, more = _load_records(evidence_root)
    problems.extend(more)
    seen_inputs: dict = {}
    seen_receipts: dict = {}
    for key, record in records.items():
        where = "%s-%s-%s-r%s-%s" % key
        _check_record(record, where, freeze, evidence_root, problems)
        group = (key[0], key[1], key[2])
        seen_inputs.setdefault(group, set()).add(record.get("input_digest"))
        for ref in record.get("receipts") or []:
            if ref in seen_receipts:
                problems.append("receipt-reuse %s first-seen %s" % (
                    where, seen_receipts[ref]))
            else:
                seen_receipts[ref] = where
    for group, digests in seen_inputs.items():
        if len(digests) > 1:
            problems.append("cross-arm-input-divergence %s-%s-%s" % group)
    by_pair: dict = {}
    for key in records:
        short = (key[0], key[2], key[3], key[4])
        by_pair.setdefault(short, set()).add(key[1])
    for short, panels in by_pair.items():
        if len(panels) > 1:
            problems.append("cross-panel-collision %s-%s-r%s-%s" % short)
    present = {key[1] for key in records}
    for panel in panels:
        expected = freeze_mod.expected_pairs(freeze["schedule"], panel,
                                             freeze["freeze_id"])
        have = {key for key in records if key[1] == panel}
        for key in sorted(expected - have):
            problems.append("missing-pair %s-%s-%s-r%s-%s" % key)
        for key in sorted(have - expected):
            problems.append("unbound-record %s-%s-%s-r%s-%s" % key)
    for panel in sorted(present - set(panels)):
        problems.append("unbound-panel-evidence %s" % panel)
    if dsn and receipt_table:
        try:
            problems.extend(_cross_check_receipts(dsn, receipt_table,
                                                  records))
        except Exception as exc:
            problems.append("db-cross-check-failed %s" % exc)
    return {"problems": sorted(set(problems)),
            "clean": not problems, "records": len(records),
            "summary": summarize(records)}


def _cross_check_receipts(dsn: str, table: str, records: dict) -> list:
    from settlement import db

    problems = []
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT receipt_identity FROM %s" % table)
            anchored = {row[0] for row in cur.fetchall()}
            conn.commit()
    for key, record in records.items():
        where = "%s-%s-%s-r%s-%s" % key
        for ref in record.get("receipts") or []:
            if ref not in anchored:
                problems.append("altered-receipt %s %s" % (where, ref))
    return problems


def summarize(records: dict) -> dict:
    summary = {}
    for key, record in records.items():
        _, panel, task, _, arm = key
        cell = summary.setdefault("%s/%s" % (panel, arm),
                                  {"solved": 0, "total": 0, "by_family": {}})
        solved = record.get("outcome") == "success" \
            and (record.get("protected") or {}).get("failed") == 0 \
            and bool(record.get("frozen_digest"))
        cell["total"] += 1
        cell["solved"] += 1 if solved else 0
        fam = oracle.TASK_FAMILY.get(task, "?")
        fam_cell = cell["by_family"].setdefault(fam, {"solved": 0,
                                                      "total": 0})
        fam_cell["total"] += 1
        fam_cell["solved"] += 1 if solved else 0
    return summary


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="coord02 offline checker")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--dsn", default="")
    parser.add_argument("--receipt-table", default="")
    parser.add_argument("--panels", nargs="+",
                        default=["evaluation", "transfer"])
    args = parser.parse_args(argv)
    report = check_evidence(args.evidence_root, args.freeze,
                            dsn=args.dsn,
                            receipt_table=args.receipt_table,
                            panels=tuple(args.panels))
    print(json.dumps({"clean": report["clean"],
                      "problems": report["problems"],
                      "records": report["records"],
                      "summary": report["summary"]}, indent=2))
    return 0 if report["clean"] else 1
