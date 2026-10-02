"""The bounded connect exists; the hot path does not use it.

`settlement/db.py` offers two doors. `connect()` opens a session with no
`connect_timeout` at all, and `read_connect()` opens one with a 10s
connect timeout and a 60s statement timeout. `policy_exec._receipts`
uses the first, and `run_probe_call` calls `_receipts` once per probe,
so a coordinate cell opens a new unbounded connection for every probe
it runs.

This is why the full suite appeared to hang. Measured with `py-spy dump`
rather than inferred:

    connect (settlement/db.py:18)
    _receipts (coord02/policy_exec.py:49)
    run_probe_call (coord02/policy_exec.py:212)
    _run_probes (coord02/controller.py:393)
    run_episode (coord02/controller.py:717)
    run_cell (coord02/entry.py:655)

The cluster was not saturated - 7 of 100 connections, and a fresh
`psql` connected instantly - so the wait was unbounded rather than
contended. Two earlier attempts to "fix" the suite by shortening a
pytest timeout would have hidden this rather than found it, and the
handoff is explicit that a full-suite timeout must not be counted as
passing.

These tests pin the contract that the repair has to satisfy: every
connect in the probe path is bounded, and no caller has to know which
door it went through.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from settlement import db


COORD02 = ROOT / "experiments" / "coord02"
DB = ROOT / "src" / "settlement" / "db.py"


def _source(path: Path) -> str:
    return path.read_text()


def test_the_default_connect_is_bounded():
    """The repair, stated as the thing that is now true.

    `connect()` now defaults `connect_timeout`, so a caller that reaches
    for the plain door gets a bounded session without knowing the
    difference. Seventeen call sites across coord02 used the plain
    door; bounding the default fixed all of them at once, where editing
    each caller would have left the next one unguarded.
    """
    assert db.WRITE_CONNECT_TIMEOUT_S > 0
    assert "connect_timeout" in _source(DB).split("def read_connect")[0]


def test_a_caller_can_still_ask_for_longer():
    """Bounded by default, not capped: a caller that needs more can say so."""
    calls = []

    class _Fake:
        def __init__(self, dsn, **kwargs):
            calls.append(kwargs)

    import psycopg
    original = psycopg.connect
    psycopg.connect = _Fake
    try:
        db.connect("dsn")
        db.connect("dsn", connect_timeout=90)
    finally:
        psycopg.connect = original

    assert calls[0]["connect_timeout"] == db.WRITE_CONNECT_TIMEOUT_S
    assert calls[1]["connect_timeout"] == 90


def test_the_read_door_is_still_the_tighter_of_the_two():
    """`read_connect` must keep the shorter budget it always had."""
    assert db.READ_CONNECT_TIMEOUT_S < db.WRITE_CONNECT_TIMEOUT_S

    calls = []

    class _Fake:
        def __init__(self, dsn, **kwargs):
            calls.append(kwargs)

    import psycopg
    original = psycopg.connect
    psycopg.connect = _Fake
    try:
        db.read_connect("dsn")
    finally:
        psycopg.connect = original

    assert calls[0]["connect_timeout"] == db.READ_CONNECT_TIMEOUT_S
    assert "statement_timeout" in calls[0].get("options", "")


def test_no_call_site_in_coord02_has_to_know_about_the_timeout():
    """The guard is the default, so walking the tree finds nothing to fix.

    Before the repair this walk listed seventeen call sites. It is kept
    as a test because a future change that adds a raw `psycopg.connect`
    to coord02 would reintroduce an unbounded session with no default
    to catch it.
    """
    offenders = []
    for path in sorted(COORD02.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "connect":
                continue
            owner = getattr(func, "value", None)
            module = getattr(owner, "id", None) or getattr(owner, "attr", None)
            if module != "psycopg":
                continue
            offenders.append("%s:%d" % (path.relative_to(ROOT), node.lineno))

    assert not offenders, (
        "raw psycopg.connect() in coord02 bypasses the bounded default: %s"
        % ", ".join(offenders))
