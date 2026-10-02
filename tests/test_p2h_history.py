"""P2 historical/live verification split (Lane D)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.experiment import checker, freeze

REP = ROOT / "experiments" / "representation"
EXPERIMENT = REP / "experiment"
ACQ1_SHA = (EXPERIMENT / "manifest_acq1.sha256").read_text().strip()


def test_historical_freeze_verifies_without_live_tree():
    assert freeze.verify_history("manifest_acq1.json") == []
    assert freeze.verify_history() == []


def test_live_freeze_still_regenerates():
    assert freeze.verify_committed() == []


def test_historical_mechanics_is_checker_clean():
    report = checker.check_all(REP / "evidence",
                               manifest_name="manifest_acq1.json",
                               historical=True)
    assert report["clean"], report["problems"]
    assert report["records"] == 27


def test_live_mode_still_flags_tree_drift_on_history():
    report = checker.check_all(REP / "evidence",
                               manifest_name="manifest_acq1.json")
    assert not report["clean"]
    assert any(p.startswith("digest-mismatch") for p in report["problems"])


def _copied_evidence(tmp_path: Path) -> Path:
    dest = tmp_path / "evidence"
    shutil.copytree(REP / "evidence", dest)
    return dest


def test_historical_tampered_pin_breaks_check(tmp_path):
    root = _copied_evidence(tmp_path)
    pristine = checker.check_all(root, manifest_name="manifest_acq1.json",
                                 historical=True)
    assert pristine["clean"], pristine["problems"]
    target = sorted((root / "arm_task").glob("*.json"))[0]
    record = json.loads(target.read_bytes())
    record["manifest_sha256"] = "0" * 64
    target.write_text(json.dumps(record))
    report = checker.check_all(root, manifest_name="manifest_acq1.json",
                               historical=True)
    assert not report["clean"]
    assert any(p.startswith("manifest-drift") for p in report["problems"])


def test_historical_tampered_record_breaks_check(tmp_path):
    root = _copied_evidence(tmp_path)
    target = sorted((root / "arm_task").glob("*.json"))[0]
    record = json.loads(target.read_bytes())
    record["result"]["improvement_u"] = 0.123456
    target.write_text(json.dumps(record))
    report = checker.check_all(root, manifest_name="manifest_acq1.json",
                               historical=True)
    assert not report["clean"]
    assert any(p.startswith("improvement-mismatch")
               for p in report["problems"])


def test_historical_records_pin_acq1_sha():
    for path in sorted((REP / "evidence" / "arm_task").glob("*.json")):
        record = json.loads(path.read_bytes())
        assert record["manifest_sha256"] == ACQ1_SHA, path.name
