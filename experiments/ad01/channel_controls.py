"""The channel's controls, written by the reviewer rather than by the channel.

The assignment asks for effectful, no-op and disconnect controls that are
*independently written* and that qualify the channel from identical starting
conditions. They were not. All four builders lived in `learner_revision`,
the same module as the acquisition mechanism they test, and the improve-path
entry built them from that module's own table, so a reader could not tell a
control from the thing it controls.

This module is the reviewer-owned half. It imports the channel for the
incumbent's bytes, the instrument's range and the descendant metric, and it
writes every control itself. It adds no second eligibility rule, no second
evaluator and no second metric: the numbers a control is judged on come from
`improve_channel`, so a control cannot flatter the mechanism by grading
itself.

Four controls, and the fourth is the one that earns the other three their
right to be believed. `disconnect-bytes` produces bytes that differ from the
incumbent and are admitted as eligible, yet the decision does not change,
because the branch that would move the input is the branch no learner takes.
That is the C15 shape, and it is the only control here that can catch an
acquired arm whose bytes differ and whose behaviour does not. A positive
control passes a do-nothing reviser; a no-op cannot tell a correctly
unchanged decision from one that never ran.
"""

from __future__ import annotations

from experiments.ad01 import boolean_rule as _rules
from experiments.ad01 import frontier as _frontier
from experiments.ad01 import improve_channel as channel

AUTHORED = "reviewer-authored"

# The cohort the controls are compared on. Small on purpose: a control is a
# discrimination test, not a significance test, and the run's own cohort is
# the place a real effect is estimated.
COHORT = list(range(24))
AUDIT = "audit"

INCUMBENT_X = channel.INCUMBENT_EVIDENCE[0]

# --- the four controls -----------------------------------------------------

REVIEWER_X = 8
REVIEWER_WHY = (
    "The reviewer read `reachable_descendant_means` in the qualified "
    "headroom artifact, where %d is the highest of the sixteen inputs the "
    "instrument accepts, and wrote a selector that names that input unless "
    "the learner has already spent it. The effect is known before the arm is "
    "run: on the first step the view carries no observation, so the control "
    "names %d, the descendant it selects differs from the incumbent's, and "
    "the size and direction of that difference are properties of the "
    "substrate rather than of the reviewer." % (REVIEWER_X, REVIEWER_X))


def _selector(imp_source: str, preferred: str, fallback: str) -> str:
    """Bind the probed input to a value read out of the learner's experience.

    The rule is one line and is the same shape for all three controls: name
    the preferred input unless the learner has already probed it, and name
    the fallback when it has. Only the two integers differ between them.

    The view read is written at the point of use rather than bound to a name
    on the line above. `improve_channel._probe_x_expression` resolves an
    `x` through module-level assignments and then asks whether the resulting
    expression reads the view, so an intermediate name turns a genuine
    selector into a refusal. That is a property of the rule and the controls
    are written to satisfy it rather than to work around it.

    Every control produced here differs from the incumbent at the probed
    input and at nothing else, which is what `improve_channel`'s scope check
    now enforces rather than assumes. A control that moved anything else
    would be refused by the very gate it is written to qualify.
    """
    return imp_source.replace(
        '"x": %s' % preferred,
        '"x": %s if %s not in set(o.get("x") for o in view["experience"])'
        ' else %s' % (preferred, preferred, fallback), 1)


def reviewer_revision() -> dict:
    """A revision a human wrote, with its effect stated in advance.

    It exists to prove the apparatus can carry a known effect through to a
    descendant measurement. It is labeled `reviewer-authored` and never
    enters an acquired arm, and the label travels in the evidence rather
    than in a comment, so a reader cannot mistake it for a model reply.
    """
    return {
        "label": AUTHORED,
        "control_id": "reviewer-authored-x%d" % REVIEWER_X,
        "source": _selector(
            channel._revision_source(str(REVIEWER_X)), str(REVIEWER_X), "3"),
        "known_effect": REVIEWER_WHY,
        "expects_changed_decision": True,
        "x_under_incumbent": 3,
        "x_under_revision": REVIEWER_X,
    }


def no_op_revision() -> dict:
    """The control that must change nothing, and the only one that may not.

    It names the incumbent's own input through the same view read the
    known-effect control uses, so the two differ in the integers they name
    and in nothing else. A revision that returned the incumbent's bytes
    verbatim would be refused by the study's identity check before it could
    be measured, which is correct for an acquired arm and useless for a
    control whose whole purpose is to arrive at the measurement.
    """
    return {
        "label": AUTHORED,
        "control_id": "no-op-incumbent-x3",
        "source": _selector(channel._revision_source("3"), "3", "8"),
        "known_effect": (
            "The incumbent's own input, 3, selected by the same view read "
            "the known-effect control uses. On the first step nothing has "
            "been spent, so it names 3, the descendant it builds is the "
            "incumbent's descendant, and the paired difference is exactly "
            "zero by construction rather than by a measurement that happened "
            "to be small."),
        "expects_changed_decision": False,
        "x_under_incumbent": 3,
        "x_under_revision": 3,
    }


