"""Reproduce pytest's collection ORDER and per-file test COUNTS for tests/.

Static analysis. Imports nothing from the package, opens no database, runs no
pytest. Reads a checkout of tests/ and emits the node-id sequence pytest builds,
in the order pytest builds it.

Why this exists
---------------
Four CI shards stop at the same collection index and then emit nothing for
~58 minutes. Naming the test at that index needs the collection ORDER, not a
guess at it. This produces that order, and validates itself against 174
anchors CI itself reported (each failed/erroring node id paired with its
position in the `-q` progress output).

Method
------
`pyproject.toml` sets `testpaths = ["tests"]`, so pytest walks tests/ in sorted
order and, inside each file, takes module-level `test_*` functions in
definition order. Order is verified against the anchors, not assumed.

Test COUNT needs the arity of every `pytest.mark.parametrize`. A value's
identity never matters, only how many of them there are, so arity is computed
structurally instead of by evaluating the data:

    [a, b, c]                       -> 3      (element count)
    CONST                           -> len(CONST) when it is a literal container
    sorted(X) / list(X)             -> len(X)
    tuple(range(N))                 -> N
    [f(x) for x in X]               -> len(X)
    [(a, b) for a, b in X]          -> len(X)
    pytest.param(...) elements      -> counted like any other element
    <anything else>                 -> UNRESOLVED, contributes a floor of 1

Every site that could not be counted structurally is reported by name rather
than estimated. `--verify` then checks the reproduction against the anchors and
exits non-zero unless every one of them lands at the index CI reported.

Tied to one commit
------------------
The anchors describe the collection of ONE commit, and a reproduction from a
different commit is not a near miss to be tuned -- it is meaningless, and it
does not look like that. A test file added between the two commits shifts every
index after it by a constant, so nearly every anchor still matches and the run
reads as a handful of stragglers. Measured: against this repo's HEAD instead of
the anchors' commit, the result is 150 exact, 19 off by exactly +19, 5 absent,
where the 19 are one added file.

So `--sha` is REQUIRED to verify, and `anchors.json` records the commit it
describes. An unnamed tree is refused rather than silently compared. Note the
limit: `--sha` is asserted by the caller, so the tool cannot detect a run that
lies about its tree. It prevents the unnamed case, not the deliberate one.

For the same reason this script writes nothing unless `--out` is given. An
earlier version wrote `collection.json` beside itself, so a later run against a
different tree silently overwrote the earlier run's artifact, and the committed
one no longer matched the commit it was committed against.

Usage
-----
    python collection_order.py <tests_dir> --sha <commit> \\
        [--out collection.json] [--verify anchors.json] [--report]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys


class Unresolved(Exception):
    """The arity of this expression cannot be determined statically."""


# --- structural arity -----------------------------------------------------

def _sum_over_packed_values(node, consts):
    """Arity of a comprehension that flattens a dict's values.

    `[... for k, v in D.items() for x in v]` yields one element per value
    across every entry, so the count is `sum(len(v) for v in D.values())` --
    NOT the product `len(D) * something`, and not the value of any single
    axis. Returns None when the shape does not match, so the caller falls
    through to the generic product rule rather than guessing."""
    gens = node.generators
    if len(gens) != 2:
        return None
    first, second = gens
    if not isinstance(first.target, ast.Tuple):
        return None
    names = [n.id for n in first.target.elts]
    # The inner generator ranges over a value unpacked from the entry. Its
    # target need not repeat that name verbatim (`for k, v in D.items()
    # for x in v` is the common shape), so what matters is that it is a plain
    # name, not which name it is.
    if len(names) != 2 or not isinstance(second.target, ast.Name):
        return None
    # the first generator must iterate a resolved dict's items, possibly
    # wrapped in sorted(...) which does not change the set
    it = first.iter
    if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "sorted" \
       and len(it.args) == 1:
        it = it.args[0]
    base = it.func.value if (isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute)
                             and it.func.attr == "items") else it
    if not isinstance(base, ast.Name):
        return None
    entry = consts.get(base.id)
    if entry is None:
        return None
    kind, payload = entry
    if kind != "value" or not isinstance(payload, dict):
        return None
    try:
        return sum(len(v) for v in payload.values())
    except TypeError:
        return None


def arity(node, consts):
    """Number of argvalues a parametrize expression yields, or raise Unresolved."""
    # literal first: covers lists/tuples/sets/dicts and scalars alike
    try:
        v = ast.literal_eval(node)
    except Exception:
        pass
    else:
        try:
            return len(v)
        except TypeError:
            return 1

    # a name bound to a module-level constant, literal or measured structurally
    if isinstance(node, ast.Name):
        entry = consts.get(node.id)
        if entry is not None:
            kind, payload = entry
            return payload if kind == "struct" else arity(ast.Constant(payload), consts)
        # not defined here; it may be imported from another module
        external = _cross_module_arity(node, consts)
        if external is not None:
            return external
        raise Unresolved(f"name {node.id!r} is not a resolvable module constant")

    # a literal container holding non-literals: the element count is the arity
    # regardless of what each element evaluates to
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts)

    if isinstance(node, ast.Dict):
        # dict as argvalues -> pytest iterates keys
        return len(node.keys)

    # X.items() / X.values(): unpacks a resolved container, then delegate
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
       and node.func.attr in ("items", "keys", "values") and len(node.args) == 0:
        base = node.func.value
        if isinstance(base, ast.Name):
            entry = consts.get(base.id)
            if entry is not None:
                kind, payload = entry
                if kind == "struct":
                    return payload
                arity_of_base = arity(ast.Constant(payload), consts)
                if node.func.attr in ("items", "keys"):
                    return arity_of_base
                raise Unresolved(f"{base.id}.values() is not a sequence")
        external = _cross_module_arity(node, consts)
        if external is not None:
            return external
        raise Unresolved(f"{ast.unparse(base)[:40]}.{node.func.attr}() is not resolvable")

    # tuple(range(N)) / list(range(N))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
       and node.func.id in ("tuple", "list") and len(node.args) == 1:
        inner = node.args[0]
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) \
           and inner.func.id == "range":
            bounds = []
            for a in inner.args:
                try:
                    bounds.append(ast.literal_eval(a))
                except Exception:
                    raise Unresolved("range() bounds are not literals")
            if not bounds:
                return 0
            if len(bounds) == 1:
                return max(bounds[0], 0)
            if len(bounds) == 2:
                return max(bounds[1] - bounds[0], 0)
            return max(bounds[2] - bounds[0], 0) // max(bounds[1], 1)
        return arity(inner, consts)

    # sorted(X) / list(X) / tuple(X) / set(X): order and identity are irrelevant
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
       and node.func.id in ("sorted", "list", "tuple", "set") and len(node.args) == 1 \
       and not node.keywords:
        return arity(node.args[0], consts)

    # a comprehension over a resolvable literal: one generated test per element
    if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
        gens = node.generators
        external = _cross_module_arity(node, consts)
        if external is not None:
            return external
        if all(not g.ifs for g in gens):
            # Generators that range over a value unpacked from the previous
            # one (`for k, v in D.items() for v in v`) are not independent
            # axes: the arity is the SUM of the inner containers.
            summed = _sum_over_packed_values(node, consts)
            if summed is not None:
                return summed
            total = 1
            for g in gens:
                total *= arity(g.iter, consts)
            return total
        raise Unresolved("comprehension has a filter")

    # a comprehension over a cross-module constant, named with an attribute
    # (e.g. `[(mod, sym) for mod, syms in sorted(X.items()) for sym in syms]`)
    resolved = _cross_module_arity(node, consts)
    if resolved is not None:
        return resolved

    raise Unresolved(f"{type(node).__name__} expression: {ast.unparse(node)[:60]}")


# --- cross-module constants ----------------------------------------------
#
# A handful of parametrize sites take their arity from a name defined in
# another module. `external` maps "<module path>.<NAME>" to the arity, read by
# a human from that module's source and recorded here with the line that
# establishes it. Each entry below cites where the number came from.

EXTERNAL = {
    "channel.FROZEN_FIELDS": (
        6, "experiments/ad01/policy_action.py; tests/test_inv_x2_subscript_freeze.py:96 "
           "asserts len(channel.FROZEN_FIELDS) == 6"),
    "SUBSCRIPT_WRITES": (
        6, "a dict comprehension over channel.FROZEN_FIELDS, one entry per "
           "field; that test asserts len(channel.FROZEN_FIELDS) == 6 at line 96"),
    "ABSENT_SYMBOLS": (
        2, "experiments/ad01/s09_plan_claims.py:129, a literal 2-tuple of Citation"),
    "R.ACTIONS": (
        4, "settlement/representation.py, a literal 4-tuple of action names"),
    "world.BUDGET_LIMITS": (
        None, "settlement world.BUDGET_LIMITS -- not resolved, left UNRESOLVED"),
}

# Arity for a comprehension whose generator chain sums a container's parts.
# `[(mod, sym) for mod, syms in sorted(EXPECTED_ENTRY_POINTS.items()) for sym in syms]`
# is one test per symbol across every module, so the total is the sum of the
# inner containers' lengths. Recorded here with the count that establishes it.
COMPREHENSION_SUMS = {
    "EXPECTED_ENTRY_POINTS": (
        32, "tests/test_s09_merged_tip_regression.py:74, a dict of 9 modules "
            "holding 32 symbols in total"),
}


def _cross_module_arity(node, consts):
    """Arity of an expression whose length comes from another module.

    Handles the shapes this tree uses:
        sorted(MOD.NAME)                    -> len(MOD.NAME)
        sorted(MOD.NAME.items())            -> number of dict entries
        NAME                                -> EXTERNAL table
        [... for k, v in NAME.items() for v in v]   -> sum of inner lengths
    Returns None when nothing is known, so the caller reports UNRESOLVED."""
    if isinstance(node, ast.Name) and node.id in EXTERNAL \
       and EXTERNAL[node.id][0] is not None:
        return EXTERNAL[node.id][0]

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
       and node.func.attr in ("items", "keys") and isinstance(node.func.value, ast.Name):
        key = node.func.value.id
        if key in EXTERNAL and EXTERNAL[key][0] is not None:
            return EXTERNAL[key][0]

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sorted":
        arg = node.args[0]
        # sorted(MOD.NAME)
        if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
            key = f"{arg.value.id}.{arg.attr}"
            if key in EXTERNAL and EXTERNAL[key][0] is not None:
                return EXTERNAL[key][0]
        # sorted(NAME) / sorted(NAME.items())
        if isinstance(arg, ast.Name):
            if arg.id in EXTERNAL and EXTERNAL[arg.id][0] is not None:
                return EXTERNAL[arg.id][0]
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) \
           and arg.func.attr == "items" and isinstance(arg.func.value, ast.Name):
            key = arg.func.value.id
            if key in EXTERNAL and EXTERNAL[key][0] is not None:
                return EXTERNAL[key][0]

    if isinstance(node, ast.Attribute):
        key = f"{node.value.id}.{node.attr}" if isinstance(node.value, ast.Name) else None
        if key in EXTERNAL and EXTERNAL[key][0] is not None:
            return EXTERNAL[key][0]

    if isinstance(node, (ast.ListComp, ast.GeneratorExp)):
        gens = node.generators
        if len(gens) == 2:
            outer, inner = gens
            if isinstance(inner.iter, ast.Call) and isinstance(inner.iter.func, ast.Attribute) \
               and inner.iter.func.attr == "items" and isinstance(inner.iter.value, ast.Name):
                key = inner.iter.value.id
                if key in COMPREHENSION_SUMS:
                    return COMPREHENSION_SUMS[key][0]
            if isinstance(outer.iter, ast.Call) and isinstance(outer.iter.func, ast.Attribute) \
               and outer.iter.func.attr == "items" and isinstance(outer.iter.value, ast.Name):
                key = outer.iter.value.id
                if key in COMPREHENSION_SUMS:
                    return COMPREHENSION_SUMS[key][0]
    return None


# --- module constants -----------------------------------------------------

def module_constants(tree):
    """Name -> resolved arity (or value) for module-level assignments.

    Two passes, because a constant can be a literal CONTAINER whose ELEMENTS
    are not literals -- `{'named': '...' % NAME}` is the common shape here.
    `ast.literal_eval` rejects the whole container in that case, so it is
    measured structurally instead: a dict's arity is its key count, a
    list/tuple/set's is its element count, and what each element evaluates to
    never leaves this function."""
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
           and isinstance(node.targets[0], ast.Name):
            consts.setdefault(node.targets[0].id, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.value is not None:
            consts.setdefault(node.target.id, node.value)

    resolved = {}
    for name, value in consts.items():
        try:
            resolved[name] = ("value", ast.literal_eval(value))
            continue
        except Exception:
            pass
        # second chance: the container is literal in shape even if its
        # elements are not. This is the path that fixes a dict of
        # %-formatted strings.
        if isinstance(value, ast.Dict) and value.keys:
            if not any(k is None for k in value.keys):
                resolved[name] = ("struct", len(value.keys))
        elif isinstance(value, (ast.List, ast.Tuple, ast.Set)) and value.elts:
            resolved[name] = ("struct", len(value.elts))
    return resolved


# --- collection -----------------------------------------------------------

def parametrize_arity(dec, consts):
    """Arity contributed by one parametrize mark."""
    argvalues = None
    if len(dec.args) > 2:
        argvalues = dec.args[2]
    elif len(dec.args) > 1:
        argvalues = dec.args[1]
    else:
        argvalues = next((k.value for k in dec.keywords if k.arg == "argvalues"), None)
    if argvalues is None:
        raise Unresolved("parametrize has no argvalues")
    return arity(argvalues, consts)


def collect_file(path):
    """(count, unresolved, [(test_name, arity)]) for one file.

    `count` is exact when `unresolved` is empty. Otherwise it is a LOWER BOUND
    and every shortfall is named, so a caller can never mistake a floor for a
    measurement."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    consts = module_constants(tree)

    tests = []
    unresolved = []
    total = 0
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        n = 1
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "parametrize"):
                continue
            try:
                n *= parametrize_arity(dec, consts)
            except Unresolved as exc:
                unresolved.append(f"{node.name}: {exc}")
        tests.append((node.name, n))
        total += n
    return total, unresolved, tests


