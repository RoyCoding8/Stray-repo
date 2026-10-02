"""E3 post-fix: the ladder, its divergence case, and what reached the store.

The committed `e3-crossover.json` was produced at `02ce64b` and never
regenerated. `crossover()` builds one policy instance per (budget,
policy) and reuses it across all three worlds, and both policies are
stateful, so world 1's trajectory decided what world 2 was permitted to
pick. `sever_control` already builds a fresh policy per cell; the ladder
never did.

Three store defects are pinned here because each produced a number that
read as a measurement.

The first is the shared instance. The second is a study ceiling of
`max_model_calls: 0`, which is *reached at 0* by a `domain-command`
operation because `_study_operation_counts` only ever increments
`model_calls` for an operation whose stored effect is `model-inference`.
A zero ceiling is therefore a refusal of everything, not a statement
that no model was called, and it turned 42 admitted operations into 42
refusals.

The third is the count itself. `selection.DecisionRecorder` seeds a
parentless allocation, so its operations are settled and receipted but
invisible to the store's own contamination scanner, and a count taken
that way under-reports by half. It is the same class as ledger N-301,
which recorded the pre-fix witness measuring `count(*)` over the whole
table and crediting a foreign lane's row to E3.

Every assertion here is proved to fail by breaking the thing it guards,
and the break is named next to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import agenda_policy, e3_ladder, selection

# --- the shared instance ---------------------------------------------------


def test_one_policy_instance_walks_every_world_in_the_committed_ladder(migrated_db):
    """The defect, named in the shape it has at the tip.

    Break by moving `policy = make_policy()` back inside the world loop
    of `s09_e3_selection.crossover`, which is where it was at `02ce64b`.
    """
    from experiments.ad01 import s09_e3_selection as e3

    policy = agenda_policy.agenda_policy()
    first = e3.run_policy(policy, 0, 14)
    second = e3.run_policy(policy, 1, 14)

    assert len(first.choices) and len(second.choices)
    assert first.policy_version == second.policy_version


def test_a_fresh_ladder_moves_every_cell_the_committed_one_moved(migrated_db):
    """The fix is not cosmetic: the sharing changed all twelve cells.

    Break by returning to a single instance in `e3_ladder.ladder`, or by
    comparing shared against shared.
    """
    shared = e3_ladder.ladder(shared=True)
    fresh = e3_ladder.ladder(shared=False)

    delta = e3_ladder._delta(shared, fresh)
    assert delta["measures_compared"] == 48, (
        "the ladder compares four measures across two policies and six "
        "budgets; a different count means the matrix shape moved")
    assert delta["measures_changed_by_the_shared_instance"] > 0, (
        "sharing one policy across worlds changed nothing, so the "
        "committed artifact was not describing a shared traversal")


def test_each_world_in_a_fresh_cell_is_an_independent_run(migrated_db):
    """Two fresh cells on the same world at the same budget agree.

    Break by sharing the instance between the two cells.
    """
    left = e3_ladder._run_arm("agenda", 14, (0, 1), shared=False)
    right = e3_ladder._run_arm("agenda", 14, (0, 1), shared=False)

    assert left["yield_totals"] == right["yield_totals"]
    for a, b in zip(left["cells"], right["cells"]):
        assert a["yield"]["choices"] == b["yield"]["choices"]


def test_the_committed_artifact_is_reproducible_from_the_current_code(migrated_db):
    """The committed file is a faithful record of what `crossover` does.

    This is the finding that makes the regeneration meaningful. If the
    committed file did not reproduce, the defect would live in the
    artifact alone and a fixed `crossover` would be a different
    experiment. Break by changing any number in `crossover`.
    """
    import json

    from experiments.ad01 import s09_e3_selection as e3

    committed = json.loads((
        ROOT / "reports" / "evidence" / "inv_r1_e3_selection"
        / "e3-crossover.json").read_text())
    fresh = e3.crossover()

    assert committed["measure_digest"] == fresh["measure_digest"]
    for a_step, b_step in zip(committed["ladder"], fresh["ladder"]):
        for a_arm, b_arm in zip(a_step["arms"], b_step["arms"]):
            assert a_arm["policy"] == b_arm["policy"]
            assert a_arm["held_out_reduction_mean"] == \
                b_arm["held_out_reduction_mean"], (
                "budget %d %s no longer reproduces the committed ladder"
                % (a_arm["budget"], a_arm["policy"]))
            assert a_arm["yield_totals"] == b_arm["yield_totals"]


# --- the treatment is active ----------------------------------------------


def test_the_two_policies_choose_different_investigations(migrated_db):
    """The handoff's diagnostic case, and every cell that has one.

    Break by pointing both arms at the same policy factory, or by
    returning `False` from `_picks_differ`.
    """
    survey = e3_ladder.divergence_survey()

    assert survey, "no (world, budget) cell where the two policies differ"
    for case in survey:
        left = [(p[0], p[1]) for p in case["agenda_picks"]]
        right = [(p[0], p[1]) for p in case["control_picks"]]
        assert left != right
        assert case["first_divergence_at_choice"] == 0, (
            "a cell recorded as divergent diverged only after agreeing "
            "for %d choices, so the census is measuring a stall"
            % case["first_divergence_at_choice"])


def test_divergence_is_a_real_choice_and_not_a_stall(migrated_db):
    """A diverging cell runs different work, not zero work.

    Break by returning `None` from one of the policies, which makes it
    stop at once and would otherwise read as maximal divergence.
    """
    survey = e3_ladder.divergence_survey(worlds=(0,), budgets=(14,))
    assert survey, "world 0 at budget 14 is the nominated case and does not differ"

    case = survey[0]
    assert case["agenda_picks"] and case["control_picks"], (
        "one arm chose nothing, so the policies did not differ in what "
        "they chose")
    assert case["agenda_reasons"] and case["control_reasons"]
    assert all("pre-committed" not in r for r in case["agenda_reasons"]), (
        "the agenda arm is replaying the control's own authored schedule")


def test_the_divergence_survey_covers_the_whole_matrix(migrated_db):
    """Break by dropping a world or a budget from the survey."""
    assert len(e3_ladder.WORLDS) == 3
    assert len(e3_ladder.BUDGETS) == 6
    full = e3_ladder.divergence_survey()
    assert len(full) <= len(e3_ladder.WORLDS) * len(e3_ladder.BUDGETS)
    assert {c["budget"] for c in full} == set(e3_ladder.BUDGETS), (
        "at least one budget has no divergent cell, so the ladder is not "
        "showing a choice at that envelope")


# --- the frozen measures ---------------------------------------------------


def test_the_four_yields_are_frozen_before_the_run(migrated_db):
    """Break by redefining a measure, or by loosening the pinned digest."""
    digest = selection.assert_measure_freeze()
    assert digest == selection.FROZEN_MEASURE_DIGEST
    assert set(selection.YIELD_MEASURES) == {
        "retained_behaviors", "held_out_reduction", "diagnoses_correct",
        "resources_used"}


def test_the_ladder_reports_all_four_measures_for_both_arms(migrated_db):
    """Break by dropping a measure from `_measure` or from `direction`."""
    payload = e3_ladder.ladder(shared=False)

    assert payload["measure_digest"] == selection.FROZEN_MEASURE_DIGEST
    for step in payload["ladder"]:
        assert {a["policy"] for a in step["arms"]} == {"agenda", "control"}
        for arm in step["arms"]:
            for key in ("retained_behaviors", "diagnoses_correct",
                        "resources_used"):
                assert key in arm["yield_totals"]
            assert "held_out_reduction_mean" in arm
    for row in payload["direction"]["per_budget"]:
        for key in ("held_out_reduction", "retained_behaviors",
                    "diagnoses_correct", "resources_used"):
            assert "agenda_ahead_on_" + key in row
            assert "control_" + key in row


# --- the store -------------------------------------------------------------


def test_decisions_reach_admitted_operations_with_receipts(migrated_db):
    """The handoff's line 73, counted by SELECT rather than by report.

    Break by dropping the `dsn=` from the `run_investigations` call in
    `store_ladder`, or by removing `dispatch_operation` from `_admit`.
    """
    from settlement import authority

    with _authorized(migrated_db) as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)
        verdict = e3_ladder.store_verdict(migrated_db, study_root)

        assert payload["arms"], "the store half ran no cells"
        assert verdict["operations_in_store"] > 0
        assert verdict["receipts_in_store"] == \
            verdict["operations_in_store"], (
            "an operation settled without a receipt, or a receipt names no "
            "operation")
        assert verdict["every_settled_operation_has_a_success_receipt"]
        assert verdict["every_operation_carries_a_decision"]
        assert verdict["receipt_payload_matches_operation"]


def test_the_store_count_is_read_both_ways_and_both_are_published(migrated_db):
    """Two independent reads, and they must now agree.

    The walk below is the query the store's own isolation gate uses. It
    once could not see the allocation the `DecisionRecorder` seeded
    outside the study, so the two reads disagreed and the run reported
    42 of 84 operations. `store_ladder` now seeds that allocation as a
    child of the study's own, so agreement is the assertion. INVERTED,
    per `tests/test_s09_controls.py:158`; this control asserted a defect
    and the defect is repaired, so it is inverted rather than deleted.

    Both reads stay in the verdict, because two reads that agree are
    still two reads. Break by making `_operation_rows` return one path
    only, or by dropping `walk_missed` from the verdict.
    """
    from settlement import authority

    with _authorized(migrated_db) as study_root:
        e3_ladder.store_ladder(migrated_db, study_root)
        verdict = e3_ladder.store_verdict(migrated_db, study_root)

        assert verdict["operations_in_store"] > 0
        assert sum(verdict["per_path"].values()) == \
            verdict["operations_in_store"]
        assert verdict["per_path"]["admit_study_call"] > 0, (
            "nothing went through authority.admit_study_call, so the "
            "decisions bypassed the durable reservation owner")
        assert verdict["per_path"]["decision_recorder"] > 0, (
            "the run's own recorder admitted nothing, so the second tree "
            "is untested")
        assert verdict["walked_operation_count"] == \
            verdict["operations_in_store"], (
            "the parentage walk found %d operations but the store holds %d "
            "under this study; the operations it missed are real and "
            "receipted, and no study-scoped read can see them"
            % (verdict["walked_operation_count"],
               verdict["operations_in_store"]))
        assert verdict["walk_agrees_with_prefix"], (
            "the durable-name count and the parentage walk disagree, so "
            "one of them is under-reporting this study")
        assert not verdict["walk_missed"]
        assert verdict["every_counted_operation_is_this_study"], (
            "a counted row was not minted by this study, which is N-301: "
            "an unscoped count credits a foreign lane's row to the run")
        assert "N-301" in verdict["counting_method"]


def test_a_foreign_rows_row_is_not_counted(migrated_db):
    """The pre-fix witness measured `count(*)` over the whole table.

    N-301 records that a foreign lane's row was credited to E3 that way.
    This run counts by durable name prefix, so a row written under
    another study's allocation is invisible to it. Break by replacing
    the prefix filter with `count(*)` over the table.
    """
    from settlement import authority, db

    with _authorized(migrated_db) as study_root:
        e3_ladder.store_ladder(migrated_db, study_root)
        before = e3_ladder.store_verdict(migrated_db, study_root)
        with db.read_connect(migrated_db) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM operations")
                whole_table = cur.fetchone()[0]
            conn.commit()
            with db.connect(migrated_db) as write:
                # A real allocation under another study's authority, so
                # the row is well formed and the only thing separating
                # it from this run's count is the name.
                write.execute(
                    "INSERT INTO allocations (id, parent_id, domain, epoch,"
                    " authorized, amount_scale, max_occupancy, owner_scope)"
                    " VALUES ('nobody-elses-alloc', NULL, 'cpu', 0, 10, 1,"
                    " 8, '') ON CONFLICT (id) DO NOTHING")
                write.execute(
                    "INSERT INTO operations (id, allocation_id, payload,"
                    " payload_digest) VALUES ('somebody-elses-row',"
                    " 'nobody-elses-alloc', '{}', 'not-our-digest')")
                write.commit()

        after = e3_ladder.store_verdict(migrated_db, study_root)
        with db.read_connect(migrated_db) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM operations")
                grown = cur.fetchone()[0]
            conn.commit()
            with db.connect(migrated_db) as write:
                write.execute("DELETE FROM operations"
                              " WHERE id = 'somebody-elses-row'")
                write.execute("DELETE FROM allocations"
                              " WHERE id = 'nobody-elses-alloc'")
                write.commit()

    assert whole_table == before["operations_in_store"], (
        "the whole table holds %d rows and this study's prefixes cover %d, "
        "so writing one more row cannot be shown to be ignored"
        % (whole_table, before["operations_in_store"]))
    assert grown == whole_table + 1
    assert after["operations_in_store"] == before["operations_in_store"], (
        "a row this study did not write changed the count, which is the "
        "N-301 defect reproduced here")
    assert after["walked_operation_count"] == \
        before["walked_operation_count"], (
        "the foreign row was also counted by the parentage walk, which "
        "means the study subtree resolved to a row it does not own")


def test_the_per_arm_count_is_never_copied_from_the_run(migrated_db):
    """The run's own admission tally must equal what the store holds.

    The verdict counts per arm across the whole ladder, so the run's
    tally is summed per arm first; comparing a per-cell figure against a
    per-arm total would be a comparison of two different quantities.
    Break by summing `arm["admitted"]` into the verdict, or by
    classifying arms by position rather than by name.
    """
    from settlement import authority

    with _authorized(migrated_db) as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)
        verdict = e3_ladder.store_verdict(migrated_db, study_root)

        reported = {"agenda": 0, "control": 0}
        for arm in payload["arms"]:
            reported[arm["policy"]] += arm["admitted"]

        assert sum(reported.values()) == verdict["per_path"][
            "admit_study_call"], (
            "the run admitted %d decisions through admit_study_call, the "
            "store holds %d under the study allocation"
            % (sum(reported.values()),
               verdict["per_path"]["admit_study_call"]))
        assert sum(reported.values()) + verdict["per_path"][
            "decision_recorder"] == verdict["operations_in_store"], (
            "the two admission paths account for %d of %d operations"
            % (sum(reported.values()) + verdict["per_path"][
                "decision_recorder"], verdict["operations_in_store"]))
        for policy, count in reported.items():
            assert count > 0, (
                "arm %s admitted nothing through admit_study_call" % policy)
            assert verdict["per_arm"][policy]["success_receipts"] >= count


def test_the_recorder_writes_a_second_tree_the_walk_now_sees(migrated_db):
    """Both admission paths write real operations, and both are adopted.

    This asserted the opposite, and passed only while the defect was
    live. `selection.DecisionRecorder` seeded a parentless per-cell
    allocation, so its operations were settled and receipted but
    invisible to `s09_run_isolation._persisted_operations`, and the run
    reported half the work it did. `store_ladder` now seeds that
    allocation as a child of the study's own, so the walk sees both
    trees and the gap closes. INVERTED, per the convention at
    `tests/test_s09_controls.py:158`; a control that asserts a defect
    must be inverted when the defect is repaired, not deleted.

    The two paths stay separate. Adoption parents the recorder's
    allocation; it does not make the recorder's path the same as
    `admit_study_call`'s, and `per_path` is what shows both are still
    exercised. Break by classifying the second tree as if it were the
    first, or by dropping the adoption so the walk sees one tree again.
    """
    from settlement import authority

    with _authorized(migrated_db) as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)
        verdict = e3_ladder.store_verdict(migrated_db, study_root)

        recorder = sum(arm["recorder_admitted"] for arm in payload["arms"])
        assert recorder > 0, (
            "the run's own recorder admitted nothing, so the second tree "
            "is untested")
        assert verdict["per_path"]["decision_recorder"] == recorder
        assert verdict["per_path"]["admit_study_call"] == \
            verdict["operations_in_store"] - recorder
        assert verdict["walked_operation_count"] == \
            verdict["operations_in_store"], (
            "the parentage walk found %d of %d; the recorder's tree is "
            "still outside the study subtree, so half this run wrote is "
            "invisible to a study-scoped read"
            % (verdict["walked_operation_count"],
               verdict["operations_in_store"]))
        assert verdict["walk_agrees_with_prefix"], (
            "the two reads of the same study disagree, so a count taken "
            "either way reads as a different number of operations")
        assert not verdict["walk_missed"]
        assert verdict["every_recorder_operation_is_adopted_under_the_study"]


def test_a_refusal_is_reported_rather_than_dropped(migrated_db):
    """A ceiling that refuses the work must appear as a refusal.

    A store with room admits everything, so the refusal has to come from
    a store that has run out. Break by filtering `refused` out of the
    payload, by raising instead of returning, or by admitting through a
    path that cannot be refused.
    """
    from settlement import authority

    with _refused(migrated_db) as study_root:
        admitted = [e3_ladder._admit(
            migrated_db, study_root, "development",
            "e3ladder-root-op-bogus-%d" % i, {"target": "x"})
            for i in range(3)]

    first, second, third = admitted

    assert first["admitted"] is True, (
        "the first operation should fit inside the ceiling; if it did not, "
        "the refusal this test needs is not a ceiling refusal")
    assert second["admitted"] is True, (
        "the study authorized two units and only one was spent; the second "
        "operation should also fit: %r" % second)
    assert third["admitted"] is False, (
        "the third operation exceeded the authority and was admitted "
        "anyway: %r" % third)
    assert third["refusal"] == "insufficient-authority"
    assert "free" in third["detail"], (
        "the refusal names %r, so it did not come from exhausted authority"
        % third["detail"])


def test_a_refused_decision_still_leaves_the_runs_own_record_intact(migrated_db):
    """A refusal is recorded on the run, not silently dropped.

    `DecisionRecorder` never raises on a refusal, so a run whose
    operations the store rejected still produced a decision, and the
    record of it has to survive. Break by swallowing the refusal, by
    returning an empty `refusals`, or by raising.
    """
    from settlement import authority

    with _authorized(migrated_db) as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)

    for arm in payload["arms"]:
        accounted = arm["recorder_admitted"] + len(arm["recorder_refusals"])
        assert accounted == arm["decisions"], (
            "arm %s at budget %d: %d decisions, %d admitted, %d refused; "
            "one of them went unrecorded"
            % (arm["policy"], arm["budget"], arm["decisions"],
               arm["recorder_admitted"], len(arm["recorder_refusals"])))
        for refusal in arm["recorder_refusals"]:
            assert refusal["settled"] is False
            assert refusal["operation_id"]
            assert refusal["code"]


def test_a_zero_model_call_ceiling_no_longer_refuses_a_domain_command(migrated_db):
    """A7, inverted. This control passed only while the defect was present.

    It asserted the opposite: that `max_model_calls: 0` refuses a
    `domain-command`, because `_study_operation_counts` increments
    `model_calls` only for a `model-inference` effect and the ceiling
    was compared against an operation that spends no model call. That
    turned 42 admitted operations into 42 refusals.

    The store now checks a ceiling only against the counters the
    operation would actually spend, so a zero model-call ceiling means
    zero model calls. Inverted rather than deleted: the same query
    proves the repair, and a study that binds a ceiling it cannot
    spend against is still refused below. Break by comparing every
    ceiling against every operation again.
    """
    from settlement import authority, broker, loop, store

    assert store.is_ceiling_enforced("max_model_calls")
    with _authorized(migrated_db) as study_root:
        authority.authorize_study(
            migrated_db, "e3ladder-zerocap", authorized=1_000,
            allocation_id="e3ladder-zerocap-alloc",
            ceilings={"max_operations": 64, "max_model_calls": 0,
                      "max_development": 64})
        admitted = e3_ladder._admit(
            migrated_db, "e3ladder-zerocap", "development",
            "e3ladder-root-op-zeroceiling", {"target": "x"})
        spent = authority.admit_study_call(
            migrated_db, "e3ladder-zerocap", kind="development",
            operation_id="e3ladder-root-op-zerocap-model",
            effect=broker.MODEL_INFERENCE,
            payload={"model": "test-model",
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": 8})

    assert admitted["admitted"] is True, (
        "max_model_calls=0 refused a domain-command, which spends no "
        "model call: %r" % admitted)
    assert not isinstance(spent, loop.Grant), (
        "a zero model-call ceiling admitted a model-inference: %r" % spent)
    assert "max_model_calls=0" in getattr(spent, "detail", ""), (
        "the model call was refused by something other than the zero "
        "ceiling: %r" % getattr(spent, "detail", ""))


def test_the_study_does_not_bind_the_ceiling_that_would_refuse_it(migrated_db):
    """The repair: the bound ceilings admit the whole matrix.

    Break by putting `max_model_calls: 0` back into `study_ceilings`,
    which silently turns every admitted operation into a refusal.
    """
    cap = e3_ladder.cap_sheet(e3_ladder.ladder(shared=False, worlds=(0,)),
                              study_root="e3ladder-root",
                              authorized_units=100_000)
    ceilings = e3_ladder.study_ceilings(cap)

    assert "max_model_calls" not in ceilings, (
        "binding a counter the store never increments for this effect is "
        "how the whole store half was refused at zero")
    assert ceilings["max_operations"] == cap["max_operations"]
    assert ceilings["max_development"] == cap["max_operations"]


def test_every_bound_ceiling_is_one_the_store_can_enforce(migrated_db):
    """`authorize_study` refuses a name it does not know, so the bound set
    and the declared set cannot be the same dict.

    Break by folding the model-call declaration back into the ceilings,
    which `authorize_study` rejects before the study starts.
    """
    from settlement import store

    cap = e3_ladder.cap_sheet(e3_ladder.ladder(shared=False, worlds=(0,)),
                              study_root="e3ladder-root",
                              authorized_units=100_000)
    ceilings = e3_ladder.study_ceilings(cap)
    declaration = e3_ladder.model_call_declaration()

    for name, value in ceilings.items():
        assert store.is_ceiling_name(name), (
            "authorize_study refuses %r outright" % name)
        assert store.is_ceiling_enforced(name), (
            "%r is a declared-only ceiling, so the store records it and "
            "never checks it" % name)
        assert isinstance(value, int) and value > 0

    assert declaration["model_calls_the_matrix_produces"] == 0
    assert declaration["bound"] is False
    assert set(declaration) & set(ceilings) == set(), (
        "a name in both dicts would be bound by authorize_study whether or "
        "not the study meant to bind it")


def test_a_ceiling_above_the_plan_admits_everything(migrated_db):
    """The cap sheet the study actually binds, and it is finite.

    Break by returning a round number from `cap_sheet`, or by removing a
    ceiling from `build`.
    """
    cap = e3_ladder.cap_sheet(e3_ladder.ladder(shared=False, worlds=(0,)),
                              study_root="e3ladder-root",
                              authorized_units=100_000)
    assert cap["max_operations"] > 0
    assert cap["model_calls_the_matrix_produces"] == 0
    assert cap["provider_dispatches_the_matrix_produces"] == 0
    assert cap["offline_cells"] and cap["store_cells"]
    assert isinstance(cap["widest_cell_decisions"], int)
    assert cap["widest_cell_decisions"] > 0, (
        "the cap is derived from the widest cell, so a zero here means the "
        "ladder ran no decisions and every other number is a fiction")

    with _authorized(migrated_db) as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)
        assert not [a for a in payload["arms"] if a["refused"]], (
            "a cell was refused under the study's own cap sheet: %r"
            % [a["refused"] for a in payload["arms"] if a["refused"]])


def test_the_gateway_probe_never_records_the_credential(migrated_db):
    """Break by writing the credential into the probe's record."""
    import os

    record = e3_ladder.probe_gateway()

    assert record["credential_recorded"] is False
    assert record["max_tokens"] == e3_ladder.PROBE_MAX_TOKENS
    assert record["gateway"] == e3_ladder.GATEWAY
    secret = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    assert not secret or secret not in json_text(record), (
        "the probe's record contains the gateway credential")


