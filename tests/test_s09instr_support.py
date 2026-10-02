"""Lane F: the two pilot worlds' finite support, identity, separation,
difficulty and the panels qualified against them.

The assertions here pin computed values against literals. A world that
admits 24 targets and is asked for 8 held-out ones is not short of
evidence; a world that admits 4 and is asked for 8 is reporting
replication that does not exist. Both facts are cheap to state and easy to
forget, so they are computed from the code in every run.
"""

import json
import math

import pytest

from experiments.ad01 import boolean_active
from experiments.ad01 import boolean_rule
from experiments.ad01 import s09_instruments as instruments
from experiments.ad01 import second_active


def _ordering_view(split="qual", seed=4):
    task = second_active.make_task(split, seed)
    return task, second_active.public_state(second_active.ScheduleSession(task))


def _boolean_view(split="qual", seed=4):
    task = boolean_rule.make_task(split, seed)
    return task, boolean_active.public_state(boolean_rule.RuleSession(task))


# ---------------------------------------------------------------- support


def test_the_ordering_world_admits_exactly_twenty_four_hidden_targets():
    from itertools import permutations

    support = instruments.enumerate_support(instruments.ORDERING)

    assert instruments.spec_for(instruments.ORDERING).support_size == 24
    assert len(support) == 24
    assert len(set(support)) == 24
    assert set(support) == set(permutations(second_active.JOB_IDS))


def test_ordering_support_is_entirely_reachable_from_the_generator():
    reachable = {second_active.make_task(split, seed)["order"]
                 for split in second_active.SPLITS
                 for seed in range(48)}

    assert reachable == set(instruments.enumerate_support(
        instruments.ORDERING))


def test_boolean_world_admits_four_distinct_class_members_per_target():
    spec = instruments.spec_for(instruments.BOOLEAN)

    assert len(boolean_rule.CLASS_TABLES) == 224
    assert spec.support_size == 224 * 223 * 222 * 221
    assert spec.support_size == 2450745024
    assert spec.enumerable is False


def test_boolean_support_refuses_to_materialise_rather_than_exhaust_memory():
    with pytest.raises(instruments.PanelRefused) as refusal:
        instruments.enumerate_support(instruments.BOOLEAN)

    assert refusal.value.reason == "support-not-enumerable"
    assert refusal.value.detail["support_size"] == 2450745024


def test_the_requested_panel_does_not_fit_the_ordering_support():
    """Four dev plus eight held-out is twelve of twenty-four. It fits, but
    only just, and the boundary is the finding: this world cannot grow."""
    probability = instruments.collision_probability(
        instruments.ORDERING, 12)

    assert probability == pytest.approx(0.0354678, abs=1e-6)
    assert 12 <= 24
    assert instruments.collision_probability(instruments.ORDERING, 25) == 0.0


def test_a_seed_panel_over_the_ordering_world_actually_collides():
    """The probability above is a prior. This is what the generator does.

    Seeds 0 through 11 of one split return twelve instances over eleven
    distinct targets. The thirteenth instance is not new evidence.
    """
    orders = [second_active.make_task("dev", seed)["order"]
              for seed in range(12)]

    assert len(orders) == 12
    assert len(set(orders)) == 11


# ---------------------------------------------------------------- identity


def test_a_panel_refuses_when_it_asks_for_more_targets_than_exist():
    with pytest.raises(instruments.PanelRefused) as refusal:
        instruments.build_panel(instruments.ORDERING, dev=4, held=24)

    assert refusal.value.reason == "panel-exceeds-finite-support"
    assert refusal.value.detail == {
        "requested": 28,
        "support_size": 24,
        "support_formula": "4! strict total orders on four named jobs",
    }


def test_differing_seeds_are_not_evidence_of_a_differing_target():
    """Two seeds, one target. This is the instance-identity failure the
    handoff names, in its smallest form."""
    first = second_active.make_task("dev", 5)
    second = second_active.make_task("dev", 11)

    assert first["seed"] != second["seed"]
    assert first["task_id"] != second["task_id"]
    assert first["order"] == second["order"]
    assert instruments.target_digest(instruments.ORDERING, first) == \
        instruments.target_digest(instruments.ORDERING, second)


def test_a_built_panel_holds_distinct_targets_where_seed_enumeration_would_not():
    panel = instruments.build_panel(instruments.ORDERING, dev=4, held=8)
    raw = [second_active.make_task("dev", seed) for seed in range(4)] \
        + [second_active.make_task("qual", seed) for seed in range(8)]

    assert len({cell.target_digest for cell in panel.cells}) == 12
    assert len({instruments.target_digest(instruments.ORDERING, task)
                for task in raw}) < 12


def test_a_booleans_panel_over_its_own_support_is_all_distinct():
    panel = instruments.build_panel(instruments.BOOLEAN, dev=4, held=8)

    assert len({cell.target_digest for cell in panel.cells}) == 12
    assert len({(cell.split, cell.seed) for cell in panel.cells}) == 12
    assert len({cell.task_id for cell in panel.cells}) == 12


