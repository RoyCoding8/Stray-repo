"""The control arm's use phase, in a fresh process, on any arm name.

`experiments.ad01.cli` refuses an `--arm` outside `("I", "R")` at
`cli.py:238`, and that vocabulary is closed in two more places for
campaign ids. The control arm is not a campaign arm — it has no campaign,
it is authored, and it has no rotation to be I or R of — so widening that
vocabulary would have said the control is a third ordering of the same
trajectory, which it is not.

So this runs the same call the CLI's `use` branch runs, in a fresh process
of its own, and the process boundary is preserved on purpose. The child's
member bytes are what execute, and a policy that raises has to be recorded
as a refusal by `run_use` rather than as an exception out of the study;
both of those properties come from being in another process, not from the
CLI being the thing that starts it.

The old `compile_step` compatibility entry point is bounded too, but this
fresh-process caller passes source bytes directly to `run_use` so the policy
operation can be accounted for with the use record.

Written rather than borrowed so that `cli.py` stays untouched by an arm
that does not exist in its vocabulary.
"""
from __future__ import annotations

import json
import sys


def main(argv: list | None = None) -> int:
    import argparse
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    for entry in (str(ROOT), str(ROOT / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    parser = argparse.ArgumentParser(prog="ad01-control-use")
    parser.add_argument("--repertoire", required=True)
    parser.add_argument("--policy-source", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--allocation-id", required=True)
    parser.add_argument("--world", type=int, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--tasks", required=True)
    args = parser.parse_args(argv)

    from experiments.ad01 import trajectory, worlds

    if args.world not in worlds.WORLDS:
        print("unknown --world %r" % args.world, file=sys.stderr)
        return 2
    try:
        repertoire = trajectory.load_repertoire(args.repertoire)
        policy_source = Path(args.policy_source).read_text(encoding="utf-8")
    except Exception as exc:
        print("ad01-control-use refused: %s" % exc, file=sys.stderr)
        return 2
    try:
        records = trajectory.run_use(
            repertoire, args.world, args.arm,
            [task for task in args.tasks.split(",") if task],
            {}, policy_source=policy_source, dsn=args.dsn,
            allocation_id=args.allocation_id)
    except Exception as exc:
        print("ad01-control-use refused: %s" % exc, file=sys.stderr)
        return 2
    json.dump(records, sys.stdout, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
