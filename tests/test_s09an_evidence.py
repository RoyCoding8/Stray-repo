"""Lane J. M4's seven named rejecting examples, plus the structures that
make a rejection worth something: a recomputation that recomputes, a type
that separates a recomputed fact from a runtime-attested one, within-task
paired comparison, per-family rows a failed domain cannot be pooled out
of, and an accounting that refuses to divide across denominations.

A baseline that already fails cannot make a later rejection mean
anything, so every tamper test runs through `baseline()` and `rejected()`.
`rejected()` asserts the example's own problem, not just a failing
status, so a verifier that trips on something unrelated cannot pay for
the example.

M4's seven: doubled receipt inserted into live lineage, foreign study
identity, source substitution, disconnected policy, hidden-answer
contamination, absent usage treated as zero, resumed-count rollback.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (str(ROOT), str(ROOT / "src"), str(ROOT / "tests")):
    if path not in sys.path:
        sys.path.insert(0, path)

from test_m4_offline_recompute import (  # noqa: E402
    P1_SRC, P2_SRC, _digest, demo_bundle)
from experiments.ad01 import offline_recompute as M4  # noqa: E402
from experiments.ad01 import paired_results as pairs  # noqa: E402


def baseline() -> dict:
    bundle = demo_bundle()
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    return bundle


def rejected(bundle: dict, problem: str) -> list:
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail", (
        "the mutation was accepted: %s" % (result["problems"],))
    assert any(expected in actual for actual in result["problems"]
               for expected in problem.split("|")), result["problems"]
    return result["problems"]


def test_doubled_receipt_inserted_into_live_lineage_is_rejected():
    bundle = baseline()
    operation_id = "op-use-a-P0-u-sw-0"
    original = bundle["operations"][operation_id]["receipts"][0]
    doubled = copy.deepcopy(original)
    doubled["receipt_identity"] = doubled["receipt_identity"] + "-doubled"
    doubled_operation = operation_id + "-doubled"
    bundle["operations"][operation_id]["receipts"].append(doubled)
    bundle["operations"][doubled_operation] = {
        "operation_id": doubled_operation, "receipts": [doubled],
        "invocation": {"operation_id": doubled_operation,
                       "launcher": "test-double", "attempt": 1}}
    bundle["child_receipts"][doubled_operation] = doubled

    problems = rejected(
        bundle,
        "dispatch-operation-receipt-bijection|"
        "duplicate-receipt-identity|multiple-terminal-receipts|"
        "receipt-lineage-mismatch")

    assert any("duplicate-receipt-identity" in problem
               for problem in problems), problems


def test_foreign_study_identity_is_rejected():
    bundle = baseline()
    bundle["freeze"]["study_id"] = "a-study-that-never-ran"
    bundle["freeze"]["study_root"] = "a-study-that-never-ran"
    bundle["study_id"] = "a-study-that-never-ran"
    bundle["study_root"] = "a-study-that-never-ran"
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])

    rejected(bundle, "foreign-study-identity")


def test_bundle_naming_a_study_other_than_its_freeze_is_rejected():
    bundle = baseline()
    bundle["study"] = "a-study-that-never-ran"

    rejected(bundle, "bundle-study-mismatch")


def test_source_substitution_is_rejected():
    """An arm runs another arm's frozen bytes, with every binding rebound.

    The freeze, the construction record, the repertoire and the per-record
    policy digests all move together. Nothing in the bundle contradicts
    itself, so only the exclusivity of the source proves it.
    """
    bundle = baseline()
    substituted = P2_SRC
    digest = _digest(substituted)
    identity = bundle["freeze"]["policy_identities"]["P1"]
    identity["source"] = substituted
    identity["source_digest"] = digest
    identity["artifact"]["source_digest"] = digest
    bundle["construction"]["P1"]["policy_source"] = substituted
    bundle["construction"]["P1"]["source_digest"] = digest
    bundle["freeze"]["method_repertoires"]["P1"] = copy.deepcopy(
        bundle["freeze"]["method_repertoires"]["P2"])
    bundle["freeze"]["arm_contracts"]["P1"]["input_bindings"] = dict(
        bundle["freeze"]["arm_contracts"]["P2"]["input_bindings"])
    bundle["freeze"]["arm_contracts"]["P1"]["prompt_bindings"] = dict(
        bundle["freeze"]["arm_contracts"]["P2"]["prompt_bindings"])
    for record in bundle["use_records"]:
        if record["arm"] == "P1":
            record["policy_digest"] = digest
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])

    rejected(bundle, "source-shared-between-arms")


def test_disconnected_policy_is_rejected():
    bundle = baseline()
    for episode in bundle["assessment"]:
        episode["policy_digest"] = _digest(P2_SRC)

    rejected(bundle, "policy-digest-frozen-mismatch")


def test_hidden_answer_contamination_is_rejected():
    """The frozen policy source carries the answer table for held-out tasks.

    Every digest in the bundle is recomputed to match. The bytes alone
    condemn it.
    """
    bundle = baseline()
    contaminated = (
        P1_SRC + "\nTASK_ANSWERS = {'u-sw-0': 'reduce-3',"
        " 'u-gr-0': 'reduce-5'}\n")
    digest = _digest(contaminated)
    identity = bundle["freeze"]["policy_identities"]["P1"]
    identity["source"] = contaminated
    identity["source_digest"] = digest
    identity["artifact"]["source_digest"] = digest
    bundle["construction"]["P1"]["policy_source"] = contaminated
    bundle["construction"]["P1"]["source_digest"] = digest
    repertoire = bundle["freeze"]["method_repertoires"]["P1"]
    repertoire["members"].append({"method_source": contaminated,
                                  "source_digest": digest})
    repertoire["member_digests"].append(digest)
    for record in bundle["use_records"]:
        if record["arm"] == "P1":
            record["policy_digest"] = digest
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])

    rejected(bundle, "hidden-answer-contamination")


def test_absent_usage_treated_as_zero_is_rejected():
    """No receipt in the bundle reports usage, and the accounting claims a
    measured zero against a bare self-asserted baseline. The dispatches
    are untouched, so only the billing claim is at fault."""
    bundle = baseline()
    bundle["accounting"]["billed_units"] = {
        "measured": 0, "measurement_status": "measured",
        "source": "billing:zero-cost-baseline"}

    rejected(bundle, "billed-unknown-scored-as-zero")


def test_resumed_count_rollback_is_rejected():
    bundle = baseline()
    bundle["resume"] = {"resumed_at_dispatch": 13, "carried_calls": 0,
                        "source": "resume-counter"}

    rejected(bundle, "resume-count-rollback")


def test_a_resume_ledger_that_agrees_with_the_lineage_is_accepted():
    bundle = baseline()
    bundle["resume"] = {"resumed_at_dispatch": 13, "carried_calls": 13,
                        "source": "resume-counter"}

    result = M4.verify_bundle(bundle)

    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["resume"]["carried_calls"] == 13


def test_recomputation_responds_to_a_frozen_input_change():
    """Changing one frozen task's label changes the recomputed outcome.

    The stored `claimed_verdict` and the stored per-arm mean are left
    exactly as the bundle recorded them, and both are asserted still so.
    Anything that replayed the recorded number would still pass.
    """
    bundle = baseline()
    task_id = "u-gr-0"
    stored = bundle["freeze"]["tasks"][task_id]["expected"]
    before = dict(next(row for row in bundle["use_records"]
                       if row["task_id"] == task_id
                       and row["claimed_verdict"] == "preserved"))
    bundle["freeze"]["tasks"][task_id]["expected"] = "reduce-99"
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])

    result = M4.verify_bundle(bundle)

    after = next(row for row in bundle["use_records"]
                 if row["record_id"] == before["record_id"])
    assert after == before, "the stored record moved"
    assert M4._recomputed_quality(bundle["freeze"], after) == 0.0
    assert result["status"] == "fail"
    assert any(problem.startswith("quality-mismatch")
               for problem in result["problems"]), result["problems"]


def test_a_recomputed_count_is_a_recount_not_a_restatement():
    """Drop one episode's dispatch. The recount falls; the bundle's own
    claimed total does not, and the verifier sides with the recount."""
    bundle = baseline()
    dropped = "op-construct-P2-repair"
    del bundle["operations"][dropped]
    del bundle["child_receipts"][dropped]
    bundle["dispatch_ledger"] = [entry for entry in bundle["dispatch_ledger"]
                                 if entry["operation_id"] != dropped]
    bundle["construction"]["P2"]["operations"] = [
        "op-construct-P2-init"]
    bundle["freeze"]["dispatch_ledger"] = bundle["dispatch_ledger"]
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])
    bundle["accounting"]["model_dispatches"]["measured"] = 13

    result = M4.verify_bundle(bundle)

    assert result["recomputed"]["model_calls"] == 12
    assert result["status"] == "fail"
    assert any(problem.startswith("accounting-model_dispatches-mismatch")
               or problem.startswith("construction-dispatch-ledger-mismatch")
               for problem in result["problems"]), result["problems"]


def test_recomputed_and_attested_are_different_types():
    recomputed = pairs.Recomputed("13")
    attested = pairs.Attested(value=13, source="gateway-receipt")

    assert not isinstance(recomputed, pairs.Attested)
    assert not isinstance(attested, pairs.Recomputed)
    assert pairs.measurement_kind(recomputed) == pairs.RECOMPUTABLE
    assert pairs.measurement_kind(attested) == pairs.RUNTIME_ATTESTED


def test_an_attested_number_cannot_be_passed_off_as_a_recomputation():
    with pytest.raises(TypeError):
        pairs.Recomputed(pairs.Attested(
            value=13, source="gateway-receipt"))


def test_a_recomputation_cannot_carry_a_source():
    with pytest.raises(TypeError):
        pairs.Attested(value=13, source="gateway-receipt",
                       recomputable_from="operations")


def test_the_accounting_table_keeps_the_two_apart():
    bundle = baseline()
    accounting = M4.recomputed_accounting(bundle)

    for name in M4.RECOUNTABLE:
        assert isinstance(accounting[name], pairs.Recomputed), name
    for name in ("input_tokens", "output_tokens", "child_compute_ms",
                 "billed_units", "human_interventions"):
        assert not isinstance(accounting[name], pairs.Recomputed), name
        assert isinstance(accounting[name], pairs.Attested), name
        assert accounting[name].status in M4.MEASUREMENT_STATUSES
    assert accounting["billed_units"].value == "unknown"
    assert accounting["input_tokens"].value == "unknown"


def _scored(arm, family, task, value, lineage, unit="model-dispatches",
            cost=None):
    return pairs.Observation(
        arm=arm, family=family, task_id=task, quality=value,
        acquisition_lineage=lineage,
        cost=None if cost is None else pairs.Cost(value=cost, unit=unit))


def test_a_pair_is_two_conditions_on_the_same_task():
    rows = [_scored("P1", "boolean", "t1", 1.0, "l1"),
            _scored("P0", "boolean", "t1", 0.0, "l1")]

    pairs_ = pairs.paired(rows, treatment="P1", control="P0")

    assert len(pairs_) == 1
    assert pairs_[0].task_id == "t1"
    assert pairs_[0].delta == 1.0


def test_a_task_seen_by_one_condition_only_is_not_paired():
    rows = [_scored("P1", "boolean", "t1", 1.0, "l1"),
            _scored("P0", "boolean", "t2", 0.0, "l1")]

    assert pairs.paired(rows, treatment="P1", control="P0") == ()


def test_a_comparison_never_reads_a_cross_arm_mean():
    """Within-task only. Two conditions that never share a task compare to
    nothing rather than to each other's averages."""
    rows = [_scored("P1", "boolean", "t1", 1.0, "l1"),
            _scored("P1", "boolean", "t2", 1.0, "l1"),
            _scored("P0", "boolean", "t3", 0.0, "l1"),
            _scored("P0", "boolean", "t4", 0.0, "l1")]

    summary = pairs.summarize(rows, treatment="P1", control="P0")

    assert summary.pairs == ()
    assert summary.matched is False
    assert summary.mean_delta is None
    assert summary.families["boolean"].unmatched_tasks == (
        "t1", "t2", "t3", "t4")