# ------------------------------------------------------- hidden separation


def test_the_policy_view_field_list_is_pinned_for_each_world():
    order_task, order_view = _ordering_view()
    bool_task, bool_view = _boolean_view()

    assert set(order_view) == set(
        instruments.spec_for(instruments.ORDERING).view_keys)
    assert set(bool_view) == set(
        instruments.spec_for(instruments.BOOLEAN).view_keys)
    assert "order" not in order_view
    assert "tables" not in bool_view
    assert order_view["split"] == "qual"
    assert bool_view["split"] == "qual"


def test_the_pinned_view_carries_no_answer_key_in_any_field():
    """The hidden object is a *permutation* and a *quadruple of tables*.
    The names that go into them are public by design, so the check is that
    no field holds the arrangement, not that no field holds the pieces."""
    order_task, order_view = _ordering_view()
    bool_task, bool_view = _boolean_view()

    for field, value in order_view.items():
        assert value != list(order_task["order"])
        assert value != order_task["order"]
    for field, value in bool_view.items():
        assert value != list(bool_task["tables"])
        assert value != bool_task["tables"]

    observed = json.dumps(order_view, sort_keys=True)
    for first in second_active.JOB_IDS:
        for second in second_active.JOB_IDS:
            if first == second:
                continue
            assert "%s%s%s" % (first, ", ", second) not in observed


def test_the_view_does_not_determine_the_target_in_either_world():
    """The leak, closed. The answer is in no field and is not computable
    from the fields, because the public `task_id` is a digest rather than the
    seed the generators are a pure function of."""
    order_task, order_view = _ordering_view()
    bool_task, bool_view = _boolean_view()

    assert instruments.view_leaks_target(
        instruments.ORDERING, order_view, order_task) is False
    assert instruments.view_leaks_target(
        instruments.BOOLEAN, bool_view, bool_task) is False


def test_the_ordering_policy_cannot_score_full_marks_without_one_query():
    def recover(state):
        try:
            order = instruments.derive_target_from_view(
                instruments.ORDERING, state)
        except instruments.PanelRefused:
            return {"kind": "stop", "target": "schedule.task", "inputs": {},
                    "evidence_refs": [], "requested_resources": {}}
        return {"kind": "construct", "target": "schedule.commit",
                "inputs": {"order": list(order)}, "evidence_refs": [],
                "requested_resources": {}}

    result = second_active.run_episode(recover, split="qual", seed=4)

    assert result["final"] is None
    assert result["comparisons"] == []


def test_the_boolean_policy_cannot_score_full_marks_without_one_query():
    def recover(state):
        try:
            tables = instruments.derive_target_from_view(
                instruments.BOOLEAN, state)
        except instruments.PanelRefused:
            return {"kind": "stop", "target": "boolean.task", "inputs": {},
                    "evidence_refs": [], "requested_resources": {}}
        return {"kind": "construct", "target": "boolean.commit",
                "inputs": {"specs": [boolean_rule.spec_for_table(table)
                                     for table in tables]},
                "evidence_refs": [], "requested_resources": {}}

    result = boolean_active.run_episode(recover, split="qual", seed=4)

    assert result["final"] is None
    assert result["queried"] == []


def test_closing_the_leak_means_removing_the_seed_from_the_view():
    """What a fix has to do. Renaming `task_id` hides the seed from the
    policy; the target stops being a function of the view. The audit then
    reports no leak, which is the property lane I needs to be able to
    assert rather than assume."""
    order_task, order_view = _ordering_view()
    opaque = dict(order_view)
    opaque["task_id"] = "order-%s-%s" % (
        order_view["split"],
        instruments.target_digest(instruments.ORDERING, order_task))

    assert instruments.view_leaks_target(
        instruments.ORDERING, opaque, order_task) is False


# ------------------------------------------------------------ split overlap


def test_a_built_panel_shares_no_target_between_dev_and_held_out():
    panel = instruments.build_panel(instruments.ORDERING, dev=4, held=8)
    report = instruments.audit_panel(panel)

    dev = {cell.target_digest for cell in panel.by_split("dev")}
    qual = {cell.target_digest for cell in panel.by_split("qual")}
    audit = {cell.target_digest for cell in panel.by_split("audit")}

    assert report["overlapping_target_count"] == 0
    assert dev & qual == set()
    assert dev & audit == set()
    assert qual & audit == set()


def test_a_booleans_panel_shares_no_target_between_splits_either():
    report = instruments.audit_panel(
        instruments.build_panel(instruments.BOOLEAN, dev=4, held=8))

    assert report["overlapping_target_count"] == 0
    assert report["duplicate_targets"] == {}


