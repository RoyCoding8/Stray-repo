"""The four rewriting rules, checked by executing programs rather than by
comparing two normal forms.

`_normal_form` decides whether a SWE repair is correct, so each rule it
applies has to be an identity over all inputs. Two ways of testing that
exist here and they are not the same test. Reducing both sides and
comparing the results shows the rule agrees with itself: a rule that
rewrites `x * 1` to `x` passes whether or not `x * 1` means `x`.
Executing both programs over a grid of inputs is the only thing that
distinguishes them, so every identity claim below is settled by running
the two programs and comparing what they returned, down to the type.

The normal form is still consulted, once per rule, for causation rather
than for truth: a pair is only a test of `_drop_unit_factor` if that one
named rule is what closes the gap between the two normal forms. Both
halves are asserted, so a rule cannot pass by being consistent with a
wrong rewrite.

Rules are addressed by name throughout. `_NORMALISERS` is a tuple and its
order is not part of any claim here, so a test that indexed it would be
testing the tuple. `_rule` raises rather than falling back, which keeps a
rename from silently reducing the number of rules under test.

The withdrawn comparison operators have their own test, and it is the
regression for two defects found by measurement. `_canonical_test` once
admitted all nine Python comparison operators while justifying `!=` alone,
and once accounted for a conditional's negation three times where it had
one. Both errors were credits to candidates computing something other than
the reference. Asserting only that the normal forms differ would pass again
if the rule were widened, so each operator is checked twice: the normal
forms must stay apart, and some point on the grid must show the two
programs actually computing different functions.

The unit guards are a different matter, and these tests pin what the code
does rather than what its docstring said. The guards compare a value against
1, so `1.0` and `True` are admitted, and neither rewrite is an identity. An
acceptance pass called that a documentation inaccuracy that was not a live
defect, because no reference source reaches either rule. Measuring it again
from the candidate's side found 44 of 44 candidates ending `* 1.0` scored
`repaired` and returned a float where the reference returned an int, which
is a wrong credit and not only a false sentence. Those tests ask the module
whether its guard fires, and are marked `xfail(strict=True)`: they fail
today, and a fix turns them into a failure, so the marker cannot outlive the
fix. Writing them to assert the documented behaviour instead would mean a test
that passes against a docstring known to be false, which is the check that
reads green while matching nothing.

`x * 1` is also not an identity for every `x`. A bool operand gives an int and
an operand with a custom `__mul__` observes the dropped call. That is stated
in one test rather than left to a reader to infer, and no guard narrowing
fixes it, since `1` is an int and the guard admits an int.
"""

from __future__ import annotations

import ast
import builtins

import pytest

from experiments.ad01 import s09_swe_tasks as tasks

RULE_NAMES = ("_drop_unit_factor", "_drop_unit_step",
              "_fill_missing_slice_bound", "_canonical_test")

# The operands these programs actually see: a digit string for `body` and
# a small non-negative integer for `n`. "An identity over all inputs" can
# only be tested on a domain, and this is the domain the catalogue draws
# from, so it is the domain the identity claims are checked on. `BODY_RANGE`
# draws 4 to 6 characters, so every length in that range is represented and a
# grid of only the short strings would be a claim about a domain the
# instrument never visits.
DIGITS = ("", "1", "12", "123", "213", "1213", "2231", "1111", "31213")
COUNTS = (0, 1, 2, 3, 4, 5, 6, 12)

ONE_ARG = [(value,) for value in DIGITS + COUNTS]
SLICE_ARG = [(value, bound) for value in DIGITS for bound in (0, 1, 2, 5, -3)]
RANGE_ARG = [(low, high) for low in (-3, -1, 0, 1, 4, 12)
             for high in (-2, 0, 1, 3, 7, 13)]

# Comparison grids. The float and bool members are not decoration:
# `1 == 1.0` and `1 == True`, so `is not` and `is` part company on them
# and a grid of plain integers cannot separate those two operators.
VALUES = (0, 1, 2, -1, 3, 0.0, 1.0, 2.0, -2.5, True, False,
          "", "a", "ab", [1], [1.0], [0, 1], (1,))
PAIR_ARG = [(left, right) for left in VALUES for right in VALUES]


def _rule(name: str):
    """The one rewriting rule with this name, by name and never by index."""
    for normalise in tasks._NORMALISERS:
        if normalise.__name__ == name:
            return normalise
    raise AssertionError(
        "no rewriting rule named %r among %s"
        % (name, [normalise.__name__ for normalise in tasks._NORMALISERS]))


