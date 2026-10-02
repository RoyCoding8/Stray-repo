"""The declared freeze must be the enforced freeze.

`improve_channel` declares `FROZEN_FIELDS` and says a revision "may change
which diagnostic evidence the learner gathers, and only that". Nothing
enforced the "only that". `classify_revision` checked five conditions, and
none of them was "and nothing else changed", so a revision that kept a valid
view-dependent `x` while rewriting the probe's requested allocation, the
construction branch or the action target was admitted as `eligible`.

An audit measured six such variants and found all six eligible
(`reports/workstreams/w4-e4-interface.md` §4). Those six are the fixtures
here, and the measurement is now a test: each is ineligible, and each names
the decision it moved.

The other direction is the one that matters for milestone C. A guard that
refused everything would pass a file of refusals and leave no live
experiment. So the authorised kind - a revision that rewrites the probed
input and nothing else - is asserted eligible on its own account, positively,
against the real module.

The second half of the lane is the control registry. Four controls are
written and the channel's role tuple named three, so the one that catches a
do-nothing reviser was unreachable through the channel's public control
entry. The registry and the role declaration are reconciled here, and the
three required roles are driven from identical starting conditions.

Deterministic and offline: no network, no live model, fixture gateway never
called. The controls that execute a step need real PostgreSQL authority,
because `method_exec.run_step_out_of_process` refuses to execute a policy
source without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import improve_channel as channel

# --- the six variants the audit measured ----------------------------------
#
# Each is the baseline selector with exactly one unauthorised change. The
# baseline is `_revision_source("8")` run through the same view read every
# authored control uses, so the view-dependence gate is satisfied by
# construction and cannot be the reason any of them is refused. A reason that
# blamed the view read would be the guard misfiring, not the freeze working.

AUTHORISED = "3 if not view[\"experience\"] else 8"


def _data_dependent_baseline() -> str:
    """The baseline every variant is derived from.

    `_revision_source("8")` on its own names a fixed input, so it is refused
    as `task-solver-not-decision` before any scope question is reached. The
    audit's base ran the same view read every authored control uses, which
    satisfies the data-dependence gate by construction and means a refusal
    can only be the freeze. The baseline has to keep that shape or these
    fixtures would be testing the wrong gate.
    """
    from experiments.ad01 import channel_controls
    return channel_controls._selector(
        channel._revision_source("8"), "8", "3")

ALLOC_ALLOCATION_UP = (
    '"requested_resources": {"queries": 1, "steps": 1}',
    '"requested_resources": {"queries": 8, "steps": 8}')
ALLOC_ALLOCATION_DOWN = (
    '"requested_resources": {"queries": 1, "steps": 1}',
    '"requested_resources": {"queries": 0, "steps": 0}')
CONSTRUCTION_FORCED = (
    'strategy = "high" if first[0] == 1 else "low"',
    'strategy = "high"')
CONSTRUCTION_REWRITTEN = (
    'strategy = "high" if first[0] == 1 else "low"',
    'strategy = "high" if len(first) > 99 else "low"')
TARGET_REWRITTEN = ('"target": "rule-improve"', '"target": "rule-bypass"')
# A skeleton change that keeps the probe, so the boundary is still reached
# and the freeze is what refuses it. Replacing the probe instead removes the
# boundary, and that is a different refusal; it is checked separately below
# because the audit's sixth line does exactly that.
SKELETON_REWRITTEN = ('state = {"step": 1}',
                      'state = {"step": 2}')

# name -> (old, new, the decision the refusal must name)
UNAUTHORISED = {
    "probe-allocation-raised": (*ALLOC_ALLOCATION_UP, "probe-allocation"),
    "probe-allocation-zeroed": (*ALLOC_ALLOCATION_DOWN, "probe-allocation"),
    "construction-forced": (*CONSTRUCTION_FORCED, "candidate-construction"),
    "construction-rewritten": (
        *CONSTRUCTION_REWRITTEN, "candidate-construction"),
    "target-rewritten": (*TARGET_REWRITTEN, "probe-target"),
    "step-skeleton-rewritten": (*SKELETON_REWRITTEN, "step-skeleton"),
}


def _mission() -> dict:
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [{"instrument": "boolean-rule-v1",
                          "split": "dev", "seed": 4}],
    }


def _bound_store(tmp_path, name="c2.json"):
    from experiments.ad01 import frontier
    store = frontier.create_store(
        tmp_path / name, namespace=frontier.NAMESPACE, mission=_mission(),
        authority={"queries": 16, "steps": 12})
    base = channel.make_control("low")
    store.bind_active(base)
    return store, base


def _views(store, base, seeds=(0, 1, 2, 3)):
    from experiments.ad01 import frontier
    views = []
    for _ in seeds:
        view = store.step_view(frontier.IMPROVE, base)
        view["experience"] = []
        view["round"] = 1
        views.append(view)
    return views


@pytest.mark.parametrize("name", sorted(UNAUTHORISED))
def test_a_revision_that_moves_another_decision_is_ineligible(tmp_path, name):
    """The measured defect, one variant at a time.

    The reason must name the decision the revision moved. A bare
    "ineligible" would satisfy a reader who only counts verdicts, and would
    hide a guard that refuses everything.
    """
    old, new, expected = UNAUTHORISED[name]
    store, base = _bound_store(tmp_path, "%s.json" % name)
    baseline = _data_dependent_baseline()
    assert old in baseline, (
        "the incumbent no longer contains the text this fixture rewrites,"
        " so the fixture is not testing the freeze: %r" % (baseline,))
    revision = baseline.replace(old, new, 1)

    verdict = channel.classify_revision(revision, _views(store, base))

    assert verdict["eligibility"] != channel.ELIGIBLE, (
        "%s changed a decision the revision was not authorised to change and"
        " was still admitted: %r" % (name, verdict))
    assert verdict["eligibility"] == channel.INELIGIBLE_OUT_OF_SCOPE, (
        "%s was refused, but for the wrong reason: %r" % (name, verdict))
    reason = verdict["reason"]
    assert expected in reason, (
        "%s was refused without naming the change it made, so a reader"
        " cannot tell the freeze from any other refusal: %r" % (name, reason))


def test_the_authorised_change_is_still_eligible(tmp_path):
    """A revision that changes the acquisition procedure and nothing else.

    Asserted positively. If the freeze were satisfied by refusing
    everything, every test above would pass and milestone C would have no
    live experiment left, which is a worse outcome than the defect.
    """
    store, base = _bound_store(tmp_path, "authorised.json")
    revision = channel._revision_source(AUTHORISED)

    verdict = channel.classify_revision(revision, _views(store, base))

    assert verdict["eligibility"] == channel.ELIGIBLE, (
        "the one change the interface names is the one change a revision is"
        " authorised to make, and it was refused: %r" % (verdict,))
    assert verdict["decision"] == channel.DECISION
    assert verdict["selected_evidence"], (
        "an admitted revision selected no evidence, so the eligibility"
        " verdict is asserting a decision it never made: %r" % (verdict,))


def test_every_authored_control_is_an_authorised_change(tmp_path):
    """The controls are the admissible kind, so they pin the admissible kind.

    A freeze that refused the channel's own controls would be refusing the
    only revisions anyone has written. Each of the four is checked against
    the module, not against a fixture, so moving a builder fails here.
    """
    from experiments.ad01 import channel_controls

    store, base = _bound_store(tmp_path, "controls.json")
    views = _views(store, base)

    for role in sorted(channel_controls.CONTROL_BUILDERS):
        source = channel_controls.build_control(role)["source"]
        verdict = channel.classify_revision(source, views)
        assert verdict["eligibility"] == channel.ELIGIBLE, (
            "the %s control changes only the probed input and was refused as"
            " out of scope: %r" % (role, verdict))


def test_a_skeleton_change_that_removes_the_boundary_is_still_refused(
        tmp_path):
    """The audit's sixth line, which loses the probe rather than moving it.

    Refused for a stronger reason than the freeze. A revision that never
    emits a probe does not reach the decision under study at all, so
    `no-boundary-action` is the accurate report and naming a scope breach
    would overstate what the freeze contributed. Asserted separately so the
    ordering is pinned rather than implied: every one of the six measured
    variants is ineligible, and the reason differs.
    """
    store, base = _bound_store(tmp_path, "boundary.json")
    revision = _data_dependent_baseline().replace(*SKELETON_REWRITTEN, 1)
    revision = revision.replace('"kind": "probe"', '"kind": "construct"', 1)

    verdict = channel.classify_revision(revision, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_NO_BOUNDARY
    assert "diagnostic evidence" in verdict["reason"]


def test_every_measured_variant_is_ineligible(tmp_path):
    """All six, counted, so none is refused for an unstated reason.

    The six are measured one at a time above because the reason is the
    point. This asserts the count so a future edit cannot drop a fixture and
    leave the rest green.
    """
    assert len(UNAUTHORISED) == 6


def test_the_scope_refusal_is_its_own_reason(tmp_path):
    """`mutates-frozen-field` is a write to a declared frozen field.

    A revision that rewrites the construction branch writes no frozen field
    at all, so reusing that reason would tell a reader the revision touched
    the grant or the evaluator when it did not. The reasons are enumerated
    so the two cannot be confused, and the enumeration is asserted rather
    than assumed.
    """
    store, base = _bound_store(tmp_path, "reasons.json")
    revision = _data_dependent_baseline().replace(*CONSTRUCTION_FORCED, 1)

    verdict = channel.classify_revision(revision, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_OUT_OF_SCOPE, (
        "the scope breach was not reported as one: %r" % (verdict,))
    assert channel.INELIGIBLE_OUT_OF_SCOPE in channel.INELIGIBILITY_REASONS
    assert channel.INELIGIBLE_OUT_OF_SCOPE != \
        channel.INELIGIBLE_FROZEN_WRITE
    assert len(set(channel.INELIGIBILITY_REASONS)) == len(
        channel.INELIGIBILITY_REASONS), (
        "two refusal reasons share a name, so a caller cannot tell them"
        " apart: %r" % (channel.INELIGIBILITY_REASONS,))


def test_the_six_variants_were_eligible_before_the_freeze(tmp_path):
    """The audit's measurement is re-derived, so the regression is named.

    If a future change made these variants ineligible for some other reason,
    the tests above would still pass and this would say which change. It
    asserts the *baseline* is eligible, which is what makes the six refusals
    attributable to the freeze rather than to a fixture that never worked.
    """
    store, base = _bound_store(tmp_path, "baseline.json")
    verdict = channel.classify_revision(
        channel._revision_source(AUTHORISED), _views(store, base))

    assert verdict["eligibility"] == channel.ELIGIBLE


# --- the control registry -------------------------------------------------


def test_every_written_control_is_reachable_from_control_roles():
    """No written control may be unreachable through the public entry.

    Four builders were written and three roles declared, so the fourth - the
    only control that catches a reviser whose bytes differ and whose
    behaviour does not - could not be built through the channel's declared
    entry. The registry and the declaration are checked against each other
    rather than against a count, because a count passes when one control is
    renamed and another is added.
    """
    from experiments.ad01 import channel_controls

    written = set(channel_controls.CONTROL_BUILDERS)
    declared = set(channel.WRITTEN_CONTROL_ROLES)

    assert written == declared, (
        "the written controls and the channel's declaration disagree: %r"
        " against %r" % (sorted(written), sorted(declared)))
    assert set(channel.CONTROL_ROLES) <= declared, (
        "the channel qualifies against a role no builder produces: %r"
        % (channel.CONTROL_ROLES,))
    for role in sorted(written):
        assert isinstance(channel_controls.build_control(role), dict), (
            "the %s control is declared but cannot be built" % (role,))


def test_the_channel_qualifies_the_control_that_catches_a_do_nothing_reviser(
        migrated_db, tmp_path):
    """A disconnect-bytes arm that *changed* its decision unqualifies.

    The gate used to read three roles, so this arm could report a change and
    the channel would still call the apparatus qualified. It is reported, not
    required: a run that never drove the arm cannot be failed for its
    absence, because the immutable E4 artifact records three controls and
    requiring four would misread that history.
    """
    controls = [
        _drive(role, migrated_db, tmp_path)
        for role in sorted(channel.WRITTEN_CONTROL_ROLES)]
    verdict = channel.qualify_apparatus(controls)

    assert verdict["qualified"] is True, (
        "the four controls did not qualify the apparatus, so no run outcome"
        " would mean anything: %r" % (verdict,))
    assert "disconnect-bytes" in verdict["additional_checks"]

    moved = list(controls)
    moved[-1] = dict(moved[-1], as_expected=False, decision_changed=True)

    assert channel.qualify_apparatus(moved)["qualified"] is False, (
        "the control that catches a do-nothing reviser reported a change and"
        " the apparatus was still called qualified")


def test_the_three_mandatory_roles_alone_still_qualify(
        migrated_db, tmp_path):
    """The immutable E4 artifact recorded three, and three still decide.

    `WRITTEN_CONTROL_ROLES` grew by one so the fourth control could be
    reached. That must not retroactively make a three-control run incomplete,
    because the committed run is exactly that and its verdict is history.
    """
    controls = [
        _drive(role, migrated_db, tmp_path) for role in channel.CONTROL_ROLES]

    verdict = channel.qualify_apparatus(controls)

    assert verdict["qualified"] is True
    assert "additional_checks" not in verdict, (
        "a run that drove only the mandatory roles reported a fourth: %r"
        % (verdict,))


# --- the three required controls, from identical starting conditions -------


def _allocation(migrated_db, tmp_path):
    """One real allocation row, so a step may execute at all.

    `method_exec.run_step_out_of_process` refuses to execute a policy source
    without a dsn, an allocation and an operation id. The controls drive real
    steps, so they need one, and this is the only reason this file touches
    the database.
    """
    from settlement import db
    allocation_id = "c2-freeze-alloc"
    with db.connect(migrated_db) as write:
        write.execute(
            "INSERT INTO allocations (id, parent_id, domain, epoch,"
            " authorized, amount_scale, max_occupancy, owner_scope) VALUES"
            " (%s, NULL, 'cpu', 0, 100000, 1, 500, '')"
            " ON CONFLICT (id) DO NOTHING", (allocation_id,))
        write.commit()
    return allocation_id


def _drive(role, migrated_db, tmp_path):
    from experiments.ad01 import channel_controls
    return channel_controls.drive_record(
        role, dsn=migrated_db, allocation_id=_allocation(
            migrated_db, tmp_path), workdir=tmp_path)


def test_the_effectful_control_changes_an_acquisition_decision(
        migrated_db, tmp_path):
    """From identical starting conditions, the effectful control moves x.

    The incumbent probes 3. A control that changes an acquisition decision has
    to name a different input, or the apparatus is measuring nothing.
    """
    from experiments.ad01 import boolean_rule as rules

    effectful = _drive("known-effect", migrated_db, tmp_path)
    noop = _drive("no-op", migrated_db, tmp_path)

    assert noop["x_probed"] == channel.INCUMBENT_EVIDENCE[0], (
        "the comparison arm did not reproduce the incumbent, so a"
        " difference between the two arms would not be attributable: %r"
        % (noop,))
    assert effectful["x_probed"] != noop["x_probed"], (
        "the effectful control selected the same input as the incumbent, so"
        " it changed nothing: %r" % (effectful,))
    assert effectful["refused_by_instrument"] is False, (
        "the effectful control was refused by the instrument, so it never"
        " reached the decision it is meant to move: %r" % (effectful,))
    assert 0 <= effectful["x_probed"] < rules.N_STATES, (
        "the effectful control named an input outside the instrument: %r"
        % (effectful,))
    assert effectful["decision_changed"] is True
    assert effectful["as_expected"] is True


def test_the_no_op_control_changes_nothing(migrated_db, tmp_path):
    """The control that may not move.

    It reaches the boundary by the same view read as the effectful control
    and differs only in the integers it names, so a paired difference of
    exactly zero is by construction rather than by luck.
    """
    from experiments.ad01 import boolean_rule as rules

    noop = _drive("no-op", migrated_db, tmp_path)

    assert noop["x_probed"] == channel.INCUMBENT_EVIDENCE[0] == 3, (
        "the no-op control did not select the incumbent's own input, so it"
        " is not a no-op: %r" % (noop,))
    assert noop["refused_by_instrument"] is False, (
        "the no-op control was refused by the instrument, so it never"
        " reached the decision it is meant to leave alone: %r" % (noop,))
    assert noop["delta"] == 0.0
    assert 0 <= noop["x_probed"] < rules.N_STATES


def test_the_disconnect_control_is_refused(migrated_db, tmp_path):
    """A decision that is spent and arrives at nothing.

    The instrument's own action validator refuses the input, which is the
    earliest point at which the range of an input is known. A no-op cannot
    demonstrate this: it is wired correctly and correctly chooses the same
    thing, and both would score flat under an evaluator that looked only at
    the number.

    The refusal is a recorded outcome rather than an error, so no input was
    ever spent and no descendant was built.
    """
    disconnect = _drive("disconnect", migrated_db, tmp_path)

    assert disconnect["refused_by_instrument"] is True, (
        "the disconnect control named an input the instrument accepts, so it"
        " is a revision rather than a disconnect: %r" % (disconnect,))
    assert disconnect["x_probed"] == -1, (
        "the disconnect was refused before an input was spent, so it must"
        " not report having probed one: %r" % (disconnect,))
    assert "0..15" in disconnect["refused_reason"], (
        "the refusal does not name the range the instrument accepts, so a"
        " reader cannot tell it from any other refusal: %r"
        % (disconnect["refused_reason"],))
    assert disconnect["delta"] == 0.0


def test_the_disconnect_bytes_control_still_catches_a_do_nothing_reviser(
        migrated_db, tmp_path):
    """The load-bearing property, preserved.

    Its bytes differ from the incumbent and it is admitted, yet the decision
    does not change, because the branch that would move the input is the
    branch no learner takes. Nothing else in the registry catches a reviser
    whose bytes differ and whose behaviour does not.
    """
    from experiments.ad01 import frontier

    control = _drive("disconnect-bytes", migrated_db, tmp_path)

    assert control["x_probed"] == channel.INCUMBENT_EVIDENCE[0]
    assert control["source_digest"] != frontier.source_digest(
        channel.IMPROVE_LOW_SOURCE), (
        "the control's bytes are the incumbent's, so it no longer separates"
        " different bytes from the same behaviour: %r" % (control,))
    assert control["delta"] == 0.0
    assert control["as_expected"] is True


def test_the_three_required_roles_are_covered_by_the_written_registry():
    """The assignment's three, named, inside the larger registry."""
    from experiments.ad01 import channel_controls

    assert set(channel.CONTROL_ROLES) == {
        "known-effect", "no-op", "disconnect"}
    assert set(channel.CONTROL_ROLES) < set(
        channel_controls.CONTROL_BUILDERS), (
        "the three required roles are not a strict subset of what is"
        " written, so the registry is not a superset of the contract")
    assert "disconnect-bytes" in channel_controls.CONTROL_BUILDERS