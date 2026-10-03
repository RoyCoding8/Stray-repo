from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.team01 import checker, panel, template
from settlement.common import SettlementError

PHASES = ("development", "template", "evaluation", "transfer", "disposition")


def _write_status(evidence_root, status: dict) -> Path:
    target = Path(evidence_root) / ("experiment-%s.json" % status["tag"])
    target.write_bytes((json.dumps(status, sort_keys=True, indent=2)
                        + "\n").encode())
    return target


def run_team_panel(dsn: str, *, tag: str, evidence_root, runs_root,
                   phases=PHASES) -> dict:
    for phase in phases:
        if phase not in PHASES:
            raise SettlementError("unknown phase %r" % (phase,))
    wanted = [phase for phase in PHASES if phase in phases]
    status: dict = {"tag": tag, "phases_requested": list(phases),
                    "phases_completed": [], "phase_completed": "none",
                    "template": None, "evaluation": None, "transfer": None,
                    "disposition": None}
    evidence_root = Path(evidence_root)
    frozen = template.load_template(evidence_root)
    if "development" in wanted:
        dev = panel.run_development(dsn, evidence_root=evidence_root,
                                    runs_root=runs_root, tag=tag)
        status["development"] = {"episodes": len(dev),
                                 "probes": sorted({r["probe"] for r in dev})}
        status["phases_completed"].append("development")
        status["phase_completed"] = "development"
    if "template" in wanted:
        dev_records = [json.loads(path.read_bytes()) for path in sorted(
            (evidence_root / "episodes").glob("dev-*.json"))]
        if not dev_records:
            frozen = template.freeze_none(evidence_root,
                                          reason="no development episodes")
        else:
            builds = template.build_candidates(dev_records)
            if not builds:
                frozen = template.freeze_none(
                    evidence_root, reason="no eligible candidate")
            else:
                winner, frozen_out = template.select_candidate(builds,
                                                               dev_records)
                frozen = template.freeze_template(evidence_root,
                                                  winner=winner,
                                                  frozen_out=frozen_out,
                                                  builds=builds)
        status["template"] = {"frozen": frozen["template"],
                              "digest": frozen["digest"]}
        status["phases_completed"].append("template")
        status["phase_completed"] = "template"
    if frozen is not None and frozen.get("template") == "none":
        frozen = None
    if "evaluation" in wanted:
        out = panel.run_comparison(dsn, evidence_root=evidence_root,
                                   runs_root=runs_root, tag=tag,
                                   template=frozen)
        status["evaluation"] = {"episodes": len(out["records"])}
        status["phases_completed"].append("evaluation")
        status["phase_completed"] = "evaluation"
    if "transfer" in wanted:
        out = panel.run_transfer(dsn, evidence_root=evidence_root,
                                 runs_root=runs_root, tag=tag,
                                 template=frozen)
        status["transfer"] = {"episodes": len(out["records"])}
        status["phases_completed"].append("transfer")
        status["phase_completed"] = "transfer"
    if "disposition" in wanted:
        report = checker.check_all(evidence_root, dsn=dsn)
        status["disposition"] = {
            "clean": report["clean"], "records": report["records"],
            "promising": {name: rule["promising"] for name, rule in
                           report["pilot_rule"].items()},
            "reasons": [problem for problem in report["problems"]],
            "release_eligible": False}
        status["phases_completed"].append("disposition")
        status["phase_completed"] = "disposition"
    _write_status(evidence_root, status)
    return status


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Team 01 panel entry")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--phases", default=",".join(PHASES))
    args = parser.parse_args(argv)
    dsn = args.dsn or os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn or not args.tag or not args.evidence_root:
        print("need --dsn (or SETTLEMENT_TEST_DSN), --tag, --evidence-root")
        return 2
    try:
        status = run_team_panel(
            dsn, tag=args.tag, evidence_root=args.evidence_root,
            runs_root=args.runs_root or args.evidence_root,
            phases=tuple(part for part in args.phases.split(",") if part))
    except SettlementError as exc:
        print(json.dumps({"tag": args.tag, "error": str(exc)}))
        return 1
    print(json.dumps(status, sort_keys=True, indent=2))
    return 0 if _disposition_clean(status) else 1


def _disposition_clean(status: dict) -> bool:
    """Whether the panel's own disposition found nothing wrong.

    `checker.check_all` exits 1 on the same `clean` field, so this is the
    entry point agreeing with the checker that owns the verdict. A run
    that asked for no disposition holds no verdict and cannot have
    failed one.
    """
    disposition = status.get("disposition")
    if disposition is None:
        return True
    return bool(disposition.get("clean"))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
