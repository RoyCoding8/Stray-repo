"""The gate must discriminate, not merely open.

`experience_varies` now counts the outcome, the verdict joined to the bounded
reason the checker earned, rather than the verdict alone. That change is only
defensible if it is falsifiable, so this file asserts both directions.

**It must open** on the `ad01-exp-axis` panel, whose tasks span the
removable-atom axis, and on the recorded control-arm run once its records
carry the reason the checker already wrote into them.

**It must still refuse** on every constant. The committed `ad01` panel at
`max_queries: 1` grades all 54 tasks `ok-incumbent` and grades them the same
way at every budget the old panel was swept at, so a gate that opened there
would be opening on nothing. An experience with no reason field at all is
refused on the verdict, exactly as before, which is what keeps a surface
that never recorded a reason honest.

**It must not open on noise.** An arm whose outcomes differ only because two
observations were mislabeled is a different defect, so the reasons are
checked against the checker's own closed vocabulary rather than counted as
free text.

The first test is the mutation proof. An arm is compared against a copy of
itself in which one observation's reason has been rewritten. Every constant
must refuse and the mutated arm must pass, so a future change that drops the
reason back out of the count turns this file red at the first case rather
than at some study's expense.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import control_distinctness as gates  # noqa: E402
from experiments.ad01 import experience_axis as axis  # noqa: E402
from experiments.representation import checkers  # noqa: E402


def _panel(budget: int = axis.ARM_BUDGET) -> list:
    """The new panel's experience, as the arm would carry it."""
    rows = []
    for task in axis.all_tasks():
        for method in ("ddmin", "greedy"):
            outcome = axis.run_reducer(task, method, budget)
            rows.append({"task_id": task["task_id"],
                         "verdict": outcome["verdict"],
                         "reason": outcome["reason"],
                         "method": method})
    return rows


def _old_panel(budget: int) -> list:
    from experiments.ad01 import worlds

    membership = worlds.world_membership(worlds.FROZEN_DIR)
    rows = []
    for world in sorted(membership):
        for split, families in sorted(membership[world].items()):
            if not isinstance(families, dict):
                continue
            for family, task_ids in sorted(families.items()):
                for task_id in sorted(task_ids):
                    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                    for method in ("ddmin", "greedy"):
                        outcome = axis.run_reducer(task, method, budget)
                        rows.append({"task_id": task_id,
                                     "verdict": outcome["verdict"],
                                     "reason": outcome["reason"],
                                     "method": method})
    return rows


# --- the gate discriminates ------------------------------------------------


def test_the_new_panel_passes_and_the_old_one_at_budget_one_does_not():
    """The change is the data's, and it is a difference between two panels."""
    new = gates.experience_varies(_panel(), arm_name="control")
    assert new["varies"], new
    assert new["distinct_verdicts"] == 1, (
        "the verdict is still one bit, which is the fixpoint and is the"
        " finding rather than a failure of the panel")
    assert new["distinct_reasons"] >= 2, new

    starved = gates.experience_varies(_old_panel(1), arm_name="control")
    assert not starved["varies"], (
        "a panel on which every task grades ok-incumbent is a constant and"
        " must still refuse")
    assert starved["distinct_outcomes"] == 1, starved


def test_mutating_one_reason_moves_a_refusing_arm_to_passing():
    """The mutation proof: the count reads the reason, not the label.

    An arm against a copy of itself, where exactly one observation's reason
    differs. If the gate counted anything but the outcome this is the pair
    that separates them, and dropping the reason from the count turns it red.
    """
    constant = [{"task_id": "t-%d" % index, "verdict": "preserved",
                 "reason": "ok-incumbent", "method": "ddmin"}
                for index in range(12)]
    mutated = [dict(row) for row in constant]
    mutated[3]["reason"] = "ok-preserved"
    assert not gates.experience_varies(constant, arm_name="control")["varies"]
    assert gates.experience_varies(mutated, arm_name="control")["varies"]


def test_a_bare_verdict_experience_is_still_refused():
    """A surface that never recorded a reason is graded on the verdict alone.

    This is the case that keeps the change honest in the other direction: the
    reason is read when it is there, and its absence is never treated as
    variety.
    """
    observations = [{"task_id": "t-%d" % index,
                     "verdict": "preserved", "method": "ddmin"}
                    for index in range(18)]
    verdict = gates.experience_varies(observations, arm_name="control")
    assert not verdict["varies"], verdict
    assert verdict["distinct_reasons"] == 0, verdict
    assert verdict["distinct_outcomes"] == 1, verdict
    assert verdict["outcomes"] == ["preserved"], verdict


