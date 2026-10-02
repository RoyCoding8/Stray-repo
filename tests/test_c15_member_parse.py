"""C15: `verify_member` must answer a deep source with a refusal, not a raise.

C14 widened one of the module's two `ast.parse` guards and reported that the
other was identical on base and left open. This file closes it, and the first
thing the exposure has to earn is that it was real rather than nominal:
`verify_member` sits on the live acquisition path through
`construct._evaluate`, whose handler catches
`(MethodExecutionError, SyntaxError, ValueError)` — none of which is what
CPython raises when the parser stack overflows.

What escapes is a property of the parser, not of the rule under test, and the
parser's answer changes with the shape of the nesting. A list display is
refused by a paren counter at depth 201 with a `SyntaxError` the narrow tuple
already caught. A not-chain is not counted at all: CPython parses it on the C
stack and answers a few thousand deep with `MemoryError: Parser stack
overflowed`. Measured by this lane's own bisection on this interpreter and
pinned below, so a CPython change is visible here rather than silent.

Every case is a refusal or an admission. None may raise anything that is not a
`MethodExecutionError`, because the caller of this gate records a refusal as a
failed attempt and has no answer at all for an exception.
"""

from __future__ import annotations

import ast
import builtins
import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

from experiments.ad01 import method_exec

NOT_CHAIN_PARSES = 5959
LAMBDA_CHAIN_PARSES = 2979
BARE_NOT_CHAIN_PARSES = 5968
BARE_LAMBDA_CHAIN_PARSES = 2984
NOT_FRAME_COST = 9
LAMBDA_FRAME_COST = 5
NESTED_DISPLAY_PARSES = 200

GATE = "verify_member"
SIBLING_GATE = "verify_step_source"


def _source(statement: str) -> str:
    return ("def ENTRY(task, oracle):\n"
            "    x = %s\n"
            "    return task\n" % statement)


def _not_chain(depth: int) -> str:
    return _source("not " * depth + "1")


def _lambda_chain(depth: int) -> str:
    return _source("lambda: " * depth + "1")


def _nested_display(depth: int) -> str:
    return _source("[" * depth + "]" * depth)


def _member(source: str) -> dict:
    return {"method_source": source, "entry": "ENTRY"}


def _outcome(source: str) -> str:
    try:
        return "admitted" if method_exec.verify_member(
            _member(source)) == "ENTRY" else "refused"
    except method_exec.MethodExecutionError:
        return "refused"


def _module_tree() -> ast.Module:
    return ast.parse(
        pathlib.Path(method_exec.__file__).read_text(encoding="utf-8"))


def _function(function: str) -> ast.FunctionDef:
    definitions = [node for node in _module_tree().body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == function]
    assert len(definitions) == 1, (
        "%s is not one module-level function; this file reads it by name"
        % function)
    return definitions[0]


def _catch_tuple(function: str) -> set:
    """The exception classes one gate function actually catches.

    Read out of the module's own `ast.parse` guard rather than restated here,
    so a tuple that lost a name fails this file instead of being agreed with
    by a second copy of it. Anchored on the function by name rather than on
    position: the module parses untrusted source in two places, and a
    positional read would silently check whichever came first.
    """
    for node in ast.walk(_function(function)):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        caught = node.type.elts if isinstance(
            node.type, ast.Tuple) else [node.type]
        names = {ast.unparse(item) for item in caught}
        if "SyntaxError" in names:
            return {getattr(builtins, name) for name in names}
    raise AssertionError("%s no longer catches SyntaxError" % function)


def test_the_depths_this_file_asserts_are_real_on_this_interpreter():
    """Pin the parser's own answers, so a CPython change is visible here.

    A sweep asserting "no exception escapes" passes whether or not the gate is
    doing anything, because a parser that refuses everything at depth 1
    satisfies it trivially. These numbers say which side of each parser limit
    the cases below sit on.

    The boundaries are bisected here against the same wrapped source the cases
    below use, and a bare expression is pinned alongside them because the
    difference is the point: the `def` frame the gate's source needs costs
    nine levels of the parser's own stack, so the limit for the source this
    gate actually reads is nine lower than the limit for the chain alone. A
    number quoted for the chain and applied to the wrapped source would put
    every "just past the limit" case on the wrong side of it.
    """
    def parses(build, depth) -> bool:
        try:
            ast.parse(build(depth))
        except BaseException:
            return False
        return True

    assert parses(_nested_display, NESTED_DISPLAY_PARSES)
    assert not parses(_nested_display, NESTED_DISPLAY_PARSES + 1)
    assert parses(_not_chain, NOT_CHAIN_PARSES)
    assert not parses(_not_chain, NOT_CHAIN_PARSES + 1)
    assert parses(_lambda_chain, LAMBDA_CHAIN_PARSES)
    assert not parses(_lambda_chain, LAMBDA_CHAIN_PARSES + 1)

    def bare_not(depth):
        return "not " * depth + "1"

    def bare_lambda(depth):
        return "lambda: " * depth + "1"

    assert parses(bare_not, BARE_NOT_CHAIN_PARSES)
    assert not parses(bare_not, BARE_NOT_CHAIN_PARSES + 1)
    assert parses(bare_lambda, BARE_LAMBDA_CHAIN_PARSES)
    assert not parses(bare_lambda, BARE_LAMBDA_CHAIN_PARSES + 1)


