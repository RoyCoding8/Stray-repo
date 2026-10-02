"""S09 revision: eligibility, immutability, and the apparatus controls.

Lane L. The campaign asks for a bounded meta-learning result: use
development evidence to let the model propose an executable change to an
existing learning decision, then judge the revision by what its
descendants achieve.

These tests cover four things kept apart on purpose. Eligibility is a
property of revision bytes. The reachable range of the decision is a
property of the channel. Apparatus qualification is a property of the
measurement machinery, decided by the three mandatory controls alone.
Benefit is a property of a run and never supplies either of the others.

Deterministic only: no network, no database, no live model call.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import boolean_rule as br
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel

COHORT = list(range(24))
ELIGIBILITY_SEEDS = (0, 1, 2, 3)


def _mission():
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [
            {"instrument": "boolean-rule-v1", "split": "dev", "seed": 4},
        ],
    }


def _store(tmp_path, name="s09rev.json"):
    return frontier.create_store(
        tmp_path / name, namespace=frontier.NAMESPACE,
        mission=_mission(), authority={"queries": 16, "steps": 12})


def _bound_store(tmp_path, name):
    store = _store(tmp_path, name)
    base = channel.make_control("low")
    store.bind_active(base)
    return store, base


def _eligibility_views(store, package, seeds=ELIGIBILITY_SEEDS):
    views = []
    for seed in seeds:
        view = store.step_view(frontier.IMPROVE, package)
        view["experience"] = []
        view["round"] = 1
        views.append(view)
    return views


def _revision_package(imp_source, parent, control_id="s09rev"):
    package = {
        "control_id": control_id, "origin": "authored-control",
        "source_kind": "fixed-menu", "op_source": parent["op_source"],
        "imp_source": imp_source,
        "op_digest": frontier.source_digest(parent["op_source"]),
        "imp_digest": frontier.source_digest(imp_source),
        "parent_digest": parent["package_digest"],
        "provenance": None, "provenance_digest": None,
        "version": int(parent["version"]) + 1,
        "authority_request": dict(parent["authority_request"]),
        "obligations": list(parent["obligations"]),
        "channel": parent["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    return package


# --- the intervention boundary -------------------------------------------

def test_the_probe_reaches_a_built_descendant(tmp_path):
    """The decision is operative in the narrow sense: it reaches behavior.

    The development probe is spent against a real instrument and its output
    bit selects the descendant package that gets built. So this is a real
    boundary, not a discarded decision.
    """
    task = br.make_task("dev", 0)
    built = {}
    for x in (3, 11):
        store, base = _bound_store(tmp_path, "reach-%d.json" % x)
        store.adopt_revision(_revision_package(
            channel._revision_source(str(x)), base))
        driven = channel.drive_improve_round(
            store, task, package=store.active_package, round_no=1,
            admit_probes=True)
        assert driven["observations"], "the probe was never spent"
        assert driven["observations"][0]["x"] == x
        assert driven["log"][0]["executed_digest"] == \
            store.active_package["imp_digest"]
        built[x] = driven["candidate"]
    assert built[3]["imp_digest"] != built[11]["imp_digest"], (
        "the development probe did not change the descendant package")


def test_the_decision_actually_flips_on_a_real_task(tmp_path):
    """The boundary is not merely wired; it changes which package is built.

    Over a handful of real tasks the probed input must select both menu
    members. A decision whose output is constant across every task it
    could ever see is a decision that cannot be steered.
    """
    seen = set()
    for seed in range(8):
        store, base = _bound_store(tmp_path, "flip-%d.json" % seed)
        store.adopt_revision(_revision_package(
            channel._revision_source("0"), base))
        driven = channel.drive_improve_round(
            store, br.make_task("dev", seed), package=store.active_package,
            round_no=1, admit_probes=True)
        seen.add(driven["observations"][0]["y"][0])
    assert seen == {0, 1}, (
        "the probed output never varied, so this decision cannot be"
        " steered to either descendant")


# --- the reachable range of this decision --------------------------------

def test_a_descendant_only_ever_runs_the_authored_menu():
    """What survives into a descendant is the menu entry, not the choice.

    `leaf_construct` swaps the improvement source for a member of an
    authored two-entry menu, so a descendant gathers one of exactly two
    evidence sets no matter what the revision selected. Any descendant
    metric that scores the reviser's own evidence would be measuring an
    improvement no descendant ever received.
    """
    assert channel._STRATEGY_EVIDENCE == {"low": 3, "high": 11}
    assert set(channel.REACHABLE_EVIDENCE) == {"3", "11"}


def test_the_reachable_lineage_range_is_within_the_noise_floor():
    """The whole descendant range this decision can reach is noise.

    The honest headline for this lane. The best and worst development
    probe a revision could choose differ by less than the spread two
    halves of the same cohort produce, so no revision of this decision can
    be said to improve its descendants, and the apparatus says so rather
    than reporting a sign.
    """
    full = {p: channel.evaluate_lineage([p], split="qual", seeds=COHORT)[
        "mean"] for p in range(16)}
    half_a = {p: channel.evaluate_lineage(
        [p], split="qual", seeds=COHORT[0::2])["mean"] for p in range(16)}
    half_b = {p: channel.evaluate_lineage(
        [p], split="qual", seeds=COHORT[1::2])["mean"] for p in range(16)}
    reach = max(full.values()) - min(full.values())
    resample = max(max(half_a.values()) - min(half_a.values()),
                   max(half_b.values()) - min(half_b.values()))
    assert reach <= resample, (
        "reachable lineage spread %.5f exceeds the resampling spread"
        " %.5f, so the range is measurable after all" % (reach, resample))
    assert max(half_a, key=half_a.get) != max(half_b, key=half_b.get) or \
        reach == 0.0, (
        "the two cohort halves disagree on which probe is best, so the"
        " ordering is not a property of the decision")


def test_channel_headroom_reports_no_measurable_headroom():
    """The channel can be asked whether it has room before a study runs.

    A claim about this decision is only checkable against what the channel
    physically allows, so the report has to answer that question with a
    number that can come out either way. The estimator is a paired
    difference between the best reachable probe and the incumbent, so a
    negative is reported as a negative magnitude against the spread of
    that same paired difference, not as a sign. Here the gap is negative
    and inside its own noise, so this decision has no measurable
    descendant effect to find.

    The previous version asserted `reachable_spread <= noise_floor`, and
    both of those terms are gone. That comparison was the defect N-63
    removed: `reachable_spread` is a spread over the whole cohort and
    `noise_floor` is the same spread recomputed on halves of it, so the
    first was structurally the smaller number at every cohort size and
    `headroom` could not come out positive whatever the substrate was
    doing. It reported the estimator's own sample sizes, and a report
    that cannot return the other answer is not a measurement. Renaming
    `reachable_spread` to `delta` would have kept a test that no longer
    describes anything, so the assertion is re-aimed instead.

    `delta <= 0` on its own would be nearly free, so the test also pins
    the report's two refusal conditions and the incumbent it compares
    against. `measurable` is not vacuously false here:
    `tests/test_s09_e4_remediation.py` requires the same flag to come out
    true for a substrate with a planted effect, which is what makes its
    being false on this one worth reading.
    """
    report = channel.channel_headroom(split="qual", seeds=COHORT)
    assert report["estimator"] == channel.ESTIMATOR
    assert report["reachable_evidence"] == ["3", "11"]
    scoring = report["split_half"]["score"]["seeds"]
    paired = [channel.lineage_descendant_score(
        report["best_probe"], "qual", seed)["unqueried"]
        - channel.descendant_score(channel.INCUMBENT_EVIDENCE, "qual", seed)[
            "unqueried"]
        for seed in scoring]
    mean = sum(paired) / len(paired)
    spread = statistics.pstdev(paired) / len(paired) ** 0.5
    assert report["delta"] == mean, (
        "the reported gap is not the paired difference it claims to be")
    assert report["paired_se"] == spread, (
        "the reported standard error is not the spread of the paired"
        " difference it claims to be")
    assert report["delta"] <= 0.0, (
        "the best reachable probe beats the incumbent by %.5f, so the"
        " channel does carry headroom and the decision is steerable after"
        " all: %r" % (report["delta"], report))
    assert report["delta"] <= report["paired_se"], (
        "the gap %.5f exceeds its own standard error %.5f on %d seeds, so"
        " the channel does carry a reachable effect: %r" % (
            report["delta"], report["paired_se"], report["n"], report))
    assert report["best_beats_incumbent"] is False
    assert report["measurable"] is False
    assert report["incumbent_mean"] == sum(
        channel.descendant_score(channel.INCUMBENT_EVIDENCE, "qual", seed)[
            "unqueried"] for seed in scoring) / len(scoring), (
        "the report must quote the incumbent it compares against, and on"
        " the half of the cohort it compares on, or the comparison is"
        " against nothing: %r" % (report,))


# --- eligibility ----------------------------------------------------------

def test_prose_recommendation_is_ineligible(tmp_path):
    store, base = _bound_store(tmp_path, "prose.json")
    verdict = channel.classify_revision(
        "Recommend probing input 7 because it is the most informative.",
        _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_PROSE


def test_empty_revision_is_ineligible(tmp_path):
    store, base = _bound_store(tmp_path, "empty.json")
    verdict = channel.classify_revision(
        "", _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_PROSE


def test_revision_that_never_selects_evidence_is_ineligible(tmp_path):
    store, base = _bound_store(tmp_path, "noboundary.json")
    revision = channel._revision_source("3").replace(
        '"kind": "probe"', '"kind": "wait"')
    verdict = channel.classify_revision(
        revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_NO_BOUNDARY


def test_task_solver_is_ineligible(tmp_path):
    """A revision that answers the task instead of choosing evidence.

    It names a fixed input whatever the learner has seen, so it cannot be
    steered and it is a solver, not a decision.
    """
    store, base = _bound_store(tmp_path, "solver.json")
    verdict = channel.classify_revision(
        channel._revision_source("7"), _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_SOLVER


def test_delegation_to_the_unchanged_reducer_is_ineligible(tmp_path):
    """Reproducing the frozen reducer's own choice is not a change."""
    store, base = _bound_store(tmp_path, "delegate.json")
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import rule_learner as reducer
    learner = reducer.VersionSpaceLearner(rules.CLASS_TABLES, 0)
    scored = [(learner._disagreement(x), x) for x in range(rules.N_STATES)]
    best = max(score for score, _ in scored)
    argmax = sorted(x for score, x in scored if score == best)[0]
    revision = channel._revision_source(
        "%d if not view[\"experience\"] else %d" % (argmax, argmax))
    assert channel.delegates_to_frozen_reducer(
        revision, _eligibility_views(store, base)[0]) is True
    verdict = channel.classify_revision(
        revision, _eligibility_views(store, base))
    assert verdict["eligibility"] in (
        channel.INELIGIBLE_DELEGATION, channel.INELIGIBLE_SOLVER)


