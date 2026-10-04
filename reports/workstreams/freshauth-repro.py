"""What this lane measured, and what it could not.

Three sections, each rerunnable on a host with no PostgreSQL and no WSL,
because nothing here reaches either. Run it with the repo venv:

    D:\\AI\\Agent-Society-v2\\.venv\\Scripts\\python.exe \\
        reports/workstreams/freshauth-repro.py

1. `fresh_round` on an owned store, before and after the threading. The refusal
   is decided at the top of `drive_improve_round`, so it needs no SQL; a round
   that gets past it then tries to reach a ledger and fails on the absent
   server, which is why "no refusal" and "reached the executor" are different
   lines below.
2. The call-site census: every caller of the three improve-round entry points,
   whether it passes an authority, and which of them run on a store that
   records an owner.
3. The three doubles in `tests/test_a55_continuation_owner.py` that this lane's
   edit turns from green to red. That file is not this lane's, so the breakage
   is measured here and reported rather than repaired.

There is no "expected output" section. Section 1 changes with the edit and
section 3 changes with it too; read the lines, do not compare them.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import live_mission  # noqa: E402
from experiments.ad01 import frontier  # noqa: E402
from experiments.ad01 import improve_channel as channel  # noqa: E402
from experiments.ad01 import live_construct as live  # noqa: E402

MISSION = live_mission(
    live.LIVE_MISSION_OBJECTIVE,
    [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}])
DSN = "dbname=freshauth-repro"
CALLS = ("drive_improve_round", "run_operate_step", "run_live_improve_round")
OWNING_CONSTRUCTORS = ("create_store", "ensure_live_store", "FrontierStore")


# ------------------------------------------------- 1. fresh_round, both ways


def _store(path: pathlib.Path, *, owned: bool):
    identity = frontier.StoreIdentity(
        investigation_id="freshauth-owned", dsn=DSN) if owned else None
    frontier.create_store(
        path, namespace=frontier.NAMESPACE, mission=MISSION,
        authority=dict(live.LIVE_AUTHORITY), identity=identity)
    store = frontier.FrontierStore(path, identity=identity)
    live.bind_live_control(store, "low")
    store.save()
    return path


def _fresh_round(path: pathlib.Path, **kwargs) -> str:
    try:
        summary = channel.fresh_round(path, 2, **kwargs)
    except frontier.Refused as exc:
        return "Refused: %s" % exc
    except Exception as exc:
        first = str(exc).splitlines()[0]
        if "is bad" in first or "connection" in first.lower():
            return ("reached the executor, then found no PostgreSQL"
                    " (%s)" % type(exc).__name__)
        return "%s: %s" % (type(exc).__name__, first)
    return "returned a summary (round %s)" % summary["round"]


def section_one() -> None:
    print("=" * 72)
    print("1. fresh_round on an owned store")
    print("=" * 72)
    with tempfile.TemporaryDirectory() as raw:
        tmp = pathlib.Path(raw)
        owned = _store(tmp / "owned.json", owned=True)
        print("  no allocation, store owns itself")
        print("    %s" % _fresh_round(owned, dsn=DSN,
                                     investigation_id="freshauth-owned"))
        print("  allocation supplied")
        print("    %s" % _fresh_round(owned, dsn=DSN,
                                     investigation_id="freshauth-owned",
                                     allocation_id="freshauth-alloc"))
        print("  allocation without a dsn")
        print("    %s" % _fresh_round(owned, investigation_id=None,
                                     allocation_id="freshauth-alloc"))
        print("  nameless store, no allocation (the fixture boundary)")
        print("    %s" % _fresh_round(_store(tmp / "n.json", owned=False)))


# ------------------------------------------------------ 2. the call census


def _sources() -> list[pathlib.Path]:
    out = []
    for area in ("experiments", "scripts", "tests"):
        for path in sorted((ROOT / area).rglob("*.py")):
            if "worktrees" in path.parts or "_heavy_archived" in path.parts:
                continue
            out.append(path)
    return out


def section_two() -> None:
    print()
    print("=" * 72)
    print("2. every improve-round call site")
    print("=" * 72)
    rows = []
    for path in _sources():
        rel = path.relative_to(ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(
                node.func, "id", None)
            if name not in CALLS:
                continue
            keys = {k.arg for k in node.keywords}
            rows.append((str(rel), node.lineno, name,
                         "YES" if "authority" in keys else "-",
                         "-" if any(k.arg is None for k in node.keywords)
                         else "no"))
    width = max(len(r[0]) for r in rows)
    print("  %-*s %-6s %-22s %-9s %s"
          % (width, "file", "line", "call", "authority", "splat"))
    for rel, lineno, name, authority, splat in sorted(rows):
        print("  %-*s %-6d %-22s %-9s %s"
              % (width, rel, lineno, name, authority, splat))
    print()
    print("  A site with no authority refuses only when its store names an")
    print("  owner. These are the constructions that record one:")
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(
                node.func, "id", None)
            if name not in OWNING_CONSTRUCTORS:
                continue
            keys = {k.arg for k in node.keywords}
            if {"dsn", "identity"} & keys:
                print("    %s:%d  %s" % (path.relative_to(ROOT), node.lineno,
                                         name))


# -------------------------------------------- 3. the doubles this lane broke


def section_three() -> None:
    print()
    print("=" * 72)
    print("3. test_a55_continuation_owner.py doubles, measured")
    print("=" * 72)
    path = ROOT / "tests/test_a55_continuation_owner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    linenos = sorted(
        node.lineno for node in ast.walk(tree)
        if (isinstance(node, ast.Call)
            and getattr(node.func, "attr", None) == "setattr"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "drive_improve_round"))
    real = channel.drive_improve_round

    def double(store, task, round_no, admit_probes=False):
        return {"candidate": {"control_id": "cand",
                              "parent_digest": "p" * 64,
                              "imp_digest": "i" * 64}}

    try:
        channel.drive_improve_round = double
        for lineno in linenos:
            with tempfile.TemporaryDirectory() as raw:
                made = _store(pathlib.Path(raw) / "n.json", owned=False)
                print("  a55:%-5d %s" % (lineno, _fresh_round(made)))
    finally:
        channel.drive_improve_round = real
    print()
    print("  These name only store, task, round_no and admit_probes, so the")
    print("  keyword fresh_round now sends reaches them as a TypeError. Each")
    print("  reads OK at fb4e868, measured by running this file again with")
    print("  improve_channel.py restored from that commit. Repair is one")
    print("  keyword per lambda and belongs to that file's owner.")


def main() -> int:
    section_one()
    section_two()
    section_three()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())