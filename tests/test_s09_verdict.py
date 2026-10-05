"""The five M5 verdicts must be a function of bytes, not of prose.

The committed `evidence_s09_m3_live` bundle is the run under dispute. Its
own construction requests record the model as `recorded-double` while the
freeze pins a live route, and its use records persist the repertoire method
as the executed source while the arm-to-arm difference is attributed to a
policy wrapper that never hashed to those bytes. Every expected value below
was read off that bundle before these assertions were written, and each is a
literal, so a module that returned a constant would fail here.

The clean bundle is the discrimination test. A module that cannot tell this
one from the contaminated run cannot be the thing that reissues a verdict.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from experiments.ad01 import s09_verdict as verdict

REPO = Path(__file__).resolve().parents[1]
CONTAMINATED = REPO / "evidence_s09_m3_live"

LIVE_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
ACQUIRED_SOURCE = (
    "def STEP(view, state):\n"
    "    return {'action': {'kind': 'revise', 'target': 'x'}, 'state': {}}\n")
AUTHORED_SOURCE = (
    "def STEP(view, state):\n"
    "    return {'action': {'kind': 'stop', 'target': 'x'}, 'state': {}}\n")
ACQUIRED_DIGEST = verdict.sha256_text(ACQUIRED_SOURCE)
AUTHORED_DIGEST = verdict.sha256_text(AUTHORED_SOURCE)
CONSTRUCT_OPERATION = "ac1-ac1-I-01-b0-a1-acq-policy-policy-l1-init"

# The shape `live_construct.read_acquisition_evidence` returns for a live
# provider. `earned` is the field `Bundle.earned_origin` reads, and the
# route metadata beside it is what made the original verdict necessary: a
# recorded double can name any model it likes, so a model string alone was
# never evidence of anything.
_EARNED_EVIDENCE = {
    "operation_id": CONSTRUCT_OPERATION,
    "version": "invl02-acquisition-evidence-v1",
    "prompt_digest": "e" * 64,
    "requested_model": LIVE_MODEL,
    "receipt_identity": "gw:" + CONSTRUCT_OPERATION,
    "response_digest": "d" * 64,
    "route": {"model": LIVE_MODEL, "provider": "NVIDIA", "tier": "free"},
    "simulated": None,
    "earned": True,
    "reason": "live provider response",
}


def _record(arm, task, domain, source, policy_digest, initial, final,
            fallback=""):
    return {
        "study_arm": arm, "arm": arm, "task_id": task, "domain": domain,
        "executed_source": source,
        "executed_source_digest": verdict.sha256_text(source),
        "executed_policy_digest": policy_digest, "policy_digest": policy_digest,
        "initial_measure": initial, "final_measure": final,
        "normalized_reduction": (initial - final) / initial,
        "verdict": "preserved", "fallback_reason": fallback,
        "requested": "acquired" if arm == "A1" else "authored",
        "executed": "acquired" if arm == "A1" else "authored",
        "policy_actions": [{"kind": "development", "task_id": task}],
    }


def _receipt(operation_id, effect):
    return {
        "effect": effect,
        "receipts": [{"operation_id": operation_id, "outcome": "success",
                      "receipt_identity": "gw:" + operation_id,
                      "usage": {"input_tokens": 5, "output_tokens": 9}}],
    }


def write_clean_bundle(root: Path, requested_model=LIVE_MODEL,
                       pinned_model=LIVE_MODEL, use_records=None,
                       scopes=None, earned=True) -> Path:
    """`requested_model` and `pinned_model` are separate knobs because the
    leg under test is precisely whether the two agree.

    `earned` is the third knob, and it is the one that matters most. The
    freeze's `origin` is a claim, so the fixture has to be able to produce
    an arm that claims `model-acquired` with nothing behind it, which is the
    shape every real bundle in this repo has. Passing `earned=False` drops
    the construction record's acquisition evidence and the arm reads as a
    stand-in.
    """
    graph_op = "ac1-ac1-I-01-g-a1-acq-policy-s0-k0"
    authored_op = "ac1-ac1-I-02-a0-policy-s0-k0"
    operations = {
        CONSTRUCT_OPERATION: _receipt(CONSTRUCT_OPERATION,
                                      "model-inference"),
        graph_op: _receipt(graph_op, "sandbox-exec"),
        authored_op: _receipt(authored_op, "sandbox-exec"),
    }
    if use_records is None:
        use_records = [
            _record("A1", "t-sw-0", "software", ACQUIRED_SOURCE,
                    ACQUIRED_DIGEST, 8, 3),
            _record("A1", "t-gr-0", "graph", ACQUIRED_SOURCE,
                    ACQUIRED_DIGEST, 12, 3),
            _record("A0", "t-sw-0", "software", AUTHORED_SOURCE,
                    AUTHORED_DIGEST, 8, 4),
            _record("A0", "t-gr-0", "graph", AUTHORED_SOURCE,
                    AUTHORED_DIGEST, 12, 7),
        ]
    if scopes is None:
        scopes = {"A0": {"family": "software"}, "A1": {"family": "software"}}
    payload = {
        "freeze": {
            "freeze_digest": "f" * 64,
            "config": {"model": pinned_model},
            "metric_rule": {
                "quality": "preserved-verdict-plus-normalized-reduction",
                "scope": "sealed-use-tasks-only"},
            "policy_identities": {
                "A0": {"source": AUTHORED_SOURCE, "source_digest": AUTHORED_DIGEST,
                       "status": "available",
                       "artifact": {"origin": verdict.ORIGIN_AUTHORED,
                                    "applicability": scopes["A0"]}},
                "A1": {"source": ACQUIRED_SOURCE, "source_digest": ACQUIRED_DIGEST,
                       "status": "available",
                       "artifact": {"origin": verdict.ORIGIN_ACQUIRED,
                                    "applicability": scopes["A1"]}},
            },
        },
        "construction": {
            "A0": {"disposition": "authored", "status": "available",
                   "bound_digest": AUTHORED_DIGEST,
                   "candidate_digest": AUTHORED_DIGEST,
                   "source_digest": AUTHORED_DIGEST,
                   "policy_source": AUTHORED_SOURCE,
                   "construction_requests": []},
            "A1": {"disposition": "bound", "status": "available",
                   "bound_digest": ACQUIRED_DIGEST,
                   "candidate_digest": ACQUIRED_DIGEST,
                   "source_digest": ACQUIRED_DIGEST,
                   "policy_source": ACQUIRED_SOURCE,
                   "acquisition_evidence": _EARNED_EVIDENCE if earned else None,
                   "construction_requests": [{
                       "operation_id": CONSTRUCT_OPERATION, "model": requested_model,
                       "max_output_tokens": 2048, "reasoning_effort": "low"}]},
        },
        "operations": operations,
        "use_records": use_records,
        "accounting": {"dispatch_guard": {"pinned_model": pinned_model}},
        "assessment": [],
    }
    root.mkdir(parents=True, exist_ok=True)
    for name, data in payload.items():
        (root / (name + ".json")).write_text(json.dumps(data, indent=1))
    return root


def green_mechanism():
    return verdict.mechanism_verdict(REPO, {
        name: verdict.SuiteResult(test_file, 1, 0, 0, 0)
        for name, (_, test_file) in verdict.REPRESENTATION_BINDING.items()})


@pytest.fixture(scope="module")
def contaminated():
    return verdict.load_bundle(CONTAMINATED)


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    root = tmp_path_factory.mktemp("clean") / "bundle"
    return verdict.load_bundle(write_clean_bundle(root))



def test_contaminated_run_is_unproven_not_false_and_not_true(contaminated):
    acquisition = verdict.live_acquisition_verdict(contaminated)
    assert acquisition.value == 'unproven'
    assert acquisition.value != 'false'
    assert acquisition.value != 'true'


def test_contaminated_run_fails_on_the_provenance_it_actually_fails(contaminated):
    """The four provenance legs, plus the one the origin gate adds.

    `no_earned_acquired_arm` was not here before. P1 claims
    `model-acquired` in its own freeze and its construction record carries
    no acquisition evidence, so it is not an acquired arm and the legs that
    compare P1's executed bytes to a bound policy are answering a question
    about a stand-in. The leg names that, so a reader sees the demotion
    rather than a list of failures that all look incidental.
    """
    acquisition = verdict.live_acquisition_verdict(contaminated)
    assert acquisition.failing_legs == (
        "declared_model_matches_freeze",
        "executed_bytes_are_the_bound_policy",
        "dispatch_was_live_not_a_recording",
        "no_earned_acquired_arm",
    )
    assert acquisition.leg("bound_equals_candidate").status == verdict.LEG_PASS
    assert acquisition.leg("no_earned_acquired_arm").evidence == (
        "1 arm(s) claim origin 'model-acquired' and none earned it: P1 "
        "(claims 'model-acquired', reads 'fixture-stand-in': the construction "
        "record carries no acquisition evidence, so nothing shows a live "
        "provider wrote it)")
    assert acquisition.leg("declared_model_matches_freeze").evidence == (
        "the run pinned model 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free'"
        "; 1 of 1 construction requests persisted 'recorded-double', first on "
        "P1 (ad01-ad01-w0-I-54-b1-ad01-w0-dev-sw-00-policy-policy-l1-init)")
    assert acquisition.leg(
        "executed_bytes_are_the_bound_policy").evidence == (
        "over 4 executed records: P1 on ad01-w1-within-sw-00 hashes to "
        "3834317f66d4, bound policy is b71a7f8f39ad")
    assert acquisition.leg(
        "dispatch_was_live_not_a_recording").status == verdict.LEG_FAIL


def test_the_freeze_label_and_the_earned_origin_disagree_on_this_run(
        contaminated):
    """P1 is labelled acquired and is not. The two reads are kept apart.

    `arm_origin` is what the freeze claims. `earned_origin` is what the
    construction record supports. A test that only exercised the first
    would have passed against this bundle for the whole time it was in the
    repository.
    """
    assert contaminated.arm_origin("P1") == verdict.ORIGIN_ACQUIRED
    assert contaminated.earned_origin("P1") == verdict.ORIGIN_STAND_IN
    assert contaminated.arms_by_origin(verdict.ORIGIN_ACQUIRED) == ("P1",)
    assert contaminated.earned_arms_by_origin(verdict.ORIGIN_ACQUIRED) == ()
    assert contaminated.earned_arms_by_origin(
        verdict.ORIGIN_STAND_IN) == ("P1",)


def test_contaminated_utility_is_not_comparable_on_the_executed_digest(
        contaminated):
    utility = verdict.task_utility_verdict(contaminated)
    assert utility.value == 'not_comparable'
    comparability = utility.leg("arms_execute_their_own_bound_policy")
    assert comparability.status == verdict.LEG_FAIL
    assert "P0 executed source hashes to 3834317f66d4, its bound policy is " \
           "f92058cf6c04" in comparability.evidence
    assert "P1 executed source hashes" not in comparability.evidence, (
        "P1 is not an acquired arm, so the paired comparison must not count "
        "its executed bytes as the treatment side of the contrast")
    assert utility.leg("shared_tasks_present").evidence == (
        "acquired arms [], authored arms ['P0']; the freeze labels P1 "
        "'model-acquired' and its own construction record carries no "
        "evidence that a live provider wrote it")


def test_contaminated_transfer_excludes_every_fallback_graph_record(
        contaminated):
    transfer = verdict.transfer_verdict(contaminated)
    assert transfer.value == 'unproven'
    assert transfer.leg("software_scoped_policy_exists").evidence == (
        "no arm carries earned origin 'model-acquired'; the freeze labels P1 "
        "'model-acquired' and its own construction record carries no "
        "evidence that a live provider wrote it")


def test_contaminated_recursive_improvement_is_ineligible_with_m4s_reason(
        contaminated):
    recursive = verdict.recursive_improvement_verdict(contaminated)
    assert recursive.value == 'ineligible'
    assert recursive.value != 'false'
    assert 'ineligible' in verdict.ELIGIBILITY_RULE
    assert "not an improved improver" in verdict.ELIGIBILITY_RULE
    assert recursive.leg("an_acquired_policy_exists").evidence == (
        "no arm carries earned origin 'model-acquired'; the freeze labels P1 "
        "'model-acquired' and its own construction record carries no "
        "evidence that a live provider wrote it; M4 admits no other candidate")


def test_contaminated_run_does_not_decide_keep(contaminated):
    decision = verdict.issue(contaminated, green_mechanism())
    assert decision.outcome == 'prior-state'
    assert decision.outcome != 'keep'
    assert decision.rationale == (
        "the acquisition provenance gate is unsatisfied, so no acquisition "
        "or utility claim can be carried: declared_model_matches_freeze, "
        "executed_bytes_are_the_bound_policy, "
        "dispatch_was_live_not_a_recording, no_earned_acquired_arm",)



def test_clean_bundle_is_a_true_acquisition(clean):
    acquisition = verdict.live_acquisition_verdict(clean)
    assert acquisition.value == 'true'
    assert acquisition.failing_legs == ()
    for leg in acquisition.legs:
        assert leg.status == 'pass'
        assert leg.evidence


def test_clean_and_contaminated_acquisition_verdicts_differ(clean, contaminated):
    assert verdict.live_acquisition_verdict(clean).value == 'true'
    assert verdict.live_acquisition_verdict(contaminated).value == 'unproven'


def test_evidence_that_says_not_earned_is_read_as_not_earned(tmp_path):
    """`earned: false` is a refusal, and a check that ignores the flag misses it.

    This is the shape a recording double actually produces:
    `read_acquisition_evidence` returns a full record with `simulated` set
    and `earned` false, not a missing one. A gate that tested only whether
    evidence is present would read that as a live provider, and the check
    that exists to catch the double would pass it.
    """
    root = write_clean_bundle(tmp_path / "refused", earned=False)
    bundle = verdict.load_bundle(root)
    bundle = verdict.Bundle(
        root=bundle.root, freeze=bundle.freeze,
        construction={**bundle.construction,
                      "A1": {**bundle.construction["A1"],
                             "acquisition_evidence": {
                                 **_EARNED_EVIDENCE, "earned": False,
                                 "simulated": True,
                                 "reason": "response is marked simulated"}}},
        operations=bundle.operations, use_records=bundle.use_records,
        accounting=bundle.accounting, assessment=bundle.assessment)

    assert bundle.earned_origin("A1") == verdict.ORIGIN_STAND_IN
    assert verdict.live_acquisition_verdict(bundle).value == 'unproven'
    assert verdict.task_utility_verdict(bundle).value == 'not_comparable'
    assert "no evidence that a live provider wrote it" in \
        verdict.task_utility_verdict(bundle).leg(
            "shared_tasks_present").evidence


def test_an_earned_arm_and_a_demoted_one_are_different_arms(tmp_path, clean):
    """The check discriminates rather than refusing everything.

    A gate that returned `fixture-stand-in` for every claim would satisfy
    every test above. This one is the other direction: the same bundle
    shape, the only difference being the earned flag, has to produce a
    true acquisition verdict on one side and an unproven one on the other.
    """
    demoted = verdict.load_bundle(write_clean_bundle(
        tmp_path / "same-but-unearned", earned=False))

    assert verdict.live_acquisition_verdict(clean).value == 'true'
    assert verdict.live_acquisition_verdict(demoted).value == 'unproven'
    assert clean.arm_origin("A1") == demoted.arm_origin("A1"), (
        "the label is identical in both bundles, so the difference has to "
        "come from the evidence and nowhere else")
    assert clean.earned_origin("A1") == verdict.ORIGIN_ACQUIRED
    assert demoted.earned_origin("A1") == verdict.ORIGIN_STAND_IN


def test_clean_bundle_utility_transfer_and_decision(clean):
    assert verdict.task_utility_verdict(clean).value == 'win'
    transfer = verdict.transfer_verdict(clean)
    assert transfer.value == 'true'
    assert transfer.leg(
        "graph_execution_of_the_bound_policy").evidence == (
        "1 graph records executed the bound software-scoped policy: A1 on "
        "t-gr-0")
    decision = verdict.issue(clean, green_mechanism())
    assert decision.outcome == 'keep'


def test_a_recorded_double_construction_request_is_not_a_live_acquisition(
        tmp_path):
    root = write_clean_bundle(tmp_path / "recorded",
                              requested_model="recorded-double")
    acquisition = verdict.live_acquisition_verdict(verdict.load_bundle(root))
    assert acquisition.value == 'unproven'
    assert acquisition.failing_legs == (
        "declared_model_matches_freeze",
        "dispatch_was_live_not_a_recording",)
    assert "replayed recording" in acquisition.leg(
        "dispatch_was_live_not_a_recording").evidence


def test_a_request_naming_another_route_than_the_pin_is_not_live(
        tmp_path):
    root = write_clean_bundle(tmp_path / "rerouted",
                              requested_model="openrouter/some/other-model")
    acquisition = verdict.live_acquisition_verdict(verdict.load_bundle(root))
    assert acquisition.value == 'unproven'
    assert acquisition.failing_legs == ("declared_model_matches_freeze",)
    assert acquisition.leg(
        "dispatch_was_live_not_a_recording").status == 'pass'
    assert acquisition.leg("declared_model_matches_freeze").evidence == (
        "the run pinned model "
        "'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free'; 1 of 1 "
        "construction requests persisted 'openrouter/some/other-model', "
        "first on A1 (%s)" % CONSTRUCT_OPERATION)


def test_executed_bytes_that_are_not_the_bound_policy_block_the_claim(tmp_path):
    other = _record("A1", "t-sw-0", "software", AUTHORED_SOURCE,
                    ACQUIRED_DIGEST, 8, 3)
    root = write_clean_bundle(tmp_path / "swapped", use_records=[other])
    acquisition = verdict.live_acquisition_verdict(verdict.load_bundle(root))
    assert acquisition.value == 'unproven'
    assert acquisition.failing_legs == (
        "executed_bytes_are_the_bound_policy",)


def test_a_reused_receipt_identity_blocks_the_claim(tmp_path):
    root = write_clean_bundle(tmp_path / "reused")
    operations = json.loads((root / "operations.json").read_text())
    borrowed = next(key for key in operations if key != CONSTRUCT_OPERATION)
    operations[CONSTRUCT_OPERATION]["receipts"][0]["receipt_identity"] = (
        operations[borrowed]["receipts"][0]["receipt_identity"])
    (root / "operations.json").write_text(json.dumps(operations))
    assert operations[CONSTRUCT_OPERATION]["receipts"][0][
        "receipt_identity"] != ("gw:" + CONSTRUCT_OPERATION)
    acquisition = verdict.live_acquisition_verdict(verdict.load_bundle(root))
    assert acquisition.value == 'unproven'
    assert acquisition.failing_legs == (
        "dispatch_was_live_not_a_recording",)
    assert "carried by more than one operation" in acquisition.leg(
        "dispatch_was_live_not_a_recording").evidence



def test_a_fallback_graph_record_is_not_transfer_evidence_even_when_its_digest(
        tmp_path):
    records = [
        _record("A1", "t-sw-0", "software", ACQUIRED_SOURCE,
                ACQUIRED_DIGEST, 8, 3),
        _record("A1", "t-gr-0", "graph", ACQUIRED_SOURCE,
                ACQUIRED_DIGEST, 12, 3,
                fallback="arm-domain-uncovered: incumbent executed"),
        _record("A0", "t-sw-0", "software", AUTHORED_SOURCE,
                AUTHORED_DIGEST, 8, 4),
        _record("A0", "t-gr-0", "graph", AUTHORED_SOURCE,
                AUTHORED_DIGEST, 12, 7,
                fallback="no eligible repertoire member for graph"),
    ]
    root = write_clean_bundle(tmp_path / "covered", use_records=records)
    transfer = verdict.transfer_verdict(verdict.load_bundle(root))
    assert transfer.value == 'unproven'
    assert transfer.leg(
        "graph_execution_of_the_bound_policy").evidence == (
        "0 graph records executed the bound software-scoped policy: none")
    assert transfer.leg(
        "graph_records_served_without_fallback").evidence == (
        "0 of 1 graph records were served without a fallback; reasons: "
        "arm-domain-uncovered: incumbent executed")


def test_a_tie_is_a_tie_and_does_not_decide_keep(tmp_path, clean):
    tied = []
    for record in clean.use_records:
        clone = dict(record)
        if clone["study_arm"] == "A0":
            paired = next(other for other in clean.use_records
                          if other["study_arm"] == "A1"
                          and other["task_id"] == clone["task_id"])
            clone["final_measure"] = paired["final_measure"]
            clone["normalized_reduction"] = paired["normalized_reduction"]
        tied.append(clone)
    root = write_clean_bundle(tmp_path / "tie", use_records=tied)
    bundle = verdict.load_bundle(root)
    assert verdict.task_utility_verdict(bundle).value == 'tie'
    assert verdict.issue(bundle, green_mechanism()).outcome == 'simplify'


def test_a_loss_is_a_loss(tmp_path):
    worse = [
        _record("A1", "t-sw-0", "software", ACQUIRED_SOURCE,
                ACQUIRED_DIGEST, 8, 6),
        _record("A1", "t-gr-0", "graph", ACQUIRED_SOURCE,
                ACQUIRED_DIGEST, 12, 9),
        _record("A0", "t-sw-0", "software", AUTHORED_SOURCE,
                AUTHORED_DIGEST, 8, 1),
        _record("A0", "t-gr-0", "graph", AUTHORED_SOURCE,
                AUTHORED_DIGEST, 12, 3),
    ]
    root = write_clean_bundle(tmp_path / "loss", use_records=worse)
    bundle = verdict.load_bundle(root)
    assert verdict.task_utility_verdict(bundle).value == 'loss'
    assert verdict.issue(bundle, green_mechanism()).outcome == 'simplify'


def test_a_losing_run_produces_a_losing_decision_not_a_keep(tmp_path):
    worse = [
        _record("A1", "t-sw-0", "software", ACQUIRED_SOURCE,
                ACQUIRED_DIGEST, 8, 6),
        _record("A1", "t-gr-0", "graph", ACQUIRED_SOURCE,
                ACQUIRED_DIGEST, 12, 9),
        _record("A0", "t-sw-0", "software", AUTHORED_SOURCE,
                AUTHORED_DIGEST, 8, 1),
        _record("A0", "t-gr-0", "graph", AUTHORED_SOURCE,
                AUTHORED_DIGEST, 12, 3),
    ]
    root = write_clean_bundle(tmp_path / "losing", use_records=worse)
    bundle = verdict.load_bundle(root)
    assert verdict.live_acquisition_verdict(bundle).value == 'true'
    assert verdict.issue(bundle, green_mechanism()).outcome == 'simplify'


def test_a_failed_mechanism_suite_decides_replace(tmp_path):
    failing = {
        name: verdict.SuiteResult(test_file, 0, 1, 0, 1)
        for name, (_, test_file) in verdict.REPRESENTATION_BINDING.items()}
    mechanism = verdict.mechanism_verdict(REPO, failing)
    assert mechanism.value == 'unproven'
    root = write_clean_bundle(tmp_path / "replace")
    decision = verdict.issue(verdict.load_bundle(root), mechanism)
    assert decision.outcome == 'replace'


def test_mechanism_is_computed_from_suites_and_never_from_a_bundle(tmp_path):
    never_ran = {
        name: verdict.SuiteResult(test_file, 0, 0, 0, 5)
        for name, (_, test_file) in verdict.REPRESENTATION_BINDING.items()}
    assert verdict.mechanism_verdict(REPO, never_ran).value == 'unproven'
    green = green_mechanism()
    assert green.value == 'true'
    assert green.basis.source == verdict.BASIS_TESTS
    assert "a live bundle is not consulted" in green.basis.detail
    for leg in green.legs:
        assert leg.evidence


def test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run(
        contaminated):
    suites = {name: verdict.run_representation_suite(REPO, test_file)
              for name, (_, test_file) in verdict.REPRESENTATION_BINDING.items()}
    mechanism = verdict.mechanism_verdict(REPO, suites)
    assert mechanism.value == 'true'
    counts = {name: result.passed for name, result in suites.items()}
    assert counts["step"] == 10
    assert counts["policy_ast"] == 47
    assert counts["action_graph"] == 12
    decision = verdict.issue(contaminated, mechanism)
    assert decision.outcome == 'prior-state'


def test_a_verdict_with_no_basis_cannot_be_constructed():
    basis = verdict.Basis(source=verdict.BASIS_NONE, detail="nothing read")
    leg = verdict.Leg(name="x", role=verdict.REQUIRED,
                      status=verdict.LEG_PASS, evidence="read one byte")
    with pytest.raises(ValueError, match="unissuable"):
        verdict.Transfer(value=verdict.TRUE, legs=(leg,), basis=basis)
    with pytest.raises(ValueError, match="unissuable"):
        verdict.Mechanism(value=verdict.TRUE, legs=(leg,), basis=basis)
    assert verdict.Transfer(value=verdict.TRUE, legs=(leg,), basis=verdict.Basis(
        source=verdict.BASIS_BUNDLE, detail="x")).value == verdict.TRUE


def test_the_types_refuse_a_positive_verdict_with_a_failed_provenance_leg():
    failing = verdict.Leg(name="declared_model_matches_freeze",
                          role=verdict.REQUIRED, status=verdict.LEG_FAIL,
                          evidence="persisted 'recorded-double'")
    passing = verdict.Leg(name="bound_equals_candidate",
                          role=verdict.REQUIRED, status=verdict.LEG_PASS,
                          evidence="candidate=bound")
    basis = verdict.Basis(source=verdict.BASIS_BUNDLE, detail="the run")
    with pytest.raises(ValueError, match="cannot read true"):
        verdict.LiveAcquisition(value=verdict.TRUE, legs=(failing, passing),
                                basis=basis)
    with pytest.raises(ValueError, match="not false"):
        verdict.LiveAcquisition(value=verdict.FALSE, legs=(failing, passing),
                                basis=basis)
    assert verdict.LiveAcquisition(
        value=verdict.UNPROVEN, legs=(failing, passing),
        basis=basis).value == verdict.UNPROVEN


def test_the_decision_cannot_change_while_the_gate_is_unsatisfied(
        contaminated, clean):
    ruled = verdict.issue(contaminated, green_mechanism())
    assert ruled.verdicts.acquisition.value == 'unproven'
    for claimed in ('keep', 'simplify', 'replace'):
        with pytest.raises(ValueError, match="cannot change"):
            verdict.Decision(outcome=claimed, verdicts=ruled.verdicts,
                             rationale=("a hand-written acquisition claim",))
    verdict.Decision(outcome='prior-state', verdicts=ruled.verdicts,
                     rationale=("the gate is unsatisfied",))
    for outcome in ('keep', 'simplify', 'replace'):
        verdict.Decision(outcome=outcome,
                         verdicts=verdict.issue(
                             clean, green_mechanism()).verdicts,
                         rationale=("constructed from a clean bundle",))


def test_every_verdict_carries_its_basis_and_its_evidence(contaminated):
    for name, issued in verdict.issue(
            contaminated, green_mechanism()).verdicts.as_dict().items():
        assert issued.basis.source in ('bundle-and-receipts', 'test-results')
        assert issued.basis.detail
        assert issued.legs
        for leg in issued.legs:
            assert leg.evidence, "%s: %s carries no evidence" % (name, leg.name)
            assert leg.role in ('required', 'optional')
            assert leg.status in ('pass', 'fail', 'unknown')


def test_the_decision_rule_is_stated_on_the_decision(contaminated, clean):
    ruled = verdict.issue(contaminated, green_mechanism())
    assert ruled.rule == verdict.PROVENANCE_GATE
    assert verdict.TRUE in ruled.rule and verdict.UNPROVEN in ruled.rule
    assert verdict.KEEP in ruled.rule and verdict.SIMPLIFY in ruled.rule
    assert verdict.REPLACE in ruled.rule
    assert verdict.issue(clean, green_mechanism()).rule == verdict.PROVENANCE_GATE


# ---------------------------------------------------------------------------
# a repertoire arm's own members are its own bytes
# ---------------------------------------------------------------------------


def test_a_repertoire_arm_executes_a_member_and_that_is_its_own_policy(tmp_path):
    """The control arm binds four members and each record runs exactly one.

    `control_arm.policy_identities` writes `source_digest` over the
    concatenation of every member's source and `member_digests` as a map from
    capability id to the digest of that member. `run_use` executes one member
    per record, chosen by the selector. So a leg that compares a record's
    `executed_source` against the concatenation fails on all eighteen records
    of the one arm the comparison exists to make.

    This reads the real repertoire rather than a fixture, because the bug is
    in the relationship between two real shapes: a digest over a
    concatenation, and a record holding one member's bytes. A hand-built
    fixture could agree with the wrong half of it.

    It is the change that moved `task_utility` on `invl02_liveacq_r3` from
    `not_comparable` to a measured result with the r3 bytes alone.
    """
    from experiments.ad01 import control_arm

    repertoire = control_arm.control_repertoire("ad01-ctl")
    identities = control_arm.policy_identities("C", repertoire)
    members = repertoire["members"]
    assert len(members) > 1, "a one-member repertoire cannot express this"

    allowed = verdict._bound_digests(
        verdict.Bundle(root=tmp_path, freeze={"policy_identities": identities},
                       construction={}, operations={}, use_records=(),
                       accounting={}, assessment=()), "C")
    concatenated = identities["C"]["source_digest"]
    for member in members:
        digest = verdict.sha256_text(member["method_source"])
        assert digest in allowed, (
            "member %s executed source is not one of the arm's own bound "
            "digests" % member["capability_id"])
        assert digest != concatenated, (
            "this fixture no longer distinguishes a member from the whole "
            "repertoire, so it would pass against the defect too")

    records = [{"study_arm": "C", "task_id": "ad01-w0-within-sw-00",
                "executed_source": members[0]["method_source"],
                "executed": members[0]["capability_id"]}]
    bundle = verdict.Bundle(
        root=tmp_path, freeze={"policy_identities": identities},
        construction={}, operations={}, use_records=tuple(records),
        accounting={}, assessment=())
    leg = verdict._comparability_leg(bundle, (), ("C",))
    assert leg.status == verdict.LEG_PASS, leg.evidence


def test_a_record_outside_the_repertoire_still_fails_the_leg(tmp_path):
    """The widening is bounded by the arm's own members.

    The fix admits an arm's members, not any source. A record carrying bytes
    that are neither the arm's digest nor any member of it is the
    contamination the leg exists to catch, and
    `test_contaminated_utility_is_not_comparable_on_the_executed_digest`
    already holds that line for the single-source arms in the committed
    bundle. This is the same refusal for the repertoire shape.
    """
    from experiments.ad01 import control_arm

    identities = control_arm.policy_identities(
        "C", control_arm.control_repertoire("ad01-ctl"))
    stranger = ("def ENTRY(task, oracle, max_queries=16):\n"
                "    return {'candidate': None, 'queries': 0}\n")
    records = [{"study_arm": "C", "task_id": "ad01-w0-within-sw-00",
                "executed_source": stranger, "executed": "ctl-stranger"}]
    bundle = verdict.Bundle(
        root=tmp_path, freeze={"policy_identities": identities},
        construction={}, operations={}, use_records=tuple(records),
        accounting={}, assessment=())

    assert verdict.sha256_text(stranger) not in verdict._bound_digests(
        bundle, "C")
    leg = verdict._comparability_leg(bundle, (), ("C",))
    assert leg.status == verdict.LEG_FAIL


def test_a_nested_suite_run_does_not_claim_a_database(monkeypatch):
    """The nested run must not contend with its parent for the run token.

    `run_representation_suite` copies this process's environment into the
    child, which carries `S09ISO_TOKEN` with it. The child then asks the same
    database for the same per-token advisory lock this process is holding for
    the whole suite, and waits for it indefinitely. That is what stalled the
    `py3.12`, `py3.13`, `py3.134` and `py3.14` shards in runs 37261826154 and
    37277929945 while the other four finished, and the cancel is followed 24ms
    later by a `CREATE DATABASE` naming this job's own token returning "already
    exists".

    The child reads test files and needs no database, so the environment it is
    given says so. Reading the environment back out of the real function is what
    makes this a check on the child rather than a restatement of the constant:
    a test asserting only that `S09ISO_DISABLE` appears in this module would
    pass with the line commented out, since the docstring above would still
    name it.
    """
    captured: dict = {}

    def _capture(cmd, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "10 passed", "")

    monkeypatch.setattr(verdict.subprocess, "run", _capture)
    monkeypatch.setenv("S09ISO_TOKEN", "b3130000")

    verdict.run_representation_suite(REPO, "tests/test_x.py")

    assert captured["env"].get("S09ISO_DISABLE") == "1", (
        "the nested run would claim the parent's run token")
    # The parent's token is inherited and then made inert; the child must not
    # silently present a different one either, because that would still collide
    # with a sibling holding the same job token.
    assert captured["env"].get("S09ISO_TOKEN") == "b3130000"


def test_a_nested_suite_run_reports_a_hang_rather_than_waiting_forever(monkeypatch):
    """A nested run with no bound is invisible, so it gets one.

    pytest emits nothing at all about a test that never returns. The parent
    therefore waits until the job's own `timeout-minutes` kills it, and the run
    is recorded as `failure` rather than as a hang: nine of the last 25 runs hit
    exactly the 100-minute limit on the job owning this file, and every one of
    those nine reads as a failure. Nothing in the log distinguishes that from a
    slow suite.

    The bound is this call's, not the job's, and reaching it is a verdict input
    rather than a crash, so the caller still gets a `SuiteResult`.
    """
    def _hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(verdict.subprocess, "run", _hang)

    result = verdict.run_representation_suite(REPO, "tests/test_x.py")

    assert result.returncode == verdict.NESTED_SUITE_TIMEOUT_RC, (
        "a hung nested run must report the project's bound-reached status, "
        "not a status a passing child could produce")
    assert result.returncode not in (0, 1), (
        "0 or 1 would read as a verdict about the suite")
    assert (result.passed, result.failed, result.errored) == (0, 0, 0)

    # And the bound is passed down, rather than left to the job's timeout.
    captured: dict = {}

    def _capture(cmd, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, "3 passed", "")

    monkeypatch.setattr(verdict.subprocess, "run", _capture)
    verdict.run_representation_suite(REPO, "tests/test_x.py")
    assert captured["timeout"] == verdict.NESTED_SUITE_TIMEOUT_S
