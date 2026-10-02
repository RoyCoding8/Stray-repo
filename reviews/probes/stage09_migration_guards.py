"""Bounded, DB-free checks of the current stage 9 migration seams."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "experiments")]

from experiments.ad01 import trajectory, worlds


def main():
    target = next(p.stem for p in sorted(worlds.FROZEN_DIR.rglob("*.json"))
                  if "w0-transfer-sw" in p.stem)
    proposal = {"unknown": "Does this preserve the witness?", "basis_references": [],
                "next_action": {"kind": "diagnostic", "diagnostic": "software", "task_id": target},
                "requested_resources": {"queries": 1}}
    boundary, charter = {"world": 0, "arm": "I", "seq": 0}, {"objective": "investigate"}
    admitted = trajectory.admit_investigation(proposal, {"observations": []}, charter, boundary)
    with patch.object(trajectory, "run_diagnostic", side_effect=AssertionError("protected effect executed")):
        _, episode, spend = trajectory._run_boundary(
            "ad01-w0-dev-sw-00", "seed-sw-greedy", {"diagnostic_queries": 16},
            {"observation_id": "obs-audit", "task_id": "ad01-w0-dev-sw-00", "verdict": "unmeasured"},
            charter=charter, boundary=boundary, experience={"observations": []}, accepted=proposal)
    assert admitted["decision"] == "admitted"
    assert "protected-use target" in episode["fallback_reason"] and spend == 0
    members = [{"capability_id": name, "scope": {"family": "software"}} for name in ("old", "revision")]
    forward = trajectory._select_member({"members": members}, {"family": "software"})["capability_id"]
    reverse = trajectory._select_member({"members": members[::-1]}, {"family": "software"})["capability_id"]
    assert (forward, reverse) == ("old", "revision")
    print(json.dumps({"implementation": "1d90c2e", "admission": admitted["decision"],
                      "public_effect_disposition": episode, "spend": spend,
                      "selection_forward": forward, "selection_reversed": reverse,
                      "scope": "Real pure admission and target guard; diagnostic replaced by a must-not-run sentinel. Pure member selection. No DB or provider effects."}, indent=2))


if __name__ == "__main__":
    main()
