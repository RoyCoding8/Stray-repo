"""AG01-EXP panel replay CLI: resume interrupted trajectories, prove equivalence.

Commands:
  run     execute one trajectory fresh or resumed; a resumed run continues
          the same database in this process, so invoking run --resume from a
          new process is a fresh-process resume.
  verify  prove a resumed trace carries the same effect/cost sequence as an
          uninterrupted control trace.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

COMPARE_KEYS = ("traj_id", "world_id", "family", "variant", "arm", "tie",
                "policy_version", "manifest_sha256", "backend", "rng_seed",
                "end_reason", "complete", "ticks", "observations", "products",
                "pending_drained", "drained_products", "option_spend",
                "totals", "grade")

LEDGER_KEYS = ("ops", "reservations", "allocations", "receipts", "links",
               "decisions", "outcomes", "conflicts", "cursor")


def compare_traces(control: dict, candidate: dict) -> list:
    diffs = []
    for key in COMPARE_KEYS:
        if control.get(key) != candidate.get(key):
            diffs.append(f"trace-field-diverged {key}")
    ledger_a, ledger_b = control.get("ledger") or {}, candidate.get("ledger") or {}
    for key in LEDGER_KEYS:
        if ledger_a.get(key) != ledger_b.get(key):
            diffs.append(f"ledger-diverged {key}")
    return diffs


def cmd_run(args) -> int:
    from . import manifest, runner
    try:
        manifest_doc, digest = manifest.load_verified(
            args.manifest, args.manifest_hash_file,
            run_unverified=args.run_unverified)
    except (ValueError, OSError) as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 1
    world = next(w for w in manifest_doc["worlds"] if w["world_id"] == args.world)
    policy_fn = runner.resolve_policy(args.arm)
    policy_version = manifest_doc["policy_versions"][args.arm]
    try:
        trace = runner.run_trajectory(
            args.base_dsn, world, args.arm, args.tie, policy_fn, policy_version,
            manifest_doc, digest, args.out_dir, keep_db=args.keep_db,
            max_ticks=args.max_ticks, resume=args.resume)
    except Exception as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"traj_id": trace.get("traj_id"),
                      "complete": trace.get("complete"),
                      "end_reason": trace.get("end_reason"),
                      "grade": trace.get("grade")}, sort_keys=True))
    return 0 if trace.get("complete") or args.max_ticks is not None else 1


def cmd_verify(args) -> int:
    control = json.loads(Path(args.control).read_text())
    candidate = json.loads(Path(args.candidate).read_text())
    diffs = compare_traces(control, candidate)
    print(json.dumps({"ok": not diffs, "diffs": diffs}, indent=2, sort_keys=True))
    return 0 if not diffs else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-dsn", required=True)
    run.add_argument("--world", required=True)
    run.add_argument("--arm", required=True, choices=("R", "Q"))
    run.add_argument("--tie", type=int, default=0)
    run.add_argument("--manifest", required=True)
    run.add_argument("--manifest-hash-file", required=True)
    run.add_argument("--run-unverified", action="store_true")
    run.add_argument("--out-dir", required=True)
    run.add_argument("--max-ticks", type=int, default=None)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--keep-db", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--control", required=True)
    verify.add_argument("--candidate", required=True)
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
