"""The S09-M2 rubric is frozen, deterministic, and refuses to guess."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import s09_m2_rubric as rubric

CASES = ("changed-actions-changed-outcome",
         "changed-actions-same-outcome",
         "same-actions-same-outcome")

ACQUIRED = "model-acquired"
DIGEST = "d" * 64


def _acquisition(attempt_id, provenance=ACQUIRED, clean=True,
                 digest=DIGEST):
    return rubric.AcquisitionRecord(
        attempt_id=attempt_id, provenance=provenance,
        response_digest="r" + digest, validated=clean, child_dry_run=clean,
        bound_digest=digest, executed_digest=digest)


def _arm(arm, representation, **over):
    base = dict(
        arm=arm, representation=representation,
        program_provenance=ACQUIRED, constructed_attempts=4,
        interface_contracts_passed=4, bound_digest=DIGEST,
        executed_digest=DIGEST, use_record_refs=("use-%s" % arm,),
        strategy_behaviors=10, executed_behaviors=10,
        behavior_evidence_refs=tuple("ev-%s-%d" % (arm, i) for i in range(10)),
        intervention_counts={name: 0 for name in
                             rubric.INTERVENTION_CATEGORIES},
        operations=20, model_dispatches=2, successes=2,
        checker_verdicts=("clean",),
        sensitivity_cases=(CASES[0],) * 5,
        acquisitions=tuple(_acquisition("a%d" % i) for i in range(4)),
    )
    base.update(over)
    return rubric.ArmEvidence(**base)


def _three_arms():
    return [_arm("A", "step", executed_behaviors=8,
                 behavior_evidence_refs=tuple("ev-a-%d" % i for i in range(8))),
            _arm("B", "policy_ast", intervention_counts=dict(
                host_authored_repair=0, authored_witness_after_model_failure=0,
                intervention_count=2, billed_units=0)),
            _arm("C", "action_graph")]


def test_the_five_required_axes_are_frozen_with_their_definitions():
    assert [axis.name for axis in rubric.AXES] == [
        "model_construction_success", "executable_coverage",
        "intervention_cost", "behavior_sensitivity", "search_efficiency"]

    for axis in rubric.AXES:
        assert axis.question and axis.numerator and axis.denominator
        assert axis.unit and axis.direction in (rubric.HIGHER, rubric.LOWER)
        assert axis.ineligible_reason
        assert axis.evidence_class in (rubric.ACQUIRED, rubric.WITNESS)


def test_construction_and_search_require_acquired_bytes_the_others_do_not():
    acquired = {axis.name for axis in rubric.AXES
                if axis.evidence_class == rubric.ACQUIRED}
    witness = {axis.name for axis in rubric.AXES
               if axis.evidence_class == rubric.WITNESS}

    assert acquired == {"model_construction_success", "search_efficiency"}
    assert witness == {"executable_coverage", "intervention_cost",
                       "behavior_sensitivity"}


def test_the_frozen_digest_covers_every_axis_definition():
    rubric.verify_frozen()

    assert rubric.FROZEN_DIGEST == hashlib.sha256(
        rubric.canonical(rubric.FROZEN_TABLE).encode("utf-8")).hexdigest()
    assert [entry["name"] for entry in rubric.FROZEN_TABLE["axes"]] == [
        axis.name for axis in rubric.AXES]


def test_editing_one_axis_definition_breaks_the_digest():
    edited = list(rubric.AXES)
    edited[1] = dataclasses.replace(
        rubric.AXES[1],
        denominator="whatever the arm felt like reporting")
    table = dict(rubric.FROZEN_TABLE)
    table["axes"] = [dict(entry) for entry in table["axes"]]
    table["axes"][1]["denominator"] = "whatever the arm felt like reporting"

    digest = hashlib.sha256(
        rubric.canonical(table).encode("utf-8")).hexdigest()

    assert edited[1].denominator != rubric.FROZEN_TABLE["axes"][1]["denominator"]
    assert digest != rubric.FROZEN_DIGEST


def test_reloading_the_module_does_not_change_the_digest():
    fresh = importlib.reload(rubric)

    assert fresh.FROZEN_DIGEST == rubric.FROZEN_DIGEST
    assert fresh.verify_frozen() is None


def test_an_authored_program_alone_cannot_claim_model_construction():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", program_provenance=rubric.WITNESS,
                 acquisitions=(), interface_contracts_passed=0),
            _arm("C", "action_graph", program_provenance=rubric.WITNESS,
                 acquisitions=(), interface_contracts_passed=0)]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Insufficient)
    assert set(verdict.reasons) == {"B", "C"}
    assert "mechanism witness" in verdict.reasons["B"]
    assert "search_efficiency" in verdict.reasons["C"]


def test_an_authored_witness_is_still_scored_on_the_axes_it_can_support():
    witness = _arm("B", "policy_ast", program_provenance=rubric.WITNESS,
                   acquisitions=(), interface_contracts_passed=0)

    records = {record.axis: record
               for record in (rubric.score_axis(witness, axis)
                              for axis in rubric.AXES)}

    assert records["model_construction_success"].is_measured is False
    assert records["model_construction_success"].insufficient_reason == (
        "arm is a mechanism witness: its program is a mechanism-witness "
        "artifact, not a model acquisition record")
    assert records["search_efficiency"].is_measured is False
    assert "resource efficiency is not a mechanism-witness claim" in \
        records["search_efficiency"].insufficient_reason
    assert records["executable_coverage"].is_measured is True
    assert records["intervention_cost"].is_measured is True
    assert records["behavior_sensitivity"].is_measured is True
    assert records["executable_coverage"].value == Fraction(1)


def test_a_witness_claim_measured_only_on_its_own_axes_is_a_refusal_not_a_win():
    """The two new arms cannot win by being scored on a friendlier scale."""
    authored = [_arm("B", "policy_ast", program_provenance=rubric.WITNESS,
                     acquisitions=(), interface_contracts_passed=0,
                     executed_behaviors=10, operations=0,
                     model_dispatches=0),
                _arm("C", "action_graph", program_provenance=rubric.WITNESS,
                     acquisitions=(), interface_contracts_passed=0)]

    verdict = rubric.select(authored)

    assert isinstance(verdict, rubric.Insufficient)
    assert not hasattr(verdict, "selected")


def test_bound_bytes_that_differ_from_executed_bytes_refuse_the_selection():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", executed_digest="e" * 64,
                 acquisitions=tuple(_acquisition("a%d" % i, digest="b" * 64)
                                    for i in range(4)))]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Insufficient)
    assert "bound-bytes-differ-from-executed-bytes" in verdict.reasons["B"]


def test_an_executed_behavior_without_a_use_record_is_not_coverage():
    arms = [_arm("A", "step"), _arm("B", "policy_ast", use_record_refs=())]

    verdict = rubric.select(arms)

    assert "executed-behaviors-without-a-use-record" in verdict.reasons["B"]


def test_a_policy_whose_bytes_do_not_bind_to_behavior_has_no_sensitivity():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast",
                 sensitivity_cases=(CASES[2],) * 6)]

    verdict = rubric.select(arms)

    assert "form does not bind its bytes" in verdict.reasons["B"]


def test_too_few_substitution_cases_refuse_rather_than_score_thinly():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast",
                 sensitivity_cases=(CASES[0],) * 4)]

    verdict = rubric.select(arms)

    assert "below the frozen panel minimum of 5" in verdict.reasons["B"]


def test_an_axis_with_no_checker_verdict_is_unmeasured_not_clean():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", checker_verdicts=())]

    verdict = rubric.select(arms)

    assert "no-checker-verdict" in verdict.reasons["B"]


def test_a_mixed_checker_verdict_cannot_read_as_a_clean_success():
    with pytest.raises(ValueError, match="partial checker run"):
        _arm("A", "step", checker_verdicts=("clean", "dirty"))


def test_no_clean_success_leaves_efficiency_undefined_not_worst():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", successes=0, operations=999)]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Insufficient)
    assert "undefined, not poor" in verdict.reasons["B"]


def test_an_intervention_with_no_executed_behavior_refuses_instead_of_scoring_zero():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", executed_behaviors=0,
                 behavior_evidence_refs=(), use_record_refs=(),
                 intervention_counts=dict(
                     host_authored_repair=3, authored_witness_after_model_failure=0,
                     intervention_count=0, billed_units=0))]

    verdict = rubric.select(arms)

    assert "interventions-charged-with-no-executed-behavior" in \
        verdict.reasons["B"]


def test_an_authored_repair_charged_to_an_acquired_program_breaks_parity():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", intervention_counts=dict(
                host_authored_repair=0, authored_witness_after_model_failure=1,
                intervention_count=0, billed_units=0))]

    verdict = rubric.select(arms)

    assert "arms are not separated" in verdict.reasons["B"]


def test_an_unrecorded_intervention_category_cannot_be_omitted():
    with pytest.raises(ValueError, match="intervention_counts is missing"):
        _arm("A", "step", intervention_counts={"intervention_count": 1})


def test_the_rule_selects_a_step_arm_that_wins_on_every_axis():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", constructed_attempts=4,
                 interface_contracts_passed=2,
                 acquisitions=tuple(
                     _acquisition("a%d" % i, clean=i < 2) for i in range(4)),
                 executed_behaviors=4, behavior_evidence_refs=tuple(
                     "ev-b-%d" % i for i in range(4)),
                 operations=40, model_dispatches=4),
            _arm("C", "action_graph", constructed_attempts=4,
                 interface_contracts_passed=2,
                 acquisitions=tuple(
                     _acquisition("a%d" % i, clean=i < 2) for i in range(4)),
                 executed_behaviors=4, behavior_evidence_refs=tuple(
                     "ev-c-%d" % i for i in range(4)),
                 operations=40, model_dispatches=4)]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Decision)
    assert verdict.selected == "A"
    assert verdict.margin_over_runner_up >= rubric.SELECTION_MARGIN
    assert {rejection.arm for rejection in verdict.rejections} == {"B", "C"}
    assert all(rejection.evidence for rejection in verdict.rejections)


def test_the_highest_construction_success_axis_gets_twice_the_coverage_weight():
    assert rubric.SELECTION_WEIGHTS["model_construction_success"] == \
        Fraction(1, 5)
    assert rubric.SELECTION_WEIGHTS["executable_coverage"] == Fraction(2, 5)
    assert rubric.SELECTION_WEIGHTS["search_efficiency"] == 0


def test_a_tie_inside_the_margin_is_refused_not_broken_by_hand():
    arms = [_arm("A", "step"), _arm("B", "policy_ast")]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Insufficient)
    assert {rejection.reason_code for rejection in verdict.rejected_arms} == {
        "tied-within-margin"}


def test_every_unselected_arm_has_a_machine_readable_reason():
    arms = [_arm("A", "step"),
            _arm("B", "policy_ast", successes=0),
            _arm("C", "action_graph", successes=0)]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Insufficient)
    assert set(verdict.reasons) == {"B", "C"}
    assert "undefined, not poor" in verdict.reasons["B"]
    assert "undefined, not poor" in verdict.reasons["C"]


def test_the_selection_is_deterministic_across_input_order():
    arms = _three_arms()
    forward = rubric.select(arms)
    backward = rubric.select(list(reversed(arms)))

    assert forward.selected == backward.selected
    assert forward.totals == backward.totals


def test_duplicate_arm_names_are_refused():
    with pytest.raises(ValueError, match="duplicate arm names"):
        rubric.select([_arm("A", "step"), _arm("A", "policy_ast")])


def test_an_arm_outside_the_three_representations_is_refused():
    with pytest.raises(ValueError, match="unknown representation"):
        rubric.select([_arm("A", "step"), _arm("B", "imperative-shell")])


def test_one_arm_alone_is_not_a_comparison():
    with pytest.raises(ValueError, match="at least two representations"):
        rubric.select([_arm("A", "step")])


def test_three_arms_on_identical_evidence_are_ranked_not_tied():
    arms = [_arm("A", "step", executed_behaviors=8,
                 behavior_evidence_refs=tuple("ev-a-%d" % i for i in range(8))),
            _arm("B", "policy_ast"),
            _arm("C", "action_graph", intervention_counts=dict(
                host_authored_repair=0, authored_witness_after_model_failure=0,
                intervention_count=2, billed_units=0))]

    verdict = rubric.select(arms)

    assert isinstance(verdict, rubric.Decision)
    assert verdict.selected == "B"
    assert verdict.totals["B"] > verdict.totals["A"] > verdict.totals["C"]
