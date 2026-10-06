"""Behavioural checks on the S09 doubles forensics.

The gate these protect is narrow. A forensic module that reports a verdict
it did not recompute is worse than no module, so every assertion here is
pinned to a literal value read out of the committed bundle or observed by
running the real `_call` against an isolated store. Deleting the evidence
bundle must fail these tests, not pass them.

The database survey is the one expensive section. It is marked so it can be
deselected when a reviewer only wants the bundle recomputation, and its
assertions are about what the survey actually is, not about a hoped-for hit.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.ad01 import s09_doubles_forensics as forensics

LIVE_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
DOUBLE_MODEL = "recorded-double"
BOUND_DIGEST = "b71a7f8f39ad1655555f0ac47ab2ab81321a78d98ac90f1079944fc626194706"
METHOD_DIGEST = "3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de66ea04c58685"
INIT_OPERATION = (
    "ad01-ad01-w0-I-54-b1-ad01-w0-dev-sw-00-policy-policy-l1-init")
EPISODE = "ad01-w0-I-54-b1-ad01-w0-dev-sw-00-policy"


def test_freeze_declares_live_and_request_persists_the_double():
    freeze = json.loads((forensics.EVIDENCE / "freeze.json").read_text())
    construction = json.loads(
        (forensics.EVIDENCE / "construction.json").read_text())
    request = construction["P1"]["construction_requests"][0]

    assert freeze["config"]["mode"] == "live"
    assert freeze["config"]["model"] == LIVE_MODEL
    assert request["model"] == DOUBLE_MODEL
    assert request["model"] != freeze["config"]["model"]


def test_saved_request_model_is_the_stores_model_not_the_calls_argument():
    origin = forensics.does_request_model_come_from_the_call_or_from_the_operation()

    assert origin["persisted_request_model"] == DOUBLE_MODEL
    assert origin["freeze_model"] == LIVE_MODEL
    assert origin["persisted_matches_freeze_model"] is False
    assert origin["reads_from"] == "operations.payload (durable store)"
    assert "request.get(\"model\"" in origin["model_read"]


def test_operation_identity_does_not_depend_on_model_or_mode():
    from experiments.ad01 import construct

    doubles = construct._policy_op_id(EPISODE, 1, "init")
    live = construct._policy_op_id(EPISODE, 1, "init")
    other_live = construct._policy_op_id(EPISODE, 1, "init")

    assert doubles == live == other_live == INIT_OPERATION

    identity = forensics.identity_independence()
    assert identity["rebuild_reproduces_persisted_id"] is True
    assert identity["rebuilt_ids"]["policy_init"] == INIT_OPERATION
    assert identity["model_is_a_free_input"] is False
    free = {name for builder in identity["builders"]
            for name in builder["free_inputs"]}
    assert "model" not in free
    assert "mode" not in free
    assert "study_root" not in free


def test_policy_fixture_is_the_bound_source():
    construction = json.loads(
        (forensics.EVIDENCE / "construction.json").read_text())
    p1 = construction["P1"]

    assert p1["policy_source"] == forensics._module_constant("P1_POLICY_SOURCE")[0]
    assert p1["bound_digest"] == BOUND_DIGEST
    assert p1["candidate_digest"] == BOUND_DIGEST


def test_call_reuses_a_settled_receipt_without_dispatching(tmp_path, monkeypatch):
    from experiments.ad01 import construct
    from settlement import broker
    from settlement.common import ResultCode

    dispatched: list[str] = []
    admitted: list[str] = []

    class _Result:
        code = ResultCode.APPLIED
        detail = ""

    def _ensure(dsn, *, operation_id, effect, payload, allocation_id, **kw):
        admitted.append(operation_id)
        return _Result()

    def _dispatch(dsn, operation_id, launchers=None, gateway=None):
        dispatched.append(operation_id)
        return {}

    monkeypatch.setattr(broker, "ensure_operation", _ensure)
    monkeypatch.setattr(broker, "dispatch_operation", _dispatch)
    monkeypatch.setattr(construct, "_settled_text",
                        lambda dsn, operation_id: "SETTLED-DOUBLE-TEXT")

    reused = construct._call(
        "postgresql:///unused", cid=EPISODE, lineage=1, attempt="init",
        prompt="ignored", budget={}, gateway=object(),
        model=LIVE_MODEL, allocation_id="alloc",
        operation_id=INIT_OPERATION)

    assert reused == {"operation_id": INIT_OPERATION,
                      "text": "SETTLED-DOUBLE-TEXT", "reused": True}
    assert admitted == []
    assert dispatched == []


def test_call_dispatches_and_reports_fresh_when_nothing_is_settled(
        tmp_path, monkeypatch):
    from experiments.ad01 import construct
    from settlement import broker
    from settlement.common import ResultCode

    dispatched: list[str] = []
    lookups: list[str] = []
    texts = iter([None, "FRESH-LIVE-TEXT"])

    class _Result:
        code = ResultCode.APPLIED
        detail = ""

    def _ensure(dsn, *, operation_id, effect, payload, allocation_id, **kw):
        assert payload["model"] == LIVE_MODEL
        return _Result()

    def _dispatch(dsn, operation_id, launchers=None, gateway=None):
        dispatched.append(operation_id)
        return {}

    def _settled(dsn, operation_id):
        lookups.append(operation_id)
        return next(texts)

    monkeypatch.setattr(broker, "ensure_operation", _ensure)
    monkeypatch.setattr(broker, "dispatch_operation", _dispatch)
    monkeypatch.setattr(construct, "_settled_text", _settled)

    fresh = construct._call(
        "postgresql:///unused", cid=EPISODE, lineage=1, attempt="init",
        prompt="ignored", budget={}, gateway=object(),
        model=LIVE_MODEL, allocation_id="alloc",
        operation_id=INIT_OPERATION)

    assert fresh == {"operation_id": INIT_OPERATION,
                     "text": "FRESH-LIVE-TEXT", "reused": False}
    assert dispatched == [INIT_OPERATION]
    assert lookups == [INIT_OPERATION, INIT_OPERATION]


def test_settled_lookup_appears_before_dispatch_in_the_committed_source():
    reuse = forensics.reuse_path()

    assert reuse["settled_lookup_precedes_dispatch"] is True
    assert reuse["returns_reused_true"] is True
    assert reuse["site"] == "experiments/ad01/construct.py:81"


def test_reuse_flag_does_not_survive_into_the_saved_candidate():
    construction = json.loads(
        (forensics.EVIDENCE / "construction.json").read_text())
    candidate = construction["P1"]["policy_candidate"]

    assert "reused" not in candidate
    assert "reused" not in (candidate.get("lineage") or {})
    assert candidate["lineage"]["calls_made"] == 1
    assert candidate["lineage"]["init_operation"] == INIT_OPERATION


def test_s09r02_executed_digest_is_the_authored_fixture_not_the_bound_policy():
    substitution = forensics.use_phase_digest_substitution()

    assert substitution["bound_digest"] == BOUND_DIGEST
    assert substitution["policy_source_digest"] == BOUND_DIGEST
    assert substitution["method_source_digest"] == METHOD_DIGEST
    assert substitution["p1_software_use_records"] == 4
    assert substitution["executed_digests_software_arm"] == [METHOD_DIGEST]
    assert substitution["executed_equals_method_source"] is True
    assert substitution["executed_equals_bound"] is False
    assert substitution["executed_equals_policy"] is False
    assert substitution["p1_use_records"] == 8


def test_only_the_software_p1_records_run_the_authored_fixture():
    records = json.loads(
        (forensics.EVIDENCE / "use_records.json").read_text())
    p1 = [r for r in records if r.get("arm") == "P1"]
    software = [r for r in p1 if "-sw-" in r["task_id"]]
    graph = [r for r in p1 if "-gr-" in r["task_id"]]

    assert len(software) == 4
    assert {r["executed_source_digest"] for r in software} == {METHOD_DIGEST}
    assert {r["executed_source_digest"] for r in graph} != {METHOD_DIGEST}
    assert {r["policy_digest"] for r in p1} == {BOUND_DIGEST}


def test_init_operation_carries_one_five_token_receipt():
    collision = forensics.double_then_live_collision()

    assert collision["id"] == INIT_OPERATION
    assert collision["one_receipt_only"] is True
    receipt = collision["receipts"][0]
    assert receipt["outcome"] == "success"
    assert receipt["usage"]["input_tokens"] == 5
    assert receipt["usage"]["output_tokens"] == 5
    assert collision["reuse_is_possible"] is True


def test_ledger_exposure_carries_both_reservations():
    exposure = forensics.ledger_exposure()
    by_reservation = {e["reservation"]: e for e in exposure["entries"]}

    assert exposure["total_unsettled_units"] == 5563
    assert exposure["r4_only_total"] == 2294
    assert exposure["understatement_if_r4_only"] == 3269
    assert by_reservation[
        "res-invl02-output-872608eb94c3-P1-audit-0023-a1"]["units"] == 2294
    assert by_reservation[
        "res-ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-"
        "construct-l1-init"]["units"] == 3269
    assert all(e["in_ledger"] for e in exposure["entries"])


def test_db_survey_reports_only_the_supplied_probe_rows():
    probe = {"database": "fixture", "has_operations": True,
             "earliest": "2100-01-01T00:00:00+00:00", "prefix_count": 2,
             "prefix_models": [DOUBLE_MODEL], "construction": ""}
    survey = forensics.db_survey([probe])

    assert survey["databases_with_operations_table"] > 0
    assert survey["read_only"] is True
    for hit in survey["prefix_hits"]:
        assert hit["matching_operations"] > 0
    later = [h for h in survey["prefix_hits"] if not h["predates_bundle"]]
    for hit in later:
        assert not forensics._predates(hit["earliest_operation"],
                                       survey["bundle_written_at"])


def test_no_store_predating_the_bundle_admitted_this_campaign_live(monkeypatch):
    monkeypatch.setattr(forensics, "_probe_all", lambda: [])
    admission = forensics.model_admission_evidence()
    survey = forensics.db_survey()

    assert admission["bundle_operation_ever_live"] is False
    assert survey["bundle_init_operation_in_a_store_predating_the_bundle"] is False
    for row in admission["live_model_rows"]:
        assert row["operation_id"] != INIT_OPERATION


def test_verdict_is_join_defect_confirmed_with_the_store_absent(monkeypatch):
    monkeypatch.setattr(forensics, "_probe_all", lambda: [])
    result = forensics.verdict()

    assert result["outcome"] == forensics.JOIN_DEFECT_CONFIRMED
    assert len(result["reasons"]) == 6
    assert "dsn" in result["unprovable_from_surviving_artifacts"]
    assert "inferred" in result["double_then_live_collision"]


def test_an_empty_survey_reports_no_operations_not_a_live_pass():
    survey = forensics.db_survey([])
    assert survey["databases_total"] == 0
    assert survey["databases_with_operations_table"] == 0
    assert survey["prefix_hits"] == []
    assert survey["bundle_init_operation_found_in_any_database"] is False
