"""Census improve-round call sites and their authority threading.

Derives, in one command, the numbers a fix depends on:

  * every call site of `drive_improve_round`, `bind_retained_acquisition` and
    `run_live_improve_round` across tests, experiments, scripts and src;
  * how many name `authority=` and how many omit it;
  * of the sites that omit it, how many drive an OWNED store, which is the only
    shape the execution-authority refusal actually fires on.

Run from the repository root:

    python tools/census_improve_round_authority.py
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = ("drive_improve_round", "bind_retained_acquisition",
           "run_live_improve_round", "run_improve_step", "run_operate_step")

SEARCH_TREES = ("tests", "experiments", "scripts", "src")


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _keywords(node: ast.Call) -> set[str]:
    return {kw.arg for kw in node.keywords if kw.arg}


def _creates_owned_store(node: ast.Call) -> bool:
    """Does this call build a store that names an owner?

    An owned store is one created with an `identity=`, which is what
    `drive_improve_round` refuses when no authority is supplied.
    """
    return _call_name(node) in {"create_store", "FrontierStore"} \
        and "identity" in _keywords(node)


def _module_owned_names(tree: ast.Module) -> set[str]:
    """Names bound, in this module, to an owned store.

    Ownership does not arrive at the round on the same expression. A helper
    builds the store, returns it, and the test passes the name onward, so a
    walk that only inspects the call's own arguments finds nothing. This
    follows the assignment, and follows a helper's own return statement into
    the helper body, so a store built in one function and driven in another is
    still recognised as owned.
    """
    owned: set[str] = set()
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}
    returning_owned: set[str] = set()

    def value_is_owned(value: ast.expr, depth: int = 0) -> bool:
        if depth > 4:
            return False
        if isinstance(value, ast.Call):
            return _creates_owned_store(value)
        if isinstance(value, ast.Name):
            return value.id in owned
        if isinstance(value, ast.IfExp):
            return value_is_owned(value.body, depth + 1) \
                or value_is_owned(value.orelse, depth + 1)
        if isinstance(value, ast.Tuple):
            return any(value_is_owned(item, depth + 1) for item in value.elts)
        if isinstance(value, (ast.List, ast.Set)):
            return any(value_is_owned(item, depth + 1) for item in value.elts)
        return False

    def call_returns_owned(call, depth: int = 0) -> bool:
        if depth > 4 or not isinstance(call, ast.Call) \
                or not isinstance(call.func, ast.Name):
            return False
        target = functions.get(call.func.id)
        if target is None:
            return False
        if call.func.id in returning_owned:
            return True
        for node in ast.walk(target):
            if isinstance(node, ast.Return) and node.value is not None:
                if value_is_owned(node.value, depth + 1):
                    returning_owned.add(call.func.id)
                    return True
        return False

    # Two passes: the first settles which helpers hand back an owned store,
    # the second binds names. A helper that returns an owned store can only be
    # recognised once the names it returns are known, so the fixpoint is
    # reached by repeating until nothing new is learned.
    for _ in range(4):
        grew = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [t for t in node.targets if isinstance(t, ast.Name)]
                if not targets:
                    continue
                if value_is_owned(node.value) or call_returns_owned(node.value):
                    for target in targets:
                        if target.id not in owned:
                            owned.add(target.id)
                            grew = True
        if not grew:
            break
    return owned


def _drives_owned_store(node: ast.Call, owned: set[str]) -> bool:
    """Does this call hand the round a store that names an owner?

    Ownership arrives in two different shapes, so the check is per target
    rather than one rule for all of them.

    `bind_retained_acquisition` names no store object. It opens one itself,
    and it opens an OWNED one exactly when it is given both halves of an
    identity: `_open_owned_store` builds a `FrontierStore` with
    `identity=_live_identity(dsn, investigation_id)`, and that helper refuses
    half an identity. So naming `dsn=` and `investigation_id=` together is
    what makes the store owned, whether or not the caller ever held it.

    The three round drivers take the store as an argument, so ownership is a
    property of the object passed in, resolved through this module's
    assignments.
    """
    keywords = _keywords(node)
    if _call_name(node) == "bind_retained_acquisition":
        return {"dsn", "investigation_id"} <= keywords
    for argument in list(node.args) + [kw.value for kw in node.keywords]:
        if isinstance(argument, ast.Name) and argument.id in owned:
            return True
        if isinstance(argument, ast.Call) and _creates_owned_store(argument):
            return True
    return False


def _source_of(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _tree_of(path: Path):
    text = _source_of(path)
    if text is None:
        return None
    try:
        return text, ast.parse(text)
    except SyntaxError:
        return None


def census() -> list[dict]:
    rows: list[dict] = []
    for tree_name in SEARCH_TREES:
        base = ROOT / tree_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = path.relative_to(ROOT).parts
            if any(part.startswith(".") for part in parts):
                continue
            parsed = _tree_of(path)
            if parsed is None:
                continue
            _, tree = parsed
            owned_names = _module_owned_names(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node)
                if name not in TARGETS:
                    continue
                keywords = {kw.arg for kw in node.keywords if kw.arg}
                rows.append({
                    "target": name,
                    "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": node.lineno,
                    "names_authority": "authority" in keywords,
                    "constructs_owned_store": _drives_owned_store(
                        node, owned_names),
                })
    return rows


def main() -> None:
    rows = census()
    print("call sites per target (authority= named vs omitted)")
    for target in TARGETS:
        subset = [row for row in rows if row["target"] == target]
        named = sum(1 for row in subset if row["names_authority"])
        print("  %-28s total=%-3d named=%-3d omitted=%d"
              % (target, len(subset), named, len(subset) - named))
    named_all = sum(1 for row in rows if row["names_authority"])
    print("  %-28s total=%-3d named=%-3d omitted=%d"
          % ("ALL", len(rows), named_all, len(rows) - named_all))

    omitting = [row for row in rows if not row["names_authority"]]
    owned = [row for row in omitting if row["constructs_owned_store"]]
    print("\nof the %d sites omitting authority=, %d construct an owned store"
          % (len(omitting), len(owned)))
    print("owned sites (the refusal fires here):")
    for row in sorted(owned, key=lambda r: (r["file"], r["line"])):
        print("  %s:%d  %s" % (row["file"], row["line"], row["target"]))

    print("\nomitting sites per file and target:")
    counts = Counter((row["file"], row["target"]) for row in omitting)
    for (name, target), count in sorted(counts.items()):
        print("  %-52s %-28s x%d" % (name, target, count))

    print("\nWHAT THIS CENSUS CANNOT SEE")
    print("  It resolves ownership within one file, so it reports 0 for a")
    print("  caller that builds its store in another module. The live path in")
    print("  `scripts/invl02_live.py` is exactly that shape:")
    print("  `_run_frontier_investigation` opens an OWNED store via")
    print("  `ensure_live_store(dsn=, investigation_id=)` and then reaches")
    print("  `run_live_improve_round` with `authority=_study_authority(dsn,")
    print("  allocation_id)`, which is None when the caller supplies no")
    print("  allocation. Two tests in tests/test_r123_gates.py call it that")
    print("  way and fail on the execution-authority refusal.")
    print("  For a cross-module census, read the CI log for the refusal")
    print("  string rather than trusting this count of 0.")


if __name__ == "__main__":
    main()
