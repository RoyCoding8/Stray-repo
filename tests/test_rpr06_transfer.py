"""RPR-06 unchanged-core transfer with fixed budgets (Lane D)."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import panel, run as panel_run
from settlement import representation as R

EVIDENCE_SUB = "arm_task"


def _ctx(dsn, tmp_path, tag):
    base = panel_run.ensure_foundation(dsn, tag)
    manifest = base["manifest"]
    lane_b = manifest["lane_b"]["manifest_digest"]
    panel_run.ensure_episodes(dsn, tag, lane_b)
    artifacts = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    runs = tmp_path / "runs"
    evidence = tmp_path / "evidence"
    for path in (artifacts, staging, runs, evidence):
        path.mkdir(parents=True, exist_ok=True)
    panel_run.ensure_compositions(dsn, tag, staging, artifacts)
    panel_run.ensure_protocols(dsn, tag, manifest)
    from settlement import launcher_local
    launcher = launcher_local.LocalLauncher(str(runs))
    return {**base, "tag": tag, "launcher": launcher,
            "artifacts_root": artifacts, "evidence_root": evidence}


def test_unchanged_core_proved_from_bytes(migrated_db, tmp_path):
    dsn = migrated_db
    ctx = _ctx(dsn, tmp_path, "t06core")
    source = R.check_composition(dsn, ctx["artifacts_root"],
                                 "rpr-C-source-v1-t06core")
    transfer = R.check_composition(dsn, ctx["artifacts_root"],
                                   "rpr-C-transfer-v1-t06core")
    assert source["ok"] and transfer["ok"]
    assert R.compositions_share_core(source, transfer)
    assert source["core_digest"] == transfer["core_digest"]
    assert source["adapter_digest"] != transfer["adapter_digest"]
    manifest = ctx["manifest"]
    comps = {c["composition_id"]: c for c in manifest["compositions"]}
    assert source["core_digest"] == comps["rpr-C-source-v1"]["core_digest"]
    assert transfer["core_digest"] == comps["rpr-C-transfer-v1"]["core_digest"]


def test_transfer_pair_fixed_budget(migrated_db, tmp_path):
    dsn = migrated_db
    ctx = _ctx(dsn, tmp_path, "t06xfer")
    for arm in ("A", "B", "C"):
        result = panel_run.run_benefit_pair(dsn, ctx, arm, "gr-eva-00")
        assert result["skipped"] is False
        record = result["record"]
        assert record["stage"] == "evaluation"
        assert record["family"] == "graph"
        assert record["costs"]["queries_used"] <= panel.BUDGETS["witness_queries"]
        assert record["costs"]["invocations_used"] <= \
            panel.BUDGETS["component_invocations"]
        assert record["costs"]["model_calls"] == 0
        assert {t["protocol_id"] for t in record["trial"]} == \
            ({"rpr-acq-B-t06xfer", "rpr-acq-C-t06xfer"} if arm == "A"
             else {"rpr-acq-%s-t06xfer" % arm})
    by_arm = {arm: json.loads(
        (ctx["evidence_root"] / EVIDENCE_SUB / ("%s-gr-eva-00.json" % arm))
        .read_bytes()) for arm in panel.ARMS}
    assert by_arm["C"]["composition"]["core_digest"] == \
        by_arm["C"]["inputs_digest"]["core"]
    assert by_arm["C"]["result"]["improvement_u"] >= 0.0
    assert by_arm["C"]["result"]["verified"] in (True, False)


def test_acceptance_is_byte_identical_incumbent(migrated_db, tmp_path):
    dsn = migrated_db
    ctx = _ctx(dsn, tmp_path, "t06acc")
    result = panel_run.run_benefit_pair(dsn, ctx, "C", "gr-eva-00")
    record = result["record"]
    task, _ = panel_run.load_task("gr-eva-00")
    incumbent, _ = panel_run.incumbent_of(task)
    if record["result"]["improvement_u"] == 0.0:
        assert record["result"]["delivered_digest"] == panel_run._digest(
            panel_run._canon(incumbent))


def test_core_substitution_attributes_improvement_to_core(migrated_db,
                                                         tmp_path):
    dsn = migrated_db
    ctx = _ctx(dsn, tmp_path, "t06attr")
    for task_id, family in panel.ATTRIBUTION:
        result = panel_run.run_attribution(dsn, ctx, task_id, family)
        record = result["record"]
        assert record["result"]["improvement_u"] == 0.0
        task, _ = panel_run.load_task(task_id)
        incumbent, _ = panel_run.incumbent_of(task)
        assert record["result"]["delivered_digest"] == panel_run._digest(
            panel_run._canon(incumbent))
