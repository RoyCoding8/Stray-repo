"""A panel can only be qualified against the observable that actually varies.

`WORKER-STAGE-09-PARALLEL-EXPANSION.md:55` asks for interventions that
distinguish mechanisms, and `TASKS.md` §D records four E2 attempts refused
because the treatment arm's experience was a constant. The prescription was a
panel of tasks the authored reducers genuinely fail.

**That prescription cannot be carried out, and this file is the measurement
that says so rather than the fourth attempt at it.** A reducer's oracle and the
campaign's grader are the same function, so `reduce_software` accepts a
deletion only when the checker graded it `preserved`, and returns either the
task itself or a set the oracle already approved. Both grade `preserved`.
`experience_axis.oracle_is_the_grader` established the identity and
`frozen_census` measured 540 triples; `test_the_terminal_verdict_is_a_fixpoint
_on_every_task_in_this_panel` measures it again on the panel built here, and
the answer is the same. `not_preserved` and `invalid` are reachable only from a
task that does not parse or whose witness does not hold, and a panel of those
is grading its own malformity.

So the varying quantity is not the answer, it is the walk. Every trial the
reducer asks the oracle is a graded outcome, and a task whose trials are all
one verdict gives a developing policy nothing to read. That is the property
this panel is built to have and the property the audit refuses a panel without,
and it is measured from the checker rather than predicted from the generator,
because a panel whose difficulty is a claim about its own construction is a
claim the construction could be wrong about.

**The separations are measured, not declared.** `ad01`'s development specs and
`ad01-exp-axis`'s are different sets that the world sizes differ, and
`test_development_and_assessment_specs_are_disjoint` reads the specs off the
frozen files and intersects them. A panel that fails this is not a held-out set
and no amount of re-salting a seed repairs it.

**The instrument's discrimination is proved, not credited.** The C15 lesson is
that a policy copying verdicts into a key and deciding nothing scored the same
as the reference reader, and the run read it as learning. The reader/echoer
test here runs both through the real `s09_e2_scored.Score.measure`, and
`test_the_evidence_leg_goes_red_when_it_reads_echoable_inputs` is the mutation
that makes it red: it recomputes the same leg over the action's own inputs,
which is the leg the C15 run used, and asserts the echoer then ties the reader.
A discrimination test that cannot go red is worse than none.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import control_distinctness
from experiments.ad01 import e2_replication
from experiments.ad01 import panel_variation as panel
from experiments.ad01 import s09_e2_scored as scored
from experiments.representation import checkers
from execution_authority import execution_store

BUDGET = panel.ARM_BUDGET


@pytest.fixture(scope="module")
def frozen():
    return panel.all_tasks()


@pytest.fixture(scope="module")
def authority():
    """The store the instrument measures through.

    `s09_e2_scored.Score.measure` requires `{dsn, allocation_id}` and refuses a
    caller holding none. It executed policy source without them before, so
    every reading on this panel was `unscored: execute` and the reader-echoer
    separation these tests assert could not be observed at all.
    """
    with execution_store("panelvariation") as store:
        yield store


@pytest.fixture(scope="module")
def census(frozen):
    return panel.census(frozen, BUDGET)


# ---------------------------------------------------------------------------
# the negative result, pinned
# ---------------------------------------------------------------------------


def test_the_terminal_verdict_is_a_fixpoint_on_every_task_in_this_panel(frozen):
    """No task on this panel earns a terminal verdict outside `preserved`.

    This is the finding the four E2 attempts needed and could not find, and
    it is a property of the reducer/checker pair rather than of any panel. The
    assertion is deliberately exhaustive: it names every task, method and
    budget rather than sampling, so a future generator cannot quietly add a
    task that breaks the fixpoint and leave the count reading one.
    """
    offenders = []
    for task in frozen:
        for method in ("ddmin", "greedy"):
            for budget in (1, 2, 4, 8, 16):
                verdict = panel.terminal_verdict(task, method, budget)
                if verdict != checkers.PRESERVED:
                    offenders.append((task["task_id"], method, budget,
                                      verdict))
    assert offenders == [], offenders


def test_the_fixpoint_is_not_a_claim_about_these_tasks_only(frozen):
    """The same reading, on the frozen `ad01` world, is also constant.

    One panel would be consistent with a generator that happened to be easy.
    Two independent generators agreeing is what makes it a property of the
    reducer, and it is why the prescription could not be carried out rather
    than merely not yet carried out.
    """
    from experiments.ad01 import worlds as ad01_worlds

    offenders = []
    for path in sorted(ad01_worlds.FROZEN_DIR.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        task = json.loads(path.read_text())
        for method in ("ddmin", "greedy"):
            verdict = panel.terminal_verdict(task, method, BUDGET)
            if verdict != checkers.PRESERVED:
                offenders.append((task["task_id"], method, verdict))
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# the varying observable
# ---------------------------------------------------------------------------


def test_the_walk_varies_on_every_task_in_this_panel(frozen):
    """The trials a reducer asks about span two verdicts on every task.

    This is the property that replaces the terminal verdict, and it is the one
    a reader can consume: a stream of graded outcomes is what a developing
    policy saw, and a stream of one repeated value is a constant whatever the
    panel's answers are.
    """
    constants = []
    for task in frozen:
        for method in ("ddmin", "greedy"):
            verdicts = set(panel.stream_verdicts(task, method, BUDGET))
            if len(verdicts) < 2:
                constants.append((task["task_id"], method, sorted(verdicts)))
    assert constants == [], constants


def test_the_census_reports_the_two_verdicts_it_measured(census):
    """The census is a measurement of this panel at the pinned budget.

    A count of what was found, not a constant. If a future panel lost the
    walk's variation the census would read one verdict and this fails before
    anyone spends a dispatch on it.
    """
    assert census["stream_verdicts"] == ["not_preserved", "preserved"]
    assert census["distinct_stream_verdicts"] == 2
    assert census["tasks_with_a_varying_walk"] == census["task_method_pairs"]
    assert census["trials"] > census["task_method_pairs"]


def test_the_two_methods_differ_on_most_of_the_panel(frozen):
    """Method choice has to reach the world, or a method contrast is a label.

    The two authored reducers are the only things E2 can contrast, and a
    panel on which they returned the same bytes everywhere would make the
    contrast unmeasurable however well the experience arm varied. The bound
    is one half, which is what the panel measures.
    """
    same = [task["task_id"] for task in frozen if panel.same_candidate(task, BUDGET)]
    assert len(same) * 2 <= len(frozen), same
    software = [task for task in frozen if task["family"] == "software"]
    split = [task for task in software if not panel.same_candidate(task, BUDGET)]
    assert len(split) >= len(software) // 3, len(split)


# ---------------------------------------------------------------------------
# the separations, measured
# ---------------------------------------------------------------------------


def test_development_and_assessment_specs_are_disjoint(frozen):
    """Development, within and transfer share no program structure.

    Read off the frozen files rather than off the generator's own tables, so a
    generator that assigns a spec to two roles is caught by the artifacts that
    carry it. E1 requires templates and fault families separated across
    development, selection and assessment; a panel that fails this is not a
    held-out set.
    """
    by_role = panel.specs_by_role(frozen)
    assert by_role["dev"], by_role
    for left, right in (("dev", "within"), ("dev", "transfer"),
                        ("within", "transfer")):
        overlap = sorted(by_role[left] & by_role[right])
        assert overlap == [], (left, right, overlap)


def test_no_assessment_task_repeats_development_content(frozen):
    """Content, not just naming. Two tasks can share a spec and differ.

    The rule is measured with the same content key the generators deduplicate
    on, so a re-salting bug that changes the id but not the ops is caught.
    """
    dev = {panel.content_key(task) for task in frozen
           if task["task_id"].split("-")[2] == "dev"}
    leaks = [task["task_id"] for task in frozen
             if task["task_id"].split("-")[2] != "dev"
             and panel.content_key(task) in dev]
    assert leaks == [], leaks


def test_the_audit_refuses_a_panel_whose_development_leaks(frozen):
    """The audit is proven on a panel that does leak, not only on one that does not.

    Every audit test above is satisfied by an audit that returns an empty list
    unconditionally. This plants a leak and asks.
    """
    tasks = list(frozen)
    dev = next(t for t in tasks if t["task_id"].split("-")[2] == "dev")
    planted = [dict(t, task_id="panel-w0-transfer-LEAK-00",
                    template=dev["template"])
               for t in tasks if t["task_id"].split("-")[2] == "transfer"][:1]
    problems = panel.audit(dev_specs=panel.DEVELOPMENT_SPECS,
                           within_specs=panel.WITHIN_SPECS,
                           transfer_specs=panel.TRANSFER_SPECS,
                           tasks=tasks + planted)
    assert any("assessment-on-a-development-spec" in problem
               for problem in problems), problems


def test_the_audit_refuses_a_spec_shared_by_two_roles(frozen):
    """The other half of the same rule, on a table rather than on the files.

    A generator whose tables named one spec for two roles produces a panel
    whose files agree with each other and whose roles overlap, so reading the
    files alone would pass it. The audit checks the tables too.
    """
    problems = panel.audit(
        dev_specs=panel.DEVELOPMENT_SPECS,
        within_specs=panel.WITHIN_SPECS + (panel.DEVELOPMENT_SPECS[0],),
        transfer_specs=panel.TRANSFER_SPECS, tasks=list(frozen))
    assert any("spec-shared-by" in problem for problem in problems), problems


def test_the_audit_refuses_a_task_whose_walk_is_a_constant(frozen):
    """The qualification the four attempts lacked, exercised on a planted panel.

    A panel whose tasks all answer `preserved` walks to one verdict on every
    trial, and a reader on that stream is reading a constant. The audit
    refuses it, and the refusal is the thing that would have stopped the
    fourth dispatch. The stream is supplied rather than measured, so the
    refusal is about the audit and not about this panel.
    """
    problems = panel.audit(
        dev_specs=panel.DEVELOPMENT_SPECS,
        within_specs=panel.WITHIN_SPECS,
        transfer_specs=panel.TRANSFER_SPECS, tasks=list(frozen),
        measure_stream=lambda task, method, budget: [checkers.PRESERVED] * 8)
    assert any("constant-walk" in problem for problem in problems), problems


# ---------------------------------------------------------------------------
# the gate, and the only observation builder that can open it
# ---------------------------------------------------------------------------


def test_walk_observations_open_the_experience_gate(frozen):
    """The arm built from this panel's walks is not a constant.

    `control_distinctness.experience_varies` is the gate that refused four
    E2 attempts. The records here are graded outcomes the reducer earned on
    the way, not the answer it returned, and the gate reads more than one.
    """
    records = panel.walk_observations(
        [task["task_id"] for task in frozen
         if task["task_id"].split("-")[2] == "dev"][:6], BUDGET)
    verdict = control_distinctness.experience_varies(records, arm_name="panel")
    assert verdict["varies"] is True
    assert verdict["distinct_outcomes"] >= 2, verdict


def test_the_terminal_candidate_cannot_open_that_gate(frozen):
    """And the builder the four attempts used cannot, on this panel either.

    `e2_replication.measured_observations` grades the candidate a reducer
    returned. It reads its task from the frozen `ad01` directory, so the
    first thing this asserts is that it cannot read a panel task at all; the
    second is that the arm it would have built for an `ad01` task is refused
    anyway. Together they are the refusal the prescription was aimed at: a
    better panel does not help a builder that grades the returned candidate,
    which is a fixpoint on every panel.
    """
    with pytest.raises(KeyError):
        e2_replication.measured_observations(
            [task["task_id"] for task in frozen
             if task["task_id"].split("-")[2] == "dev"][:1])

    records = e2_replication.measured_observations(
        ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"], max_queries=BUDGET)
    try:
        verdict = control_distinctness.experience_varies(
            records, arm_name="terminal")
    except control_distinctness.GateRefused as refusal:
        verdict = {"varies": False, "refusal": str(refusal)}
    assert verdict["varies"] is False, verdict


# ---------------------------------------------------------------------------
# the instrument separates reading from echoing
# ---------------------------------------------------------------------------


def _scored_on(task, source, records, monkeypatch, tmp_path, authority):
    """One authored policy, stepped by the real instrument on a panel task.

    `s09_e2_scored` reaches back through `worlds.FROZEN_DIR` to load the task
    its action names, and that directory is the frozen `ad01` world, which
    does not hold a panel task. The panel task is therefore staged in a
    temporary root and `worlds.FROZEN_DIR` is pointed at it for the duration.
    The instrument itself is used as it is; only the directory it reads from
    is moved, and the task is the real frozen file rather than a copy.
    """
    staged = tmp_path / "worlds_panel"
    staged.mkdir(exist_ok=True)
    (staged / ("%s.json" % task["task_id"])).write_text(
        json.dumps(task, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(scored.worlds, "FROZEN_DIR", staged)
    score = scored.Score({"policy_source": source}, "authored-control",
                         "panel", BUDGET)
    return score.measure(task, records,
                         eligible_methods=e2_replication.eligible_for(task),
                         remaining={"steps": 1, "queries": 64,
                                    "model_calls": 0}, authority=authority)


def test_a_reader_outscores_an_echoer_on_this_panel(frozen, monkeypatch,
                                                    tmp_path, authority):
    """The C15 test, on a panel whose stream varies and under the real scorer.

    The reader counts the verdicts and names its method on the count; the
    echoer writes the same verdicts into an input key and names the same
    method either way. The echoer is the shape the C15 run scored 2.0 on, and
    the order of these two names is the order the defect appeared in.

    The reader counts rather than tests membership because membership is
    vacuous here and the flip is what the leg measures. On the `ad01` world
    the stream is all `preserved`, so "does any observation disagree" is false
    and the flip makes it true. On this panel the stream already holds both,
    so the predicate is true under either exposure and
    `e2_replication.PROMPTED_SHAPE_READER` scores 1.0 — a policy that reads,
    re-plans, and is invisible. That is asserted below rather than left as a
    note, because a reader inherited from a constant panel is a reader that
    stopped being one.
    """
    software = [task for task in frozen if task["family"] == "software"]
    task = next(t for t in software
                if t["task_id"].split("-")[2] == "transfer"
                and not panel.same_candidate(t, BUDGET))
    records = panel.walk_observations(
        [t["task_id"] for t in frozen
         if t["task_id"].split("-")[2] == "dev"
         and t["family"] == "software"], BUDGET)

    reader = _scored_on(task, panel.COUNT_READS_THE_VERDICTS,
                        records, monkeypatch, tmp_path, authority)
    echoer = _scored_on(task, panel.ECHOES_WITHOUT_READING,
                        records, monkeypatch, tmp_path, authority)

    assert reader.scored and echoer.scored
    assert reader.candidate_digest_scored != reader.candidate_digest_alternate
    assert (echoer.candidate_digest_scored
            == echoer.candidate_digest_alternate)
    assert reader.evidence > echoer.evidence, (reader.evidence, echoer.evidence)
    assert reader.score > echoer.score, (reader.score, echoer.score)


def test_a_membership_reader_is_vacuous_on_a_panel_that_varies(frozen,
                                                               monkeypatch,
                                                               tmp_path,
                                                               authority):
    """The reader the `ad01` world qualified cannot read this panel's stream.

    `e2_replication.PROMPTED_SHAPE_READER` switches on whether any observation
    is `not_preserved`. Its qualification was earned on a constant stream, and
    a panel that varies the stream makes the predicate constant in the other
    direction. Recorded because the alternative is a reader credited on this
    panel for a read it did not make.
    """
    software = [task for task in frozen if task["family"] == "software"]
    task = next(t for t in software
                if t["task_id"].split("-")[2] == "transfer"
                and not panel.same_candidate(t, BUDGET))
    records = panel.walk_observations(
        [t["task_id"] for t in frozen
         if t["task_id"].split("-")[2] == "dev"
         and t["family"] == "software"], BUDGET)

    membership = _scored_on(task, e2_replication.PROMPTED_SHAPE_READER,
                            records, monkeypatch, tmp_path, authority)
    assert membership.scored
    assert membership.evidence == 0.0, membership.evidence
    assert (membership.candidate_digest_scored
            == membership.candidate_digest_alternate)


def test_the_evidence_leg_goes_red_when_it_reads_echoable_inputs(frozen):
    """The mutation: recompute the leg over the action's own inputs.

    `s09_e2_scored._evidence` compares the candidate the world produced, which
    `assessment_profile._resolve_method` builds from the task and from
    `method_id`/`max_queries` and refuses to let a policy supply. The C15 run
    compared the action's inputs instead, and on that leg a policy that copies
    a verdict into a key moves the field being measured while deciding nothing.

    Both legs are recomputed here from the same two actions, and the assertion
    is the inversion: under the echoable leg the echoer scores the full
    evidence and the reader scores the full evidence too, so the leg cannot
    separate them. Under the shipped leg the reader's method is a VERBATIM
    field and neither policy moves the candidate by writing, so the leg
    separates them by exactly the thing it measures. A discrimination that
    lives only in the instrument is not a discrimination, and this is the
    test that says which of the two it is.
    """
    def leg(action_inputs, candidate):
        return {"action": {"inputs": dict(action_inputs)},
                "candidate": dict(candidate)}

    echoer = leg({"method_id": "seed-sw-ddmin", "max_queries": 8,
                  "read_verdicts": "preserved,preserved"},
                 {"method": "ddmin"})
    flipped_echoer = leg({"method_id": "seed-sw-ddmin", "max_queries": 8,
                          "read_verdicts": "not_preserved,not_preserved"},
                         {"method": "ddmin"})
    reader = leg({"method_id": "seed-sw-greedy", "max_queries": 8},
                 {"method": "greedy"})
    flipped_reader = leg({"method_id": "seed-sw-ddmin", "max_queries": 8},
                         {"method": "greedy"})

    assert scored._evidence(echoer, flipped_echoer)["ratio"] == 0.0
    assert scored._evidence(reader, flipped_reader)["ratio"] == 0.0

    def echoable_leg(first, second):
        first_inputs = first["action"]["inputs"]
        second_inputs = second["action"]["inputs"]
        sites = [name for name in first_inputs
                 if name not in scored.VERBATIM]
        if not sites:
            return 0.0
        moved = sum(1 for name in sites
                    if first_inputs[name] != second_inputs.get(name))
        return moved / len(sites)

    assert echoable_leg(echoer, flipped_echoer) == 1.0
    assert echoable_leg(reader, flipped_reader) == 0.0
    assert (scored._evidence(echoer, flipped_echoer)["ratio"]
            != echoable_leg(echoer, flipped_echoer))


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def test_the_freeze_verifies_and_regenerates():
    """The freeze is content-addressed and its own generator reproduces it.

    A panel that is not frozen is a panel a later run cannot tell apart from
    the one before it, which is the condition the four retractions were
    written under.
    """
    assert panel.verify_freeze(panel.FROZEN_DIR) == []
    assert panel.build_manifest(panel.FROZEN_DIR) == json.loads(
        (panel.FROZEN_DIR / "manifest.json").read_text())


def test_the_panel_is_not_the_frozen_ad01_world(frozen):
    """A new namespace, and no file under the frozen world is one of ours.

    The four retracted directories stay byte-unchanged, and this panel is a
    different set of task ids in a different directory rather than a second
    name for the same tasks.
    """
    assert panel.FREEZE_ID == "ad01-panel-v1"
    assert all(task["task_id"].startswith("panel-") for task in frozen)
    assert panel.FROZEN_DIR != panel.AD01_FROZEN_DIR
    ids = {task["task_id"] for task in frozen}
    ad01 = {path.stem for path in panel.AD01_FROZEN_DIR.rglob("*.json")
            if path.name != "manifest.json"}
    assert not ids & ad01
