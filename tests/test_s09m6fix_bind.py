"""S09-M6fix gates: public run_use follows the active binding (F1) and
use operation identity versions with the executed method (F2)."""

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

DB = "s09_m6f_bind"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"

USE_TASK = "ad01-w0-within-sw-00"
DEV_TASK = "ad01-w0-dev-sw-00"
PROTOCOL = "s09-revision-v1"
EVALUATOR = "ad01-method-exec-v1"

REV_A_SOURCE = (
    "def rev_a_entry(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
REV_B_SOURCE = (
    "def rev_b_entry(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"ddmin\","
    " max_queries=max_queries)\n"
)


@pytest.fixture(scope="module")
def store():
    assert "live" not in DSN
    assert DB.startswith("s09_m6f_")
    subprocess.run(["createdb", "-h", "/var/run/postgresql",
                    "-U", "ubuntu", DB],
                   check=True, capture_output=True, text=True, timeout=60)
    try:
        from settlement import db
        db.apply_migrations(DSN, MIGRATIONS)
        yield DSN
    finally:
        subprocess.run(["dropdb", "-h", "/var/run/postgresql",
                        "-U", "ubuntu", DB],
                       capture_output=True, text=True, timeout=60)


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src",
                                      ROOT / "experiments")
    return env


def _member(capability_id, source, entry):
    return {"capability_id": capability_id,
            "scope": {"family": "software"},
            "method_source": source, "entry": entry,
            "source_digest": hashlib.sha256(
                source.encode("utf-8")).hexdigest(),
            "authored": False, "params": {"max_queries": 4}}


def _lifecycle(dsn, tag, source, entry):
    from experiments.ad01 import records
    proposal = records.open_revision_proposal(
        dsn, investigation_id="m6f-inv-%s" % tag,
        parent_digest="seed-sw-greedy",
        failure_record={"task_id": USE_TASK,
                        "parent_digest": "seed-sw-greedy",
                        "verdict": "not_preserved"},
        scope={"family": "software"})
    freeze = records.freeze_candidate(
        dsn, proposal_id=proposal["proposal_id"],
        source_bytes=source, entry=entry)
    assessment = records.assess_frozen(
        dsn, proposal_id=proposal["proposal_id"], tasks=[DEV_TASK],
        evaluator_version=EVALUATOR, protocol_id=PROTOCOL)
    assert assessment["outcome"] == "bind", assessment
    assert assessment["candidate_digest"] == freeze["candidate_digest"]
    return {"proposal": proposal, "freeze": freeze,
            "assessment": assessment}


def _bind(dsn, life, release, versions, expected):
    from experiments.ad01 import selection
    return selection.bind_revision(
        dsn, release_id=release, versions=list(versions),
        scope={"family": "software"}, disposition="default",
        fallback="seed-sw-greedy", expected_versions=expected,
        policy_version="p1", protocol_id=PROTOCOL,
        evaluator_version=EVALUATOR,
        evidence_refs=[life["assessment"]["attempt_id"]],
        proposal_id=life["proposal"]["proposal_id"],
        candidate_digest=life["freeze"]["candidate_digest"])


def _authorize(dsn, cid):
    from experiments.ad01 import trajectory
    return trajectory.authorize_campaign(
        dsn, cid, authorized=100000)["allocation_id"]


def test_direct_selector_follows_binding(store):
    from experiments.ad01 import selection
    life = _lifecycle(store, "prem", REV_B_SOURCE, "rev_b_entry")
    _bind(store, life, "s09-m6f-prem", ["m6fix-rev-b"], None)
    repertoire = {"campaign_id": "prem", "members": [
        _member("m6fix-rev-a", REV_A_SOURCE, "rev_a_entry"),
        _member("m6fix-rev-b", REV_B_SOURCE, "rev_b_entry")]}
    chosen = selection.select_member(
        repertoire, {"family": "software"}, dsn=store,
        release_id="s09-m6f-prem")
    assert chosen["capability_id"] == "m6fix-rev-b"