def disconnect_revision() -> dict:
    """A revision that reaches the boundary and cannot change anything.

    The input it names is outside the instrument's own range, so the
    instrument refuses it, the probe returns nothing, and the round has no
    observation to turn into a descendant. This is the failure a no-op
    cannot demonstrate: a no-op is wired correctly and decides correctly and
    correctly chooses the same thing, while this is a decision that is spent
    and arrives at nothing. Reporting both as a flat descendant would hide
    the difference between a learner that learned and one that could not ask.

    It is refused at the action validator, before the instrument sees it,
    which is the earliest point at which the range of an input is known. The
    run records the refusal rather than an exception, so the disconnect is a
    recorded outcome of a real attempt.
    """
    out_of_range = _rules.N_STATES
    return {
        "label": AUTHORED,
        "control_id": "disconnect-x%d" % out_of_range,
        "source": _selector(
            channel._revision_source(str(out_of_range)), str(out_of_range),
            "3"),
        "known_effect": (
            "The decision is reached and the input is named, but the "
            "instrument's own action validator refuses input %d because the "
            "task exposes only inputs 0..%d. The probe returns no "
            "observation, no descendant is built and the round ends without "
            "a candidate. The difference from a no-op is the point: a no-op "
            "learns what the incumbent learns, and this learns nothing at "
            "all, and both would score flat under an evaluator that looked "
            "only at the number." % (out_of_range, _rules.N_STATES - 1)),
        "expects_changed_decision": True,
        "x_under_incumbent": 3,
        "x_under_revision": out_of_range,
        "refused_by_instrument": True,
    }


# The C15 shape, kept under its own name. `disconnect` above is a decision
# the instrument refuses; this is a decision the instrument accepts and that
# still changes nothing, which is the shape that actually shipped once
# already: bytes that differ, behaviour that does not.
DISCONNECT_X = 7
_C15_ANCHOR = '''    if step == 0:
        inner = {"kind": "probe", "inputs": {"x": 3},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}'''
_C15_REPLACEMENT = '''    if step == 0:
        inner = {"kind": "probe",
                 "inputs": {"x": %d if view["experience"] else 3},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}''' % DISCONNECT_X


def disconnect_bytes_revision() -> dict:
    """Bytes that differ, and a decision that does not.

    The other two controls each fail loudly. This one passes every gate and
    still does nothing, because the only branch that would change the probed
    input is the branch the learner is never on: `view["experience"]` is
    empty on the step where the probe is spent, so the `else 3` arm is the
    one that runs and input 3 is the incumbent's own input.

    It is admitted as eligible, and admitted now for a stated reason: its
    only difference from the incumbent is the expression bound to the probed
    input, which is the change the interface names. An eligibility rule
    cannot tell a revision that chooses from one that merely contains a
    choice, and this control is what that sentence looks like when it runs.

    The integer is the ceiling's argmax on the audit cohort, so a reader can
    see the rule is not trivial - the same integer, reached, would improve
    the descendant. The control is the unreachability, not the integer.
    """
    source = channel.IMPROVE_LOW_SOURCE
    if _C15_ANCHOR not in source:
        raise _frontier.Refused("the incumbent step source no longer has the"
                                " probe branch this control rewrites")
    return {
        "label": AUTHORED,
        "control_id": "disconnect-bytes-x%d-unreachable" % DISCONNECT_X,
        "source": source.replace(_C15_ANCHOR, _C15_REPLACEMENT, 1),
        "known_effect": (
            "The bytes differ from the incumbent and are admitted as "
            "eligible, because the only thing that differs is the "
            "expression bound to the probed input. The decision does not "
            "change: on the step that spends the probe, `view[\"experience\"]`"
            " is empty, so the expression takes its `else 3` arm and the "
            "learner probes the incumbent's own input. The descendant is "
            "therefore the incumbent's descendant and the paired difference "
            "is exactly zero, while the source digest is not the "
            "incumbent's digest. This is the C15 shape: different bytes, "
            "same behaviour."),
        "expects_changed_decision": False,
        "x_under_incumbent": 3,
        "x_under_revision": 3,
        "decoy_x": DISCONNECT_X,
        "shaped_like": "C15",
    }


CONTROL_BUILDERS = {
    "known-effect": reviewer_revision,
    "no-op": no_op_revision,
    "disconnect": disconnect_revision,
    "disconnect-bytes": disconnect_bytes_revision,
}

# What each role must do, stated before the run. The check reads the
# declaration rather than restating it next to the number, so a control
# cannot quietly agree with itself.
EXPECTATION = {
    "known-effect": "changes the decision",
    "no-op": "changes nothing",
    "disconnect": "is refused by the instrument",
    "disconnect-bytes": "changes nothing though its bytes differ",
}


def build_control(role: str) -> dict:
    try:
        return CONTROL_BUILDERS[role]()
    except KeyError:
        raise _frontier.Refused("unknown E4 control role %r" % (role,))


# --- driving one control ---------------------------------------------------