def _rewrite_with(node, rules):
    """`_rewrite` with the rule set chosen by the caller.

    Production applies every rule until one fires. A test of one rule needs
    that one rule alone, or a test would pass because some other rule
    happened to close the gap. This is `_rewrite` unchanged apart from
    taking its rules as an argument.
    """
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            setattr(node, field,
                    [_rewrite_with(item, rules) if isinstance(item, ast.AST)
                     else item for item in value])
        elif isinstance(value, ast.AST):
            setattr(node, field, _rewrite_with(value, rules))
    for normalise in rules:
        replaced = normalise(node)
        if replaced is not None:
            return replaced
    return node


def _normal_form_with(source: str, names) -> str:
    rules = [_rule(name) for name in names]
    tree = ast.parse(source)
    return ast.dump(ast.fix_missing_locations(_rewrite_with(tree, rules)))


def _production_form(source: str) -> str:
    return ast.dump(ast.fix_missing_locations(
        tasks._rewrite(ast.parse(source))))


def test_the_local_traversal_agrees_with_the_production_one():
    """`_rewrite_with` is a copy, so it is pinned against the original.

    A per-rule test needs that one rule alone, and production applies all four
    until one fires. That makes the copy a second implementation of the
    traversal, and an unchecked second implementation is the kind this repo has
    been bitten by: truncating production `_rewrite` to the first rule in the
    tuple left every other test in this file green, because no reference source
    contains a `* 1` or a three-argument `range`, so nothing on the catalogue
    path exercises the traversal at all.

    Production takes no rule argument, so the two can only be compared where
    they are answering the same question: a source exactly one rule rewrites,
    where applying all four and applying that one coincide. Each rule gets its
    own nested source, since a single source containing all four would let
    first-match-wins hide a divergence.
    """
    per_rule = [
        ("_drop_unit_factor",
         "def probe(x, b):\n"
         "    for index in range(b):\n"
         "        step = index * 1\n"
         "    return step\n"),
        ("_drop_unit_step",
         "def probe(x, b):\n"
         "    for index in range(0, b, 1):\n"
         "        step = x * 2\n"
         "    return step\n"),
        ("_fill_missing_slice_bound",
         "def probe(x, b):\n"
         "    for index in range(b):\n"
         "        step = x[:b]\n"
         "    return step\n"),
        ("_canonical_test",
         "def probe(x, b):\n"
         "    for index in range(b):\n"
         "        step = 0 if not (x != b) else 1\n"
         "    return step\n"),
    ]

    for name, source in per_rule:
        assert _normal_form_with(source, ()) != _normal_form_with(source, (name,)), (
            "%s: this source is not a single-rule case, so the comparison "
            "below would prove nothing" % name)
        assert _normal_form_with(source, (name,)) == _production_form(source), (
            "%s: the local traversal and the production one disagree, so every "
            "per-rule assertion in this file is measuring the copy"
            % name)

    untouched = ("def probe(x, b):\n"
                 "    for index in range(b):\n"
                 "        step = index + b\n"
                 "    return step\n")

    assert _normal_form_with(untouched, ()) == _production_form(untouched)


def _probe(source: str):
    """A `Program` whose entry point is the one `source` defines."""
    return tasks.Program("probe", "counting", "probe", [], {})


def _observe(source: str, args: list) -> dict:
    """What a program returned on one call, keyed so `None` is a real answer.

    `1` and `1.0` and `True` all compare equal, so an equality-only observation
    cannot tell a program that returns an integer from one that returns the
    same value as a float. The type is carried alongside the value, which is
    how the unit-factor tests see the drift the rules introduce.
    """
    outcome = tasks.run_program(_probe(source), args, [source])
    if outcome["kind"] != "value":
        return {"error": outcome["name"]}
    value = outcome["value"]
    return {"value": repr(value), "type": type(value).__name__}


def _diverge(shaped: str, plain: str, args: list) -> list:
    """The arguments where the two programs returned different things."""
    return [row for row in args
            if _observe(shaped, row) != _observe(plain, row)]


def test_every_rule_is_reachable_by_name():
    """The names the tests below address rules by all still exist."""
    named = [normalise.__name__ for normalise in tasks._NORMALISERS]

    assert sorted(named) == sorted(RULE_NAMES)
    for name in RULE_NAMES:
        assert _rule(name).__name__ == name


