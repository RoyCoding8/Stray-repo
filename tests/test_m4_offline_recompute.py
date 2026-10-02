"""M4 offline recomputation (E1/E2 prospective comparison).

Deterministic only: no gateway, no database, no network. Quality is
derived from frozen tasks plus observable behavior, never from runtime
verdict labels. Resource use is a runtime attestation named by its
declared source; unknown billing stays unknown, never zero.

TDD log: every tamper test below failed before
experiments/ad01/offline_recompute.py existed (collection error), then
passed against the implemented verifier. Each tamper class fails under
a distinct problem name so a masked check cannot hide behind another.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.ad01 import offline_recompute as M4

P0_SRC = ("def STEP(view, state):\n"
          "    return {'action': {'kind': 'diagnose', 'target': 't',"
          " 'inputs': {}, 'evidence_refs': [], 'requested_resources': {}},"
          " 'state': {}}\n")
P1_SRC = ("def STEP(view, state):\n"
          "    return {'action': {'kind': 'construct_method', 'target': 't',"
          " 'inputs': {'max_queries': 2}, 'evidence_refs': [],"
          " 'requested_resources': {'queries': 2}}, 'state': {}}\n")
P2_SRC = ("def STEP(view, state):\n"
          "    return {'action': {'kind': 'use_method', 'target': 't',"
          " 'inputs': {'method': 'm'}, 'evidence_refs': [],"
          " 'requested_resources': {}}, 'state': {}}\n")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _action(kind: str) -> dict:
    return {"kind": kind, "target": "t", "inputs": {},
            "evidence_refs": [], "requested_resources": {}}


def _op(op_id: str, settled: bool = True) -> dict:
    outcome = "success" if settled else "unknown"
    return {"receipts": [{"receipt_identity": "gw:%s" % op_id,
                          "outcome": outcome}],
            "invocation": {"operation_id": op_id, "launcher": "test-double",
                           "attempt": 1}}


def _tasks() -> dict:
    return {
        "d-sw-0": {"expected": "reduce-4"},
        "d-gr-0": {"expected": "reduce-6"},
        "u-sw-0": {"expected": "reduce-3"},
        "u-gr-0": {"expected": "reduce-5"},
        "x-sw-0": {"expected": "reduce-2"},
    }


def _freeze() -> dict:
    sources = {"P0": P0_SRC, "P1": P1_SRC, "P2": P2_SRC}
    identities = {}
    repertoires = {}
    for arm, source in sources.items():
        digest = _digest(source)
        identities[arm] = {
            "status": "available",
            "source": source,
            "source_digest": digest,
            "artifact": {"kind": "learning-policy",
                         "abi": "ad01-policy-step-v1",
                         "source_digest": digest},
            "history_tokens": 40 if arm == "P0" else 120,
            "failed_attempts": 0,
        }
        repertoires[arm] = {
            "members": [{"method_source": source,
                         "source_digest": digest}],
            "member_digests": [digest],
        }
    freeze = {
        "study_id": "invl02-m4-demo",
        "study_root": "invl02_m4",
        "arms": ["P0", "P1", "P2"],
        "order": ["P1", "P2"],
        "development": [{"episode_id": "d-sw-0", "task_id": "d-sw-0"},
                        {"episode_id": "d-gr-0", "task_id": "d-gr-0"}],
        "assessment": [{"episode_id": "a-0",
                        "use_tasks": ["u-sw-0", "u-gr-0"]}],
        "audit": [{"episode_id": "t-0", "use_tasks": ["x-sw-0"]}],
        "construction_allowance": M4.reserve_allowance(
            ["P1", "P2"], init=1, repair=1),
        "caps": {"per_episode": {"policy_steps": 6, "model_calls": 4},
                 "diagnostic_queries_per_episode": 8,
                 "study_model_calls": 20,
                 "history_token_ceiling": 10000},
        "metric_rule": {"kind": "mean-quality", "margin": 0.0,
                        "tie": "incumbent"},
        "resource_rule": {"kind": "ceiling",
                          "note": "quality under common ceilings"},
        "config": {"model": "test-double",
                   "instruments": ["diagnostic", "construct", "use"],
                   "abi": "ad01-policy-step-v1",
                   "artifact_kind": "learning-policy"},
        "policy_identities": identities,
        "method_repertoires": repertoires,
        "tasks": _tasks(),
    }
    freeze["freeze_digest"] = M4.freeze_digest(freeze)
    return freeze


def _episode(episode_id: str, arm: str, digest: str, op_id: str) -> dict:
    return {"episode_id": episode_id, "arm": arm,
            "policy_digest": digest,
            "policy_actions": [_action("diagnose")],
            "policy_steps": 1, "model_calls": 1, "witness_queries": 2,
            "history_tokens": 30, "failed_attempts": 0,
            "operations": [op_id]}


def demo_bundle() -> dict:
    freeze = _freeze()
    digests = {arm: _digest(source)
               for arm, source in (("P0", P0_SRC), ("P1", P1_SRC),
                                   ("P2", P2_SRC))}
    ops = {}
    for op_id in ("op-d-sw-0", "op-d-gr-0", "op-a-0", "op-t-0",
                  "op-construct-P1-init", "op-construct-P2-init",
                  "op-construct-P2-repair"):
        ops[op_id] = _op(op_id)
    observed = {
        ("P0", "u-sw-0"): "reduce-3", ("P0", "u-gr-0"): "other",
        ("P1", "u-sw-0"): "other", ("P1", "u-gr-0"): "other",
        ("P2", "u-sw-0"): "reduce-3", ("P2", "u-gr-0"): "reduce-5",
        ("P0", "x-sw-0"): "reduce-2", ("P1", "x-sw-0"): "other",
        ("P2", "x-sw-0"): "reduce-2",
    }
    records = []
    for (arm, task), output in sorted(observed.items()):
        rid = "a-%s-%s" % (arm, task) if task.startswith("u") else \
            "t-%s-%s" % (arm, task)
        op_id = "op-use-%s" % rid
        ops[op_id] = _op(op_id)
        expected = freeze["tasks"][task]["expected"]
        records.append({
            "record_id": rid, "arm": arm, "task_id": task,
            "executed": "candidate",
            "policy_digest": digests[arm],
            "executed_source_digest": digests[arm],
            "policy_artifact_kind": "learning-policy",
            "observed": output,
            "claimed_verdict": "preserved" if output == expected
                               else "failed",
            "costs": {"witness_queries": 1},
            "operation_ids": [op_id],
        })
    witness_use = len(records)
    bundle = {
        "freeze": freeze,
        "development": [_episode("d-sw-0", "P0", digests["P0"],
                                 "op-d-sw-0"),
                        _episode("d-gr-0", "P0", digests["P0"],
                                 "op-d-gr-0")],
        "construction": {
            "P1": {"status": "available", "policy_source": P1_SRC,
                   "source_digest": digests["P1"], "calls": 1,
                   "history_tokens": 120, "failed_attempts": 0,
                   "operations": ["op-construct-P1-init"]},
            "P2": {"status": "available", "policy_source": P2_SRC,
                   "source_digest": digests["P2"], "calls": 2,
                   "history_tokens": 200, "failed_attempts": 1,
                   "operations": ["op-construct-P2-init",
                                  "op-construct-P2-repair"]},
        },
        "assessment": [_episode("a-0", "P0", digests["P0"], "op-a-0")],
        "audit": [_episode("t-0", "P0", digests["P0"], "op-t-0")],
        "use_records": records,
        "operations": ops,
        "accounting": {
            "model_dispatches": {
                "measured": 7,
                "source": "runtime-attestation:test-builder"},
            "input_tokens": {"measured": "unknown",
                             "source": "unmeasured-offline"},
            "output_tokens": {"measured": "unknown",
                              "source": "unmeasured-offline"},
            "tool_queries": {
                "measured": 8 + witness_use,
                "source": "runtime-attestation:test-builder"},
            "child_compute_ms": {"measured": "unknown",
                                 "source": "unmeasured-offline"},
            "billed_units": {"measured": "unknown",
                             "source": "billing:unresolved-provider"},
            "unresolved_exposure": {
                "measured": 0,
                "source": "runtime-attestation:test-builder"},
            "human_interventions": {
                "measured": 0,
                "source": "runtime-attestation:test-builder"},
        },
        "claimed": {"winner": "P2",
                    "note": "assessment means P2 1.0 over P0 0.5, P1 0.0"},
    }
    return bundle


def test_offline_recompute_passes_without_gateway_or_db(monkeypatch):
    for name in list(__import__("os").environ):
        if name.startswith(("SETTLEMENT_", "GATEWAY_", "VERCEL_",
                            "AI_GATEWAY_")):
            monkeypatch.delenv(name, raising=False)
    bundle = demo_bundle()
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    recomputed = result["recomputed"]
    assert recomputed["model_calls"] == 7
    assert recomputed["history_tokens"] == 30 * 4 + 120 + 200
    assert recomputed["failed_attempts"] == 1
    assert recomputed["quality_by_arm"] == {"P0": 0.5, "P1": 0.0,
                                            "P2": 1.0}
    assert recomputed["comparison"]["winner"] == "P2"
    assert recomputed["comparison"]["status"] == "complete"
    source = Path(M4.__file__).read_text()
    imports = [line for line in source.splitlines()
               if line.startswith(("import ", "from "))]
    assert not any("gateway" in line or "psycopg" in line
                   or "settlement" in line or "urllib" in line
                   or "httpx" in line or "os" in line
                   for line in imports)
    assert "os.environ" not in source
    assert "SETTLEMENT_" not in source


def test_tamper_identity_fails():
    bundle = demo_bundle()
    bundle["freeze"]["policy_identities"]["P1"]["source"] = P2_SRC
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(
        bundle["freeze"])
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("identity-digest-mismatch P1")
               for p in result["problems"])


def test_tamper_content_fails():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P2-u-sw-0")
    record["observed"] = "forged-output"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("quality-mismatch a-P2-u-sw-0")
               for p in result["problems"])


def test_tamper_membership_fails():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P1-u-sw-0")
    record["task_id"] = "elsewhere-task"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("membership-unknown-task a-P1-u-sw-0")
               for p in result["problems"])


def test_tamper_costs_fails():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P2-u-gr-0")
    record["costs"]["witness_queries"] = 99
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("accounting-tool_queries-mismatch")
               for p in result["problems"])


def test_tamper_results_fails():
    bundle = demo_bundle()
    bundle["claimed"]["winner"] = "P1"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "comparison-verdict-mismatch" in result["problems"]


def test_swapped_candidate_is_refused():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P1-u-sw-0")
    record["executed_source_digest"] = _digest(P2_SRC)
    record["policy_digest"] = _digest(P2_SRC)
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("executed-source-not-frozen a-P1-u-sw-0")
               for p in result["problems"])


def test_disconnected_artifact_is_refused():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P2-u-sw-0")
    record["executed_source_digest"] = "f" * 64
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("executed-source-not-frozen a-P2-u-sw-0")
               for p in result["problems"])


def test_forged_witness_without_execution_is_refused():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P1-u-gr-0")
    record["observed"] = "reduce-5"
    record["claimed_verdict"] = "preserved"
    record["operation_ids"] = ["op-missing-forgery"]
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "missing-operation op-missing-forgery" in result["problems"]


def test_quota_reservation_reversed_order_same_allowance():
    forward = M4.reserve_allowance(["P1", "P2"], init=1, repair=1)
    reversed_ = M4.reserve_allowance(["P2", "P1"], init=1, repair=1)
    assert forward == reversed_
    assert forward["P1"] == forward["P2"] == {"init": 1, "repair": 1}
    bundle = demo_bundle()
    bundle["construction"]["P2"]["calls"] = 3
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "construction-ceiling-exceeded P2" in result["problems"]


def test_unavailable_arm_never_substituted():
    bundle = demo_bundle()
    freeze = bundle["freeze"]
    freeze["policy_identities"]["P1"] = {"status": "unavailable",
                                        "reason": "no settled response",
                                        "history_tokens": 60,
                                        "failed_attempts": 1}
    freeze["method_repertoires"]["P1"] = {"members": [],
                                          "member_digests": []}
    freeze["freeze_digest"] = M4.freeze_digest(freeze)
    bundle["construction"]["P1"] = {
        "status": "unavailable", "reason": "no settled response",
        "calls": 1, "history_tokens": 60, "failed_attempts": 1,
        "operations": ["op-construct-P1-init"]}
    for record in bundle["use_records"]:
        if record["arm"] != "P1":
            continue
        record.update({"executed": "incumbent", "observed": "baseline",
                       "claimed_verdict": "failed"})
        record.pop("policy_digest", None)
        record.pop("executed_source_digest", None)
    bundle["claimed"] = {"winner": "none",
                         "note": "P1 unavailable so no verdict"}
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["comparison"]["status"] == "incomplete"
    assert result["recomputed"]["comparison"]["missing_arms"] == ["P1"]
    assert result["recomputed"]["comparison"]["winner"] is None
    assert result["recomputed"]["quality_by_arm"]["P1"] is None
    cheating = copy.deepcopy(bundle)
    record = next(r for r in cheating["use_records"]
                  if r["record_id"] == "a-P1-u-sw-0")
    record.update({"executed": "candidate",
                   "executed_source_digest": _digest(P2_SRC),
                   "policy_digest": _digest(P2_SRC),
                   "policy_artifact_kind": "learning-policy"})
    refused = M4.verify_bundle(cheating)
    assert refused["status"] == "fail"
    assert any(p.startswith("substituted-baseline a-P1-u-sw-0")
               for p in refused["problems"])


def test_unknown_billing_stays_unknown_not_zero():
    bundle = demo_bundle()
    assert bundle["accounting"]["billed_units"]["measured"] == "unknown"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    scored = copy.deepcopy(bundle)
    scored["accounting"]["billed_units"]["measured"] = 0
    denied = M4.verify_bundle(scored)
    assert denied["status"] == "fail"
    assert "billed-unknown-scored-as-zero" in denied["problems"]


def test_bundle_round_trips_through_json_file(tmp_path):
    bundle = demo_bundle()
    path = tmp_path / "m4-bundle.json"
    path.write_text(json.dumps(bundle, sort_keys=True) + "\n")
    assert M4.verify_bundle_file(str(path))["status"] == "pass"
