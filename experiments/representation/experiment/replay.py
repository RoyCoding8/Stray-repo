"""Replay CLI for the Representation Lane D pilot (RPR-04/08).

Committed-input replay in the agenda freeze discipline: ``--mode check``
re-verifies the manifest and runs the strict checker over committed
evidence without touching a database; ``--mode run`` re-executes the full
panel from committed inputs against a real database and re-checks. Both
modes refuse on any manifest problem before doing work.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import run as panel_run
from experiments.representation.experiment import checker, freeze

REP = ROOT / "experiments" / "representation"


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Lane D replay")
    parser.add_argument("--mode", choices=("check", "run"), default="check")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--tag", default="main")
    parser.add_argument("--artifacts-root", default="/tmp/rpr-acq-artifacts")
    parser.add_argument("--staging-root", default="/tmp/rpr-acq-staging")
    parser.add_argument("--runs-root", default="/tmp/rpr-acq-runs")
    parser.add_argument("--evidence-root", default=str(REP / "evidence"))
    args = parser.parse_args(argv)
    import os
    problems = freeze.verify_committed()
    if problems:
        print(json.dumps({"refused": problems}, indent=2))
        return 1
    if args.mode == "check":
        report = checker.check_all(Path(args.evidence_root))
        print(json.dumps({"clean": report["clean"],
                          "problems": report["problems"],
                          "records": report["records"],
                          "pilot_rule": report["pilot_rule"]}, indent=2))
        return 0 if report["clean"] else 1
    dsn = args.dsn or os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        print("no DSN: pass --dsn or set SETTLEMENT_TEST_DSN")
        return 2
    index = panel_run.run_panel(
        dsn, tag=args.tag, artifacts_root=Path(args.artifacts_root),
        staging_root=Path(args.staging_root), runs_root=Path(args.runs_root),
        evidence_root=Path(args.evidence_root))
    report = checker.check_all(Path(args.evidence_root), dsn=dsn)
    print(json.dumps({"pairs": index["pairs"], "clean": report["clean"],
                      "problems": report["problems"],
                      "pilot_rule": report["pilot_rule"]}, indent=2))
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
