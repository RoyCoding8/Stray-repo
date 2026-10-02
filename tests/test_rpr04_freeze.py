"""RPR-04 freeze discipline and strict checker (Lane D)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import splits
from experiments.representation.acquire import panel
from experiments.representation.experiment import checker, freeze

EXPERIMENT = ROOT / "experiments" / "representation" / "experiment"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _manifest():
    return json.loads((EXPERIMENT / "manifest.json").read_bytes())


def test_freeze_verifies_clean():
    assert freeze.verify_committed() == []


def test_manifest_matches_panel():
    manifest = _manifest()
    assert manifest["version"] == panel.PANEL_VERSION
    assert manifest["checker_version"] == panel.CHECKER_VERSION
    assert manifest["panel"]["benefit_sw"] == panel.BENEFIT_SW
    assert manifest["panel"]["benefit_gr"] == panel.BENEFIT_GR
    assert manifest["panel"]["controls"] == panel.CONTROLS
    assert manifest["panel"]["use"] == panel.USE
    assert manifest["budgets"] == panel.BUDGETS
    assert manifest["protocols"] == [panel.PROTOCOL_B, panel.PROTOCOL_C]
    assert {c["composition_id"] for c in manifest["compositions"]} == \
        {c["composition_id"] for c in freeze.COMPOSITIONS}


def test_bundles_regenerate_byte_identical():
    for family, stem in (("software", "sw"), ("graph", "gr")):
        raw = freeze.build_checker_bundle(family)
        committed = (EXPERIMENT / ("bundle_%s_checker.py" % stem)).read_bytes()
        assert _digest(raw) == _digest(committed)


def test_bundle_agrees_with_lane_b_oracle(tmp_path):
    from experiments.representation import checkers
    entry = {"software": EXPERIMENT / "bundle_sw_checker.py",
             "graph": EXPERIMENT / "bundle_gr_checker.py"}
    tasks = [splits.generate_software("development", 0),
             splits.generate_graph("development", 0)]
    for task in tasks:
        fam = task["family"]
        doc = {"task_id": task["task_id"], "source_task": task, "aux": {},
               "candidate": task, "role": "initial"}
        cand = tmp_path / "cand.json"
        verd = tmp_path / "verd.json"
        cand.write_text(json.dumps(doc))
        proc = subprocess.run([sys.executable, str(entry[fam]), str(cand),
                               str(verd)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        via = json.loads(verd.read_text())
        direct = (checkers.check_software if fam == "software"
                  else checkers.check_graph)(task, task)
        assert via == {"verdict": direct["verdict"],
                       "measure": direct["measure"],
                       "reason": direct["reason"]}


def _record(arm="A", task_id="sw-dev-00", manifest_sha="s" * 64):
    return {"arm": arm, "task_id": task_id, "family": "software",
            "stage": "mechanics", "manifest_sha256": manifest_sha,
            "checker_version": panel.CHECKER_VERSION,
            "inputs_digest": {"context": "c", "fixture": "f"},
            "composition": {"native": True, "procedure": "greedy"},
            "initial": {"measure": 10},
            "result": {"disposition": "improved", "reason": "locally-irreducible",
                       "best_measure": 3, "improvement_u": 0.7,
                       "verified": True, "delivered_digest": "d"},
            "oracle_queries": [{"verdict": "preserved", "measure": 3,
                                "reason": "ok-preserved"}],
            "invocations": [],
            "costs": {"invocations_used": 0, "queries_used": 9,
                      "validation_used": 0, "elapsed_s": 0.01,
                      "model_calls": 0, "model_tokens": {"in": 0, "out": 0}},
            "trial": [{"protocol_id": "p", "assignment_id": "a",
                       "outcome": "success", "invocation_ref": ""}]}


def _evidence_dir(tmp_path, manifest_sha, records):
    root = tmp_path / "evidence"
    (root / "arm_task").mkdir(parents=True)
    (root / "controls").mkdir()
    (root / "use").mkdir()
    for (arm, task_id), record in records.items():
        (root / "arm_task" / ("%s-%s.json" % (arm, task_id))).write_text(
            json.dumps(record))
    return root


def _full_panel_records(manifest_sha):
    manifest = _manifest()
    records = {}
    for task_id in manifest["panel"]["benefit_sw"] + manifest["panel"]["benefit_gr"]:
        for arm in panel.ARMS:
            record = _record(arm, task_id, manifest_sha)
            if arm == "C":
                record["composition"] = {"native": False,
                                         "composition_id": "c",
                                         "core_digest": "k",
                                         "adapter_digest": "a",
                                         "package_digest": "p",
                                         "checker_id": "rpr-sw-checker/1"}
                record["invocations"] = [{"op_id": "op-%s-%s" % (arm, task_id),
                                          "action": "encode", "seq": 0}]
            records[(arm, task_id)] = record
    return records


def _write_controls_use(root, manifest_sha):
    from experiments.representation.acquire import run as panel_run
    manifest = _manifest()
    for task_id in manifest["panel"]["controls"]:
        for arm in panel.ARMS:
            task, _ = panel_run.load_task(task_id)
            incumbent, _ = panel_run.incumbent_of(task)
            record = {"arm": arm, "task_id": task_id,
                      "family": task["family"], "stage": "control",
                      "manifest_sha256": manifest_sha,
                      "control_pass": True,
                      "result": {"delivered_digest": _digest(
                          panel_run._canon(incumbent))},
                      "oracle_queries": [{"verdict": "not_preserved"}],
                      "invocations": [],
                      "costs": {"invocations_used": 0, "queries_used": 1,
                                "validation_used": 0, "elapsed_s": 0.01,
                                "model_calls": 0,
                                "model_tokens": {"in": 0, "out": 0}}}
            (root / "controls" / ("%s-%s.json" % (arm, task_id))).write_text(
                json.dumps(record))
    for task_id in manifest["panel"]["use"]:
        route = "incumbent" if "out-of-scope" in task_id else "A-fallback"
        record = {"task_id": task_id, "selected": {"route": route},
                  "c_attempt": {"trial_only": True}}
        (root / "use" / ("%s.json" % task_id)).write_text(json.dumps(record))


def test_checker_rejects_missing_record(tmp_path):
    manifest = _manifest()
    manifest_sha = (EXPERIMENT / "manifest.sha256").read_text().strip()
    records = _full_panel_records(manifest_sha)
    records.pop(("C", manifest["panel"]["benefit_sw"][0]))
    root = _evidence_dir(tmp_path, manifest_sha, records)
    _write_controls_use(root, manifest_sha)
    _, problems = checker.check_evidence(root, manifest, manifest_sha)
    assert any(p.startswith("missing-record") for p in problems)


def test_checker_rejects_unbound_and_mismatch(tmp_path):
    manifest = _manifest()
    manifest_sha = (EXPERIMENT / "manifest.sha256").read_text().strip()
    records = _full_panel_records(manifest_sha)
    records[("Z", "no-such-task")] = _record("Z", "no-such-task", manifest_sha)
    key = ("A", manifest["panel"]["benefit_sw"][0])
    records[key]["result"]["improvement_u"] = 0.123
    del records[key]["costs"]["queries_used"]
    records[("B", manifest["panel"]["benefit_gr"][0])]["trial"] = []
    root = _evidence_dir(tmp_path, manifest_sha, records)
    _write_controls_use(root, manifest_sha)
    _, problems = checker.check_evidence(root, manifest, manifest_sha)
    joined = "\n".join(problems)
    assert "unbound-record" in joined
    assert "improvement-mismatch" in joined
    assert "omitted-cost-queries_used" in joined
    assert "unbound-trial" in joined


def test_checker_rejects_manifest_drift(tmp_path):
    manifest = _manifest()
    manifest_sha = (EXPERIMENT / "manifest.sha256").read_text().strip()
    records = _full_panel_records("0" * 64)
    root = _evidence_dir(tmp_path, "0" * 64, records)
    _write_controls_use(root, "0" * 64)
    _, problems = checker.check_evidence(root, manifest, manifest_sha)
    assert any(p.startswith("manifest-drift") for p in problems)


def test_pilot_rule_honest_negative():
    manifest_sha = (EXPERIMENT / "manifest.sha256").read_text().strip()
    records = {}
    for task_id in (panel.BENEFIT_SW + panel.BENEFIT_GR):
        family = "software" if task_id.startswith("sw") else "graph"
        for arm, u in (("A", 0.7), ("B", 0.7), ("C", 0.2)):
            record = _record(arm, task_id, manifest_sha)
            record["family"] = family
            record["result"]["improvement_u"] = u
            record["result"]["best_measure"] = 3
            record["initial"]["measure"] = 10
            records[(arm, task_id)] = record
    rule = checker.pilot_rule(records)
    assert rule["promising"] is False
    assert rule["clauses"]["transfer-gain-0.10-vs-A"] is False


def test_both_freezes_verify_independently():
    from experiments.representation.experiment import freeze
    assert freeze.verify_committed() == []
    assert freeze.verify_history("manifest_acq1.json") == []
    acq1 = json.loads((EXPERIMENT / "manifest_acq1.json").read_bytes())
    current = json.loads((EXPERIMENT / "manifest.json").read_bytes())
    assert acq1["version"] == "RPR-ACQ/1"
    assert current["version"] == "RPR-ACQ/2"
    assert acq1 != current