def test_a_failed_domain_keeps_its_own_row():
    rows = [_scored("P1", "boolean", "t1", 1.0, "l1", cost=1),
            _scored("P0", "boolean", "t1", 1.0, "l1", cost=1),
            _scored("P1", "software", "s1", 0.0, "l2", cost=4),
            _scored("P0", "software", "s1", 0.0, "l2")]

    summary = pairs.summarize(rows, treatment="P1", control="P0")

    assert sorted(summary.families) == ["boolean", "software"]
    boolean = summary.families["boolean"]
    software = summary.families["software"]
    assert boolean.mean_delta == 0.0
    assert boolean.cost_ratio == 1.0
    assert software.mean_delta == 0.0
    assert software.tasks == 1
    assert boolean.tasks == 1
    assert summary.families["software"].cost_ratio is None, (
        "an uncosted control cannot be divided into a ratio")
    assert summary.unmatched_families == ()


def test_a_family_where_the_control_never_ran_is_not_pooled_away():
    rows = [_scored("P1", "boolean", "t1", 1.0, "l1"),
            _scored("P0", "boolean", "t1", 0.0, "l1"),
            _scored("P1", "software", "s1", 1.0, "l2"),
            _scored("P1", "software", "s2", 1.0, "l2")]

    summary = pairs.summarize(rows, treatment="P1", control="P0")

    assert summary.families["software"].matched is False
    assert summary.families["software"].mean_delta is None
    assert summary.families["software"].unmatched_tasks == ("s1", "s2")
    assert summary.families["boolean"].matched is True
    assert summary.unmatched_families == ("software",)