def _identity_pairs():
    """`(rule, shaped, plain, args)` for every shape a rule must accept.

    The pair differs only in the spelling the rule rewrites, so the named
    rule is the only thing that can make their normal forms agree.
    """
    return [
        ("_drop_unit_factor", "def probe(x):\n    return x * 1\n",
         "def probe(x):\n    return x\n", ONE_ARG),
        ("_drop_unit_factor", "def probe(x):\n    return 1 * x\n",
         "def probe(x):\n    return x\n", ONE_ARG),
        ("_drop_unit_step",
         "def probe(a, b):\n    return list(range(a, b, 1))\n",
         "def probe(a, b):\n    return list(range(a, b))\n", RANGE_ARG),
        ("_fill_missing_slice_bound",
         "def probe(x, b):\n    return x[:b]\n",
         "def probe(x, b):\n    return x[0:b]\n", SLICE_ARG),
        ("_fill_missing_slice_bound",
         "def probe(x, b):\n    return x[:b:2]\n",
         "def probe(x, b):\n    return x[0:b:2]\n", SLICE_ARG),
        ("_fill_missing_slice_bound",
         "def probe(x, b):\n    return x[::2]\n",
         "def probe(x, b):\n    return x[0::2]\n", SLICE_ARG),
        ("_fill_missing_slice_bound",
         "def probe(x, b):\n    return x[:]\n",
         "def probe(x, b):\n    return x[0:]\n", SLICE_ARG),
        ("_canonical_test",
         "def probe(a, b):\n    return 0 if not (a != b) else 1\n",
         "def probe(a, b):\n    return 0 if a == b else 1\n", PAIR_ARG),
        ("_canonical_test",
         "def probe(a, b):\n    return 0 if a != b else 1\n",
         "def probe(a, b):\n    return 1 if a == b else 0\n", PAIR_ARG),
    ]


IDENTITY_PAIRS = _identity_pairs()


@pytest.mark.parametrize("name,shaped,plain,args", IDENTITY_PAIRS,
                         ids=["%s#%d" % (name, number)
                              for number, (name, _, _, _)
                              in enumerate(IDENTITY_PAIRS)])
def test_each_rule_fires_only_where_it_is_an_identity(name, shaped, plain,
                                                      args):
    """The rule closes the normal-form gap, and the two programs agree.

    The first assertion is causation: with no rules the two normal forms
    differ, and with this one rule named they do not. The second is truth:
    executing both programs over the grid returns the same thing, including
    the same type. A rule that rewrote to something merely consistent would
    fail the second half.
    """
    assert _normal_form_with(shaped, ()) != _normal_form_with(plain, ()), (
        "%s has nothing to do on %r" % (name, shaped))
    assert _normal_form_with(shaped, (name,)) == \
        _normal_form_with(plain, (name,)), (
        "%s does not carry %r onto %r" % (name, shaped, plain))
    assert _diverge(shaped, plain, args) == [], (
        "%s rewrites %r to something that computes differently"
        % (name, shaped))


def _untouched_pairs():
    """Shapes each rule must leave alone, and why it must not touch them.

    Every source binds both parameters it is asked about, so the shape under
    test is the one thing that distinguishes one row from the next. A rule
    firing on any of these rewrites a program the candidate wrote in a form
    the rule was never documented for.
    """
    def probe(body: str) -> str:
        return ("def probe(a, b):\n"
                "    left = a\n"
                "    right = b\n"
                "    return 0 if %s else 1\n" % body)

    def unit(body: str) -> str:
        return ("def probe(a, b):\n"
                "    x = a if b else b\n"
                "    return %s\n" % body)

    return [
        ("_drop_unit_factor", unit("x * 2")),
        ("_drop_unit_factor", unit("x * 0")),
        ("_drop_unit_factor", unit("x * -1")),
        ("_drop_unit_factor", unit("x + 1")),
        ("_drop_unit_factor", unit("x // 1")),
        ("_drop_unit_factor", unit("x ** 1")),
        ("_drop_unit_step",
         "def probe(a, b):\n    return list(range(a, b, 2))\n"),
        ("_drop_unit_step",
         "def probe(a, b):\n    return list(range(a, b, 0))\n"),
        ("_drop_unit_step",
         "def probe(a, b):\n    return list(range(a, b, -1))\n"),
        ("_drop_unit_step",
         "def probe(a, b):\n    return list(range(a, b, step=1))\n"),
        ("_drop_unit_step",
         "def probe(a, b):\n    return list(range(a, b))\n"),
        ("_fill_missing_slice_bound",
         "def probe(a, b):\n    x = a if b else b\n    return x[a:b]\n"),
        ("_fill_missing_slice_bound",
         "def probe(a, b):\n    x = a if b else b\n    return x[b:]\n"),
        ("_fill_missing_slice_bound",
         "def probe(a, b):\n    x = a if b else b\n    return x[b]\n"),
        ("_fill_missing_slice_bound",
         "def probe(a, b):\n    x = a if b else b\n    return x[0:b]\n"),
        ("_canonical_test", probe("a == b")),
        ("_canonical_test", probe("not (a == b)")),
        ("_canonical_test", probe("not a")),
        ("_canonical_test", probe("a < b < b")),
        ("_canonical_test", probe("not not (a != b)")),
        ("_canonical_test", probe("(a != b) == b")),
        ("_canonical_test", probe("not (a if b else a)")),
    ]