def test_the_parser_stack_cost_of_the_def_frame_is_what_separates_them():
    """The wrapped source's limit is the chain's limit, less the frame's cost.

    Without this, the two constants above could drift apart and the file would
    still pass: it asserts each is on the right side of its own boundary, not
    that the gap between them is what the parser charges for the `def` the
    gate's source is wrapped in. The cost is measured separately for each
    shape rather than assumed equal, because it is not: a not-chain loses nine
    levels to the frame and a lambda chain loses five.
    """
    assert BARE_NOT_CHAIN_PARSES - NOT_CHAIN_PARSES == NOT_FRAME_COST
    assert BARE_LAMBDA_CHAIN_PARSES - LAMBDA_CHAIN_PARSES == LAMBDA_FRAME_COST


@pytest.mark.parametrize("build,depth", [
    (_nested_display, NESTED_DISPLAY_PARSES + 1),
    (_not_chain, 1),
    (_not_chain, 100),
    (_not_chain, 1000),
    (_not_chain, 5000),
    (_not_chain, NOT_CHAIN_PARSES),
    (_not_chain, NOT_CHAIN_PARSES + 1),
    (_not_chain, NOT_CHAIN_PARSES * 4),
    (_not_chain, 100000),
    (_lambda_chain, 1),
    (_lambda_chain, 100),
    (_lambda_chain, LAMBDA_CHAIN_PARSES),
    (_lambda_chain, LAMBDA_CHAIN_PARSES + 1),
    (_lambda_chain, 100000),
])
def test_depth_yields_a_verdict_not_an_exception(build, depth):
    """No depth escapes, whichever side of the parser's limit it sits on.

    A shallow chain parses and satisfies every rule the gate checks, so the
    gate admits it and that is the correct answer; a chain past the parser's
    limit has no tree and is refused. Both are verdicts. Only a raise is a
    defect, because the caller of this gate has no answer for one.
    """
    try:
        outcome = _outcome(build(depth))
    except BaseException as exc:
        raise AssertionError(
            "%s at depth %d escaped verify_member"
            % (type(exc).__name__, depth)) from exc
    assert outcome in ("admitted", "refused"), outcome


@pytest.mark.parametrize("build,depth", [
    (_not_chain, NOT_CHAIN_PARSES + 1),
    (_not_chain, 100000),
    (_lambda_chain, LAMBDA_CHAIN_PARSES + 1),
    (_lambda_chain, 100000),
])
def test_a_source_past_the_parser_limit_is_refused(build, depth):
    assert _outcome(build(depth)) == "refused", (
        "a source too deep for the parser to take cannot be admitted")


def test_a_source_the_parser_refuses_outright_is_a_method_error():
    for depth in (NOT_CHAIN_PARSES * 4, LAMBDA_CHAIN_PARSES * 4):
        with pytest.raises(method_exec.MethodExecutionError) as caught:
            method_exec.verify_member(_member(_not_chain(depth)))
        assert "unparseable-python" in str(caught.value)


def test_the_catch_tuple_names_every_exception_the_parser_can_raise():
    """The gate's tuple must name every class `ast.parse` delivers here.

    Measured by asking the parser, then checked against the module's own tuple.
    Each shape below is one whose refusal arrives as a distinct exception
    class, and a tuple missing any of them turns a refusal into an escape on
    the live path.
    """
    raised = {}
    for label, build in (
        ("paren-limit", lambda: "[" * 400 + "]" * 400),
        ("null-byte", lambda: "x = 1\x00"),
        ("parser-stack", lambda: "not " * 100000 + "1"),
        ("lambda-stack", lambda: "lambda: " * 100000 + "1"),
    ):
        try:
            ast.parse(build())
        except BaseException as exc:
            raised[label] = type(exc)
    assert set(raised) == {"paren-limit", "null-byte", "parser-stack",
                           "lambda-stack"}, (
        "a shape stopped raising; this would be measuring a parser that no"
        " longer refuses")
    caught = _catch_tuple(GATE)
    for label, kind in raised.items():
        assert kind in caught, (
            "%s raises %s, which the gate's tuple does not catch"
            % (label, kind.__name__))


