"""The E2 observable must read the policy's behaviour, not its vocabulary.

`reports/evidence/inv_r1_e2_challenge/RESULT.md` retracts five E2
contrasts because `diagnostic` was a dead field: identical between the
experience arm and the no-experience arm in every condition, so it carried
no signal in either direction. A later pass falsified the "it echoes the
most recent family token" reading that came first, and settled on the
weaker claim — a dead observable, which is a statement about the field and
not about the model.

A field can be dead for a reason that is about the proposal rather than
about the model. The learner asks for one JSON object holding a
`next_action` with a `kind` and a `diagnostic` drawn from
{software, graph, diagnostic_resolves} — a category label. Whatever the
model is shown, the label in the prompt is the label most likely to come
back, and nothing in that string says whether the policy built from it does
anything with the evidence it was handed.

So the tests here do not check that a scored observable exists. They check
the one property the dead field could not have: whether a policy reads its
observations changes its score, while a policy that ignores them does not.
If the two were indistinguishable, a scored observable would be a
better-looking dead field.

Three obligations, in the order the old one failed them:

- A verdict-reading policy and a policy identical except for ignoring the
  verdict score differently, on the same target task. Not "the bytes
  differ" — the executed actions and the checker's verdict on them.
- A context-echoing policy cannot earn the agreement leg by writing its
  context down, even handed a category that says what the answer is.
- A proposal that yields no scored policy is `unscored`, not zero, so a
  transport failure cannot be read as a result about the model.

The execution route is the one the campaign already has.
`method_exec.run_step_out_of_process` runs the returned bytes in a child
under real wall, CPU and output limits, and `assessment_profile.dispatch`
sends the admitted action through the shipped action dispatcher into
`method_exec.run_member_out_of_process`, where the checkers grade the
candidate. No local evaluator is written here: a local evaluator is a
second scorer, and a second scorer is a second thing to be wrong.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec
from experiments.ad01 import policy_step
from experiments.ad01 import s09_e2_scored as scored
from experiments.ad01 import worlds
from execution_authority import execution_store

SOFTWARE = "ad01-w1-dev-sw-00"


@pytest.fixture(scope="module")
def authority():
    """The store every measurement in this file executes against.

    One module-scoped store rather than one per test: creating and migrating a
    database is most of the cost and none of the subject, and every
    measurement here needs the same three keys to exist.

    The executor is idempotent on `operation_id`, and every call site below
    derives a distinct one from the bytes it is about, so a repeated
    measurement of the same policy on the same task reads back its first
    receipt instead of spending a second child, while a different policy or a
    different view still executes.
    """
    with execution_store("e2scored") as store:
        yield store
# The op this task's witness observation names. `materialize_view` carries
# the op list, so an observation can point at one of them.
WITNESS_OP = "o0"
GRAPH = "ad01-w1-dev-gr-00"

# ddmin reaches 3 of 14 ops on the software target and greedy stops at 7.
# The gap is what keeps the agreement leg separable, and it is measured
# here rather than assumed, so a change to the frozen world cannot quietly
# turn the control into a twin of the namer below.
DDMIN_METHOD = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle,"
    " method='ddmin', max_queries=max_queries)\n"
)

# The two policies that decide the key test. The reader believes the op a
# preserved observation names is the witness, and drops it from its plan;
# under a not_preserved observation it keeps every op. The second source
# is the same plan with the reader's two helpers removed, so the two differ
# by exactly the act of reading.
READS_THE_VERDICT = '''def _kept(view):
    kept = []
    for row in view["observations"]:
        if str(row["verdict"]) == "preserved":
            words = str(row["detail"]).split()
            if len(words) == 2 and words[0] == "ref":
                kept.append(words[1])
    return kept


def _witness(view, kept):
    if not kept:
        return -1
    ops = view["task_content"]["ops"]
    for index in range(len(ops)):
        if ops[index].get("id") in kept:
            return index
    return -1


def STEP(view, state):
    probe = view["_probe"]["method_source"] if "_probe" in view else ""
    if probe:
        return {"action": {"kind": "use_method",
                           "target": view["task_content"]["task_id"],
                           "inputs": {"method_source": probe,
                                      "entry": "ENTRY", "max_queries": 8},
                           "evidence_refs": [],
                           "requested_resources": {"queries": 8}},
                "state": {}}
    ops = view["task_content"]["ops"]
    kept = _kept(view)
    witness = _witness(view, kept)
    plan = [index for index in range(len(ops)) if index != witness]
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_source": _PACKED, "entry": "ENTRY",
                                  "max_queries": 8, "plan": plan,
                                  "witness": witness},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''

IGNORES_THE_VERDICT = '''def _witness(view):
    ops = view["task_content"]["ops"]
    for index in range(len(ops)):
        if "id" in ops[index]:
            return index
    return -1


def STEP(view, state):
    probe = view["_probe"]["method_source"] if "_probe" in view else ""
    if probe:
        return {"action": {"kind": "use_method",
                           "target": view["task_content"]["task_id"],
                           "inputs": {"method_source": probe,
                                      "entry": "ENTRY", "max_queries": 8},
                           "evidence_refs": [],
                           "requested_resources": {"queries": 8}},
                "state": {}}
    ops = view["task_content"]["ops"]
    witness = _witness(view)
    plan = [index for index in range(len(ops)) if index != witness]
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_source": _PACKED, "entry": "ENTRY",
                                  "max_queries": 8, "plan": plan,
                                  "witness": witness},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''

# A reader whose read reaches the world. It names a different method when a
# verdict says the op is not preserved, and `method_id` is the one field the
# resolver turns into a different reduction, so this is the pair the leg is
# built to separate: the two policies differ by the act of reading and the
# difference lands in the candidate rather than in a claim about one.
RE_ROUTES_ON_THE_VERDICT = '''def _method(view):
    for row in view["observations"]:
        if str(row.get("verdict", "")) == "not_preserved":
            return "greedy"
    return "ddmin"


def STEP(view, state):
    method = _method(view)
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": "seed-sw-%s" % method,
                                  "max_queries": 8},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''

IGNORES_THE_ROUTING = RE_ROUTES_ON_THE_VERDICT.replace(
    'if str(row.get("verdict", "")) == "not_preserved":', "if False:")

# Echoes the whole view into the action. A legal action, a real
# execution, a real candidate, and none of that is the score.
ECHOES_THE_VIEW = '''def STEP(view, state):
    probe = view["_probe"]["method_source"] if "_probe" in view else ""
    if probe:
        return {"action": {"kind": "use_method",
                           "target": view["task_content"]["task_id"],
                           "inputs": {"method_source": probe,
                                      "entry": "ENTRY", "max_queries": 8},
                           "evidence_refs": [],
                           "requested_resources": {"queries": 8}},
                "state": {}}
    rows = [{"observation_id": row["observation_id"],
             "task_id": row["task_id"], "verdict": row["verdict"]}
            for row in view["observations"]]
    action = {"kind": "use_method",
              "target": view["task_content"]["task_id"],
              "inputs": {"method_source": _PACKED, "entry": "ENTRY",
                         "max_queries": 8,
                         "diagnostic": "graph", "basis_references": rows,
                         "content": view["task_content"]["template"]},
              "evidence_refs": [],
              "requested_resources": {"queries": 8}}
    return {"action": action, "state": {"rows": len(rows)}}
'''

# The `diagnostic` field under a scored observable, on its own. One
# reachable plan, chosen by a category in the view, never by a verdict.
LABEL_ONLY = '''def STEP(view, state):
    probe = view["_probe"]["method_source"] if "_probe" in view else ""
    if probe:
        return {"action": {"kind": "use_method",
                           "target": view["task_content"]["task_id"],
                           "inputs": {"method_source": probe,
                                      "entry": "ENTRY", "max_queries": 8},
                           "evidence_refs": [],
                           "requested_resources": {"queries": 8}},
                "state": {}}
    if "stale-read" in view["task_content"]["template"]:
        diagnostic = "preserved"
    elif "stale-clear" in view["task_content"]["template"]:
        diagnostic = "not_preserved"
    else:
        diagnostic = "diagnostic_resolves"
    action = {"kind": "use_method",
              "target": view["task_content"]["task_id"],
              "inputs": {"method_source": _PACKED, "entry": "ENTRY",
                         "max_queries": 8, "diagnostic": diagnostic},
              "evidence_refs": [],
              "requested_resources": {"queries": 8}}
    return {"action": action, "state": {"diagnostic": diagnostic}}
'''

# Names a repertoire member. The name is in the view, so the policy does
# read it; the candidate it reaches is a property of the name alone.
NAMES_A_METHOD = '''def STEP(view, state):
    probe = view["_probe"]["method_source"] if "_probe" in view else ""
    if probe:
        return {"action": {"kind": "use_method",
                           "target": view["task_content"]["task_id"],
                           "inputs": {"method_source": probe,
                                      "entry": "ENTRY", "max_queries": 8},
                           "evidence_refs": [],
                           "requested_resources": {"queries": 8}},
                "state": {}}
    method_id = view["eligible_methods"][0]
    action = {"kind": "use_method",
              "target": view["task_content"]["task_id"],
              "inputs": {"method_id": method_id, "max_queries": 8},
              "evidence_refs": [],
              "requested_resources": {"queries": 8}}
    return {"action": action, "state": {"method_id": method_id}}
'''

# Its target is not the task, so the dispatcher refuses it. An action that
# is well-formed and governs nothing.
REFUSES_EVERYTHING = '''def STEP(view, state):
    return {"action": {"kind": "use_method",
                       "target": "somewhere-else",
                       "inputs": {"method_source": _PACKED, "entry": "ENTRY",
                                  "max_queries": 8},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''

RAISES = 'def STEP(view, state):\n    raise ValueError("no policy here")\n'

# Returns no envelope at all. Parses, passes the gate, and the driver
# refuses the shape. A different refusal from the one above, and it has to
# stay one: a policy that returned nothing is not a policy that decided to
# do nothing.
RETURNS_NOTHING = ('def STEP(view, state):\n'
                   '    return None\n')

# Names a method the target task has no repertoire for, so the dispatcher
# resolves nothing. A refusal on scope rather than on execution.
UNKNOWN_METHOD = '''def STEP(view, state):
    action = {"kind": "use_method",
              "target": view["task_content"]["task_id"],
              "inputs": {"method_id": "seed-graph-greedy", "max_queries": 8},
              "evidence_refs": [], "requested_resources": {"queries": 8}}
    return {"action": action, "state": {}}
'''

NEEDS_AN_IMPORT = ('def STEP(view, state):\n'
                   '    import json\n'
                   '    return {"action": {}, "state": {}}\n')


def _source(template: str, method: str = DDMIN_METHOD) -> str:
    return template.replace("_PACKED", json.dumps(method))


def _load(task_id: str) -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, task_id)


def _score(template: str, arm: str = "e2", **kwargs) -> scored.Score:
    return scored.Score({"policy_source": _source(template)},
                        "authored-control", arm,
                        kwargs.pop("max_queries", 8), **kwargs)


def _observations(verdicts, task_id: str = SOFTWARE) -> list:
    """Observations in the shape a trajectory records them.

    The detail names the op each observation is about, the way a real
    diagnostic observation names what it looked at. It is the only thing
    that ties a verdict to an op, so a policy reading only the verdict
    cannot act on one.
    """
    return [{"observation_id": "obs-%s-%d" % (task_id, index),
             "task_id": task_id,
             "capability_id": "ad01-%s" % task_id.split("-")[3],
             "verdict": verdict,
             "detail": "ref %s" % WITNESS_OP}
            for index, verdict in enumerate(verdicts)]


# ---------------------------------------------------------------------------
# the key test: reading the evidence, or not
# ---------------------------------------------------------------------------


def test_two_policies_differing_only_in_whether_they_read_score_differently(authority):
    """The test the dead `diagnostic` field could not pass.

    Same target task, same observations, same frozen world, same query
    budget, same checker, same dispatcher, same method run. The one
    difference is whether the policy names a different method when a
    verdict says the op is not preserved.
    """
    read = _score(RE_ROUTES_ON_THE_VERDICT).measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)
    unread = _score(IGNORES_THE_ROUTING).measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)

    assert read.scored and unread.scored, (read.detail, unread.detail)
    assert read.origin == unread.origin
    assert read.digest != unread.digest
    # Both governed, and both graded by the checker on their own candidate.
    assert read.leg_status()[scored.LEG_VALID_ACTION] == "pass"
    assert unread.leg_status()[scored.LEG_VALID_ACTION] == "pass"
    assert read.verdict == unread.verdict == "preserved"
    # The reader's read changes the method, and the method changes the
    # reduction, so the two candidates differ. That difference is the site.
    assert read.candidate_digest_scored != read.candidate_digest_alternate
    assert (unread.candidate_digest_scored
            == unread.candidate_digest_alternate)
    assert read.score > unread.score
    assert scored.LEG_EVIDENCE == "candidate_varies_with_evidence"


def test_a_read_that_never_reaches_the_world_scores_like_a_blind_policy(authority):
    """The plan-only reader, and the reason the leg does not read actions.

    This policy reads the verdicts, re-plans from them, and moves two
    input keys between the two exposures. Those keys are named nowhere in
    `assessment_profile._resolve_method`, so the world runs the same method
    and returns the same candidate either way. Under the old input-
    comparing leg it scored 2.00, which meant the instrument could not tell
    a read that does nothing from a policy that echoes, and ranked the
    first above a genuine re-route.
    """
    plan_only = _score(READS_THE_VERDICT).measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)
    echoer = _score(ECHOES_THE_VIEW).measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)

    assert plan_only.scored and echoer.scored
    # It does read, and the read is visible in its action.
    assert plan_only.action["inputs"]["plan"] != [0, 1, 2, 3, 4, 5, 6, 7, 8,
                                                   9, 10, 11, 12, 13]
    # And the read does not reach the world.
    assert (plan_only.candidate_digest_scored
            == plan_only.candidate_digest_alternate)
    assert (echoer.candidate_digest_scored
            == echoer.candidate_digest_alternate)
    assert plan_only.evidence == echoer.evidence == 0.0
    assert plan_only.score == echoer.score


def test_a_policy_that_reads_nothing_scores_the_same_under_two_observations(authority):
    """The control for the test above, so it cannot pass vacuously.

    A fixed plan has one reachable score. A scheme that rewarded a policy
    for looking at its input would have to move this one, and it must not.
    """
    blind = _score(IGNORES_THE_VERDICT)

    first = blind.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    second = blind.measure(_load(SOFTWARE), _observations(["not_preserved"]),
        authority=authority)

    assert first.scored and second.scored
    assert first.score == second.score
    assert first.evidence == second.evidence == 0.0
    assert first.quality == second.quality
    assert first.action["inputs"] == second.action["inputs"]


def test_the_evidence_leg_measures_dependence_on_the_verdict_not_on_its_length(authority):
    """Two observations of the same length, different verdicts.

    A scheme that scored an action for how much text it carried would pass
    a length check and fail this one. The method the reader commits to is
    shaped by the verdict it was shown; the other policy cannot move.
    """
    read = _score(RE_ROUTES_ON_THE_VERDICT)
    blind = _score(IGNORES_THE_ROUTING)

    kept = read.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    dropped = read.measure(_load(SOFTWARE), _observations(["not_preserved"]),
        authority=authority)
    unchanged = blind.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    unchanged_too = blind.measure(
        _load(SOFTWARE), _observations(["not_preserved"]),
        authority=authority)

    # The leg is the dependence itself, so it does not vary with which set
    # of verdicts the reading was taken under: both readings of the reader
    # score 1 because the world returns it a different candidate, and both
    # readings of the blind policy score 0 because it does not.
    #
    # The score is NOT `evidence + 1`. The benefit leg is the normalized
    # reduction the world actually produced, which on this task is 0.786 and
    # not a constant. These two assertions read 2.0 and 1.0 while the benefit
    # leg was still the `QUALITY` verdict bit, and they could not fail on a
    # Windows host because the whole file is `unscored` there. They are
    # asserted as a relation between the two readings instead of as literals,
    # because the literal is exactly the thing that changed.
    assert kept.evidence == dropped.evidence == 1.0
    assert unchanged.evidence == unchanged_too.evidence == 0.0
    # Each reading's score is that reading's own evidence plus its own
    # reduction. The two verdicts of one reader no longer score alike, and
    # that is the point of the repair: under the constant QUALITY leg they
    # always did, so a flipped verdict could not move the number. Here it
    # can, because the two verdict sets produce different candidates.
    assert kept.score == kept.evidence + kept.normalized_reduction
    assert dropped.score == dropped.evidence + dropped.normalized_reduction
    assert kept.score != dropped.score
    assert unchanged.score == unchanged.evidence + unchanged.normalized_reduction
    assert kept.score > unchanged.score
    assert kept.evidence_varied == kept.evidence_total == 1
    assert list(kept.evidence_sites) == [scored.CANDIDATE_SITE]
    assert list(unchanged.evidence_sites) == [scored.CANDIDATE_SITE]
    assert unchanged.evidence_total == 1
    # Under the preserved verdict the reader names ddmin and under the
    # flipped one it names greedy, and those two run to different sizes.
    assert kept.action["inputs"]["method_id"] == "seed-sw-ddmin"
    assert dropped.action["inputs"]["method_id"] == "seed-sw-greedy"
    assert kept.candidate_measure != dropped.candidate_measure


def test_the_evidence_leg_reads_the_candidate_and_not_the_action(authority):
    """What the leg is set on, and what is still set aside.

    The candidate is the site. `method_source` and `entry` remain in
    `VERBATIM` and remain excluded from the recorded inputs, so a reader can
    see which fields the policy declared rather than ran. They are not
    compared at all now: the leg has one site and it is not an input.
    """
    assert scored.VERBATIM == ("method_source", "source", "entry",
                               "method_id", "max_queries")
    assert "method_source" in scored.VERBATIM

    result = _score(RE_ROUTES_ON_THE_VERDICT).measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)

    assert "method_source" not in result.control_inputs
    assert "max_queries" not in result.control_inputs
    assert set(result.evidence_sites) == {scored.CANDIDATE_SITE}
    assert result.evidence_total == 1
    # `method_id` is never counted directly, and that is the point: it is
    # counted only through the reduction the named method actually ran.
    assert "method_id" not in result.control_inputs
    assert result.candidate_digest_scored != result.candidate_digest_alternate


# ---------------------------------------------------------------------------
# context cannot be echoed into a score
# ---------------------------------------------------------------------------


def test_a_policy_that_echoes_its_context_cannot_earn_the_agreement_leg_by_it(authority):
    """A context-echoing policy scores on execution, not on what it wrote.

    This policy writes the whole view into its action: the observation
    rows, a `diagnostic` label, the template. The action is legal, it
    executes out of process, and the world produces a real candidate from
    it. The score is the checker's verdict on that candidate, which is the
    same verdict the searching policy gets and the same the label-only
    policy gets, so the echo bought nothing.
    """
    echoer = _score(ECHOES_THE_VIEW)
    searcher = _score(IGNORES_THE_VERDICT)

    echoed = echoer.measure(_load(SOFTWARE),
                                _observations(["preserved"]),
                                authority=authority)
    searched = searcher.measure(_load(SOFTWARE),
                                _observations(["preserved"]),
                                authority=authority)

    assert echoed.scored and searched.scored
    assert [row["verdict"] for row in
            echoed.action["inputs"]["basis_references"]] == ["preserved"]
    assert echoed.action["inputs"]["diagnostic"] == "graph"
    # It copied its context into the action and the action was admitted and
    # executed, so the echo is real and the score is not read off it.
    assert echoed.candidate_measure == searched.candidate_measure
    assert echoed.verdict == searched.verdict == "preserved"
    assert echoed.agreement == searched.agreement == "pass"
    # It did read the verdicts, in the sense that it wrote them into its own
    # action. What it gained for that was the full evidence leg under the
    # old input-comparing observable, because the echoed string was the only
    # site a policy could move there. The leg now reads the candidate the
    # world produced, and the echo changed nothing about what the method
    # ran, so the echo buys nothing at all.
    assert echoed.evidence == 0.0
    assert list(echoed.evidence_sites) == [scored.CANDIDATE_SITE]
    assert list(searched.evidence_sites) == [scored.CANDIDATE_SITE]
    assert echoed.score == searched.score


def test_the_label_a_policy_carries_scores_nothing_on_its_own(authority):
    """The `diagnostic` field under a scored observable, tested directly.

    `LABEL_ONLY` and `ECHOES_THE_VIEW` are both label carriers and both
    run the same method. They carry different labels and write different
    context into their actions, and the score reads the same for both,
    because the score is the checker's grade on the candidate the world
    produced. A label cannot be the dependent variable, which is the
    finding the retraction rests on, and this is the check that the finding
    survives the new instrument.
    """
    labelled = _score(LABEL_ONLY)
    echoing = _score(ECHOES_THE_VIEW)

    left = labelled.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    right = echoing.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)

    assert left.scored and right.scored
    assert left.action["inputs"]["diagnostic"] == "preserved"
    assert right.action["inputs"]["diagnostic"] == "graph"
    assert left.action["inputs"] != right.action["inputs"]
    assert left.verdict == right.verdict == "preserved"
    assert left.candidate_measure == right.candidate_measure
    # Two policies, one task, one reduction. The benefit leg reads the
    # measure rather than the verdict, so it agrees here for the reason
    # that matters: both world-produced candidates removed the same number
    # of ops, not that both verdicts said `preserved`.
    assert left.quality == right.quality == left.normalized_reduction
    assert left.quality == (14 - left.candidate_measure) / 14
    assert left.agreement == right.agreement == "pass"
    assert list(left.evidence_sites) == [scored.CANDIDATE_SITE]
    # The echoing policy writes strictly more of its context into the
    # action and earns exactly the same evidence for it, because the leg
    # reads the candidate and neither policy changes the method that runs.
    assert right.evidence == left.evidence == 0.0


def test_the_grade_the_label_predicts_does_not_move_the_score(authority):
    """The same method, two templates, two predicted grades, one result.

    `LABEL_ONLY` reads the task's template and calls the candidate
    `preserved` on one template and `not_preserved` on another. The
    checker grades those two candidates on their own merits, so the label
    a policy writes down is never what the reading carries.
    """
    stale_read = _load(SOFTWARE)
    stale_clear = _load("ad01-w1-dev-sw-01")
    assert stale_read["template"] == "stale-read-2chain"
    assert stale_clear["template"] == "stale-clear-core"

    label = _score(LABEL_ONLY)
    left = label.measure(stale_read, _observations(["preserved"]),
        authority=authority)
    right = label.measure(stale_clear, _observations(["preserved"]),
        authority=authority)

    assert left.action["inputs"]["diagnostic"] == "preserved"
    assert right.action["inputs"]["diagnostic"] == "not_preserved"
    # The benefit leg reads the checker's measure, so it is derived from
    # what the world produced and never from the label the policy wrote.
    assert left.quality == left.normalized_reduction
    assert right.quality == right.normalized_reduction
    assert left.quality == (left.initial_measure
                            - left.candidate_measure) / left.initial_measure
    assert right.quality == (right.initial_measure
                             - right.candidate_measure) / right.initial_measure
    assert left.score == left.evidence + left.quality


def test_a_policy_that_names_a_method_rather_than_building_one_reaches_the_control(authority):
    """The control the agreement leg compares against is reachable.

    `NAMES_A_METHOD` reads the view for a repertoire name and emits
    `use_method`, so it runs `seed-sw-greedy`. The control on this task is
    `seed-sw-ddmin`, and the two reach different candidates, so a reader
    can see the agreement leg is a comparison of candidates and not a
    constant.
    """
    namer = _score(NAMES_A_METHOD)
    searcher = _score(IGNORES_THE_VERDICT)

    named = namer.measure(_load(SOFTWARE), _observations([]),
                          eligible_methods=["seed-sw-greedy"],
        authority=authority)
    searched = searcher.measure(_load(SOFTWARE), _observations([]),
        authority=authority)

    assert named.scored and searched.scored, (named.detail, searched.detail)
    assert named.selected_identity == "seed-sw-greedy"
    assert searched.selected_identity.startswith("inline:ENTRY:")
    assert named.candidate_measure == 7
    assert searched.candidate_measure == 3
    assert named.control_verdict == searched.control_verdict == "preserved"
    assert named.leg_status()[scored.LEG_AGREEMENT] == "pass"
    assert searched.leg_status()[scored.LEG_AGREEMENT] == "pass"
    # Same verdict, different candidates. A verdict alone would have been a
    # dead observable too, so the measure rides beside it and a reader can
    # see the two are not the same candidate.
    assert named.agreement == searched.agreement == "pass"
    # Different candidates, so a different benefit leg. Under the verdict bit
    # both were 1.0 and the arm that ran `seed-sw-greedy` (7 ops) scored the
    # same as the one that ran the inline searcher (3 ops) on a 14-op task.
    assert named.candidate_measure != searched.candidate_measure
    assert named.quality == (14 - named.candidate_measure) / 14
    assert searched.quality == (14 - searched.candidate_measure) / 14
    assert named.quality != searched.quality
    assert named.reason == ("the checker graded the candidate preserved "
                            "and the authored control ok-preserved")
    assert named.control_verdict == searched.control_verdict
    assert named.initial_measure == searched.initial_measure == 14


def test_the_agreement_leg_fails_when_the_candidate_is_not_preserved(authority):
    """The leg is not a constant, and this is what a failure looks like.

    A policy that hands the dispatcher a source it cannot execute never
    agrees with the control, and the reading says so rather than scoring it
    as a merely different plan.
    """
    empty_method = '''def ENTRY(task, oracle, max_queries=16):
    return {"candidate": {"family": "software", "task_id": "",
                         "ops": []}, "queries": 0}
'''
    garbled = _score(IGNORES_THE_VERDICT.replace(
        '"method_source": _PACKED,',
        '"method_source": %s,' % json.dumps(empty_method)))
    result = garbled.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)

    assert result.scored, result.detail
    assert result.verdict in {"invalid", "not_preserved", "unknown"}
    assert result.quality == 0.0
    assert result.leg_status()[scored.LEG_AGREEMENT] == "fail"
    assert result.leg_status()[scored.LEG_VALID_ACTION] == "pass"
    assert result.control_verdict == "preserved"
    assert result.score == result.evidence
    assert result.normalized_reduction == 0.0


# ---------------------------------------------------------------------------
# the scheme is bounded, and its refusals are not scores
# ---------------------------------------------------------------------------


def test_a_policy_that_never_governs_is_unscored_rather_than_zero(authority):
    """A transport failure is an absent result, not a bad one.

    The distinction the old field could not carry: an arm that produced no
    scored policy has not produced a worse policy, and a study that read
    it as zero would be reporting a dispatch failure as a result.
    """
    refused = _score(REFUSES_EVERYTHING)

    result = refused.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)

    assert not result.scored
    assert result.score == 0
    assert result.quality == 0.0
    assert result.evidence == 0.0
    assert result.detail.startswith("unscored: execute: ")
    assert set(result.leg_status().values()) == {"absent"}


def test_the_four_ways_a_policy_never_governs_are_all_unscored(authority):
    """Four refusals, four different reasons inside the one stage.

    Returns nothing, raises, names a method this task does not have, and
    aims its action at a task that is not the one it was handed. Each is a
    policy that did not govern, and each is absent rather than bad. A
    scheme that read any of them as a score of zero would be reporting a
    dispatch failure as a result about the model.
    """
    for template in (RETURNS_NOTHING, RAISES, UNKNOWN_METHOD,
                     REFUSES_EVERYTHING):
        result = _score(template).measure(_load(SOFTWARE),
                                          _observations(["preserved"]),
            authority=authority)

        assert not result.scored, template
        assert result.score == 0
        assert result.quality == 0.0
        assert result.evidence == 0.0
        assert result.action is None
        assert result.candidate is None
        assert result.verdict == ""
        assert result.agreement == scored.ABSENT
        assert result.detail == ("unscored: execute: the returned bytes "
                                 "admitted no action that reaches a method "
                                 "executor")


def test_a_policy_needing_an_import_is_refused_at_the_gate_not_scored(authority):
    """An unrunnable proposal is `unscored`, and the gate is named.

    `verify_step_source` is the campaign's own gate. A policy that needs an
    import cannot be run in the child at all, and scoring it against a
    hand-written substitute would measure the substitute.
    """
    needs_import = scored.Score({"policy_source": NEEDS_AN_IMPORT},
                                "authored-control", "e2", 8)

    result = needs_import.measure(_load(SOFTWARE), _observations([]),
        authority=authority)

    assert not result.scored
    assert result.detail == "unscored: gate: refused: imports-forbidden"
    with pytest.raises(method_exec.MethodExecutionError,
                       match="imports-forbidden"):
        method_exec.verify_step_source(NEEDS_AN_IMPORT, "STEP")


def test_every_non_scored_case_names_the_stage_that_refused_it(authority):
    """Four refusals, two stages, each named, and the messages differ.

    A reader who cannot tell a source the gate refused from bytes that
    will not run cannot tell a capability failure from a transport failure
    either, and that conflation is what the null-and-reversal discipline
    exists to prevent.
    """
    for text in ("not json at all", json.dumps({"notes": "here"})):
        with pytest.raises(scored.ScoreRefused, match="does not parse"):
            scored.proposal_source(text)

    stages = {}
    for source in (NEEDS_AN_IMPORT, RAISES, _source(REFUSES_EVERYTHING)):
        result = scored.Score({"policy_source": source},
                              "authored-control", "e2", 8).measure(
                                  _load(SOFTWARE), _observations([]),
            authority=authority)
        assert not result.scored, source
        assert result.score == 0 and result.quality == 0.0
        assert result.evidence == 0.0
        assert result.detail.startswith("unscored: ")
        stages[source] = result.detail.split(":", 2)[1].strip()
        assert stages[source] in ("gate", "execute"), result.detail

    assert sorted(set(stages.values())) == ["execute", "gate"]
    assert len(set(stages)) == 3


def test_a_missing_proposal_source_is_refused_rather_than_scored_as_empty(authority):
    """An arm that returned no bytes has not returned a policy.

    `None` and `""` are the two ways a study's record can say nothing came
    back. An empty source would pass a truthiness check somewhere
    downstream and read as a policy that chose to do nothing, which is the
    `diagnostic` failure in a different costume: a value that means nothing
    being read as a value.
    """
    for proposal in (None, {}, {"policy_source": ""}, {"policy_source": 7}):
        result = scored.Score(proposal, "authored-control", "e2", 8).measure(
            _load(SOFTWARE), _observations([]), authority=authority)

        assert not result.scored, proposal
        assert result.detail.startswith("unscored: gate: "), result.detail
        assert any(fragment in result.detail
                   for fragment in ("unparseable-python",
                                    "empty-policy-source", "artifact")), \
            result.detail


def test_a_family_with_no_authored_control_is_refused_rather_than_defaulted(authority):
    """The control is named, not assumed.

    A scheme that fell back to a default control for an unrecognised
    family would be comparing every arm against nothing in particular, and
    the agreement leg would read as a pass.
    """
    with pytest.raises(scored.ScoreRefused, match="authored control"):
        _score(IGNORES_THE_VERDICT).measure({"task_id": "t",
                                             "family": "quantum"},
                                            _observations([]),
            authority=authority)
    with pytest.raises(scored.ScoreRefused, match="task_id"):
        _score(IGNORES_THE_VERDICT).measure({"family": "software"},
                                            _observations([]),
            authority=authority)
    with pytest.raises(scored.ScoreRefused, match="authored method"):
        scored.inline_method({"family": "quantum"}, "ddmin")
    with pytest.raises(scored.ScoreRefused, match="authored control"):
        scored.control_name({"family": "quantum"}, "ddmin")


# ---------------------------------------------------------------------------
# the score is read from the world, not computed here
# ---------------------------------------------------------------------------


def test_the_grade_is_the_checkers_own_vocabulary_and_no_other(authority):
    """The score is not computed here.

    `checkers` emits preserved / not_preserved / invalid / unknown, and a
    scheme that graded its own arithmetic would be a second scorer. The
    benefit leg reads the checker's *measure* through that report rather
    than mapping its verdict to a bit, because the verdict is a fixpoint of
    the oracle that admits the trial: every candidate reaching a Reading
    came back `preserved`, so a bit taken from it was a constant.
    """
    result = _score(IGNORES_THE_VERDICT).measure(_load(SOFTWARE),
                                                 _observations(["preserved"]),
        authority=authority)

    assert result.reason == ("the checker graded the candidate preserved "
                             "and the authored control ok-preserved")
    assert result.initial_measure == 14
    assert result.normalized_reduction == (14 - result.candidate_measure) / 14
    assert result.quality == result.normalized_reduction
    assert result.score == pytest.approx(result.evidence + result.quality)
    assert 0 <= result.score <= scored.MAX_SCORE


def test_the_score_is_the_sum_of_two_legs_and_normalising_is_not_its_job(authority):
    """A weight between the legs is a pre-registration, not a default.

    Weighting agreement against evidence would have this module choosing on
    behalf of every study that used it, so the score is a plain sum and
    the two legs ride out beside it in the serialized reading.
    """
    result = _score(RE_ROUTES_ON_THE_VERDICT).measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)

    assert result.score == result.evidence + result.quality
    assert result.evidence == 1.0
    assert result.evidence_varied == result.evidence_total == 1
    assert 0 <= result.evidence <= 1
    # The benefit leg is a fraction of the task's initial measure, so it is
    # bounded by 1 but is not a bit: a policy that removed 11 of 14 ops
    # scores 11/14, and one that returned its input scores 0.0.
    assert 0.0 <= result.quality <= 1.0
    payload = result.as_dict()
    assert payload["evidence"] == result.evidence
    assert payload["quality"] == result.quality
    assert payload["score"] == result.score
    # The two candidate digests ride out beside the score, so a reader can
    # see the comparison the evidence leg made without rerunning anything.
    assert payload["candidate_digest_scored"] == result.candidate_digest_scored
    assert payload["candidate_digest_alternate"] \
        == result.candidate_digest_alternate
    assert payload["candidate_digest_scored"] != payload["candidate_digest_alternate"]


def test_the_executed_bytes_are_the_scored_bytes(authority):
    """The score is attributed to the source that ran, not to a claim.

    `executed_source` is the method the dispatcher ran, which for these
    policies is the source the policy put in the action. If it disagreed
    with the digest this reading is about, the reading would be about a
    stranger's bytes, which is the verified-entry-versus-executed-bytes
    defect the campaign has already paid for once.
    """
    result = _score(IGNORES_THE_VERDICT).measure(_load(SOFTWARE),
                                                 _observations(["preserved"]),
        authority=authority)
    in_process = hashlib.sha256(DDMIN_METHOD.encode("utf-8")).hexdigest()

    assert result.scored
    assert result.executed_source == DDMIN_METHOD
    assert result.digest != in_process
    assert result.selected_identity == "inline:ENTRY:%s" % in_process[:12]
    # And the source the policy put in its action is the source the
    # dispatcher ran, so the reading is about the method this policy named
    # and not about the policy bytes that named it.
    assert result.action["inputs"]["method_source"] == DDMIN_METHOD
    assert result.control == "seed-sw-ddmin"
    assert scored.STEP_METHOD_KINDS == ("construct_method", "use_method")


def test_the_probe_run_is_a_separate_view_and_never_the_scored_one():
    """The control's search space does not leak into the scored run.

    The probe view is the scored view plus one key, and the two are
    otherwise identical. A scheme that let the policy read the control
    during the run that is scored would be scoring a run the study never
    holds.
    """
    views = scored.build_views(_load(SOFTWARE),
                               _observations(["preserved"]))

    assert scored.PROBE_KEY in views["probe"]
    assert scored.PROBE_KEY not in views["scored"]
    assert scored.PROBE_KEY not in views["alternate"]
    stripped = {name: value for name, value in views["probe"].items()
                if name != scored.PROBE_KEY}
    assert stripped == views["scored"]
    assert views["probe"][scored.PROBE_KEY]["method_source"] == DDMIN_METHOD
    assert views["probe"][scored.PROBE_KEY]["control"] == "seed-sw-ddmin"


def test_the_probe_view_is_not_a_view_the_abi_owes_a_policy():
    """The probe key is this module's, and the ABI does not name it.

    `materialize_view` is the view a policy is entitled to; the probe key
    is added on top of it by this scheme alone. A caller reading the probe
    key as part of the contract would be reading a private seam.
    """
    assert scored.PROBE_KEY == "_probe"
    assert scored.PROBE_KEY not in policy_step.VIEW_REQUIRED
    assert policy_step.VIEW_REQUIRED == (
        "task_content", "observations", "open_questions", "last_result",
        "eligible_methods", "remaining", "contract_versions")
    task = _load(SOFTWARE)
    observations = _observations(["preserved"])
    assert scored.build_views(task, observations)["scored"] == \
        policy_step.materialize_view(
            task=task, observations=observations, open_questions=[],
            last_result=None, eligible_methods=[], remaining={"steps": 1})


# ---------------------------------------------------------------------------
# a reading is a value, and two of them are a contrast
# ---------------------------------------------------------------------------


def test_a_score_is_a_frozen_value_that_serializes_and_repeats(authority):
    """Two measurements of one policy and task are the same measurement.

    A result that varied run to run could not carry a contrast, and one
    that would not serialize could not be written to an evidence bundle.
    """
    score = _score(IGNORES_THE_VERDICT)

    first = score.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    second = score.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)

    assert first == second
    assert json.loads(json.dumps(first.as_dict())) == first.as_dict()
    assert first.as_dict()["digest"] == first.digest
    assert first.as_dict()["task_id"] == SOFTWARE
    assert first.as_dict()["scheme"] == scored.SCHEME
    assert first.as_dict()["scored"] is True


def test_a_contrast_is_a_word_with_a_rule_and_never_a_number(authority):
    """The reader-facing output is a verdict; the numbers ride beside it.

    `contract` refuses to compare readings of different tasks or different
    schemes, because a contrast between two instruments is a number and
    nothing else.
    """
    reader = _score(RE_ROUTES_ON_THE_VERDICT, arm="relevant")
    ignore = _score(IGNORES_THE_ROUTING, arm="no-experience")

    read = reader.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    unread = ignore.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    settled = scored.contract(read, unread)

    assert settled.outcome == "relevant"
    assert settled.left_arm == "relevant"
    assert settled.right_arm == "no-experience"
    assert settled.left_score > settled.right_score
    assert settled.rule == scored.CONTRACT_RULE
    # The reason names the winner, the loser, and both scores. A tie
    # reason would say neither, so this is what tells a win from a tie that
    # a comparison broke by hand.
    #
    # The scores are the measured ones, not the `2.000`/`1.000` the constant
    # QUALITY leg used to produce. Pinning the literals would pin the defect
    # back in; the format is pinned instead, since that is what this test is
    # actually about.
    assert settled.reason.startswith(
        "relevant scored %.3f against %.3f"
        % (settled.left_score, settled.right_score))
    assert settled.reason != "relevant scored 2.000 against 1.000"
    assert "on %s" % SOFTWARE in settled.reason
    assert "the candidate moved under flipped verdicts" in settled.reason
    assert json.loads(json.dumps(settled.as_dict())) == settled.as_dict()

    on_another = scored.Reading(**{**read.__dict__, "task_id": GRAPH})
    with pytest.raises(scored.ScoreRefused, match="not one contrast"):
        scored.contract(read, on_another)


def test_a_contrast_with_an_unscored_arm_is_unscored_and_names_the_arm(authority):
    """An absent result cannot be compared with a present one.

    This is the conflation the retraction's own lesson is about: a field
    that carries no signal invites a positive, and a zero invites a
    negative. Neither is a result.
    """
    reader = _score(READS_THE_VERDICT, arm="relevant")
    broken = _score(REFUSES_EVERYTHING, arm="no-experience")

    read = reader.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    dead = broken.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)
    settled = scored.contract(read, dead)

    assert settled.outcome == "unscored"
    assert settled.left_score > 0.0
    assert settled.right_score == 0.0
    assert "no-experience" in settled.reason
    assert "unscored: execute" in settled.reason


def test_a_contrast_between_two_equal_readings_is_a_tie_not_a_win(authority):
    """A tie is a tie, and it is not broken by hand.

    The campaign has two recorded ties already, and this is the third
    place the rule would otherwise lapse.
    """
    left = _score(IGNORES_THE_ROUTING, arm="relevant").measure(
        _load(SOFTWARE), _observations([]), authority=authority)
    # The echoer on no observations names no observation, so it copies
    # nothing into its action, and neither policy's read reaches the world.
    # Same evidence, same grade, same score.
    right = _score(ECHOES_THE_VIEW, arm="irrelevant").measure(
        _load(SOFTWARE), _observations([]), authority=authority)

    settled = scored.contract(left, right)

    assert left.evidence == right.evidence == 0.0
    assert left.quality == right.quality
    assert left.score == right.score
    assert left.score == left.evidence + left.quality
    assert settled.outcome == "tie"
    assert settled.reason == (
        "both readings scored %.3f on %s: the candidate did not move under"
        " flipped verdicts, the reduction leg read %.3f of the initial"
        " measure and the agreement leg read pass"
        % (left.score, SOFTWARE, left.quality))


# ---------------------------------------------------------------------------
# the proposal this scheme consumes
# ---------------------------------------------------------------------------


def test_a_parsed_proposal_scores_identically_to_its_response(authority):
    """The scheme consumes what the construction path settles.

    `construct.construct_policy` never hands raw source to its caller, so
    the entry has to be read back out of the response with the campaign's
    own parser. If a proposal could reach this scheme by another door, the
    bytes scored would not be the bytes returned.

    `origin` is passed in rather than defaulted, because this function
    hands `from_response` nothing that could earn one. The bytes here are
    a literal in this file, so the honest label is the study's own.
    """
    score = _score(IGNORES_THE_VERDICT)
    direct = score.measure(_load(SOFTWARE), _observations(["preserved"]),
        authority=authority)

    parsed = scored.Score.from_response(
        score.response(), 8, origin="authored-control").measure(
        _load(SOFTWARE), _observations(["preserved"]), authority=authority)

    assert parsed.digest == direct.digest
    assert parsed.score == direct.score
    assert parsed.action == direct.action
    assert parsed.origin == "authored-control"
    assert scored.proposal_source(score.response()) == score.source


def test_from_response_will_not_label_a_response_on_its_own():
    """The origin is the caller's to name, because the caller has the receipt.

    `from_response` used to default to `model-acquired`, so this file's own
    literal came back labelled as a live provider's bytes. Omitting the
    argument is now a TypeError rather than a claim.
    """
    score = _score(IGNORES_THE_VERDICT)
    with pytest.raises(TypeError):
        scored.Score.from_response(score.response(), 8)


def test_a_caller_can_name_a_stand_in_and_the_reading_says_so(authority):
    """The label survives the round trip when the caller earned it.

    The counterpart to the two tests above. If `from_response` dropped or
    overwrote the origin it was handed, this would read `authored-control`
    and the fix would be cosmetic.
    """
    score = _score(IGNORES_THE_VERDICT)
    for origin in ("model-acquired", "fixture-stand-in", "authored-control"):
        parsed = scored.Score.from_response(
            score.response(), 8, origin=origin)
        assert parsed.origin == origin
        reading = parsed.measure(_load(SOFTWARE), _observations(["preserved"]),
            authority=authority)
        assert reading.origin == origin


def test_the_control_is_named_and_a_study_can_choose_which_one_it_uses(authority):
    """The control is visible in the reading, and there is more than one.

    A scheme that hid which control it compared against would make its
    agreement leg unreadable, and a scheme with one control would be
    asserting that one control is the answer.
    """
    assert scored.control_candidates() == {
        "graph": {"ddmin": "seed-gr-ddmin", "greedy": "seed-gr-greedy"},
        "software": {"ddmin": "seed-sw-ddmin", "greedy": "seed-sw-greedy"}}

    default = _score(IGNORES_THE_VERDICT).measure(_load(SOFTWARE),
                                                 _observations([]),
        authority=authority)
    greedy = _score(IGNORES_THE_VERDICT, control_method="greedy").measure(
        _load(SOFTWARE), _observations([]), authority=authority)

    assert default.control == "seed-sw-ddmin"
    assert greedy.control == "seed-sw-greedy"
    assert default.control_verdict == greedy.control_verdict == "preserved"
    assert default.initial_measure == greedy.initial_measure == 14


def test_score_response_can_pass_the_eligible_methods_through():
    """The convenience entry point dropped the one argument that matters.

    `Score.measure` takes `eligible_methods` and `build_views` honours it,
    but `score_response` forwards `**kwargs` to the `Score` constructor
    rather than to `measure`. So a caller passing the family's controls
    got a `TypeError` from `Score.__init__`, and a caller who left it out
    got a view with `eligible_methods: []` — so every policy read an empty
    list, took the stop branch, and was reported as "admitted no action
    that reaches a method executor". Both are the same defect seen from
    two sides: the method list could not reach the view.
    """
    import inspect

    from experiments.ad01 import s09_e2_scored as scored

    signature = inspect.signature(scored.score_response)
    assert "eligible_methods" in signature.parameters, (
        "score_response must accept eligible_methods explicitly; forwarding "
        "**kwargs to the Score constructor sends it to the wrong call")
    assert "remaining" in signature.parameters