UNTOUCHED_PAIRS = _untouched_pairs()


@pytest.mark.parametrize("name,source", UNTOUCHED_PAIRS,
                         ids=["%s#%d" % (name, number)
                              for number, (name, _)
                              in enumerate(UNTOUCHED_PAIRS)])
def test_a_rule_leaves_the_shapes_it_must_not_touch_alone(name, source):
    """Applying the rule changes nothing, so it is refused rather than forced.

    A rule that fires on a shape outside its identity rewrites a program
    the candidate wrote in a form the rule was never documented for. The
    normal form is compared with and without the rule; if they differ the
    rule fired where it must not.
    """
    assert _normal_form_with(source, ()) == _normal_form_with(source, (name,)), (
        "%s fires on %r, which is outside its identity" % (name, source))


WITHDRAWN_OPERATORS = ("<", "<=", ">", ">=", "is", "is not", "in", "not in")


def _withdrawn_pairs():
    """The two orientations each withdrawn operator was once admitted in.

    Peeled: `0 if not (a OP b) else 1` against `0 if a == b else 1`, the
    form the `not` alone accounts for. Branch-swapped: `0 if a OP b else 1`
    against `1 if a == b else 0`, the form the swap alone accounts for.
    Rewriting an operator in either orientation is the bug; both are here
    because the old rule did both at once, and did the peel on a predicate
    that carried no `not`.
    """
    pairs = []
    for operator in WITHDRAWN_OPERATORS:
        pairs.append(("peeled", operator,
                      "def probe(a, b):\n    return 0 if not (a %s b) else 1\n"
                      % operator,
                      "def probe(a, b):\n    return 0 if a == b else 1\n"))
        pairs.append(("swapped", operator,
                      "def probe(a, b):\n    return 0 if a %s b else 1\n"
                      % operator,
                      "def probe(a, b):\n    return 1 if a == b else 0\n"))
    return pairs


WITHDRAWN_PAIRS = _withdrawn_pairs()


@pytest.mark.parametrize("orientation,operator,shaped,plain", WITHDRAWN_PAIRS,
                         ids=["%s-%s" % (orientation, operator)
                              for orientation, operator, _, _ in WITHDRAWN_PAIRS])
def test_a_withdrawn_operator_is_not_treated_as_equality(orientation, operator,
                                                         shaped, plain):
    """The eight operators whose negation is not `==` stay refused.

    Two assertions, because either alone passes for the wrong reason. The
    normal forms staying apart says the rule did not admit this operator,
    which is the fix. Some point on the grid where the two programs return
    different things says admitting it would have been a wrong credit,
    which is why the fix is not a matter of taste: `not (a is b)` is
    `a is not b`, and `is` and `==` part company on an int and its float.
    """
    assert tasks._normal_form([shaped]) != tasks._normal_form([plain]), (
        "_canonical_test admitted %r in the %s orientation"
        % (operator, orientation))
    assert _diverge(shaped, plain, PAIR_ARG) != [], (
        "%r in the %s orientation computes the same function, so refusing "
        "it is only conservative and this test proves nothing about it"
        % (operator, orientation))


def test_the_one_sound_comparison_still_collapses():
    """`!=` is the only operator whose negation is `==`, so it is still admitted.

    Without this the refusal above would be satisfiable by a rule that fires
    on nothing. Both orientations, because they are separate claims: the peel
    needs the `not`, the swap needs the branches, and a bare `!=` does not
    reach `==` by either route alone.
    """
    peeled = "def probe(a, b):\n    return 0 if not (a != b) else 1\n"
    swapped = "def probe(a, b):\n    return 0 if a != b else 1\n"

    assert tasks._normal_form([peeled]) == \
        tasks._normal_form(["def probe(a, b):\n    return 0 if a == b else 1\n"])
    assert tasks._normal_form([swapped]) == \
        tasks._normal_form(["def probe(a, b):\n    return 1 if a == b else 0\n"])
    assert _diverge(peeled, "def probe(a, b):\n"
                     "    return 0 if a == b else 1\n", PAIR_ARG) == []
    assert _diverge(swapped, "def probe(a, b):\n"
                     "    return 1 if a == b else 0\n", PAIR_ARG) == []


