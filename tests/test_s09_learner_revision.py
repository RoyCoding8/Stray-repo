"""E4's run, and the claims the result artifact is not allowed to make.

`improve_channel` owns the decision and its eligibility rule and has its own
tests. What was missing is the run: the frozen revision interface, the
acquisition gate, the three apparatus controls driven through real improve
rounds, and the descendant comparison. Those are what this file covers.

Two of these tests exist because the corresponding claim is one an artifact
can make dishonestly. `live_claim` re-derives the live-acquisition claim
from the dispatches rather than reading the campaign's own verdict, and the
guard test hands it a campaign that claims an acquisition it cannot support.
Without it the builder would write "live-acquired" over a dispatch with no
route behind it, which is the failure this study is most able to commit.

The controls are the part that does not need a provider, so they run here
rather than being asserted from the artifact. Each drives a real improve
round through `drive_improve_round` and is scored on the cohort the run
used, so a control that stopped qualifying would be red in this file before
any reader had to open the JSON.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "reports" / "evidence" / "inv_r1_e4"))

from experiments.ad01 import boolean_rule as br
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as lr

ARTIFACT = ROOT / "reports" / "evidence" / "inv_r1_e4" / "result.json"
CAMPAIGN = ROOT / "reports" / "evidence" / "inv_r1_e4" / "run" / "campaign.json"

SMALL_COHORT = list(range(24))
FULL_COHORT = list(range(150))


def _builder():
    spec = importlib.util.spec_from_file_location(
        "e4_make_result", ROOT / "reports" / "evidence" / "inv_r1_e4"
        / "make_result.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result() -> dict:
    assert ARTIFACT.exists(), (
        "E4 has a result artifact path but no result; %s is missing" % (
            ARTIFACT,))
    return json.loads(ARTIFACT.read_text())


def _drive(role, tmp_path):
    control = lr.build_control(role)
    record = lr._run_one(role, control["source"], control["control_id"],
                         control["label"], tmp_path, role)
    record["changed"] = lr.arm_changed_decision(record, control)
    return record


# --- the revision interface ------------------------------------------------


def test_the_revision_interface_names_one_executable_field():
    """A revision may change one thing, and the study says which.

    The interface is frozen before any dispatch, so what a reply is allowed
    to change cannot drift with the replies. It names a field in the
    vocabulary the channel actually executes: the `x` inside the probe
    action that `drive_improve_round` spends against the real instrument.
    """
    assert lr.REVISION_INTERFACE == (
        "improve_channel.STEP.frontier_action.probe.inputs.x")
    assert lr.FROZEN["evaluator"] == channel.EVALUATOR_ID
    assert lr.FROZEN["execution_limits"] == channel.EXECUTION_LIMITS
    assert set(channel.FROZEN_FIELDS) <= set(lr.FROZEN["frozen_fields"])


def test_the_frozen_state_does_not_move_while_a_revision_is_admitted(tmp_path):
    """Admission is the step a revision is closest to the authority.

    The grant, the used-so-far counters, the evaluator, the sealed results
    and the execution limits are compared as digests before and after, so a
    write is caught by the comparison rather than by the static check that
    precedes it.
    """
    store = _store_for(tmp_path)
    before = lr.frozen_state_digest(store)
    views = lr._admission_views(tmp_path, "frozen-view.json")
    verdict = lr.acquire(store, lr.build_control("known-effect")["source"],
                         views, arm="control")
    after = lr.frozen_state_digest(store)

    assert verdict["eligibility"] == channel.ELIGIBLE
    assert before == after
    assert verdict["frozen_state_digest"]


def _store_for(tmp_path, name="frozen-state.json"):
    store = frontier.create_store(
        tmp_path / name, namespace=frontier.NAMESPACE,
        mission=lr._mission(), authority={"queries": 16, "steps": 12})
    store.bind_active(channel.make_control("low"))
    return store


def test_a_revision_that_writes_the_frozen_authority_is_refused(tmp_path):
    """The refusal has to fire on bytes that are also otherwise eligible.

    Written into a probe's inputs rather than into a discarded branch, so
    the frozen-write check is the only thing that can catch it. A guard that
    only refused a revision which was ineligible for some other reason would
    pass this test by accident.
    """
    source = channel._revision_source("8").replace(
        '"x": 8', '"x": 8, "used": 0', 1).replace(
        '    step = state.get("step", 0)\n',
        '    step = state.get("step", 0)\n'
        '    used = 8 - len(view["experience"])\n', 1).replace(
        '"x": 8, "used": 0', '"x": 8 if used >= 0 else 8, "used": used', 1)
    verdict = lr.acquire(_store_for(tmp_path, "frozen-write.json"), source,
                         lr._admission_views(tmp_path, "frozen-write-view.json"))

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE


# --- the eligibility rule ---------------------------------------------------


def test_prose_is_refused_and_the_reason_is_kept():
    """A paragraph is not a revision, and saying so is not a measurement."""
    verdict = lr.judge_acquisition(
        "I would choose the input that maximises information gain.",
        operation_id="t-prose")

    assert verdict["acquisition"] == lr.UNUSABLE
    assert "STEP" in verdict["detail"]
    assert verdict["reply"]


def test_a_reply_that_is_the_incumbent_verbatim_is_refused_by_the_study(tmp_path):
    """Eligibility is not enough; there has to be a revision to attribute to.

    The channel's own rule would admit these bytes, and they are executable
    and they do select evidence. The study refuses them anyway, because a
    descendant that matches the incumbent's cannot tell anyone anything, and
    an arm that measured one would report a null with no cause.
    """
    verdict = lr.acquire(_store_for(tmp_path, "identity.json"),
                         channel.IMPROVE_LOW_SOURCE,
                         lr._admission_views(tmp_path, "identity-view.json"))

    assert verdict["eligibility"] == "identical-to-incumbent"


def test_a_literal_probe_input_is_refused_before_it_is_measured():
    """A fixed answer wearing a selector's syntax.

    The channel refuses a revision whose input cannot vary with the view.
    This catches the case the channel cannot: an expression that reads the
    view and evaluates to the same integer under every view the learner will
    ever be shown, which is what the live campaign returned six times.
    """
    literal = channel._revision_source("7")
    view_dependent = literal.replace(
        '"x": 7', '"x": 7 if not view["experience"] else 3', 1)

    assert lr.judge_acquisition(literal, operation_id="t-lit")[
        "acquisition"] == lr.UNUSABLE
    assert lr.is_constant_x(view_dependent) is False


def test_the_frozen_prompt_hands_over_the_skeleton_and_is_not_answered_by_copying_it():
    """The prompt carries the incumbent's value, and copying it is refused.

    The prompt does not withhold the incumbent's input. `template_for` is
    `IMPROVE_LOW_SOURCE`, so the model receives the whole program including
    `{"x": 3}`, and `INCUMBENT_EVIDENCE[0]` is 3. This test previously
    asserted the opposite under this name, which is why the name and the body
    disagreed.

    Carrying the value is deliberate, and two checks make it safe. The
    skeleton is the interface: `unauthorised_change` blanks the probed input on
    both sides and refuses anything that is not the same program afterwards,
    so a prompt without the incumbent's skeleton would yield replies refused
    for `step-skeleton` rather than revisions. And the value is the parrot
    defence: a verbatim echo is the incumbent's own bytes, so the identity
    check refuses it before it can be measured.

    The first assertion is the giveaway half, kept because it is a real
    property of the frozen bytes rather than a wish: the instruction prose
    names no input, so the only source of a number is the fenced template.
    """
    prompt = lr.prompt_for()
    template = lr.template_for()

    assert template == channel.IMPROVE_LOW_SOURCE
    assert '"x": %d' % channel.INCUMBENT_EVIDENCE[0] in template
    assert str(channel.INCUMBENT_EVIDENCE[0]) not in prompt["user"].split(
        "```python")[0]

    echo = "```python\n%s\n```" % template
    verdict = lr.judge_acquisition(echo, operation_id="prompt-echo")

    assert verdict["acquisition"] == lr.UNUSABLE, (
        "a verbatim echo of the template is the incumbent's own bytes; if it"
        " were acquired, the prompt would be answering itself")
    assert lr.differs_from_incumbent(template) is False


def test_a_skeleton_the_prompt_never_supplied_is_refused_for_that_skeleton():
    """Why the template is the interface rather than an answer key.

    A revision built on any program other than the incumbent's is refused for
    the skeleton it changed, even when its probed input is computed from the
    view and would otherwise pass every other gate. Without this, a prompt
    could drop the template as a giveaway and still measure nothing, because
    every reply would be refused here instead.
    """
    foreign = ('def STEP(view, state):\n'
               '    picked = 7 if not view["experience"] else 9\n'
               '    return {"action": {"kind": "probe",\n'
               '                       "inputs": {"x": picked},\n'
               '                       "requested_resources": {}},\n'
               '            "state": state}\n')

    assert channel._x_is_data_dependent(foreign) is True
    assert channel.unauthorised_change(
        channel.IMPROVE_LOW_SOURCE, foreign)["decision"] == "step-skeleton"


# --- the controls -----------------------------------------------------------


def test_the_reviewer_revision_is_admitted_and_changes_the_decision(tmp_path):
    """The known-effect control, driven through a real improve round.

    It names input 8 where the incumbent names 3, so the descendant it
    builds is not the incumbent's. Written to reach a real descendant rather
    than a refusal, because a control that cannot complete the journey
    qualifies nothing.
    """
    record = _drive("known-effect", tmp_path)

    assert record["eligibility"] == channel.ELIGIBLE
    assert record["x_probed"] == lr.REVIEWER_X
    assert record["candidate_id"], "no descendant was built"
    assert record["changed"]["changed_decision"] is True


def test_the_no_op_selects_the_incumbents_own_input_and_scores_exactly_zero(
        tmp_path):
    """Zero with no standard error, which is the point.

    A measured null has a standard error; a structural one does not. The
    no-op differs from the incumbent in nothing that reaches the
    descendant, so every paired difference is identically zero and the
    estimator has no spread to report. Asserting that the delta is zero and
    the standard error is zero together distinguishes the two, and a
    control that had quietly been given a different input would show a
    non-zero delta here.
    """
    record = _drive("no-op", tmp_path)
    paired = lr.compare(record["x_probed"], 3, split="audit",
                        seeds=SMALL_COHORT)

    assert record["x_probed"] == 3
    assert paired["measured"] is True
    assert paired["delta"] == 0.0
    assert paired["paired_se"] == 0.0
    assert paired["paired_sd"] == 0.0


def test_the_disconnect_is_refused_by_the_instrument_and_measured_as_nothing(
        tmp_path):
    """A decision that is spent and arrives at nothing.

    The difference from the no-op is the whole reason both are here. The
    no-op learns what the incumbent learns and scores zero; the disconnect
    builds no descendant at all, and reporting that as a large negative
    difference would turn a refusal at the boundary into an exceptionally
    bad result obtained by measurement.
    """
    record = _drive("disconnect", tmp_path)
    paired = lr.compare(record["x_probed"], 3, split="audit",
                        seeds=SMALL_COHORT)

    assert record["refused_by_instrument"] is True
    assert record["x_probed"] == -1
    assert not record["candidate_id"]
    assert paired["measured"] is False
    assert paired["delta"] is None
    assert paired.get("no_descendant") is True


def test_all_three_controls_qualify_the_apparatus(tmp_path):
    """Qualification comes from the controls alone.

    No run outcome is an input. A campaign that acquired nothing and a
    campaign that acquired a great revision are both only meaningful if this
    passes, which is why the check takes no arm.
    """
    arms = {}
    for role in lr.CONTROL_BUILDERS:
        control = lr.build_control(role)
        record = _drive(role, tmp_path)
        record["paired"] = lr.compare(record["x_probed"], 3, split="audit",
                                     seeds=SMALL_COHORT)
        record["control"] = control
        arms[role] = record
    verdict = lr.qualify(arms)

    assert set(verdict["checks"]) == set(lr.CONTROL_BUILDERS)
    assert verdict["qualified"] is True, (
        "a control misbehaved, so no run outcome would mean anything: %r"
        % (verdict["checks"],))


# --- the acquisition claim --------------------------------------------------


def test_the_builder_refuses_a_campaign_that_claims_what_it_cannot_show():
    """The one test here that is about the artifact rather than the run.

    A dispatch whose route, model and response digest have all been removed
    cannot be evidence that a model was reached, whatever the campaign
    claims about it. Without this the builder would write `live-acquired`
    over it, and that is the failure this study is most able to commit.
    """
    builder = _builder()
    campaign = json.loads(CAMPAIGN.read_text())
    campaign["dispatches"][0]["eligible"] = True
    campaign["dispatches"][0]["acquisition"] = lr.ACQUIRED
    campaign["dispatches"][0]["route"] = {}
    campaign["dispatches"][0]["source_digest"] = None

    try:
        builder.build(campaign)
    except builder.ResultRefused as exc:
        assert "route" in str(exc)
    else:
        raise AssertionError(
            "a campaign claiming an acquisition with no route behind it was"
            " written as a result")


def test_the_artifact_reports_the_cell_it_could_not_run():
    """An unrun cell is named, not omitted.

    The live arm produced six executable replies and admitted none, so the
    cell is reported as run-but-ineligible with the count. A report that
    simply omitted it would read as a study that never tried.
    """
    result = _result()
    cells = {cell["cell"]: cell for cell in result["cells"]}

    assert set(cells) == {
        "live-acquisition", "reviewer-authored-revision", "no-op-control",
        "disconnect-counterexample"}
    assert cells["live-acquisition"]["result"]
    assert result["verdicts"]["qualification"] == channel.QUALIFIED
    assert result["verdicts"]["benefit"] is False
    assert result["verdicts"]["scope"] is None


def test_the_qualification_and_the_acquisition_are_reported_separately():
    """A qualified apparatus and a failed acquisition are compatible.

    They are separate verdicts about separate things, and collapsing them is
    how a study reports "no benefit" when it means "no attempt", or the
    reverse. The artifact for this run qualifies and does not acquire, and
    both facts are load-bearing.
    """
    result = _result()

    assert result["verdicts"]["qualification"] == channel.QUALIFIED
    assert result["verdicts"]["acquisition"] == lr.INELIGIBLE_REPORTED
    assert result["verdicts"]["benefit"] is False
    assert "no eligible revision" in result["verdicts"]["benefit_basis"]


def test_the_null_is_bounded_by_a_measured_ceiling_and_a_wider_one():
    """Two ceilings, because the boundary and the decision are not the same.

    The narrow ceiling is the range this intervention can express. The wide
    one is the frozen reducer's own evidence selection, which is the real
    decision in this codebase and which has large headroom. Reporting only
    the narrow one would let a null be read as a property of evidence
    selection when it is a property of how `leaf_construct` builds a
    descendant.
    """
    result = _result()
    narrow = result["ceiling"]
    wide = result["evidence_ceiling"]

    assert narrow["measured"] is True
    assert narrow["n_seeds"] > 0
    assert wide["reducer_mean"] > wide["incumbent_mean"] * 2, (
        "the wider evidence decision lost its headroom, so the statement"
        " that the learner has room to improve is no longer measured: %r"
        % (wide,))
    assert result["evidence_ceiling"]["decision"] == "evidence-set-selection"


def test_no_model_byte_reaches_the_artifact_unattributed():
    """The gateway key is read at runtime and is nowhere in the result.

    The route is recorded because a dispatch is not reproducible without it,
    and the provider is recorded in the spelling the gateway attested rather
    than the spelling the freeze preferred, so the case fold is visible
    instead of silent.
    """
    result = _result()
    blob = json.dumps(result)

    assert "SETTLEMENT_GATEWAY_KEY" not in blob
    assert "Bearer" not in blob
    assert result["route"]["tier"] == "free"
    assert result["authority_deviation"]["observed"] is True
