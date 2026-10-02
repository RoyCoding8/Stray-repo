"""P3 rep sweep: checker must bind record inputs/composition to the freeze."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.experiment import checker, freeze

REP = ROOT / "experiments" / "representation"


def _manifest(name="manifest.json"):
    return json.loads((REP / "experiment" / name).read_bytes())


def _sha(name="manifest.json"):
    stem = Path(name).stem
    return (REP / "experiment" / ("%s.sha256" % stem)).read_text().strip()


def _stage(tmp_path, evidence):
    root = tmp_path / "evidence"
    shutil.copytree(REP / evidence / "arm_task", root / "arm_task")
    shutil.copytree(REP / evidence / "controls", root / "controls")
    shutil.copytree(REP / evidence / "use", root / "use")
    return root


def _first(root, arm):
    paths = sorted((root / "arm_task").glob("%s-*.json" % arm))
    assert paths, "no %s records" % arm
    return paths[0]


def _rewrite(path, fn):
    record = json.loads(path.read_bytes())
    fn(record)
    path.write_text(json.dumps(record))


def test_committed_evidence_binds_clean():
    manifest, sha = _manifest(), _sha()
    _, problems = checker.check_evidence(
        REP / "evidence-heldout", manifest, sha)
    assert not [p for p in problems if "drift" in p or "unbound" in p]


def test_historical_evidence_binds_clean():
    manifest, sha = _manifest("manifest_acq1.json"), _sha("manifest_acq1.json")
    _, problems = checker.check_evidence(
        REP / "evidence", manifest, sha)
    assert not [p for p in problems if "drift" in p or "unbound" in p]


def test_tampered_fixture_digest_rejected(tmp_path):
    root = _stage(tmp_path, "evidence-heldout")
    _rewrite(_first(root, "A"),
             lambda r: r["inputs_digest"].update(fixture="0" * 64))
    _, problems = checker.check_evidence(root, _manifest(), _sha())
    assert any(p.startswith("input-drift-fixture") for p in problems)


def test_tampered_context_and_checker_digests_rejected(tmp_path):
    root = _stage(tmp_path, "evidence-heldout")
    _rewrite(_first(root, "A"),
             lambda r: r["inputs_digest"].update(context="0" * 64,
                                                checker="0" * 64))
    _, problems = checker.check_evidence(root, _manifest(), _sha())
    assert any(p.startswith("input-drift-context") for p in problems)
    assert any(p.startswith("input-drift-checker") for p in problems)


def test_tampered_composition_digest_rejected(tmp_path):
    root = _stage(tmp_path, "evidence-heldout")
    _rewrite(_first(root, "C"),
             lambda r: r["composition"].update(core_digest="0" * 64))
    _, problems = checker.check_evidence(root, _manifest(), _sha())
    assert any(p.startswith("composition-drift-core") for p in problems)


def test_unknown_composition_id_rejected(tmp_path):
    root = _stage(tmp_path, "evidence-heldout")
    _rewrite(_first(root, "C"),
             lambda r: r["composition"].update(composition_id="rpr-C-nope-v9"))
    _, problems = checker.check_evidence(root, _manifest(), _sha())
    assert any(p.startswith("unbound-composition-id") for p in problems)


def test_freeze_closures_hold():
    assert freeze.verify_committed() == []
    assert freeze.verify_history("manifest_acq1.json") == []
    heldout = checker.check_all(REP / "evidence-heldout")
    assert heldout["clean"] and heldout["records"] == 48
    history = checker.check_all(REP / "evidence",
                                manifest_name="manifest_acq1.json",
                                historical=True)
    assert history["clean"] and history["records"] == 27
