"""The E3 control must be a competent pre-committed rule, and be blind.

`FixedPolicy`'s docstring claimed its `DEFAULT_RULE` was "the strongest
world-blind constant pair, chosen by an exhaustive search over every
(capability, depth) combination scored on the three qualified worlds at
once". Measured at this tip that claim is false at three of the four loose
budgets: an exhaustive search over the same space finds a higher-scoring
pair at 20, 30 and 60, and ties at 40. `DEFAULT_RULE` is retained for the
committed evidence and the claim is withdrawn; `fitted_fixed_rule` is the
honest control, fitted on development retention, which the agenda never
reads.

A control weaker than the honest one is not a conservative control, it is a
misleading one. Every advantage the agenda shows against the historical
rule is an advantage against a rule that was never shown to be the best its
own family can produce, so an arm beating it is not yet evidence of
anything about selection.

These tests pin the properties the arm needs to be worth reporting: that
the fitted rule is a genuine improvement on the historical one, that it is
not an oracle for the metric the comparison reads, that it depends only on
pre-run inputs, and that the control's allocation cannot be moved by
run-time state.
"""

from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import agenda_policy
from experiments.ad01 import s09_e3_selection as e3
from experiments.ad01 import selection

# The search space `FixedPolicy`'s docstring claims the default came from.
SEARCH_DEPTHS = (1, 2, 3, 4, 5, 6, 7)


def _held_out(rule, world: int, budget: int) -> float:
    run = selection.run_investigations(
        None, agenda_policy.fixed_policy(rule),
        selection.Allocation(authorized=budget), world=world)
    return run.yield_.held_out_reduction


def _all_rules():
    """Every constant pair in the space `FixedPolicy` can express."""
    for sw_method, gr_method, sw_depth, gr_depth in product(
            selection.METHODS, selection.METHODS,
            SEARCH_DEPTHS, SEARCH_DEPTHS):
        yield {"software": (sw_method, sw_depth),
               "graph": (gr_method, gr_depth)}


def _best_fitted_rule(budget: int, worlds=selection.WORLDS) -> tuple:
    """Exhaustive search: the rule maximising mean held-out over `worlds`.

    This is an oracle in the sense `best_fixed_allocation` already is -- it
    reads a score the control is forbidden to see at run time. It is
    computed here, in the test, rather than imported, so that pinning the
    arm's rule against it cannot be satisfied by the arm agreeing with
    itself. Both arms are scored with the frozen measures and the same
    three worlds, so a difference here is a difference in the rule and not
    in the instrument.
    """
    best = None
    for rule in _all_rules():
        score = sum(_held_out(rule, w, budget) for w in worlds) / len(worlds)
        if best is None or score > best[0]:
            best = (score, rule)
    return best[0], best[1]


def _retained(rule, world: int, budget: int) -> int:
    run = selection.run_investigations(
        None, agenda_policy.FixedPolicy(rule),
        selection.Allocation(authorized=budget), world=world)
    return run.yield_.retained_behaviors


def _historical_default_is_not_the_optimum_at_any_budget():
    """The measurement behind the docstring change, kept as a function.

    The historical `DEFAULT_RULE` scored lower than an exhaustive search
    over its own space at budgets 20, 30 and 60 and equal at 40, so it was
    never the strongest rule its space contains. It is retained for the
    committed evidence and is no longer claimed to be fitted-optimal.
    """
    gaps = {}
    for budget in (20, 30, 40, 60):
        best_score, _rule = _best_fitted_rule(budget)
        default_score = sum(
            _held_out(agenda_policy.FixedPolicy.DEFAULT_RULE, w, budget)
            for w in selection.WORLDS) / len(selection.WORLDS)
        gaps[budget] = default_score - best_score
    return gaps


