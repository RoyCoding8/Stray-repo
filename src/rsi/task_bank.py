"""Import and sanity-check a frozen Exercism bank without calling a model.

Run with ``python -m rsi.task_bank --help``. Keep the artifact/run roots outside
agent workspaces; the complete task packages include hidden verifier/reference bytes.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher

from . import task, verifier


def import_bank(dsn: str, source: Path, root: Path, *, sanity: bool = True,
                timeout_ms: int = 30000) -> dict:
    tasks = task.from_exercism(source)
    roots = {"staging_root": root / "stage", "artifacts_root": root / "art"}
    for item in tasks:
        task.publish(dsn, item, **roots)
    index = [{"name": t.name, "digest": t.digest, "split": t.split,
              "evaluator_version": t.evaluator_version} for t in tasks]
    raw = json.dumps(index, sort_keys=True, separators=(",", ":")).encode()
    manifest = {"kind": "rsi-bank", "files": task.file_manifest({"index.json": raw})}
    receipt = artifacts.stage_package(dsn, roots["staging_root"], manifest=manifest,
                                      files={"index.json": raw}, scope="rsi-bank",
                                      access_label="evaluator", format="rsi-bank")
    result = artifacts.publish_package(dsn, Command(
        request_id=f"rsi-bank-{receipt['digest']}", payload={"digest": receipt["digest"]}),
        roots["artifacts_root"], receipt)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    bank = receipt["digest"]
    report = {"bank": bank, "tasks": len(tasks), "splits": dict(Counter(t.split for t in tasks)),
              "sanity": [], "model_calls": 0, "sanity_passed": None}
    if sanity:
        allocation = f"rsi-bank-cpu-{bank}"
        payload = {"profile": "local-process", "argv": ["python"], "timeout_ms": timeout_ms}
        exposure, _ = broker.exposure_schedule(broker.SANDBOX_EXEC, payload)
        result = store.seed_allocation(dsn, Command(
            request_id=allocation, payload={"allocation_id": allocation, "domain": "cpu",
                                           "authorized": 2 * len(tasks) * exposure}))
        if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise SettlementError(result.detail)
        launcher = LocalLauncher(root / "verifiers")
        for item in tasks:
            row = {"name": item.name, "task": item.digest, "split": item.split}
            for role, files in (("reference", item.reference), ("stub", item.workspace)):
                operation = "rsi-sanity-" + hashlib.sha256(
                    f"{bank}:{item.digest}:{role}".encode()).hexdigest()
                checked = verifier.check(dsn, launcher, item, files,
                                         operation_id=operation, allocation_id=allocation,
                                         attempt_id=None, timeout_ms=timeout_ms, **roots)
                row[role] = {"status": checked.status, "passed": checked.passed,
                             "operation_id": operation, "solution": checked.solution}
            report["sanity"].append(row)
            print(f"{item.name}: reference={row['reference']['status']} stub={row['stub']['status']}",
                  flush=True)
        report["sanity_passed"] = all(r["reference"]["passed"] is True
                                         and r["stub"]["passed"] is False
                                         for r in report["sanity"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "bank-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Exercism practice directory")
    parser.add_argument("--root", type=Path, required=True, help="Kernel-owned artifacts and run root")
    parser.add_argument("--dsn", required=True, help="PostgreSQL database route")
    parser.add_argument("--migrations", type=Path, help="Apply migrations from this directory first")
    parser.add_argument("--skip-sanity", action="store_true", help="Import only; does not qualify a bank")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()
    if args.migrations:
        db.apply_migrations(args.dsn, args.migrations)
    report = import_bank(args.dsn, args.source, args.root.resolve(),
                         sanity=not args.skip_sanity, timeout_ms=args.timeout_ms)
    print(json.dumps({k: v for k, v in report.items() if k != "sanity"}, indent=2))
    raise SystemExit(1 if report["sanity_passed"] is False else 0)


if __name__ == "__main__":
    main()
