"""L-CTX packet binding and opposition regressions (D2A-004, D2A-005).

Real PostgreSQL in every test (`settlement_d2livectx` via SETTLEMENT_TEST_DSN).
Operations are prepared through the real broker admission path; nothing is
dispatched, so no gateway, launcher, or model double is needed anywhere here.

Correspondence (reviewer probes are characterization only, never contracts):
- `test_packet_binding_accepts_unrelated_operation_without_reading_input`
  -> `test_bind_refuses_sandbox_operation`,
  `test_bind_records_model_input_digest`,
  `test_bind_refuses_conflicting_packet_to_second_operation`,
  `test_bind_accepts_true_redelivery_to_second_operation`
- `test_ready_budget_fallback_removes_counterexample_body`
  -> `test_budget_overrun_keeps_opposition_and_stages`
  (the maintained `test_budget_stages_and_refuses` in
  `tests/test_dev02_context.py` pins the same intended contract).
"""

from __future__ import annotations

import sys

import hashlib
import json
import uuid

from settlement import broker, context, db, development, evidence, store
from settlement.common import Command, ResultCode

BIG = {"input_chars": 200_000, "output_reserve": 2_000}


def _cmd() -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload={})


def _seed(dsn, tag):
    store.seed_grant(dsn, Command(request_id=f"{tag}-grant", payload={
        "version": 1, "charter_text": "ctx", "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(dsn, Command(request_id=f"{tag}-alloc", payload={
        "allocation_id": f"{tag}-alloc", "domain": "ctx", "authorized": 100_000,
        "max_occupancy": 64}))
    store.admit_commitment(dsn, Command(request_id=f"{tag}-inv", payload={
        "investigation_id": f"{tag}-inv", "objective": f"objective {tag}",
        "scope": {}, "obligations": {"finish": True}}))
    gen = store.acquire_work(dsn, Command(request_id=f"{tag}-acq", payload={
        "attempt_id": f"{tag}-att", "investigation_id": f"{tag}-inv",
        "allocation_id": f"{tag}-alloc"})).data["ownership_generation"]
    return {"allocation_id": f"{tag}-alloc", "investigation_id": f"{tag}-inv",
            "attempt_id": f"{tag}-att", "generation": gen}


def _observe(dsn, tag, seed, claim_id=None):
    refs = [{"task_id": "t1", "family": "f"}]
    if claim_id:
        refs.append({"task_id": "t1", "claim_id": claim_id})
    development.observe(dsn, _cmd(), episode_id=f"{tag}-ep",
                        investigation_id=seed["investigation_id"], trigger_refs=refs,
                        bottleneck="bottleneck t1")
    development.propose(dsn, _cmd(), episode_id=f"{tag}-ep",
                        predicted_effect="effect t1", competing="other")
    return f"{tag}-ep"


def _receipt(dsn, op_id, attempt_id, content):
    from psycopg.types.json import Json
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO operations (id, attempt_id, payload_digest, payload,"
                        " dispatch_state) VALUES (%s, %s, %s, %s, 'observed')",
                        (op_id, attempt_id, "d", Json({"kind": "infer"})))
            cur.execute("INSERT INTO receipts (receipt_identity, operation_id,"
                        " content_digest, content, outcome) VALUES (%s, %s, %s, %s, %s)",
                        (f"rc-{op_id}", op_id, "c", Json(content), "success"))
            conn.commit()


def _ready_packet(dsn, tag, seed, claim_id=None):
    ep = _observe(dsn, tag, seed, claim_id)
    evidence.register_observation(dsn, _cmd(), seed["attempt_id"],
                                  {"finding": "attempted"}, source_identity="sensor")
    _receipt(dsn, f"{tag}-op", seed["attempt_id"], {"repaired": True})
    result = context.build_packet(dsn, _cmd(), decision={
        "decision_kind": "diagnose", "purpose": f"diagnose {tag}",
        "required_inputs": [], "allowed_actions": ["read"], "access": "evaluator",
        "budget": dict(BIG), "current_versions": {},
        "investigation_id": seed["investigation_id"], "episode_id": ep})
    assert result.code == ResultCode.APPLIED
    assert result.data["outcome"] == "ready"
    return result


def _model_op(dsn, op_id, seed, prompt="decide"):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "probe-model",
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": 16, "deadline_ms": 300_000},
        allocation_id=seed["allocation_id"], attempt_id=seed["attempt_id"])


def _sandbox_op(dsn, op_id, seed):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": [sys.executable, "-c", "pass"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        allocation_id=seed["allocation_id"], attempt_id=seed["attempt_id"])


def _stored_payload(dsn, operation_id):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM operations WHERE id = %s",
                        (operation_id,))
            payload = cur.fetchone()[0]
            conn.commit()
    return dict(payload)


def _invocations(dsn, packet_id):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT packet_id, operation_id, rendered_digest, input_digest"
                        " FROM packet_invocations WHERE packet_id = %s", (packet_id,))
            rows = [tuple(r) for r in cur.fetchall()]
            conn.commit()
    return rows


def test_bind_refuses_sandbox_operation(migrated_db):
    dsn = migrated_db
    tag = f"d02live-{uuid.uuid4().hex[:8]}"
    seed = _seed(dsn, tag)
    packet = _ready_packet(dsn, tag, seed)
    prepared = _sandbox_op(dsn, f"{tag}-sandbox", seed)
    assert prepared.code == ResultCode.APPLIED
    refused = context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-sandbox")
    assert refused.code == ResultCode.INVALID_INPUT
    assert "not model inference" in refused.detail
    assert _invocations(dsn, packet.data["packet_id"]) == []