def test_the_search_space_is_not_flat():
    """A guard that the fitted comparisons are real discriminations.

    If every rule in the space scored identically, both "the default is not
    optimal" and "the fit is not an oracle" would pass vacuously. This
    asserts the space actually separates rules, so the searches measure
    something.
    """
    budget = 60
    best_score, _best_rule = _best_fitted_rule(budget)
    default_score = sum(
        _held_out(agenda_policy.FixedPolicy.DEFAULT_RULE, w, budget)
        for w in selection.WORLDS) / len(selection.WORLDS)

    assert best_score > default_score, (
        "no rule in the search space beats the historical default at budget "
        "%d, so the fitted comparison cannot distinguish a strong control "
        "from a weak one" % budget)


def test_the_fitted_rule_beats_the_historical_default_on_its_own_objective():
    """The honest control must actually beat the historical one.

    Fitted on development retention, which the agenda never reads, the rule
    returned for an envelope must retain strictly more than `DEFAULT_RULE`
    does. Without this the fit could return the default and still pass every
    blindness test, and the arm would be the historical strawman wearing a
    fitted label.
    """
    budget = 60
    fitted = agenda_policy.fitted_fixed_rule(budget)
    default_retained = sum(
        _retained(agenda_policy.FixedPolicy.DEFAULT_RULE, w, budget)
        for w in selection.WORLDS)

    assert fitted["fitted_retained"] > default_retained, (
        "the development-fitted rule retains %d where the historical "
        "default retains %d at budget %d, so the fitted arm is not a "
        "stronger control"
        % (fitted["fitted_retained"], default_retained, budget))
    # The search must span the whole depth ladder the agenda walks, or the
    # control is a rule chosen from a narrower family than the treatment
    # chooses from and the comparison is not like-for-like. A margin
    # assertion cannot pin this: depth turned out to bind so weakly on this
    # substrate that restricting the search to a single depth still reached
    # the same retained count, so the ordering and even the 2x margin held
    # against a materially weaker control. The coverage is pinned directly.
    assert agenda_policy.FITTED_DEPTHS == SEARCH_DEPTHS, (
        "the control's search space is %r but the agenda walks %r; a rule "
        "fitted over a narrower ladder is not the same family"
        % (agenda_policy.FITTED_DEPTHS, SEARCH_DEPTHS))


def test_the_fitted_rule_is_not_a_held_out_oracle():
    """Non-circularity, measured. This is what separates a control from C15.

    If the fit were secretly reading the reported metric it would approach
    the exhaustive held-out search's score. The gap below is the evidence
    that it is fitted on something the held-out score cannot see.
    """
    budget = 60
    fitted = agenda_policy.fitted_fixed_rule(budget)
    fitted_held = sum(
        _held_out(fitted["rule"], w, budget) for w in selection.WORLDS) / 3
    _oracle_held, _oracle_rule = _best_fitted_rule(budget)

    assert not fitted["objective_reads_held_out"]
    assert fitted_held < _oracle_held - 0.05, (
        "the development-fitted rule reaches %.6f mean held-out reduction "
        "against an exhaustive held-out search's %.6f, so it is within 0.05 "
        "of an oracle and cannot be called a control"
        % (fitted_held, _oracle_held))


def test_the_fitted_rule_depends_only_on_pre_run_inputs():
    """Blindness of the rule itself, asserted on its reported provenance."""
    fitted = agenda_policy.fitted_fixed_rule(60)

    assert fitted["inputs_are_fixed_before_the_run"] == [
        "budget", "worlds", "depths", "methods", "objective"]
    assert set(fitted["rule"]) == set(selection.FAMILIES)
    for family, (method, depth) in fitted["rule"].items():
        assert method in selection.METHODS
        assert depth in agenda_policy.FITTED_DEPTHS