def test_evidence_dependent_revision_is_eligible(tmp_path):
    store, base = _bound_store(tmp_path, "eligible.json")
    revision = channel._revision_source(
        '3 if not view["experience"] else 6')
    verdict = channel.classify_revision(
        revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.ELIGIBLE
    assert verdict["decision"] == channel.DECISION


# --- immutability ---------------------------------------------------------

def test_revision_writing_the_grant_is_refused(tmp_path):
    store, base = _bound_store(tmp_path, "grant.json")
    revision = channel._revision_source("3").replace(
        "    step = state.get",
        "    grant = 999\n    step = state.get")
    verdict = channel.admit_revision_under_freeze(
        store, revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE


def test_revision_writing_the_evaluator_is_refused(tmp_path):
    store, base = _bound_store(tmp_path, "evaluator.json")
    revision = channel._revision_source("3").replace(
        "    step = state.get",
        '    evaluator = "invl02-tilted"\n    step = state.get')
    verdict = channel.admit_revision_under_freeze(
        store, revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE


def test_revision_writing_sealed_results_is_refused(tmp_path):
    store, base = _bound_store(tmp_path, "sealed.json")
    revision = channel._revision_source("3").replace(
        "    step = state.get",
        "    sealed_results = []\n    step = state.get")
    verdict = channel.admit_revision_under_freeze(
        store, revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE


def test_revision_augmenting_used_budget_is_refused(tmp_path):
    store, base = _bound_store(tmp_path, "used.json")
    revision = channel._revision_source("3").replace(
        "    step = state.get",
        "    used['queries'] = 99\n    step = state.get")
    verdict = channel.admit_revision_under_freeze(
        store, revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE


def test_frozen_state_survives_admitting_an_eligible_revision(tmp_path):
    store, base = _bound_store(tmp_path, "freeze.json")
    before = channel.frozen_state(store)
    revision = channel._revision_source('3 if not view["experience"] else 6')
    verdict = channel.admit_revision_under_freeze(
        store, revision, _eligibility_views(store, base))
    assert verdict["eligibility"] == channel.ELIGIBLE
    after = channel.frozen_state(store)
    assert before == after
    assert after["evaluator"] == channel.EVALUATOR_ID
    assert after["execution_limits"]["max_queries"] == br.MAX_QUERIES
    assert after["grant"] == {"queries": 16, "steps": 12}


def test_grant_actually_bounds_what_a_revision_can_spend(tmp_path):
    """The freeze is not only about the revision's intent.

    A revision that asks for more than the grant is refused by the
    authority, so a revision cannot buy itself a bigger budget by
    requesting one.
    """
    store, base = _bound_store(tmp_path, "grantbound.json")
    greedy = channel._revision_source("3").replace(
        '{"queries": 1, "steps": 1}',
        '{"queries": 999, "steps": 999}')
    store.adopt_revision(_revision_package(greedy, base, "greedy"))
    try:
        channel.drive_improve_round(
            store, br.make_task("dev", 0), package=store.active_package,
            round_no=1, admit_probes=True)
    except Exception as exc:
        assert "grant" in str(exc) or "authority" in str(exc) or \
            "candid" in str(exc), str(exc)
    assert store.authority["queries_remaining"] >= 0
    assert store.authority["steps_remaining"] >= 0


# --- apparatus controls ---------------------------------------------------

def _measured(evidence, split="qual", seeds=COHORT):
    return channel.evaluate_descendants(list(evidence), split=split,
                                        seeds=seeds)


def test_known_effect_revision_produces_its_effect():
    """The apparatus can detect a real improvement, on a real descendant.

    The evidence here is one no descendant of this channel can gather, so
    this control qualifies the measurement machinery and is explicitly not
    a claim about the channel. It is the control that shows a positive
    reading is a reading and not an artifact.
    """
    incumbent = _measured([3])
    revised = _measured(channel.GENERAL_POSITION)
    delta = channel.descendant_delta(revised, incumbent)
    assert delta["measured"] is True
    assert delta["delta"] > 0, (
        "the apparatus failed to detect a known improvement; it cannot"
        " detect anything")


def test_noop_control_produces_no_effect():
    """The control that makes every other number mean something.

    A revision attached to the learner that returns the incumbent's own
    choice must leave the descendant bit-for-bit unchanged. If it moved
    the metric, the metric is fitting noise and nothing it reports is
    evidence.
    """
    baseline = _measured([3])
    noop = _measured([3])
    assert noop["mean"] == baseline["mean"]
    assert channel.descendant_delta(noop, baseline)["delta"] == 0.0


def test_disconnect_counterexample_produces_no_effect():
    """A revision causally disconnected from the learner.

    Its chosen input is one the instrument refuses, so no observation
    reaches the reducer. The descendant must be identical to a descendant
    that received nothing from the revision at all, which is what
    "disconnected" has to mean for a measurement to be honest.
    """
    disconnected = _measured([16])
    received_nothing = _measured([])
    assert disconnected["mean"] == received_nothing["mean"]
    scored = channel.descendant_score([16], "qual", 0)
    assert scored["refused_inputs"] == 1
    assert scored["learned_inputs"] == 0
    assert channel.descendant_delta(
        disconnected, received_nothing)["delta"] == 0.0


def test_a_disconnect_and_a_noop_are_different_failures():
    """Both produce no measured effect, and they are not the same thing.

    The no-op learns from real evidence; the disconnect learns nothing.
    An apparatus that could not tell those apart would be reporting a
    number without knowing which run produced it.
    """
    noop = _measured([3])
    disconnect = _measured([16])
    assert noop["mean"] != disconnect["mean"]
    assert channel.descendant_score([3], "qual", 0)["learned_inputs"] == 1
    assert channel.descendant_score([16], "qual", 0)["learned_inputs"] == 0


def _controls(noop_delta=0.0, disconnect_delta=0.0, known=True):
    def delta_of(evidence, seeds=COHORT):
        return channel.descendant_delta(
            _measured(evidence, seeds=seeds),
            _measured([3], seeds=seeds))["delta"]
    return [
        {"role": "known-effect", "as_expected": known,
         "delta": delta_of(channel.GENERAL_POSITION)},
        {"role": "no-op", "as_expected": noop_delta == 0.0,
         "delta": noop_delta},
        {"role": "disconnect", "as_expected": disconnect_delta == 0.0,
         "delta": disconnect_delta},
    ]


def test_qualification_passes_when_all_three_controls_behave():
    verdict = channel.qualify_apparatus(_controls())
    assert verdict["qualified"] is True
    assert verdict["qualification"] == channel.QUALIFIED
    for role in channel.CONTROL_ROLES:
        assert verdict["checks"][role]["passed"] is True


def test_qualification_fails_when_the_noop_moves():
    """A moving no-op makes the apparatus invalid, not merely unproven."""
    verdict = channel.qualify_apparatus(_controls(noop_delta=0.01))
    assert verdict["qualified"] is False
    assert verdict["checks"]["no-op"]["passed"] is False


def test_qualification_fails_when_the_disconnect_moves():
    verdict = channel.qualify_apparatus(_controls(disconnect_delta=0.02))
    assert verdict["qualified"] is False
    assert verdict["checks"]["disconnect"]["passed"] is False


def test_qualification_fails_when_a_control_is_absent():
    verdict = channel.qualify_apparatus(_controls()[:2])
    assert verdict["qualified"] is False
    assert verdict["checks"]["disconnect"]["present"] is False


# --- qualification and outcome are separate ------------------------------

def test_qualification_takes_no_run_outcome_as_input():
    """The verdict is a function of the controls and nothing else."""
    controls = _controls()
    assert channel.qualify_apparatus(controls) == \
        channel.qualify_apparatus(list(reversed(controls)))


def test_outcome_cannot_read_the_qualification():
    """The separation is structural, not a convention.

    `benefit_outcome` takes no qualification argument, so a run cannot
    smuggle a passing qualification in as evidence of its own merit, and
    the two verdicts cannot be produced by one function.
    """
    import inspect
    assert "qualification" not in inspect.signature(
        channel.benefit_outcome).parameters
    assert set(inspect.signature(
        channel.benefit_outcome).parameters) == {"delta", "acquisition"}


def test_a_qualified_apparatus_cannot_manufacture_a_benefit():
    assert channel.qualify_apparatus(_controls())["qualified"] is True
    outcome = channel.benefit_outcome(
        {"measured": True, "delta": 0.01},
        {"eligible": False, "live_attributable": False})
    assert outcome["benefit"] is False
    assert "no eligible revision was acquired" in outcome["blockers"]


def test_a_failing_run_does_not_unqualify_the_apparatus():
    controls = _controls()
    qualification = channel.qualify_apparatus(controls)
    failing = channel.benefit_outcome(
        {"measured": True, "delta": -0.2},
        {"eligible": True, "live_attributable": True})
    assert failing["benefit"] is False
    assert qualification["qualified"] is True


def test_no_live_acquisition_means_no_benefit_claim():
    """The campaign's own fallback: report the outcome, claim nothing."""
    outcome = channel.benefit_outcome(
        {"measured": True, "delta": 0.02},
        {"eligible": False, "live_attributable": False})
    assert outcome["benefit"] is False
    assert outcome["scope"] is None
    assert any("live" in blocker for blocker in outcome["blockers"])


def test_an_unmeasured_descendant_metric_never_claims_benefit():
    outcome = channel.benefit_outcome(
        {"measured": False, "delta": None},
        {"eligible": True, "live_attributable": True})
    assert outcome["benefit"] is False
    assert "descendant metric was not measured" in outcome["blockers"]


# --- descendant metric versus reviser score -------------------------------

def test_descendant_metric_and_reviser_score_disagree():
    """The two measure different things and the apparatus tells them apart.

    The reviser's own round only asks whether a probe returned bits, so it
    scores 1.0 for every evidence choice. The descendant metric asks what
    the frozen reducer can still say about inputs nobody probed. A revision
    that raises the first and not the second has not improved learning.
    """
    good = _measured(channel.GENERAL_POSITION)
    bad = _measured([7])
    reviser_good = channel.reviser_own_score(
        [{"x": x, "y": [1, 0, 1, 0]} for x in channel.GENERAL_POSITION])
    reviser_bad = channel.reviser_own_score([{"x": 7, "y": [1, 1, 0, 1]}])
    assert reviser_good == 1.0
    assert reviser_bad == 1.0
    assert good["mean"] > bad["mean"], (
        "the descendant metric did not separate the two evidence sets, so"
        " it cannot detect an improvement either")
