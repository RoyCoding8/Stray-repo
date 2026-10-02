"""A revision's chosen construction must reach its descendant.

`improve_channel` declared the model constructor a leaf effect and, in the
same breath, owned a fixed research script. `leaf_construct` resolved the
program it installed with `imp_source = _STRATEGY_SOURCE[strategy]`, a
two-member dict written at module scope, and `REACHABLE_EVIDENCE` was the
sorted set of that dict's two values. So the evidence any descendant could
ever gather was two integers no matter what a revision decided, and the
module said so itself at what is now `improve_channel.py:625-628`: a
descendant runs the menu's input, not the one the revision selected.

This lane repairs that boundary and nothing else. The descendant's
construction is now derived from its parent's own bytes, carrying the
input the revision actually probed, so the choice survives adoption instead
of being replaced by a menu the reviser could not have changed.

Four things are asserted here, and each is asserted against the artifact a
reader would check rather than against a return value:

1. the reachable set is computed from a program, and two programs with
   different procedures produce different sets;
2. a revision's choice reaches the descendant, read back out of the
   descendant's own bytes;
3. the descendant's bytes differ from its parent's, and differ at the
   probed input and nowhere else - asserted with `unauthorised_change`,
   the instrument lane C2 built, so this lane and that one grade the same
   difference the same way;
4. the constructor gained no authority. It is still a leaf effect, so it
   still cannot move the grant, the used-so-far counters, the evaluator
   identity, the sealed results or the execution limits - asserted
   positively, by constructing a descendant and showing the frozen state
   and the authority request are exactly what they were.

Lane C2's freeze is untouched and this lane is not a way around it. C2
admits a revision that changes the probed input and nothing else, and
`unauthorised_change` is what says so. Using it here means the descendant
this lane builds is provably the parent's procedure with one decision
substituted, which is the same claim C2 makes about a revision, applied
to a construction.

Deterministic and offline. No network, no live model call, no child
execution: every assertion here reads bytes and runs pure functions.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel

# Small on purpose. A construction decision is a discrimination question
# here, not a significance test; the run's own cohort is where a real
# effect is estimated.
COHORT = list(range(24))

# Two revisions of the same boundary that differ only in the input they
# probe, which is the one change lane C2 authorises.
REVISION_A = 5
REVISION_B = 8


def _mission() -> dict:
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [{"instrument": "boolean-rule-v1",
                          "split": "dev", "seed": 4}],
    }


def _bound_store(tmp_path, name="c4.json"):
    from experiments.ad01 import frontier
    store = frontier.create_store(
        tmp_path / name, namespace=frontier.NAMESPACE, mission=_mission(),
        authority={"queries": 16, "steps": 12})
    base = channel.make_control("low")
    store.bind_active(base)
    return store, base


def _adopt(store, source, control_id):
    """Bind a revision onto the store, the way a live run adopts one.

    Adoption needs no child execution, so this lane never needs execution
    authority. The package is assembled the way `channel_controls` assembles
    its own rather than borrowed from the mechanism under test, so a
    revision cannot be admitted here by a bug in the thing it revises.
    """
    from experiments.ad01 import frontier

    parent = store.active_package
    package = {
        "control_id": control_id, "origin": channel.ORIGIN,
        "source_kind": "fixed-menu", "op_source": parent["op_source"],
        "imp_source": source,
        "op_digest": frontier.source_digest(parent["op_source"]),
        "imp_digest": frontier.source_digest(source),
        "parent_digest": parent["package_digest"], "provenance": None,
        "provenance_digest": None, "version": int(parent["version"]) + 1,
        "authority_request": dict(parent["authority_request"]),
        "obligations": list(parent["obligations"]),
        "channel": parent["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    store.adopt_revision(package)
    return store.active_package


# --- 1. the reachable set comes from a program -----------------------------


def test_reachable_evidence_derives_from_a_revision():
    """A function of the program, not a constant beside it.

    `REACHABLE_EVIDENCE` was the sorted set of a two-member dict's values,
    so it was two integers for every revision in the world. What a
    descendant gathers is a property of the descendant's own bytes, and
    that is now something a caller asks the program.
    """
    low = channel.reachable_evidence(channel.IMPROVE_LOW_SOURCE)
    high = channel.reachable_evidence(channel.IMPROVE_HIGH_SOURCE)

    assert low == ("3",), (
        "the low program no longer reports the input it probes: %r" % (low,))
    assert high == ("11",), (
        "the high program no longer reports the input it probes: %r"
        % (high,))


def test_two_procedures_yield_different_reachable_sets():
    """The claim that makes it inheritable rather than merely computed.

    If every procedure reported the same set, the function would be a
    constant wearing a parameter, and a revision would still be choosing
    between two things it cannot name.
    """
    from experiments.ad01 import frontier

    low = channel.reachable_evidence(channel.IMPROVE_LOW_SOURCE)
    high = channel.reachable_evidence(channel.IMPROVE_HIGH_SOURCE)
    assert low != high

    # And through the real path: two revisions that differ only in the
    # input they probe produce two different descendants' worth of
    # reachable evidence.
    assert channel.reachable_evidence(
        channel._revision_source(str(REVISION_A))) == (str(REVISION_A),)
    assert channel.reachable_evidence(
        channel._revision_source(str(REVISION_B))) == (str(REVISION_B),)
    assert frontier.source_digest(
        channel._revision_source(str(REVISION_A))) != frontier.source_digest(
        channel._revision_source(str(REVISION_B)))


def test_the_construction_menu_is_gone():
    """The two-member selector is deleted, not extended.

    Growing the menu to three members would leave a reviser choosing
    between three things, which is the same defect with a larger number on
    it. What a revision can reach is now a property of the revision.
    """
    assert not hasattr(channel, "_STRATEGY_SOURCE"), (
        "the fixed two-member source menu is still in the module, so the"
        " constructor still owns a research script a reviser could not"
        " have changed")
    assert not hasattr(channel, "REACHABLE_EVIDENCE"), (
        "the module still publishes a reachable set derived from that menu;"
        " a caller reading it is reading a fixed script, not a revision")


def test_the_reachable_range_is_no_longer_two_wide():
    """Measured, not asserted from a constant.

    Every probed input builds a different descendant, so the decision the
    channel asks about reaches more than the two the menu allowed. This is
    the lane's headline claim, so it is measured over the cohort rather
    than read off a table.
    """
    means = {p: channel.evaluate_lineage(
        [p], split="dev", seeds=COHORT)["mean"] for p in range(16)}

    distinct = sorted({round(value, 12) for value in means.values()})

    assert len(distinct) > 2, (
        "the descendant a revision can reach still only takes %d distinct"
        " values across all sixteen inputs, so the construction decision is"
        " as narrow as the two-member menu it replaced: %r"
        % (len(distinct), means))
    assert distinct[0] < distinct[-1], (
        "every probed input builds the same descendant, so the decision"
        " cannot reach anything at all: %r" % (means,))


# --- 2. the revision's choice reaches the descendant ----------------------


def test_revision_chosen_construction_reaches_the_descendant(tmp_path):
    """Asserted by reading the descendant's bytes, not a return value.

    The revision is adopted, so it is the program a descendant would
    actually be built from. The descendant's own source is then asked what
    it probes, and the answer is the revision's choice.
    """
    store, base = _bound_store(tmp_path, "reach.json")
    revision = channel._revision_source(str(REVISION_B))
    adopted = _adopt(store, revision, "revision-x%s" % REVISION_B)

    assert channel.bound_improve_source(store) == revision, (
        "the store did not adopt the revision, so the descendant would be"
        " built from the incumbent whatever this test says: %r" % (adopted,))

    descendant = channel.leaf_construct(REVISION_B, adopted, 1)

    assert channel.reachable_evidence(descendant["imp_source"]) == (
        str(REVISION_B),), (
        "the revision probed input %s and its descendant probes %r, so the"
        " choice did not survive into the descendant: %r"
        % (REVISION_B,
           channel.reachable_evidence(descendant["imp_source"]),
           descendant["control_id"]))


def test_two_revisions_build_two_different_descendants(tmp_path):
    """Same parent, different choices, different descendants."""
    store, base = _bound_store(tmp_path, "pair.json")
    parent = channel.leaf_construct(REVISION_A, base, 1)
    other = channel.leaf_construct(REVISION_B, base, 1)

    assert parent["imp_source"] != other["imp_source"], (
        "two descendants built from the same parent by two different"
        " decisions carry the same improvement bytes, so the decision"
        " changed nothing: %r" % (parent["control_id"],))
    assert channel.reachable_evidence(parent["imp_source"]) == (
        str(REVISION_A),)
    assert channel.reachable_evidence(other["imp_source"]) == (
        str(REVISION_B),)


def test_the_same_procedure_builds_the_same_descendant():
    """Inheritance has to be exact when nothing changed.

    If the constructor perturbed the bytes on its own, every descendant
    would differ from its parent and 'differs because the procedure
    differs' would mean nothing.
    """
    parent = channel.make_control("low")
    descendant = channel.leaf_construct(
        channel.INCUMBENT_EVIDENCE[0], parent, 1)

    assert descendant["imp_source"] == parent["imp_source"], (
        "a descendant built from the incumbent's own decision is not the"
        " incumbent's bytes, so the constructor changes something the"
        " revision did not ask it to change")


# --- 3. the bytes differ, and only where the decision is ------------------


def test_descendant_source_differs_from_parent_source():
    """The named claim, asserted at the decision rather than in general.

    The descendant's improvement bytes differ from its parent's, and
    `unauthorised_change` is what says where. Blanking every probed input
    from both sides and comparing the programs leaves no difference, which
    proves the substitution is the whole of the change rather than one
    change among several. That is lane C2's own instrument applied to a
    construction, so the two lanes grade one claim the same way.
    """
    parent = channel.make_control("low")
    descendant = channel.leaf_construct(REVISION_B, parent, 1)

    assert descendant["imp_source"] != parent["imp_source"], (
        "the descendant carries its parent's improvement bytes, so the"
        " revision's construction did not reach it: %r"
        % (descendant["control_id"],))
    assert channel.unauthorised_change(
        parent["imp_source"], descendant["imp_source"]) == {}, (
        "the descendant differs from its parent at a decision other than"
        " the probed input, so the constructor changed more than it was"
        " asked to change: %r" % (
            channel.unauthorised_change(
                parent["imp_source"], descendant["imp_source"]),))


def test_the_descendant_keeps_its_parents_operational_bytes():
    """Construction is the improvement program only.

    `adopt_revision` refuses a revision whose operational bytes differ, so
    a constructor that rebuilt them would produce a descendant the store
    would reject. Asserted on the bytes rather than on the refusal, so a
    reader sees what was kept.
    """
    parent = channel.make_control("low")
    descendant = channel.leaf_construct(REVISION_B, parent, 1)

    assert descendant["op_source"] == parent["op_source"]
    assert descendant["op_digest"] == parent["op_digest"]
    assert descendant["parent_digest"] == parent["package_digest"]
    assert descendant["version"] == parent["version"] + 1


# --- 4. the constructor is still a leaf effect ----------------------------


def test_the_constructor_gained_no_authority(tmp_path):
    """Positive, not implied by the absence of a failure.

    Constructing a descendant must leave the grant, the used-so-far
    counters, the evaluator identity, the sealed results and the execution
    limits exactly as they were, must not widen the authority the
    descendant may request, and must not attach any of them to the
    package it builds. A constructor is a leaf effect, and this is what
    that says once it builds bytes rather than choosing between two.
    """
    from experiments.ad01 import frontier

    store, base = _bound_store(tmp_path, "authority.json")
    before = channel.frozen_state(store)
    before_digest = frontier.canonical(before)

    descendant = channel.leaf_construct(REVISION_B, base, 1)

    assert frontier.canonical(channel.frozen_state(store)) == before_digest, (
        "constructing a descendant moved the frozen state, so the"
        " constructor is no longer a leaf effect: %r"
        % (channel.frozen_state(store),))
    assert descendant["authority_request"] == base["authority_request"], (
        "the descendant asked for different authority than its parent, so"
        " construction became a way to spend more: %r"
        % (descendant["authority_request"],))
    for field in channel.FROZEN_FIELDS:
        assert field not in descendant, (
            "the constructed package carries %r, so a descendant can read"
            " it without asking the store" % (field,))


def test_a_construction_that_reaches_for_the_grant_is_caught(tmp_path):
    """The positive half of the same property.

    A procedure that tries to write the grant is refused by the same check
    that refuses a revision for it, whether it is offered as a revision or
    as the construction a descendant is built from. `frozen_state` is
    captured before the bytes run and compared after, so a write that got
    past the static check would still be caught rather than trusted.

    The revision differs from the incumbent at the probed input and at one
    grant write and nowhere else, so the scope check would admit it and
    the frozen-write check is the only thing that can refuse it. That is
    what makes this a test of the constructor's lack of authority rather
    than of the freeze, which lane C2 already owns.
    """
    from experiments.ad01 import frontier

    store, base = _bound_store(tmp_path, "grant.json")
    before_digest = channel._frontier.canonical(channel.frozen_state(store))
    greedy = channel._revision_source(
        "3 if not view[\"experience\"] else 8").replace(
            'def STEP(view, state):',
            'def STEP(view, state):\n    grant = {"queries": 99}',
            1)
    assert greedy != base["imp_source"], (
        "the fixture did not rewrite anything, so it is not testing the"
        " check: %r" % (base["imp_source"],))
    assert channel._attempts_frozen_write(greedy), (
        "the fixture is no longer a frozen write, so the refusal it is"
        " asserting cannot fire: %r" % (greedy,))
    views = []
    for _ in range(2):
        view = store.step_view(frontier.IMPROVE, base)
        view["experience"] = []
        views.append(view)

    verdict = channel.admit_revision_under_freeze(store, greedy, views)

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE, (
        "a construction that writes the grant was not refused as one: %r"
        % (verdict,))
    assert channel._frontier.canonical(
        channel.frozen_state(store)) == before_digest


def test_constructing_a_descendant_does_not_touch_the_store(tmp_path):
    """The constructor reads its parent; it does not write to the world.

    Adoption is the only step that changes what is bound, and it is a
    separate call the store guards itself. Constructing the candidate
    leaves the store's bound program, its lineage and its counters as they
    were.
    """
    store, base = _bound_store(tmp_path, "leaf.json")
    lineage_before = len(store._doc["lineage"])
    digest_before = store.active_digest

    channel.leaf_construct(REVISION_B, base, 1)

    assert store.active_digest == digest_before, (
        "constructing a descendant rebound the store's active program")
    assert len(store._doc["lineage"]) == lineage_before, (
        "constructing a descendant appended lineage, which is adoption's"
        " authority and not the constructor's")


# --- the boundary between this lane and lane C2 ---------------------------


def test_the_constructor_is_not_a_way_around_the_freeze(tmp_path):
    """C2's claim about a revision, applied to a construction.

    A revision that moves another decision is refused, and so is a
    descendant whose construction differs from its parent at another
    decision. The two lanes compose: the freeze says what a reviser may
    change, and the inheritance says that what it is allowed to change
    survives into the descendant.
    """
    store, base = _bound_store(tmp_path, "compose.json")
    revision = channel._revision_source(str(REVISION_B))
    adopted = _adopt(store, revision, "compose-x%s" % REVISION_B)

    verdict = channel.classify_revision(revision, [], incumbent=None)

    assert verdict["eligibility"] == channel.INELIGIBLE_NO_BOUNDARY, (
        "a revision with no learner view is refused for the boundary, not"
        " admitted on the strength of its bytes: %r" % (verdict,))

    descendant = channel.leaf_construct(REVISION_B, adopted, 1)

    assert channel.unauthorised_change(
        adopted["imp_source"], descendant["imp_source"]) == {}, (
        "the construction moved a decision the interface does not name, so"
        " the constructor is a way around the freeze rather than inside it")