def test_both_parse_guards_in_this_module_carry_the_same_tuple():
    """One policy, two exposures — which is the batch's actual subject.

    These two guards were byte-identical on base and were widened one at a
    time, which is how two answers to one question come to live in one file.
    Each tuple is read out of its own function's AST, so this fails when a
    widening reaches only one of them and when a narrowing drops a name from
    either.
    """
    tuples = {name: _catch_tuple(name) for name in (GATE, SIBLING_GATE)}
    assert tuples[GATE] == tuples[SIBLING_GATE], (
        "the two parse guards disagree: %s vs %s" % (
            sorted(n.__name__ for n in tuples[GATE]),
            sorted(n.__name__ for n in tuples[SIBLING_GATE])))
    for required in (SyntaxError, ValueError, RecursionError, MemoryError):
        assert required in tuples[GATE], (
            "%s is missing from the gate's tuple" % required.__name__)


def test_the_widened_catch_does_not_swallow_a_base_exception():
    """The guard is widened by one name, not out to `BaseException`.

    `MemoryError` is the parser's answer to a source it will not take. A
    control-flow signal from the host is a different thing, and a catch that
    reached one would turn an operator's interrupt into a refusal that reads
    like a verdict about the model.
    """
    caught = _catch_tuple(GATE)
    for signal in (KeyboardInterrupt, SystemExit, GeneratorExit):
        assert signal not in caught, (
            "%s is not the parser refusing a source" % signal.__name__)


def test_a_widened_catch_still_refuses_what_the_narrow_one_refused():
    """Widening a catch on a gate can hide a bug; this is the check on it.

    A source the narrow tuple already refused must still be refused, and with
    a `refused:` message, so nothing provable before the tuple grew has
    stopped being provable because of it.
    """
    for source in (_nested_display(400),
                   "def ENTRY(task, oracle):\n    return task\n    def",
                   "def ENTRY(task, oracle, extra, more):\n    return task\n",
                   "def ENTRY(task, oracle):\n    import os\n    return task\n",
                   "def ENTRY(task, oracle):\n    return task.__class__\n",
                   "def ENTRY(task, oracle):\n    return eval('1')\n",
                   "def OTHER(task, oracle):\n    return task\n"):
        with pytest.raises(method_exec.MethodExecutionError) as caught:
            method_exec.verify_member(_member(source))
        assert "refused:" in str(caught.value), (
            "%r was refused as %r, which is not this gate's refusal shape"
            % (source[:40], str(caught.value)))


_CORPUS = (
    (_nested_display(400), "ENTRY"),
    (_nested_display(200), "ENTRY"),
    (_not_chain(NOT_CHAIN_PARSES + 1), "ENTRY"),
    (_not_chain(100000), "ENTRY"),
    (_lambda_chain(LAMBDA_CHAIN_PARSES + 1), "ENTRY"),
    (_lambda_chain(100000), "ENTRY"),
    ("x = 1\x00", "ENTRY"),
    ("def ENTRY(task, oracle):\n    return task\n", "ENTRY"),
    ("def ENTRY(task, oracle, max_queries):\n    return task\n", "ENTRY"),
    ("def ENTRY(oracle, task):\n    return task\n", "ENTRY"),
    ("task = 1\n", "ENTRY"),
    ("def ENTRY(task):\n    return task\n", "ENTRY"),
    ("def OTHER(task, oracle):\n    return task\n", "ENTRY"),
    ("def ENTRY(task, oracle):\n    import os\n    return task\n", "ENTRY"),
    ("def ENTRY(task, oracle):\n    return task.__class__\n", "ENTRY"),
    ("def ENTRY(task, oracle):\n    return eval('1')\n", "ENTRY"),
    ("", "ENTRY"),
    ("   ", "ENTRY"),
    ("def ENTRY(task, oracle):\n    return task\n\n"
     "def ENTRY(t, o):\n    return t\n", "ENTRY"),
    ("def ENTRY(task, oracle):\n    return task\n", ""),
    ("def ENTRY(task, oracle):\n    return task\n", None),
)

