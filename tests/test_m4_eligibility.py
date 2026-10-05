"""M4's eligibility precondition, and whether any revision can satisfy it.

M4 asks for a parent-versus-revised comparison on fresh acquisition episodes.
Every downstream step depends on one unanswered question: does an eligible
revision exist? The run artifact says no for the six replies it dispatched
(`reports/evidence/inv_r1_e4/result.json`), and every other "eligible" verdict
in that artifact belongs to a reviewer-authored control rather than to a model.
Nothing in the tree says whether the rule refuses on its merits or refuses
because of a property of the prompt that produced those six replies.

It refuses because of the prompt. The rule is correct and these tests do not
relax it. The prompt asked for a computed value over a view carrying no
observation, so every natural reading of it yields 0, which is the one integer
the delegation gate refuses; and it forbade the bare literal that would have
cleared that gate, which gate 4 refuses in turn. The prompt excluded the only
admissible answer while withholding the fact that excluded it
(`reports/workstreams/m4-eligibility.md:162-196`).

So the claim pinned here is a property of the repaired prompt, not of its
wording. A prompt is repaired only if a competent reader following it produces
bytes the rule admits, and the only honest way to check that without a model
call is to take the expressions the prompt offers, put each through every gate
that does not need a database, and read what integer each names at the view the
rule judges on. The tests below do that, so they can fail: the first fails on
the prompt that produced E4's six refusals and passes on the repaired one.

Gate 6 was checked by reading the probed expression and evaluating it against
`channel._reducer_argmax`, not by executing `classify_revision`, which opens a
disposable PostgreSQL database to run the step under real authority. That is
stated wherever the conclusion rests on it.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as revision

CAMPAIGN = ROOT / "reports" / "evidence" / "inv_r1_e4" / "run" / "campaign.json"

# The view `_admit` hands the rule: one real view, no observation carried yet.
# `learner_revision.py` builds it and `experience` is empty, because the
# decision is made before anything has been observed.
ADMISSION_VIEW = {"experience": [], "round": 1, "frontier": [], "step": 0}

# A backticked span in the prompt. The repaired prompt marks its worked
# examples this way, and the rule that reads them does not care why they are
# backticked, so an example written in any other markup is not read as one.
EXAMPLE_SPAN = re.compile(r"`([^`\n]+)`")

# The prompt as it stood when E4 dispatched its six replies. Kept verbatim so
# the discriminating test can be shown to fail on it rather than asserted to.
BROKEN_USER_TEMPLATE = """\
Rewrite the agent's improvement step so it chooses which input to probe.

The only thing you may change is the `x` in the probe action below. Emit the
whole function, unchanged except for that one integer.

```python
{template}
```

