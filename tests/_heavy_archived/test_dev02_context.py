"""M-CTX bounded decision-context packets (CTX-01..CTX-07, CTX-09).

Real PostgreSQL in every test (`settlement_dev02ctx` via SETTLEMENT_TEST_DSN)
plus real subprocesses for the fresh-process reconstruction check. No model
inference anywhere on these paths, so no doubles are needed: fixtures use the
real store/evidence/artifact/development entry points, with direct SQL only
where no public setter exists (episode explanations/candidates, capability
rows, quarantine, outcome receipts).

Correspondence (D02LIVE lane L-CTX): reviewer probe
`test_ready_budget_fallback_removes_counterexample_body`
(`reviews/probes/test_development_02_acceptance.py`) characterized
ready-with-omissions stripping of opposition bodies; `test_budget_stages`
below now pins the intended contract instead (never strip, stage on
overrun). Probe `test_packet_binding_accepts_unrelated_operation...` maps
to `tests/test_d02live_context.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid

import pytest
from jinja2 import Environment
from psycopg.types.json import Json

from settlement import artifacts, broker, capabilities, context, db, development, evidence, store
from settlement.api import overview_data
from settlement.common import Command, ResultCode, SettlementError

from conftest import unique

BIG = {"input_chars": 200_000, "output_reserve": 2_000}


def _cmd(tag=None) -> Command:
    return Command(request_id=f"req_{tag or uuid.uuid4().hex[:12]}", payload={})


def _pcmd(tag, payload) -> Command:
    return Command(request_id=f"req_{tag}-{unique('c')}", payload=payload)


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


def _record(dsn, op_id, attempt_id, outcome, content):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO operations (id, attempt_id, payload_digest, payload,"
                        " dispatch_state) VALUES (%s, %s, %s, %s, 'observed')",
                        (op_id, attempt_id, "d", Json({"kind": "infer"})))
            cur.execute("INSERT INTO receipts (receipt_identity, operation_id,"
                        " content_digest, content, outcome) VALUES (%s, %s, %s, %s, %s)",
                        (f"rc-{op_id}", op_id, "c", Json(content), outcome))
            conn.commit()


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


def _set_episode(dsn, episode_id, **fields):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for key, value in fields.items():
                cur.execute(f"UPDATE development_episodes SET {key} = %s WHERE id = %s",
                            (Json(value), episode_id))
            conn.commit()


def _warranted_claim(dsn, tag, seed, access="public", groups=2):
    receipts = [evidence.register_observation(
        dsn, _cmd(), seed["attempt_id"], {"finding": f"s{i}"},
        source_identity="sensor").data["receipt_id"] for i in range(groups)]
    evidence.propose_claim(dsn, _cmd(), f"{tag}-c", {"text": f"claim {tag} holds"},
                           access_label=access)
    evidence.admit_warrant(dsn, _cmd(), f"{tag}-w", f"{tag}-c", "review", "v1",
                           [[(receipt, "observation")] for receipt in receipts])
    return receipts


def _publish_bytes(dsn, roots, tag, text="print('ok')"):
    raw = text.encode()
    manifest = {"files": [{"path": "entry.py", "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(),
                           "size": len(raw)}],
                "entry": "entry.py", "verify_args": ["--selftest"]}
    receipt = artifacts.stage_package(dsn, roots["staging"], manifest=manifest,
                                      files={"entry.py": raw}, scope=tag)
    artifacts.publish_package(dsn, _cmd(), roots["artifacts"], receipt)
    return receipt


def _capability(dsn, tag, digest):
    vid = f"{tag}-cv"
    invocation = {"entry": "entry.py", "args": ["--selftest"]}
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family, invocation, effect,"
                        " resource, artifact_digest, applicability) VALUES"
                        " (%s, %s, %s, %s, %s, %s, %s)",
                        (vid, "f", Json(invocation), Json({"writes": "none"}),
                         Json({"cpu_ms": 100}), digest, Json({"family": "f"})))
            conn.commit()
    return vid, invocation


def _decision(kind, seed, episode_id="", access="evaluator", versions=None,
              budget=None, purpose="probe"):
    return {"decision_kind": kind, "purpose": purpose,
            "required_inputs": [], "allowed_actions": ["read"], "access": access,
            "budget": dict(budget or BIG), "current_versions": dict(versions or {}),
            "investigation_id": seed["investigation_id"], "episode_id": episode_id}


def _diagnose_ready(dsn, tag, seed, roots=None, claim_id=None):
    ep = _observe(dsn, tag, seed, claim_id)
    evidence.register_observation(dsn, _cmd(), seed["attempt_id"],
                                  {"finding": "attempted"}, source_identity="sensor")
    _record(dsn, f"{tag}-op", seed["attempt_id"], "success", {"repaired": True})
    result = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, purpose=f"diagnose {tag}"))
    assert result.code == ResultCode.APPLIED
    assert result.data["outcome"] == "ready"
    return result, ep


def test_kind_contracts_differ_and_empty_refs_never_ready(migrated_db):
    dsn = migrated_db
    seed = {"investigation_id": "missing"}
    gaps = {}
    for kind in ("diagnose", "construct", "resume"):
        result = context.build_packet(dsn, _cmd(), decision=_decision(
            kind, seed, "missing", purpose=f"empty {kind}"))
        assert result.data["outcome"] == "needs_information", kind
        gaps[kind] = {g["slot"] for g in result.data["gaps"] if not g.get("stale")}
    assert gaps["diagnose"] == {"development_inputs", "attempted_behaviors", "outcomes",
                                "task_specs"}
    assert gaps["construct"] == {"intervention", "examples", "development_feedback",
                                 "invocation_contract", "applicability",
                                 "effect_envelope", "revision_budget"}
    assert gaps["resume"] == {"objective", "selected_versions", "obligations",
                              "next_decision", "allocation"}
    assert len({frozenset(v) for v in gaps.values()}) == 3
    narrowed = dict(_decision("diagnose", seed, "missing"))
    narrowed["required_inputs"] = ["allocation"]
    held = context.build_packet(dsn, _cmd(), decision=narrowed)
    assert "allocation" in {g["slot"] for g in held.data["gaps"]}
    with pytest.raises(SettlementError):
        context.build_packet(dsn, _cmd(), decision=_decision(
            "fly", seed, "missing"))
    bad = dict(_decision("diagnose", seed, "missing"))
    bad["required_inputs"] = ["no-such-slot"]
    with pytest.raises(SettlementError):
        context.build_packet(dsn, _cmd(), decision=bad)
    for budget in ({}, {"input_chars": 0, "output_reserve": 0}):
        broken = dict(_decision("diagnose", seed, "missing"))
        broken["budget"] = budget
        with pytest.raises(SettlementError):
            context.build_packet(dsn, _cmd(), decision=broken)


def test_diagnose_ready_materializes_experience(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, f"ctx02-{unique('t')}")
    result, _ = _diagnose_ready(dsn, f"ctx02-{unique('t')}", seed)
    data = result.data
    assert set(data["mandatory_content"]) == set(context._REQUIRED["diagnose"])
    assert data["mandatory_content"]["task_specs"]["objective"].startswith("objective ")
    assert data["rendered_digest"] == hashlib.sha256(
        data["rendered"].encode()).hexdigest()
    assert data["token_estimate"]["labeled"] == "chars-not-tokens"
    assert "token" not in json.dumps(data["token_estimate"]).lower().replace(
        "chars-not-tokens", "")
    wire = json.dumps({"packet_id": data["packet_id"],
                       "policy_version": context.POLICY_VERSION,
                       "rendered": data["rendered"]},
                      sort_keys=True, separators=(",", ":"))
    assert data["token_estimate"]["chars"] == len(wire) + BIG["output_reserve"]
    assert data["token_estimate"]["chars"] <= BIG["input_chars"]
    assert data["footprint"]["policy_version"] == context.POLICY_VERSION
    again = context.build_packet(
        dsn, Command(request_id=result.request_id, payload={}),
        decision=_decision("diagnose", seed, "missing"))
    assert again.code == ResultCode.ALREADY_APPLIED
    assert again.data["packet_id"] == data["packet_id"]


def test_protected_evaluation_material_never_delivered(migrated_db):
    dsn = migrated_db
    tag = f"ctx03-{unique('t')}"
    seed = _seed(dsn, tag)
    evidence.register_observation(dsn, _cmd(), seed["attempt_id"], {"finding": "x"},
                                  source_identity="sensor")
    _record(dsn, f"{tag}-op", seed["attempt_id"], "success", {"ok": True})
    evidence.propose_claim(dsn, _cmd(), f"{tag}-hid", {"text": "sealed eval note"},
                           access_label="hidden")
    ep = _observe(dsn, tag, seed)
    sealed = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, access="candidate", purpose="candidate view"))
    assert sealed.data["outcome"] == "ready"
    assert "sealed eval note" not in sealed.data["rendered"]
    _set_episode(dsn, ep, explanations=[{"id": "e1", "text": "h"}])
    _warranted_claim(dsn, tag, seed)
    open_view = context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, access="candidate", versions={},
        purpose="candidate construct"))
    assert "sealed eval note" not in open_view.data["rendered"]
    assert f"claim {tag} holds" in open_view.data["rendered"]
    full = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, access="evaluator", purpose="evaluator view"))
    assert full.data["outcome"] == "ready"


def test_construct_contracts_are_exact(migrated_db, tmp_roots):
    dsn = migrated_db
    tag = f"ctx04-{unique('t')}"
    seed = _seed(dsn, tag)
    ep = _observe(dsn, tag, seed)
    _set_episode(dsn, ep, explanations=[{"id": "e1", "text": "cause"}],
                 candidates=[{"version": f"{tag}-v0"}])
    _warranted_claim(dsn, tag, seed)
    evidence.register_opposition(dsn, _cmd(), f"{tag}-o", f"{tag}-c",
                                 "opposition", {"note": "counterexample"})
    receipt = _publish_bytes(dsn, tmp_roots, tag)
    vid, invocation = _capability(dsn, tag, receipt["digest"])
    result = context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions={"candidate_version": vid},
        purpose="construct it"))
    assert result.data["outcome"] == "ready"
    content = result.data["mandatory_content"]
    assert content["invocation_contract"]["invocation"] == invocation
    assert content["invocation_contract"]["version"] == vid
    assert content["effect_envelope"]["effect"] == {"writes": "none"}
    assert content["revision_budget"]["ceilings"]["max_candidates"] == 2
    assert content["candidate_lineage"]["candidates"] == [{"version": f"{tag}-v0"}]
    bundle = next(b for b in result.data["evidence_bundles"]
                  if b["claim_id"] == f"{tag}-c")
    assert bundle["disposition"] == "supported"
    assert bundle["proposition"] == {"text": f"claim {tag} holds"}
    assert any("counterevidence" in q for q in bundle["qualifications"])
    assert any("authoritative" in q for q in bundle["qualifications"])
    assert result.data["footprint"]["derivation_routes"][f"{tag}-c"] == f"{tag}-w"
    assert f"{tag}-o" in result.data["footprint"]["oppositions"]


def test_budget_stages_and_refuses(migrated_db):
    dsn = migrated_db
    tag = f"ctx05-{unique('t')}"
    seed = _seed(dsn, tag)
    ep = _observe(dsn, tag, seed, claim_id=f"{tag}-big")
    small = evidence.register_observation(
        dsn, _cmd(), seed["attempt_id"], {"finding": "small"},
        source_identity="sensor").data["receipt_id"]
    evidence.propose_claim(dsn, _cmd(), f"{tag}-big", {"text": "big holds"})
    evidence.admit_warrant(dsn, _cmd(), f"{tag}-w", f"{tag}-big", "review", "v1",
                           [[(small, "observation")]])
    evidence.register_opposition(dsn, _cmd(), f"{tag}-big-o", f"{tag}-big",
                                 "opposition", {"note": "y" * 50_000})
    _record(dsn, f"{tag}-op", seed["attempt_id"], "success", {"ok": True})
    wide = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, purpose="wide"))
    assert wide.data["outcome"] == "ready"
    assert "y" * 1_000 in wide.data["rendered"]
    full_total = wide.data["token_estimate"]["chars"]
    squeezed = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, budget={"input_chars": full_total - 10_000,
                                      "output_reserve": 2_000},
        purpose="squeezed"))
    assert squeezed.data["outcome"] == "needs_information"
    assert "y" * 1_000 in squeezed.data["rendered"]
    assert not [o for o in squeezed.data["omissions"] if o["reason"] == "budget"]
    staged = next(g for g in squeezed.data["gaps"] if g["slot"] == "budget")
    assert "narrower" in staged["proposal"]
    assert squeezed.data["rendered"].index("== mandatory ==") < \
        squeezed.data["rendered"].index("== evidence ==")
    refused = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, budget={"input_chars": 100, "output_reserve": 0},
        purpose="refused"))
    assert refused.data["outcome"] == "needs_information"
    assert any(g["slot"] == "budget" for g in refused.data["gaps"])
    assert refused.data["token_estimate"]["labeled"] == "chars-not-tokens"


def _admitted_model_op(dsn, op_id, seed, prompt="decide"):
    ensured = broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "probe-model",
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": 16, "deadline_ms": 300_000},
        allocation_id=seed["allocation_id"], attempt_id=seed["attempt_id"])
    assert ensured.code == ResultCode.APPLIED
    return op_id


def test_bind_records_bytes_and_refuses_metadata_only(migrated_db):
    dsn = migrated_db
    tag = f"ctx06-{unique('t')}"
    seed = _seed(dsn, tag)
    result, _ = _diagnose_ready(dsn, tag, seed)
    packet_id = result.data["packet_id"]
    infer_op = _admitted_model_op(dsn, f"{tag}-infer", seed)
    ghost = context.bind_packet_invocation(dsn, _cmd(), "pkt_missing", f"{tag}-op")
    assert ghost.code == ResultCode.INVALID_INPUT
    thin = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, "missing", purpose="thin"))
    assert thin.data["outcome"] == "needs_information"
    unready = context.bind_packet_invocation(dsn, _cmd(), thin.data["packet_id"],
                                             f"{tag}-op")
    assert unready.code == ResultCode.INVALID_INPUT
    bound = context.bind_packet_invocation(dsn, _cmd(), packet_id, infer_op)
    assert bound.code == ResultCode.APPLIED
    assert bound.data["rendered_digest"] == result.data["rendered_digest"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT packet_id, operation_id, rendered_digest"
                        " FROM packet_invocations WHERE packet_id = %s", (packet_id,))
            rows = cur.fetchall()
            conn.commit()
    assert [(packet_id, infer_op, result.data["rendered_digest"])] == [
        tuple(r) for r in rows]
    repeat = context.bind_packet_invocation(dsn, _cmd(), packet_id, infer_op)
    assert repeat.code == ResultCode.ALREADY_APPLIED
    lost = context.bind_packet_invocation(dsn, _cmd(), packet_id, "op-missing")
    assert lost.code == ResultCode.INVALID_INPUT


def test_defeat_stales_but_alternative_routes_survive(migrated_db):
    dsn = migrated_db
    tag = f"ctx07-{unique('t')}"
    seed = _seed(dsn, tag)
    ep = _observe(dsn, tag, seed, claim_id=f"{tag}-c")
    evidence.register_observation(dsn, _cmd(), seed["attempt_id"],
                                  {"finding": "attempted"}, source_identity="sensor")
    _record(dsn, f"{tag}-op", seed["attempt_id"], "success", {"ok": True})
    r1, r2 = _warranted_claim(dsn, tag, seed)
    first = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, purpose="first"))
    assert first.data["outcome"] == "ready"
    evidence.retract(dsn, _cmd(), r1, "sensor recalibrated")
    second = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, purpose="second"))
    assert second.data["outcome"] == "ready"
    bundle = next(b for b in second.data["evidence_bundles"]
                  if b["claim_id"] == f"{tag}-c")
    assert bundle["selected_route"]["premises"] == [
        {"ref": r2, "kind": "observation"}]
    assert any("blocked" in q for q in bundle["qualifications"])
    check = context.revalidate_packet(dsn, first.data["packet_id"])
    assert check["valid"] is True
    assert any("failed over" in n for n in check["notes"])
    evidence.register_opposition(dsn, _cmd(), f"{tag}-d", f"{tag}-c",
                                 "defeat", {"note": "replication failed"})
    third = context.build_packet(dsn, _cmd(), decision=_decision(
        "diagnose", seed, ep, purpose="third"))
    assert third.data["outcome"] == "stale"
    assert any(g.get("stale") for g in third.data["gaps"])
    recheck = context.revalidate_packet(dsn, first.data["packet_id"])
    assert recheck["valid"] is False
    assert any("defeated" in r for r in recheck["reasons"])


def test_quarantine_and_missing_bytes_stale(migrated_db, tmp_roots):
    dsn = migrated_db
    tag = f"ctx08-{unique('t')}"
    seed = _seed(dsn, tag)
    ep = _observe(dsn, tag, seed)
    _set_episode(dsn, ep, explanations=[{"id": "e1", "text": "cause"}])
    _warranted_claim(dsn, tag, seed)
    receipt = _publish_bytes(dsn, tmp_roots, tag)
    vid, _ = _capability(dsn, tag, receipt["digest"])
    versions = {"candidate_version": vid}
    assert context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions=versions, purpose="base")).data[
            "outcome"] == "ready"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO quarantine_registry (version_id, reason)"
                        " VALUES (%s, %s)", (vid, "regression"))
            conn.commit()
    quarantined = context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions=versions, purpose="quarantined"))
    assert quarantined.data["outcome"] == "stale"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM quarantine_registry WHERE version_id = %s",
                        (vid,))
            conn.commit()
    artifacts.retire_artifact(dsn, _cmd(), receipt["digest"])
    retired = context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions=versions, purpose="retired"))
    assert retired.data["outcome"] == "stale"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE artifact_versions SET availability = 'available'"
                        " WHERE digest = %s", (receipt["digest"],))
            conn.commit()
    (tmp_roots["artifacts"] / receipt["digest"]).unlink()
    gone = context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions=versions, purpose="gone"),
        artifacts_root=tmp_roots["artifacts"])
    assert gone.data["outcome"] == "stale"
    artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], receipt)
    assert context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions=versions, purpose="restored"),
        artifacts_root=tmp_roots["artifacts"]).data["outcome"] == "ready"
    ghost = context.build_packet(dsn, _cmd(), decision=_decision(
        "construct", seed, ep, versions={"candidate_version": "cv-ghost"},
        purpose="ghost"))
    assert ghost.data["outcome"] == "stale"


def test_fresh_process_reconstructs_without_rebuild(migrated_db, tmp_path):
    dsn = migrated_db
    tag = f"ctx09-{unique('t')}"
    seed = _seed(dsn, tag)
    _, ep = _diagnose_ready(dsn, tag, seed)
    script = tmp_path / "build_packet_child.py"
    script.write_text(
        "import sys, time\n"
        "from settlement import context\n"
        "from settlement.common import Command\n"
        "dsn, iid, eid, req = sys.argv[1:5]\n"
        "decision = {'decision_kind': 'diagnose', 'purpose': 'fresh child',\n"
        "            'required_inputs': [], 'allowed_actions': ['read'],\n"
        "            'access': 'evaluator',\n"
        "            'budget': {'input_chars': 200000, 'output_reserve': 2000},\n"
        "            'current_versions': {}, 'investigation_id': iid,\n"
        "            'episode_id': eid}\n"
        "out = context.build_packet(dsn, Command(request_id=req, payload={}),\n"
        "                           decision=decision)\n"
        "print('BUILT ' + out.data['packet_id'] + ' ' + out.data['outcome'],\n"
        "      flush=True)\n"
        "time.sleep(60)\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
    child = subprocess.Popen(
        [sys.executable, str(script), dsn, seed["investigation_id"], ep,
         "ctxkill-1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        line = child.stdout.readline()
        assert line.startswith("BUILT pkt_ctxkill-1 ready"), line
    finally:
        child.kill()
        child.wait(timeout=30)
    assert child.returncode != 0
    loaded = context.load_packet(dsn, "pkt_ctxkill-1")
    assert loaded["rendered_digest"] == hashlib.sha256(
        loaded["rendered"].encode()).hexdigest()
    assert "[development_inputs]" in loaded["rendered"]
    assert context.revalidate_packet(dsn, "pkt_ctxkill-1")["valid"] is True
    with pytest.raises(SettlementError):
        context.load_packet(dsn, "pkt_missing")


def test_resume_carries_working_state(migrated_db, tmp_path):
    dsn = migrated_db
    tag = f"ctx10-{unique('t')}"
    seed = _seed(dsn, tag)
    _record(dsn, f"{tag}-done", seed["attempt_id"], "success", {"ok": True})
    prepared = store.prepare_operation(dsn, _pcmd(
        tag, {"operation_id": f"{tag}-op", "attempt_id": seed["attempt_id"],
              "allocation_id": seed["allocation_id"],
              "operation": {"kind": "infer"}}))
    assert prepared.code == ResultCode.APPLIED, prepared.detail
    dispatched = store.advance_dispatch(dsn, _pcmd(
        tag, {"operation_id": f"{tag}-op", "launcher_id": "L1",
              "ownership_generation": seed["generation"]}))
    assert dispatched.code == ResultCode.APPLIED, dispatched.detail
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family, invocation)"
                        " VALUES (%s, %s, %s)", (f"{tag}-cv", "f",
                                                 Json({"entry": "e"})))
            conn.commit()
    capabilities.pin_capability(dsn, seed["attempt_id"], f"{tag}-cv")
    roots = tmp_path / "artifacts"
    roots.mkdir()
    saved = context.save_continuation(
        dsn, _cmd(), roots, seed["investigation_id"],
        seed["attempt_id"], "comp-v1", {"node": 1}, [], [f"{tag}-op"],
        {"verify": f"{tag}-op"}, {"next": "verify"},
        ownership_generation=seed["generation"])
    assert saved.code == ResultCode.APPLIED
    result = context.build_packet(dsn, _cmd(), decision=_decision(
        "resume", seed, "", purpose="resume it"))
    assert result.data["outcome"] == "ready"
    content = result.data["mandatory_content"]
    assert {op["id"] for op in content["pending_operations"]["pending"]} >= {f"{tag}-op"}
    assert content["obligations"]["obligations"]["finish"] is True
    assert content["obligations"]["obligations"]["verify"] == f"{tag}-op"
    assert content["next_decision"]["next_decision"] == {"next": "verify"}
    assert content["objective"]["objective"].startswith("objective ")
    assert result.data["rendered"].count(f"{tag}-op") >= 2


def test_revalidate_catches_working_state_change(migrated_db):
    dsn = migrated_db
    tag = f"ctx11-{unique('t')}"
    seed = _seed(dsn, tag)
    result, _ = _diagnose_ready(dsn, tag, seed)
    assert context.revalidate_packet(dsn, result.data["packet_id"])["valid"] is True
    prepared = store.prepare_operation(dsn, _pcmd(
        tag, {"operation_id": f"{tag}-late", "attempt_id": seed["attempt_id"],
              "allocation_id": seed["allocation_id"],
              "operation": {"kind": "infer"}}))
    assert prepared.code == ResultCode.APPLIED, prepared.detail
    dispatched = store.advance_dispatch(dsn, _pcmd(
        tag, {"operation_id": f"{tag}-late", "launcher_id": "L1",
              "ownership_generation": seed["generation"]}))
    assert dispatched.code == ResultCode.APPLIED, dispatched.detail
    check = context.revalidate_packet(dsn, result.data["packet_id"])
    assert check["valid"] is False
    assert any("working state" in r for r in check["reasons"])


def test_operator_packet_region_is_inert(migrated_db):
    dsn = migrated_db
    tag = f"ctx12-{unique('t')}"
    seed = _seed(dsn, tag)
    evil = "<script>alert(1)</script>"
    result, _ = _diagnose_ready(dsn, tag, seed)
    assert result.data["outcome"] == "ready"
    view = overview_data(dsn)
    assert isinstance(view["packets"], list) and view["packets"]
    region = next(p for p in view["packets"]
                  if p["packet_id"] == result.data["packet_id"])
    assert region["decision_kind"] == "diagnose"
    assert region["policy_version"] == context.POLICY_VERSION
    assert set(region) >= {"packet_id", "decision_kind", "purpose", "outcome",
                           "policy_version", "source_versions",
                           "transform_versions", "qualifications",
                           "rendered_digest", "gaps", "next_action"}
    assert region["rendered_digest"] == result.data["rendered_digest"]
    assert region["next_action"] == "invoke through a bound operation"
    needy = context.build_packet(dsn, _cmd(), decision=_decision(
        "resume", seed, "", purpose=evil))
    assert needy.data["outcome"] == "needs_information"
    view = overview_data(dsn)
    region = next(p for p in view["packets"]
                  if p["packet_id"] == needy.data["packet_id"])
    assert region["purpose"] == evil
    assert region["next_action"].startswith("supply missing material: ")
    probe = Environment(autoescape=True).from_string("{{ purpose }}")
    rendered = probe.render(purpose=region["purpose"])
    assert evil not in rendered
    assert "&lt;script&gt;" in rendered
