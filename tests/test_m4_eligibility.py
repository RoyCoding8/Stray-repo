"""M4's eligibility precondition, and whether any revision can satisfy it.

M4 asks for a parent-versus-revised comparison on fresh acquisition episodes.
Every downstream step depends on one unanswered question: does an eligible
revision exist? The run artifact says no for the six replies it dispatched
(`reports/evidence/inv_r1_e4/result.json`), and every other "eligible" verdict
in that artifact belongs to a reviewer-authored control rather than to a model.
Nothing in the tree says whether the rule refuses on its merits or refuses
because of a property of the prompt that produced those six replies.

These tests pin the answer as a property of the bytes and of the prompt, so a
reader does not have to re-derive it, and so a later change to either the
eligibility rule or the acquisition prompt has to say so.

The claim is narrow and falsifiable. An eligible revision must name a
non-zero integer at the admission view, because the frozen reducer's own first
choice is 0 and a revision naming 0 is refused as delegation. The prompt asks
for a computed value over a view that carries no observation, so the computed
value at that view is the sum of an empty set, which is 0. That is why six for
six reproduced the reducer. The tests below read the actual prompt and the
actual rule rather than restating either.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as revision

CAMPAIGN = ROOT / "reports" / "evidence" / "inv_r1_e4" / "run" / "campaign.json"

# The view `_admit` hands the rule: one real view, no observation carried yet.
# `learner_revision.py:1283-1286` builds it and `experience` is empty, because
# the decision is made before anything has been observed.
ADMISSION_VIEW = {"experience": [], "round": 1, "frontier": [], "step": 0}


def _dispatches() -> list:
    return json.loads(CAMPAIGN.read_text())["dispatches"]


def _first_choice(source: str):
    """The integer a program names on the step that spends the probe.

    Evaluated directly rather than through `revision_evidence_choices`, which
    opens a disposable PostgreSQL database to run the step under real
    authority. The expression itself is what the rule delegates on, and
    reading it is the same question without the database.
    """
    expressions = channel._probe_x_expression(source)
    assert expressions, "no probed input to read"
    return eval(compile(ast_expr(expressions[0]), "<x>", "eval"), {},
                {"view": ADMISSION_VIEW, "len": len})


def ast_expr(node):
    import ast
    return ast.Expression(node)


def test_a_revision_naming_zero_is_the_only_delegation() -> None:
    """The delegation gate reduces to one integer at the admission view.

    `delegates_to_frozen_reducer` compares against `_incumbent_choices` and
    `_reducer_argmax`. Both are computed from the version-space reducer's own
    disagreement over unqueried inputs, and at a view carrying no observation
    the first choice of each is 0. A revision naming any other integer is not
    refused for delegation, whatever else the rule says about it.
    """
    assert channel._reducer_argmax(ADMISSION_VIEW) == [0], (
        "the reducer's own first choice is what a revision must differ from;"
        " it is no longer 0, so the exclusion set has moved")
    assert 0 in channel._incumbent_choices(ADMISSION_VIEW)[:1], (
        "the incumbent's first choice is no longer 0")


def test_the_prompt_asks_for_a_value_that_is_zero_at_the_admission_view() -> None:
    """The acquisition prompt's requirement evaluates to the refusal.

    The prompt instructs a computed value rather than a constant, and the only
    view the rule ever judges on carries no observation. Any value computed
    over an empty experience is zero unless the reply takes a branch that
    supplies a literal, and a literal is refused for not being computed.
    These are the two sides of the rule and the prompt lands between them.
    """
    prompt = revision.prompt_for()["user"]
    assert "must be computed from the view" in prompt, (
        "the prompt no longer asks for a computed value, so the argument"
        " below no longer applies")
    for expression in ("len(view[\"experience\"])",
                       "len(view.get(\"experience\", []))",
                       "len(view.get(\"experience\", [])) % 16"):
        assert eval(expression, {}, {"view": ADMISSION_VIEW}) == 0, (
            "%s does not evaluate to 0 at the admission view" % expression)


def test_every_reply_the_campaign_collected_names_zero() -> None:
    """The six recorded replies all land on the refused integer.

    Each is data-dependent and moves nothing but the probed input, so each
    passes the static gates that do not need a database. All six are refused
    for delegation, and reading their expressions shows why rather than
    leaving it to the recorded verdict.
    """
    refused = 0
    for dispatch in _dispatches():
        source = dispatch["source"]
        assert channel._emits_probe(source), "reply emitted no probe"
        assert channel._x_is_data_dependent(source), "reply was not computed"
        assert not channel.unauthorised_change(
            channel.IMPROVE_LOW_SOURCE, source), "reply moved another decision"
        if _first_choice(source) == 0:
            refused += 1
    assert refused == len(_dispatches()) == 6, (
        "expected every recorded reply to name the refused integer; %d of %d"
        % (refused, len(_dispatches())))


def test_an_eligible_revision_is_constructible_from_the_same_prompt() -> None:
    """The rule admits a revision, so the zero is a property of the prompt.

    A reply that reads the view and still names a non-zero integer passes
    every gate the rule has before it needs a database. This is what makes
    the negative a statement about acquisition rather than about
    eligibility: the interface can express the change, and six replies
    written to it did not.
    """
    source = channel._revision_source('(len(view.get("experience", [])) or 12)')
    assert channel._emits_probe(source)
    assert channel._x_is_data_dependent(source), (
        "the reply reads the view, which is what the prompt asks for")
    assert not channel.unauthorised_change(channel.IMPROVE_LOW_SOURCE, source)
    assert _first_choice(source) == 12, (
        "the constructed revision should name a non-zero integer so that it"
        " is not refused for delegation")