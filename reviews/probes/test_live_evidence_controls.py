"""Reviewer controls: trusted fixture execution and doubled accounting boundary.

The accounting tests lock the EVID-02 contract: reporting reconciles with the
durable reservation debit, provider billing reads unknown unless verified, and
token usage stays separate. No live provider, model-generated candidate,
database or containment is exercised.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

from fault_tasks import BY_ID
from settlement import experiment


@pytest.mark.parametrize("fenced,passed", [(False, 3), (True, 0)])
def test_grader_distinguishes_correct_source_from_markdown(tmp_path, fenced, passed):
    task = BY_ID["panel-triangular"]
    code = task["fixed"]
    if fenced:
        code = "```python\n" + code + "```\n"
    candidate, cases = tmp_path / "candidate.py", tmp_path / "cases.json"
    candidate.write_text(code, encoding="utf-8")
    cases.write_text(json.dumps(task["cases"]), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "experiments/run_tests.py"),
                             str(candidate), str(cases), "10000"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    assert data["passed"] == passed and data["total"] == 3
    if fenced:
        assert all("SyntaxError" in x["actual"] for x in data["failures"])


def test_unbilled_receipt_reports_conservative_debit_with_unknown_billing():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"dispatch_state": "observed", "reservation_id": "r"},
                                  {"amount": 1000, "state": "settled"}]
    cursor.fetchall.return_value = [{"outcome": "success", "content": {"usage": {
        "charge_units": 0, "billed": False, "input_tokens": 10, "output_tokens": 20}}}]
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
    with patch.object(experiment.db, "connect", return_value=connection):
        result = experiment._op_accounting("double", "unbilled-model-op")
    assert result["reserved"] == 1000
    assert result["settled"] == 1000
    assert result["unresolved"] == 0
    assert result["billed"] is False
    assert result["provider_charge_units"] is None
    assert result["tokens"] == {"input": 10, "output": 20}


def test_billed_receipt_reports_verified_charge_exactly():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"dispatch_state": "observed", "reservation_id": "r"},
                                  {"amount": 1000, "state": "settled"}]
    cursor.fetchall.return_value = [{"outcome": "success", "content": {"usage": {
        "charge_units": 42, "billed": True, "input_tokens": 5, "output_tokens": 7}}}]
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
    with patch.object(experiment.db, "connect", return_value=connection):
        result = experiment._op_accounting("double", "billed-model-op")
    assert result["reserved"] == 1000
    assert result["settled"] == 42
    assert result["unresolved"] == 0
    assert result["billed"] is True
    assert result["provider_charge_units"] == 42
    assert result["tokens"] == {"input": 5, "output": 7}