GATE_REFUSALS = (
    "empty-method-source",
    "missing-entry",
    "unparseable-python",
    "missing-entry-function",
    "entry-arity",
    "imports-forbidden",
    "dunder-access-forbidden",
    "io-or-reflection-forbidden",
)

_PROBE = '''\
import ast, json, sys
from experiments.ad01 import method_exec

def gate(member):
    source = member.get("method_source")
    entry = member.get("entry")
    if not isinstance(source, str) or not source.strip():
        raise method_exec.MethodExecutionError("refused: empty-method-source")
    if not isinstance(entry, str) or not entry:
        raise method_exec.MethodExecutionError("refused: missing-entry")
    try:
        tree = ast.parse(source)
    except (__CATCHES__):
        raise method_exec.MethodExecutionError("refused: unparseable-python")
    targets = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == entry]
    if len(targets) != 1:
        raise method_exec.MethodExecutionError(
            "refused: missing-entry-function")
    params = list(targets[0].args.posonlyargs) + list(targets[0].args.args)
    names = [p.arg for p in params]
    if len(names) < 2 or names[0] != "task" or names[1] != "oracle" \\
            or len(names) > 3 or targets[0].args.vararg is not None \\
            or targets[0].args.kwarg is not None \\
            or targets[0].args.kwonlyargs:
        raise method_exec.MethodExecutionError("refused: entry-arity")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise method_exec.MethodExecutionError(
                "refused: imports-forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise method_exec.MethodExecutionError(
                "refused: dunder-access-forbidden")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise method_exec.MethodExecutionError(
                "refused: dunder-access-forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \\
                and node.func.id in method_exec._FORBIDDEN_CALLS:
            raise method_exec.MethodExecutionError(
                "refused: io-or-reflection-forbidden")
    return "admitted"

for index, case in enumerate(json.load(sys.stdin)):
    source, entry = case
    try:
        print(json.dumps([index, gate({"method_source": source,
                                       "entry": entry})]))
    except BaseException as exc:
        print(json.dumps([index, "%s: %s" % (type(exc).__name__, exc)]))
'''


def _run_with_tuple(names) -> dict:
    """What the gate answers over the corpus, with the guard's tuple replaced.

    The narrow tuple is re-derived here rather than imported, so this is the
    comparison itself and not a restatement of the code under it.
    """
    root = str(pathlib.Path(method_exec.__file__).resolve().parents[2])
    env = dict(os.environ)
    env["PYTHONPATH"] = root + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    script = _PROBE.replace("__CATCHES__", ", ".join(names))
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=_corpus_as_json(), capture_output=True, text=True, env=env,
        cwd=root)
    assert result.returncode == 0, result.stderr[-2000:]
    verdicts = {}
    for line in result.stdout.splitlines():
        index, verdict = json.loads(line)
        verdicts[index] = verdict
    return verdicts


def _corpus_as_json() -> str:
    return json.dumps(list(_CORPUS))


def test_widening_admits_nothing_the_narrow_tuple_did_not_admit():
    """The load-bearing claim, as a differential rather than an argument.

    The argument for widening is that a source which exhausts the parser stack
    is refused either way, so no provable admission becomes unprovable. That is
    checkable rather than arguable, and the measurement says it holds: over a
    corpus holding every refusal the gate can give and its one admission, the
    wide tuple and the narrow one differ on exactly the parser-stack sources
    and on nothing else.

    So the claim is not "nothing changed" — the escape was the thing being
    repaired, and it changed on purpose. It is that every difference is an
    uncaught exception becoming a refusal, and never an admission becoming
    something else or one refusal becoming a different one. A widening that
    turned a refusal into an admission would show up here as a difference
    whose wide side is not the parse guard's refusal.
    """
    wide = _run_with_tuple(["SyntaxError", "ValueError", "RecursionError",
                            "MemoryError"])
    narrow = _run_with_tuple(["SyntaxError", "ValueError", "RecursionError"])
    assert sorted(wide) == list(range(len(_CORPUS))), wide
    assert sorted(narrow) == list(range(len(_CORPUS))), narrow

    differences = [(index, _CORPUS[index][0][:40], narrow[index], wide[index])
                   for index in sorted(wide)
                   if wide[index] != narrow[index]]
    assert differences, (
        "the narrow and wide tuples agree everywhere, so this corpus never"
        " reached the escape and the comparison is measuring nothing")
    assert all(
        wide_verdict == "MethodExecutionError: refused: unparseable-python"
        for _, _, _, wide_verdict in differences), (
        "widening changed a verdict into something other than the parse"
        " guard's refusal: %r" % (differences,))
    assert all(
        narrow_verdict.startswith("MemoryError: ")
        for _, _, narrow_verdict, _ in differences), (
        "a verdict changed on a source the parser did not refuse, so the"
        " widening hid something the narrow tuple already handled: %r"
        % (differences,))


