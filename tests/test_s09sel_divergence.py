"""Lane K: is the treatment active, and if not, why.

These tests are written to be able to fail. An inactivity detector that
passes when trajectories collapse is worse than no detector, so the
divergence and decision-reachability tests assert measured differences
and the superiority test asserts the measured comparison in whichever
direction the evidence points.

The substrate finding these tests pin: over the qualified worlds the
held-out-optimal (capability, depth) is the same in every world, so a
constant already names the optimum and an adaptive policy has nothing
left to discover. That is why `test_the_agenda_does_not_beat_the_control`
asserts no benefit. If a future substrate change gives selection real
headroom, that test is the one that should start failing.
"""

from __future__ import annotations

from experiments.ad01 import agenda_policy, selection


WORLD = 0
WORLDS = selection.WORLDS
BUDGET = 40


def _agenda(world=WORLD, budget=BUDGET, **kwargs):
    return selection.run_investigations(
        selection.portfolio_for_world(world),
        agenda_policy.agenda_policy(**kwargs),
        selection.Allocation(authorized=budget), world=world)


def _fixed(world=WORLD, budget=BUDGET, rule=None):
    return selection.run_investigations(
        selection.portfolio_for_world(world),
        agenda_policy.fixed_policy(rule),
        selection.Allocation(authorized=budget), world=world)


def test_agenda_and_fixed_choose_different_investigations():
    agenda = _agenda()
    fixed = _fixed()

    agenda_picks = [(c.candidate.capability_id, c.candidate.max_queries,
                     c.candidate.target) for c in agenda.choices]
    fixed_picks = [(c.candidate.capability_id, c.candidate.max_queries,
                    c.candidate.target) for c in fixed.choices]

    assert agenda.choices, "the agenda undertook no investigation at all"
    assert agenda_picks != fixed_picks, (
        "both policies ran the identical schedule, so the treatment is "
        "inactive and no comparison is meaningful")


def test_both_choices_change_the_outcome():
    """Divergence that lands on the same yield is one policy relabelled."""
    agenda = _agenda()
    fixed = _fixed()

    assert agenda.yield_.retained_behaviors != fixed.yield_.retained_behaviors \
        or abs(agenda.yield_.held_out_reduction
               - fixed.yield_.held_out_reduction) > 1e-9, (
        "the policies chose different investigations and produced the same "
        "yield, so the choice did not matter")


def test_agenda_choices_move_with_the_envelope():
    """Inactivity detector.

    A policy replaying an authored schedule returns the same sequence for
    every resource envelope. A policy deciding under an envelope does not.
    """
    narrow = _agenda(budget=20)
    wide = _agenda(budget=60)

    assert [c.candidate.max_queries for c in narrow.choices] != \
        [c.candidate.max_queries for c in wide.choices], (
        "the agenda ran the same investigations at 20 and at 60 units, so "
        "the envelope did not bind and the treatment is inactive")


def test_agenda_does_not_replay_the_authored_schedule():
    from experiments.ad01 import rotation, trajectory
    agenda = _agenda()
    schedule = [step["task_id"] for step in rotation.r_schedule(WORLD)]
    default_tasks = trajectory._default_tasks(WORLD, "I")

    targets = [c.candidate.target for c in agenda.choices]
    assert targets != default_tasks, (
        "the agenda ran the software-only default task list verbatim")
    assert targets != schedule, (
        "the agenda replayed the R curriculum schedule verbatim")


def test_agenda_explores_more_than_one_capability():
    agenda = _agenda()
    capabilities = {c.candidate.capability_id for c in agenda.choices}

    assert len(capabilities) >= 3, (
        "the agenda committed to a single capability, which is what a fixed "
        "allocation does; it never compared anything")


def test_the_agenda_does_not_beat_the_control():
    """The measured comparison, asserted in the direction the evidence shows.

    The agenda leads only where the envelope is too tight for the control
    to qualify anything: 1 or 2 retained behaviors against its 0. From 30
    units up, the fitted control wins, and an exhaustive search over the
    control's own rule space beats the agenda outright. Asserting the
    observed direction keeps the study honest and turns a substrate
    change into a failing test rather than a quiet benefit claim.
    """
    for budget in (14, 20):
        agenda = _agenda(budget=budget)
        fixed = _fixed(budget=budget)
        assert fixed.yield_.retained_behaviors == 0, (
            "the control retained something at %d units, so the envelope is "
            "no longer too tight for it and the boundary needs removing"
            % budget)
        assert agenda.yield_.retained_behaviors > \
            fixed.yield_.retained_behaviors, (
            "the agenda retained %d against the control's 0 at budget %d"
            % (agenda.yield_.retained_behaviors, budget))

    for budget in (30, 40, 60):
        agenda = _agenda(budget=budget)
        fixed = _fixed(budget=budget)
        assert agenda.yield_.held_out_reduction \
            < fixed.yield_.held_out_reduction, (
            "the agenda held out %.3f against the control's %.3f at budget "
            "%d" % (agenda.yield_.held_out_reduction,
                    fixed.yield_.held_out_reduction, budget))


def test_the_control_is_the_best_rule_of_its_shape():
    """Competence, established by search rather than asserted.

    A control that loses only because it was handicapped proves nothing,
    so the rule is checked against the whole space of constants it could
    have been, scored on all three qualified worlds at once.
    """
    rule = agenda_policy.FixedPolicy.DEFAULT_RULE
    total = 0.0
    for world in WORLDS:
        total += _fixed(world=world, rule=rule).yield_.held_out_reduction

    beaten = 0
    for software_method in selection.METHODS:
        for graph_method in selection.METHODS:
            for software_depth in selection_depths():
                for graph_depth in selection_depths():
                    other = {"software": (software_method, software_depth),
                             "graph": (graph_method, graph_depth)}
                    if other == rule:
                        continue
                    score = sum(
                        _fixed(world=world, rule=other).yield_.held_out_reduction
                        for world in WORLDS)
                    if score > total:
                        beaten += 1
    assert beaten == 0, (
        "%d constant rules beat the published control, so the control is "
        "not the strongest of its shape" % beaten)


def selection_depths():
    return (1, 2, 3, 4, 5, 6, 7)


def test_the_held_out_optimum_is_world_invariant():
    """Why the treatment cannot win: there is nothing left to discover.

    A constant names the optimum, so adaptation has no headroom. This is
    the substrate fact the whole negative result rests on, so it is
    asserted rather than assumed. It costs one exhaustive search, so it
    is marked and the module-scoped result is reused.
    """
    rules = {world: selection.best_fixed_allocation(
        world=world, authorized=BUDGET).policy_version for world in WORLDS}

    assert len(set(rules.values())) == 1, (
        "the held-out-optimal fixed rule differs across worlds, so selection "
        "has real headroom and the negative result needs revisiting: %r"
        % rules)


def test_every_choice_states_a_reason_the_run_actually_took():
    """The rationale must describe this run, not boilerplate.

    A policy that stamped the same sentence on every choice would pass a
    truthiness check, so this asks whether the reasons differ and whether
    each one names the capability or depth it committed to.
    """
    run = _agenda()
    reasons = [c.rationale for c in run.choices]
    assert len(set(reasons)) > 1, (
        "every choice carried the same rationale, so the run recorded a "
        "form rather than a decision")
    for choice in run.choices:
        method = choice.candidate.capability_id.rsplit("-", 1)[-1]
        assert method in choice.rationale or str(
            choice.candidate.max_queries) in choice.rationale, (
            "the rationale for %s/%d names neither the capability nor the "
            "depth it committed to"
            % (choice.candidate.capability_id,
               choice.candidate.max_queries))