def test_split_overlap_is_reported_rather_than_silently_dropped():
    """When seeds are enumerated without a signature check, the ordering
    world does produce cross-split collisions. The audit must count them
    and refuse to certify the panel, not quietly deduplicate."""
    cells = []
    for split in ("dev", "qual", "audit"):
        for seed in range(4):
            task = second_active.make_task(split, seed)
            cells.append(instruments.Cell(
                world=instruments.ORDERING, split=split, seed=seed,
                task_id=task["task_id"],
                target_digest=instruments.target_digest(
                    instruments.ORDERING, task),
                difficulty=None))
    naive = instruments.Panel(
        world=instruments.ORDERING, cells=tuple(cells),
        support_size=24,
        support_formula="4! strict total orders on four named jobs",
        difficulty_basis="none", reference_probes=None)

    report = instruments.audit_panel(naive)

    assert report["cell_count"] == 12
    assert report["distinct_targets"] < 12
    assert report["overlapping_target_count"] > 0
    assert report["checks"]["splits_disjoint"] is False
    assert report["checks"]["targets_distinct"] is False
    assert report["qualified"] is False


# --------------------------------------------------------------- difficulty


def test_the_ordering_world_is_two_difficulties_wide_and_measured_not_assumed():
    """The instance's own cost is five comparisons for every target, so
    difficulty is flat. The cost a fixed policy actually pays is four or
    five depending on which comparisons the target makes informative, so a
    panel that wants to balance difficulty balances on this number and not
    on the flat one."""
    minimax = instruments.ordering_minimax_queries()
    spread = instruments.ordering_difficulty_spread()

    assert minimax == 5
    assert minimax == math.ceil(math.log2(24))
    assert second_active.MAX_QUERIES == 8
    assert second_active.MAX_QUERIES >= minimax
    assert spread == {4: 8, 5: 16}
    assert sum(spread.values()) == 24
    assert max(spread) == minimax


def test_the_ordering_panel_reports_a_balanced_difficulty_spread():
    panel = instruments.build_panel(instruments.ORDERING, dev=4, held=8)
    report = instruments.audit_panel(panel)

    assert report["difficulty_spread"] == 1
    assert report["checks"]["difficulty_reported"] is True
    assert report["difficulty"]["pooled_max"] == 5
    assert report["difficulty"]["pooled_min"] == 4


def test_the_booleans_world_difficulty_is_measured_under_a_named_schedule():
    """Difficulty exists but is conditional on which inputs were probed,
    so the panel names the schedule the number belongs to."""
    panel = instruments.build_panel(instruments.BOOLEAN, dev=4, held=8)
    report = instruments.audit_panel(panel)
    spec = instruments.spec_for(instruments.BOOLEAN)

    assert spec.difficulty(boolean_rule.make_task("dev", 0)) == 6
    assert spec.difficulty(boolean_rule.make_task("dev", 1)) == 12
    assert report["difficulty_reported"] is True
    assert report["difficulty"]["reference_probes"] == list(
        instruments.REFERENCE_PROBES)
    assert "probe schedule" in spec.difficulty_basis


def test_difficulty_varies_across_boolean_targets_so_a_panel_must_balance_it():
    panel = instruments.build_panel(instruments.BOOLEAN, dev=4, held=8)
    values = [cell.difficulty for cell in panel.cells]

    assert sorted(set(values)) == [4, 6, 8, 10, 12]
    assert instruments.audit_panel(panel)["difficulty_spread"] == 8
    assert instruments.audit_panel(
        instruments.build_panel(instruments.BOOLEAN, dev=4, held=8)
    )["difficulty"]["pooled_min"] == 4


# ------------------------------------------------------- qualified panels


def test_the_qualified_ordering_panel_says_what_it_is_qualified_against():
    panel = instruments.build_panel(instruments.ORDERING, dev=4, held=8)
    report = instruments.audit_panel(panel)

    assert report["qualified"] is True
    assert report["checks"] == {
        "targets_distinct": True,
        "splits_disjoint": True,
        "panel_within_support": True,
        "difficulty_reported": True,
    }
    assert report["cell_count"] == 12
    assert report["distinct_targets"] == 12
    assert report["distinct_targets_per_split"] == {
        "dev": 4, "qual": 4, "audit": 4}
    assert report["support_size"] == 24
    assert len(panel.by_split("dev")) == 4
    assert len(panel.by_split("qual")) + len(panel.by_split("audit")) == 8


def test_the_qualified_booleans_panel_is_capped_by_nothing_it_claims():
    panel = instruments.build_panel(instruments.BOOLEAN, dev=4, held=8)
    report = instruments.audit_panel(panel)

    assert report["qualified"] is True
    assert report["distinct_targets"] == 12
    assert report["support_size"] == 2450745024
    assert report["cell_count"] <= report["support_size"]


def test_a_panel_twenty_four_wide_is_the_whole_ordering_world():
    """The honest ceiling for this world, stated so nobody proposes 24
    distinct held-out targets and means 24 seeds."""
    panel = instruments.build_panel(instruments.ORDERING, dev=0, held=24)
    report = instruments.audit_panel(panel)

    assert report["cell_count"] == 24
    assert report["distinct_targets"] == 24
    assert report["support_size"] == 24
    assert report["qualified"] is True
    with pytest.raises(instruments.PanelRefused):
        instruments.build_panel(instruments.ORDERING, dev=0, held=25)