def test_bind_records_model_input_digest(migrated_db):
    dsn = migrated_db
    tag = f"d02live-{uuid.uuid4().hex[:8]}"
    seed = _seed(dsn, tag)
    packet = _ready_packet(dsn, tag, seed)
    prepared = _model_op(dsn, f"{tag}-infer", seed,
                         prompt="decide with " + packet.data["packet_id"])
    assert prepared.code == ResultCode.APPLIED
    bound = context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-infer")
    assert bound.code == ResultCode.APPLIED
    stored = _stored_payload(dsn, f"{tag}-infer")
    assert stored["effect"] == broker.MODEL_INFERENCE
    expect = hashlib.sha256(json.dumps(
        stored, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert bound.data["input_digest"] == expect
    assert _invocations(dsn, packet.data["packet_id"]) == [
        (packet.data["packet_id"], f"{tag}-infer",
         packet.data["rendered_digest"], expect)]


def test_bind_refuses_conflicting_packet_to_second_operation(migrated_db):
    dsn = migrated_db
    tag = f"d02live-{uuid.uuid4().hex[:8]}"
    seed = _seed(dsn, tag)
    packet = _ready_packet(dsn, tag, seed)
    assert _model_op(dsn, f"{tag}-first", seed,
                     prompt="decide with " + packet.data["packet_id"]).code == \
        ResultCode.APPLIED
    assert _model_op(dsn, f"{tag}-second", seed,
                     prompt="unrelated " + tag).code == ResultCode.APPLIED
    first = context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-first")
    assert first.code == ResultCode.APPLIED
    replay = context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-second")
    assert replay.code == ResultCode.INVALID_INPUT
    assert "already bound" in replay.detail
    assert [row[1] for row in _invocations(dsn, packet.data["packet_id"])] == [
        f"{tag}-first"]
    repeat = context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-first")
    assert repeat.code == ResultCode.ALREADY_APPLIED
    assert repeat.data["input_digest"] == first.data["input_digest"]


def test_bind_accepts_true_redelivery_to_second_operation(migrated_db):
    dsn = migrated_db
    tag = f"d02live-{uuid.uuid4().hex[:8]}"
    seed = _seed(dsn, tag)
    packet = _ready_packet(dsn, tag, seed)
    for op in (f"{tag}-slot0", f"{tag}-slot1"):
        assert _model_op(dsn, op, seed,
                         prompt="decide with " + packet.data["packet_id"]).code == \
            ResultCode.APPLIED
    assert context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-slot0").code == \
        ResultCode.APPLIED
    redelivered = context.bind_packet_invocation(
        dsn, _cmd(), packet.data["packet_id"], f"{tag}-slot1")
    assert redelivered.code == ResultCode.APPLIED
    assert sorted(row[1] for row in _invocations(dsn, packet.data["packet_id"])) == [
        f"{tag}-slot0", f"{tag}-slot1"]


def test_budget_overrun_keeps_opposition_and_stages(migrated_db):
    dsn = migrated_db
    tag = f"d02live-{uuid.uuid4().hex[:8]}"
    seed = _seed(dsn, tag)
    ep = _observe(dsn, tag, seed, claim_id=f"{tag}-c")
    receipt = evidence.register_observation(
        dsn, _cmd(), seed["attempt_id"], {"finding": "supports"},
        source_identity="sensor").data["receipt_id"]
    evidence.propose_claim(dsn, _cmd(), f"{tag}-c", {"text": "method is safe"})
    evidence.admit_warrant(dsn, _cmd(), f"{tag}-w", f"{tag}-c", "review", "v1",
                           [[(receipt, "observation")]])
    body = {"counterexample": "n=-1 returns wrong answer",
            "detail": "z" * 6_000}
    evidence.register_opposition(dsn, _cmd(), f"{tag}-o", f"{tag}-c",
                                 "opposition", body)
    _receipt(dsn, f"{tag}-op", seed["attempt_id"], {"ok": True})

    def _build(budget, purpose):
        return context.build_packet(dsn, _cmd(), decision={
            "decision_kind": "diagnose", "purpose": purpose,
            "required_inputs": [], "allowed_actions": ["read"],
            "access": "evaluator", "budget": budget, "current_versions": {},
            "investigation_id": seed["investigation_id"], "episode_id": ep})

    wide = _build(dict(BIG), "wide")
    assert wide.data["outcome"] == "ready"
    assert "n=-1 returns wrong answer" in wide.data["rendered"]
    tight = _build({"input_chars": wide.data["token_estimate"]["chars"] - 1_000,
                    "output_reserve": 2_000}, "tight")
    assert tight.data["outcome"] == "needs_information"
    assert "n=-1 returns wrong answer" in tight.data["rendered"]
    assert "z" * 1_000 in tight.data["rendered"]
    assert not [o for o in tight.data["omissions"] if o["reason"] == "budget"]
    staged = next(g for g in tight.data["gaps"] if g["slot"] == "budget")
    assert "narrower" in staged["proposal"]
    assert tight.data["rendered"].index("== mandatory ==") < \
        tight.data["rendered"].index("== evidence ==")
    assert tight.data["token_estimate"]["labeled"] == "chars-not-tokens"
