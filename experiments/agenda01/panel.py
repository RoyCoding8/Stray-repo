"""AG01-EXP full-panel driver: run every trajectory, check strict acceptance.

run    executes all manifest worlds x arms x ties (default 128 trajectories),
       each on an isolated database, and records panel.json with every
       incomplete or failed run. Traces land in --out-dir.
check  runs strict full-panel acceptance over a trace directory and writes
       the checker report.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import sys
import traceback
from pathlib import Path


def _job(base_dsn: str, world: dict, arm: str, tie: int, manifest_doc: dict,
         manifest_hash: str, out_dir: str, keep_dbs: bool) -> dict:
    from . import runner
    record = {"world_id": world["world_id"], "arm": arm, "tie": tie,
              "traj_id": None, "complete": False, "end_reason": None,
              "grade": None, "error": None}
    try:
        trace = runner.run_trajectory(
            base_dsn, world, arm, tie, runner.resolve_policy(arm),
            manifest_doc["policy_versions"][arm], manifest_doc, manifest_hash,
            out_dir, keep_db=keep_dbs)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"
        return record
    record["traj_id"] = trace.get("traj_id")
    record["complete"] = bool(trace.get("complete"))
    record["end_reason"] = trace.get("end_reason")
    record["grade"] = trace.get("grade")
    return record


def cmd_run(args) -> int:
    from . import manifest
    try:
        manifest_doc, digest = manifest.load_verified(
            args.manifest, args.manifest_hash_file,
            run_unverified=args.run_unverified)
    except (ValueError, OSError) as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 1
    jobs = [(w, arm, tie) for w in manifest_doc["worlds"]
            for arm in args.arms for tie in args.ties
            if not args.only or w["world_id"] in args.only]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_job, args.base_dsn, world, arm, tie,
                               manifest_doc, digest, str(out_dir), args.keep_dbs)
                   for world, arm, tie in jobs]
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            runs.append(record)
            status = ("ok" if record["complete"] else
                      f"INCOMPLETE {record['end_reason']} {record['error'] or ''}")
            print(f"[panel] {record['world_id']} {record['arm']} t{record['tie']}:"
                  f" {status}", flush=True)
    runs.sort(key=lambda r: (r["world_id"], r["arm"], r["tie"]))
    panel = {"experiment": manifest_doc["experiment"],
             "manifest_sha256": digest,
             "source_revision": manifest_doc["source_revision"],
             "policy_versions": manifest_doc["policy_versions"],
             "started": started,
             "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "runs": runs,
             "incomplete": [r for r in runs if not r["complete"]]}
    (out_dir / "panel.json").write_text(json.dumps(panel, indent=2, sort_keys=True))
    print(f"[panel] {len(runs) - len(panel['incomplete'])}/{len(runs)} complete:"
          f" {out_dir / 'panel.json'}")
    return 0 if not panel["incomplete"] else 1


def cmd_check(args) -> int:
    from . import checker, manifest
    try:
        manifest_doc, digest = manifest.load_verified(
            args.manifest, args.manifest_hash_file,
            run_unverified=args.subset and args.run_unverified)
    except (ValueError, OSError) as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 1
    report = checker.check_dir(args.trace_dir, manifest_doc, digest,
                               manifest_doc["budgets"], expect_full=not args.subset)
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({"ok": report["ok"], "traces": report["traces"],
                      "pairs": len(report["pairs"]),
                      "violations": report["violations"]},
                     indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-dsn", required=True)
    run.add_argument("--out-dir", required=True)
    run.add_argument("--manifest", required=True)
    run.add_argument("--manifest-hash-file", required=True)
    run.add_argument("--run-unverified", action="store_true")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--arms", nargs="+", default=["R", "Q"])
    run.add_argument("--ties", nargs="*", type=int, default=[0, 1])
    run.add_argument("--only", nargs="*", default=[])
    run.add_argument("--keep-dbs", action="store_true")
    check = sub.add_parser("check")
    check.add_argument("--trace-dir", required=True)
    check.add_argument("--report", required=True)
    check.add_argument("--manifest", required=True)
    check.add_argument("--manifest-hash-file", required=True)
    check.add_argument("--run-unverified", action="store_true")
    check.add_argument("--subset", action="store_true")
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "check":
        return cmd_check(args)
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