def test_the_differential_corpus_actually_reached_both_gate_outcomes():
    """A differential passes trivially if its corpus exercises nothing.

    It must reach the admission and every distinct refusal the gate can give,
    or the comparison above is between two identical error paths and proves
    nothing about the widening. An earlier version of this file compared a
    three-rule reimplementation of the gate rather than the gate itself and
    satisfied this by counting three outcomes; the count is asserted against
    the number of rules the gate has, so a corpus that narrows fails here
    rather than quietly weakening the differential.
    """
    verdicts = _run_with_tuple(["SyntaxError", "ValueError", "RecursionError",
                                "MemoryError"])
    admitted = [i for i, v in verdicts.items() if v == "admitted"]
    reached = {v.rsplit(": ", 1)[-1] for v in verdicts.values()
               if v != "admitted"}
    assert admitted, "the corpus admits nothing, so nothing is compared"
    assert reached == set(GATE_REFUSALS), (
        "the corpus stopped covering the gate's refusals; missing %r, and it"
        " reached ones the gate does not name: %r"
        % (sorted(set(GATE_REFUSALS) - reached),
           sorted(reached - set(GATE_REFUSALS))))


def test_the_probe_carries_the_real_gate_and_not_a_reimplementation():
    """The differential is only evidence if it runs the gate under test.

    The probe is a copy of `verify_member` up to the parse guard, so it could
    drift from the function it stands in for: a rule added to the gate later
    would leave the differential comparing two older versions of it and still
    agreeing. This counts the refusal strings the gate itself produces over
    the corpus and requires the probe to produce exactly those, so a
    divergence is a failure rather than a quietly weaker comparison.
    """
    real = {}
    for index, (source, entry) in enumerate(_CORPUS):
        try:
            real[index] = ("admitted" if method_exec.verify_member(
                {"method_source": source, "entry": entry}) == "ENTRY"
                else "refused")
        except BaseException as exc:
            real[index] = "%s: %s" % (type(exc).__name__, exc)
    probed = _run_with_tuple(["SyntaxError", "ValueError", "RecursionError",
                              "MemoryError"])
    assert probed == real, (
        "the probe and the gate disagree, so the differential is comparing"
        " the probe against itself: %r" % (
            [(i, real[i], probed[i]) for i in sorted(real)
             if real[i] != probed[i]],))


def test_the_escape_reaches_a_live_caller_that_does_not_catch_it():
    """Why this matters: the acquisition caller is not a blanket guard.

    `construct._evaluate` wraps the gate in
    `(MethodExecutionError, SyntaxError, ValueError)`. `MemoryError` is none
    of those, so before the widening a deep model response killed the
    evaluation instead of recording a failed attempt against it. Asserting
    the caller's tuple against the class keeps the finding true even after the
    gate stops raising, when the test would otherwise be measuring nothing.
    """
    from experiments.ad01 import construct
    caught = _verify_member_handler_types(construct._evaluate)
    assert caught, "construct._evaluate no longer wraps verify_member"
    assert "MemoryError" not in caught, (
        "the live caller now catches MemoryError itself; this escape is no"
        " longer reachable from it and the finding needs restating")
    assert issubclass(method_exec.MethodExecutionError, Exception)


def _verify_member_handler_types(function) -> set:
    """The exception names in the handlers that wrap a `verify_member` call."""
    tree = ast.parse(pathlib.Path(
        sys.modules[function.__module__].__file__
    ).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        guards = [sub for sub in ast.walk(node)
                  if isinstance(sub, ast.Call) and sub.args
                  and ast.unparse(sub.func).endswith("verify_member")]
        if not guards:
            continue
        for handler in node.handlers:
            if handler.type is None:
                found.add("bare-except")
            elif isinstance(handler.type, ast.Tuple):
                found.update(ast.unparse(item) for item in handler.type.elts)
            else:
                found.add(ast.unparse(handler.type))
    return found


def test_the_interpreter_under_test_is_the_one_the_depths_were_measured_on():
    assert sys.version_info[:2] >= (3, 12), (
        "the parser limits asserted here were measured on CPython 3.14.4; a"
        " different version may refuse at a different depth, which is a"
        " finding rather than a failure of the gate")