def test_the_probe_reports_absence_rather_than_raising(migrated_db):
    """A missing credential is availability evidence, not a crash.

    Break by letting the urllib call escape.
    """
    import os

    previous = os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
    try:
        record = e3_ladder.probe_gateway()
    finally:
        if previous is not None:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous

    assert record["status"] in e3_ladder.PROBE_STATUSES
    if not record["credential_present"]:
        assert record["status"] == "no-credential"


def test_this_pins_the_retired_statuses_and_cannot_pass_by_accident(
        migrated_db):
    """The allowlist above used to be a literal four and passed for the
    wrong reason.

    `http-error` and `unreachable` were the vocabulary of a probe that sent
    through `urllib` and reported the exception. `80582d8` routed the send
    through the broker and retired both, so the literal could name a status
    no branch returns, and the assertion survived only because this file
    pops the credential first, so the one branch it does name is always
    `no-credential`. The pin is now the module's own constant, and this
    test is what makes that pin mean something: it says the constant equals
    the six statuses the current probe can actually return.

    Break by adding a status to `PROBE_STATUSES` that no branch produces.
    """
    assert set(e3_ladder.PROBE_STATUSES) == {
        "no-credential", "unadmitted-no-authority", "unadmitted", "no-route",
        "no-settled-response", "reachable"}, (
        "the probe's status vocabulary has drifted from the branches that "
        "produce it: %r" % sorted(e3_ladder.PROBE_STATUSES))

    import os

    previous = os.environ.get("SETTLEMENT_GATEWAY_KEY")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = "e3-ladder-vocabulary-key"
    try:
        with_no_authority = e3_ladder.probe_gateway()
    finally:
        if previous is None:
            os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
        else:
            os.environ["SETTLEMENT_GATEWAY_KEY"] = previous

    assert with_no_authority["status"] == "unadmitted-no-authority", (
        "the stale allowlist could not express this status at all, so a "
        "probe that reached it was untested: %r" % with_no_authority)
    assert with_no_authority["status"] in e3_ladder.PROBE_STATUSES


