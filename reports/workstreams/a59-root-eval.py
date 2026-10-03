"""Resolve every repo-root derivation in the archived tests, for real.

Each derivation site is recovered from the AST and evaluated with __file__
bound to the file it appears in, so the answer is the path the test will
actually use rather than a reimplementation of pathlib here.

Exits nonzero if any derivation rooted at this file's own __file__ fails to
land on the repository root, which is the invariant the archived tree needs
and does not have. Scoped to tests/_heavy_archived by construction: one level
up, at tests/*.py, `parent.parent` is correct and `parents[2]` would be wrong.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path


def find_repo():
    """The checkout root, located by the tree this guards rather than by where
    this script sits. Deriving it from __file__ is only correct while the
    script lives at the root; from reports/workstreams/ it pointed at a
    directory with no tests/ and reported a green zero derivations."""
    here = Path(__file__).resolve()
    for base in (Path.cwd(), *here.parents):
        if (base / "tests" / "_heavy_archived").is_dir():
            return base
    raise SystemExit(f"no tests/_heavy_archived above {here} or under cwd")


REPO = find_repo()
HEAVY = REPO / "tests" / "_heavy_archived"


def sites(tree):
    """Yield (lineno, expr) for every Path(<own __file__ ...>) chain."""
    parent = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Path" and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id == "__file__":
            own = True
        elif (isinstance(arg, ast.Attribute) and arg.attr == "__file__"
              and isinstance(arg.value, ast.Name) and arg.value.id == "__file__"):
            own = True
        else:
            own = False
        if not own:
            continue
        top = node
        while True:
            nxt = parent.get(top)
            if isinstance(nxt, (ast.Attribute, ast.Subscript)):
                top = nxt
            elif (isinstance(nxt, ast.Call) and nxt.func is top
                  and getattr(top, "attr", None) == "resolve"):
                top = nxt
            else:
                break
        yield node.lineno, ast.unparse(top)


def main():
    rows = []
    files = sorted(HEAVY.glob("test_*.py"))
    for f in files:
        for lineno, expr in sites(ast.parse(f.read_text(encoding="utf-8"))):
            got = eval(expr, {"__file__": str(f), "Path": Path})
            rows.append({"file": f.name, "line": lineno, "expr": expr,
                         "resolves_to": str(got), "name": got.name,
                         "is_repo_root": got == REPO})
    bad = [r for r in rows if not r["is_repo_root"]]
    print(f"archived files scanned            : {len(files)}")
    print(f"own-__file__ derivations evaluated : {len(rows)}")
    print(f"landing on the repository root     : {len(rows) - len(bad)}")
    print(f"landing somewhere else             : {len(bad)}")
    print(f"distinct files affected            : {len({r['file'] for r in bad})}")
    for r in bad:
        print(f"  NOT ROOT {r['file']}:{r['line']}  {r['expr']}  -> {r['name']}")
    out = REPO / "reports" / "workstreams" / "a59-derivations.json"
    json.dump(rows, open(out, "w"), indent=1)
    print(f"wrote {out}")
    if not files:
        print("FAIL: no archived files scanned; a green run that examined nothing")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())