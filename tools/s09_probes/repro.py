"""Reproduce the `_canonical_test` unsound rewrite, before any change."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sys

from experiments.ad01 import s09_swe_tasks as S

REC = S.instance("dev", "count-lead-sum", "inverted_guard")
print("record template:", REC["template"])
print("public n:", [c["args"][1] for c in REC["public_tests"]],
      " protected n:", REC["protected_test"]["args"][1])

REF_LINE = "        marker = 0 if seen == 0 else 1"
BAD_LINE = "        marker = 1 if not (seen < 0) else 0"

ref_lines = list(REC["reference_source"])
bad_lines = list(REC["reference_source"])
idx = ref_lines.index(REF_LINE + "\n")
bad_lines[idx] = BAD_LINE + "\n"

nf_ref = S._normal_form(ref_lines)
nf_bad = S._normal_form(bad_lines)
print("normal forms identical:", nf_ref == nf_bad)
print("equivalence_verdict:", S.equivalence_verdict(REC, bad_lines))
print("score()['outcome']:", S.score(REC, bad_lines)["outcome"])

print("--- behaviour sweep over (body, n) ---")
prog = S.PROGRAMS_BY_NAME[REC["template"]]
body = "12345"
for n in (1, 2, 3):
    a = S.run_program(prog, [body, n], ref_lines)
    b = S.run_program(prog, [body, n], bad_lines)
    print("n=%d   reference=%s   candidate=%s   %s" % (
        n, a.get("value"), b.get("value"),
        "SAME" if a == b else "*** DIFFERENT ***"))
print("N_RANGE =", S.N_RANGE, "-> n=1 is outside the drawn domain")

print()
print("--- is `not P` ever the same as `==` for these operators? ---")
print("not (0 != 0) ->", not (0 != 0), " vs 0 == 0 ->", 0 == 0, " agree")
print("not (0 < 0)  ->", not (0 < 0), "  vs 0 == 0 ->", 0 == 0, " disagree")
print("not (1 < 0)  ->", not (1 < 0), "  vs 1 == 0 ->", 1 == 0, " disagree")
print("not (5 in [1,2]) ->", not (5 in [1, 2]), " vs 5 == [1,2] ->", 5 == [1, 2])
a, b = [], []
print("a is b ->", a is b, " a == b ->", a == b)
print("1000 is 1000.0 ->", 1000 is 1000.0, " 1000 == 1000.0 ->", 1000 == 1000.0)