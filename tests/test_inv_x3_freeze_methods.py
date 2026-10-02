"""The freeze refuses a frozen write made through a mapping's own methods.

Lane X2 closed the subscript side: `_attempts_frozen_write` reads the parser's
`Store` and `Del` contexts, so a bare name, an attribute and a literal-key
subscript are all caught. The door beside it was open. `view.update({"grant":
x})`, `view |= {"grant": x}`, `view.pop("grant")`, `view.clear()` and
`view.setdefault("grant", x)` write the same key and reach it with no `Store`
context on a subscript whose key is a literal, so the parser's answer was
"nothing is stored here" and the check returned false. A computed key
(`view[k] = x`) had the same outcome for the opposite reason: the key is not a
literal, so there is nothing to compare against `FROZEN_FIELDS`.

The docstring at `_frozen_key` promised a runtime backstop for exactly the
computed-key case: the before-and-after `frozen_state` comparison in
`admit_revision_under_freeze`. The independent reviewer instrumented it. A
revision's bytes run in a bounded child process against a JSON view that holds
none of the six frozen fields, against disposable stores, never against the
store being compared, so the comparison compares two states that do not
contain the frozen fields and cannot fire. The promise was the reason the gap
survived every gate.

So this file holds two things at once. Every writing form is refused with a
reason that names the form, and the module's own text is checked for the
promise that was never kept. The refusal suite and the eligibility suite are
both here because they cannot both pass by the guard being broad.

What is NOT claimed. There is no runtime backstop. The comparison is a check
that admission itself does not move frozen state, and it cannot observe a
child's writes. What replaces the promise is a default-deny on the two cases
the freeze cannot check by name: a key it cannot read, and a mapping it cannot
name the keys of. Both are refused rather than admitted, so the guard no
longer depends on a layer that does not exist.

Runtime: real PostgreSQL, WSL Ubuntu, fixture gateway only. No live model call,
no network. Every writing form below is a literal source string, and each is
asserted through the public entry a caller reads.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import improve_channel as channel

AUTHORISED = '3 if not view["experience"] else 8'

# The reviewer's finding, verbatim: `update` returns None, so the expression is
# still 3 for the policy and the revision is still the authorised kind, and the
# write still happens. The scope check cannot see it because
# `unauthorised_change` blanks the `x` site before comparing shapes.
SMUGGLED = ('(view.update({"grant": {"queries": 999999, "steps": 999999}})'
            ' or 3) if not view["experience"] else 8')


def _mission() -> dict:
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [{"instrument": "boolean-rule-v1",
                          "split": "dev", "seed": 4}],
    }


def _bound_store(tmp_path, name="x3.json"):
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


# --- 1. every writing form, refused, with the form named ------------------
#
# Each entry is a literal source string. Each is asserted twice: the private
# predicate says the write is caught, and the public entry refuses it with a
# reason that names the form rather than reporting that something differed.

METHOD_WRITES = {
    "dict.update": (
        'def STEP(view, state):\n'
        '    view.update({"grant": {"queries": 999999}})\n'
        '    return {"action": {"kind": "stop", "target": "t",'
        ' "inputs": {}, "requested_resources": {}}, "state": {}}\n',
        "update"),
    "dict.merge-augassign": (
        'def STEP(view, state):\n'
        '    view |= {"grant": {"queries": 999999}}\n'
        '    return {"action": {"kind": "stop", "target": "t",'
        ' "inputs": {}, "requested_resources": {}}, "state": {}}\n',
        "|="),
    "dict.pop": (
        'def STEP(view, state):\n'
        '    view.pop("grant", None)\n'
        '    return {"action": {"kind": "stop", "target": "t",'
        ' "inputs": {}, "requested_resources": {}}, "state": {}}\n',
        "pop"),
    "dict.clear": (
        'def STEP(view, state):\n'
        '    view.clear()\n'
        '    return {"action": {"kind": "stop", "target": "t",'
        ' "inputs": {}, "requested_resources": {}}, "state": {}}\n',
        "clear"),
    "dict.setdefault": (
        'def STEP(view, state):\n'
        '    view.setdefault("grant", {"queries": 999999})\n'
        '    return {"action": {"kind": "stop", "target": "t",'
        ' "inputs": {}, "requested_resources": {}}, "state": {}}\n',
        "setdefault"),
    "computed-subscript-key": (
        'def STEP(view, state):\n'
        '    k = "grant"\n'
        '    view[k] = {"queries": 999999}\n'
        '    return {"action": {"kind": "stop", "target": "t",'
        ' "inputs": {}, "requested_resources": {}}, "state": {}}\n',
        "key"),
}


@pytest.mark.parametrize("label", sorted(METHOD_WRITES))
def test_every_mapping_method_that_writes_a_frozen_field_is_refused(
        tmp_path, label):
    """The public contract, one form per case.

    The reason is asserted to name the form, because a refusal that says only
    "ineligible" cannot tell a reader which boundary held, which is the reason
    every refusal in this module carries its own name.
    """
    source, named = METHOD_WRITES[label]
    store, base = _bound_store(tmp_path, "%s.json" % label.replace(".", "-"))

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE, (
        "a %s that writes the grant was admitted: %r" % (label, verdict))
    assert named in verdict["reason"], (
        "the refusal for the %s form does not name the form, so a reader"
        " cannot tell which write was caught: %r" % (label, verdict["reason"]))


@pytest.mark.parametrize("label", sorted(METHOD_WRITES))
def test_the_private_predicate_agrees_with_the_public_entry(label):
    """The predicate and the entry must not disagree.

    `_attempts_frozen_write` is the thing the reviewer probed directly and the
    thing `admit_revision_under_freeze` calls. If only the entry refused, the
    predicate would still read as admitting the form to anyone measuring it.
    """
    source, _named = METHOD_WRITES[label]

    assert channel._attempts_frozen_write(source), (
        "the %s form passed the private predicate: %r" % (label, source))


def test_the_computed_key_is_refused_because_it_is_unreadable_not_because_it_is_known(
        tmp_path):
    """A computed key is refused for the honest reason.

    Following `k` to what it binds means tracking what every name in the
    program binds to, which is a taint analysis. The freeze does not do one,
    so it declines to admit the write rather than guessing. The reason names
    the unreadable key, so nobody later reads the refusal as a claim that the
    key was resolved and found to be frozen.
    """
    source = ('def STEP(view, state):\n'
              '    k = "harmless"\n'
              '    view[k] = 1\n'
              '    return {"action": {"kind": "stop", "target": "t",'
              ' "inputs": {}, "requested_resources": {}}, "state": {}}\n')
    store, base = _bound_store(tmp_path, "unreadable-key.json")

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE, (
        "a key the freeze cannot read was admitted: %r" % (verdict,))
    assert "key" in verdict["reason"], (
        "the refusal does not say the key was unreadable, so a reader would"
        " take it as a claim that the key was resolved and found frozen:"
        " %r" % (verdict["reason"],))


# --- 2. the write smuggled into the probed-input expression ---------------

def test_the_write_smuggled_into_the_probed_input_is_refused(tmp_path):
    """The demonstrated exploit, at the boundary a caller reads.

    The revision is otherwise the authorised kind: it differs from the
    incumbent at the probed input and nowhere else, so the scope check would
    admit it. Before this lane it returned `eligible` with
    `informs_decision: True` and the write landed.
    """
    store, base = _bound_store(tmp_path, "smuggled.json")
    source = channel._revision_source(SMUGGLED)
    clean = channel._revision_source(AUTHORISED)

    assert channel.classify_revision(clean, _views(store, base))[
        "eligibility"] == channel.ELIGIBLE, (
        "the clean baseline is not eligible, so the refusal below would"
        " pass for the wrong reason")

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE, (
        "a revision that overwrote the grant was admitted as an eligible"
        " intervention: %r" % (verdict,))
    assert verdict.get("informs_decision") is not True, (
        "the verdict still claims it informed a decision while carrying the"
        " write that the claim was hiding: %r" % (verdict,))


def test_the_smuggled_bytes_still_write_the_grant_when_executed(tmp_path):
    """The fixture the refusal above rests on.

    If these bytes did not overwrite the grant, refusing them would prove
    nothing. This runs them the way the bounded child does, against a view
    shaped like the one it receives, and asserts the write lands.
    """
    view = {"grant": 0, "harmless": 1, "task_content": {},
            "observations": [], "frontier": [], "purpose": "improve",
            "mission": "m", "experience": [], "open_questions": [],
            "last_result": None, "eligible_methods": [],
            "remaining": {"queries": 4, "steps": 4},
            "authority_remaining": {"queries": 4, "steps": 4}, "round": 1}
    namespace: dict = {}
    exec(channel._revision_source(SMUGGLED), namespace)  # noqa: S102

    namespace["STEP"](view, {})

    assert view["grant"] == {"queries": 999999, "steps": 999999}, (
        "the bytes no longer write the grant, so this refusal is being"
        " asserted against a program that writes nothing: %r" % (view,))


# --- 3. the authorised construction-procedure revision stays eligible ------

def test_an_authorised_construction_procedure_revision_is_still_eligible(
        tmp_path):
    """Milestone C's deliverable, asserted positively through the entry.

    Not at the predicate, and not by inference. If the widening made every
    revision ineligible, milestone C would have no live experiment and the
    defect would have been replaced by a worse one, so this asserts the whole
    path: admitted, a decision named, evidence selected, and the decision
    reported as informing the round.
    """
    store, base = _bound_store(tmp_path, "authorised.json")
    source = channel._revision_source(AUTHORISED)

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] == channel.ELIGIBLE, (
        "the authorised construction-procedure revision was refused: %r"
        % (verdict,))
    assert verdict["decision"] == channel.DECISION
    assert verdict["selected_evidence"], (
        "the admitted revision selected no evidence, so the verdict is"
        " asserting a decision it never made: %r" % (verdict,))
    assert verdict["informs_decision"] is True, (
        "the verdict stopped reporting a decision, so this case no longer"
        " demonstrates that a legitimate revision survives the widening:"
        " %r" % (verdict,))
    assert verdict["frozen_state_digest"], (
        "the frozen digest was not reported on the admitted path: %r"
        % (verdict,))


def test_a_procedure_that_computes_its_probed_input_is_still_eligible(tmp_path):
    """The controls read the view to choose the input, and still can.

    This is the shape every authored control in the repository has: the
    probed input is a conditional expression over `view["experience"]`. It is
    a computed *value* in a dict literal, which the freeze does not read as a
    key, and it is the change the interface names. If widening the guard
    caught this, inheritance would be impossible.
    """
    from experiments.ad01 import channel_controls

    store, base = _bound_store(tmp_path, "controls.json")
    views = _views(store, base)

    for role in sorted(channel_controls.CONTROL_BUILDERS):
        source = channel_controls.build_control(role)["source"]
        verdict = channel.admit_revision_under_freeze(
            store, source, views)
        assert verdict["eligibility"] == channel.ELIGIBLE, (
            "the %s control writes no frozen field and was refused anyway:"
            " %r" % (role, verdict))


# --- 4. reads stay reads --------------------------------------------------

READS_THROUGH_THE_SAME_ACCESSORS = [
    'remaining = view["grant"]["queries"]',
    'judge = view.get("evaluator")',
    'limits = dict(view["execution_limits"])',
    'have = "sealed_results" in view',
    'for key in view.keys(): pass',
    'budget = min(view["used"], view["authority"])',
    'update = view.update',          # the bound method, never called
]


@pytest.mark.parametrize("source", READS_THROUGH_THE_SAME_ACCESSORS)
def test_a_read_through_those_accessors_is_still_permitted(source):
    """The reason the check is on writes rather than on names.

    A learner reads the remaining budget to decide what it can still afford.
    Five of the six writing methods have no read-only spelling at all, so what
    is asserted here is that naming a frozen field in a read position is still
    free, including through the accessors the writing forms use. Refusing
    these would be refusing the apparatus rather than the attack.
    """
    assert not channel._attempts_frozen_write(source), (
        "reading a frozen field was treated as writing it: %r" % (source,))


def test_a_write_to_a_key_that_is_not_frozen_is_still_allowed():
    """The guard is named, not general.

    `view["experience"] = []` and `view.pop("harmless", None)` touch the same
    object the refused forms touch. What separates them is the name of the
    key, so if these were refused too the six names would be an accident of
    the implementation rather than the contract, and every revision that
    touched the view at all would be ineligible.
    """
    assert not channel._attempts_frozen_write('view["experience"] = []')
    assert not channel._attempts_frozen_write(
        'def STEP(view, state):\n'
        '    view.pop("harmless", None)\n'
        '    view.update({"experience": []})\n')


def test_the_keyless_forms_are_refused_and_that_price_is_stated():
    """`clear()` names no key, so its refusal cannot be about a name.

    The two forms that write every key a mapping holds are refused because
    their receiver is a value the revision was handed rather than one it
    built. That is a coarser rule than the key-taking forms get, and the test
    says so: a revision that clears a mapping it constructed is admitted,
    which is the same line the module draws between `view.eval(...)` and
    `eval(...)`.
    """
    built = ('def STEP(view, state):\n'
             '    mine = {"harmless": 1}\n'
             '    mine.clear()\n'
             '    mine.popitem()\n')
    handed = ('def STEP(view, state):\n'
              '    view.clear()\n'
              '    view.popitem()\n')

    assert not channel._attempts_frozen_write(built), (
        "clearing a mapping the revision built is its own business: %r"
        % (built,))
    assert channel._attempts_frozen_write(handed), (
        "clearing the view writes every key it holds and was admitted: %r"
        % (handed,))


# --- 4b. the alias and the second spelling -------------------------------
#
# Each of these was admitted by the first version of this lane's fix and was
# found by probing the fixed code rather than by reasoning about it, so they
# are here because a guard that closes six spellings and leaves the seventh
# open reads exactly as one that closed the seventh.

ALIAS_WRITES = {
    "aliased-clear": ('def STEP(view, state):\n'
                      '    alias = view\n'
                      '    alias.clear()\n'),
    "aliased-update": ('def STEP(view, state):\n'
                       '    alias = view\n'
                       '    alias.update({"grant": {"queries": 999999}})\n'),
    "aliased-pop": ('def STEP(view, state):\n'
                    '    alias = view\n'
                    '    alias.pop("grant", None)\n'),
    "keyword-update": ('def STEP(view, state):\n'
                       '    view.update(grant={"queries": 999999})\n'),
    "keyword-beside-literal": ('def STEP(view, state):\n'
                               '    view.update({"experience": []},'
                               ' grant={"queries": 999999})\n'),
    "starred-update": ('def STEP(view, state):\n'
                       '    built = {"grant": {"queries": 999999}}\n'
                       '    view.update(**built)\n'),
    "computed-pop-key": ('def STEP(view, state):\n'
                         '    k = "grant"\n'
                         '    view.pop(k, None)\n'),
}


@pytest.mark.parametrize("label", sorted(ALIAS_WRITES))
def test_a_write_through_an_alias_or_a_second_spelling_is_refused(
        tmp_path, label):
    """The receiver and the argument are both read, not just the spelling.

    `alias = view` then `alias.clear()` is the same write as `view.clear()`,
    and a receiver rule that read only the parameter would miss it. The
    keyword and the starred forms of `update` are the same write as its dict
    literal form, and a rule that read only the literal would leave both
    beside it.
    """
    source = ALIAS_WRITES[label]
    store, base = _bound_store(tmp_path, "%s.json" % label)

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] == channel.INELIGIBLE_FROZEN_WRITE, (
        "the %s form reached the grant and was admitted: %r"
        % (label, verdict))


def test_an_alias_the_guard_cannot_follow_is_not_claimed_to_be_covered():
    """The limit, asserted rather than left to the docstring alone.

    `v = dict(view)` and `helper(view)` bind a name to something derived
    from the view, and the guard reads names rather than what they resolve
    to. Following them is the taint analysis the computed-key case already
    declines. The view the child receives carries none of the six frozen
    fields, so such a write lands on nothing frozen, and that is the reason
    this limit is stated rather than closed.
    """
    derived = ('def STEP(view, state):\n'
               '    copy = dict(view)\n'
               '    copy.clear()\n')
    through_a_call = ('def STEP(view, state):\n'
                      '    helper(view)\n')

    assert not channel._attempts_frozen_write(derived), (
        "a name bound from a call is not followed; if this now refuses,"
        " the guard grew a rule this case was written to pin down: %r"
        % (derived,))
    assert not channel._attempts_frozen_write(through_a_call)

    doc = inspect.getdoc(channel._frozen_write_reason) or ""
    assert "taint" in doc.lower() and "view" in doc.lower(), (
        "the guard does not record that it reads names rather than what"
        " they resolve to: %r" % (doc,))


# --- 5. the docstring tells the truth ------------------------------------

def _docstrings() -> list:
    """Every docstring in the module, so a promise cannot hide in one."""
    import ast
    import inspect
    import textwrap

    text = inspect.getsource(channel)
    tree = ast.parse(textwrap.dedent(text))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                found.append((getattr(node, "name", "<module>"), doc))
    return found


def test_no_surviving_comment_promises_a_runtime_backstop_that_cannot_fire():
    """The promise is what let the hole survive every gate.

    `_frozen_key` said the runtime comparison of frozen state either side of
    admission was the layer that catches a computed-key write. It cannot fire:
    the revision runs out of process against a JSON view holding none of the
    six fields. This asserts no docstring defers to it.

    Naming the deleted promise is allowed and is not the same as keeping it,
    because the docstring that does so says in the same breath that the
    comparison cannot fire. What is banned here is a deferral, so the check
    is on the sentence around the mention rather than on the mention.
    """
    deferred = (
        "is the layer that catches",
        "the layer that catches a write",
        "instead of by trust",
        "the runtime comparison is the backstop",
    )
    survivors = [name for name, doc in _docstrings()
                 for phrase in deferred if phrase in doc]

    assert not survivors, (
        "a docstring still defers to the runtime comparison, which cannot"
        " observe a revision: %r" % (survivors,))


def test_the_module_still_says_why_the_deferral_was_deleted():
    """Deleting the promise without saying why loses the reason.

    The next reader to hit an unreadable key will want the deferral back,
    because a deferral reads as a design and this was one. The module has to
    keep the reason it went, which is that the comparison was checked against
    the real execution path and does not reach a child's bytes.
    """
    names = {name for name, doc in _docstrings()}
    guard = dict(_docstrings())["_frozen_write_reason"]

    assert "_frozen_write_reason" in names
    assert "cannot fire" in guard, (
        "the guard no longer records that the comparison it used to defer to"
        " cannot fire, so the reason it was deleted is lost: %r" % (guard,))
    assert "disposable stores" in guard, (
        "the guard does not say the revision ran against disposable stores"
        " rather than the store compared, which is the measurement that"
        " shows the comparison is blind: %r" % (guard,))


def test_the_freeze_docstring_states_the_real_limit():
    """The replacement promise, asserted positively.

    A guard that refuses an unreadable key is making a real claim: it is not
    resolving the key and it is not deferring to a second layer. The
    docstring has to say exactly that, because that is now the whole coverage
    story.
    """
    import inspect

    doc = inspect.getdoc(channel._frozen_write_reason) or ""

    assert "refus" in doc.lower(), (
        "the replacement for the deleted promise does not say the unreadable"
        " case is refused: %r" % (doc,))
    assert "taint" in doc.lower(), (
        "the docstring does not say why the key is not resolved, so the"
        " limit reads as an omission rather than a decision: %r" % (doc,))
    assert "cannot fire" in doc or "cannot observe" in doc, (
        "the docstring names the runtime comparison without saying it"
        " cannot fire, which is the promise that has just been deleted"
        " making itself again in a new wording: %r" % (doc,))


def test_the_entry_docstring_does_not_claim_the_comparison_is_the_backstop():
    """`admit_revision_under_freeze` had the same promise in the same words.

    Its docstring said a write that slips past the static check "is still
    caught by the comparison rather than by trust". The comparison is kept,
    because a write to the store from inside admission is real, but it is
    described for what it is: a check that admission does not move frozen
    state, which cannot see a child's bytes.
    """
    import inspect

    doc = inspect.getdoc(channel.admit_revision_under_freeze) or ""

    assert "caught by the comparison rather than by trust" not in doc, (
        "the entry still claims the comparison is the backstop: %r" % (doc,))
    assert "out of" in doc and "cannot" in doc, (
        "the entry does not say the revision runs out of process, so the"
        " comparison reads as a second layer: %r" % (doc,))