def _package_for(source: str, parent: dict, control_id: str) -> dict:
    """Bind a revision onto a fresh store, the way adoption requires.

    Built here rather than borrowed from `learner_revision`, because a
    control that reused the mechanism's own packager could not fail where
    the mechanism fails. The operational bytes are copied from the parent
    because adoption refuses a revision whose operational bytes differ, and
    a revision is not permitted an opinion about them.
    """
    package = {
        "control_id": control_id, "origin": channel.ORIGIN,
        "source_kind": "fixed-menu", "op_source": parent["op_source"],
        "imp_source": source,
        "op_digest": _frontier.source_digest(parent["op_source"]),
        "imp_digest": _frontier.source_digest(source),
        "parent_digest": parent["package_digest"],
        "provenance": None, "provenance_digest": None,
        "version": int(parent["version"]) + 1,
        "authority_request": dict(parent["authority_request"]),
        "obligations": list(parent["obligations"]),
        "channel": parent["channel"], "package_digest": None}
    package["package_digest"] = _frontier.package_digest(package)
    return package


def _mission(split: str = "dev", seed: int = 4) -> dict:
    return {"objective": "probe boolean rules within eight queries",
            "constraints": ["deterministic only", "no live network"],
            "success_criteria": ["committed predictor"],
            "environments": [{"instrument": "boolean-rule-v1",
                              "split": split, "seed": seed}]}


def _descendant_delta(x: int) -> float:
    """The paired descendant difference this input produces, or zero.

    Measured by the channel's own estimator on the channel's own cohort, so
    the control is graded by the machinery it qualifies. An input the
    instrument refuses reaches no descendant and contributes zero, which is
    the point of the disconnect rather than a gap in the measurement.
    """
    if not 0 <= x < _rules.N_STATES:
        return 0.0
    revised = channel.evaluate_descendants([x], split=AUDIT, seeds=COHORT)
    incumbent = channel.evaluate_descendants(
        [INCUMBENT_X], split=AUDIT, seeds=COHORT)
    return channel.descendant_delta(revised, incumbent)["delta"]


def drive_record(role: str, *, dsn: str | None = None,
                 allocation_id: str | None = None,
                 workdir=None) -> dict:
    """Drive one control from a fresh store and report what it decided.

    Every control gets an identical store, an identical bound incumbent and
    an identical empty experience, so the only thing that differs between two
    records is the control's own bytes. That is what makes the four records
    comparable at all.

    The decision is read off a real executed step rather than off the bytes,
    because a computed input is exactly the case that decides the
    improvement and a literal scan cannot evaluate it. Executing a policy
    source needs authority, so `dsn` and `allocation_id` are required for a
    driven record and a record without them is a refusal rather than a
    measurement reported as one.
    """
    control = build_control(role)
    if dsn is None or allocation_id is None:
        raise _frontier.Refused(
            "driving a control needs execution authority: dsn and"
            " allocation_id are required, not optional")
    if workdir is None:
        raise _frontier.Refused("a driven control needs a workdir to keep"
                                " its store in")
    workdir = __import__("pathlib").Path(workdir)
    store = _frontier.create_store(
        workdir / ("control-%s.json" % role.replace("/", "-")),
        namespace=_frontier.NAMESPACE, mission=_mission(),
        authority={"queries": 16, "steps": 12})
    parent = channel.make_control("low")
    store.bind_active(parent)
    store.adopt_revision(
        _package_for(control["source"], parent, control["control_id"]))
    view = store.step_view(_frontier.IMPROVE, store.active_package)
    view["experience"] = []
    view["round"] = 1
    action: dict = {}
    refused_reason = ""
    x_probed = -1
    try:
        stepped = channel.run_improve_step(
            store.active_package, view, {},
            authority={"dsn": dsn, "allocation_id": allocation_id},
            operation_id="inv-c2-control-%s-%s" % (
                control["control_id"],
                store.active_package["package_digest"][:12]),
            arm=role, task_id=_rules.make_task("dev", 0).get("task_id"),
            artifact_digest=store.active_package["package_digest"],
            parent_digest=store.active_package.get("parent_digest"),
            round_no=1)
        action = stepped["action"]
    except _frontier.Refused as exc:
        # The disconnect is refused at the action validator, which is the
        # earliest point at which the range of an input is known. It is a
        # recorded outcome of a real attempt, so the refusal is the result
        # and not an error around it.
        refused_reason = str(exc)
    if action.get("kind") == "probe":
        x_probed = int(action["inputs"].get("x", -1))
    refused = bool(refused_reason)
    record = {
        "role": role,
        "control_id": control["control_id"],
        "known_effect": control["known_effect"],
        "source_digest": _frontier.source_digest(control["source"]),
        "x_probed": x_probed,
        "refused_by_instrument": refused,
        "refused_reason": refused_reason,
        "decision_changed": 0 <= x_probed != INCUMBENT_X,
        "delta": _descendant_delta(x_probed),
    }
    record["as_expected"] = (
        refused if control.get("refused_by_instrument")
        else record["decision_changed"] == bool(
            control["expects_changed_decision"]))
    return record