def test_the_distribution_across_lineages_is_reported_not_its_mean():
    rows = [_scored("P1", "boolean", "t1", 1.0, "north"),
            _scored("P0", "boolean", "t1", 0.0, "north"),
            _scored("P1", "boolean", "t2", 0.0, "south"),
            _scored("P0", "boolean", "t2", 0.0, "south"),
            _scored("P1", "boolean", "t3", 1.0, "south"),
            _scored("P0", "boolean", "t3", 1.0, "south")]

    summary = pairs.summarize(rows, treatment="P1", control="P0")

    assert summary.families["boolean"].by_lineage == {
        "north": (1.0, 1), "south": (0.0, 2)}
    assert summary.families["boolean"].mean_delta == 1 / 3


def test_an_unavailable_arm_is_classified_by_why():
    rows = [pairs.Failure(arm="P1", family="boolean", task_id="t1",
                           reason=pairs.CONSTRUCTION_FAILED,
                           detail="the response did not parse"),
            pairs.Failure(arm="P2", family="boolean", task_id="t1",
                          reason=pairs.PROVIDER_UNAVAILABLE,
                          detail="route refused"),
            pairs.Failure(arm="P1", family="software", task_id="s1",
                          reason=pairs.INELIGIBLE,
                          detail="no source-world artifact"),
            pairs.Failure(arm="P1", family="software", task_id="s2",
                          reason=pairs.CONTAMINATED,
                          detail="a hidden answer was in the source"),
            pairs.Failure(arm="P1", family="software", task_id="s3",
                          reason=pairs.EXECUTION_FAILED,
                          detail="the child returned a malformed record")]

    table = pairs.classify(rows)

    assert table[pairs.PROVIDER_UNAVAILABLE] == (("P2", "boolean", "t1"),)
    assert table[pairs.CONSTRUCTION_FAILED] == (("P1", "boolean", "t1"),)
    assert table[pairs.INELIGIBLE] == (("P1", "software", "s1"),)
    assert table[pairs.CONTAMINATED] == (("P1", "software", "s2"),)
    assert table[pairs.EXECUTION_FAILED] == (("P1", "software", "s3"),)
    assert len(table) == 5, "the reasons must not collapse into one bucket"


