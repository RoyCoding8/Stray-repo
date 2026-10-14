from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_rsi_memory_integration import (
    LATER_INSTRUCTION,
    NONEMPTY_INSTRUCTION,
    RESUME_CHILD,
    ROOT,
    WORKER,
    _create,
    _revise_lesson,
    _sources,
    _step,
    _task,
    _worker_calls,
)

from rsi import context, episode, investigate, memory
from rsi import investigation as state_store
from settlement import broker
from settlement.common import Command, ResultCode


def _packet_consumed(packet, call):
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return encoded in call["prompt"]

def test_p03_c_required_claim_need_is_visible_without_dispatch(migrated_db, tmp_path_factory):
    root = tmp_path_factory.mktemp("p03-c")
    target = _create(
        root, migrated_db, "p03-required-missing",
        _task("p03-required-missing-task", LATER_INSTRUCTION, empty=True),
        context_options={"required_claim_ids": ["claim-that-does-not-exist"]},
    )
    result = _step(target)

    assert result["context_outcome"]["status"] == "needs_information"
    assert result["context_outcome"]["needs"]
    assert _worker_calls(target) == []
    durable = investigate.read(migrated_db, target["id"])
    assert durable["status"] == "ready" and durable["pending_decision"] is None


def test_p03_d_selected_artifact_change_blocks_new_decision(migrated_db, tmp_path_factory,
                                                             monkeypatch):
    root = tmp_path_factory.mktemp("p03-d")
    original, _, _, _, support, opposition = _sources(root, migrated_db)
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)
    target = _create(
        root, migrated_db, "p03-stale-packet",
        _task("p03-stale-packet-task", LATER_INSTRUCTION, empty=True),
    )
    build = context.build
    changed = {}

    def build_then_change_source(dsn, request, *, artifacts_root):
        packet = build(dsn, request, artifacts_root=artifacts_root)
        view = packet["memory_view"]
        digests = [digest for observation in view["observations"]
                   for digest in observation.get("artifacts", [])]
        assert digests
        path = Path(artifacts_root) / digests[0]
        changed["path"] = path
        changed["bytes"] = path.read_bytes()
        path.write_bytes(b"changed after context construction")
        return packet

    monkeypatch.setattr(context, "build", build_then_change_source)
    try:
        result = _step(target)
    finally:
        changed["path"].write_bytes(changed["bytes"])

    assert result["context_outcome"]["status"] in ("stale", "needs_information")
    assert investigate.read(migrated_db, target["id"])["pending_decision"] is None
    assert _worker_calls(target) == []


def test_p03_d_swapped_valid_packet_cannot_cross_decision_identity(
    migrated_db, tmp_path_factory,
):
    root = tmp_path_factory.mktemp("p03-swap")
    source = _create(
        root, migrated_db, "p03-packet-source",
        _task("p03-packet-source-task", LATER_INSTRUCTION, empty=True),
    )
    assert _step(source)["status"] == "unresolved"
    source_decision = state_store.export(migrated_db, source["id"])["decisions"][-1]
    packet = source_decision["data"]["visible_input"]["context_packet"]

    target = _create(
        root, migrated_db, "p03-packet-target",
        _task("p03-packet-target-task", LATER_INSTRUCTION, empty=True),
    )
    state = target["state"]
    visible = {
        "objective": state["objective"],
        "objective_revision": state["objective_revision"],
        "state_revision": state["revision"],
        "open_questions": state["open_questions"],
        "artifact_refs": state["artifact_refs"],
        "previous_observation": state["last_observation"],
        "context_packet": packet,
    }
    decided = state_store.decide(migrated_db, Command(
        request_id="p03-swapped-valid-packet",
        expected_revision=state["revision"],
        payload={
            "investigation_id": target["id"],
            "decision_id": "p03-swapped-decision",
            "attempt_id": "p03-swapped-attempt",
            "operation_id": "p03-swapped-operation",
            "action": {"kind": "worker", "explanation": "Use pinned context.",
                       "intended_observation": "Check maximum behavior."},
            "visible_input": visible,
        },
    ))
    assert decided.code == ResultCode.APPLIED

    result = _step(target)

    assert result["context_outcome"]["status"] == "stale"
    assert investigate.read(migrated_db, target["id"])["pending_decision"]["operation_id"] == \
        "p03-swapped-operation"
    assert _worker_calls(target) == []


def test_p03_packet_removal_cannot_fall_back_to_legacy_pending_path(
    migrated_db, tmp_path_factory, monkeypatch,
):
    root = tmp_path_factory.mktemp("p03-packet-removed")
    target = _create(
        root, migrated_db, "p03-packet-removed",
        _task("p03-packet-removed-task", NONEMPTY_INSTRUCTION),
    )
    decide = state_store.decide

    def strip_before_admission(dsn, command):
        payload = dict(command.payload)
        visible = dict(payload["visible_input"])
        visible.pop("context_packet")
        payload["visible_input"] = visible
        return decide(dsn, Command(
            request_id=command.request_id,
            expected_revision=command.expected_revision,
            payload=payload,
        ))

    monkeypatch.setattr(state_store, "decide", strip_before_admission)
    result = _step(target)

    assert result["context_outcome"]["status"] == "stale"
    assert "missing" in result["context_outcome"]["reason"]
    assert investigate.read(migrated_db, target["id"])["pending_decision"] is not None
    assert _worker_calls(target) == []


