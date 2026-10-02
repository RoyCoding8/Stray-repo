"""The recorded live-acquisition negative, recomputed from committed bytes.

The three-way answer is the point: harness artifact, genuine capability
result, or undecidable. Two of those are claims the evidence must earn,
so each is pinned here against the committed evidence rather than against
a number typed into a test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_acquisition_audit as audit


def test_the_census_is_recomputed_and_matches_the_records():
    counts = audit.census()
    assert counts["record_count"] == 24
    assert counts["executed"] == 4
    assert counts["unavailable"] + counts["preserved"] == 24
    assert counts["by_domain"]["software"]["preserved"] == 4
    assert counts["by_domain"]["graph"]["preserved"] == 4
    assert counts["by_arm"]["P1"]["unavailable"] == 8
    assert counts["by_arm"]["P2"]["unavailable"] == 8


def test_every_executed_record_names_exactly_the_bytes_it_ran():
    integrity = audit.digest_integrity()
    assert integrity["verified"] == 4
    assert not [entry for entry in integrity["unverifiable"]
                if "MISMATCH" in entry]
    assert counts_executed() == 4


def counts_executed():
    return audit.census()["executed"]


def test_all_four_executed_records_are_one_program():
    digests = audit.census()["executed_digests"]
    assert len(digests) == 1, digests


def test_no_record_shows_a_model_producing_a_policy():
    acquisition = audit.acquisition_possible()
    assert acquisition["count"] == 0
    assert acquisition["records_showing_model_acquisition"] == []


def test_the_missing_response_trace_is_outcome_unknown_with_null_usage():
    unknown = audit.unknown_outcome_operations()
    assert unknown["unknown"], "expected the missing-response operations"
    for entry in unknown["unknown"]:
        assert entry["outcome"] == "unknown"
        assert all(value is None for value in entry["usage"].values())


def test_the_receipts_cannot_distinguish_a_refusal_from_a_lost_response():
    """The reason the verdict is undecidable, pinned as a fact."""
    unknown = audit.unknown_outcome_operations()
    assert unknown["records_response_received"] is False
    assert unknown["records_response_digest"] is False


def test_the_verdict_is_undecidable_and_not_a_capability_claim():
    result = audit.verdict()
    assert result["outcome"] == audit.UNDECIDABLE
    assert result["acquisition"]["count"] == 0
    assert "void" in result["conclusion"]
    assert result["recorded_run_preceded_the_fix"] is True
    assert result["harness_fix_commit"] == "ca5aa74"


def test_the_freeze_digest_discrepancy_is_labelled_unverified():
    discrepancy = audit.freeze_digest_discrepancy()
    assert discrepancy["status"] == "UNVERIFIED"
    assert discrepancy["agree"] is False
    assert discrepancy["record_digests"]


def test_undecidable_is_a_reachable_outcome_not_a_dead_branch():
    """The three-way answer must be able to say any of the three things."""
    assert audit.HARNESS_ARTIFACT != audit.CAPABILITY_RESULT
    assert audit.CAPABILITY_RESULT != audit.UNDECIDABLE
    assert audit.HARNESS_ARTIFACT != audit.UNDECIDABLE
    assert audit.verdict()["outcome"] in (
        audit.HARNESS_ARTIFACT, audit.CAPABILITY_RESULT, audit.UNDECIDABLE)


def test_the_audit_reads_committed_bytes_not_its_own_constants():
    records = json.loads((audit.EVIDENCE / "use_records.json").read_text())
    assert audit.census()["record_count"] == len(records)
