"""Characterize DEV-02 experiment seams. Two reviewed limitations (constructor with
no normal file interface; unreleased out-of-family binding invoked without a
router check) are fixed by DEVELOPMENT-02-LIVE and pinned here at the mock
level; real-DB gates live in tests/test_d02live_episode.py.

Production functions run with explicit persistence/effect doubles, without a DB,
provider, sandbox or candidate execution. These are not runtime integration tests.
"""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

from settlement import context, development, experiment
from settlement.common import Command, CommandResult, ResultCode, SettlementError


class Cursor:
    def __init__(self, packet=None, op=None):
        self.packet, self.op, self.queries, self.rowcount = packet, op, [], 1

    def execute(self, sql, args=()):
        self.queries.append((sql, args))

    def fetchone(self):
        sql = self.queries[-1][0]
        if "FROM context_packets" in sql:
            return self.packet
        if "FROM operations" in sql:
            return self.op if self.op is not None else {"payload": {"effect": "model-inference"}}
        return {"exists": 1}

    def fetchall(self):
        return []


def transact(cursor):
    def run(dsn, cmd, fn):
        code, detail, data, _, _ = fn(cursor, {})
        return CommandResult(code=code, detail=detail, data=data, request_id=cmd.request_id)
    return run


def state():
    return {"inv": {"objective": "Repair inclusive summation", "scope": {}},
            "ep": {"id": "episode", "trigger_refs": [{"task_id": "dev-sum", "family": "off_by_one"}],
                   "bottleneck": "off-by-one", "explanations": [{"cause": "exclusive endpoint"}],
                   "intervention": {"action": "construct a repair procedure"},
                   "candidates": [], "checks": [], "max_candidates": 2},
            "seen": [], "observations": [{"receipt_id": "obs-1", "attempt_id": "attempt",
                "content": {"task_id": "dev-sum", "outcome": "success", "grade_op": "grade-1"}}],
            "receipts": [{"operation_id": "infer-1", "outcome": "success", "content": {
                "text": "def sum_to(n): return sum(range(n+1))"}},
                {"operation_id": "grade-1", "outcome": "success", "content": {"passed": 3}}],
            "attempts": [], "cont": None, "pins": [], "allocs": [], "pending": [],
            "epoch": 1, "authority_version": 1}


def decision(kind="diagnose", budget=24000):
    return {"decision_kind": kind, "purpose": "diagnose the development failures",
            "access": "candidate", "budget": {"input_chars": budget, "output_reserve": 2000},
            "investigation_id": "investigation", "episode_id": "episode"}


def materialize(kind="diagnose", budget=24000, bundles=None, contract=None):
    request = decision(kind, budget)
    if contract:
        request["candidate_contract"] = contract
    claims = [{"id": "episode-exp-dev-sum-claim", "scope": {"episode": "episode"},
               "access_label": "candidate", "proposition": {"broken": "ORIGINAL_SOURCE_SENTINEL"}}]
    with patch.object(context, "_fetch_state", return_value=state()), \
            patch.object(context, "_visible_claims", return_value=claims), \
            patch.object(context.store, "transact", side_effect=transact(Cursor())):
        if bundles is None:
            return context.build_packet("double", Command(request_id="review"), decision=request).data
        with patch.object(context, "_settle_bundles", return_value=(bundles, [])):
            return context.build_packet("double", Command(request_id="review"), decision=request).data


def test_collected_claim_is_not_resolved_for_diagnosis():
    packet = materialize()
    assert packet["outcome"] == "ready"
    assert packet["evidence_bundles"] == []
    assert "ORIGINAL_SOURCE_SENTINEL" not in packet["rendered"]
    assert "def sum_to" in packet["rendered"]


def test_budget_overrun_keeps_counterexample_body_and_stages_gap():
    bundle = {"claim_id": "claim", "proposition": {"claim": "method covers integers"},
              "premise_content": [], "alternative_routes": [], "selected_route": None,
              "opposition": [{"id": "negative-input", "kind": "opposition", "status": "active",
                              "body": {"counterexample": "n=-1 returns wrong answer", "detail": "x" * 30000}}]}
    packet = materialize(bundles=[bundle])
    assert packet["outcome"] == "needs_information"
    assert "negative-input" in packet["rendered"]
    assert "n=-1 returns wrong answer" in packet["rendered"]
    assert not [o for o in packet["omissions"] if o["reason"] == "budget"]
    staged = next(g for g in packet["gaps"] if g["slot"] == "budget")
    assert "narrower" in staged["proposal"]


def _bound_packet_row(text):
    return {"outcome": "ready", "rendered": text,
            "rendered_digest": hashlib.sha256(text.encode()).hexdigest(),
            "mandatory_content": {}}


