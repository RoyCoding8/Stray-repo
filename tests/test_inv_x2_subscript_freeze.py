"""The freeze must reach a frozen field however the revision names it.

Lane C2 made the declared freeze the enforced freeze, and the check was an
AST walk over assignment targets. It recursed into `Subscript.value` and
never looked at `Subscript.slice`, so `view.grant = ...` was refused and
`view["grant"] = ...` was admitted. The gap never showed because every
fixture in the repository writes a bare name, `grant = ...`, which the
`Name` branch catches. Lane C4 found it by asserting the check fires on its
own fixture before relying on the refusal.

So the defect is not one missed branch. It is that the walk enumerated a
few node types it knew about and treated the enumeration as the language.
`del`, annotated assignment and the walrus bind exactly like `=` and were
not in the list either. A partial list of binding positions is the same
bug wearing a different hat, so this file closes the whole set.

Reads are the other half. `remaining = view["grant"]` is a learner reading
its budget, which is legitimate and is the reason the check exists on
targets at all. A read that merely mentions a frozen name is not a write,
so the slice is examined only when the subscript is itself the target.

The last direction is the one that matters for milestone C. A guard that
refused everything would pass a file of refusals and leave no live
experiment, so the authorised kind is asserted eligible on its own account,
and the six variants lane C2 measured are asserted to still refuse for the
reason they refused for.

Deterministic and offline: no network, no live model call, no fixture
gateway, no database.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import improve_channel as channel


def _mission() -> dict:
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [{"instrument": "boolean-rule-v1",
                          "split": "dev", "seed": 4}],
    }


def _bound_store(tmp_path, name="x2.json"):
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


# --- 1. every frozen field, written by subscript --------------------------

# One case per field, each asserted individually, because a check that
# matched a sample would pass with five of the six names broken. The
# frozen set is read off the module so a field added there is a case that
# must be written here rather than a name silently uncovered.
SUBSCRIPT_WRITES = {
    field: 'view["%s"] = {"queries": 99}' % field
    for field in channel.FROZEN_FIELDS
}


def test_the_frozen_set_is_the_six_named_fields():
    """The fixtures below cover the module's own set, not a sample of it.

    A parametrised suite built from `FROZEN_FIELDS` silently loses
    coverage if that tuple shrinks, so the count is asserted rather than
    assumed.
    """
    assert len(channel.FROZEN_FIELDS) == 6, (
        "the frozen field set changed; this file's coverage was written "
        "against six names: %r" % (channel.FROZEN_FIELDS,))
    assert len(SUBSCRIPT_WRITES) == 6


@pytest.mark.parametrize("field", sorted(SUBSCRIPT_WRITES))
def test_a_subscript_write_to_a_frozen_field_is_detected(field):
    """`view["grant"] = ...` names a frozen field and must be refused.

    The string in the subscript plays exactly the role the attribute name
    plays in `view.grant`, so a check that catches one and not the other
    is not checking anything: it is checking a spelling.
    """
    source = SUBSCRIPT_WRITES[field]

    assert channel._attempts_frozen_write(source), (
        "a subscript write to the frozen field %r passed the freeze "
        "check: %r" % (field, source))


def test_the_subscript_write_is_refused_through_the_public_entry(tmp_path):
    """The end-to-end refusal, not just the private predicate.

    `_attempts_frozen_write` is an implementation detail. The verdict a
    caller observes is the contract, so the refusal is asserted where a
    caller reads it, with the reason named.
    """
    store, base = _bound_store(tmp_path, "subscript.json")
    source = channel._revision_source(
        '3 if not view["experience"] else 8').replace(
            'def STEP(view, state):',
            'def STEP(view, state):\n    view["grant"] = {"queries": 99}',
            1)
    assert source != base["imp_source"], (
        "the fixture rewrote nothing, so the refusal cannot be attributed "
        "to the write: %r" % (source,))

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE, (
        "a revision writing a frozen field by subscript was not refused "
        "as one: %r" % (verdict,))


# --- 2. a read is not a write ---------------------------------------------

# The reason the check exists on targets rather than on names. A learner
# reads the remaining budget to decide what it can still afford; two
# fields are enough to show the shape is not special-cased to one.
SUBSCRIPT_READS = {
    "remaining = view[\"grant\"]": "grant",
    "x = view[\"used\"][\"queries\"]": "used",
    "limit = view[\"execution_limits\"][\"max_queries\"]": "execution_limits",
    "sealed = view[\"sealed_results\"]": "sealed_results",
    "who = view[\"authority\"]": "authority",
    "judge = view[\"evaluator\"]": "evaluator",
}


@pytest.mark.parametrize("source", sorted(SUBSCRIPT_READS))
def test_a_subscript_read_of_a_frozen_field_is_not_flagged(source):
    """Reading the frozen state is what a revision is for."""
    assert not channel._attempts_frozen_write(source), (
        "reading a frozen field by subscript was treated as writing it, so "
        "a legitimate revision would be refused: %r" % (source,))


def test_a_read_inside_a_call_and_a_condition_is_not_flagged():
    """The frozen name is nested, not on the target.

    A check that searched the whole subtree would flag both of these. The
    one on the target is the difference between the guard and a blanket
    refusal.
    """
    for source in ('budget = min(view["used"]["queries"], view["grant"]["queries"])',
                   'if view["authority"] and not view["sealed_results"]: pass',
                   'return_value = dict(view["grant"])["queries"]'):
        assert not channel._attempts_frozen_write(source), (
            "a read that merely mentions a frozen field was refused: %r"
            % (source,))


def test_writing_a_key_that_is_not_frozen_is_still_allowed():
    """The guard is named, not general.

    If every subscript write were refused, the six frozen names would be
    an accident of the implementation rather than the contract, and every
    revision that touched the view at all would be ineligible.
    """
    assert not channel._attempts_frozen_write('view["experience"] = []')
    assert not channel._attempts_frozen_write('view["grant_of_last_run"] = 1')


# --- 3. the other write forms --------------------------------------------

# The forms the enumeration did not know about. Each one binds or deletes
# exactly as `=` does, so each one was a hole of the same kind rather than
# a different defect.
OTHER_WRITES = [
    'view["used"] += 1',
    'view["grant"]["queries"] = 99',
    "view['authority'][0] = 1",
    'view["execution_limits"] |= {"max_queries": 99}',
    'del view["sealed_results"]',
    'del view["grant"], view["used"]',
    'del view["used"]["queries"]',
    'view["grant"]: dict = {"queries": 99}',
    'if (grant := {"queries": 99}): pass',
    'view["grant"] = view["used"] = {"queries": 99}',
    'for view["grant"] in ({"queries": 99},): pass',
    'view["grant"], other = {"queries": 99}, 1',
    '*view["grant"], other = (1, 2)',
    'grant: dict = {"queries": 99}',
    'if (grant := {"queries": 99}): pass',
    'for grant in ({"queries": 99},): pass',
    'del grant',
    'del view.grant',
    'for used in ({},): pass',
    'with open("f") as authority: pass',
    'try: pass\nexcept Exception as evaluator: pass',
    'y = [1 for grant in ({1},)]',
    'view.__setitem__("grant", {"queries": 99})',
    'view.__delitem__("used")',
    'object.__setattr__(view, "grant", 1)',
    'object.__delattr__(view, "evaluator")',
]


@pytest.mark.parametrize("source", OTHER_WRITES)
def test_every_binding_form_that_writes_a_frozen_field_is_detected(source):
    """The list of positions, not the positions someone remembered."""
    assert channel._attempts_frozen_write(source), (
        "a write to a frozen field passed the freeze check: %r" % (source,))


def test_the_binding_forms_are_the_ones_the_language_has():
    """The set is closed, so the guard cannot have a hole by omission.

    Python's positions that store a value into a name or delete one are
    enumerated here. A site added to the language would need a case here
    and would fail loudly rather than quietly widening the freeze.
    """
    assert len(OTHER_WRITES) == 26


def test_a_method_named_like_a_refused_builtin_is_not_refused():
    """The refusal follows the act, not the word.

    `obj.eval(...)` is an attribute on a type this program never sees, and
    refusing it would be the guard refusing a name rather than the write it
    stands for. The builtin and the protocol methods are separate sets, and
    this is what keeps the two apart.
    """
    assert not channel._attempts_frozen_write('view.eval("grant")')
    assert not channel._attempts_frozen_write(
        'view.setattr("grant", {"queries": 99})')
    assert channel._attempts_frozen_write('eval("view[\'grant\'] = 1")')


# Two forms a reader reasonably expects in the list above, and which are
# not there because the language does not have them. Asserted rather than
# left to a reader's imagination, because a missing case that cannot
# happen is indistinguishable from a missing case that was not thought
# about.
UNREACHABLE_FORMS = {
    "walrus-on-subscript": 'if (view["grant"] := 1): pass',
    "assignment-expression-on-attribute": 'if (view.grant := 1): pass',
}


@pytest.mark.parametrize("name", sorted(UNREACHABLE_FORMS))
def test_a_walrus_cannot_target_a_subscript_so_the_check_is_not_missing_it(
        name):
    """`ast.parse` rejects it, which is the whole reason it is unreachable.

    A guard with a case for a form the language forbids is a guard testing
    its own imagination. Proving the form cannot be written is what keeps
    `OTHER_WRITES` a list of real positions rather than a list of ideas.
    """
    import ast

    with pytest.raises(SyntaxError):
        ast.parse(UNREACHABLE_FORMS[name])


# --- 4. the authorised revision is still eligible -------------------------

AUTHORISED = '3 if not view["experience"] else 8'


def test_an_authorised_revision_writes_no_frozen_field(tmp_path):
    """The invariant the fix must not break, at the predicate.

    This is the change lane C4 made inheritable: a revision that rewrites
    the probed input and nothing else. If the check refuses it, milestone
    C has no live experiment and the defect has been replaced by a worse
    one.
    """
    source = channel._revision_source(AUTHORISED)

    assert not channel._attempts_frozen_write(source), (
        "the authorised revision was treated as a frozen write, so no "
        "revision can be admitted at all: %r" % (source,))


def test_an_authorised_revision_is_still_eligible(tmp_path):
    """Asserted positively through the mechanism, not inferred.

    The refusal suite and this one cannot both pass by the guard being
    broad, which is the point: the guard has to be narrow enough to admit
    the authorised kind and wide enough to catch the subscript.
    """
    store, base = _bound_store(tmp_path, "authorised.json")
    source = channel._revision_source(AUTHORISED)

    verdict = channel.classify_revision(source, _views(store, base))

    assert verdict["eligibility"] == channel.ELIGIBLE, (
        "the one change the interface names is the one change a revision "
        "is authorised to make, and it was refused: %r" % (verdict,))
    assert verdict["selected_evidence"], (
        "the admitted revision selected no evidence, so the verdict is "
        "asserting a decision it never made: %r" % (verdict,))


def test_every_authored_control_stays_eligible(tmp_path):
    """The channel's own revisions are the admissible kind.

    A freeze that refused the channel's controls would be refusing the
    only revisions anyone has written. Checked against the registry rather
    than a fixture, so moving a builder fails here.
    """
    from experiments.ad01 import channel_controls

    store, base = _bound_store(tmp_path, "controls.json")
    views = _views(store, base)

    for role in sorted(channel_controls.CONTROL_BUILDERS):
        source = channel_controls.build_control(role)["source"]
        assert not channel._attempts_frozen_write(source), (
            "the %s control writes a frozen field: %r" % (role, source))
        verdict = channel.classify_revision(source, views)
        assert verdict["eligibility"] == channel.ELIGIBLE, (
            "the %s control changes only the probed input and was refused "
            "as out of scope: %r" % (role, verdict))


def test_a_constructed_descendant_writes_no_frozen_field():
    """Lane C4's inheritance, which is the authorised kind by construction.

    A descendant is its parent's procedure with the probed input
    substituted. Widening the freeze far enough to catch it would make
    inheritance impossible, so it is asserted here rather than assumed.
    """
    for construction in (3, 8, 11):
        descendant = channel._descendant_source(
            channel.IMPROVE_HIGH_SOURCE, construction)
        assert not channel._attempts_frozen_write(descendant), (
            "constructing x=%s produced a descendant that writes a frozen "
            "field: %r" % (construction, descendant))


# --- 5. lane C2's six variants still refuse, for the same reason ----------

UNAUTHORISED = {
    "probe-allocation-raised": (
        '"requested_resources": {"queries": 1, "steps": 1}',
        '"requested_resources": {"queries": 8, "steps": 8}',
        "probe-allocation"),
    "probe-allocation-zeroed": (
        '"requested_resources": {"queries": 1, "steps": 1}',
        '"requested_resources": {"queries": 0, "steps": 0}',
        "probe-allocation"),
    "construction-forced": (
        'strategy = "high" if first[0] == 1 else "low"', 'strategy = "high"',
        "candidate-construction"),
    "construction-rewritten": (
        'strategy = "high" if first[0] == 1 else "low"',
        'strategy = "high" if len(first) > 99 else "low"',
        "candidate-construction"),
    "target-rewritten": ('"target": "rule-improve"', '"target": "rule-bypass"',
                         "probe-target"),
    "step-skeleton-rewritten": ('state = {"step": 1}', 'state = {"step": 2}',
                                "step-skeleton"),
}


def _data_dependent_baseline() -> str:
    """The baseline lane C2's six are derived from.

    The same shape the audit measured, so a refusal here can only be the
    freeze rather than a fixture that never satisfied the view-dependence
    gate.
    """
    from experiments.ad01 import channel_controls
    return channel_controls._selector(
        channel._revision_source("8"), "8", "3")


def test_the_baseline_every_variant_is_derived_from_is_eligible(tmp_path):
    """The six refusals below are attributable to the freeze.

    If the baseline were ineligible for its own reason, the six would
    still be ineligible and this file would prove nothing.
    """
    store, base = _bound_store(tmp_path, "baseline.json")
    baseline = _data_dependent_baseline()

    assert not channel._attempts_frozen_write(baseline), (
        "the baseline writes a frozen field: %r" % (baseline,))
    verdict = channel.classify_revision(baseline, _views(store, base))
    assert verdict["eligibility"] == channel.ELIGIBLE, (
        "the baseline is not the authorised kind, so the refusals below "
        "are not attributable to the freeze: %r" % (verdict,))


@pytest.mark.parametrize("name", sorted(UNAUTHORISED))
def test_the_unauthorised_variant_still_refuses_with_its_own_reason(
        tmp_path, name):
    """Lane C2's fixture, re-measured against the widened check.

    Widening a guard can quietly reclassify a refusal, so each variant is
    asserted against the decision it moved, not merely against
    ineligibility. A frozen-write refusal here would mean the widened
    check had started refusing revisions for the wrong reason.
    """
    old, new, expected = UNAUTHORISED[name]
    store, base = _bound_store(tmp_path, "%s.json" % name)
    baseline = _data_dependent_baseline()
    assert old in baseline, (
        "the incumbent no longer contains the text this fixture rewrites, "
        "so it is not testing the freeze: %r" % (baseline,))
    revision = baseline.replace(old, new, 1)

    verdict = channel.classify_revision(revision, _views(store, base))

    assert verdict["eligibility"] != channel.ELIGIBLE, (
        "%s moved a decision the revision was not authorised to move and "
        "was still admitted: %r" % (name, verdict))
    assert verdict["eligibility"] == channel.INELIGIBLE_OUT_OF_SCOPE, (
        "%s was refused, but the widened freeze changed its reason: %r"
        % (name, verdict))
    assert expected in verdict["reason"], (
        "%s was refused without naming the change it made: %r"
        % (name, verdict["reason"]))


def test_the_variants_refused_are_the_ones_that_were_measured():
    """Six, so a future edit cannot drop a fixture and leave the rest
    green."""
    assert len(UNAUTHORISED) == 6
