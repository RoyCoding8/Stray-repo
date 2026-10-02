"""S09-M2 policy gates: divergence plus restart consistency.

Two independently authored STEP policies run through the public campaign
entry under identical initial conditions and must produce different
actual operations. One unchanged policy rerun from a fresh process must
reconcile the same operations with no duplicate child executions.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01.agenda_policy import step_policy_consumer
from experiments.ad01.policy_step import make_policy_artifact

DB = "s09_m2_policy"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"
RUNS = ROOT / ".ad01-runs"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16,
        "model_calls": 60}
TASK = "ad01-w0-dev-sw-00"

DIAGNOSE_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    seen = int(state.get(\"n\", 0))\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"n\": seen + 1}}\n"
)

DEVELOP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    action = {\"kind\": \"construct_method\", \"target\": target,\n"
    "              \"inputs\": {\"max_queries\": 4},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 4}}\n"
    "    return {\"action\": action, \"state\": {\"n\": 1}}\n"
)


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src",
                                      ROOT / "experiments")
    return env


@pytest.fixture(scope="module")
def store():
    assert "live" not in DSN
    assert DB.startswith("s09_m2_")
    subprocess.run(["createdb", "-h", "/var/run/postgresql",
                    "-U", "ubuntu", DB],
                   check=True, capture_output=True, text=True, timeout=60)
    before = set(p.name for p in RUNS.iterdir()) if RUNS.is_dir() else set()
    try:
        from settlement import db
        db.apply_migrations(DSN, MIGRATIONS)
        yield DSN
    finally:
        if RUNS.is_dir():
            for child in RUNS.iterdir():
                if child.name not in before:
                    import shutil
                    shutil.rmtree(child, ignore_errors=True)
        subprocess.run(["dropdb", "-h", "/var/run/postgresql",
                        "-U", "ubuntu", DB],
                       capture_output=True, text=True, timeout=60)


def _consumer(dsn, cid, source, gateway=None):
    from experiments.ad01 import trajectory
    artifact = make_policy_artifact(
        source, origin="authored-control",
        applicability={"world": 0, "arm": "I"})
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return step_policy_consumer(
        artifact, dsn=dsn, cid=cid, charter=dict(CHARTER),
        world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid),
        study_root=cid, gateway=gateway)


def _s09_row(dsn, cid, seq):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT * FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = %s",
            (cid, seq)).fetchone()


def _policy_ops(dsn, cid):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)"
            " ORDER BY id", ("ad01-%s-policy-" % cid,)).fetchall()


def test_two_authored_policies_diverge_through_public_entry(store):
    from experiments.ad01 import trajectory
    cid_a = trajectory.campaign_id(0, "I", 60)
    cid_b = trajectory.campaign_id(0, "I", 61)
    out_a = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=60, dsn=store,
        consumer=_consumer(store, cid_a, DIAGNOSE_SOURCE))
    out_b = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=61, dsn=store,
        consumer=_consumer(store, cid_b, DEVELOP_SOURCE))
    assert out_a["episodes"][0]["disposition"] == "inspected"
    assert out_b["episodes"][0].get("kind", "development") \
        != "diagnostic"
    assert out_a["queries"] != out_b["queries"]
    assert out_a["boundaries"][0]["observation_id"] != \
        out_b["boundaries"][0].get("observation_id", "") \
        or out_a["episodes"][0] != out_b["episodes"][0]
    for cid in (cid_a, cid_b):
        row = _s09_row(store, cid, 0)
        assert row is not None
        assert row["provenance"] == "s09-m2"
        assert row["status"] == "incorporated"
        assert dict(row["policy_input"]) != {}
        assert dict(row["policy_output"]) != {}
        assert dict(row["state_transition"]) != {}
        assert len(_policy_ops(store, cid)) >= 1
    digest_a = hashlib.sha256(
        DIAGNOSE_SOURCE.encode()).hexdigest()
    digest_b = hashlib.sha256(
        DEVELOP_SOURCE.encode()).hexdigest()
    assert digest_a != digest_b
    assert dict(_s09_row(store, cid_a, 0)[
        "policy_output"])["source_digest"] == digest_a


RESUME_SCRIPT = (
    "import json, sys\n"
    "dsn, cid, source_path = sys.argv[1:4]\n"
    "from experiments.ad01 import trajectory\n"
    "from experiments.ad01.agenda_policy import step_policy_consumer\n"
    "from experiments.ad01.policy_step import make_policy_artifact\n"
    "source = open(source_path).read()\n"
    "artifact = make_policy_artifact(source, origin='authored-control',\n"
    "    applicability={'world': 0, 'arm': 'I'})\n"
    "consumer = step_policy_consumer(artifact, dsn=dsn, cid=cid,\n"
    "    charter=%s, world=0, arm='I',\n"
    "    allocation_id=trajectory._alloc_id(cid), study_root=cid)\n"
    "out = trajectory.resume_campaign(dsn, cid, %s, %s,\n"
    "    tasks=['%s'], consumer=consumer)\n"
    "print(json.dumps(out, default=str))\n"
    % (repr(CHARTER), repr(CHARTER), repr(CAPS), TASK))


def test_policy_consistent_after_fresh_process_restart(store,
                                                       tmp_path):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 62)
    first = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=62, dsn=store,
        consumer=_consumer(store, cid, DIAGNOSE_SOURCE))
    assert [b["seq"] for b in first["boundaries"]] == [0]
    before = _policy_ops(store, cid)
    assert len(before) >= 1
    source_path = tmp_path / "policy.py"
    source_path.write_text(DIAGNOSE_SOURCE)
    proc = subprocess.run(
        [sys.executable, "-c", RESUME_SCRIPT, store, cid,
         str(source_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    resumed = json.loads(proc.stdout)
    assert resumed["campaign_id"] == cid
    assert [b["seq"] for b in resumed["boundaries"]] == [0]
    assert resumed["boundaries"][0]["observation_id"] == \
        first["boundaries"][0]["observation_id"]
    assert resumed["episodes"] == first["episodes"]
    assert resumed["stop"] == first["stop"]
    assert _policy_ops(store, cid) == before
    row = _s09_row(store, cid, 0)
    assert row["status"] == "incorporated"
