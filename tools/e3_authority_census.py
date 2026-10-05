"""Census of every call site that can reach an improve round.

Answers: how many sites drive an improve round, and which carry an
authority. Run from the repo root. Excludes .worktrees/ so a sibling
lane's copy of the tree is never counted.

    python tools/e3_authority_census.py [--json]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

# Entry points that can reach `drive_improve_round`. Each is a function
# whose body calls another entry point, so the census walks a call graph
# rather than a single function name.
ENTRY_POINTS = {
    "drive_improve_round",
    "run_improve_step",
    "run_operate_step",
    "fresh_round",
    "run_live_improve_round",
    "bind_live_revision",
    "bind_retained_acquisition",
    "adopt_live_revision",
    "retain_acquired",
}

# Names that carry an authority, at any call position.
AUTHORITY_KEYWORDS = {"authority"}

SKIP_DIRS = {".git", ".worktrees", "__pycache__", ".venv", "node_modules",
             ".a53-base", ".a53-ci", ".a53-ci2", ".a53-prev", "reports",
             "evidence", "evidence-ad01", "evidence-live"}


def repo_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def call_sites(tree, names):
    """Yield (lineno, funcname, keywords, is_await) for calls to `names`."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            yield (node.lineno, func.id,
                   {kw.arg for kw in node.keywords if kw.arg},
                   isinstance(node.func, ast.Attribute))
        elif isinstance(func, ast.Attribute) and func.attr in names:
            yield (node.lineno, func.attr,
                   {kw.arg for kw in node.keywords if kw.arg},
                   True)


def definitions(tree, names):
    """Yield (lineno, funcname) for defs of `names`, module level and nested."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name in names:
            yield (node.lineno, node.name)


def signature_authority(tree, name):
    """Does `name` itself accept an authority keyword?"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            args = node.args
            for arg in list(args.args) + list(args.kwonlyargs) \
                    + list(args.posonlyargs):
                if arg.arg in AUTHORITY_KEYWORDS:
                    return True
            return False
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    definitions_by_file = {}
    calls = []
    signatures = {}
    for path in sorted(repo_files(root)):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, root)
        found = list(definitions(tree, ENTRY_POINTS))
        if found:
            definitions_by_file[rel] = sorted(found)
        for name in ENTRY_POINTS:
            sig = signature_authority(tree, name)
            if sig is not None:
                signatures[name] = sig
        for lineno, func, keywords, is_attr in call_sites(tree, ENTRY_POINTS):
            calls.append({
                "file": rel,
                "line": lineno,
                "function": func,
                "authority": bool(keywords & AUTHORITY_KEYWORDS),
                "keywords": sorted(keywords),
                "method_call": is_attr,
            })

    rows = sorted(calls, key=lambda r: (r["file"], r["line"]))
    carriers = [r for r in rows if r["authority"]]
    bare = [r for r in rows if not r["authority"]]

    report = {
        "root": root,
        "total_call_sites": len(rows),
        "carry_authority": len(carriers),
        "no_authority": len(bare),
        "signatures_accept_authority": signatures,
        "definitions": definitions_by_file,
        "call_sites": rows,
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("root: %s" % root)
    print("call sites: %d  (authority: %d, none: %d)" % (
        len(rows), len(carriers), len(bare)))
    print("definitions of entry points:")
    for path, found in sorted(definitions_by_file.items()):
        for lineno, name in found:
            print("  %s:%d  def %s  authority=%s" % (
                path, lineno, name, signatures.get(name)))
    print("call sites (C=carries authority, -=does not):")
    for row in rows:
        print("  %s %s:%d  %s(%s)" % (
            "C" if row["authority"] else "-",
            row["file"], row["line"], row["function"],
            ", ".join(row["keywords"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())