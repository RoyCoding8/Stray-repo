from __future__ import annotations

import shutil
from dataclasses import replace

import pytest
from test_rsi_investigate import _scenario, _worker_calls
from test_rsi_memory_integration import LATER_INSTRUCTION

from rsi import context, investigate, memory
from rsi import investigation as state_store
from settlement.common import SettlementError


def test_prepare_context_pins_input_without_admitting_a_decision(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "p06-prepare-pure", "pass-first")
    revision = run["state"]["revision"]

    prepared = investigate.prepare_context(
        run["dsn"], "p06-prepare-pure", target_revision=revision,
        artifacts_root=run["roots"]["artifacts_root"],
    )
    repeated = investigate.prepare_context(
        run["dsn"], "p06-prepare-pure", target_revision=revision,
        artifacts_root=run["roots"]["artifacts_root"],
    )

    assert prepared["status"] == "ready"
    assert prepared["decision_id"] and prepared["attempt_id"] and prepared["operation_id"]
    assert prepared["visible_input"]["state_revision"] == revision
    assert repeated == prepared
    assert state_store.export(run["dsn"], "p06-prepare-pure")["decisions"] == []
    assert _worker_calls(run["worker_log"]) == []


def test_prepared_fresh_start_survives_another_branch_memory_capture(migrated_db, tmp_path):
    first = _scenario(migrated_db, tmp_path / "first", "p06-branch-one", "pass-first")
    second = _scenario(migrated_db, tmp_path / "second", "p06-branch-two", "pass-first")
    first_prepared = investigate.prepare_context(
        first["dsn"], "p06-branch-one", target_revision=first["state"]["revision"],
        artifacts_root=first["roots"]["artifacts_root"],
    )
    second_prepared = investigate.prepare_context(
        second["dsn"], "p06-branch-two", target_revision=second["state"]["revision"],
        artifacts_root=second["roots"]["artifacts_root"],
    )
    pinned_revision = second_prepared["visible_input"]["context_packet"]["memory_view"]["revision"]
    assert first_prepared["status"] == second_prepared["status"] == "ready"

    first_result = investigate.step(
        first["dsn"], first["agent"], first["checker"], "p06-branch-one", **first["roots"]
    )
    assert first_result["status"] == "completed"
    assert _worker_calls(first["worker_log"])
    assert state_store.export(first["dsn"], "p06-branch-one")["observations"]

    second_result = investigate.step(
        second["dsn"], second["agent"], second["checker"], "p06-branch-two", **second["roots"]
    )
    second_call, = _worker_calls(second["worker_log"])
    assert second_result["status"] == "completed"
    assert second_call["continuation"] == second_prepared["visible_input"]
    assert state_store.export(second["dsn"], "p06-branch-two")["decisions"][0]["data"][
        "visible_input"
    ] == second_prepared["visible_input"]
    assert second_prepared["visible_input"]["context_packet"]["memory_view"][
        "revision"
    ] == pinned_revision
    assert context.validate(
        second["dsn"], second_prepared["visible_input"]["context_packet"],
        artifacts_root=second["roots"]["artifacts_root"],
    )["status"] == "ready"


def test_changed_selected_claim_makes_prepared_input_stale(migrated_db, tmp_path):
    source = _scenario(migrated_db, tmp_path / "source", "p06-claim-source",
                       "repair-after-feedback")
    failed = investigate.step(
        source["dsn"], source["agent"], source["checker"], "p06-claim-source",
        **source["roots"],
    )
    assert failed["status"] == "ready" and failed["last_observation"]["passed"] is False
    completed = investigate.step(
        source["dsn"], source["agent"], source["checker"], "p06-claim-source",
        **source["roots"],
    )
    assert completed["status"] == "completed" and completed["last_observation"]["passed"] is True
    observations = state_store.export(migrated_db, "p06-claim-source")["observations"]
    opposition, support = (item["id"] for item in observations)
    memory.revise(
        migrated_db, claim_id="p06-selected-claim", expected_version=0,
        text="List bounds determine whether the chosen maximum method works.",
        scope={"domain": "task"}, status="challenged", support=(support,),
        opposition=(opposition,), artifacts_root=source["roots"]["artifacts_root"],
    )

    target = _scenario(migrated_db, tmp_path / "target", "p06-changed-claim",
                       "pass-first", objective=LATER_INSTRUCTION)
    shutil.copytree(source["roots"]["artifacts_root"],
                    target["roots"]["artifacts_root"], dirs_exist_ok=True)
    target_id = "p06-changed-claim-prepared"
    target_state = investigate.create(
        migrated_db, target["agent"], target["seed"],
        investigation_id=target_id, task=target["candidate"],
        token_allocation="tokens-p06-changed-claim",
        cpu_allocation="cpu-p06-changed-claim", max_steps=2,
        timeout_ms=30_000, token_ceiling=5_000,
        context={"required_claim_ids": ["p06-selected-claim"]},
        **target["roots"],
    )

    prepared = investigate.prepare_context(
        migrated_db, target_id, target_revision=target_state["revision"],
        artifacts_root=target["roots"]["artifacts_root"],
    )
    claim, = [item for item in prepared["visible_input"]["context_packet"]["memory_view"][
        "claims"
    ] if item["claim_id"] == "p06-selected-claim"]
    memory.revise(
        migrated_db, claim_id="p06-selected-claim", expected_version=claim["version"],
        text="A changed selected claim must invalidate its prepared P03 input.",
        scope=claim["scope"], status=claim["status"], support=(support,),
        opposition=(opposition,), artifacts_root=target["roots"]["artifacts_root"],
    )

    result = investigate.step(
        migrated_db, target["agent"], target["checker"], target_id,
        **target["roots"],
    )

    assert result["context_outcome"]["status"] == "stale"
    assert state_store.read(migrated_db, target_id)["pending_decision"] is None
    assert state_store.export(migrated_db, target_id)["decisions"] == []
    assert _worker_calls(target["worker_log"]) == []


def test_worker_model_mismatch_refuses_before_preparation(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "p06-model-mismatch", "pass-first")
    run["agent"].provider = replace(run["agent"].provider, model="fixture:other")

    with pytest.raises(SettlementError, match="worker model differs"):
        investigate.step(
            run["dsn"], run["agent"], run["checker"], "p06-model-mismatch", **run["roots"]
        )

    assert state_store.export(run["dsn"], "p06-model-mismatch")["decisions"] == []
    assert _worker_calls(run["worker_log"]) == []