def test_a_bare_not_eq_does_not_reach_the_peeled_form():
    """The peel and the swap are separate routes, and neither composes.

    `0 if a != b else 1` is `1 if a == b else 0`, not `0 if a == b else 1`.
    A rule that reached the peeled form from a bare `!=` would have applied a
    negation the conditional never had, which is the second half of the
    defect this file covers.
    """
    bare = "def probe(a, b):\n    return 0 if a != b else 1\n"

    assert tasks._normal_form([bare]) != \
        tasks._normal_form(["def probe(a, b):\n"
                            "    return 0 if a == b else 1\n"])
    assert tasks._normal_form([bare]) == \
        tasks._normal_form(["def probe(a, b):\n"
                            "    return 1 if a == b else 0\n"])


# The unit guards compare a node's value against 1, and `1.0 == 1` and
# `True == 1` in Python, so both rules fire on shapes that are not identities.
# `x * 1.0` returns a float where `x` returns an int, and on a digit string it
# raises where `x` returns it. `range(a, b, 1.0)` raises on every argument.
#
# What that costs is a credit rather than a false sentence. Measured: all 44
# candidates ending `* 1.0` scored `repaired` and returned a float where the
# reference returned an int.
#
# The tests below ask the module directly, through `_rule`, whether it fires.
# An earlier version of this file instead ran `x * 1.0` and `x` as two
# programs and asserted they agreed, which is a fact about Python rather than
# about this module: those tests still failed with both rules deleted outright,
# so they could never XPASS and would have advertised a fixed defect forever.
# The evidence that the rewrite is harmful lives in the grid assertions here
# and in `test_the_sound_half_of_the_unit_guards_is_an_identity_on_the_domain`;
# what belongs in a guard test is whether the guard fires.
#
# `xfail(strict=True)` means a narrowed guard turns these into XPASS, which
# pytest reports as a failure, so the marker cannot outlive the fix.

FLOAT_XFAIL = ("the guard is a value comparison, so 1.0 is admitted; measured "
               "44 of 44 candidates ending `* 1.0` scored repaired and "
               "returned a float where the reference returned an int")
STEP_XFAIL = ("the guard is a value comparison, so 1.0 is admitted; "
              "`range(a, b, 1.0)` raises TypeError on every input and is "
              "credited as equal to `range(a, b)`")
BOOL_XFAIL = ("the guard is a value comparison, so True is admitted; "
              "`x * True` and `True * x` drop a multiplication an operand with "
              "a custom `__mul__` can observe")


def _fires(rule_name: str, source: str) -> bool:
    """Whether this one named rule fires anywhere in `source`."""
    rule = _rule(rule_name)
    for node in ast.walk(ast.parse(source)):
        if rule(node) is not None:
            return True
    return False


@pytest.mark.xfail(strict=True, reason=FLOAT_XFAIL)
@pytest.mark.parametrize("side", ("x * 1.0", "1.0 * x"),
                         ids=["right-hand", "left-hand"])
def test_a_unit_factor_refuses_a_float_constant_on_either_side(side):
    """The float is admitted on both sides of the product.

    Both sides matter. The guard has two operand clauses and a fix that
    narrows only one leaves the other admitting the same wrong rewrite, which
    is why this is a pair rather than a single case.
    """
    source = "def probe(x):\n    return %s\n" % side

    assert not _fires("_drop_unit_factor", source), (
        "_drop_unit_factor rewrites %r to `x`, and %r is not `x` on this "
        "module's own digit-string and integer domain"
        % (side, side))


@pytest.mark.xfail(strict=True, reason=BOOL_XFAIL)
@pytest.mark.parametrize("side", ("x * True", "True * x"),
                         ids=["right-hand", "left-hand"])
def test_a_unit_factor_refuses_a_bool_constant_on_either_side(side):
    """A bool is admitted on both sides too, and `True * 1` is the integer 1.

    A rewrite that drops the multiplication also drops the type a downstream
    `==` distinguishes, and on an operand with a custom `__mul__` it drops the
    call altogether. Both facts are in
    `test_the_sound_half_of_the_unit_guards_is_an_identity_on_the_domain`.
    """
    source = "def probe(x):\n    return %s\n" % side

    assert not _fires("_drop_unit_factor", source), (
        "_drop_unit_factor rewrites %r to `x`, which is a different function"
        % side)