def test_packet_binding_records_input_digest_for_model_inference():
    cursor = Cursor(_bound_packet_row("required decision evidence"))
    with patch.object(context.store, "transact", side_effect=transact(cursor)):
        result = context.bind_packet_invocation("double", Command(), "packet", "unrelated-operation")
    assert result.code == ResultCode.APPLIED
    wire_in = json.dumps({"effect": "model-inference"}, sort_keys=True, separators=(",", ":"))
    assert result.data["input_digest"] == hashlib.sha256(wire_in.encode()).hexdigest()


def test_packet_binding_refuses_non_inference_operation():
    cursor = Cursor(_bound_packet_row("required decision evidence"),
                    op={"payload": {"effect": "sandbox-exec"}})
    with patch.object(context.store, "transact", side_effect=transact(cursor)):
        try:
            context.bind_packet_invocation("double", Command(), "packet", "sandbox-operation")
        except SettlementError as exc:
            assert "not model inference" in str(exc)
        else:
            raise AssertionError("non-inference binding was not refused")


def capture_construct_prompt(bundles=None):
    episode = {**state()["ep"], "state": "diagnosed", "comparison_exposed": False,
               "allocation_id": "allocation", "access_policy": {"families": ["off_by_one"]}}
    captured = {}

    class Captured(Exception):
        pass

    def make_packet(dsn, ep, kind, contract=None):
        captured["contract"] = contract
        return materialize(kind, bundles=bundles or [], contract=contract)

    def infer(dsn, adapter, **kwargs):
        captured["prompt"] = kwargs["prompt"]
        raise Captured()

    with patch.object(development, "_require_episode", return_value=episode), \
            patch.object(development, "_check_policy_scope"), \
            patch.object(development, "_packet_for", side_effect=make_packet), \
            patch.object(experiment, "_infer_via_broker", side_effect=infer):
        try:
            development.construct("double", Command(), None, SimpleNamespace(profile="local-uncontained"),
                                  episode_id="episode", model="requested-model", artifacts_root="unused",
                                  staging_root="unused", version_stem="candidate", family="off_by_one")
        except Captured:
            return captured
    raise AssertionError("constructor did not reach inference")


def test_constructor_declares_normal_file_interface():
    captured = capture_construct_prompt()
    invocation = captured["contract"]["invocation"]
    assert invocation["entry"] == "candidate.py"
    assert invocation["verify_args"] == ["--selftest"]
    assert invocation["invoke_args"] == ["<in-dir>/broken.py", "<out-dir>/fixed.py"]
    for key in ("reads", "writes", "selftest", "effects", "shape"):
        assert invocation[key]
    prompt = json.loads(captured["prompt"])
    assert prompt["file_abi"]["entry"] == "candidate.py"
    assert "fixed.py" in captured["prompt"]


def test_subsequent_use_refuses_unreleased_out_of_family_binding():
    candidate = {"id": "unreleased-candidate", "artifact_digest": "digest",
                 "applicability": {"family": "off_by_one"}}
    with patch.object(experiment, "_fresh_worker", return_value="attempt"), \
            patch.object(experiment.trials, "freeze_protocol"), \
            patch.object(experiment.evaluation, "propose_hidden_answer"), \
            patch.object(experiment, "_infer_via_broker",
                         return_value=("model-op", "fixed-text", {})), \
            patch.object(experiment.capabilities, "pin_capability") as pin, \
            patch.object(experiment.capabilities, "route") as route, \
            patch.object(experiment, "_invoke_method",
                         return_value=("fixed", "method")) as invoke, \
            patch.object(experiment, "begin_solver_grade",
                         return_value=({"status": "ok", "detail": "d"},
                                       "grade-op", None)), \
            patch.object(experiment, "finish_solver_grade",
                         return_value={"outcome": "success",
                                       "grade_class": "pass",
                                       "grade_detail": "d"}), \
            patch.object(experiment, "_settle_costs"), \
            patch.object(experiment.store, "restart_reconciliation", return_value={}), \
            patch.object(experiment.store, "transact", side_effect=transact(Cursor())):
        result = experiment.run_subsequent_use("double", artifacts_root="unused", launcher=None,
            adapter=None, model="unused", allocation_id="allocation", investigation_id="investigation",
            episode_id="episode", bindings={"version_id": candidate["id"]},
            use_task={"id": "transfer-task", "family": "wrong_operator", "broken": "broken", "cases": []},
            grader_path="unused", protocol_prefix="review", prior_exposure="transfer-comparison")
    assert result["method"] == "incumbent" and result["version_id"] == ""
    assert "unreleased" in result["reason"]
    assert result["disposition"] == {"released": {}, "router_policies": {}, "trial": False}
    invoke.assert_not_called()
    route.assert_not_called()
    pin.assert_not_called()
