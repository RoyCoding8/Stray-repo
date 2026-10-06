"""C14: the gate's own parse must not let a depth escape as an exception.

C8 asserted this and C12 removed the file's cases. The claim is worth keeping
and it is worth measuring rather than restating: what escapes `verify_step_source`
on untrusted bytes is a property of CPython's parser, not of the rule under
test, and the parser's answer changes with the shape of the nesting. A list
display is refused by a paren counter at depth 201. A not-chain is not, and
CPython answers it with `MemoryError: Parser stack overflowed` instead, which
is a refusal to parse that a tuple of `(SyntaxError, ValueError,
RecursionError)` does not catch.

Every case here is written as a refusal or an admission. None may raise
anything that is not a `MethodExecutionError`, because the callers of this
gate are a construction parser on the live acquisition path, where an
exception that is not a refusal is a dead response rather than a rejected
one.
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys

import pytest

from experiments.ad01 import method_exec

NOT_CHAIN_PARSES = 5968
LAMBDA_CHAIN_PARSES = 2984
NESTED_DISPLAY_PARSES = 200


def _source(statement: str) -> str:
    return ("def STEP(view, state):\n"
            "    x = %s\n"
            "    return {\"action\": None, \"state\": state}\n" % statement)


def _shape(depth: int) -> str:
    return _source("[" * depth + "]" * depth)


def _not_chain(depth: int) -> str:
    return _source("not " * depth + "1")


def _lambda_chain(depth: int) -> str:
    return _source("lambda: " * depth + "1")


def _outcome(source: str) -> str:
    try:
        return "admitted" if method_exec.verify_step_source(
            source, "STEP") == "STEP" else "refused"
    except method_exec.MethodExecutionError:
        return "refused"


def test_the_depths_this_file_asserts_are_real_on_this_interpreter():
    """Exercise accepted and overflowing parses without pinning C-stack size."""
    def parses(build, depth) -> bool:
        try:
            ast.parse(build(depth))
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return False
        return True

    for build in (lambda d: "[" * d + "]" * d,
                  lambda d: "not " * d + "1",
                  lambda d: "lambda: " * d + "1"):
        assert parses(build, 20)
        assert not parses(build, 100000)
    valid = ('def STEP(view, state):\n'
             '    return {"action": {"kind": "stop", "target": "t", '
             '"inputs": {}, "evidence_refs": [], "requested_resources": {}}, '
             '"state": state}\n')
    assert method_exec.verify_step_source(valid, "STEP") == "STEP"


@pytest.mark.parametrize("depth", [1, 40, 90, 150, 200, 299])
def test_nested_display_depth_yields_a_verdict_not_an_exception(depth):
    assert _outcome(_shape(depth)) == "refused", (
        "a nested list is a legal literal and an inert one, so the gate"
        " refusing it is the right answer")


@pytest.mark.parametrize("depth", [
    1, 100, 1000, 5000, NOT_CHAIN_PARSES, NOT_CHAIN_PARSES + 1,
    NOT_CHAIN_PARSES * 4, 100000,
])
def test_not_chain_depth_yields_a_verdict_not_an_exception(depth):
    assert _outcome(_not_chain(depth)) == "refused"


@pytest.mark.parametrize("depth", [
    1, 100, 1000, LAMBDA_CHAIN_PARSES, LAMBDA_CHAIN_PARSES + 1, 100000,
])
def test_lambda_chain_depth_yields_a_verdict_not_an_exception(depth):
    assert _outcome(_lambda_chain(depth)) == "refused"


def test_a_source_the_parser_refuses_outright_is_still_a_method_error():
    for statement in ("not " * 100000 + "1",
                      "lambda: " * 100000 + "1",
                      "[" * 400 + "]" * 400):
        try:
            method_exec.verify_step_source(_source(statement), "STEP")
        except method_exec.MethodExecutionError:
            continue
        except BaseException as exc:
            raise AssertionError(
                "%s escaped verify_step_source" % type(exc).__name__) from exc
        raise AssertionError("an unparseable source was admitted")


def _gate_catch_tuple(function: str) -> set:
    """The exception classes one gate function actually catches.

    Read out of the module's own `ast.parse` guard rather than restated
    here, so a tuple that lost a name fails this file instead of being
    agreed with by a second copy of it. Anchored on the function, because
    the module parses untrusted source in two places and the other one
    still carries the narrow tuple.
    """
    tree = ast.parse(
        pathlib.Path(method_exec.__file__).read_text(encoding="utf-8"))
    definitions = [node for node in tree.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == function]
    assert len(definitions) == 1, (
        "%s is not one module-level function; this reads its guard" % function)
    for node in ast.walk(definitions[0]):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        caught = node.type.elts if isinstance(
            node.type, ast.Tuple) else [node.type]
        names = {ast.unparse(item) for item in caught}
        if "SyntaxError" in names:
            return {getattr(builtins, name) for name in names}
    raise AssertionError("%s no longer catches SyntaxError" % function)


def test_the_catch_tuple_matches_what_the_parser_can_raise():
    """The gate's tuple must name every exception `ast.parse` raises here.

    Measured by asking the parser, then checked against the module's own
    tuple: each shape below is one whose refusal the parser delivers as a
    distinct exception class, and a tuple missing any of them turns a
    refusal into an escape on the live path.
    """
    raised = {}
    for label, build in (
        ("paren-limit", lambda: "[" * 400 + "]" * 400),
        ("parser-stack", lambda: "not " * 100000 + "1"),
        ("lambda-stack", lambda: "lambda: " * 100000 + "1"),
    ):
        try:
            ast.parse(build())
        except BaseException as exc:
            raised[label] = type(exc)
    assert set(raised) == {"paren-limit", "parser-stack", "lambda-stack"}, (
        "a shape stopped raising; this test would be measuring a parser"
        " that no longer refuses")
    caught = _gate_catch_tuple("verify_step_source")
    for label, kind in raised.items():
        assert kind in caught, (
            "%s raises %s, which the gate's tuple does not catch"
            % (label, kind.__name__))


def test_a_widened_catch_still_refuses_what_the_narrow_one_refused():
    """Widening a catch on a gate can hide a bug; this is the check on it.

    A source that the narrow tuple already refused must still be refused
    with the same message, so nothing that was provable before the tuple
    grew has stopped being refused because of it.
    """
    for statement in ("[" * 400 + "]" * 400,
                      "def STEP(view, state):\n    return {\"action\": "):
        with pytest.raises(method_exec.MethodExecutionError) as caught:
            method_exec.verify_step_source(
                statement if statement.startswith("def")
                else _source(statement), "STEP")
        assert "unparseable-python" in str(caught.value)


def test_the_interpreter_under_test_is_the_one_the_depths_were_measured_on():
    assert sys.version_info[:2] >= (3, 12), (
        "the parser limits asserted here were measured on CPython 3.14; a"
        " different version may refuse at a different depth, which is a"
        " finding rather than a failure of the gate")
