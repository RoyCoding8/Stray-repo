"""Is the shipped `_canonical_test` an identity on every shape it fires on?

For each (shape, operator) the rule rewrites, compare the candidate's own
behaviour against the behaviour of the term it rewrote it to. Ground truth is
direct evaluation, so an operator that raises counts as raising on both sides
rather than silently agreeing.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ast
import sys


from experiments.ad01 import s09_swe_tasks as S

OPS = {"==": ast.Eq, "!=": ast.NotEq, "<": ast.Lt, "<=": ast.LtE,
       ">": ast.Gt, ">=": ast.GtE, "is": ast.Is, "is not": ast.IsNot,
       "in": ast.In, "not in": ast.NotIn}

SHAPES = {
    "bare          ": "0 if a {op} b else 1",
    "under not     ": "0 if not (a {op} b) else 1",
    "swapped bare  ": "1 if a {op} b else 0",
    "swapped+not   ": "1 if not (a {op} b) else 0",
}


def _inputs():
    pairs = [(0, 0), (1, 2), (2, 1), (1, 1), (2, 2), (-1, 1), (3, 3),
             (1000, 1000.0), (1.0, 1), (0.0, -0.0), (5, 5.0)]
    lists = [([], []), ([1], [1]), ([1, 2], [1, 2]), ([], [1]), ([1], []),
             (0, False), (1, True)]
    return pairs + lists


INPUTS = _inputs()


def dump(expr):
    return ast.dump(ast.parse("def f(a, b):\n    return %s\n" % expr))


def rewrite(expr):
    """The tree the shipped rule produces, as source text."""
    tree = ast.parse("def f(a, b):\n    return %s\n" % expr)
    out = S._rewrite(tree)
    return ast.unparse(out.body[0].body[0].value)


def fired_on(candidate):
    """True only when the rewrite changed the tree, not just its spelling."""
    return dump(candidate) != dump(rewrite(candidate))


def value(expr, a, b):
    try:
        return ("v", repr(eval(expr, {"__builtins__": {}}, {"a": a, "b": b})))
    except Exception as exc:
        return ("e", type(exc).__name__)


fired, sound, unsound = 0, [], []
for shape, template in SHAPES.items():
    for name in OPS:
        candidate = template.format(op=name)
        if not fired_on(candidate):
            continue
        rewritten = rewrite(candidate)
        fired += 1
        witness = next(((x, y) for x, y in INPUTS
                        if value(candidate, x, y) != value(rewritten, x, y)),
                       None)
        entry = (shape + name, candidate, rewritten, witness)
        (unsound if witness else sound).append(entry)

print("shapes the rule fires on : %d" % fired)
print("  identity holds         : %d" % len(sound))
print("  identity fails         : %d" % len(unsound))
for shape, candidate, rewritten, witness in unsound:
    print("   UNSOUND %s" % shape)
    print("      %s  ->  %s" % (candidate, rewritten))
    print("      witness %r: %s vs %s"
          % (witness, value(candidate, *witness),
             value(rewritten, *witness)))
if not unsound:
    for shape, candidate, rewritten, _ in sound:
        print("   sound    %s  %s  ->  %s" % (shape, candidate, rewritten))

print()
print("=== the three guard rules, checked the same way ===")
GUARDS = [
    ("_drop_unit_factor", "(a * 1)", "(a)", lambda e: S._drop_unit_factor(
        ast.parse(e, mode="eval").body) is not None),
    ("_drop_unit_factor", "(1 * a)", "(a)", lambda e: S._drop_unit_factor(
        ast.parse(e, mode="eval").body) is not None),
    ("_drop_unit_step", "range(a, b, 1)", "range(a, b)", None),
    ("_fill_missing_slice_bound", "c[:a]", "c[0:a]", None),
]
for name, before, after, _ in GUARDS:
    rew = rewrite(before)
    ok = all(value(before, x, y) == value(after, x, y) for x, y in INPUTS)
    print("  %-26s %-14s -> %-14s  identity: %s"
          % (name, before, rew, "yes" if ok else "NO"))