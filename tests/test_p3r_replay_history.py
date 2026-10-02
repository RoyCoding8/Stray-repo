"""P3 rep sweep: replay CLI must honor the live/history freeze split."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.experiment import replay

REP = ROOT / "experiments" / "representation"


def test_historical_flag_routes_on_filename():
    assert replay._historical("manifest_acq1.json") is True
    assert replay._historical("manifest.json") is False
    assert replay._historical(str(REP / "experiment" / "manifest_acq1.json")) is True


def test_replay_check_live_heldout():
    rc = replay.main(["--mode", "check",
                      "--evidence-root", str(REP / "evidence-heldout")])
    assert rc == 0


def test_replay_check_historical_evidence():
    rc = replay.main(["--mode", "check",
                      "--manifest-file", "manifest_acq1.json",
                      "--evidence-root", str(REP / "evidence")])
    assert rc == 0


def test_replay_check_unknown_manifest_refuses():
    rc = replay.main(["--mode", "check",
                      "--manifest-file", "manifest_nope.json",
                      "--evidence-root", str(REP / "evidence-heldout")])
    assert rc == 1