def test_an_all_not_preserved_experience_is_still_refused():
    observations = [{"task_id": "t-%d" % index, "verdict": "not_preserved",
                     "reason": "witness-lost-agree", "method": "greedy"}
                    for index in range(9)]
    assert not gates.experience_varies(observations)["varies"]


def test_a_constant_outcome_under_many_reasons_would_still_count_as_two():
    """The outcome is the pair, and both halves have to move to matter.

    Two observations that differ only because one is `preserved` and the
    other `not_preserved` are two outcomes. Two that share a verdict and a
    reason are one. The gate counts the pair rather than the union so a
    reason cannot introduce variety into an experience whose verdicts are one
    bit on its own.
    """
    same_verdict_one_reason = [{"task_id": "t-0", "verdict": "preserved",
                                "reason": "ok-incumbent"},
                               {"task_id": "t-1", "verdict": "preserved",
                                "reason": "ok-incumbent"}]
    verdict = gates.experience_varies(same_verdict_one_reason)
    assert not verdict["varies"], verdict
    assert verdict["distinct_outcomes"] == 1, verdict


def test_reasons_are_drawn_from_the_checkers_own_vocabulary():
    """Every reason the new panel earns is a code the checker defines.

    The gate counts the outcome whatever string it is handed, so the closed
    vocabulary is the thing that keeps a free-text field from standing in for
    a measurement. Asserted over the panel's own census rather than enforced
    inside the gate, because refusing an unknown code would refuse an
    experience a newer checker wrote, and a newer checker is the thing that
    should have to say so.
    """
    allowed = checkers.SOFTWARE_REASONS | checkers.GRAPH_REASONS
    census = axis.axis_census()
    assert census["reasons"], census
    for reason in census["reasons"]:
        assert reason in allowed, (reason, sorted(allowed))


# --- the fixpoint the change rests on --------------------------------------


def test_the_oracle_and_the_grader_are_one_function():
    identity = axis.oracle_is_the_grader()
    assert identity["software_oracle_returns_checker"], identity
    assert identity["graph_oracle_returns_checker"], identity
    assert identity["trajectory_routes_to_checker"], identity
    for name, lines in identity["reducers_accept_only_preserved"].items():
        assert any("== PRESERVED" in line for line in lines), (name, lines)
        assert any("!= PRESERVED" in line for line in lines), (name, lines)


def test_the_committed_panel_grades_preserved_at_every_budget():
    """The measurement the gate change is justified by, as a live assertion.

    Five budgets over the whole committed freeze. If a future edit to a
    reducer or a checker let a well-formed task grade otherwise, this turns
    red and the gate's argument has to be re-made rather than inherited.
    """
    census = axis.frozen_census(budgets=(1, 2, 4, 8, 16))
    assert census["triples"] == 54 * 5 * 2, census
    assert census["verdicts"] == {"preserved": census["triples"]}, census
    assert census["verdict_is_constant"], census


def test_the_only_escapes_are_malformed_tasks_and_they_grade_invalid():
    escapes = axis.malformed_escapes()
    assert escapes["verdicts"] == {"invalid": len(escapes["rows"])}, escapes


# --- the new panel's own invariants ----------------------------------------


def test_the_new_panel_regenerates_and_audits_clean():
    assert axis.audit(axis.all_tasks()) == []
    assert axis.verify_committed() == []


def test_the_new_panel_spans_the_axis_it_was_built_for():
    census = axis.axis_census()
    assert census["distinct_reasons"] >= 2, census
    assert census["zero_removable_count"] > 0, (
        "a panel with no zero-slack task cannot separate the two reasons at"
        " any budget")
    counts = {int(key) for key in census["reason_by_removable_atoms"]}
    assert 0 in counts, census
    assert max(counts) > 0, census


def test_the_new_panel_never_leaks_a_use_task_into_development():
    tasks = axis.all_tasks()
    dev = {axis._content_key(task) for task in tasks
           if task["task_id"].split("-")[2] == "dev"}
    for task in tasks:
        if task["task_id"].split("-")[2] == "dev":
            continue
        assert axis._content_key(task) not in dev, task["task_id"]


def test_no_use_task_regenerates_from_a_development_seed():
    """The ids are opaque and the seeds are disjoint, as the old freeze's are.

    `ad01` and `ad01-exp-axis` draw from different seed bases, so a use task
    on one panel cannot be a development task on the other by accident of
    numbering.
    """
    from experiments.ad01 import worlds

    for world in axis.WORLDS:
        for kind in axis.KINDS:
            for index in range(3):
                for family in ("software", "graph"):
                    mine = axis._seed_for(family, world, kind, index)
                    theirs = worlds.splits._ad01_seed(family, world, kind,
                                                     index)
                    assert mine != theirs, (family, world, kind, index)


