"""S09-M34 atomic bind gates: fresh-process select plus failed preserves."""

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

DB = "s09_m34_bind"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"

DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"
PROTOCOL = "s09-revision-v1"
EVALUATOR = "ad01-method-exec-v1"

GOOD_SOURCE = (
    "def m34_good_entry(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
GOOD_ENTRY = "m34_good_entry"


@pytest.fixture(scope="module")
def store():
    assert "live" not in DSN
    assert DB.startswith("s09_m34_")
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


def _lifecycle(dsn, tag):
    from experiments.ad01 import records
    proposal = records.open_revision_proposal(
        dsn, investigation_id="m34-inv-%s" % tag,
        parent_digest="seed-sw-greedy",
        failure_record={"task_id": USE_TASK,
                        "parent_digest": "seed-sw-greedy",
                        "verdict": "not_preserved"},
        scope={"family": "software"})
    freeze = records.freeze_candidate(
        dsn, proposal_id=proposal["proposal_id"],
        source_bytes=GOOD_SOURCE, entry=GOOD_ENTRY)
    assessment = records.assess_frozen(
        dsn, proposal_id=proposal["proposal_id"], tasks=[DEV_TASK],
        evaluator_version=EVALUATOR, protocol_id=PROTOCOL)
    assert assessment["outcome"] == "bind", assessment
    assert assessment["candidate_digest"] == freeze["candidate_digest"]
    return {"proposal": proposal, "freeze": freeze,
            "assessment": assessment}


def _bind(dsn, life, release, versions, expected=None):
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


def test_failed_comparison_preserves_old_binding(store):
    from experiments.ad01 import selection
    life = _lifecycle(store, "preserve")
    _bind(store, life, "s09-bind-preserve", ["v-old"], None)
    with pytest.raises(selection.StaleBind):
        _bind(store, life, "s09-bind-preserve", ["v-bad"], ["v-wrong"])
    active = selection.active_binding_for(store, "software",
                                          release_id="s09-bind-preserve")
    assert active["versions"] == ["v-old"]


def test_atomic_bind_selects_revised_bytes_fresh_process(store, tmp_path):
    from experiments.ad01 import selection
    life = _lifecycle(store, "fresh")
    _bind(store, life, "s09-bind-fresh", ["v-old"], None)
    _bind(store, life, "s09-bind-fresh", ["v-new"], ["v-old"])
    repertoire = {"members": [
        {"capability_id": "v-old", "scope": {"family": "software"},
         "method_source": GOOD_SOURCE, "entry": GOOD_ENTRY,
         "source_digest": hashlib.sha256(GOOD_SOURCE.encode()).hexdigest()},
        {"capability_id": "v-new", "scope": {"family": "software"},
         "method_source": GOOD_SOURCE, "entry": GOOD_ENTRY,
         "source_digest": hashlib.sha256(GOOD_SOURCE.encode()).hexdigest()}]}
    chosen = selection.select_member(
        repertoire, {"family": "software"}, dsn=store,
        release_id="s09-bind-fresh")
    assert chosen["capability_id"] == "v-new"
    probe = tmp_path / "fresh_select.py"
    probe.write_text(
        "import sys\n"
        "dsn, release = sys.argv[1:3]\n"
            "from experiments.ad01 import selection\n"
            "repertoire = {'members': ["
            "{'capability_id': 'v-old', 'scope': {'family': 'software'}, "
            "'method_source': %r, 'entry': %r, 'source_digest': %r}, "
            "{'capability_id': 'v-new', 'scope': {'family': 'software'}, "
            "'method_source': %r, 'entry': %r, 'source_digest': %r}]}\n"
            "chosen = selection.select_member(repertoire,"
            " {'family': 'software'}, dsn=dsn, release_id=release)\n"
            "print(__import__('json').dumps("
            "{'selected': chosen['capability_id']}))\n" % (
                GOOD_SOURCE, GOOD_ENTRY,
                hashlib.sha256(GOOD_SOURCE.encode()).hexdigest(),
                GOOD_SOURCE, GOOD_ENTRY,
                hashlib.sha256(GOOD_SOURCE.encode()).hexdigest()))
    proc = subprocess.run(
        [sys.executable, str(probe), store, "s09-bind-fresh"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"selected": "v-new"}