def test_f1_run_use_selects_revised_bytes(store):
    from experiments.ad01 import trajectory
    life = _lifecycle(store, "f1", REV_B_SOURCE, "rev_b_entry")
    _bind(store, life, "s09-m6f-f1", ["m6fix-rev-b"], None)
    cid = trajectory.campaign_id(0, "I", 70)
    allocation = _authorize(store, cid)
    repertoire = {"campaign_id": cid, "queries": 0, "members": [
        _member("m6fix-rev-a", REV_A_SOURCE, "rev_a_entry"),
        _member("m6fix-rev-b", REV_B_SOURCE, "rev_b_entry")]}
    [record] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation, release_id="s09-m6f-f1")
    assert record["selected"] == "m6fix-rev-b"
    assert record["executed_source"] == REV_B_SOURCE


def test_f1_run_use_selects_revised_bytes_fresh_process(store, tmp_path):
    from experiments.ad01 import trajectory
    life = _lifecycle(store, "f1fresh", REV_B_SOURCE, "rev_b_entry")
    _bind(store, life, "s09-m6f-f1fresh", ["m6fix-rev-b"], None)
    cid = trajectory.campaign_id(0, "I", 71)
    allocation = _authorize(store, cid)
    repertoire = {"campaign_id": cid, "queries": 0, "members": [
        _member("m6fix-rev-a", REV_A_SOURCE, "rev_a_entry"),
        _member("m6fix-rev-b", REV_B_SOURCE, "rev_b_entry")]}
    frozen = tmp_path / "repertoire.json"
    frozen.write_text(json.dumps(repertoire))
    probe = tmp_path / "fresh_run_use.py"
    probe.write_text(
        "import json, sys\n"
        "repertoire_path, dsn, allocation, release = sys.argv[1:5]\n"
        "from experiments.ad01 import trajectory\n"
        "repertoire = json.loads(open(repertoire_path).read())\n"
        "[record] = trajectory.run_use(\n"
        "    repertoire, 0, 'I', [%r], {}, dsn=dsn,\n"
        "    allocation_id=allocation, release_id=release)\n"
        "print(json.dumps({'selected': record['selected'],\n"
        "                  'executed_source':"
        " record['executed_source']}))\n" % USE_TASK)
    proc = subprocess.run(
        [sys.executable, str(probe), str(frozen), store, allocation,
         "s09-m6f-f1fresh"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"selected": "m6fix-rev-b",
                                       "executed_source": REV_B_SOURCE}


def test_f2_revision_mints_new_identity_retry_reuses(store):
    from experiments.ad01 import trajectory
    life_a = _lifecycle(store, "f2-a", REV_A_SOURCE, "rev_a_entry")
    life_b = _lifecycle(store, "f2-b", REV_B_SOURCE, "rev_b_entry")
    _bind(store, life_a, "s09-m6f-f2", ["m6fix-rev-a"], None)
    cid = trajectory.campaign_id(0, "I", 72)
    allocation = _authorize(store, cid)
    rep_a = {"campaign_id": cid, "queries": 0, "members": [
        _member("m6fix-rev-a", REV_A_SOURCE, "rev_a_entry")]}
    [first] = trajectory.run_use(
        rep_a, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation, release_id="s09-m6f-f2")
    [retry] = trajectory.run_use(
        rep_a, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation, release_id="s09-m6f-f2")
    assert first["operation_ids"] and \
        retry["operation_ids"] == first["operation_ids"]
    assert retry["output"] == first["output"]
    _bind(store, life_b, "s09-m6f-f2", ["m6fix-rev-b"], ["m6fix-rev-a"])
    rep_b = {"campaign_id": cid, "queries": 0, "members": [
        _member("m6fix-rev-b", REV_B_SOURCE, "rev_b_entry")]}
    [revised] = trajectory.run_use(
        rep_b, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation, release_id="s09-m6f-f2")
    assert revised["selected"] == "m6fix-rev-b"
    assert revised["executed_source"] == REV_B_SOURCE
    assert revised["operation_ids"] != first["operation_ids"]
    assert revised["output"] != first["output"]
