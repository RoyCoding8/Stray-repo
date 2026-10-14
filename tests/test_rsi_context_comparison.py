from __future__ import annotations

import json
import os
import tempfile
from argparse import Namespace
from pathlib import Path

import pytest
from isolation_db import disposable_db

from experiments.context03 import driver, recompute
from settlement.common import SettlementError


def _args(dsn, tmp_path, policy, condition):
    return Namespace(
        dsn=dsn,
        run_root=tmp_path / "runs",
        evidence_root=tmp_path / "evidence",
        policy=policy,
        condition=condition,
        mode="fixture",
        route_envfile=None,
        codex_cmd=None,
    )


def _run_cell(dsn, tmp_path, policy, condition):
    path = driver.run_cell(_args(dsn, tmp_path, policy, condition))
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("operation", [
    {"id": "unknown", "settled": False},
    {"id": "unknown", "settled": True, "receipts": []},
    {"id": "unknown", "settled": True,
     "receipts": [{"operation_id": "unknown", "receipt_identity": "receipt", "tokens": None}]},
])
def test_unknown_receipt_usage_stays_unknown(operation):
    assert recompute._operation_usage(operation) == {
        "operation_id": "unknown", "tokens": None, "status": "unknown",
    }


def test_worker_usage_aggregator_does_not_sum_costs_or_other_operations():
    operations = [
        {"id": "worker", "settled": True, "receipts": [{
            "operation_id": "worker", "receipt_identity": "worker-receipt",
            "tokens": {"input_tokens": 10, "output_tokens": 2}, "actual_cost": 12,
        }]},
        {"id": "verifier", "settled": True, "receipts": [{
            "operation_id": "verifier", "receipt_identity": "verifier-receipt",
            "tokens": {"input_tokens": 0, "output_tokens": 3000}, "actual_cost": 3000,
        }]},
    ]
    summary = recompute._aggregate_worker_usage(operations, "worker")
    assert summary["recorded_tokens"] == 12
    assert summary["known_token_subtotal"] == 12
    assert summary["unknown_usage_operations"] == []
    assert not any("cost" in key for key in summary)


def test_frozen_nine_cell_fixture_comparison_recomputes_and_rejects_tampering():
    admin = os.environ.get("SETTLEMENT_TEST_DSN")
    if not admin:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    records = []
    with tempfile.TemporaryDirectory(prefix="p03-", dir=tempfile.gettempdir()) as root:
        short_root = Path(root)
        for policy, condition in driver.MATRIX:
            with disposable_db("p03ctx", admin_dsn=admin) as database:
                records.append(_run_cell(database.dsn, short_root, policy, condition))

    manifest = {"matrix": [list(item) for item in driver.MATRIX],
                "model_alias": "fixture:p03-context03/1"}
    result = recompute.recompute(manifest, records)
    assert result["matrix_cells"] == 9
    assert result["dispatched_workers"] == 6
    assert result["source_removal_refusals"] == 3
    assert result["structured_complete_baseline_pass"] is True
    assert result["claim_limit"].startswith("recorded outcomes")
    structured_distractor = next(
        item for item in records
        if item["policy"] == "structured/1" and item["condition"] == "misleading"
    )["child_inputs"][0]
    assert structured_distractor["saw_misleading_claim"] is True
    assert structured_distractor["rejected_misleading_claim_with_opposition"] is True
    assert structured_distractor["used_checked_empty_evidence"] is True

    missing = records[:-1]
    with pytest.raises(ValueError, match="matrix exports are incomplete"):
        recompute.recompute(manifest, missing)

    disconnected = json.loads(json.dumps(records))
    complete = next(item for item in disconnected
                    if item["condition"] == "complete" and item["policy"] == "structured/1")
    complete["invocation"]["connected"] = False
    with pytest.raises(ValueError, match="invocation digest chain"):
        recompute.recompute(manifest, disconnected)

    wrong_source = json.loads(json.dumps(records))
    wrong_source[0]["context_packet"]["memory_view"]["observations"].clear()
    with pytest.raises(ValueError, match="context packet digest mismatch"):
        recompute.recompute(manifest, wrong_source)

    unknown_usage = json.loads(json.dumps(records))
    live_like = next(item for item in unknown_usage
                     if item["condition"] == "complete" and item["policy"] == "structured/1")
    worker_id = live_like["invocation"]["operation_id"]
    worker_op = next(item for item in live_like["operations"] if item["id"] == worker_id)
    for receipt in worker_op["receipts"]:
        receipt["tokens"] = None
    live_like["invocation"]["receipts"] = worker_op["receipts"]
    unknown_result = recompute.recompute(manifest, unknown_usage)
    assert unknown_result["recorded_token_total"] is None
    assert worker_id in unknown_result["unknown_usage_operations"]
    assert next(item for item in unknown_result["cells"]
                if item["cell_id"] == live_like["cell_id"])["recorded_tokens"] is None


def test_comparison_cell_refuses_a_database_with_prior_investigations():
    admin = os.environ.get("SETTLEMENT_TEST_DSN")
    if not admin:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    with (
        tempfile.TemporaryDirectory(prefix="p03-", dir=tempfile.gettempdir()) as root,
        disposable_db("p03old", admin_dsn=admin) as database,
    ):
        _run_cell(database.dsn, Path(root), "structured/1", "complete")
        with pytest.raises(SettlementError, match="comparison database already contains investigations"):
            _run_cell(database.dsn, Path(root), "raw-history/1", "complete")