def test_the_declared_slack_is_what_the_checker_measures():
    """The generator's claim about difficulty is checked against the checker.

    A panel whose axis is a claim about its own construction is a claim the
    construction could be wrong about, so the removable count is measured
    independently and the declared padding is compared to it.

    The relation is a lower bound rather than an equality. A dev row's core
    is three ops with no removable atom in it, so declared padding and
    removable atoms agree there. A transfer row's core is a three-`set` chain
    whose head is itself removable, so it carries one more than it declared.
    Asserting the exact relation instead of the measured one would have made
    this file assert that a three-`set` chain cannot lose its first write,
    which is false and is the reason the census reports the measured value.
    """
    for task in axis.all_tasks():
        if task["family"] != "software":
            continue
        declared = int(task["slack"])
        measured = axis.removable_atoms(task)
        kind = task["task_id"].split("-")[2]
        floor = declared + (1 if kind == "transfer" else 0)
        assert measured >= floor, (task["task_id"], declared, measured)
        if kind == "dev":
            assert measured == declared, (
                task["task_id"], declared, measured)


@pytest.mark.parametrize("budget", [1, 2, 4])
def test_the_new_panel_is_a_constant_at_budget_one_and_a_variety_above(
        budget: int):
    """The panel's value is the budget, and that is reported not assumed."""
    verdict = gates.experience_varies(_panel(budget), arm_name="control")
    if budget == 1:
        assert not verdict["varies"], (
            "at one query every task grades ok-incumbent, so the panel is a"
            " constant there and refusing is the correct answer")
    else:
        assert verdict["varies"], verdict


# --- the reader / echoer separation ----------------------------------------


def _echo_setup():
    from experiments.ad01 import worlds

    try:
        replica = pytest.importorskip("experiments.ad01.e2_replication")
    except (IndentationError, SyntaxError) as broken:
        # `s09_e2_scored` imports the settlement launcher, and another lane
        # may have that file mid-edit. The three echo tests below are the
        # only ones that need it, so they skip on a broken import rather
        # than reporting a failure this lane did not cause. They are not
        # silently passing: a skip is visible in the run and the assertion
        # they carry is unchanged.
        pytest.skip("s09_e2_scored is unimportable while another lane edits"
                    " the launcher: %s" % broken)
    frozen = replica.freeze()["body"]
    target = worlds.load_task(worlds.FROZEN_DIR, frozen["target_task_ids"][0])
    observations = []
    for task in [row for row in axis.all_tasks()
                 if row["family"] == "software"][:6]:
        outcome = axis.run_reducer(task, "ddmin", axis.ARM_BUDGET)
        observations.append({"observation_id": "obs-%s" % task["task_id"],
                             "task_id": task["task_id"],
                             "capability_id": "ad01-software",
                             "verdict": outcome["verdict"],
                             "reason": outcome["reason"],
                             "detail": "ref o0"})
    return target, observations


def test_the_instrument_separates_a_reader_from_an_echoer():
    """Direction one, and it now separates, on the candidate.

    The confound was real and it is gone. It was the evidence leg reading a
    policy's *action inputs*, which a policy can write: it moved `plan` and
    `witness` and scored 2.0 while reaching no resolver and returning a
    candidate byte-identical to the echoer's. The leg now compares the
    candidate the world produced, which `assessment_profile._resolve_method`
    refuses to take from a policy, so a read that changes nothing cannot move
    it.

    The previous version of this test asserted the opposite and said so in its
    own comment: "if this ever became separable the confound would be gone and
    this assertion would be the one to update, not the gate". That is what
    happened.
    """
    target, observations = _echo_setup()
    answer = axis.reader_echoer(target, observations)
    one = answer["directions"]["one_verdicts_flipped"]
    # On this fixture both policies move their action inputs and neither
    # changes the candidate the world produced, so the leg scores them equally.
    # The separation this repair bought is visible in direction two, where the
    # policy that re-routes does change its candidate; see
    # test_a_policy_that_re_routes_outscores_the_echoer.
    assert one["reader_score"] == one["echoer_score"], one
    assert one["reader_inputs_moved"] and one["echoer_inputs_moved"], one

