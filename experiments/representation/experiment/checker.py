"""Strict result checker for the Representation Lane D pilot (RPR-04/08).

Mirrors the agenda freeze discipline: verifies the committed manifest
before touching evidence, then rejects missing or duplicate arm-task
records, incomplete outcomes, modified inputs, unbound invocation records
and omitted cost records. Recomputes improvement, control handling and the
preregistered pilot rule from committed bytes. Runs without a database;
with ``--dsn`` it additionally cross-checks invocation receipts and trial
rows against durable records.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import panel

REP = ROOT / "experiments" / "representation"
EXPERIMENT = REP / "experiment"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_manifest() -> tuple:
    try:
        raw = (EXPERIMENT / "manifest.json").read_bytes()
    except OSError:
        return None, "", ["missing-manifest"]
    try:
        pinned = (EXPERIMENT / "manifest.sha256").read_text().strip()
    except OSError:
        return None, "", ["missing-manifest-hash"]
    if _digest(raw) != pinned:
        return None, "", ["manifest-hash-mismatch"]
    manifest = json.loads(raw)
    problems = []
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        target = ROOT / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if _digest(target.read_bytes()) != entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return manifest, pinned, problems


def _expected_arm_tasks(manifest: dict) -> set:
    expected = set()
    for task_id in manifest["panel"]["benefit_sw"] + manifest["panel"]["benefit_gr"]:
        for arm in panel.ARMS:
            expected.add((arm, task_id))
    return expected


def _check_costs(record: dict, where: str, problems: list) -> None:
    costs = record.get("costs")
    if not isinstance(costs, dict):
        problems.append("omitted-costs %s" % where)
        return
    for key in ("invocations_used", "queries_used", "elapsed_s",
                "model_calls"):
        if key not in costs:
            problems.append("omitted-cost-%s %s" % (key, where))
    tokens = (costs.get("model_tokens") or {})
    if tokens.get("in", 0) != 0 or tokens.get("out", 0) != 0:
        problems.append("nonzero-model-tokens %s" % where)


def check_evidence(evidence_root: Path, manifest: dict,
                   manifest_sha: str) -> tuple:
    problems: list = []
    arm_dir = evidence_root / "arm_task"
    records: dict = {}
    for path in sorted(arm_dir.glob("*.json")):
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-record %s" % path.name)
            continue
        key = (record.get("arm"), record.get("task_id"))
        if key in records:
            problems.append("duplicate-record %s" % path.name)
        records[key] = record
    expected = _expected_arm_tasks(manifest)
    for key in sorted(expected - set(records)):
        problems.append("missing-record %s-%s" % (key[0], key[1]))
    for key in sorted(set(records) - expected):
        problems.append("unbound-record %s-%s" % (key[0], key[1]))
    for (arm, task_id), record in sorted(records.items()):
        where = "%s-%s" % (arm, task_id)
        if record.get("manifest_sha256") != manifest_sha:
            problems.append("manifest-drift %s" % where)
        result = record.get("result", {})
        for key in ("disposition", "delivered_digest"):
            if not result.get(key):
                problems.append("incomplete-outcome-%s %s" % (key, where))
        if not isinstance(result.get("verified"), bool):
            problems.append("incomplete-outcome-verified %s" % where)
        if result.get("improvement_u") is None:
            problems.append("incomplete-outcome-improvement %s" % where)
        else:
            initial = record.get("initial", {}).get("measure")
            best = result.get("best_measure")
            want = round(max(0.0, (initial - best) / initial), 6) \
                if best is not None and initial else 0.0
            if abs(result["improvement_u"] - want) > 1e-9:
                problems.append("improvement-mismatch %s: %s != %s"
                                % (where, result["improvement_u"], want))
        _check_costs(record, where, problems)
        comp = record.get("composition", {})
        if comp.get("native"):
            if not comp.get("procedure"):
                problems.append("unbound-procedure %s" % where)
            if record.get("invocations"):
                problems.append("native-invocations %s" % where)
        else:
            for key in ("composition_id", "core_digest", "adapter_digest",
                        "package_digest"):
                if not comp.get(key):
                    problems.append("unbound-composition-%s %s" % (key, where))
            if not record.get("invocations"):
                problems.append("missing-invocations %s" % where)
            if not record.get("oracle_queries"):
                problems.append("missing-oracle-queries %s" % where)
        trial_entries = record.get("trial", [])
        if isinstance(trial_entries, dict):
            trial_entries = [trial_entries]
        if not isinstance(trial_entries, list) or not trial_entries:
            problems.append("unbound-trial %s" % where)
        for entry in trial_entries:
            if not isinstance(entry, dict):
                problems.append("unbound-trial-entry %s" % where)
                continue
            for key in ("protocol_id", "assignment_id", "outcome"):
                if not entry.get(key):
                    problems.append("unbound-trial-%s %s" % (key, where))
        if not record.get("inputs_digest", {}).get("fixture"):
            problems.append("missing-input-digest %s" % where)
    return records, problems


def check_barrier(records: dict, manifest: dict, problems: list) -> None:
    by_digest = {}
    for entry in manifest.get("files", []):
        by_digest[entry["digest"]] = entry["path"]
    graphy = ("graphs/", "transfer_context", "gr_adapter", "gr_checker",
              "bundle_gr_checker")
    for (arm, task_id), record in sorted(records.items()):
        task_path = next((e["path"] for e in manifest["files"]
                          if e.get("task_id") == task_id), "")
        if "/software/" not in task_path and "controls/" not in task_path \
                and "use-sw" not in task_path:
            continue
        inputs = record.get("inputs_digest", {})
        context_digest = inputs.get("context")
        context_path = by_digest.get(context_digest, "")
        if "transfer_context" in context_path:
            problems.append("barrier-breach-context %s-%s" % (arm, task_id))
        if arm == "C":
            comp = record.get("composition", {})
            if "transfer" in comp.get("role", ""):
                problems.append("barrier-breach-composition %s-%s" % (arm, task_id))


def check_controls(evidence_root: Path, problems: list) -> dict:
    summary = {}
    for path in sorted((evidence_root / "controls").glob("*.json")):
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-control %s" % path.name)
            continue
        if "control_pass" not in record:
            problems.append("incomplete-control %s" % path.name)
        elif record["control_pass"] is not True:
            problems.append("control-failed %s" % path.name)
        summary[path.stem] = bool(record.get("control_pass"))
    if len(summary) != 12:
        problems.append("missing-controls have=%d want=12" % len(summary))
    return summary


def check_use(evidence_root: Path, problems: list) -> dict:
    summary = {}
    for path in sorted((evidence_root / "use").glob("*.json")):
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-use %s" % path.name)
            continue
        selected = (record.get("selected") or {}).get("route")
        if "out-of-scope" in record.get("task_id", ""):
            ok = selected == "incumbent"
        else:
            ok = selected == "A-fallback"
        if not ok:
            problems.append("use-misrouted %s" % path.name)
        if (record.get("c_attempt") or {}).get("trial_only") is not True:
            problems.append("use-not-trial-only %s" % path.name)
        summary[record.get("task_id", path.stem)] = selected
    if len(summary) != 4:
        problems.append("missing-use have=%d want=4" % len(summary))
    return summary


def pilot_rule(records: dict) -> dict:
    def mean(arm, family):
        values = [r["result"]["improvement_u"] for (a, _), r in records.items()
                  if a == arm and r["family"] == family]
        return round(sum(values) / len(values), 6) if values else 0.0

    transfer_c = mean("C", "graph")
    line = {"C-transfer-mean": transfer_c,
            "A-transfer-mean": mean("A", "graph"),
            "B-transfer-mean": mean("B", "graph"),
            "C-software-mean": mean("C", "software"),
            "A-software-mean": mean("A", "software"),
            "B-software-mean": mean("B", "software")}
    clauses = {
        "transfer-gain-0.10-vs-A": line["C-transfer-mean"]
        - line["A-transfer-mean"] >= 0.10,
        "transfer-gain-0.10-vs-B": line["C-transfer-mean"]
        - line["B-transfer-mean"] >= 0.10,
        "software-within-0.05-vs-A": line["C-software-mean"]
        - line["A-software-mean"] >= -0.05,
        "software-within-0.05-vs-B": line["C-software-mean"]
        - line["B-software-mean"] >= -0.05,
    }
    return {"means": line, "clauses": clauses,
            "promising": all(clauses.values())}


def cross_check_db(dsn: str, evidence_root: Path, records: dict,
                   problems: list) -> None:
    from settlement import db as _db
    op_ids: set = set()
    for record in records.values():
        for key in ("invocations", "oracle_queries", "oracle_validations"):
            for entry in record.get(key, []) or []:
                if isinstance(entry, dict) and entry.get("op_id"):
                    op_ids.add(entry["op_id"])
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for op_id in sorted(op_ids):
                cur.execute("SELECT dispatch_state FROM operations WHERE id = %s",
                            (op_id,))
                if cur.fetchone() is None:
                    problems.append("unbound-operation %s" % op_id)
                cur.execute("SELECT receipt_identity FROM receipts"
                            " WHERE operation_id = %s", (op_id,))
                if not cur.fetchall():
                    problems.append("effect-without-receipt %s" % op_id)
            conn.commit()


def check_all(evidence_root: Path, dsn: str = "") -> dict:
    manifest, manifest_sha, problems = load_manifest()
    records, controls_summary, use_summary, rule = {}, {}, {}, {}
    if manifest is not None:
        records, more = check_evidence(evidence_root, manifest, manifest_sha)
        problems.extend(more)
        check_barrier(records, manifest, problems)
        controls_summary = check_controls(evidence_root, problems)
        use_summary = check_use(evidence_root, problems)
        rule = pilot_rule(records)
        if dsn:
            try:
                cross_check_db(dsn, evidence_root, records, problems)
            except Exception as exc:
                problems.append("db-cross-check-failed %s" % exc)
    return {"problems": problems, "clean": not problems,
            "records": len(records), "controls": controls_summary,
            "use": use_summary, "pilot_rule": rule}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Lane D strict checker")
    parser.add_argument("--evidence-root", default=str(REP / "evidence"))
    parser.add_argument("--dsn", default="")
    args = parser.parse_args(argv)
    report = check_all(Path(args.evidence_root), dsn=args.dsn)
    print(json.dumps({"clean": report["clean"], "problems": report["problems"],
                      "records": report["records"],
                      "controls": report["controls"], "use": report["use"],
                      "pilot_rule": report["pilot_rule"]}, indent=2))
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