def test_the_control_cannot_observe_run_time_state():
    """Blindness, demonstrated rather than asserted in a docstring.

    The control's allocation must be a function of inputs fixed before the
    run. `FixedPolicy.propose` is handed the agenda, whose `episodes`,
    `ran` and allocation are all run-time state, so the property is not
    structural and has to be shown: two agendas offering the same portfolio
    under the same envelope, differing only in what the run has observed,
    must yield the same schedule.

    The first proposal is compared on its own, before either agenda is
    driven. A driver that advanced both agendas in step would mark them
    identically and hide exactly the leak being looked for, so each
    proposal index is read from a *fresh* pair whose run-time state is set
    to that index's worth of observations and nothing else. That makes a
    leak at any depth of the schedule visible at that index, and it is the
    reason this test is written as it is: an earlier version advanced both
    agendas with the same call and passed against a control that read
    `agenda.state["ran"]`.
    """
    budget = 30
    schedule = agenda_policy.fixed_policy().plan()
    assert len(schedule) > 1, "a one-step schedule cannot show a depth leak"

    for index in range(len(schedule)):
        def agenda_with_history(steps):
            agenda = selection.Agenda(
                selection.WORLDS[0], None,
                selection.Allocation(budget))
            for done in steps:
                family, method, _step, _depth = schedule[done]
                agenda.advance(agenda.world, family,
                               {"disposition": "retained"}, 1, 1)
                agenda.note_ran(
                    agenda.cheapest(family, method,
                                    schedule[done][2]).target)
            return agenda

        history = list(range(index))
        policy = agenda_policy.fixed_policy()
        learned = policy.propose(agenda_with_history(history))
        fresh = agenda_policy.fixed_policy().propose(
            agenda_with_history([]))

        if learned is None or fresh is None:
            continue
        assert learned["candidate"].identity == fresh["candidate"].identity, (
            "at step %d the control proposed %r after observing %d prior "
            "steps, and %r from a clean agenda, so its allocation is not a "
            "function of pre-run inputs"
            % (index, learned["candidate"].identity, index,
               fresh["candidate"].identity))


def test_the_fit_is_memoized_without_changing_what_it_returns():
    """Caching must not become a second source of truth.

    The cache is keyed on every argument the search reads. A key that
    omitted the objective or the world list would hand back a rule fitted
    for a different question, and the arm would be a held-out oracle at
    some budgets and not others with nothing in the result saying so.
    """
    first = agenda_policy.fitted_fixed_rule(60)
    again = agenda_policy.fitted_fixed_rule(60)
    assert again["rule"] == first["rule"]

    other_objective = agenda_policy.fitted_fixed_rule(
        60, objective="held_out_reduction")
    assert other_objective["objective"] == "held_out_reduction"
    assert other_objective["objective_reads_held_out"]
    assert other_objective["rule"] != first["rule"], (
        "the held-out objective produced the same rule as the development "
        "objective, so the objective is not reaching the search")
    assert agenda_policy.fitted_fixed_rule(60)["rule"] == first["rule"], (
        "a cache entry was overwritten by a differently-keyed search")


def test_a_caller_cannot_edit_the_cached_rule_in_place():
    """Pre-committed means pre-committed for every later caller too.

    The cache hands the same payload to every arm built at an envelope, so
    a shallow copy would let one caller rewrite the constants the next
    caller receives. That would make the control adaptive by side effect,
    which is the one property this arm is for, and it would be invisible:
    the fitted rule would simply differ between two runs of the same study.
    """
    first = agenda_policy.fitted_fixed_rule(60)
    original = first["rule"]["software"]
    first["rule"]["software"] = ("greedy", 1)
    first["worlds"].append(99)

    second = agenda_policy.fitted_fixed_rule(60)

    assert second["rule"]["software"] == original, (
        "a caller's edit to the cached rule survived into the next caller's "
        "control: got %r, expected the fitted %r"
        % (second["rule"]["software"], original))
    assert 99 not in second["worlds"], (
        "a caller's edit to the cached world list survived into the next "
        "caller's provenance record")


