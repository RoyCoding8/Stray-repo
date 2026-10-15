from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from experiments.agenda05.check import recompute
from experiments.agenda05.driver import build_scenario, run_arm
from experiments.agenda05.freeze import freeze


@pytest.mark.parametrize(("policy", "expected"), [
    ("seed/1", ["source", "priority-task", "scope-probe"]),
    ("adaptive/1", ["source", "scope-probe", "followup-probe"]),
])
def test_frozen_fixture_arm_uses_public_agenda_and_pristine_p01(
    migrated_db, tmp_path, policy, expected
):
    repo = Path(__file__).resolve().parents[1]
    bundle = tmp_path / "freeze"
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps(build_scenario(
        (datetime.now(UTC) + timedelta(hours=1)).isoformat())), encoding="utf-8")
    frozen = freeze(repo, bundle, scenario_path)
    report = run_arm(repo, bundle, tmp_path / "campaign", migrated_db,
                     policy.split("/", 1)[0], "fixture")

    assert report["result"]["status"] == "acknowledged"
    choices = [row["data"] for row in report["agenda_export"]["decisions"]
               if row["kind"] == "p05.choice"]
    assert [choice["opportunity_id"] for choice in choices] == expected
    assert all(choice["policy"] == policy for choice in choices)
    assert all(choice["ranked"][0]["id"] == choice["opportunity_id"]
               and choice["ranked"][0]["eligible"] is True for choice in choices)
    assert report["agenda_export"]["agenda"]["flight"] is None
    assert len(report["operations"]) >= len(choices) * 2
    grade = recompute(frozen, report)
    assert grade["task_results"][0]["status"] == "failed"
    assert any(result["status"] == "passed" for result in grade["task_results"])
    assert grade["failed"] >= 1
    assert grade["verified"] >= 1
    assert grade["unscored"] == 0
    if policy == "adaptive/1":
        assert grade["feedback_effects"]
        assert grade["feedback_effects"][0]["selected"] != \
            grade["feedback_effects"][0]["without_feedback"]

    first_ack = next(row["data"] for row in report["agenda_export"]["decisions"]
                     if row["kind"] == "p05.ack")
    scenario = json.loads(base64.b64decode(frozen["scenario"], validate=True))
    first_choice = next(row["data"] for row in report["agenda_export"]["decisions"]
                        if row["kind"] == "p05.choice")
    selected = next(row for row in scenario["arms"][report["arm_id"]]["charter"]["opportunities"]
                    if row["id"] == first_choice["opportunity_id"])
    task_id = selected["task_id"]
    task_package = json.loads(base64.b64decode(report["task_packages"][task_id]))
    evaluator = task_package["manifest"]["evaluator_version"]
    verifier_id = "rsi-verify-" + hashlib.sha256(
        f"{first_ack['operation_id']}:{evaluator}".encode()).hexdigest()

    missing = copy.deepcopy(report)
    next(row for row in missing["operations"]
         if row["operation"]["id"] == verifier_id)["receipts"] = []
    with pytest.raises(ValueError, match="receipt"):
        recompute(frozen, missing)

    swapped = copy.deepcopy(report)
    verifier_row = next(row for row in swapped["operations"]
                        if row["operation"]["id"] == verifier_id)
    worker_row = next(row for row in swapped["operations"]
                      if row["operation"]["id"] == first_ack["operation_id"])
    verifier_row["receipts"] = worker_row["receipts"]
    with pytest.raises(ValueError, match="receipt"):
        recompute(frozen, swapped)

    changed = copy.deepcopy(report)
    choice_row = next(row for row in changed["agenda_export"]["decisions"]
                      if row["kind"] == "p05.choice")
    choice_row["data"]["opportunity_id"] = "wrong-choice"
    with pytest.raises(ValueError):
        recompute(frozen, changed)

    wrong_task = copy.deepcopy(report)
    worker_operation = next(row["operation"] for row in wrong_task["operations"]
                            if row["operation"]["id"] == first_ack["operation_id"])
    worker_operation["payload"]["payload"]["task"] = "wrong-task"
    with pytest.raises(ValueError, match="Task"):
        recompute(frozen, wrong_task)

    if policy == "adaptive/1":
        disconnected = copy.deepcopy(report)
        candidate = next(row["data"] for row in disconnected["agenda_export"]["decisions"]
                         if row["kind"] == "p05.choice" and row["data"]["turn"] == 2)
        next(option for option in candidate["ranked"]
             if option["id"] == "scope-probe")["triggered"] = False
        with pytest.raises(ValueError, match="ranking"):
            recompute(frozen, disconnected)


def test_fixture_timeout_preserves_pending_flight_and_unknown_usage(migrated_db, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    bundle = tmp_path / "freeze"
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps(build_scenario(
        (datetime.now(UTC) + timedelta(hours=1)).isoformat(), timeout_ms=300)), encoding="utf-8")
    frozen = freeze(repo, bundle, scenario_path)
    report = run_arm(repo, bundle, tmp_path / "campaign", migrated_db,
                     "seed", "fixture", fixture_delay_pairs="2,3")

    assert [result["status"] for result in report["results"]] == ["pending"]
    assert report["agenda_export"]["agenda"]["flight"] is not None
    assert not [row for row in report["agenda_export"]["decisions"]
                if row["kind"] == "p05.ack"]
    grade = recompute(frozen, report)
    assert grade["unscored"] == 1
    assert grade["failed"] == grade["verified"] == 0

    choice = next(row["data"] for row in report["agenda_export"]["decisions"]
                  if row["kind"] == "p05.choice")
    history = report["investigations"][choice["investigation_id"]]
    worker = next(row["data"]["operation_id"] for row in history["decisions"]
                  if row["kind"] == "worker")
    accounting = report["accounting"]
    cost = next(row for row in accounting["reservations"] if row["operation_id"] == worker)
    assert cost["receipt_actual_cost"] is None
    assert cost["charge_basis"] == "reserved_amount_fallback"
    assert cost["charged_units"] == cost["amount"] > 0
    assert cost["usage_status"] == "unknown"
    assert worker in accounting["unknown_usage_operation_ids"]
    assert accounting["allocations"][cost["allocation_id"]]["reserved"] == 0
