from __future__ import annotations

import json
from pathlib import Path

import pytest

from rsi import context, memory
from settlement.common import ConflictPayload
from test_rsi_memory_integration import (
    LATER_INSTRUCTION,
    _create,
    _revise_lesson,
    _sources,
    _task,
)


def test_context_module_exposes_the_packet_boundary():
    assert callable(context.build)
    assert callable(context.validate)


def _request(investigation_id, *, policy="structured/1", required_obs=(),
             required_claims=(), budget=None, objective=LATER_INSTRUCTION):
    return {
        "investigation_id": investigation_id,
        "objective_revision": 1,
        "state_revision": 1,
        "decision_id": "decision-context-test",
        "attempt_id": "attempt-context-test",
        "operation_id": "operation-context-test",
        "continuation": {
            "objective": objective,
            "objective_revision": 1,
            "state_revision": 1,
            "open_questions": ["Does the solution honor the empty-input rule?"],
            "artifact_refs": {},
            "previous_observation": None,
        },
        "purpose": "task: " + objective,
        "scope": {"domain": "task"},
        "policy": policy,
        "limit": 10,
        "required_observation_ids": list(required_obs),
        "required_claim_ids": list(required_claims),
        **({"budget": budget} if budget is not None else {}),
    }


def _lesson_context(tmp_path, migrated_db):
    (original, _, changed, _, support, opposition) = _sources(tmp_path, migrated_db)
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)
    return changed, support, opposition


def test_packet_pins_complete_claim_bundle_and_replays_without_refresh(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("context")
    run, support, opposition = _lesson_context(tmp_path, migrated_db)
    request = _request(run["id"], required_obs=[support], required_claims=["p02-max-lesson"])

    packet = context.build(migrated_db, request, artifacts_root=run["artifacts_root"])
    claim, = packet["memory_view"]["claims"]
    assert packet["status"] == "ready"
    assert claim["support"] == [support]
    assert claim["opposition"] == [opposition]
    assert {item["observation_id"] for item in packet["memory_view"]["observations"]} == {
        support, opposition,
    }
    continuation = {**request["continuation"], "context_packet": packet}
    assert packet["counts"]["packet_bytes"] == len(json.dumps(
        continuation, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8"))
    assert context.build(migrated_db, request, artifacts_root=run["artifacts_root"]) == packet
    assert context.validate(migrated_db, packet, artifacts_root=run["artifacts_root"])["status"] == "ready"
    changed = _request(run["id"], required_obs=[support], required_claims=["p02-max-lesson"])
    changed["budget"] = {**context.DEFAULT_BUDGET, "packet_bytes": 47_000}
    with pytest.raises(ConflictPayload):
        context.build(migrated_db, changed, artifacts_root=run["artifacts_root"])


def test_missing_required_blocks_but_optional_warnings_do_not(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("context")
    run, _, _ = _lesson_context(tmp_path, migrated_db)
    optional = context.build(
        migrated_db, _request(run["id"]), artifacts_root=run["artifacts_root"])
    assert optional["status"] == "ready"

    required = _request(run["id"] + "-required", required_obs=[999_999])
    # The investigation must exist because P02 enforces scope ownership.
    required_run = _create(
        tmp_path, migrated_db, required["investigation_id"],
        _task("context-required-missing", LATER_INSTRUCTION),
    )
    blocked = context.build(
        migrated_db, required, artifacts_root=required_run["artifacts_root"])
    assert blocked["status"] == "needs_information"
    assert blocked["needs"][0]["kind"] == "observation"
    assert context.validate(migrated_db, blocked,
                            artifacts_root=required_run["artifacts_root"])["status"] == "needs_information"


def test_adaptive_policy_search_changes_visible_excerpt_within_byte_budget(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("context")
    run, support, opposition = _lesson_context(tmp_path, migrated_db)
    req = _request(
        run["id"], policy="adaptive/1", required_claims=["p02-max-lesson"],
        budget={"packet_bytes": 48_000, "scan_bytes": 4096,
                "excerpt_bytes": 256, "actions": 2},
        objective="maximum empty input returns zero — entrée zéro 🧪",
    )
    packet = context.build(migrated_db, req, artifacts_root=run["artifacts_root"])
    assert packet["status"] == "ready"
    assert packet["counts"]["actions"] == 2
    assert packet["counts"]["scanned_bytes"] <= 4096
    assert packet["counts"]["excerpt_bytes"] <= 256
    assert packet["counts"]["packet_bytes"] <= req["budget"]["packet_bytes"]
    assert packet["excerpts"]
    assert {item["observation_id"] for item in packet["memory_view"]["observations"]} == {
        support, opposition,
    }
    assert "empty" in json.dumps(packet["excerpts"]).casefold()
    assert any("xs" in item.get("matched_terms", []) for item in packet["excerpts"])


def test_cached_retry_returns_exact_packet_after_selected_source_disappears(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("context")
    run, support, _ = _lesson_context(tmp_path, migrated_db)
    req = _request(run["id"], required_obs=[support])
    packet = context.build(migrated_db, req, artifacts_root=run["artifacts_root"])
    source = next(item for item in packet["memory_view"]["observations"]
                  if item["observation_id"] == support)
    artifact_path = Path(run["artifacts_root"]) / source["artifacts"][0]
    raw = artifact_path.read_bytes()
    artifact_path.unlink()

    assert context.build(migrated_db, req, artifacts_root=run["artifacts_root"]) == packet
    assert context.validate(migrated_db, packet,
                            artifacts_root=run["artifacts_root"])["status"] == "stale"
    assert raw


def test_packet_validation_ignores_unselected_memory_growth_and_rejects_tampering(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("context")
    run, support, opposition = _lesson_context(tmp_path, migrated_db)
    req = _request(run["id"], required_claims=["p02-max-lesson"])
    packet = context.build(migrated_db, req, artifacts_root=run["artifacts_root"])

    memory.revise(
        migrated_db, claim_id="unrelated-context-claim", expected_version=0,
        text="unrelated claim", scope={"domain": "task"}, status="untested",
        support=(support,), opposition=(), artifacts_root=run["artifacts_root"],
    )
    assert context.validate(migrated_db, packet,
                            artifacts_root=run["artifacts_root"])["status"] == "ready"

    forged = json.loads(json.dumps(packet))
    forged["memory_view"]["observations"].pop()
    assert context.validate(migrated_db, forged,
                            artifacts_root=run["artifacts_root"])["status"] == "stale"


def test_tiny_budget_returns_information_need_instead_of_truncated_opposition(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("context")
    run, support, opposition = _lesson_context(tmp_path, migrated_db)
    req = _request(
        run["id"], required_claims=["p02-max-lesson"],
        budget={"packet_bytes": 1000, "scan_bytes": 1000,
                "excerpt_bytes": 128, "actions": 2},
    )
    packet = context.build(migrated_db, req, artifacts_root=run["artifacts_root"])
    assert packet["status"] == "needs_information"
    assert packet["needs"]
