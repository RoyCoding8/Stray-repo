"""S09-M1 driver gates: resume after acceptance and after effect.

Gate one kills after acceptance and requires a fresh resume to reconcile
the same operation with no duplicate effects. Gate two kills after the
effect but before incorporation and requires resume to incorporate the
stored result without renewed limits. Kill is simulated with os._exit in
a fresh interpreter per phase, so only durable database state crosses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
TOKEN = "m1-driver"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}
TASK = "ad01-w0-dev-sw-00"
TASK2 = "ad01-w0-dev-sw-01"
DECISION = {"basis_references": [],
            "unknown": "does the seed disagree with itself",
            "question": "q0",
            "next_action": {"kind": "diagnostic",
                            "diagnostic": "diagnostic_resolves",
                            "task_id": TASK},
            "requested_resources": {"diagnostic_queries": 1}}


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src",
                                      ROOT / "experiments")
    return env


ACCEPT_PHASE = (
    "import json, os, sys\n"
    "dsn, cid, seq, task, decision_path = sys.argv[1:6]\n"
    "from experiments.ad01 import trajectory\n"
    "decision = json.loads(open(decision_path).read())\n"
    "trajectory.authorize_campaign(dsn, cid, authorized=1000)\n"
    "trajectory.ensure_campaign(dsn, cid, 0, 'I', %s, %s, tasks=[task])\n"
    "trajectory.accept_action(dsn, cid, int(seq), decision)\n"
    "os._exit(0)\n" % (repr(CHARTER), repr(CAPS)))

EXECUTE_PHASE = (
    "import json, os, sys\n"
    "dsn, cid, seq, task, decision_path, counter = sys.argv[1:7]\n"
    "from experiments.ad01 import trajectory as T\n"
    "decision = json.loads(open(decision_path).read())\n"
    "trajectory = T\n"
    "trajectory.authorize_campaign(dsn, cid, authorized=1000)\n"
    "trajectory.ensure_campaign(dsn, cid, 0, 'I', %s, %s, tasks=[task])\n"
    "trajectory.accept_action(dsn, cid, int(seq), decision)\n"
    "real = T.run_diagnostic\n"
    "def counting(admitted, experience, budget=None):\n"
    "    with open(counter, 'a') as handle:\n"
    "        handle.write('effect\\n')\n"
    "    return real(admitted, experience, budget=budget)\n"
    "T.run_diagnostic = counting\n"
    "seq = int(seq)\n"
    "out = T.execute_pending(dsn, cid, seq, task_id=task,\n"
    "    capability_id='seed-sw-greedy', caps=%s,\n"
    "    seed_obs={'observation_id': 'obs-%%s-seed' %% task, 'task_id': task,\n"
    "              'capability_id': 'seed-sw-greedy', 'verdict': 'unmeasured'},\n"
    "    charter=%s, boundary={'world': 0, 'arm': 'I', 'seq': seq},\n"
    "    experience={'observations': [], 'remaining': {'queries': 16,\n"
    "              'model_calls': 60, 'boundaries': 6, 'dev_episodes': 3}},\n"
    "    state={'dev_episodes': 0, 'model_calls': 0,\n"
    "           'construction_calls': 0}, study_root=cid)\n"
    "print(json.dumps({'observation_id': out[0]['observation_id'],\n"
    "                  'spend': out[2]}), flush=True)\n"
    "os._exit(0)\n" % (repr(CHARTER), repr(CAPS), repr(CAPS),
                       repr(CHARTER)))

RESUME_WRAPPED = (
    "import json, sys\n"
    "dsn, cid, counter, tasks = sys.argv[1:5]\n"
    "from experiments.ad01 import trajectory as T\n"
    "real = T.run_diagnostic\n"
    "def counting(admitted, experience, budget=None):\n"
    "    with open(counter, 'a') as handle:\n"
    "        handle.write('effect\\n')\n"
    "    return real(admitted, experience, budget=budget)\n"
    "T.run_diagnostic = counting\n"
    "out = T.resume_campaign(dsn, cid, %s, %s, tasks=tasks.split(','))\n"
    "print(json.dumps(out, default=str))\n" % (repr(CHARTER), repr(CAPS)))


def _database_name(dsn):
    return [field for field in dsn.split() if field.startswith("dbname=")][0][7:]


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    with iso.disposable_db(TOKEN) as database:
        from settlement import db
        assert "live" not in database.name
        db.apply_migrations(database.dsn, MIGRATIONS)
        yield database.dsn


def _run_phase(script, *args):
    proc = subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _decision_rows(dsn, cid):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT o.content FROM attempt_observations o"
            " JOIN attempts a ON a.id = o.attempt_id"
            " WHERE a.investigation_id = %s AND o.content->>'kind' = 'decision'",
            (cid,)).fetchall()
        return [dict(r["content"]) for r in rows]


def _operation_rows(dsn, cid):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT id FROM operations WHERE id LIKE %s", ("ad01-%s%%" % cid,)
        ).fetchall()
        return [dict(r) for r in rows]


def _s09_row(dsn, cid, seq):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT * FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = %s",
            (cid, seq)).fetchone()


def test_kill_after_acceptance_resumes_same_operation(store, tmp_path):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 40)
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(DECISION))
    _run_phase(ACCEPT_PHASE, store, cid, "0", TASK, str(decision_path))
    assert _decision_rows(store, cid)[0]["decision"] == DECISION
    assert _s09_row(store, cid, 0)["status"] == "accepted"
    resume = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "resume",
         "--dsn", store, "--campaign", cid, "--max-boundaries", "6"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert resume.returncode == 0, resume.stderr
    out = json.loads(resume.stdout)
    assert out["campaign_id"] == cid
    assert [b["seq"] for b in out["boundaries"]] == [0]
    assert out["boundaries"][0]["decision"] == DECISION
    assert out["episodes"][0]["disposition"] == "inspected"
    assert out["queries"] == 1
    assert len(_decision_rows(store, cid)) == 1
    row = _s09_row(store, cid, 0)
    assert row["status"] == "incorporated"
    # This boundary ran a host-side diagnostic and admitted no operation, so
    # the effect identity is empty rather than a name. It used to assert
    # `ad01-%s-b0-effect` % cid, a constant that matched no `operations` row on
    # this path or any other: the effect column named an identity that had
    # never existed (RF-02). The campaign below carries the construction arm,
    # and `tests/test_inv_x4b_effect_identity.py` pins the admitted case, where
    # the identity is a real settled operation.
    assert row["effect_id"] == ""
    operations = _operation_rows(store, cid)
    assert operations == [], (
        "this boundary admits no operation, so an empty effect identity is"
        " the honest value; the store holds %r" % (operations,))
    control = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=41)
    assert out["boundaries"][0]["observation_id"] == \
        control["boundaries"][0]["observation_id"]


def test_kill_after_effect_incorporates_without_renewed_limits(
        store, tmp_path):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 42)
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(DECISION))
    counter = tmp_path / "effects.log"
    printed = _run_phase(EXECUTE_PHASE, store, cid, "0", TASK,
                         str(decision_path), str(counter))
    effect = json.loads(printed)
    assert counter.read_text().strip().splitlines() == ["effect"]
    assert _s09_row(store, cid, 0)["effect_record"] is not None
    resumed = json.loads(_run_phase(
        RESUME_WRAPPED, store, cid, str(counter), TASK))
    assert counter.read_text().strip().splitlines() == ["effect"]
    assert [b["seq"] for b in resumed["boundaries"]] == [0]
    assert resumed["boundaries"][0]["observation_id"] == \
        effect["observation_id"]
    assert resumed["queries"] == effect["spend"] == 1
    assert resumed["stop"] == {"reason": "no admissible work remains"}
    assert resumed["episodes"][0]["disposition"] == "inspected"
    control = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=43)
    assert resumed["queries"] == control["queries"]
    assert resumed["stop"] == control["stop"]


def test_the_store_is_one_this_run_created(store):
    """A dropped store must never be a store somebody else still runs on.

    The gate that failed under a campaign run reads as duplicate effects
    across a crash, which is the exact failure this file exists to detect.
    A per-run name means the only database destroyed here is the one this
    run made.
    """
    name = _database_name(store)

    assert name.startswith("s09iso_m1-driver_"), name
    assert store.count(name) == 1, name


def test_the_store_survives_a_second_module_scope(store):
    """Re-deriving the store must not reuse this module's database."""
    from experiments.ad01 import s09_run_isolation as iso

    other = iso.create_disposable_db(TOKEN)

    assert other.name != _database_name(store)
    assert other.name.startswith("s09iso_m1-driver_")
    iso.drop_disposable_db(other)
