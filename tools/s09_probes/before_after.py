"""Before/after on the wider churn census, using the shipped rule as shipped.

Runs both rules over identity+churn mutations so the two figures come from
one script rather than from two.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ast
import sys


import census as C
from experiments.ad01 import s09_swe_tasks as S

GUARDS = (S._drop_unit_factor, S._drop_unit_step, S._fill_missing_slice_bound)


def unshipped(node):
    if not isinstance(node, ast.IfExp):
        return None
    test = node.test
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        test = test.operand
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or \
            len(test.comparators) != 1:
        return None
    if isinstance(test.ops[0], ast.Eq):
        return None
    if not isinstance(test.ops[0], (ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
                                   ast.GtE, ast.Is, ast.IsNot, ast.In,
                                   ast.NotIn)):
        return None
    node.test = ast.Compare(left=test.left, ops=[ast.Eq()],
                            comparators=test.comparators)
    node.body, node.orelse = node.orelse, node.body
    return node


FIXED = S._NORMALISERS[-1]

for label, rule in (("BEFORE (as shipped, nine operators)", unshipped),
                    ("AFTER  (one negation, accounted for once)", FIXED)):
    S._NORMALISERS = GUARDS + (rule,)
    C._DIFF_CACHE.clear()
    total, credited = C.census(with_churn=True)
    C.report(label, total, credited)