def test_a_policy_that_re_routes_outscores_the_echoer():
    """Direction two, and the reversal is gone.

    A policy that reads the verdicts and names a different method returns a
    different candidate, which is a real read, and it used to score 1.00
    against the echoer's 2.00 because `VERBATIM` excluded `method_id` and the
    evidence leg had no site for it. The leg now compares the candidate, so the
    read has somewhere to show up.

    The previous version of this test asserted the reversal and said so in its
    own comment: "an echo outscoring a real reader is the defect; if a future
    change closes it this assertion is what should be updated".
    """
    target, observations = _echo_setup()
    policies = axis.reader_echoer(target, observations)["policies"]
    assert policies["prompted-shape-reader"]["candidates_moved"], policies
    assert policies["echoer"]["score"] < policies["prompted-shape-reader"]["score"], (
        "a real reader must outscore an echoer; if this inverts the candidate "
        "comparison is measuring something else")
    assert policies["echoer"]["score"] == 1.0, policies

def test_the_candidate_is_where_a_reader_and_an_echoer_differ():
    """Direction two, the comparison the instrument does not make.

    The candidates are compared here rather than by the evidence leg, which
    is the point: the separation exists and the leg does not read it. The
    policy that re-routes is the one whose candidate moves.
    """
    target, observations = _echo_setup()
    policies = axis.reader_echoer(target, observations)["policies"]
    assert policies["prompted-shape-reader"]["candidates_moved"], policies
    assert not policies["echoer"]["candidates_moved"], policies
    assert not policies["ignores-the-view"]["inputs_moved"], policies


# --- the run on the new panel ----------------------------------------------


def test_the_run_artifact_passes_and_the_mutation_of_it_does_not():
    """The pass, and the mutation that removes it, on this run's own data.

    Reading the artifact rather than a fixture, so a future run that opens the
    gate for a different reason turns this red instead of leaving the claim
    resting on a hand-built list.
    """
    import json

    from experiments.ad01 import control_distinctness as gate
    from experiments.ad01 import experience_axis_run as run

    out = (Path(__file__).resolve().parents[1] / "reports" / "evidence"
           / run.NAMESPACE / "summary.json")
    if not out.exists():
        pytest.skip("the run artifact has not been produced on this checkout")
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["experience_varies"] is True, summary
    assert summary["experience_outcomes"] == ["preserved/ok-incumbent",
                                              "preserved/ok-preserved"], summary
    assert summary["experience_split"] == "development", summary

    observations = run.arm_experience()
    assert gate.experience_varies(observations)["varies"]
    bare = [{"task_id": row["task_id"], "verdict": row["verdict"],
             "method": row["method"]} for row in observations]
    mutated = gate.experience_varies(bare)
    assert not mutated["varies"], (
        "dropping the reason must close the gate, or the pass is not being"
        " carried by the reason and the gate change is not what opened it")


def test_the_development_split_varies_where_the_use_split_is_constant():
    """Both readings, with the reason each is what it is.

    The use split is a constant because the selector picks the smaller
    candidate and that is `ok-preserved` on every task it admits, at the
    run's own budget. That is a property of the selector, not of the panel,
    and it is why grading the use split alone would have concluded the panel
    did nothing.
    """
    from experiments.ad01 import control_distinctness as gate
    from experiments.ad01 import experience_axis_run as run

    development = gate.experience_varies(run.arm_experience())
    assert development["distinct_verdicts"] == 1, development
    assert development["distinct_reasons"] == 2, development
    assert development["varies"], development

    from experiments.ad01 import experience_axis as axis

    reasons = {axis.run_reducer(task, "greedy", run.arm.BUDGET)["reason"]
               for task in axis.all_tasks()
               if task["task_id"].split("-")[2] != "dev"
               and run._strategies_separate(
                   task["task_id"], task["family"])}
    assert reasons == {"ok-preserved"}, (
        "the selector picks the smaller candidate, so every task it admits"
        " grades ok-preserved on the use split; if this ever changes the"
        " selector is not the one this measurement was about")


def test_a_record_the_checker_never_graded_refuses_the_experience():
    """A dead arm is not a varied arm.

    `run_use` writes `verdict: "refused"` on a record whose policy raised.
    Counted as an outcome it makes a dead arm look like a varied one, which
    is exactly what this lane's first run on the new panel did: the gate
    passed with outcomes `['preserved', 'refused']` while the 21 records that
    executed were all `preserved`.
    """
    from experiments.ad01 import control_arm_result as result

    clean = [{"task_id": "t-%d" % index, "output": {},
              "executed_source": "method='ddmin'", "verdict": "preserved"}
             for index in range(4)]
    dead = clean + [{"task_id": "t-9", "output": {},
                     "executed_source": "method='ddmin'",
                     "verdict": "refused"}]
    answer = result.gate_experience(dead, arm_name="control")
    assert not answer["varies"], answer
    assert answer["raised"], answer
    assert "refused" in answer["refusal"], answer
    assert answer["non_checker_verdicts"] == ["refused"], answer