@pytest.mark.xfail(strict=True, reason=STEP_XFAIL)
def test_a_unit_range_step_refuses_a_float_step():
    """`range(a, b, 1.0)` is rewritten to a form that raises on every input."""
    source = "def probe(a, b):\n    return list(range(a, b, 1.0))\n"

    assert not _fires("_drop_unit_step", source), (
        "_drop_unit_step rewrites `range(a, b, 1.0)` to `range(a, b)`, which "
        "yields a list where the original raises TypeError")


def test_the_sound_half_of_the_unit_guards_is_an_identity_on_the_domain():
    """`x * 1`, `1 * x` and `range(a, b, 1)` really are the rewrites claimed.

    The xfails above say the guards are too wide. That is only worth saying if
    they are not too narrow, so this pins the shapes they must keep admitting
    and shows the rewrite is sound on them. `x * 1` is not an identity for
    every `x`: a bool operand gives an int, `True * 1` being `1`, and an
    operand with a custom `__mul__` observes the dropped call. It is an
    identity on the operands this instrument uses.
    """
    for shaped, plain in (
            ("def probe(x):\n    return x * 1\n",
             "def probe(x):\n    return x\n"),
            ("def probe(x):\n    return 1 * x\n",
             "def probe(x):\n    return x\n")):
        assert _diverge(shaped, plain, ONE_ARG) == []
        assert _fires("_drop_unit_factor", shaped)
    assert _diverge(
        "def probe(a, b):\n    return list(range(a, b, 1))\n",
        "def probe(a, b):\n    return list(range(a, b))\n", RANGE_ARG) == []
    assert _fires(
        "_drop_unit_step",
        "def probe(a, b):\n    return list(range(a, b, 1))\n")


def test_the_unit_factor_identity_breaks_on_a_call_the_operand_observes():
    """`x * 1` drops a call, which an operand with a `__mul__` can see.

    Not an xfail. No guard narrowing fixes it, because `1` is an int and the
    guard admits an int. It is stated as a fact about the documented rewrite
    so the docstring's "for the operands this instrument uses" cannot be read
    as a claim about Python, and so a reader knows the boundary.
    """
    observable = ("class W:\n"
                  "    def __mul__(self, other):\n"
                  "        return ('mul', other)\n"
                  "    def __rmul__(self, other):\n"
                  "        return ('rmul', other)\n")
    namespace = {}
    exec(observable + "def probe(x):\n    return x\n", namespace)
    expected = namespace["probe"](namespace["W"]())
    namespace = {}
    exec(observable + "def probe(x):\n    return x * 1\n", namespace)
    got = namespace["probe"](namespace["W"]())

    assert got != expected, (
        "`x * 1` no longer calls the operand, so the rewrite is an identity "
        "for builtins only; a docstring claiming otherwise is false")


# --- The certificate itself, over the whole catalogue. ---


def _all_instances():
    return (tasks.enumerate_instances("dev")
            + tasks.enumerate_instances("held_out"))


def test_every_reference_repairs_its_own_instance():
    """All 39 instances score `repaired` against their own reference.

    The strongest liveness claim the instrument has. If one reference stopped
    reducing to its own normal form, the `repaired` outcome would be
    unreachable for that instance and every repair rate read off it would be
    measuring a harness that no longer credits anything. Nothing else here
    would notice: the refusal tests all pass against a rule list that admits
    nothing at all.
    """
    records = _all_instances()

    assert len(records) == 39
    scored = [(record, tasks.score(record, record["reference_source"]))
              for record in records]

    assert [(record["task_id"], outcome["outcome"])
            for record, outcome in scored
            if outcome["outcome"] != "repaired"] == []
    assert {outcome["public_passed"] for _, outcome in scored} == \
        {outcome["public_total"] for _, outcome in scored}
    assert {outcome["protected"]["outcome"] for _, outcome in scored} == {"pass"}


FAULT_FAMILIES = ("off_by_one", "double_count", "dropped_guard",
                  "stale_accumulator", "index_drift")


