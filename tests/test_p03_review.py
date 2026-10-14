from __future__ import annotations

import pytest
from test_rsi_context import _request
from test_rsi_memory_integration import (
    LATER_INSTRUCTION,
    _create,
    _revise_lesson,
    _sources,
    _step,
    _task,
    _worker_calls,
)

from rsi import context, investigate, memory
from rsi import investigation as state_store


def test_new_pending_packet_refuses_withdrawal_without_replacing_effect(
    migrated_db, tmp_path_factory, monkeypatch,
):
    root = tmp_path_factory.mktemp("sol-withdraw")
    original, _, _, _, support, opposition = _sources(root, migrated_db)
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)
    target = _create(root, migrated_db, "sol-pending", _task(
        "sol-pending-task", LATER_INSTRUCTION, empty=True))

    def stop_before_send(*args, **kwargs):
        raise RuntimeError("review stop before send")

    with monkeypatch.context() as patch:
        patch.setattr(investigate.episode, "run_episode", stop_before_send)
        with pytest.raises(RuntimeError, match="review stop before send"):
            _step(target)
    pending = investigate.read(migrated_db, target["id"])["pending_decision"]
    packet = pending["visible_input"]["context_packet"]
    assert context.validate(migrated_db, packet, artifacts_root=original["artifacts_root"])["status"] == "ready"
    memory.revise(migrated_db, claim_id="p02-max-lesson", expected_version=1,
                  text="Withdraw this interpretation.", scope={"domain": "task"},
                  status="withdrawn", support=(support,), opposition=(opposition,),
                  artifacts_root=original["artifacts_root"])
    refused = _step(target)
    assert refused["context_outcome"]["status"] == "stale"
    assert refused["context_outcome"]["operation_id"] == pending["operation_id"]
    assert investigate.read(migrated_db, target["id"])["pending_decision"] == pending
    assert _worker_calls(target) == []


def test_adaptive_next_inspection_changes_with_real_prior_source(
    migrated_db, tmp_path_factory,
):
    root = tmp_path_factory.mktemp("sol-adaptive")
    observed = []
    for name, instruction in (
        ("sol-alpha", "maximum alpha"),
        ("sol-beta", "maximum beta"),
        ("sol-follow", "alpha bears the zero default"),
    ):
        run = _create(root, migrated_db, name, _task(name, instruction))
        assert _step(run)["last_observation"]["passed"] is True
        observation_id = state_store.export(migrated_db, name)["observations"][0]["id"]
        observed.append((run, observation_id))
    packets = []
    for first in observed[:2]:
        request = _request(first[0]["id"], policy="adaptive/1",
                           objective="maximum", required_obs=[first[1], observed[2][1]],
                           budget={"packet_bytes": 48000, "scan_bytes": 1024,
                                   "excerpt_bytes": 256, "actions": 2})
        packet = context.build(migrated_db, request, artifacts_root=first[0]["artifacts_root"])
        assert packet["status"] == "ready"
        assert packet["counts"]["actions"] == 2
        assert context.validate(migrated_db, packet, artifacts_root=first[0]["artifacts_root"])["status"] == "ready"
        packets.append(packet)
    alpha, beta = packets
    alpha_follow = [item for item in alpha["excerpts"] if item["observation_id"] == observed[2][1]]
    beta_follow = [item for item in beta["excerpts"] if item["observation_id"] == observed[2][1]]
    assert alpha_follow == [{"observation_id": observed[2][1],
                             "text": "alpha bears the zero default", "matched_terms": ["alpha"]}]
    assert beta["excerpts"][0]["text"] == "maximum beta"
    assert beta_follow == []