# --- helpers ---------------------------------------------------------------


def json_text(value) -> str:
    import json

    return json.dumps(value, default=str)


def _authorized(dsn: str):
    """A study root whose ceilings admit this study's own operations.

    `max_model_calls` is the number of model-inference operations the
    matrix can produce, which is zero, and that zero is what the store
    enforces today against every effect. The number here is therefore
    chosen from the count the store actually applies rather than from
    the count the ladder conceptually makes.
    """
    import contextlib

    from settlement import authority

    @contextlib.contextmanager
    def bind():
        handle = authority.authorize_study(
            dsn, e3_ladder.STUDY_ROOT, authorized=100_000,
            allocation_id=e3_ladder.STUDY_ALLOCATION,
            ceilings={"max_operations": 512, "max_development": 512})
        try:
            yield handle.study_root
        finally:
            _wipe(dsn, handle.study_root, e3_ladder.STUDY_ALLOCATION)

    return bind()


def _refused(dsn: str):
    """A study root whose child allocations run out.

    `admit_study_call` refuses with `insufficient-authority` when the
    study's allocation has no free units left, and every study operation
    takes one from it. Two units of parent authority, one per operation,
    so the third is refused. A ceiling alone will not do it: each
    operation subdivides into its own child allocation carrying only its
    own exposure, so a per-study ceiling and a per-allocation ceiling read
    different tables.
    """
    import contextlib

    from settlement import authority

    @contextlib.contextmanager
    def bind():
        handle = authority.authorize_study(
            dsn, "e3ladder-tight", authorized=2,
            allocation_id="e3ladder-tight-alloc")
        try:
            yield handle.study_root
        finally:
            _wipe(dsn, "e3ladder-tight", "e3ladder-tight-alloc")

    return bind()


def _wipe(dsn: str, study_root: str, allocation_id: str) -> None:
    import contextlib

    from settlement import db

    with contextlib.suppress(Exception):
        with db.connect(dsn) as conn:
            conn.execute("DELETE FROM operations WHERE id LIKE %s"
                         " OR allocation_id LIKE %s",
                         (study_root + "-op-%", allocation_id + "/%"))
            conn.execute("DELETE FROM allocations WHERE id LIKE %s",
                         (allocation_id + "/%",))
            conn.execute("DELETE FROM study_authority WHERE study_root = %s",
                         (study_root,))
            conn.commit()


@pytest.fixture
def migrated_db():
    """A disposable, migrated store for one test only.

    Each test gets its own database. A shared one would carry the first
    test's `study_authority` row into the next, and `authorize_study`
    refuses a study root already bound with different authority fields,
    so the failure would read as a study defect rather than as fixture
    reuse.
    """
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("e3ladder")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)
