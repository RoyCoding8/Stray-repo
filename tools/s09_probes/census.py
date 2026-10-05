"""Mutation census for the s09 equivalence certificate.

`score` credits `repaired` only when a candidate's normal form equals the
reference's. The four rules in `_NORMALISERS` are the only thing that can make
that happen, so a census that measures the certificate has to generate the
mutations those rules claim to reach, plus a churn sweep for breadth.

Two generators:

  identity  - the forward direction of each of the four rules, applied to the
              source text and to pairs of them on one line. Every mutation it
              emits is either a true identity (so a correct repair, and the
              certificate should credit it) or the false claim the rule makes
              (the certificate must not credit it).
  churn     - numeric and comparison-operator replacement, which is mostly
              wrong and measures how much noise passes.

A credited candidate is then checked against the reference on a probe grid
that reaches outside the drawn domain, because a candidate can agree on every
drawn case and still be wrong elsewhere. That is the whole failure this
census exists to count.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ast
import itertools
import re
import sys


from experiments.ad01 import s09_swe_tasks as S

MAX_STEPS = 200000


# ---------------------------------------------------------------- oracle ---

class _Budget(Exception):
    pass


def _load(entry_name, lines):
    """Compile a program once and hand back its entry point, or None."""
    try:
        tree = compile(S.render_source(lines), "<census>", "exec")
    except Exception:
        return None
    namespace = {}
    try:
        exec(tree, namespace)
    except Exception:
        return None
    entry = namespace.get(entry_name)
    return entry if callable(entry) else None


def _call(entry, args, budget):
    def tracer(frame, event, arg):
        if budget[0] <= 0:
            raise _Budget
        budget[0] -= 1
        return None
    budget[0] = MAX_STEPS
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        return ("value", entry(*args))
    except Exception:
        return ("error", None)
    finally:
        sys.settrace(previous)


def probe_grid():
    """Inputs the drawn cases never cover.

    The drawn domain is n in 2..4 over bodies of length 4..6 over "123". n <= 1
    is where the known divergence sits, so it leads the grid.
    """
    bodies = []
    for length in (1, 2, 3, 4, 5):
        bodies.extend("".join(t) for t in itertools.product("123", repeat=length))
    bodies = sorted(set(bodies), key=lambda b: (len(b), b))
    return [(body, n) for n in (1, 0, 2, 3, 4, 5, 6, 7, 8) for body in bodies]


GRID = probe_grid()


_DIFF_CACHE = {}


def behaviour_diff(program, ref_entry, cand_lines):
    """First (body, n) where the candidate disagrees with the reference.

    None when it agrees everywhere on the grid, "unloadable" when it does not
    run at all. A grid that cannot reach every reachable state is still a grid
    that reaches the drawn domain and its near misses, which is what the wrong
    credits live in.
    """
    key = (program.name, S.render_source(cand_lines))
    if key in _DIFF_CACHE:
        return _DIFF_CACHE[key]
    cand_entry = _load(program.entry, cand_lines)
    if cand_entry is None:
        _DIFF_CACHE[key] = "unloadable"
        return "unloadable"
    result = None
    for body, n in GRID:
        if _call(ref_entry, (body, n), [0]) != _call(cand_entry, (body, n), [0]):
            result = "reached"
            break
    _DIFF_CACHE[key] = result
    return result


# ------------------------------------------------- identity forward image ---

MUL, ADD, SUB = ast.Mult, ast.Add, ast.Sub


def _c(value):
    return ast.Constant(value=value)


def _clone(node):
    return ast.parse(ast.unparse(node), mode="eval").body


def _ifexps(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.IfExp)]


def _identity_edits(text):
    """Source-level forward images of the four rules, on one line.

    Each rule contributes a group of (span-as-written, replacement) pairs, and
    the emitted mutations are the direct product across groups, so two rules
    that touch the same span are both generated rather than one overwriting
    the other.
    """
    try:
        tree = ast.parse(text.strip())
    except SyntaxError:
        return []
    groups = []

    def group(original, replacement):
        """Record (span-as-written, its replacement). Spans may overlap."""
        try:
            key = ast.unparse(original)
            new = ast.unparse(replacement)
        except Exception:
            return
        if key and key in text and new and new != key:
            groups.append((key, new))

    # `_drop_unit_factor`: `x` written `x * 1` is still `x`.
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        if isinstance(node.op, MUL) and isinstance(node.right, ast.Constant) \
                and node.right.value == 1:
            group(node, node.left)
        elif isinstance(node.op, MUL):
            group(node, ast.BinOp(left=node, op=MUL(), right=_c(1)))

    # `_drop_unit_step`: `range(a, b, 1)` yields `range(a, b)`.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "range" and len(node.args) == 2:
            group(node, ast.Call(func=_clone(node.func),
                               args=list(node.args) + [_c(1)], keywords=[]))

    # `_fill_missing_slice_bound`: `x[:b]` is `x[0:b]`.
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice) \
                and node.slice.lower is None:
            node.slice.lower = _c(0)
            group(node, node)
            node.slice.lower = None

    # `_canonical_test`, as the whole family the rule claims to normalise:
    # branch order in {as-written, swapped}, a `not` in {present, absent},
    # and a comparison operator in all ten. The operator sweep under a `not`
    # is what the rule's docstring justifies for exactly one operator, so the
    # other nine are the disputed claims and have to be generated.
    for node in _ifexps(tree):
        inner = node.test
        if isinstance(inner, ast.UnaryOp) and isinstance(inner.op, ast.Not):
            inner = inner.operand
        comparable = isinstance(inner, ast.Compare) and len(inner.ops) == 1
        operators = ([_OP_TYPES[op]() for op in CMP_OPS] if comparable
                     else [None])
        for swap in (False, True):
            yes, no = ((node.orelse, node.body) if swap
                       else (node.body, node.orelse))
            for negated in (False, True):
                for operator in operators:
                    if comparable:
                        test = ast.Compare(left=_clone(inner.left), ops=[operator],
                                           comparators=[
                                               _clone(inner.comparators[0])])
                    else:
                        test = _clone(inner)
                    if negated:
                        test = ast.UnaryOp(op=ast.Not(), operand=test)
                    group(node, ast.IfExp(test=test, body=_clone(yes),
                                          orelse=_clone(no)))

    out = []
    for index, (first, one) in enumerate(groups):
        out.append(text.replace(first, one))
        for second, two in groups[index + 1:]:
            if second not in text or second == first:
                continue
            composed = text.replace(second, two).replace(first, one)
            if composed != text:
                out.append(composed)
    return out


# ------------------------------------------------------------------ churn ---

NUM = re.compile(r"(?<![\w.])(\d+)(?![\w.])")
CMP_OPS = ("==", "!=", "<=", ">=", "<", ">", "is not", "is", "in", "not in")
_OP_TYPES = {"==": ast.Eq, "!=": ast.NotEq, "<=": ast.LtE, ">=": ast.GtE,
             "<": ast.Lt, ">": ast.Gt, "is": ast.Is, "is not": ast.IsNot,
             "in": ast.In, "not in": ast.NotIn}


def _churn_edits(text):
    out = set()
    for match in NUM.finditer(text):
        value = int(match.group(1))
        for replacement in (0, 1, 2, 3, value + 1, max(0, value - 1)):
            if replacement == value:
                continue
            out.add(text[:match.start(1)] + str(replacement)
                    + text[match.end(1):])
    for op in CMP_OPS:
        for start in _spaced(text, op):
            for other in CMP_OPS:
                if other == op:
                    continue
                out.add(text[:start] + other + text[start + len(op):])
    return out


def _spaced(text, op):
    """Every start index where `op` appears as a whole word pair."""
    out = []
    start = 0
    while True:
        found = text.find(op, start)
        if found == -1:
            return out
        before = text[found - 1] if found else " "
        after = text[found + len(op)] if found + len(op) < len(text) else " "
        whole = (before in " \t(" and after in " \t),+")
        if not (before.isalnum() or before == "_") and \
                not (after.isalnum() or after == "_") and whole:
            out.append(found)
        start = found + 1


# ----------------------------------------------------------------- census ---

def mutations(source, with_churn=True):
    """Every single-line replacement of `source`, deduplicated per position."""
    for index, line in enumerate(source):
        text = line.rstrip("\n")
        candidates = set(_identity_edits(text))
        if with_churn:
            candidates |= _churn_edits(text)
        candidates.discard(text)
        for replacement in sorted(candidates):
            if "\n" in replacement:
                continue
            yield index, replacement


def census(with_churn=True, per_record=None):
    records = []
    for split in ("dev", "held_out"):
        records.extend(S.enumerate_instances(split))
    if per_record is not None:
        records = records[:per_record]
    credited = []
    total = 0
    for record in records:
        program = S.PROGRAMS_BY_NAME[record["template"]]
        ref_lines = list(record["reference_source"])
        ref_entry = _load(program.entry, ref_lines)
        ref_form = S._normal_form(ref_lines)
        for index, text in mutations(ref_lines, with_churn):
            total += 1
            candidate = list(ref_lines)
            candidate[index] = text + "\n"
            verdict = S.score(record, candidate)
            if verdict["outcome"] != "repaired":
                continue
            credited.append({
                "split": split,
                "template": record["template"],
                "mechanism": record["mechanism"],
                "site": index,
                "reference_line": ref_lines[index].strip(),
                "text": text.strip(),
                "diff": behaviour_diff(program, ref_entry, candidate),
                "same_form": S._normal_form(candidate) == ref_form,
            })
    return total, credited


def report(label, total, credited):
    wrong = [item for item in credited if item["diff"] is not None]
    reachable = [item for item in wrong if item["diff"] == "reached"]
    forms = {}
    for item in wrong:
        forms.setdefault((item["reference_line"], item["text"]), []).append(item)
    print()
    print("=== %s ===" % label)
    print("mutations:                          %d" % total)
    print("credited `repaired`:                %d" % len(credited))
    print("credited AND wrong:                 %d" % len(wrong))
    print("  ...reached by a disagreeing input: %d" % len(reachable))
    print("distinct credited-wrong forms:      %d" % len(forms))
    for (ref, got), items in sorted(forms.items()):
        splits = sorted({i["split"] for i in items})
        print("  x%-3d [%s]" % (len(items), ",".join(splits)))
        print("      ref: %s" % ref)
        print("      got: %s" % got)
    return reachable


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("identity", "both"):
        total, credited = census(with_churn=False)
        report("identity mutations only", total, credited)
    if mode in ("churn", "both"):
        total, credited = census(with_churn=True)
        report("identity + churn", total, credited)