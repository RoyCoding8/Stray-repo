"""Regression tests for the Team 01 live2 derived corrections (lane D).

Grounds the refusal / unavailable-evidence / unsettled-effect distinction
and the corrected panel accounting against the committed raw bundle.
Offline: reads tracked JSON only.
"""
from __future__ import annotations

import json
from pathlib import Path

from experiments.team01 import checker, closure2

EVIDENCE = Path(__file__).resolve().parent / "evidence-live2-panels"


def _bundle():
    return closure2.load_bundle(EVIDENCE)


def test_refused_cell_counts_zero_success_with_receipt_usage():
    bundle = _bundle()
    by_id = closure2.recon_by_id(bundle["recon"])
    cell = closure2.classify_cell(closure2.REFUSED_CELL,
                                  bundle["records"][closure2.REFUSED_CELL],
                                  by_id[closure2.REFUSED_CELL])
    assert cell["outcome_state"] == "refused"
    assert cell["solved"] is False
    assert cell["usage_corrected"] == {"in": 890, "out": 563}
    assert cell["evidence_state"] == "available"
    assert cell["effect_state"] == "settled"
    assert cell["accounting_agreement"] is False


def test_missing_record_is_unavailable_evidence_not_refusal():
    cell = closure2.classify_cell("live2-X-team01-t99-r9", None,
                                  {"usage_receipts": {"in": 0, "out": 0}})
    assert cell["evidence_state"] == "unavailable-evidence"
    assert cell["effect_state"] == "unsettled-effect"
    assert cell["solved"] is None


def test_missing_receipts_is_unsettled_effect():
    record = {"episode_id": "e1", "outcome": "success",
              "usage": {"in": 5, "out": 5}}
    detail = {"episode_id": "e1", "missing_receipts": ["gw:x"],
              "usage_receipts": {"in": 5, "out": 5}, "usage_ok": True,
              "allocation": {"balance": 10}, "alloc_ok": True}
    cell = closure2.classify_cell("e1", record, detail)
    assert cell["solved"] is True
    assert cell["evidence_state"] == "unavailable-evidence"
    assert cell["effect_state"] == "unsettled-effect"


def test_failed_allocation_is_unsettled_effect():
    record = {"episode_id": "e2", "outcome": "failure",
              "usage": {"in": 5, "out": 5}}
    detail = {"episode_id": "e2", "missing_receipts": [],
              "usage_receipts": {"in": 5, "out": 5}, "usage_ok": True,
              "allocation": {"balance": -3}, "alloc_ok": False}
    cell = closure2.classify_cell("e2", record, detail)
    assert cell["solved"] is False
    assert cell["evidence_state"] == "available"
    assert cell["effect_state"] == "unsettled-effect"


def test_corrected_eval_rule_completes_without_changing_decision():
    bundle = _bundle()
    by_id = closure2.recon_by_id(bundle["recon"])
    adjusted = closure2.corrected_rule_input(bundle["records"], by_id)
    rule = checker.finite_panel_rule(
        adjusted, dict(bundle["verdict"]["controls"]), "eval")
    assert rule["clauses"]["complete-records"] is True
    assert rule["clauses"]["beats-S"] is False
    assert rule["clauses"]["beats-P"] is True
    assert rule["promising"] is False
    assert rule["vectors"]["S"]["comparator_tokens"] == 95395
    assert rule["vectors"]["S"]["comparator_solves"] == 15


def test_corrected_transfer_rule_unchanged():
    bundle = _bundle()
    by_id = closure2.recon_by_id(bundle["recon"])
    adjusted = closure2.corrected_rule_input(bundle["records"], by_id)
    rule = checker.finite_panel_rule(
        adjusted, dict(bundle["verdict"]["controls"]), "transfer")
    assert rule["clauses"]["complete-records"] is True
    assert rule["promising"] is False


def test_raw_refusal_record_preserved():
    record = _bundle()["records"][closure2.REFUSED_CELL]
    assert record["outcome"] == "refused"
    assert record["usage"] == {"in": 0, "out": 0}


def test_calibration_probe_counts_against_stored_records():
    totals = closure2.compute_totals(_bundle())
    calibration = totals["groups"]["calibration"]
    assert calibration["count"] == 12
    assert calibration["success"] == 9
    assert calibration["failure"] == 3
    assert totals["groups"]["probe-template-validation"]["success"] == 1
    assert totals["groups"]["probe-continuity"]["success"] == 1
    assert totals["groups"]["eval"]["refused"] == 1
    assert totals["groups"]["transfer"]["success"] == 24


def test_campaign_union_adds_construction_to_episodes():
    totals = closure2.compute_totals(_bundle())
    assert totals["ledger_crosscheck"] is True
    episode = totals["episode_only"]
    assert (episode["model_calls"], episode["tool_calls"],
            episode["usage_in"], episode["usage_out"]) == (
                211, 135, 174881, 255342)
    construction = totals["construction"]
    assert (construction["usage_in"], construction["usage_out"]) == (
        1490, 1523)
    whole = totals["whole_campaign"]
    assert whole["op_identity_overlap"] == []
    assert whole["model_calls"] == 212
    assert whole["usage_in"] == 176371
    assert whole["usage_out"] == 256865


def test_template_labeled_advisory_with_unenforced_applies_when():
    label = closure2.template_label(
        json.loads((EVIDENCE / "template-frozen-live2.json").read_bytes()))
    assert label["version"] == "coordination-template/2"
    assert label["semantic_role"] == "advisory text"
    assert label["directive_chars"] == 1386
    assert label["applies_when"]["enforced"] is False
    solver_src = (Path(__file__).resolve().parent / "solver.py").read_text()
    assert "applies_when" not in solver_src