def test_no_faulty_source_is_credited_in_any_family():
    """Zero credits per fault family, and the fault is confirmed applied.

    A zero is only worth reading next to evidence that the faulty source
    differs from the reference, that it fails the case the catalogue says the
    fault is observable on, and that it cleared every other bar. If any of
    those were false the family would be contributing nothing and the zero
    would be vacuous.
    """
    by_family = {}
    for record in _all_instances():
        by_family.setdefault(record["mechanism"], []).append(record)

    assert set(FAULT_FAMILIES) <= set(by_family)

    for family in FAULT_FAMILIES:
        records = by_family[family]
        assert records, "no instance carries the %s fault" % family

        for record in records:
            faulty, reference = record["source"], record["reference_source"]
            changed = [number for number, (line, other)
                       in enumerate(zip(faulty, reference), start=1)
                       if line != other]

            assert changed, (
                "%s left the source unchanged, so the fault is not applied"
                % record["task_id"])
            assert len(changed) == 1, (
                "%s changed %d lines (%s), so it is not the single fault the "
                "catalogue claims"
                % (record["task_id"], len(changed), changed))
            # The site is a fault label and is deliberately withheld from the
            # record, so the patch is where a reader can read it from.
            assert changed == [edit["line"] for edit in record["patch"]], (
                "%s changed line %s but its patch claims %s, so the fault and "
                "the repair it derives do not describe the same line"
                % (record["task_id"], changed,
                   [edit["line"] for edit in record["patch"]]))

            scored = tasks.score(record, faulty)
            assert scored["outcome"] != "repaired", (
                "%s (%s) was credited as a repair while still carrying its "
                "fault" % (record["task_id"], family))
            assert scored["protected"]["outcome"] == "fail", (
                "%s (%s) passes its own protected case, so the fault it "
                "carries is not observable there and the refusal above says "
                "nothing" % (record["task_id"], family))

        credited = [record["task_id"] for record in records
                    if tasks.score(record, record["source"])["outcome"]
                    == "repaired"]

        assert credited == [], "%s credited %d faulty sources" % (
            family, len(credited))


def _shadow_for(record: dict) -> list:
    """The reference gated to the box its own drawn cases happen to reach.

    The shape of the first defect found in this file: correct inside a box
    chosen to cover the cases that were drawn, a constant outside it. The box
    is read off the drawn cases rather than hardcoded, so the shadow is
    exactly as generous as the sampling the instrument replaces.
    """
    source = tasks.render_source(record["reference_source"])
    lines = source.split("\n")
    function = ast.parse(source).body[0]
    counts = sorted(case["args"][1] for case in
                    record["public_tests"] + [record["protected_test"]])
    low, high = counts[0], counts[-1]
    first = function.body[0]
    at = first.end_lineno if isinstance(first, ast.Expr) and isinstance(
        first.value, ast.Constant) else first.lineno
    indent = " " * first.col_offset

    return [line + "\n" for line in
            lines[:at] + ["%sif not (%d <= n <= %d):" % (indent, low, high),
                          "%s    return -999" % indent] + lines[at:]
            if line]


def test_a_gate_sized_shadow_is_refused_on_every_instance():
    """A candidate correct only where it was shown does not score `repaired`.

    Built per instance from that instance's own drawn cases, so it agrees with
    the reference on every case `score` runs and is wrong everywhere else. The
    test also asserts the shadow passed all of them, because a shadow that
    failed its own drawn cases would be refused for the uninteresting reason
    that it is simply broken.
    """
    mismatched = []
    repaired = []
    credited = []
    for record in _all_instances():
        program = tasks.PROGRAMS_BY_NAME[record["template"]]
        shadow = _shadow_for(record)
        drawn = record["public_tests"] + [record["protected_test"]]

        for case in drawn:
            got = _result(program, shadow, case["args"])
            want = _result(program, record["reference_source"], case["args"])
            if got != want:
                mismatched.append((record["task_id"], case["args"]))
        verdict = tasks.equivalence_verdict(record, shadow)["outcome"]
        if verdict == "pass":
            credited.append(record["task_id"])
        if tasks.score(record, shadow)["outcome"] == "repaired":
            repaired.append(record["task_id"])

    assert mismatched == [], (
        "the shadow did not agree with the reference on every drawn case, so "
        "its refusal says nothing: %s" % mismatched[:3])
    assert credited == []
    assert repaired == []


# --- Sound refusals: wrong for a stated reason, not by accident. ---

RENAME = {"total": "accum", "window": "slice_", "marker": "flag",
          "contribution": "part", "seen": "counted", "previous": "prior",
          "carry": "held", "state": "position", "width": "extent",
          "start": "origin", "index": "offset", "moves": "table",
          "body": "digits", "n": "limit"}


