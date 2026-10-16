from __future__ import annotations

import copy
import json
import sys

import pytest
from fixtures.p10_campaign import ROOT, prepare_campaign

from rsi import campaign
from settlement.common import SettlementError
from settlement.launcher_codex import CodexLauncher, Provider


def _complete_export(dsn, tmp_path):
    from fixtures.p10_campaign import prepare_campaign

    case = prepare_campaign(
        dsn, tmp_path / "prepare", campaign_id="p10-recompute", round_count=1, max_turns=1
    )
    campaign.start(
        dsn, campaign_id="p10-recompute", charter=case["charter"],
        protocol=case["protocol"], **case["run"]["roots"],
    )
    outcome = campaign.run(
        dsn, case["run"]["agent"], case["run"]["checker"], "p10-recompute",
        **case["run"]["roots"], max_wakes=8, wall_seconds=120,
    )
    if outcome["status"] != "complete":
        investigation = outcome.get("investigation", {})
        last = (outcome.get("results") or [{}])[-1]
        gate_report = last.get("gate", {})
        raise AssertionError({
            "status": outcome["status"], "reason": outcome.get("reason"),
            "last_status": last.get("status"),
            "gate_disposition": gate_report.get("disposition"),
            "gate_reason": gate_report.get("reason"),
            "gate_phases": gate_report.get("phases"),
            "investigation_status": investigation.get("status"),
            "revision": investigation.get("revision"),
            "context_outcome": investigation.get("context_outcome"),
            "execution_error": investigation.get("execution_error"),
            "pending_decision": investigation.get("pending_decision"),
        })
    bundle = campaign.export(
        dsn, "p10-recompute", artifacts_root=case["run"]["roots"]["artifacts_root"]
    )
    assert campaign.recompute(bundle)["status"] == "consistent"
    return bundle


def test_assessment_protocol_keeps_its_own_byte_bound():
    protocol = {"schema": "p10-assessment/1", "rounds": [{
        "id": "x" * campaign._MAX_PROTOCOL_BYTES, "after_turn": 0,
        "epoch": "epoch", "parent": "parent", "candidate": "candidate",
        "model": "model", "route_identity": "0" * 64,
    }]}

    with pytest.raises(SettlementError, match="assessment protocol exceeds byte bound"):
        campaign._parse_protocol(protocol, max_turns=1)


def _assessment_gate(bundle):
    decision = next(row for row in bundle["gate_decisions"] if row["id"].startswith("gate:"))
    return decision["data"], decision["id"].removeprefix("gate:")


def _remove_operation(bundle, operation_id):
    bundle["operations"] = [row for row in bundle["operations"] if row["id"] != operation_id]
    bundle["receipts"] = [
        row for row in bundle["receipts"] if row["operation_id"] != operation_id
    ]


def test_recompute_derives_gain_from_complete_phase_receipt_evidence(migrated_db, tmp_path):
    baseline = _complete_export(migrated_db, tmp_path)
    report, _ = _assessment_gate(baseline)
    assert report["disposition"] == "quarantine"
    assert report["phases"]["val"]

    changed = copy.deepcopy(baseline)
    changed_report, _ = _assessment_gate(changed)
    changed_report["disposition"] = "experimental_gain"
    result = campaign.recompute(changed)
    assert result["status"] == "tampered"
    assert result["comparison_gain"] is False

    verdict_operation = report["phases"]["val"][0]["verdict"]
    missing_receipt = copy.deepcopy(baseline)
    _remove_operation(missing_receipt, verdict_operation)
    result = campaign.recompute(missing_receipt)
    assert result["status"] != "consistent"
    assert result["comparison_gain"] is False

    missing_phase = copy.deepcopy(baseline)
    missing_report, _ = _assessment_gate(missing_phase)
    removed = missing_report["phases"]["val"].pop(0)
    _remove_operation(missing_phase, removed["episode"])
    _remove_operation(missing_phase, removed["verdict"])
    missing_phase["episodes"] = [
        row for row in missing_phase["episodes"] if row["operation_id"] != removed["episode"]
    ]
    missing_phase["verdicts"] = [
        row for row in missing_phase["verdicts"]
        if not (row["episode"] == removed["episode"]
                and row["evaluator_version"] in {
                    spec["evaluator"] for spec in next(
                        epoch["tasks"] for epoch in missing_phase["gate_epochs"]
                        if epoch["digest"] == report["epoch"]
                    ).values()
                })
    ]
    result = campaign.recompute(missing_phase)
    assert result["status"] != "consistent"
    assert result["comparison_gain"] is False

    false_claim = copy.deepcopy(baseline)
    false_report, _ = _assessment_gate(false_claim)
    claimed = false_report["phases"]["val"][0]
    claimed_verdict = next(
        row for row in false_claim["verdicts"] if row["episode"] == claimed["episode"]
    )
    claimed["passed"] = not claimed["passed"]
    claimed["status"] = "passed" if claimed["passed"] else "failed"
    claimed_verdict["passed"] = claimed["passed"]
    claimed_verdict["status"] = claimed["status"]
    result = campaign.recompute(false_claim)
    assert result["status"] == "tampered"
    assert result["comparison_gain"] is False