The integer must satisfy 0 <= x < 16. It must be computed from the view or
the state, never written as a constant. Reply with the function only. Start
your reply with ```python and end it with ```."""


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
    return eval(compile(ast.Expression(expressions[0]), "<x>", "eval"), {},
                {"view": ADMISSION_VIEW, "len": len})


def _offered_expressions(prompt: str) -> list:
    """Every expression the prompt offers as an example of an acceptable x.

    Found by mechanism rather than by wording. A backticked span that parses as
    an expression and evaluates to an integer at the admission view is an
    example the prompt is offering, whether or not it is admissible. Nothing
    here compares the prompt against expected text, so rewording around an
    example does not fail this, while replacing an example with one the rule
    refuses does.

    A bare literal counts as an offer even though it is refused, because
    offering one is the original defect coming back through a different door:
    the reader copies it and gate 4 refuses the reply. Filtering ineligible
    examples out before the assertion would hide exactly that.
    """
    offered = []
    for span in EXAMPLE_SPAN.findall(prompt):
        try:
            node = ast.parse(span.strip(), mode="eval").body
        except SyntaxError:
            continue
        try:
            value = eval(compile(ast.Expression(node), "<x>", "eval"), {},
                         {"view": ADMISSION_VIEW, "len": len})
        except Exception:
            continue
        if type(value) is int:
            offered.append(span)
    return offered


def _admissible(source: str) -> dict:
    """Run one candidate through every gate that does not need a database."""
    moved = channel.unauthorised_change(channel.IMPROVE_LOW_SOURCE, source)
    return {
        "emits_probe": channel._emits_probe(source),
        "data_dependent": channel._x_is_data_dependent(source),
        "in_scope": not moved,
        "x": _first_choice(source),
        "delegates": _first_choice(source) in channel._reducer_argmax(
            ADMISSION_VIEW),
    }


def test_the_repaired_prompt_offers_an_expression_every_gate_admits() -> None:
    """The discriminating test: the prompt names a reply that is eligible.

    E4's prompt offered no expression at all, so a reader following it exactly
    produced 0 six times out of six and was refused every time. The repaired
    prompt offers worked examples, and this asserts that each one survives
    gate 3, gate 4 and gate 5 as actual bytes and names a non-zero integer at
    the admission view.

    It fails on the prompt that produced the six refusals, because that prompt
    offers nothing this can read, and it fails again if any example is later
    changed to one the rule refuses. Neither failure is a wording change.
    """
    offered = _offered_expressions(revision.prompt_for()["user"])

    assert offered, (
        "the prompt offers no expression that names a non-zero integer at the"
        " admission view, so a reader following it produces the refused 0"
        " again; this is the defect E4 recorded as an unexplained zero")

    for expression in offered:
        report = _admissible(channel._revision_source("(%s)" % expression))
        assert report["emits_probe"], "%s emits no probe" % expression
        assert report["data_dependent"], (
            "%s is not read from the view, so gate 4 refuses it as a task"
            " solver" % expression)
        assert report["in_scope"], (
            "%s moves a decision the interface does not authorise" % expression)
        assert not report["delegates"], (
            "%s names %d, which is the frozen reducer's own first choice, so"
            " gate 6 refuses it as delegation"
            % (expression, report["x"]))

    assert _offered_expressions(
        BROKEN_USER_TEMPLATE.format(template=revision.template_for())) == [], (
        "the prompt that produced E4's six refusals is expected to offer no"
        " eligible expression; if it now does, this test is not discriminating"
        " and the finding it carries has been stated wrong")


def test_the_prompt_no_longer_forbids_the_only_reply_that_succeeds() -> None:
    """The old instruction excluded every admissible answer.

    It required a computed value and forbade a constant. A constant is refused
    by gate 4 and a computed value over an empty experience is 0, which gate 6
    refuses, so the instruction left the model no way through. The repaired
    prompt has to have dropped that prohibition, and dropping it is a
    relaxation the rule's own gates still bound.
    """
    prompt = revision.prompt_for()["user"]

    assert "never written as a constant" not in prompt, (
        "the prompt still forbids the literal, and gate 4 still refuses it, so"
        " the model is again left with only the computed value that lands on"
        " the refusal")

    literal = channel._revision_source("12")
    assert not channel._x_is_data_dependent(literal), (
        "a bare literal is no longer refused by gate 4; if that changed the"
        " argument above no longer holds and the rule did")
    assert _first_choice(literal) == 12


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


def test_the_prompt_states_the_refused_integer_and_the_empty_case() -> None:
    """The prompt supplies the two facts a reader cannot infer.

    Neither the template nor the reducer says which integer is refused, and
    nothing says the experience is empty on the step that spends the probe.
    Both were the reason six correct replies were refused. Asserting the
    guidance carries them is what makes the previous test's passing mean
    something: the prompt cannot go back to asking for a computed value alone.
    """
    prompt = revision.prompt_for()["user"]

    assert "empty" in prompt and "0" in prompt, (
        "the prompt no longer explains the empty-experience case that makes"
        " every plain reading of it evaluate to 0")
    assert re.search(r"picks input 0 first", prompt), (
        "the prompt no longer names the integer the delegation gate refuses")
    assert "in place" in prompt, (
        "the prompt no longer states that the expression must be written at"
        " the probe site; binding it to a name is refused step-skeleton")


def test_binding_x_to_a_name_is_refused_and_the_prompt_says_so() -> None:
    """A second constraint the old prompt left to be discovered at cost.

    Binding the expression to a name before the probe is a statement the
    incumbent does not contain, so `unauthorised_change` refuses it
    `step-skeleton`. Measured here so the prompt's claim about it is a fact
    rather than a warning.
    """
    bound = channel.IMPROVE_LOW_SOURCE.replace(
        'inner = {"kind": "probe", "inputs": {"x": 3},',
        'picked = len(view["experience"]) or 12\n'
        '        inner = {"kind": "probe", "inputs": {"x": picked},', 1)

    assert bound != channel.IMPROVE_LOW_SOURCE, (
        "the template no longer contains the site this test rewrites")
    assert channel.unauthorised_change(
        channel.IMPROVE_LOW_SOURCE, bound)["decision"] == "step-skeleton", (
        "binding x to a name is no longer refused; if that changed, the"
        " prompt's warning is stale")


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