def collect(tests_dir):
    files = sorted(f for f in os.listdir(tests_dir)
                   if f.startswith("test_") and f.endswith(".py"))
    per_file = []
    order = []
    index = 0
    for f in files:
        n, unresolved, tests = collect_file(os.path.join(tests_dir, f))
        start = index
        # node ids repeat once per generated parameter
        for name, arity in tests:
            for k in range(arity):
                order.append({"index": index, "id": f"tests/{f}::{name}",
                              "param": k if arity > 1 else None})
                index += 1
        per_file.append({"file": f, "count": n, "start": start, "end": index,
                         "unresolved": unresolved})
    return {
        "count": index,
        "complete": all(not p["unresolved"] for p in per_file),
        "files": per_file,
        "nodes": order,
    }


# --- verification ---------------------------------------------------------

def verify(result, anchors_path, anchors_sha=None):
    """Check the reproduction against CI-reported anchors.

    Each anchor is (collection_index, node_id). A correct reproduction puts
    every one of them at exactly the index CI reported.

    The anchors describe ONE commit's collection. Verifying them against a
    different tree's collection is meaningless and, read carelessly, looks
    like a partial pass: a file added between the two commits shifts every
    index after it by a constant, so most anchors still land and the failure
    reads as "a few stragglers" rather than "wrong tree". So when the anchors
    record a commit and the caller names one, a mismatch is a hard error
    before any counting happens.
    """
    anchors_doc = json.load(open(anchors_path, encoding="utf-8"))
    if isinstance(anchors_doc, dict):
        anchors = anchors_doc["anchors"]
        anchors_sha = anchors_doc.get("sha")
    else:
        anchors = anchors_doc

    # A wrong tree does not fail loudly. It shifts every index after the
    # differing file by a constant, so most anchors still land and the run
    # reads as a near miss rather than as the category error it is. So
    # verifying without naming the commit is refused outright.
    if anchors_sha and not result.get("sha"):
        print("REFUSING TO VERIFY: the anchors record the commit they describe "
              f"({anchors_sha[:12]}), but this run did not name one. Pass --sha "
              "so a mismatch is caught instead of being read as stragglers.")
        return False
    if anchors_sha and result.get("sha") and anchors_sha != result["sha"]:
        print(f"REFUSING TO VERIFY: anchors are for {anchors_sha[:12]}, "
              f"this collection is from {result['sha'][:12]}")
        return False

    by_id = {}
    for node in result["nodes"]:
        by_id.setdefault(node["id"], []).append(node["index"])
    hits, misses, unmatched = 0, [], []
    for idx, node_id in anchors:
        # pytest appends a parametrised node id's "[param-id]" with NO space
        # before the bracket, so the suffix is stripped at the bracket itself.
        base = node_id.split("[")[0]
        if base in by_id:
            if idx in by_id[base]:
                hits += 1
            else:
                misses.append((idx, node_id, min(by_id[base]), max(by_id[base])))
        else:
            unmatched.append((idx, node_id))
    print(f"anchors:              {len(anchors)}")
    print(f"exact index match:    {hits}")
    print(f"matched but wrong idx:{len(misses)}")
    print(f"node id not in repro: {len(unmatched)}")
    for idx, node_id, lo, hi in misses[:15]:
        print(f"   anchor {idx:5d}  repro says [{lo}..{hi}]  {node_id}")
    for idx, node_id in unmatched[:10]:
        print(f"   anchor {idx:5d}  UNMATCHED  {node_id}")
    return hits == len(anchors)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tests_dir")
    ap.add_argument("--verify", metavar="ANCHORS_JSON")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", metavar="PATH",
                    help="where to write the reproduction. Defaults to stdout only.")
    ap.add_argument("--sha", metavar="HEX",
                    help="the commit the tests_dir was checked out from, recorded in "
                         "the output. The anchors below belong to one specific commit, "
                         "so an unrecorded run cannot be told apart from a wrong one.")
    args = ap.parse_args()

    result = collect(args.tests_dir)
    result["tests_dir"] = os.path.abspath(args.tests_dir)
    result["sha"] = args.sha or None

    dest = args.out
    if dest:
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(result, fh)

    unresolved = [p for p in result["files"] if p["unresolved"]]
    print(f"tests_dir:            {result['tests_dir']}")
    print(f"sha:                  {result['sha'] or '(not recorded -- pass --sha)'}")
    print(f"files collected:      {len(result['files'])}")
    print(f"tests reproduced:     {result['count']}")
    print(f"complete:             {result['complete']}")
    print(f"files with shortfall: {len(unresolved)}")
    for p in unresolved:
        print(f"   {p['file']} (index {p['start']}..{p['end']})")
        for u in p["unresolved"]:
            print(f"      {u}")
    if dest:
        print(f"written:              {dest}")
    else:
        print("written:              (nothing; pass --out to write a file)")

    if args.report:
        for p in result["files"]:
            if p["count"] or p["unresolved"]:
                flag = "" if not p["unresolved"] else f"  <{len(p['unresolved'])} SHORTFALL>"
                print(f"  {p['end']:6d}  +{p['count']:4d}  {p['file']}{flag}")

    if args.verify:
        print()
        ok = verify(result, args.verify)
        print()
        print("VERIFIED" if ok else "NOT VERIFIED")
        return 0 if ok else 1
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