def test_export_keeps_a_pending_gate_incomplete_not_tampered(migrated_db, tmp_path):
    case = prepare_campaign(
        migrated_db, tmp_path / "prepare-incomplete", campaign_id="p10-incomplete",
        round_count=1, max_turns=1,
    )
    case["protocol"]["rounds"][0]["after_turn"] = 0
    campaign.start(
        migrated_db, campaign_id="p10-incomplete", charter=case["charter"],
        protocol=case["protocol"], **case["run"]["roots"],
    )
    infra_agent = CodexLauncher(
        tmp_path / "incomplete-runs",
        codex_cmd=[sys.executable, str(ROOT / "tests" / "fixtures" / "fake_codex.py"), "infra"],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=frozenset(),
    )
    outcome = campaign.run(
        migrated_db, infra_agent, case["run"]["checker"], "p10-incomplete",
        **case["run"]["roots"], max_wakes=3, wall_seconds=90,
    )
    assert outcome["status"] == "unscored"
    assert outcome["results"][-1]["gate"]["disposition"] == "incomplete"

    bundle = campaign.export(
        migrated_db, "p10-incomplete",
        artifacts_root=case["run"]["roots"]["artifacts_root"],
    )
    report = campaign.recompute(bundle)
    assert report["status"] == "incomplete"
    assert report["comparison_gain"] is False
    assert report["unresolved_operations"], {
        "operations": bundle["operations"], "problems": report["problems"],
    }
    assert not report["problems"]


def test_recompute_requires_exported_effect_reservations(migrated_db, tmp_path):
    bundle = _complete_export(migrated_db, tmp_path)
    assert bundle["reservations"]
    baseline = campaign.recompute(bundle)
    assert baseline["status"] == "consistent", baseline

    without_reservations = copy.deepcopy(bundle)
    without_reservations["reservations"] = []
    wrong_amount = copy.deepcopy(bundle)
    wrong_amount["reservations"][0]["amount"] += 1
    wrong_root = copy.deepcopy(bundle)
    wrong_root["reservations"][0]["allocation_id"] = next(
        item["id"] for item in bundle["allocations"]
        if item["id"] != wrong_root["reservations"][0]["allocation_id"]
    )

    for altered in (without_reservations, wrong_amount, wrong_root):
        report = campaign.recompute(altered)
        assert report["status"] == "tampered", report
        assert report["comparison_gain"] is False
        assert report["resource_units"] is None


def test_six_round_export_exceeds_protocol_limit_and_recomputes(migrated_db, tmp_path):
    case = prepare_campaign(
        migrated_db, tmp_path / "prepare-large", campaign_id="p10-large-export",
        round_count=6, max_turns=1,
    )
    campaign.start(
        migrated_db, campaign_id="p10-large-export", charter=case["charter"],
        protocol=case["protocol"], **case["run"]["roots"],
    )
    outcome = campaign.run(
        migrated_db, case["run"]["agent"], case["run"]["checker"], "p10-large-export",
        **case["run"]["roots"], max_wakes=20, wall_seconds=300,
    )
    assert outcome["status"] == "complete", outcome

    bundle = campaign.export(
        migrated_db, "p10-large-export",
        artifacts_root=case["run"]["roots"]["artifacts_root"],
    )
    encoded = json.dumps(
        bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert len(encoded) > campaign._MAX_PROTOCOL_BYTES
    assert campaign.recompute(bundle)["status"] == "consistent"
