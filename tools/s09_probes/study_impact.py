"""What does the shipped policy actually emit, and does the fix change it?

The module's measured claim about the study run rests on `pol.rewrites()`.
Enumerate it over every faulty instance, score each candidate, and report the
credited and credited-wrong counts before and after the rule change.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sys


import census as C
from experiments.ad01 import s09_swe_tasks as S
from experiments.ad01 import s09_swe_policy as POL


def installed_rule():
    return S._NORMALISERS[-1]


GUARDS = (S._drop_unit_factor, S._drop_unit_step, S._fill_missing_slice_bound)
FIXED = installed_rule()


def unshipped_rule(node):
    """The pre-fix rule, restored verbatim, for the before/after comparison."""
    import ast
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


def sweep(label, rule):
    S._NORMALISERS = GUARDS + (rule,)
    C._DIFF_CACHE.clear()
    total = credited = wrong = 0
    forms = set()
    instances = 0
    for split in ("dev", "held_out"):
        for record in S.enumerate_instances(split):
            instances += 1
            program = S.PROGRAMS_BY_NAME[record["template"]]
            source = record["source"]
            pool = [line for line in source]
            ref_entry = C._load(program.entry, record["reference_source"])
            for number, source_line in enumerate(source, start=1):
                for line in POL.rewrites(source_line, pool):
                    candidate = S.apply_edits(source, [{"line": number,
                                                       "text": line}])
                    if candidate == source:
                        continue
                    total += 1
                    if S.score(record, candidate)["outcome"] != "repaired":
                        continue
                    credited += 1
                    diff = C.behaviour_diff(program, ref_entry, candidate)
                    if diff is not None:
                        wrong += 1
                        forms.add((program.name, line.strip()))
    print("  %s" % label)
    print("     instances %d   scorable candidates %d   credited %d   "
          "credited-wrong %d" % (instances, total, credited, wrong))
    for form in sorted(forms):
        print("       wrong credit: %s" % (form,))
    return credited, wrong


if __name__ == "__main__":
    print("=" * 72)
    print("the shipped policy's own edit vocabulary, scored both ways")
    print("=" * 72)
    sweep("before the fix (nine-operator allowlist)", unshipped_rule)
    sweep("after the fix (negation accounted for once)", FIXED)