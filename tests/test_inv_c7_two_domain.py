"""One mission entry crossing both task structures.

Lane C1 built one durable mission entry (`experiments/ad01/mission.py` over
`investigations`). Lane C6 made suspend and resume answer from it. Neither
wires the two task structures together: the entry is one row, but nothing has
ever run one mission through more than one of them, so "one mission crosses
both domains" was unanswerable rather than answered.

This lane answers it, and it answers two things that are easy to conflate:

- that the CROSSING happens, on one row, across more than one episode in
  each structure, with permitted experience advancing across the boundary;
- that the COMPARISON on each side has sufficient family coverage. It does
  not, and the reason is measured rather than asserted: the Boolean/reducer
  instrument publishes exactly ONE hypothesis class across every split and seed
  (`boolean_rule`, 120 tasks, one distinct `hypothesis_class` descriptor),
  so under the study's own cluster rule `(family, template)` the whole
  Boolean side is a single cluster against the six a contrast needs at
  alpha 1/20. The SWE side offers nine templates, which clears six.

So a two-domain demonstration is not a two-domain result, and this file says
so in a test rather than in a comment.

Every number asserted here was measured on this tree. The contract field
count is 6, read from `policy_action.view_contract()` rather than restated,
and a test pins it against that source so a widening shows up as a failure.

No model call, no network, no dispatch. Both episodes are driven in-process
against the real worlds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "c7twodomain"

# The mission. One investigation id, two structures, and the second structure
# reads what the first wrote. `permitted_experience` is the field the
# crossing advances; it is a dict, so the world a piece of experience came
# from and the world that may spend it are two keys of one value rather than
# two shapes of a column.
MISSION_ID = "c7-two-domain-mission"
CHARTER = {
    "objective": "identify a hidden rule, then repair a program under test",
    "environments": ["boolean-rule-v1", "software-fault-repair-v1"],
    "constraints": ["deterministic only", "no live network"],
    "success_criteria": ["an episode in each structure"],
}


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


def _cross(dsn):
    """Run one mission through both structures and return what it recorded.

    Each structure runs MORE THAN ONE episode, and the episodes are counted
    from what the mission entry holds afterwards rather than from a counter
    this function increments, so a run that reported two episodes while
    recording one would fail.
    """
    from experiments.ad01 import twodomain

    twodomain.record_two_domain_mission(dsn, MISSION_ID, charter=CHARTER)
    return twodomain.run_two_domain_crossing(dsn, MISSION_ID)


# --- 1. one row, not two joined -----------------------------------------


def test_one_mission_row_carries_both_structures_and_is_not_a_join(store):
    """The crossing is one row.

    The failure this pins is a mission implemented as a second table keyed
    by structure, or as a `permitted_experience` list holding two entries
    that a reader has to zip. Both would answer "what is this mission doing"
    with a join, which is the arrangement lane C1 removed. Here the two
    structures are two keys of ONE jsonb value on ONE `investigations` row,
    and that row is asserted literally.
    """
    _cross(store)
    from experiments.ad01 import mission

    entry = mission.read_mission(store, MISSION_ID)

    # One row. `read_mission` refuses rather than returning a partial, and a
    # second carrier would have made it answer for the same question.
    assert entry.investigation_id == MISSION_ID
    assert entry.improvement_mode == "operate"
    assert entry.environments == CHARTER["environments"]

    crossing = entry.frontier["crossing"]
    assert sorted(crossing) == ["boolean-rule-v1", "software-fault-repair-v1"], (
        "the mission does not carry both structures in one value: %r"
        % sorted(crossing))
    assert crossing["boolean-rule-v1"]["instrument"] == "boolean-rule-v1"
    assert crossing["software-fault-repair-v1"]["instrument"] == (
        "software-fault-repair-v1")

    # And the six mission fields live on `investigations`, which is the only
    # table carrying any of them.
    with mission.connect(store) as conn:
        carriers = conn.execute(
            "SELECT table_name FROM information_schema.columns"
            " WHERE column_name IN ('frontier', 'permitted_experience',"
            " 'active_program', 'acquired_artifacts', 'retained_use',"
            " 'improvement_mode', 'in_flight')"
            " AND table_schema = 'public' GROUP BY table_name"
            " ORDER BY table_name").fetchall()
        conn.commit()
    assert [row["table_name"] for row in carriers] == ["investigations"], (
        "a mission field is reachable from another table, so the crossing "
        "would be a join: %r" % [row["table_name"] for row in carriers])


def test_the_second_structure_sees_what_the_first_produced(store):
    """Permitted experience advances across the boundary.

    The Boolean episodes observe a hidden function. Each observation becomes
    permitted experience tagged with the structure that produced it. The SWE
    episodes are then handed that experience as their starting budget for
    what they may inspect, and the mission records which experience each SWE
    episode actually spent. Without this the two structures would be two
    campaigns that happen to share an id.
    """
    out = _cross(store)
    from experiments.ad01 import boolean_rule, mission

    entry = mission.read_mission(store, MISSION_ID)

    observations = entry.permitted_experience["observations"]
    boolean_obs = [o for o in observations
                   if o["produced_by"] == "boolean-rule-v1"]
    assert len(boolean_obs) >= 1, (
        "the Boolean structure produced no permitted experience to carry")

    # What the SWE structure was permitted, and what it says it spent.
    permitted = entry.permitted_experience["by_structure"]
    assert permitted["software-fault-repair-v1"]["from"] == (
        "boolean-rule-v1"), (
        "the SWE structure's permitted experience did not come from the "
        "Boolean one")
    spent = [o for o in out["software-episodes"]
             if o["observations_consumed"]]
    assert spent, (
        "no SWE episode consumed any experience the Boolean structure "
        "produced, so the crossing did not advance anything")

    # A consumed observation is named by id and by the value the second
    # structure actually read, not merely counted.
    for episode in spent:
        assert episode["observations_consumed"], "an episode consumed nothing"
        for used in episode["observations_consumed"]:
            assert used["observation_id"] in {
                o["observation_id"] for o in boolean_obs}, (
                "an SWE episode consumed %r, which the Boolean structure "
                "never produced" % (used["observation_id"],))
            assert 0 <= used["input"] < boolean_rule.N_STATES, (
                "the SWE structure read input %r from an observation, which "
                "is not an input of the Boolean instrument"
                % (used["input"],))
            assert used["n_outputs"] == boolean_rule.N_OUTPUTS, (
                "the transferred reading described %r outputs where the "
                "Boolean instrument produces %d"
                % (used["n_outputs"], boolean_rule.N_OUTPUTS))


# --- 2. more than one episode in each structure --------------------------


def test_each_structure_ran_more_than_one_episode(store):
    """Counted from the mission, not from a run log.

    "It ran twice" is a claim about the runner. This asserts the entry
    holds more than one episode per structure, so a run that executed one
    episode and reported two cannot pass.
    """
    _cross(store)
    from experiments.ad01 import mission

    crossing = mission.read_mission(store, MISSION_ID).frontier["crossing"]

    for instrument in ("boolean-rule-v1", "software-fault-repair-v1"):
        episodes = crossing[instrument]["episodes"]
        assert len(episodes) >= 2, (
            "%s ran %d episode(s); the crossing needs more than one"
            % (instrument, len(episodes)))
        # Distinct tasks, not the same one replayed.
        assert len({e["task_id"] for e in episodes}) == len(episodes), (
            "%s replayed one task rather than running more than one episode"
            % instrument)

    # Both structures were entered from the same entry, in one call, and the
    # order is recorded: the second is the one that consumed.
    assert crossing["boolean-rule-v1"]["entered"] < crossing[
        "software-fault-repair-v1"]["entered"]


# --- 3. the view normalisation, at the count measured today --------------


def test_both_structures_normalise_to_the_same_contract_field_count():
    """The contract, measured at the count it publishes today.

    `s09_arm_parity.py:39-46` claimed `swe` was "registered for
    addressability, not because the harness can normalise its view", on the
    grounds that the contract "demands exactly eight public-state fields"
    and the SWE world publishes twelve. Both halves are stale: the contract
    publishes 6, and each world declares its OWN field set
    (`VIEW_CONTRACT_FIELDS`), so 8-against-12 is a per-world declaration
    rather than a refusal. The named test,
    `test_a_swe_arm_is_refused_by_the_harness_view_normaliser`, does not
    exist on this tree.

    So the gap is real and it is in the comment. This asserts the behaviour
    the comment denies, at the field count measured here, read from the
    contract's own source so a widening fails rather than being restated.
    """
    from experiments.ad01 import policy_action
    from experiments.ad01 import s09_arm_parity as parity
    from experiments.ad01 import boolean_active, boolean_rule
    from experiments.ad01 import s09_swe_tasks as swe_tasks
    from experiments.ad01 import s09_swe_world as swe

    contract_fields = policy_action.view_contract()["fields"]
    assert len(contract_fields) == 6, (
        "the contract publishes %d fields, not the 6 this lane measured"
        % len(contract_fields))

    boolean_state = boolean_active.public_state(
        boolean_rule.RuleSession(boolean_rule.make_task("dev", 4)))
    record = swe_tasks.instance(
        "held_out", swe_tasks.HELD_OUT_TEMPLATES[0],
        swe_tasks.HELD_OUT_MECHANISMS[0])
    swe_state = swe.SweSession(record).policy_view()

    # Each world declares a different count of its own, and neither is 6.
    assert len(parity.VIEW_CONTRACT_FIELDS["boolean-rule-v1"]) == 8
    assert len(parity.VIEW_CONTRACT_FIELDS["software-fault-repair-v1"]) == 12
    assert len(boolean_state) == 8
    assert len(swe_state) == 12

    # Both are admitted, both normalise, and both come back with exactly the
    # same six keys. That is the claim the stale comment denies.
    for state in (boolean_state, swe_state):
        assert parity.admit_world_view(state) is None
    contracts = [parity.contract_view(state)
                 for state in (boolean_state, swe_state)]
    for view in contracts:
        assert set(view) == set(contract_fields)
        assert parity.admit_shared_view(view) is None
    assert set(contracts[0]) == set(contracts[1]), (
        "the two structures do not normalise to one contract")


# --- 4. the honesty constraint, as a test -------------------------------


def test_the_boolean_side_cannot_be_powered_and_the_mission_says_so():
    """The crossing is not a two-domain result, and this fails if it claims to be.

    B8's census answers the power question for the frozen `software` and
    `graph` families. Those are not these instruments: this lane's Boolean
    side is `boolean_rule` and its SWE side is `s09_swe_world`, and the
    cluster rule transfers while the counts do not. Measured here: the
    Boolean instrument publishes ONE hypothesis class across every split
    and seed, so its whole side is one cluster under `(family, template)`.

    `run_two_domain_crossing` therefore returns resolution, available family
    coverage and actual assessment counts per structure rather than a
    statistical-power verdict.
    """
    from experiments.ad01.s09_panel_inventory import (
        minimum_clusters_for_alpha, CLUSTER_RULE)

    required = minimum_clusters_for_alpha(1 / 20)
    assert required == 6
    assert CLUSTER_RULE == "(family, template)"

    from experiments.ad01 import boolean_rule
    from experiments.ad01 import twodomain

    census = twodomain.cluster_census()

    assert census["boolean-rule-v1"]["cluster_count"] == 1, (
        "the Boolean side now reports %d clusters; if the instrument "
        "changed, this lane's power claim is stale and must be re-derived"
        % census["boolean-rule-v1"]["cluster_count"])
    assert census["boolean-rule-v1"]["minimum_p_resolution"][
        "meets_alpha_resolution"] is False
    assert census["software-fault-repair-v1"]["cluster_count"] == 9
    assert census["software-fault-repair-v1"]["minimum_p_resolution"][
        "meets_alpha_resolution"] is True

    # The required count is named, so a reader can see 1-vs-6 rather than
    # being asked to trust a boolean.
    assert census["required_clusters"] == required
    assert (census["boolean-rule-v1"]["minimum_p_resolution"][
        "required_clusters"] - census["boolean-rule-v1"]["cluster_count"]
            == required - 1)

    assert census["boolean-rule-v1"]["available_family_coverage"] == {
        "dev": 1, "qual": 1, "audit": 1}
    assert census["software-fault-repair-v1"][
        "available_family_coverage"] == {"dev": 3, "held_out": 6}
    assert census["boolean-rule-v1"]["actual_assessment_counts"] == {
        "episodes": 3, "by_split": {"dev": 2, "qual": 1}}
    assert census["software-fault-repair-v1"][
        "actual_assessment_counts"] == {
            "episodes": 3, "by_split": {"dev": 2, "held_out": 1}}
    assert census["crossing_coverage_sufficient"] is False


def test_a_failed_acquisition_stays_a_no_acquisition_row(store):
    """Nothing authored is counted as acquired.

    B12 measured zero acquired lineages on the SWE construction run and B17
    measured the route answering in prose rather than emitting a policy at a
    served budget of 2048 tokens. So the crossing runs the real worlds and
    reports what they scored; it does not hand an arm a program and record
    the result as acquisition. This lane runs no acquisition at all, and the
    mission must say so.
    """
    _cross(store)
    from experiments.ad01 import mission

    entry = mission.read_mission(store, MISSION_ID)

    assert entry.acquired_artifacts == [], (
        "the crossing acquired %r without running an acquisition, which is "
        "the substitution this lane must not make"
        % (entry.acquired_artifacts,))
    assert entry.retained_use is None, (
        "retained_use is set with no acquired artifact to retain")
    assert entry.frontier["acquisition"] == "not-attempted", (
        "the mission records an acquisition outcome it did not run")
