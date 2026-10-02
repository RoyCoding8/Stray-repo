"""The scope check must not be repairable by loosening it.

`test_s09_e4_channel.py` had a red test whose cause was its own fixture, not
the freeze: it built a STEP program by hand, rewriting the whole step
skeleton to probe a different experience index. That program differs from
the incumbent everywhere, so `classify_revision` refused it as
`changes-an-unauthorised-decision` / `step-skeleton` — correctly, since the
only change a revision is authorised to make is the probed input.

The obvious way to make that test green again is to stop comparing against
the incumbent. This file exists so that repair cannot happen quietly.

Three claims, each asserted against a literal:

1. An authorised change - the probed input, and nothing else - is admitted.
   Stated positively, because a guard that refused everything would also
   pass a file of refusals and leave milestone C with no live experiment.
2. The admitted and refused verdicts are two different shapes. The admitted
   one carries `selected_evidence` and no `reason`; the refused one carries
   `reason` and no `selected_evidence`. Both halves are asserted, so a
   verdict that grew both keys would fail here.
3. All six unauthorised variants are still refused, each naming the decision
   it moved. They are derived from this file's own admitted fixture rather
   than imported, so a change to that fixture cannot quietly narrow the set.

Deterministic and offline: no network, no live model, no execution authority
required. `classify_revision` answers every question asked here before it
reaches the gate that executes the revision.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import improve_channel as channel


def _view(observations=None) -> dict:
    """A learner view in the shape `_step_view` builds.

    An observation carries `y` as the instrument's own 4-bit vector, not as
    a scalar. It used to be written `{"x": 2, "y": 1}` here, which parsed
    and was silently wrong: the incumbent step reads `exp[-1]["y"][0]`, so a
    scalar raised inside the child process. Before lane A8 the raise was
    swallowed into an empty choice list and the revision was admitted as
    eligible having selected nothing; afterwards execution is real and the
    same bad fixture refused the whole verdict. Either way the fixture was
    not the shape it claimed to be. `RuleSession._observed` is the source of
    the real one, and every live observation in the tree is a 4-list.
    """
    return {
        "frontier": [{"task": "t", "capability": "c"}],
        "experience": list(observations or []),
        "authority_remaining": {"queries": 8, "steps": 6},
    }


# The authorised change, and the only one. It names the input the learner
# already probed rather than a constant, so the bytes are a selector rather
# than a solver, and every other decision is the incumbent's own.
ADMITTED_PROBE = 'view["experience"][0]["x"]'


def _admitted() -> str:
    """The incumbent with its probed input replaced and nothing else.

    Built through the module's own builder rather than by string surgery
    here, so this file cannot drift from the incumbent it claims to differ
    from. If that builder ever stops producing a program the freeze admits,
    the tests below fail rather than this helper quietly widening.
    """
    return channel._revision_source(ADMITTED_PROBE)


def test_the_authorised_change_is_admitted_with_the_incumbents_own_bytes():
    """Positive, because refusing everything would satisfy the guard.

    This is the claim milestone C rests on: a revision that rewrites the
    probed input and nothing else is an eligible intervention, so the
    channel still admits something and the live experiment is still runnable.
    """
    verdict = channel.classify_revision(_admitted(), views=[_view([{"x": 2, "y": [1, 0, 0, 1]}])])

    assert verdict["eligibility"] == channel.ELIGIBLE, (
        "a revision that changes the probed input and nothing else is no "
        "longer eligible, so the freeze has closed over the authorised kind "
        "and milestone C has nothing left to run: %r" % (verdict,))


def test_the_admitted_revision_normalises_to_the_incumbent():
    """The admitted bytes differ from the incumbent only at the probed input.

    Blanking that input is what makes the comparison fair, so a revision
    that normalises to the incumbent has moved nothing the interface does
    not name. This pins the mechanism rather than the verdict, so a freeze
    that stopped comparing at all could not pass by accident.
    """
    assert channel.unauthorised_change(
        channel.IMPROVE_LOW_SOURCE, _admitted()) == {}


def test_an_admission_carries_selected_evidence_and_no_reason():
    """The admitted shape, asserted as literals.

    A caller that reads `verdict["reason"]` raises on this verdict; a caller
    that reads `verdict.get("reason", "eligible")` reports an admitted
    revision as having no stated reason. Neither is visible unless the
    absence is asserted, so it is asserted here.
    """
    verdict = channel.classify_revision(_admitted(), views=[_view([{"x": 2, "y": [1, 0, 0, 1]}])])

    assert verdict["eligibility"] == channel.ELIGIBLE
    assert "selected_evidence" in verdict
    assert "reason" not in verdict, (
        "the admitted verdict grew a `reason` key, so a caller reading it "
        "unconditionally could no longer tell an admission from a refusal "
        "by that key alone: %r" % (verdict,))


def test_a_refusal_carries_a_reason_and_no_selected_evidence():
    """The refused shape, asserted as literals, and it is the mirror.

    A fixed input is refused as a solver whatever the learner has seen, so
    this half needs no scope argument and survives any correct freeze.
    """
    verdict = channel.classify_revision(
        channel._revision_source("3"), views=[_view([{"x": 2, "y": [1, 0, 0, 1]}])])

    assert verdict["eligibility"] == channel.INELIGIBLE_SOLVER
    assert "reason" in verdict
    assert verdict["reason"] == (
        "revision picks a fixed input whatever the learner has seen, so it "
        "answers the task instead of choosing what to observe")
    assert "selected_evidence" not in verdict, (
        "the refused verdict grew a `selected_evidence` key, so the two "
        "shapes are no longer told apart by their keys: %r" % (verdict,))


def test_the_two_verdict_shapes_are_disjoint():
    """Both halves in one test, so neither can drift toward the other.

    The two bugs this pins are symmetric and neither shows up alone. A
    verdict carrying both keys would satisfy either half on its own.
    """
    admitted = channel.classify_revision(
        _admitted(), views=[_view([{"x": 2, "y": [1, 0, 0, 1]}])])
    refused = channel.classify_revision(
        channel._revision_source("3"), views=[_view([{"x": 2, "y": [1, 0, 0, 1]}])])

    assert ("reason" in admitted) is False
    assert ("selected_evidence" in refused) is False
    assert ("selected_evidence" in admitted) is True
    assert ("reason" in refused) is True


# --- the six variants ------------------------------------------------------
#
# Each is this file's own admitted fixture with exactly one unauthorised
# change, so a future repair that loosened the freeze would be caught here
# even if it left the first test green.

ALLOC = '"requested_resources": {"queries": 1, "steps": 1}'
CONSTRUCT = 'strategy = "high" if first[0] == 1 else "low"'

UNAUTHORISED = {
    "probe-allocation-raised": (
        ALLOC, '"requested_resources": {"queries": 8, "steps": 8}',
        "probe-allocation"),
    "probe-allocation-zeroed": (
        ALLOC, '"requested_resources": {"queries": 0, "steps": 0}',
        "probe-allocation"),
    "construction-forced": (
        CONSTRUCT, 'strategy = "high"', "candidate-construction"),
    "construction-rewritten": (
        CONSTRUCT, 'strategy = "high" if len(first) > 99 else "low"',
        "candidate-construction"),
    "target-rewritten": (
        '"target": "rule-improve"', '"target": "rule-bypass"', "probe-target"),
    "step-skeleton-rewritten": (
        'state = {"step": 1}', 'state = {"step": 2}', "step-skeleton"),
}


@pytest.mark.parametrize("name", sorted(UNAUTHORISED))
def test_the_unauthorised_change_is_still_refused_and_names_its_decision(name):
    """A future repair may not quietly loosen the freeze.

    Derived from `_admitted()` rather than from a baseline held elsewhere,
    so this set cannot shrink when that fixture is edited.
    """
    old, new, decision = UNAUTHORISED[name]
    admitted = _admitted()
    assert old in admitted, (
        "the %s anchor is no longer in this file's admitted fixture, so the "
        "variant below is no longer testing what its name claims: %r"
        % (name, old))

    verdict = channel.classify_revision(
        admitted.replace(old, new, 1), views=[_view([{"x": 2, "y": [1, 0, 0, 1]}])])

    assert verdict["eligibility"] == channel.INELIGIBLE_OUT_OF_SCOPE
    assert "revision changed the %s" % decision in verdict["reason"]


def test_the_probe_input_is_the_only_site_the_freeze_blanks():
    """Why the six above are the complete set this file can state.

    The freeze blanks the value bound to an `x` key and compares what is
    left. So a revision differing only at such a key is admitted, and one
    differing anywhere else is refused. A freeze that blanked a second site
    would admit variants no test here refuses, so the set is closed over the
    one named site rather than left to grow.
    """
    incumbent_shape = channel._program_shape(channel.IMPROVE_LOW_SOURCE)
    revision_shape = channel._program_shape(_admitted())

    assert channel._same(incumbent_shape, revision_shape), (
        "the admitted fixture now differs from the incumbent somewhere other "
        "than the probed input, so it is no longer the authorised kind and "
        "the variants above are testing a different thing")