def test_the_committed_competence_test_covers_only_one_budget():
    """The scope defect, pinned so it cannot be re-instated by silence.

    `test_s09sel_divergence.test_the_control_is_the_best_rule_of_its_shape`
    is a real competence test over all 196 constant pairs and it passes --
    at `BUDGET = 40`. That is the single budget in the ladder where
    `DEFAULT_RULE` is optimal, and `STAGE-09-CONNECTED-STATUS.md` reports
    the check unqualified.

    This test does not assert the control is incompetent; it asserts that
    the competence check is budget-local, because that is the fact a reader
    needs and the fact the report currently omits. If a future change made
    the default optimal at every budget the check would stop being narrow,
    and this would go red for the right reason.
    """
    divergence = ROOT / "tests" / "test_s09sel_divergence.py"
    text = divergence.read_text(encoding="utf-8")

    assert "BUDGET = 40" in text, (
        "the competence test's budget moved; re-measure which budgets it "
        "covers before changing what this test claims")

    default_at_40 = sum(
        _held_out(agenda_policy.FixedPolicy.DEFAULT_RULE, w, 40)
        for w in selection.WORLDS) / len(selection.WORLDS)
    best_at_40, _rule_at_40 = _best_fitted_rule(40)
    assert abs(default_at_40 - best_at_40) < 1e-12, (
        "the default is no longer optimal at 40, so the committed "
        "competence test covers a budget where it does not hold and this "
        "test's premise has changed")

    # The claim the report makes is about the ladder, and the ladder
    # includes budgets the check does not reach. The count is the sharp
    # form: at 20 and 30 roughly half the search space beats the default,
    # so the gap is not a rounding artefact of one lucky rival.
    beaten_at_20 = sum(
        1 for rule in _all_rules()
        if rule != agenda_policy.FixedPolicy.DEFAULT_RULE
        and sum(_held_out(rule, w, 20) for w in selection.WORLDS)
        > sum(_held_out(agenda_policy.FixedPolicy.DEFAULT_RULE, w, 20)
              for w in selection.WORLDS))
    assert beaten_at_20 > 50, (
        "only %d of 196 rules beat the default at budget 20; the scope gap "
        "this records has closed and the claim may need re-measuring rather "
        "than re-stating" % beaten_at_20)


def test_the_crossover_reports_the_fitted_control_as_a_third_arm():
    """The arm has to be in the result, not merely available.

    A control that exists in the module but never appears in a reported
    ladder is a control nobody compared against, and the study would go on
    reporting the historical arm as the only fixed alternative.
    """
    ladder = e3.crossover(worlds=(0,))

    for step in ladder["ladder"]:
        names = {arm["policy"] for arm in step["arms"]}
        assert "fitted_control" in names, (
            "budget %d reports arms %r and the fitted control is absent"
            % (step["budget"], sorted(names)))
        assert "agenda" in names and "control" in names


def test_no_arm_charges_more_than_its_envelope():
    """Equal resources, or the comparison is not a comparison.

    Every arm is constructed with the same `authorized` at a given budget
    and spends from its own `Allocation`, so a study that gave one arm more
    envelope and reported the difference as a selection effect would be
    reporting its own harness. The charge is read back off the run rather
    than assumed from the argument.
    """
    budget = 30
    for name, make in sorted(e3._fitted_arms(budget).items()):
        run = e3.run_policy(make(), 0, budget)
        charged = run.yield_.resources_used
        assert charged <= budget, (
            "arm %r charged %d against an envelope of %d"
            % (name, charged, budget))


def test_the_fitted_control_is_blind_while_beating_the_default_on_dev():
    """The two properties together, which is what makes it the honest arm.

    Separately they are easy: a rule that is blind can be arbitrarily bad,
    and a rule that retains more can be arbitrarily adaptive. The control
    is only worth reporting if it is stronger than the historical rule on
    the signal it is allowed to see *and* unable to see anything the
    treatment saw. This asserts both in one place.
    """
    budget = 60
    fitted = agenda_policy.fitted_fixed_rule(budget)
    assert not fitted["objective_reads_held_out"]
    assert set(fitted["rule"]) == set(selection.FAMILIES)

    control_retained = sum(
        _retained(agenda_policy.FixedPolicy.DEFAULT_RULE, w, budget)
        for w in selection.WORLDS)
    assert fitted["fitted_retained"] > control_retained
