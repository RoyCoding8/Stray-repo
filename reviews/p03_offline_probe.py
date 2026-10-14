from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from experiments.context03 import driver, recompute
from isolation_db import disposable_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("fixture", "audit"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    if args.command == "fixture":
        if manifest_path.exists():
            raise SystemExit("Review fixture already exists.")
        repository = Path(driver.__file__).resolve().parents[2]
        manifest = {"matrix": [list(pair) for pair in driver.MATRIX],
                    "model_alias": "fixture:p03-context03/1",
                    "source_sha256": {**driver._source_digests(repository),
                        "experiments/context03/driver.py": hashlib.sha256(
                            Path(driver.__file__).read_bytes()).hexdigest(),
                        "experiments/context03/recompute.py": hashlib.sha256(
                            Path(recompute.__file__).read_bytes()).hexdigest()}}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        for policy, condition in driver.MATRIX:
            with disposable_db("solp03", admin_dsn=os.environ["SETTLEMENT_TEST_DSN"]) as database:
                options = SimpleNamespace(
                    dsn=database.dsn, run_root=root / "runs", evidence_root=root / "evidence",
                    policy=policy, condition=condition, mode="fixture",
                    route_envfile=None, codex_cmd=None)
                path = driver.run_cell(options)
                print(f"fixture {policy} {condition} {path}", flush=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = [json.loads((root / "evidence" / driver.Cell(*pair).id / "cell.json").read_text(
        encoding="utf-8")) for pair in driver.MATRIX]
    baseline = recompute.recompute(manifest, records)
    assert baseline["matrix_cells"] == 9
    assert baseline["dispatched_workers"] == 6
    assert baseline["source_removal_refusals"] == 3
    assert baseline["structured_complete_baseline_pass"] is True
    (root / "baseline-result.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    findings = {}
    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["source_sha256"]["src/rsi/context.py"] = "0" * 64
    try:
        recompute.recompute(changed_manifest, records)
    except ValueError as exc:
        findings["prospective_source_mismatch"] = {"rejected": True, "reason": str(exc)}
    else:
        findings["prospective_source_mismatch"] = {"rejected": False}
    altered = copy.deepcopy(records)
    altered[0]["state"]["last_observation"]["passed"] = False
    try:
        result = recompute.recompute(manifest, altered)
    except ValueError as exc:
        findings["outcome_disagrees_with_observation"] = {"rejected": True, "reason": str(exc)}
    else:
        findings["outcome_disagrees_with_observation"] = {
            "rejected": False, "verified_quality_rate": result["verified_quality_rate"],
            "baseline_quality_rate": baseline["verified_quality_rate"]}
    erased_state = copy.deepcopy(records)
    erased_state[0]["state"].pop("last_observation")
    try:
        result = recompute.recompute(manifest, erased_state)
    except ValueError as exc:
        findings["completed_observation_erased_from_state"] = {"rejected": True, "reason": str(exc)}
    else:
        findings["completed_observation_erased_from_state"] = {
            "rejected": False, "structured_complete_baseline_pass":
            result["structured_complete_baseline_pass"], "cell_passed": result["cells"][0]["passed"]}
    missing_verdict = copy.deepcopy(records)
    missing_verdict[0]["state"]["last_observation"].pop("verdict")
    missing_verdict[0]["attempt_observations"][0]["content"].pop("verdict")
    try:
        result = recompute.recompute(manifest, missing_verdict)
    except ValueError as exc:
        findings["boolean_grade_without_verdict"] = {"rejected": True, "reason": str(exc)}
    else:
        findings["boolean_grade_without_verdict"] = {
            "rejected": False, "verified_quality_rate": result["verified_quality_rate"]}
    disconnected = copy.deepcopy(records)
    invocation = disconnected[0]["invocation"]
    continuation = invocation["continuation"]
    stripped = {key: value for key, value in continuation.items() if key != "context_packet"}
    canonical = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False,
                 "allow_nan": False}
    instruction = invocation["instruction"].replace(
        json.dumps(continuation, **canonical), json.dumps(stripped, **canonical))
    invocation.update(instruction=instruction, instruction_bytes=len(instruction.encode("utf-8")),
                      instruction_sha256=hashlib.sha256(instruction.encode("utf-8")).hexdigest())
    try:
        recompute.recompute(manifest, disconnected)
    except ValueError as exc:
        findings["actual_instruction_disconnection"] = {"rejected": True, "reason": str(exc)}
    else:
        findings["actual_instruction_disconnection"] = {"rejected": False}
    changed_packet = copy.deepcopy(records)
    changed_packet[0]["context_packet"]["memory_view"]["observations"].clear()
    try:
        recompute.recompute(manifest, changed_packet)
    except ValueError as exc:
        findings["packet_source_mutation"] = {"rejected": True, "reason": str(exc)}
    else:
        findings["packet_source_mutation"] = {"rejected": False}
    unknown = copy.deepcopy(records)
    worker_id = unknown[0]["invocation"]["operation_id"]
    operation = next(item for item in unknown[0]["operations"] if item["id"] == worker_id)
    for receipt in operation["receipts"]:
        receipt["tokens"] = None
    unknown[0]["invocation"]["receipts"] = operation["receipts"]
    result = recompute.recompute(manifest, unknown)
    assert result["recorded_token_total"] is None
    assert result["unknown_usage_operations"] == [worker_id]
    findings["unknown_worker_usage"] = {"preserved": True}
    unrelated_costs = copy.deepcopy(records)
    for record in unrelated_costs:
        for operation in record["operations"]:
            for receipt in operation["receipts"]:
                receipt["actual_cost"] = 3000
        if record["invocation"]:
            worker = next(item for item in record["operations"]
                          if item["id"] == record["invocation"]["operation_id"])
            record["invocation"]["receipts"] = worker["receipts"]
    result = recompute.recompute(manifest, unrelated_costs)
    assert result["recorded_token_total"] == 5160
    assert "total_actual_cost" not in result
    findings["worker_tokens_exclude_unrelated_costs"] = {"preserved": True}
    (root / "probe-results.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(json.dumps(findings, indent=2), flush=True)
    if not all(item.get("rejected", True) for item in findings.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