def _renamed(record: dict) -> list:
    """The reference with every binding renamed consistently.

    The entry point's own name is left alone: it is the harness's handle on the
    program, so renaming it produces a program that does not run rather than
    one that runs and computes the same thing.
    """
    entry = tasks.PROGRAMS_BY_NAME[record["template"]].entry
    table = {name: new for name, new in RENAME.items() if name != entry}

    class Renamer(ast.NodeTransformer):
        def swap(self, ident):
            return table.get(ident, ident)

        def visit_Name(self, node):
            if not hasattr(builtins, node.id):
                node.id = self.swap(node.id)
            return node

        def visit_arg(self, node):
            node.arg = self.swap(node.arg)
            return node

    source = tasks.render_source(record["reference_source"])
    tree = Renamer().visit(ast.parse(source))
    text = ast.unparse(ast.fix_missing_locations(tree))

    return [line + "\n" for line in text.split("\n") if line]


def _result(program, lines: list, args: list) -> dict:
    """What one call of a catalogue program returned, or how it failed.

    `run_program` reports the failing line's text as well as the exception's
    name, and that text names the variables in it, so a renamed program
    raises a differently-worded error while failing identically. Comparing
    the exception's name instead is what makes "computes the reference" a
    statement about behaviour rather than about spelling.
    """
    outcome = tasks.run_program(program, args, lines)
    if outcome["kind"] != "value":
        return {"error": outcome["name"]}
    return {"value": repr(outcome["value"]),
            "type": type(outcome["value"]).__name__}


def test_a_consistently_renamed_reference_is_refused_structurally():
    """The refusal comes from the normal-form comparison, not from a bad parse.

    `equivalence_verdict` fails two different ways and this test tells them
    apart. A candidate that does not parse has normal form `None` and is
    refused without ever being compared. The renamed candidate parses, so its
    normal form exists and differs from the reference's, and that difference
    is the whole reason for the verdict. It is also a correct repair: it
    computes the reference on every drawn case and across the grid, which is
    what makes the refusal the cost the module says it is paying.
    """
    unparsed = []
    identical = []
    wrongly_credited = []
    not_equivalent = []
    for record in _all_instances():
        program = tasks.PROGRAMS_BY_NAME[record["template"]]
        renamed = _renamed(record)

        mine = tasks._normal_form(renamed)
        if mine is None:
            unparsed.append(record["task_id"])
            continue
        if mine == tasks._normal_form(record["reference_source"]):
            identical.append(record["task_id"])
        if tasks.equivalence_verdict(record, renamed)["outcome"] == "pass":
            wrongly_credited.append(record["task_id"])
        if tasks.equivalence_verdict(
                record, record["reference_source"])["outcome"] != "pass":
            not_equivalent.append(record["task_id"])

        grid = [(digits, count) for digits in DIGITS for count in COUNTS]
        for args in (record["public_tests"][0]["args"],
                     record["protected_test"]["args"]) + tuple(grid):
            got = _result(program, renamed, args)
            want = _result(program, record["reference_source"], args)
            assert got == want, (
                "%s: the renamed candidate does not compute the reference on "
                "%s, so refusing it proves nothing" % (record["task_id"], args))

    assert unparsed == [], (
        "the renamed candidate did not parse, so its refusal would be for "
        "the wrong reason: %s" % unparsed)
    assert identical == []
    assert wrongly_credited == []
    assert not_equivalent == []


def test_an_unparseable_program_refuses_through_the_normal_form():
    """The `None` path is real, and it is distinct from the structural refusal.

    Two cases, because `None` reaching the comparison at all is the hole. With
    a parseable reference, `mine` is `None` and `theirs` is a string, so a
    verdict of `fail` follows whether or not the `is not None` guard is there.
    With a reference that also does not parse, both sides are `None` and
    `None == None` is true, so dropping the guard credits a candidate that was
    never compared with anything. Measured: removing
    `mine is not None and` from `equivalence_verdict` leaves every other test
    in this file green and turns this one red.
    """
    record = _all_instances()[0]
    broken = ["def broken(:\n"]

    assert tasks._normal_form(broken) is None
    assert tasks._normal_form(["def broken(x)\n    return x\n"]) is None
    assert tasks._normal_form(["class :::\n"]) is None
    assert tasks._normal_form(["x = = 1\n"]) is None
    # `this is not python` parses: it is a chained comparison.
    assert tasks._normal_form(["this is not python\n"]) is not None

    assert tasks.equivalence_verdict(record, broken)["outcome"] == "fail"

    both_broken = {"reference_source": broken}

    assert tasks._normal_form(both_broken["reference_source"]) is None
    assert tasks.equivalence_verdict(both_broken, broken)["outcome"] == "fail", (
        "an unparseable reference normalises to None as well, so the verdict "
        "compares None with None; a candidate that was never compared with "
        "anything must still be refused")
    assert tasks.equivalence_verdict(
        record, record["reference_source"])["outcome"] == "pass"