def test_an_unclassified_failure_is_refused():
    with pytest.raises(ValueError):
        pairs.Failure(arm="P1", family="boolean", task_id="t1",
                      reason="unavailable")


def test_a_failure_reason_cannot_be_scored():
    for reason in pairs.FAILURE_REASONS:
        with pytest.raises(ValueError):
            pairs.Failure(arm="P1", family="boolean", task_id="t1",
                          reason=reason, quality=0.0)


def test_an_unknown_cost_stays_unknown_through_the_pairing():
    unknown = pairs.Cost(value="unknown", unit="model-dispatches")
    measured = pairs.Cost(value=4, unit="model-dispatches")

    assert unknown.value == "unknown"
    assert measured.value == 4
    assert pairs.total([measured, unknown]).value == "unknown"
    assert pairs.total([measured, measured]).value == 8


def test_costs_in_different_denominations_cannot_be_added():
    dispatches = pairs.Cost(value=4, unit="model-dispatches")
    units = pairs.Cost(value=25, unit="reservation-units")

    with pytest.raises(ValueError):
        pairs.total([dispatches, units])


def test_a_ratio_against_an_unknown_denominator_is_refused():
    measured = pairs.Cost(value=8, unit="model-dispatches")
    unknown = pairs.Cost(value="unknown", unit="model-dispatches")

    assert pairs.ratio(measured, measured) == 1.0
    with pytest.raises(ValueError):
        pairs.ratio(measured, unknown)
    with pytest.raises(ValueError):
        pairs.ratio(measured, pairs.Cost(value=0, unit="model-dispatches"))


def test_reservations_and_dispatches_are_reported_apart():
    bundle = baseline()
    accounting = M4.recomputed_accounting(bundle)

    dispatches = pairs.total([pairs.Cost(
        value=int(accounting["model_dispatches"].value),
        unit=pairs.UNIT_MODEL_DISPATCHES)])
    assert dispatches.value == 13
    assert pairs.UNIT_MODEL_DISPATCHES != pairs.UNIT_RESERVATION_UNITS
    with pytest.raises(ValueError):
        pairs.ratio(
            pairs.Cost(value=25, unit=pairs.UNIT_RESERVATION_UNITS),
            dispatches)


def test_a_reservation_is_not_added_to_a_dispatch_count():
    bundle = baseline()
    accounting = M4.recomputed_accounting(bundle)

    with pytest.raises(ValueError):
        pairs.total([pairs.Cost(
            value=int(accounting["model_dispatches"].value),
            unit=pairs.UNIT_MODEL_DISPATCHES),
            pairs.Cost(value=25, unit=pairs.UNIT_RESERVATION_UNITS)])
