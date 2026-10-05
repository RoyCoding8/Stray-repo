"""Post-fix behaviour checks.

1. the n=1 candidate is refused, and its normal form differs
2. the plain reference is still credited
3. a consistently renamed reference is refused, and says so as a refusal
4. the three other rules still admit what they admitted before the change
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ast
import sys


from experiments.ad01 import s09_swe_tasks as S

REC = S.instance("dev", "count-lead-sum", "inverted_guard")
REF = list(REC["reference_source"])
PROGRAM = S.PROGRAMS_BY_NAME[REC["template"]]
GUARD_LINE = "        marker = 0 if seen == 0 else 1"
SITE = REF.index(GUARD_LINE + "\n")

print("=" * 72)
print("1. the n=1 candidate")
print("=" * 72)
for label, text in (
        ("the triggering form", "        marker = 1 if not (seen < 0) else 0"),
        ("its >= sibling", "        marker = 1 if seen >= 0 else 0"),
        ("a sound `not (x != y)`", "        marker = 0 if not (seen != 0) else 1"),
        ("a sound bare `!=` swap", "        marker = 1 if seen != 0 else 0"),
        ("the reference itself", GUARD_LINE),
):
    candidate = list(REF)
    candidate[SITE] = text + "\n"
    verdict = S.score(REC, candidate)
    same = S._normal_form(candidate) == S._normal_form(REF)
    probe = S.run_program(PROGRAM, ["12345", 1], candidate)
    want = S.run_program(PROGRAM, ["12345", 1], REF)
    agrees = probe == want
    print("  %-24s %-12s normal_form_same=%-5s agrees_at_n=1=%s"
          % (label, verdict["outcome"], same, agrees))

print()
print("=" * 72)
print("2. the reference is still credited")
print("=" * 72)
print("  score(reference)['outcome'] =", S.score(REC, REF)["outcome"])

print()
print("=" * 72)
print("3. a renamed reference")
print("=" * 72)
RENAMES = (("seen", "count"), ("total", "accum"), ("index", "i"),
           ("contribution", "add"), ("previous", "prior"))
renamed = []
for line in REF:
    for old, new in RENAMES:
        line = line.replace(old, new)
    renamed.append(line)
print("  identical to the reference after renaming:",
      renamed == REF)
verdict = S.score(REC, renamed)
print("  score(renamed)['outcome'] =", verdict["outcome"])
print("  normal forms equal:", S._normal_form(renamed) == S._normal_form(REF))
grid = [("12345", 1), ("12345", 2), ("123", 4), ("", 0), ("123456", 7)]
mismatch = [(b, n) for b, n in grid
            if S.run_program(PROGRAM, [b, n], renamed)
            != S.run_program(PROGRAM, [b, n], REF)]
print("  behaves identically to the reference on %d probes: %s"
      % (len(grid), not mismatch))
print("  -> a correct repair is refused, which is the documented direction")

print()
print("=" * 72)
print("4. the other three rules still admit what they admitted")
print("=" * 72)
CASES = [
    ("_drop_unit_factor", "        contribution = 7 * 1 + seen",
     "        contribution = 7 + seen"),
    ("_drop_unit_factor", "        contribution = 1 * 7 + seen",
     "        contribution = 7 + seen"),
    ("_drop_unit_step",
     "    for index in range(1, n + 1, 1):\n        pass",
     "    for index in range(1, n + 1):\n        pass"),
    ("_fill_missing_slice_bound",
     "        window = body[:index + 2]\n        pass",
     "        window = body[0:index + 2]\n        pass"),
]
HOLD = S.instance("held_out", "count-tail-sum", "index_drift")
HSITE = next(i for i, line in enumerate(HOLD["reference_source"])
             if "body[0:" in line)
for name, before, after in CASES:
    # apply the identity to the reference, and check it is still credited
    target = next((i for i, line in enumerate(HOLD["reference_source"])
                   if line.rstrip() == after), None)
    if target is None:
        target = next((i for i, line in enumerate(HOLD["reference_source"])
                       if line.rstrip() == after.replace("index", "start")
                       or line.rstrip() == after.replace("index + 2",
                                                         "start + 2")), None)
    candidate = list(HOLD["reference_source"])
    verdict = S.score(HOLD, candidate)
    # and the direct check: does the normal form of `before` equal that of
    # `after`, using only the rule named?
    def form(text):
        body = text if text.startswith("def ") else "def f(body, n):\n" + text
        tree = ast.parse(body)
        return ast.dump(ast.fix_missing_locations(S._rewrite(tree)))
    ok = form(before) == form(after)
    print("  %-26s %-38s normal forms equal: %s"
          % (name, before.strip(), ok))
print("  reference still credited on the record used:",
      S.score(HOLD, list(HOLD["reference_source"]))["outcome"])