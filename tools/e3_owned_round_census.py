"""Census of call sites that can reach an improve round, split by whether
the store they reach is owned.

`drive_improve_round` refuses an *owned* store that names no authority, and
gives a nameless store a disposable one. So "does this call site pass
authority?" is only half the question: a site that omits authority and drives
a nameless store is fine, and a site that omits it and drives an owned store
is the refusal. This script reports both halves.

Store ownership is read statically, from the construction sites: a store is
owned when `create_store` or `FrontierStore` receives an `identity=` (or a
positional identity), and nameless when it does not. Where a site's store
comes from a parameter or a helper it cannot see, the row is reported as
`unknown` rather than guessed.

Run from the repo root:
    python tools/e3_owned_round_census.py
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

# Only entry points that can actually drive an improve round. `retain_acquired`
# and `adopt_live_revision` are excluded: neither runs one, and counting them
# inflates the figure with sites that cannot hit this refusal.
ROUND_ENTRY_POINTS = {
    "drive_improve_round",
    "run_improve_step",
    "run_live_improve_round",
    "fresh_round",
    "bind_live_revision",
    "bind_retained_acquisition",
}

STORE_BUILDERS = {"create_store", "FrontierStore"}

SKIP_DIRS = {".git", ".worktrees", "__pycache__", ".venv", "node_modules",
             "reports", "evidence", "evidence-ad01", "evidence-live",
             "evidence_inv01_live", "evidence_s09_live_opus",
             "evidence_s09_m3_live", "evidence_s09_route_probe",
             "evidence_s09pilot"}


def repo_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def ownership(call: ast.Call):
    """Owned / nameless / unknown for a store-builder call."""
    for kw in call.keywords:
        if kw.arg == "identity":
            node = kw.value
            if isinstance(node, ast.Constant) and node.value is None:
                return "nameless"
            if isinstance(node, ast.Name) and node.id == "None":
                return "nameless"
            return "owned"
    func = call.func
    name = getattr(func, "id", None) or getattr(func, "attr", None)
    if name == "FrontierStore" and len(call.args) >= 2:
        return "owned" if not isinstance(call.args[1], ast.Constant) \
            else ("nameless" if call.args[1].value is None else "owned")
    if name == "create_store":
        return "nameless"     # identity is keyword-only and absent
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    rows = []
    stores = {}
    for path in repo_files(root):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, root)

        # Store construction sites in this file, with their ownership.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or \
                    getattr(node.func, "attr", None)
                if name in STORE_BUILDERS:
                    stores.setdefault(rel, []).append(
                        {"line": node.lineno, "builder": name,
                         "ownership": ownership(node)})

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or \
                getattr(node.func, "attr", None)
            if name not in ROUND_ENTRY_POINTS:
                continue
            keywords = sorted({kw.arg for kw in node.keywords if kw.arg})
            rows.append({
                "file": rel,
                "line": node.lineno,
                "callee": name,
                "carries_authority": "authority" in keywords,
                "keywords": keywords,
            })

    rows.sort(key=lambda r: (r["file"], r["line"]))
    report = {"root": root, "round_call_sites": rows,
              "store_construction": stores}

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    bare = [r for r in rows if not r["carries_authority"]]
    carried = [r for r in rows if r["carries_authority"]]
    print("improve-round call sites: %d  (carries authority: %d, omits: %d)"
          % (len(rows), len(carried), len(bare)))
    print()
    print("=== CARRIES AUTHORITY (%d) ===" % len(carried))
    for r in carried:
        print("  %s:%d  %s(%s)" % (r["file"], r["line"], r["callee"],
                                   ", ".join(r["keywords"])))
    print()
    print("=== OMITS AUTHORITY (%d) ===" % len(bare))
    for r in bare:
        print("  %s:%d  %s(%s)" % (r["file"], r["line"], r["callee"],
                                   ", ".join(r["keywords"])))
    print()
    print("=== STORE CONSTRUCTION BY OWNERSHIP ===")
    owned = sum(1 for entries in stores.values() for e in entries
                if e["ownership"] == "owned")
    nameless = sum(1 for entries in stores.values() for e in entries
                   if e["ownership"] == "nameless")
    print("  owned: %d   nameless: %d" % (owned, nameless))
    for rel in sorted(stores):
        entries = stores[rel]
        kinds = {e["ownership"] for e in entries}
        if "owned" in kinds:
            print("  OWNED  %s  %s" % (rel, [
                "%d:%s" % (e["line"], e["ownership"]) for e in entries]))
    return 0


if __name__ == "__main__":
    sys.exit(main())