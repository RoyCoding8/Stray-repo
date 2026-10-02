"""The contract's rendered signature must describe the call that runs.

`child_contract` shipped a hand-written `signature` string per operation
and handed it to the model through `packet.public_operations`. For
`reduce_software` it read `reduce_software(task, oracle, method,
max_queries)`, presenting `method` as the third positional argument. The
wrapper the child actually binds takes `method` keyword-only, because
`_wrapper_for` generates it that way from `inspect.signature`. A member
that obeyed the contract wrote `reduce_graph(task, oracle, "ddmin",
max_queries)`, passed `verify_member` (which checks only the entry's own
arity, never the calls inside it), and died in the child with
`TypeError: reduce_graph() takes 2 positional arguments but 3 positional
arguments`. The same call with `method="ddmin"` ran.

These tests read the rendered text and then make the call it documents,
so a renderer that dropped the keyword-only marker fails here rather than
in a run that costs real dispatches.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, worlds

DEV_SW = "ad01-w0-dev-sw-00"
DEV_GR = "ad01-w0-dev-gr-00"

# A task the real reducers accept, and an oracle that answers a verdict
# the way the child's proxy does. The point of the test is the shape of
# the call, not the reduction, so nothing here needs a live provider.
TASK = worlds.load_task(worlds.FROZEN_DIR, DEV_SW)
GRAPH_TASK = worlds.load_task(worlds.FROZEN_DIR, DEV_GR)
FAMILY_TASK = {"reduce_software": TASK, "reduce_graph": GRAPH_TASK}


class _Oracle:
    def query(self, candidate):
        return {"verdict": "preserved"}


def _bound_wrappers() -> dict:
    """The wrappers the child binds, built from the real generator."""
    from experiments.representation import reducers

    namespace = {"reducers": reducers}
    exec(compile(method_exec._child_wrapper_source(),  # noqa: S102
                 "<child-wrappers>", "exec"), namespace)
    return namespace


def _call_form(signature: str) -> str:
    """The `name(...)` call out of a rendered signature.

    Found by balancing parentheses rather than by splitting on the note
    phrases, so a renderer that rewords its notes does not silently turn
    this into a parser of prose.
    """
    start = signature.index("(")
    depth = 0
    for index in range(start, len(signature)):
        if signature[index] == "(":
            depth += 1
        elif signature[index] == ")":
            depth -= 1
            if depth == 0:
                return signature[:index + 1]
    raise AssertionError("no balanced call form in %r" % signature)


@pytest.mark.parametrize("name", ["reduce_software", "reduce_graph"])
def test_a_documented_positional_strategy_is_refused_by_the_real_callee(name):
    """The regression, run as a call rather than read as a string.

    `method` is rendered after the `*`, so a member reading the contract
    writes `method="ddmin"`. The proof that the old contract was wrong is
    that the positional form it documented raises, and the proof the new
    one is right is that the keyword form the contract now shows runs.
    """
    signature = method_exec.child_contract()["callables"][name]["signature"]
    assert "method" in signature, (
        "%s never names the parameter the model has to pass, so the menu"
        " says to choose a strategy and the call form does not show how: %r"
        % (name, signature))
    task = FAMILY_TASK[name]
    wrappers = _bound_wrappers()
    wrapper = wrappers[name]

    with pytest.raises(TypeError) as refusal:
        wrapper(task, _Oracle(), "ddmin", max_queries=4)
    assert "positional argument" in str(refusal.value), refusal.value

    result = wrapper(task, _Oracle(), method="ddmin", max_queries=4)
    assert result["candidate"]["family"] == FAMILY_TASK[name]["family"]
    assert "kept" in result, sorted(result)


@pytest.mark.parametrize("name", ["reduce_software", "reduce_graph"])
def test_a_keyword_only_parameter_is_never_rendered_positionally(name):
    """Every parameter past the `*` is one the call refuses positionally.

    Read from the wrapper rather than from a list of the two families, so
    this covers whatever the table offers and fails if a future entry
    documents a keyword-only parameter as positional.
    """
    signature = method_exec.child_contract()["callables"][name]["signature"]
    call_form = _call_form(signature)
    assert "*, " in call_form, (
        "%s renders no keyword-only separator, so a model reads its"
        " keyword-only parameters as positional: %r" % (name, signature))
    inner = call_form[call_form.index("(") + 1:call_form.rindex(")")]
    pieces = [piece.strip() for piece in inner.split(",") if piece.strip()]
    head = [piece.split("=")[0].strip() for piece in pieces[:pieces.index("*")]]
    keyword_only = {value.name for value
                    in inspect.signature(_bound_wrappers()[name])
                    .parameters.values()
                    if value.kind is inspect.Parameter.KEYWORD_ONLY}
    assert not keyword_only.intersection(head), (
        "%s renders %s before the separator but the wrapper refuses it"
        " positionally" % (name, sorted(keyword_only.intersection(head))))


@pytest.mark.parametrize("name", ["reduce_software", "reduce_graph"])
def test_a_genuinely_positional_parameter_still_renders_positionally(name):
    """A parameter the wrapper takes positionally must not read otherwise.

    The separator cannot be the whole answer. If `task` and `oracle` were
    pushed behind the `*` as well, the rendered text would be safe and
    wrong, and the child adapter binds both positionally.
    """
    signature = method_exec.child_contract()["callables"][name]["signature"]
    call_form = _call_form(signature)
    assert call_form.startswith("%s(task, oracle," % name), call_form
    wrapper = _bound_wrappers()[name]
    result = wrapper(FAMILY_TASK[name], _Oracle(), method="ddmin",
                     max_queries=4)
    assert result["candidate"], (
        "task and oracle are rendered positional and the wrapper binds them"
        " that way, so the rendered call has to run")


def test_every_rendered_signature_agrees_with_its_real_binding():
    """The table and the wrappers, compared entry by entry.

    Rendered text is prose, so it is compared structurally: the names the
    text places before and after the `*` are checked against the kinds
    `inspect.signature` reports for the wrapper the child actually binds.
    A disagreement here is a contract that documents a call nothing
    implements, which is the defect this renderer exists to remove.
    """
    contract = method_exec.child_contract()
    wrappers = _bound_wrappers()
    checked = []
    for name, spec in sorted(contract["callables"].items()):
        if spec.get("binding") is None:
            assert spec["signature"] == "oracle.query(candidate)", name
            continue
        assert name in wrappers, (
            "%s has a binding but the child binds no wrapper for it" % name)
        call_form = _call_form(spec["signature"])
        assert call_form.startswith("%s(" % name), (
            "%s documents a call to something other than itself: %r"
            % (name, spec["signature"]))
        signature = inspect.signature(wrappers[name])
        keyword_only = {value.name for value in signature.parameters.values()
                        if value.kind is inspect.Parameter.KEYWORD_ONLY}
        has_var_keyword = any(
            value.kind is inspect.Parameter.VAR_KEYWORD
            for value in signature.parameters.values())
        inner = call_form[call_form.index("(") + 1:call_form.rindex(")")]
        pieces = [piece.strip() for piece in inner.split(",") if piece.strip()]
        assert pieces[0] == "*" or "*, " in inner, (
            "%s documents no keyword-only separator: %r"
            % (name, spec["signature"]))
        head = pieces[:pieces.index("*")] if "*" in pieces else pieces
        tail = pieces[pieces.index("*") + 1:] if "*" in pieces else []
        for piece in head:
            parameter = piece.split("=")[0].strip()
            assert parameter not in keyword_only, (
                "%s renders %s before the separator but the wrapper binds it"
                " keyword-only" % (name, parameter))
        for piece in tail:
            parameter = piece.split("=")[0].strip()
            if parameter.startswith("**"):
                assert has_var_keyword, (
                    "%s documents %s but its wrapper takes no **kwargs"
                    % (name, parameter))
                continue
            assert parameter in signature.parameters, (
                "%s documents %s, which its wrapper does not declare: %s"
                % (name, parameter, signature))
            assert parameter in keyword_only, (
                "%s renders %s after the separator but the wrapper binds it"
                " positionally" % (name, parameter))
        declared = [value.name if value.kind is not
                    inspect.Parameter.VAR_KEYWORD else "**" + value.name
                    for value in signature.parameters.values()]
        # A guarded strategy is rendered as a bare name rather than
        # `name=None`, because the adapter has no value behind the `None`.
        # It is still documented in the call form, so the positional and
        # keyword-only checks above already cover it; what it must not do
        # is look like a default.
        documented = [piece.split("=")[0].strip() for piece in head + tail]
        guarded = [value.name for value in signature.parameters.values()
                   if value.name == "method" and value.default is None]
        for parameter in guarded:
            assert "%s=" % parameter not in call_form, (
                "%s renders %s= but the adapter defaults it to None only to"
                " check the name, so a default here would be a lie and would"
                " read as a menu answering itself: %r"
                % (name, parameter, spec["signature"]))
        assert documented == declared, (
            "%s documents %s but its wrapper declares %s"
            % (name, documented, declared))
        checked.append(name)
    assert checked, "no bound entry was checked"
@pytest.mark.parametrize("name", ["reduce_software", "reduce_graph"])
def test_the_open_menu_survives_rendering(name):
    """The choices text is load-bearing and the renderer must keep it.

    It is what stops the wrapper supplying a default, and it is the only
    thing telling a model which two strategies exist. Rendering the
    parameter list must not drop it, and must not turn it into a default:
    the menu gate used to read the rendered text. It does not: since `ff22d77` it reads the wrapper's own signature cross-checked against the callee binding, so this is a documentation contract on the renderer, not a second gate. See tests/test_ad01_menu_binding_gate.py for the gate.
    """
    signature = method_exec.child_contract()["callables"][name]["signature"]
    assert "one of \"ddmin\" or \"greedy\"; you must name one" in signature, \
        signature
    assert not re.search(r"\bmethod\s*=\s*[^,\n)]+", signature), (
        "%s now documents a default for the choice the menu asks the model"
        " to make: %r" % (name, signature))


def test_a_wrapper_that_guards_its_strategy_says_it_is_optional():
    """The two adapted primitives guard `method`; they do not default it.

    The adapter's `method` only checks that a name matches the strategy
    the entry is already named for: omitting it runs that strategy, and
    passing the other one raises. So `method=None` would be a lie about
    the call, and it would also read to the two gates that watch for a
    defaulted strategy as a menu answering itself. The honest rendering
    names the parameter and says what happens if it is omitted.
    """
    contract = method_exec.child_contract()
    wrappers = _bound_wrappers()
    for name in method_exec._STRATEGY_METHODS.values():
        signature = contract["callables"][name]["signature"]
        assert "method=None" not in signature, (
            "%s does not default its strategy, so rendering one both lies"
            " about the call and trips the menu-openness gate: %r"
            % (name, signature))
        assert "you must name one" not in signature, (
            "%s runs the strategy it is named for when `method` is omitted,"
            " so claiming a choice here would be false: %r"
            % (name, signature))
        assert "has no value of its own" in signature, (
            "%s takes a `method` the rendered call does not describe: %r"
            % (name, signature))
        assert "family" in signature, (
            "%s is adapted and needs a family the rendered call omits: %r"
            % (name, signature))
        result = wrappers[name](TASK, _Oracle(), family="software",
                                max_queries=4)
        assert result["candidate"], (
            "%s is rendered as callable and is not" % name)
        with pytest.raises(ValueError):
            wrappers[name](TASK, _Oracle(), family="software",
                           method="greedy" if name == "ddmin_reduce"
                           else "ddmin", max_queries=4)


def test_the_menu_takes_no_default_answer():
    """No entry may document a default for the choice the model must make.

    Read structurally rather than by pattern: a `method=` in the rendered
    text is what the menu gate used to look for. That gate is live in four
    entry points. `menu_answers_nothing` is that check, run here so a
    renderer that starts supplying a strategy is caught by the test that
    owns the contract rather than by a study refusing at run time.
    """
    from experiments.ad01 import control_distinctness

    verdict = control_distinctness.menu_answers_nothing()
    assert verdict["open"], verdict.get("refusal")
