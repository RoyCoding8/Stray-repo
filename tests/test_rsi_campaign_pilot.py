from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.campaign10 import driver
from experiments.campaign10.freeze import freeze_document, verify_freeze
from rsi import campaign
from settlement import db

ROOT = Path(__file__).resolve().parents[1]


def _agent_run_ids(dsn: str) -> list[str]:
    with db.read_connect(dsn) as conn:
        rows = conn.execute(
            "SELECT id FROM operations WHERE payload->>'effect'='agent-run' ORDER BY id"
        ).fetchall()
    return [row[0] for row in rows]


def _run_fresh_driver_process(dsn: str, evidence_root: Path, phase: str,
                              campaign_id: str) -> dict:
    env = os.environ.copy()
    env["S09ISO_ADMIN_DSN"] = dsn
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)))
    command = [sys.executable, str(ROOT / "experiments/campaign10/driver.py"), phase,
               "--mode", "fixture", "--id", campaign_id,
               "--evidence-root", str(evidence_root)]
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True,
                               capture_output=True, timeout=180, check=False)
    assert completed.returncode == 0, f"pilot child returned {completed.returncode}: {completed.stdout}"
    return json.loads(completed.stdout)


def test_fixture_campaign_runs_development_then_frozen_assessment(migrated_db, tmp_path):
    campaign_id = "p10-fixture-pilot"
    run_dir = tmp_path / "evidence" / campaign_id
    prepared = driver.prepare(migrated_db, campaign_id, run_dir, mode="fixture")

    assert prepared["status"] == "prepared_suspended"
    assert campaign.inspect(migrated_db, campaign_id)["status"] == "suspended"
    assert _agent_run_ids(migrated_db) == []
    identities = prepared["identities"]
    assert identities["development_task"] not in identities["assessment_tasks"].values()
    assert set(identities["assessment_tasks"]) == {
        "assessment-development", "assessment-validation", "assessment-anchor",
    }

    development = _run_fresh_driver_process(
        migrated_db, tmp_path / "evidence", "development", campaign_id)
    assert development["status"] == "development_complete_suspended"
    assert development["evidence_status"] == "exported_and_recomputed"
    assert development["unfinished_campaigns"] == [campaign_id]
    assert len(_agent_run_ids(migrated_db)) == 1
    assert campaign.inspect(migrated_db, campaign_id)["status"] == "suspended"

    assessment = _run_fresh_driver_process(
        migrated_db, tmp_path / "evidence", "assessment", campaign_id)
    assert assessment["durable_agent_run_admissions"] == 6
    assert len(assessment["admission_operation_ids"]) == 6
    assert len(set(assessment["admission_operation_ids"])) == 6
    assert assessment["unresolved_operations"] == []
    assert set(_agent_run_ids(migrated_db)) == set(assessment["admission_operation_ids"])
    assert assessment["recomputed"]["status"] == "consistent"
    assert assessment["score"] is None

    with db.read_connect(migrated_db) as conn:
        assignments = conn.execute(
            "SELECT count(*) FROM rsi_decisions WHERE subject=%s AND kind='p10.assessment.assignment'",
            (campaign_id,),
        ).fetchone()[0]
    assert assignments == 1


def test_freeze_rejects_protocol_and_source_identity_drift(tmp_path):
    protocol = {"schema": "p10-assessment/1", "rounds": [{
        "id": "round", "after_turn": 1, "epoch": "epoch", "parent": "parent",
        "candidate": "candidate", "model": "openrouter/openrouter/free",
        "route_identity": "a" * 64,
    }]}
    freeze_path = tmp_path / "run" / "freeze.json"
    freeze_path.parent.mkdir()
    (freeze_path.parent / "scenario.json").write_text(
        json.dumps(json.loads(driver.SCENARIO.read_text(encoding="utf-8"))),
        encoding="utf-8")
    (freeze_path.parent / "identities.json").write_text("{}", encoding="utf-8")
    (freeze_path.parent / "protocol.json").write_text(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    frozen = freeze_document(mode="fixture", protocol=protocol, identities={})
    source_sha256 = frozen["source_sha256"]
    freeze_path.write_text(json.dumps(frozen), encoding="utf-8")
    assert verify_freeze(freeze_path)["protocol"] == protocol

    changed_protocol = {**protocol, "rounds": []}
    (freeze_path.parent / "protocol.json").write_text(
        json.dumps(changed_protocol, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="protocol"):
        verify_freeze(freeze_path)

    (freeze_path.parent / "protocol.json").write_text(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    frozen["source_sha256"] = "0" * 64
    freeze_path.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(ValueError, match="source_sha256"):
        verify_freeze(freeze_path)

    frozen["source_sha256"] = source_sha256
    frozen["prepared_at_epoch"] += 1
    freeze_path.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(ValueError, match="prepared_at_epoch_sha256"):
        verify_freeze(freeze_path)


def test_stopped_campaign_driver_admits_no_model_effect(migrated_db, tmp_path):
    campaign_id = "p10-fixture-stopped"
    run_dir = tmp_path / "evidence" / campaign_id
    driver.prepare(migrated_db, campaign_id, run_dir, mode="fixture")
    inspection = campaign.inspect(migrated_db, campaign_id)
    campaign.stop(migrated_db, campaign_id, inspection["revision"])

    result = driver.step(migrated_db, campaign_id, run_dir, phase="development")

    assert result["status"] == "incomplete"
    assert result["unfinished_campaigns"] == [campaign_id]
    assert result["unresolved_operations"] == []
    assert _agent_run_ids(migrated_db) == []


def test_scenario_rejects_changed_admission_or_resource_caps(tmp_path):
    scenario = json.loads(driver.SCENARIO.read_text(encoding="utf-8"))
    scenario["caps"]["model_admissions_total"] = 7
    path = tmp_path / "changed-scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")

    with pytest.raises(ValueError, match="caps changed"):
        driver._read_scenario(path)
