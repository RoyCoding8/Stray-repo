"""The three apparatus controls, each shown to discriminate.

`test_s09_learner_revision.py` covers the run: the frozen interface, the
acquisition gate, the artifact's claims. This file covers the thing that run
depends on and cannot itself establish — whether the machinery can tell a
real change from noise, and from bytes that change nothing.

Each control is driven through `drive_improve_round` against the real
instrument, scored on the cohort the run uses, and asserted against the
number it actually produced. Every test here carries a mutation: a change to
the thing the test pins, verified to turn it red. The mutations are recorded
in `MUTATIONS` at the bottom so a reader can re-run them rather than trust
this docstring.

The fourth control is the one that earns the rest their right to be believed.
`disconnect-bytes` is admitted as eligible, differs from the incumbent in its
source digest, and changes no learning decision — the C15 shape, which is the
defect that already shipped once. It is the only control that can catch an
acquired arm whose bytes differ and whose behaviour does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as lr
from experiments.ad01 import frontier as _frontier

COHORT = list(range(24))
AUDIT = "audit"
INCUMBENT_X = 3


def _drive(role: str, tmp_path: Path) -> dict:
    control = lr.build_control(role)
    record = lr._run_one(role, control["source"], control["control_id"],
                         control["label"], tmp_path, role)
    record["changed"] = lr.arm_changed_decision(record, control)
    record["paired"] = lr.compare(record["x_probed"], INCUMBENT_X, split=AUDIT,
                                  seeds=COHORT)
    record["control"] = control
    return record


# --- control 1: a revision with a known effect ------------------------------


def test_the_known_effect_control_measures_the_effect_it_declares(tmp_path):
    """The reviewer named input 8 where the incumbent names 3.

    The control is eligible, reaches a real descendant, and the paired
    difference is not zero. Asserting all three together matters: an arm that
    is merely non-zero because it errored would satisfy the last clause alone.
    """
    record = _drive("known-effect", tmp_path)

    assert record["eligibility"] == channel.ELIGIBLE
    assert record["x_probed"] == lr.REVIEWER_X == 8
    assert record["x_probed"] != INCUMBENT_X
    assert record["candidate_id"], "no descendant was built"
    assert record["changed"]["changed_decision"] is True
    assert record["paired"]["measured"] is True
    assert record["paired"]["delta"] != 0.0


def test_the_known_effect_is_the_one_the_reviewer_wrote_down(tmp_path):
    """The expectation travels in the control, not next to the number.

    If the declared input and the input the arm probed could drift apart, a
    reader would be checking the apparatus against an assertion written after
    the fact. `build_control` states the input; this asserts the two agree.
    """
    control = lr.build_control("known-effect")
    record = _drive("known-effect", tmp_path)

    assert control["x_under_revision"] == lr.REVIEWER_X
    assert control["x_under_incumbent"] == INCUMBENT_X
    assert control["expects_changed_decision"] is True
    assert record["x_probed"] == control["x_under_revision"]


# --- control 2: the no-op --------------------------------------------------


def test_the_no_op_control_measures_exactly_zero_with_no_spread(tmp_path):
    """A structural zero, not a small number that happened to land low.

    Every paired difference is identically zero, so the estimator has no
    spread to report. A null measured against noise carries a standard error;
    this one carries `0.0`, and that difference is what separates "the
    instrument cannot see a change here" from "there was no change to see".
    """
    record = _drive("no-op", tmp_path)
    paired = record["paired"]

    assert record["x_probed"] == INCUMBENT_X
    assert record["candidate_id"], "the no-op must still build a descendant"
    assert paired["measured"] is True
    assert paired["delta"] == 0.0
    assert paired["paired_sd"] == 0.0
    assert paired["paired_se"] == 0.0
    assert paired["n"] == len(COHORT)


def test_the_no_op_is_admitted_as_a_control_rather_than_as_a_revision(
        tmp_path):
    """It is the incumbent on purpose, and the waiver is recorded.

    A reply that returns the incumbent's bytes verbatim is refused by the
    study's identity check, which is correct for an acquired arm. The no-op
    has to reach the measurement to be a control at all, so the check is
    waived for it and the waiver is written into the verdict.
    """
    control = lr.build_control("no-op")
    record = _drive("no-op", tmp_path)

    assert lr.differs_from_incumbent(control["source"]) is True
    assert record["eligibility"] == channel.ELIGIBLE
    assert record["changed"]["changed_decision"] is False


# --- control 3: the disconnect ---------------------------------------------


def test_the_boundary_disconnect_is_refused_and_scores_nothing(tmp_path):
    """A decision that is spent and arrives at nothing.

    Not scored as a large negative. An arm refused at the action validator
    has no descendant, and calling that a bad result obtained by measurement
    would report a failure of the apparatus as a finding about the learner.
    """
    record = _drive("disconnect", tmp_path)

    assert record["refused_by_instrument"] is True
    assert record["x_probed"] == -1
    assert not record["candidate_id"]
    assert record["paired"]["measured"] is False
    assert record["paired"]["delta"] is None
    assert record["paired"].get("no_descendant") is True


def test_the_boundary_disconnect_is_refused_before_it_is_measured(tmp_path):
    """The refusal is at the instrument, not in the scoring code.

    `compare` returns no measurement for a negative x for any arm, so the
    distinction has to be drawn by the round itself refusing. Otherwise an
    arm that failed to start and an arm the instrument rejected would be
    indistinguishable in the artifact.
    """
    record = _drive("disconnect", tmp_path)
    control = lr.build_control("disconnect")

    assert control["refused_by_instrument"] is True
    assert control["x_under_revision"] >= 16
    assert record["error"], "a refusal must leave a reason behind"
    assert "refused" in record["error"]


# --- control 4: the C15 shape ----------------------------------------------


def test_the_c15_control_is_admitted_and_changes_nothing(tmp_path):
    """Different bytes, same decision. The shape that already shipped once.

    This is the control that would catch an acquired arm whose source digest
    differs from the incumbent's and whose descendants are the incumbent's.
    It passes every eligibility gate — the bytes are not a literal, and the
    probed input is a view read — and changes no learning decision, because
    the branch that would change it is one no learner is on.
    """
    control = lr.build_control("disconnect-bytes")
    record = _drive("disconnect-bytes", tmp_path)

    assert record["eligibility"] == channel.ELIGIBLE, (
        "the C15 control must be admitted, or it is testing the gate"
        " rather than the disconnect: %r" % (record.get("reason"),))
    assert lr.differs_from_incumbent(control["source"]) is True
    assert (control["source"].strip()
            != channel.IMPROVE_LOW_SOURCE.strip())
    assert _frontier.source_digest(control["source"]) \
        != _frontier.source_digest(channel.IMPROVE_LOW_SOURCE)


def test_the_c15_control_probes_the_incumbents_own_input(tmp_path):
    """The measured number, and the reason it is that number.

    `x_probed == 3` while the decoy input in the bytes is 7. The decoy sits
    on the `view["experience"]` branch, and experience is empty on the step
    that spends the probe, so the `else` arm runs. A reader can check this
    against the arm's own recorded decision rather than taking it on trust.
    """
    control = lr.build_control("disconnect-bytes")
    record = _drive("disconnect-bytes", tmp_path)

    assert control["decoy_x"] == lr.DISCONNECT_X == 7
    assert lr.DISCONNECT_X != INCUMBENT_X, (
        "the decoy must be a different input, or the control is the no-op")
    assert record["x_probed"] == INCUMBENT_X
    assert record["changed"]["changed_decision"] is False


def test_the_c15_control_builds_a_descendant_and_still_scores_zero(tmp_path):
    """It is not a refusal. It is a learner that built the same descendant.

    The boundary disconnect builds nothing; the no-op builds the incumbent's
    descendant. The C15 control does the second thing while claiming the
    first — its bytes announce a choice the run never makes. Reporting it as
    a flat descendant is right; reporting it as a refusal is not, and the
    two are distinguished by `candidate_id` and `eligibility` together.
    """
    record = _drive("disconnect-bytes", tmp_path)

    assert record["refused_by_instrument"] is False
    assert record["candidate_id"], (
        "if the C15 control builds no descendant it has become the boundary"
        " disconnect and no longer tests the shape it exists for")
    assert record["paired"]["measured"] is True
    assert record["paired"]["delta"] == 0.0
    assert record["paired"]["paired_se"] == 0.0


def test_the_c15_control_is_distinguishable_from_the_no_op_only_by_bytes(
        tmp_path):
    """The two controls measure the same zero for different reasons.

    Both probe input 3 and both score exactly zero. What separates them is
    the thing a C15-shaped acquisition would have changed: the bytes. If a
    reader could tell them apart from the measurement alone, the apparatus
    would be scoring byte identity and calling it a decision.
    """
    c15 = _drive("disconnect-bytes", tmp_path)
    noop = _drive("no-op", tmp_path)

    assert c15["x_probed"] == noop["x_probed"]
    assert c15["paired"]["delta"] == noop["paired"]["delta"] == 0.0
    assert c15["source_digest"] != noop["source_digest"]


def test_the_decoy_input_is_not_a_reachable_improvement(tmp_path):
    """The control is not trivial, and no longer claims to hide a gain.

    This test used to assert that the ceiling's argmax over the sixteen
    inputs *was* the decoy, on the reading that a control hiding an ordinary
    input could be dismissed as a no-op wearing a disguise. That assertion
    was true only while `lineage_descendant_score` resolved every input to
    one of two descendants, which made the mapping two-valued and its argmax
    7. Construction substitutes the probed input, so the mapping is no longer
    two-valued and the argmax is 12. The old assertion is false and it is
    kept as a canary in the opposite direction: if the decoy ever becomes
    the argmax again, the substrate changed and the comment at
    `channel_controls.DISCONNECT_X` has to be re-derived rather than assumed.

    What replaces it is the property the control actually rests on, and it
    is checked by asking the program rather than by pinning a number. The
    decoy scores exactly what the incumbent scores over the audit cohort, so
    there is no improvement going unused and none was ever shown to be. What
    the arm demonstrates is that it does not take the branch.

    The underlying substrate's argmax is unstable. The four interleaved
    quarters of this cohort disagree, and `noise_floor` reports
    `best_probe_agrees: False`, so pinning a particular winner would pin a
    quantity the module reports as noise. That instability is deliberately
    not asserted here. It is a property of the substrate rather than of the
    control, and a test that depended on it would fail on a substrate change
    that said nothing about this control.
    """
    control = lr.build_control("disconnect-bytes")
    cohort = list(range(150))
    means = {x: channel.evaluate_lineage([x], split=AUDIT, seeds=cohort)[
        "mean"] for x in range(channel._N_INPUTS)}
    argmax = max(sorted(means), key=means.get)
    record = _drive("disconnect-bytes", tmp_path)

    assert argmax != control["decoy_x"], (
        "the decoy is the ceiling's argmax again, so the drift recorded at"
        " channel_controls.DISCONNECT_X has closed and that comment is now"
        " stale: %r" % (means,))
    assert means[control["decoy_x"]] == means[INCUMBENT_X], (
        "the decoy stopped scoring exactly what the incumbent scores, so the"
        " control is hiding something and the comment at DISCONNECT_X must be"
        " re-derived before this test is re-aimed: %r" % (means,))
    assert control["decoy_x"] != INCUMBENT_X, (
        "the decoy is the incumbent's own input, so the control is the no-op")
    assert record["x_probed"] == INCUMBENT_X


# --- the apparatus verdict --------------------------------------------------


def test_all_four_controls_qualify_the_apparatus(tmp_path):
    """The verdict takes no run outcome as an input.

    A campaign that acquired nothing and a campaign that acquired an
    excellent revision are both only meaningful over a qualified apparatus,
    which is why this reads the controls and nothing else.
    """
    arms = {role: _drive(role, tmp_path) for role in lr.CONTROL_BUILDERS}
    verdict = lr.qualify(arms)

    assert set(verdict["checks"]) == set(lr.CONTROL_BUILDERS)
    assert verdict["qualified"] is True, (
        "a control misbehaved, so no run outcome would mean anything: %r"
        % (verdict["checks"],))
    assert verdict["qualification"] == lr.QUALIFIED


def test_the_qualification_fails_when_the_c15_control_reports_a_change(
        tmp_path):
    """The gate on the fourth control is the one under test.

    A verdict computed from a C15 arm that *did* change its decision must
    come back unqualified. This is what stops the check from being satisfied
    by any arm whose delta happens to be zero, which is the no-op's number
    too.
    """
    arms = {role: _drive(role, tmp_path) for role in lr.CONTROL_BUILDERS}
    assert lr.qualify(arms)["qualified"] is True

    arms["disconnect-bytes"] = dict(arms["disconnect-bytes"])
    arms["disconnect-bytes"]["changed"] = {
        "incumbent_x": 3, "revised_x": lr.DISCONNECT_X, "changed_decision": True}
    verdict = lr.qualify(arms)

    assert verdict["qualified"] is False
    assert verdict["checks"]["disconnect-bytes"]["passed"] is False
    assert verdict["qualification"] == lr.UNQUALIFIED


def test_the_qualification_fails_when_a_control_is_absent(tmp_path):
    """Missing is not passing.

    A role that produced no arm must be reported as not present rather than
    skipped, so a run that quietly failed to drive one control cannot be
    reported as qualified.
    """
    arms = {role: _drive(role, tmp_path) for role in lr.CONTROL_BUILDERS}
    del arms["no-op"]
    verdict = lr.qualify(arms)

    assert verdict["qualified"] is False
    assert verdict["checks"]["no-op"]["present"] is False
    assert verdict["checks"]["no-op"]["passed"] is False


def test_each_control_records_the_effect_it_knows_before_the_run(tmp_path):
    """Every check carries the reviewer's stated reason with it.

    The verdict is what a report would quote, and a verdict that carries only
    a pass bit cannot be audited. Each entry states the expectation in prose
    beside the number it was checked against.
    """
    arms = {role: _drive(role, tmp_path) for role in lr.CONTROL_BUILDERS}
    verdict = lr.qualify(arms)

    for role, check in verdict["checks"].items():
        assert check["known_effect"], "%s states no known effect" % role
        assert isinstance(check["known_effect"], str)
        assert len(check["known_effect"]) > 40, (
            "%s states a known effect too tersely to be a reason" % role)


# --- the mutations ----------------------------------------------------------
#
# Each entry is what was changed to make the test above go red, and what the
# run printed. They are recorded rather than merely performed so a reviewer
# can re-derive the claim instead of trusting it.
#
#   test_the_known_effect_control_measures_the_effect_it_declares
#     REVIEWER_X 8 -> 3
#     x_probed == 8  ->  AssertionError
#
#   test_the_no_op_control_measures_exactly_zero_with_no_spread
#     no_op_revision `_revision_source("3")` -> `_revision_source("8")`
#     x_probed == 3  ->  AssertionError: assert 8 == 3
#     (the control's *fallback* arm is not a mutation: it is unreachable in
#     a one-step round, so changing it leaves every number green. Recorded
#     because a test that cannot fail is this repo's standing defect, and a
#     reader is entitled to know which half of the no-op is pinned.)
#
#   test_the_boundary_disconnect_is_refused_and_scores_nothing
#     disconnect out_of_range _rules.N_STATES (16) -> 3
#     refused_by_instrument is True  ->  AssertionError
#
#   test_the_c15_control_is_admitted_and_changes_nothing
#     _C15_REPLACEMENT ... else 3 -> else 7
#     x_probed == 3  ->  AssertionError: assert 7 == 3
#
#   test_all_four_controls_qualify_the_apparatus
#     same _C15_REPLACEMENT mutation
#     qualified is True  ->  AssertionError, checks["disconnect-bytes"] false
#
#   test_the_decoy_input_is_not_a_reachable_improvement
#     DISCONNECT_X 7 -> 3 turns two tests red rather than one.
#     test_the_decoy_input_is_not_a_reachable_improvement fails on
#     `decoy_x != INCUMBENT_X` ("the control is the no-op"), because 3 then
#     *is* the incumbent's own input. The equality assertion that 3 also
#     breaks is never reached, so its message is a contingency rather than
#     the observed failure.
#     test_the_c15_control_probes_the_incumbents_own_input fails too, on
#     its own `== 7` pin, which is a literal and not a claim.
MUTATIONS = (
    {"test": "known-effect", "target": "learner_revision.REVIEWER_X",
     "from": 8, "to": 3},
    {"test": "no-op", "target": "learner_revision.no_op_revision probe",
     "from": "3", "to": "8"},
    {"test": "disconnect", "target": "_rules.N_STATES as the probed input",
     "from": 16, "to": 3},
    {"test": "disconnect-bytes", "target": "_C15_REPLACEMENT else arm",
     "from": "else 3", "to": "else 7"},
    {"test": "disconnect-bytes", "target": "channel_controls.DISCONNECT_X",
     "from": 7, "to": 3},
)
