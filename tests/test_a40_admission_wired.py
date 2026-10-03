"""The live decision path admits its operations.

`trajectory.accept_action` had no production caller, and neither did
`mission.admit_operation`, so `investigations.in_flight` was never written
outside `tests/`. A live campaign and a real resume both left that column
empty: the decision was durable in `s09_policy_state`, the effect ran, the
row was incorporated, and nothing in between said the work was owed. Every
archived campaign reflects that -- 82 episodes across 28 campaign documents,
0 of them carrying `ran_under`, which is written only when an operation was
held.

The seam is the line in `_run_boundary` immediately after `record_decision`
makes the decision durable. It is not `_s09_accept` and not
`_s09_incorporate`. `_s09_accept` records the decision and is also reached by
a policy step whose boundary never runs; `_s09_incorporate` is reached once
the effect exists, so an identity recorded there is missing exactly when the
effect has not run. The seam is the single line every admitted boundary
passes on its way to an effect and a crash can interrupt there.

These tests drive `run_campaign` and kill it at that line, in a second
interpreter, so nothing but the database crosses the restart. The point is
not that a predicate returns the right answer -- `mission.is_quiescent` and
`admit_operation` both already had that -- but that production enters the
window at all.

Both directions are pinned. A campaign killed in the window must leave a
non-empty `in_flight`, and a campaign that finishes must leave it empty: a
wiring that always holds satisfies only the first, and one that never holds
satisfies only the second.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a40admit"

CHARTER = {"objective": "hold the operation this boundary decided",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20}
DEV_TASK = "ad01-w0-dev-sw-01"

# The two seed programs that run a development boundary on this task and
# produce a *different* candidate, so a substituted program is behavioural
# rather than a field disagreement. Measured on this task; on
# `ad01-w0-dev-sw-00` the two agree exactly and a substitution there would be
# undetectable, which is why the task is named rather than defaulted.
ADMITTED_PROGRAM = "seed-sw-greedy"
SUBSTITUTED_PROGRAM = "seed-sw-ddmin"


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


def _cid(seq: int) -> str:
    from experiments.ad01 import trajectory

    trajectory.set_namespace_token("")
    return trajectory.campaign_id(0, "I", seq)


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s" % (ROOT, ROOT / "src")
    return env


def _run_phase(source: str, *args: str) -> str:
    done = subprocess.run([sys.executable, "-c", source, *args],
                          cwd=str(ROOT), env=_env(), capture_output=True,
                          text=True, timeout=600)
    assert done.returncode == 0, (
        "the phase failed: %s" % (done.stderr or done.stdout))
    return done.stdout


def _in_flight_raw(store: str, cid: str) -> list:
    """The column itself, not this lane's reading of it.

    `read_in_flight` parses through `InFlightOperation.from_json`, which
    raises on a status it does not know. Reading the column is what makes a
    claim about the row rather than about the reader, and it is the only way
    an empty-but-malformed entry would show up as empty.
    """
    from experiments.ad01 import mission

    with mission.connect(store) as conn:
        row = conn.execute(
            "SELECT in_flight FROM investigations WHERE id = %s",
            (cid,)).fetchone()
        conn.commit()
    assert row is not None, "the campaign admitted no investigation row"
    return list(row["in_flight"] or [])


def _effect_record(store: str, cid: str, seq: int = 0) -> dict | None:
    from experiments.ad01 import trajectory

    with trajectory._read_conn(store) as conn:
        row = conn.execute(
            "SELECT effect_record FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = %s",
            (cid, seq)).fetchone()
        conn.commit()
    return None if row is None else row["effect_record"]


def _s09_row(store: str, cid: str, seq: int = 0):
    from experiments.ad01 import trajectory

    return trajectory._s09_get(store, cid, seq)


# The crash point is the admission itself: the boundary decides, the decision
# is durable, the operation is held, and the process dies before the effect.
# Patching the admission to exit makes the window exact rather than
# approximate, and exiting means nothing unwinds -- no release, no
# incorporation, no finally.
_DIE_AT_ADMISSION = (
    "import os, sys\n"
    "from experiments.ad01 import trajectory, mission\n"
    "dsn, cid = sys.argv[1:3]\n"
    "real = trajectory.admit_boundary\n"
    "def die(*a, **k):\n"
    "    real(*a, **k)\n"
    "    sys.stdout.write('HELD:' + str(len(mission.read_in_flight("
    "dsn, cid))))\n"
    "    sys.stdout.flush()\n"
    "    os._exit(9)\n"
    "trajectory.admit_boundary = die\n"
    "trajectory.set_namespace_token('')\n"
    "trajectory.authorize_campaign(dsn, cid, authorized=100000)\n"
    "trajectory.ensure_campaign(dsn, cid, 0, 'I', %s, %s, tasks=[%r])\n"
    "trajectory.run_campaign(0, 'I', %s, %s, tasks=[%r], dsn=dsn,\n"
    "                      capability_id=%r)\n"
    "sys.stdout.write('DID_NOT_CRASH')\n"
    % (repr(CHARTER), repr(CAPS), DEV_TASK, repr(CHARTER), repr(CAPS),
       DEV_TASK, repr(ADMITTED_PROGRAM)))


def test_the_live_path_admits_where_it_decides(store):
    """A production campaign holds its operation the instant it decides.

    The campaign is reached through `run_campaign` and nothing else --
    no `accept_action`, no `admit_operation`, no fixture that already held an
    operation -- and the process is killed at the admission itself, before the
    effect. The operation must be on the entry at that point. This is the
    claim that was false before: `accept_action` had no production caller, so
    the column was empty here however the run ended.

    `DID_NOT_CRASH` is asserted rather than assumed. A patch that never fired
    would leave the column empty and let this pass having measured nothing,
    which is the one way this test could be green for the wrong reason.
    """
    cid = _cid(80)
    out = _run_phase(_DIE_AT_ADMISSION, store, cid)
    assert "DID_NOT_CRASH" not in out, (
        "the run finished without reaching the admission seam, so nothing "
        "was measured: %r" % out)
    assert "HELD:1" in out, (
        "the process died without reporting a held operation: %r" % out)

    held = _in_flight_raw(store, cid)
    assert len(held) == 1, (
        "the crash window holds %d operations, not the one it should: %r" % (
            len(held), held))
    admitted = held[0]
    assert admitted["attempt_id"] == "att-%s-0" % cid, (
        "the operation was admitted under %r, not the boundary's own attempt"
        % admitted["attempt_id"])
    assert admitted["capability_id"] == ADMITTED_PROGRAM, (
        "the admission recorded %r, not the program that was about to run"
        % admitted["capability_id"])
    assert admitted["task_id"] == DEV_TASK, (
        "the admission recorded task %r, not the one the decision named"
        % admitted["task_id"])
    assert admitted["status"] == "held", (
        "the operation was not held at the seam: %r" % admitted)

    # The decision is durable at the crash and the effect has not run, which
    # is what makes this a window rather than a settled row.
    assert _s09_row(store, cid) is not None, (
        "the crashed run left no policy row, so the decision was not durable")
    assert _effect_record(store, cid) is None, (
        "the crashed run recorded an effect, so it did not die before running "
        "one: %r" % (_effect_record(store, cid),))


def test_a_clean_completed_campaign_leaves_the_entry_empty(store):
    """The other direction, on the same path.

    Nothing was written here to make this true: it is the consequence of the
    live path releasing what it admits once the effect is recorded. If the
    release were missing this would fail with one stale row per boundary,
    which is the failure a wiring that only ever holds would produce.
    """
    from experiments.ad01 import trajectory

    cid = _cid(81)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                               tasks=[DEV_TASK])
    out = trajectory.run_campaign(0, "I", CHARTER, CAPS, tasks=[DEV_TASK],
                                  dsn=store, capability_id=ADMITTED_PROGRAM)

    assert len(out["boundaries"]) == 1, (
        "the campaign ran no boundary, so it proved nothing: %r" % (
            out["boundaries"],))
    assert _in_flight_raw(store, cid) == [], (
        "a completed campaign still holds its operation: %r" % (
            _in_flight_raw(store, cid),))


# Phase A runs the campaign and dies at the admission. Phase B is a separate
# interpreter that resumes through the public entry and reports what it
# continued under. Only the database crosses between them.
_RESUME_PHASE = (
    "import json, sys\n"
    "from experiments.ad01 import mission, trajectory\n"
    "dsn, cid = sys.argv[1:3]\n"
    "trajectory.set_namespace_token('')\n"
    "restored = mission.read_in_flight(dsn, cid)\n"
    "sys.stdout.write('HELD:' + json.dumps(\n"
    "    [item.as_json() for item in restored], default=str) + chr(10))\n"
    "sys.stdout.flush()\n"
    "out = trajectory.resume_campaign(dsn, cid, %s, %s, tasks=[%r],\n"
    "                                 capability_id=%r)\n"
    "sys.stdout.write('RAN:' + json.dumps(\n"
    "    {'boundaries': len(out['boundaries']),\n"
    "     'resumed': out.get('resumed_in_flight'),\n"
    "     'capability': [e.get('lineage', [{}])[0].get('capability_id')\n"
    "                    for e in out['episodes']]}, default=str) + chr(10))\n"
    % (repr(CHARTER), repr(CAPS), DEV_TASK, repr(SUBSTITUTED_PROGRAM)))


def _phase_lines(out: str, prefix: str) -> list:
    return [line[len(prefix):] for line in out.splitlines()
            if line.startswith(prefix)]


def test_a_crash_in_the_window_resumes_under_its_admitted_identity(store):
    """The whole point: pending work keeps its identity through a restart.

    Phase A is a production campaign killed at the seam. Phase B restarts in
    a new interpreter under a *different* seed program -- `seed-sw-ddmin`
    against the admitted `seed-sw-greedy`, which on this task produces a
    different candidate -- and the boundary must still run the program it was
    admitted with. The digests are compared against literals computed from
    the decision at admission, so a resume that recomputed, defaulted or
    substituted any of them fails rather than agreeing by accident.

    This is what milestone A asks for and what production did not do: the
    archived campaigns hold 82 episodes and not one `ran_under`, so before
    this the restart could not have retained anything, because there was
    nothing recorded to retain.
    """
    from experiments.ad01 import mission

    cid = _cid(82)
    _run_phase(_DIE_AT_ADMISSION, store, cid)

    held = _in_flight_raw(store, cid)
    assert len(held) == 1, (
        "the crash window held %d operations, not the one it should: %r" % (
            len(held), held))
    admitted = held[0]
    assert admitted["attempt_id"] == "att-%s-0" % cid, (
        "the operation was admitted under %r, not the boundary's own attempt"
        % admitted["attempt_id"])
    assert admitted["capability_id"] == ADMITTED_PROGRAM, (
        "the admission recorded %r, not the program that was about to run"
        % admitted["capability_id"])
    assert admitted["task_id"] == DEV_TASK, (
        "the admission recorded task %r, not the one the decision named"
        % admitted["task_id"])

    out = _run_phase(_RESUME_PHASE, store, cid)

    seen = _phase_lines(out, "HELD:")
    assert len(seen) == 1, "the resume reported its held operations %d times" % (
        len(seen),)
    from_resume = json.loads(seen[0])
    assert len(from_resume) == 1, (
        "the restart restored %d operations" % len(from_resume))
    assert from_resume[0]["program_digest"] == admitted["program_digest"], (
        "the restart came back under a different program")
    assert from_resume[0]["input_identity"] == admitted["input_identity"], (
        "the restart recomputed the operation's inputs")

    ran = json.loads(_phase_lines(out, "RAN:")[0])
    assert ran["boundaries"] == 1, (
        "the restart ran no boundary: %r" % (ran,))
    assert ran["resumed"], (
        "the resume ran a boundary that was already settled")
    assert ran["capability"] == [ADMITTED_PROGRAM], (
        "the restart ran the boundary under %r, not the program it was "
        "admitted under" % (ran["capability"],))

    # The effect record names the run, not the admission, and it must name
    # the program that actually ran.
    record = _effect_record(store, cid)
    assert record is not None, "the resumed boundary recorded no effect"
    ran_under = dict(dict(record)["ran_under"])
    assert ran_under["program_digest"] == admitted["program_digest"], (
        "the settled boundary does not say which program produced it")
    assert ran_under["input_identity"] == admitted["input_identity"]
    assert ran_under["decision_digest"] == admitted["decision_digest"]
    assert ran_under["capability_id"] == ADMITTED_PROGRAM

    assert _in_flight_raw(store, cid) == [], (
        "the settled operation is still in flight, so a later resume would "
        "restore an effect that already ran")


def test_no_production_path_writes_the_column_beside_the_mission_module():
    """The wiring adds no writer, so this is structural rather than tested
    at runtime.

    `AGENTS.md` asks for the earliest wrong ownership boundary repaired
    rather than a second authority beside it. `mission.admit_operation` is
    the only code that writes `investigations.in_flight`; this enumerates
    the writers of that column across `experiments/`, `src/` and `scripts/`
    and requires the set to be the one that was already there. A repair that
    had the frontier store or the campaign driver write the column itself
    would show up here as a second function.
    """
    import ast
    import re

    # The column as it is written, not the table and not the column name.
    # Measured across `experiments/`, `src/` and `scripts/`: matching the
    # bare name finds fourteen sites, because readers name it in a SELECT,
    # `frontier` names it in prose and `mission` names it in its own
    # docstrings. Matching the table name instead finds `store.py` five
    # times, which writes the charter columns and never this one. Only a
    # statement that sets the column is a write, and that is what this asks.
    writers = re.compile(
        r"\bUPDATE\s+investigations\s+SET\s+in_flight\b"
        r"|\bINSERT\s+INTO\s+investigations\b[^;]*\bin_flight\b",
        re.IGNORECASE | re.DOTALL)
    found: dict[str, list] = {}
    for tree_name in ("experiments", "src", "scripts"):
        tree_root = ROOT / tree_name
        if not tree_root.is_dir():
            continue
        for path in sorted(tree_root.rglob("*.py")):
            if path.name.startswith("__"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            scopes = {node: getattr(node, "name", "?")
                      for node in ast.walk(tree)
                      if isinstance(node, (ast.FunctionDef,
                                           ast.AsyncFunctionDef,
                                           ast.ClassDef))}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) \
                        or not isinstance(node.value, str):
                    continue
                if not writers.search(node.value):
                    continue
                enclosing = [(getattr(s, "lineno", 0), scopes[s])
                             for s in scopes
                             if getattr(s, "lineno", 0) <= node.lineno
                             and getattr(s, "end_lineno", node.lineno) >= node.lineno]
                owner = max(enclosing)[1] if enclosing else "<module>"
                found.setdefault(
                    "%s :: %s" % (path.relative_to(ROOT).as_posix(), owner),
                    []).append(node.lineno)

    # Every function that writes the column, across the three guarded trees.
    # A repair that had the campaign driver or the frontier store write
    # `in_flight` directly, or that added a fourth function in `mission`,
    # adds a key here. This lane's own wiring is on the call path and adds
    # none, which is the point of routing through `accept_action`.
    assert sorted(found) == sorted(_EXPECTED_WRITERS), (
        "the set of functions writing investigations.in_flight changed: %r"
        % sorted(found))


# Measured by the enumeration above at 655d684, and re-derived from the tree
# rather than remembered. Four writers in two modules: three in `mission`,
# which owns the column, and `run._hold_on_mission_entry`, which the barrier
# suspension path reaches and which this lane does not own.
_EXPECTED_WRITERS = [
    "experiments/ad01/mission.py :: admit_operation",
    "experiments/ad01/mission.py :: release_operation",
    "experiments/ad01/mission.py :: resume_operation",
    "src/settlement/run.py :: _hold_on_mission_entry",
]