def test_p03_e_packet_is_in_stored_decision_broker_payload_and_child_input(
    migrated_db, tmp_path_factory, monkeypatch,
):
    root = tmp_path_factory.mktemp("p03-e")
    original, _, _, _, support, opposition = _sources(root, migrated_db)
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)
    irrelevant = _create(
        root, migrated_db, "p03-irrelevant-source",
        _task("p03-irrelevant-task", "Determine zygote spectra resonance."),
    )
    assert _step(irrelevant)["status"] == "completed"
    irrelevant_observation = state_store.export(
        migrated_db, irrelevant["id"])["observations"][0]["id"]
    memory.revise(
        migrated_db, claim_id="p03-irrelevant-claim", expected_version=0,
        text="Zygote spectra resonance needs independent calibration.",
        scope={"domain": "task"}, status="supported",
        support=(irrelevant_observation,), artifacts_root=original["artifacts_root"],
    )
    baseline = _create(
        root, migrated_db, "p03-consumed-baseline",
        _task("p03-consumed-baseline-task", LATER_INSTRUCTION, empty=True),
    )
    passed = _step(baseline)
    baseline_call, = _worker_calls(baseline)
    baseline_decision = state_store.export(migrated_db, baseline["id"])["decisions"][-1]
    baseline_packet = baseline_decision["data"]["visible_input"]["context_packet"]
    baseline_view = baseline_packet["memory_view"]
    selected_claim, = [claim for claim in baseline_view["claims"]
                       if claim["claim_id"] == "p02-max-lesson"]
    baseline_operation = broker.read_operation(
        migrated_db, baseline_decision["data"]["operation_id"])
    baseline_instruction = baseline_operation["payload"]["payload"]["instruction"]
    assert passed["status"] == "completed" and passed["last_observation"]["passed"] is True
    assert selected_claim["support"] == [support]
    assert selected_claim["opposition"] == [opposition]
    assert all(claim["claim_id"] != "p03-irrelevant-claim"
               for claim in baseline_view["claims"])
    assert baseline_call["used_memory"] is True
    assert json.dumps(baseline_packet, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False) in baseline_instruction
    assert _packet_consumed(baseline_packet, baseline_call)

    detached = _create(
        root, migrated_db, "p03-consumed-detached",
        _task("p03-consumed-detached-task", LATER_INSTRUCTION, empty=True),
    )
    actual_run = episode.run_episode
    admitted = {}

    def disconnect_packet(*args, continuation=None, **kwargs):
        pending = investigate.read(migrated_db, detached["id"])["pending_decision"]
        admitted["packet"] = pending["visible_input"]["context_packet"]
        stripped = {key: value for key, value in continuation.items()
                    if key != "context_packet"}
        return actual_run(*args, continuation=stripped, **kwargs)

    monkeypatch.setattr(episode, "run_episode", disconnect_packet)
    result = _step(detached)
    call, = _worker_calls(detached)
    decision = state_store.export(migrated_db, detached["id"])["decisions"][-1]
    operation = broker.read_operation(migrated_db, decision["data"]["operation_id"])
    instruction = operation["payload"]["payload"]["instruction"]

    assert result["status"] == "unresolved" and result["last_observation"]["passed"] is False
    assert decision["data"]["visible_input"]["context_packet"] == admitted["packet"]
    assert json.dumps(admitted["packet"], sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False) not in instruction
    assert not _packet_consumed(admitted["packet"], call)


def test_p03_cached_packet_survives_fresh_process_resume(migrated_db, tmp_path_factory,
                                                          monkeypatch):
    root = tmp_path_factory.mktemp("p03-resume")
    target = _create(
        root, migrated_db, "p03-fresh-resume",
        _task("p03-fresh-resume-task", NONEMPTY_INSTRUCTION),
    )
    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated coordinator exit")

    monkeypatch.setattr(episode, "run_episode", interrupted)
    with pytest.raises(RuntimeError, match="simulated coordinator exit"):
        _step(target)
    pending = investigate.read(migrated_db, target["id"])["pending_decision"]
    packet = pending["visible_input"]["context_packet"]
    operation_id = pending["operation_id"]
    assert _worker_calls(target) == []

    child = subprocess.run(
        [sys.executable, str(RESUME_CHILD), target["id"], str(target["root"]),
         str(target["artifacts_root"]), str(WORKER)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(
            filter(None, (str(ROOT / "src"), os.environ.get("PYTHONPATH", ""))))},
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    resumed = investigate.read(migrated_db, target["id"])
    call, = _worker_calls(target)
    assert resumed["status"] == "completed"
    assert call["operation_id"] == operation_id
    assert call["continuation"]["context_packet"] == packet
    assert _packet_consumed(packet, call)


def test_episode_counts_complete_canonical_utf8_continuation_bytes():
    continuation = {"x": "é" * ((episode.CONTINUATION_MAX_BYTES - 8) // 2)}
    encoded = json.dumps(continuation, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert len(encoded) == episode.CONTINUATION_MAX_BYTES
    episode._instruction("work", continuation, {}, include_digest=False)
    continuation["x"] += "é"
    with pytest.raises(episode.EpisodeError, match="65536 bytes"):
        episode._instruction("work", continuation, {}, include_digest=False)


