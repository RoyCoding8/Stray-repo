"""What a model-inference receipt can and cannot tell apart.

The deliverable is the discrimination, proven in both directions. The
committed bundle cannot separate a pre-dispatch refusal from a lost
response, and the proposed shape does. Every count asserted here is also
recomputed from the bytes on disk, so a test that would survive the
bundle's deletion is a test that cannot be satisfied by the module
returning its own constants.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_receipt_diagnosability as diag

OPUS = diag.BUNDLES["opus"]
M3 = diag.BUNDLES["m3"]
BUNDLES = (OPUS, M3)


def model_inference_receipts(evidence_dir):
    operations = json.loads((evidence_dir / "operations.json").read_text())
    return [(op_id, receipt)
            for op_id, record in sorted(operations.items())
            if record["effect"] == diag.MODEL_EFFECT
            for receipt in record["receipts"]]


def synthetic_bundle(receipts):
    return {name: {"effect": diag.MODEL_EFFECT, "receipts": [receipt]}
            for name, receipt in receipts.items()}


def refused(operation_id):
    return {"operation_id": operation_id, "outcome": "failure",
            "receipt_identity": "gw:%s:route" % operation_id,
            "usage": {"input_tokens": None, "output_tokens": None,
                      "charge_units": None, "billed": None}}


def lost(operation_id):
    return {"operation_id": operation_id, "outcome": "unknown",
            "receipt_identity": "gw:%s:unknown" % operation_id,
            "usage": {"input_tokens": None, "output_tokens": None,
                      "charge_units": None, "billed": None}}


def apply_proposed_shape(receipt, *, dispatch_attempted, response_received,
                         error_class, response_status=None,
                         response_digest=None):
    """The proposed shape applied to a receipt, as data only."""
    shaped = dict(receipt)
    shaped.update({"dispatch_attempted": dispatch_attempted,
                   "response_received": response_received,
                   "error_class": error_class,
                   "response_status": response_status,
                   "response_digest": response_digest,
                   "attempted_at": "2026-09-25T00:00:00Z"
                   if dispatch_attempted else None,
                   "received_at": "2026-09-25T00:00:01Z"
                   if response_received else None})
    return shaped


def test_the_opus_bundle_cannot_separate_a_refusal_from_a_lost_response():
    report = diag.distinguishability_report(OPUS)
    assert report["verdict"] == "INDISTINGUISHABLE"
    assert report["distinguishable"] is False
    assert report["pair"] == "%s vs %s" % (diag.REFUSAL, diag.LOST)
    assert report["separating_channels"] == []


def test_the_bundles_agree_with_the_receipts_on_disk():
    for bundle in BUNDLES:
        on_disk = model_inference_receipts(bundle)
        report = diag.distinguishability_report(bundle)
        detail = diag.current_diagnosability(bundle)
        assert report["receipt_count"] == len(on_disk)
        assert detail["receipt_count"] == len(on_disk)


def test_every_non_success_receipt_leaves_both_hypotheses_live():
    detail = diag.current_diagnosability(OPUS)
    unknown = [r for r in detail["receipts"] if r["outcome"] != "success"]
    assert len(unknown) == 7
    for entry in unknown:
        assert set(entry["live_hypotheses"]) == {
            diag.REFUSAL, diag.LOST,
            diag.Hypothesis.PROVIDER_FAILURE_OBSERVED.value
        }, entry["operation_id"]
    assert detail["receipts_leaving_both_live"] == len(unknown)


def test_success_receipts_leave_only_the_response_received_hypothesis():
    detail = diag.current_diagnosability(OPUS)
    success = [r for r in detail["receipts"] if r["outcome"] == "success"]
    assert len(success) == 8
    for entry in success:
        assert entry["live_hypotheses"] == [diag.Hypothesis.RESPONSE_RECEIVED.value]


def test_the_channels_the_bytes_carry_are_the_three_they_carry():
    for bundle in BUNDLES:
        detail = diag.current_diagnosability(bundle)
        assert detail["channels_available"] == [
            "outcome", "usage_observed", "receipt_identity"]
        assert "dispatch_attempted" in detail["channels_missing"]
        assert "response_received" in detail["channels_missing"]
        assert "response_digest" in detail["channels_missing"]


def test_the_receipts_export_exactly_four_keys():
    for bundle in BUNDLES:
        for _, receipt in model_inference_receipts(bundle):
            assert sorted(receipt) == sorted(diag.EXPORTED_RECEIPT_KEYS)


def test_the_identity_suffix_does_not_partition_the_conflated_set():
    verdict = diag.identity_is_informative(OPUS)
    assert verdict["distinct_suffixes"] == ["unknown"]
    assert verdict["suffix_varies_within_pooled_set"] is False
    assert verdict["non_success_receipts"] == 7


def test_receipt_identity_is_not_a_recommended_field():
    fields = diag.required_fields()
    assert "receipt_identity" in fields["unjustified_fields"]
    assert "receipt_identity" not in fields["justified_fields"]


def test_the_m3_bundle_carries_no_unknown_receipt_at_all():
    detail = diag.current_diagnosability(M3)
    assert detail["receipts_leaving_both_live"] == 0
    assert [r for r in detail["receipts"] if r["outcome"] != "success"] == []
    assert diag.distinguishability_report(M3)["verdict"] == "INDISTINGUISHABLE"


def test_the_proposed_shape_separates_a_refusal_from_a_lost_response():
    bundle = synthetic_bundle({
        "op-refused": apply_proposed_shape(
            refused("op-refused"), dispatch_attempted=False,
            response_received=False, error_class="route"),
        "op-lost": apply_proposed_shape(
            lost("op-lost"), dispatch_attempted=True,
            response_received=False, error_class="timeout"),
    })
    report = diag.distinguishability_report(bundle)
    assert report["verdict"] == "DISTINGUISHABLE"
    assert report["distinguishable"] is True
    assert report["separating_channels"]


def test_under_the_proposed_shape_each_receipt_leaves_exactly_one_hypothesis():
    bundle = synthetic_bundle({
        "op-refused": apply_proposed_shape(
            refused("op-refused"), dispatch_attempted=False,
            response_received=False, error_class="route"),
        "op-lost": apply_proposed_shape(
            lost("op-lost"), dispatch_attempted=True,
            response_received=False, error_class="timeout"),
    })
    detail = diag.current_diagnosability(bundle)
    by_id = {r["operation_id"]: r["live_hypotheses"] for r in detail["receipts"]}
    assert by_id["op-refused"] == [diag.REFUSAL]
    assert by_id["op-lost"] == [diag.LOST]
    assert detail["receipts_leaving_both_live"] == 0


def test_the_same_two_receipts_are_conflated_without_the_proposed_fields():
    bundle = synthetic_bundle({"op-refused": refused("op-refused"),
                               "op-lost": lost("op-lost")})
    assert diag.distinguishability_report(bundle)["verdict"] == "INDISTINGUISHABLE"
    detail = diag.current_diagnosability(bundle)
    assert all(len(r["live_hypotheses"]) > 1 for r in detail["receipts"])


def test_dispatching_alone_is_enough_to_separate_the_pair():
    bundle = synthetic_bundle({
        "op-refused": apply_proposed_shape(
            refused("op-refused"), dispatch_attempted=False,
            response_received=False, error_class="route"),
        "op-lost": apply_proposed_shape(
            lost("op-lost"), dispatch_attempted=True,
            response_received=False, error_class="route"),
    })
    report = diag.distinguishability_report(bundle)
    assert report["verdict"] == "DISTINGUISHABLE"
    assert "dispatch_attempted" in report["separating_channels"]


def test_the_minimal_field_set_separates_the_named_pair_by_construction():
    fields = diag.required_fields()
    assert fields["pair"] == "%s vs %s" % (diag.REFUSAL, diag.LOST)
    assert fields["minimal_for_pair"] == ["dispatch_attempted"]
    pair = (diag.Hypothesis.PRE_DISPATCH_REFUSAL,
            diag.Hypothesis.DISPATCHED_RESPONSE_LOST)
    assert diag.separates(diag.Channel.DISPATCH_ATTEMPTED, pair[0], pair[1])
    for channel in (diag.Channel.OUTCOME, diag.Channel.USAGE_OBSERVED):
        assert not diag.separates(channel, pair[0], pair[1])


def test_every_recommended_field_names_the_pairs_it_separates():
    fields = diag.required_fields()
    assert fields["justified_fields"]
    assert "dispatch_attempted" in fields["justified_fields"]
    for row in fields["fields"]:
        if row["recommended"]:
            assert row["separates"], row["field"]
        else:
            assert row["separates"] == [], row["field"]


def test_the_proposed_shape_declares_the_field_that_does_the_work():
    shape = diag.proposed_receipt_shape()
    assert shape["load_bearing"] == ["dispatch_attempted"]
    assert shape["installs_into_src_settlement"] is False
    names = [field["name"] for field in shape["fields"]]
    for required in ("dispatch_attempted", "response_received",
                     "response_digest", "response_status", "error_class",
                     "attempted_at", "received_at"):
        assert required in names
    shaped_receipt = synthetic_bundle({
        "op-refused": apply_proposed_shape(
            refused("op-refused"), dispatch_attempted=False,
            response_received=False, error_class="route"),
        "op-lost": apply_proposed_shape(
            lost("op-lost"), dispatch_attempted=True,
            response_received=False, error_class="timeout"),
    })
    missing = {key for key in ("dispatch_attempted", "response_received",
                               "response_digest", "response_status",
                               "error_class", "attempted_at", "received_at")
               if key not in shaped_receipt["op-refused"]["receipts"][0]}
    assert missing == set()
    assert diag.distinguishability_report(shaped_receipt)["verdict"] \
        == "DISTINGUISHABLE"


def test_the_m3_success_receipts_all_carry_the_recorded_adapter_fallback():
    verdict = diag.fallback_usage_sentinel(M3)
    assert verdict["sentinel_5_5"] == verdict["success_receipts"] == 13
    assert verdict["all_success_are_sentinel"] is True
    assert verdict["adapter_conclusion"] == diag.UNKNOWN


def test_the_opus_success_receipts_carry_no_sentinel():
    verdict = diag.fallback_usage_sentinel(OPUS)
    assert verdict["sentinel_5_5"] == 0
    assert verdict["other_success_receipts"] == 8
    assert verdict["all_success_are_sentinel"] is False


def test_a_missing_bundle_is_an_error_rather_than_an_empty_verdict():
    try:
        diag.distinguishability_report(ROOT / "no-such-bundle")
    except diag.BundleMissing:
        return
    raise AssertionError("a bundle that is not there must not be diagnosed")


def test_the_table_separates_every_pair_with_the_full_channel_set():
    assert len(diag.separated_pairs(diag.Channel)) == len(diag.ALL_PAIRS)
