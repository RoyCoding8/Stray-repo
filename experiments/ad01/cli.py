"""AD01 trajectory public entry for fresh processes.

One-shot invocations (no poll loop): ``run`` advances a campaign through
the public entry and publishes settled boundaries; ``resume`` reconciles
the durable record first and continues the same campaign without
duplicate spend.
"""

from __future__ import annotations

import argparse
import json
import sys

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}


def _tasks(value: str | None) -> list | None:
    if not value:
        return None
    return [t for t in value.split(",") if t]


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ad01-traj")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dsn", required=True)
    run.add_argument("--world", type=int, required=True)
    run.add_argument("--arm", required=True)
    run.add_argument("--seq", type=int, default=0)
    run.add_argument("--max-boundaries", type=int, default=6)
    run.add_argument("--tasks", default="")
    resume = sub.add_parser("resume")
    resume.add_argument("--dsn", required=True)
    resume.add_argument("--campaign", required=True)
    resume.add_argument("--max-boundaries", type=int, default=6)
    resume.add_argument("--tasks", default="")
    args = parser.parse_args(argv)
    caps = dict(CAPS, max_boundaries=args.max_boundaries)
    from . import trajectory
    if args.command == "run":
        out = trajectory.run_campaign(
            args.world, args.arm, CHARTER, caps, tasks=_tasks(args.tasks),
            campaign_seq=args.seq, dsn=args.dsn)
    else:
        out = trajectory.resume_campaign(
            args.dsn, args.campaign, CHARTER, caps,
            tasks=_tasks(args.tasks))
    json.dump(out, sys.stdout, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
