"""The acquisition source anchor was a second copy of bytes the store holds.

`_source_anchor_value` derived the anchor from
`original["details"]["raw_payload"]`, and the evidence record that owns that
`raw_payload` is written into the same document by the same transaction. The
sidecar was a copy of a value the document already carried, keyed by a value
the document already carried, in a file with its own atomicity and no share
of the document's lock.

These tests hold the replacement to the same refusals the sidecar made.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

# The charter shape `ensure_live_store` accepts, as a fixture. It was a
# production helper with no production caller, deleted in 8d354a5.
from conftest import live_mission


def _store(tmp_path, name="store.json"):
    return live.ensure_live_store(
        tmp_path / name,
        live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))


def _dispatch(prompt="construct an improver", operation_id="op-anchor"):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id,
                json.dumps({"entry": channel.IMPROVE_LOW_SOURCE}),
                {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    guard.infer(ModelRequest(
        model="test-model",
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=8,
        deadline_ms=1000,
        operation_id=operation_id,
    ), evidence={"arm": "test", "task": "rule-dev-0004", "attempt": 1,
                 "raw_prompt": prompt})
    return guard.provenance(operation_id)


def _sidecars(store) -> list:
    return sorted(p for p in Path(store.path).parent.iterdir()
                  if ".source-anchor-" in p.name)


def _acquired(store):
    from tests.test_provenance_authority import _model_package

    store.bind_active(channel.make_control("low"))
    return _model_package(store)


def _reseal(record: dict) -> None:
    """Reseal every digest an adversary recomputing the document would get."""
    record["raw_payload_digest"] = frontier.source_digest(
        frontier.canonical(record["details"].get("raw_payload")))
    record["route_digest"] = frontier.source_digest(
        frontier.canonical(record["details"].get("route")))
    record["evidence_digest"] = frontier._evidence_identity_digest(record)


# --- one durable format -------------------------------------------------


def test_recording_acquisition_evidence_writes_no_sidecar(tmp_path):
    """A store is one format, not two.

    RED on base: the sidecar appeared here, proving the mechanism ran rather
    than this assertion passing vacuously.
    """
    store = _store(tmp_path)
    _acquired(store)
    assert _sidecars(store) == [], (
        "the acquisition path did not run: no anchor was written, so this"
        " asserts nothing")

    live.restart_store(store.path)
    assert _sidecars(store) == []


def test_a_failed_document_save_leaves_no_orphan_anchor(tmp_path, monkeypatch):
    """An anchor must not outlive the evidence record that justified it.

    On base the sidecar was written at frontier.py:1532 and the document at
    :1545, so a failed replace left the sidecar naming an operation the store
    had no record of, and nothing durable could contradict it.
    """
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    dispatch = _dispatch()

    def refuse_replace(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(frontier.os, "replace", refuse_replace)
    with pytest.raises(OSError):
        store.record_evidence(dispatch)
    monkeypatch.undo()

    persisted = json.loads(Path(store.path).read_text(encoding="utf-8"))
    assert not any(
        item.get("operation_id") == dispatch["operation_id"]
        for item in persisted["evidence"]), (
        "the reproduction did not exercise the defect: the document already"
        " recorded the evidence, so save() never failed")
    assert _sidecars(store) == []


def test_a_failed_save_does_not_refuse_the_legitimate_retry(tmp_path,
                                                           monkeypatch):
    """The sharpest form of the ordering defect.

    On base, the orphan sidecar from the failed transaction decided what the
    store would accept afterwards: a legitimate re-dispatch of the same
    operation with different bytes was refused by a file belonging to a
    transaction that never committed.
    """
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    first = _dispatch("prompt from attempt 1")

    def refuse_replace(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(frontier.os, "replace", refuse_replace)
    with pytest.raises(OSError):
        store.record_evidence(first)
    monkeypatch.undo()

    retry = _dispatch("prompt from attempt 2")
    assert store.record_evidence(retry)["operation_id"] == retry[
        "operation_id"]


# --- the validation is not weakened --------------------------------------


def test_mutated_raw_bytes_are_refused_after_restart(tmp_path):
    """The sidecar's refusal survives its deletion, and then some.

    On base this was caught by comparing the sidecar with the record. Now the
    record is bound to its own raw bytes through `input_digest` and
    `result_digest`, which is where those bytes were already checked.
    """
    store = _store(tmp_path)
    package = _acquired(store)
    original = next(
        record for record in store._doc["evidence"]
        if record.get("evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    raw_payload = dict(original["details"]["raw_payload"])
    raw_payload["raw_response"] = json.dumps(
        {"entry": channel.IMPROVE_HIGH_SOURCE})
    original["details"] = dict(original["details"], raw_payload=raw_payload)
    _reseal(original)
    store.save()

    with pytest.raises(frontier.Refused, match="source anchor"):
        live.restart_store(store.path)


def test_raw_bytes_that_digest_to_the_record_survive_restart(tmp_path):
    """The check must pass for legitimately recorded evidence.

    Deleting the sidecar must not refuse a store whose bytes are intact, or
    the deletion is a refusal rather than a repair.
    """
    store = _store(tmp_path)
    _acquired(store)
    restarted = live.restart_store(store.path)
    record = restarted._doc["evidence"][-1]
    anchored = restarted._validate_source_anchor(record)
    assert anchored["raw_prompt"] == record["details"]["raw_payload"][
        "raw_prompt"]
    assert anchored["raw_response"] == record["details"]["raw_payload"][
        "raw_response"]


def test_a_record_with_swapped_raw_bytes_is_refused_directly(tmp_path):
    """`_validate_source_anchor` still refuses a record, not a file."""
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    dispatch = _dispatch()
    forged = dict(dispatch)
    payload = dict(dispatch["details"]["raw_payload"])
    payload["raw_response"] = json.dumps(
        {"entry": channel.IMPROVE_HIGH_SOURCE})
    forged["details"] = dict(forged["details"], raw_payload=payload)
    _reseal(forged)

    with pytest.raises(frontier.Refused, match="source anchor"):
        store._validate_source_anchor(forged)
