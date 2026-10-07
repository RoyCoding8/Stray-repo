from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tests"))

from execution_authority import execution_store as make_execution_store  # noqa: E402


@pytest.fixture
def execution_store():
    with make_execution_store("ci-invc3study") as store:
        yield store


def test_cap_sheet_derived_from_runner_settings():
    import scripts.inv01_study as S
    sheet = S.build_cap_sheet()
    assert sheet["per_trajectory"]["max_boundaries"] == 6
    assert sheet["per_trajectory"]["max_dev_episodes"] == 3
    assert sheet["per_trajectory"]["max_lineages"] == 2
    assert sheet["per_trajectory"]["max_model_calls"] == 60
    assert sheet["study"]["max_construction_calls"] == 24
    assert sheet["study"]["max_model_calls"] == 360
    assert sheet["study"]["deadline_s"] > 0
    text = json.dumps(sheet, sort_keys=True)
    assert "characters/4" not in text
    assert sheet["derivation"]["token_estimate_kind"] == "estimated-budget"
    assert sheet["derivation"]["query_ceiling_source"] != "historical-average"
    assert sheet["accounting_kinds"] == [
        "estimate", "measured", "internal_charge", "provider_billing"]
    checked = S.check_caps_against_runner(sheet)
    assert checked["problems"] == [], checked


def test_study_budget_refuses_before_effects():
    import scripts.inv01_study as S
    sheet = S.build_cap_sheet()
    budget = S.StudyBudget(sheet, deadline_s=60)
    budget.spend(model_calls=360, construction_calls=24)
    refused = budget.admit(model_calls=1)
    assert refused["ok"] is False
    assert "budget" in refused["reason"] or "cap" in refused["reason"]
    assert budget.counts["model_calls"] == 360


def test_complete_study_on_recordings_with_recompute(tmp_path, execution_store):
    import scripts.inv01_study as S
    out = tmp_path / "study"
    dsn = execution_store["dsn"]
    rc = S.main(["--dsn", dsn, "--out", str(out),
                 "--agenda-authorized", "100000"])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["pilot"]["calibration_trajectories"] == 2
    assert manifest["pilot"]["comparison_trajectories"] == 4
    assert manifest["pilot"]["worlds"] == [1, 2]
    use_records = json.loads((out / "use_records.json").read_text())
    assert len(use_records) == 24
    for record in use_records:
        assert record["verdict"] in (
            "preserved", "not_preserved", "invalid", "unknown")
    caps = json.loads((out / "cap_sheet.json").read_text())
    assert caps["study"]["max_model_calls"] == 360
    accounting = json.loads((out / "accounting.json").read_text())
    assert accounting["total"]["model_calls"] <= 360
    assert accounting["total"]["construction_calls"] <= 24
    empty_path = out / "empty_use_records.json"
    assert empty_path.is_file()
    empty_records = json.loads(empty_path.read_text())
    assert empty_records
    empty_repertoire = json.loads(
        (out / "repertoires" / "empty.json").read_text())
    [incumbent] = empty_repertoire["members"]
    assert incumbent["source_digest"] == hashlib.sha256(
        incumbent["method_source"].encode("utf-8")).hexdigest()
    for record in empty_records:
        assert record["selected"] == record["executed"] == "incumbent"
        assert record["executed_source"] == incumbent["method_source"]
        assert record["policy_source_digest"]
        assert len(record["operation_ids"]) == 2
        assert record["costs"]["sandbox_ops"] == 2
        assert record["costs"]["witness_queries"] == 0
    accounting_baseline = json.loads(
        (out / "accounting.json").read_text())["incumbent_baseline"]
    assert accounting_baseline["records"] == len(empty_records)
    assert len(accounting_baseline["operation_ids"]) == 2 * len(empty_records)
    assert accounting_baseline["costs"]["sandbox_ops"] == 2 * len(empty_records)
    freeze = json.loads((out / "freeze.json").read_text())[
        "incumbent_baseline"]
    empty_repertoire_path = out / "repertoires" / "empty.json"
    empty_policy_path = out / "repertoires" / "empty-use-policy.py"
    assert freeze["repertoire"] == hashlib.sha256(
        empty_repertoire_path.read_bytes()).hexdigest()
    assert freeze["selector"] == hashlib.sha256(
        empty_policy_path.read_bytes()).hexdigest()
    assert all(record["policy_source_digest"] == freeze["selector"]
               for record in empty_records)
    baseline_export = json.loads(
        (out / "incumbent_baseline.json").read_text())
    assert sorted({op for record in baseline_export["records"]
                   for op in record["operation_ids"]}) == \
        accounting_baseline["operation_ids"]
    recomputed = tmp_path / "recomputed.json"
    rc = S.main(["--dsn", dsn, "--out", str(out), "--recompute",
                 "--recomputed-out", str(recomputed)])
    assert rc == 0
    fresh = json.loads(recomputed.read_text())
    assert fresh["total"] == accounting["total"]
    accounting_path = out / "accounting.json"
    original_accounting = accounting_path.read_text()
    tampered = json.loads(original_accounting)
    tampered["incumbent_baseline"]["operation_ids"][0] += "-tampered"
    accounting_path.write_text(json.dumps(tampered))
    assert S.main(["--dsn", dsn, "--out", str(out), "--recompute",
                   "--recomputed-out", str(recomputed)]) == 2
    tampered = json.loads(original_accounting)
    tampered["incumbent_baseline"]["costs"]["sandbox_ops"] += 1
    accounting_path.write_text(json.dumps(tampered))
    assert S.main(["--dsn", dsn, "--out", str(out), "--recompute",
                   "--recomputed-out", str(recomputed)]) == 2
    accounting_path.write_text(original_accounting)
    req = json.loads((out / "external_requirements.json").read_text())
    assert "endpoint_present" in req
    assert "key_present" in req
    assert "grant" in req
    assert req["endpoint_present"] in ("missing", "present")
    assert req["key_present"] in ("missing", "present")
    assert req["key_env"] == "SETTLEMENT_GATEWAY_KEY"
    for value in req.values():
        if isinstance(value, str):
            assert "sk-" not in value
