"""S09-M34 atomic bind gates: fresh-process select plus failed preserves."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    create_disposable_db, disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "m34bind%s" % uuid.uuid4().hex[:10]

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


def _dbname(dsn: str) -> str:
    return dict(field.split("=", 1) for field in dsn.split()
                if "=" in field).get("dbname", "").strip("'\"")


def _admin_dsn() -> str:
    """The DSN names the instance to create on, never a store to empty."""
    return _route()


@pytest.fixture(scope="module")
def store():
    admin = _admin_dsn()
    assert "live" not in _dbname(admin)
    database = create_disposable_db(RUN_TOKEN, admin_dsn=admin,
                                    migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database, admin_dsn=admin)


def test_the_store_is_named_for_this_run_not_for_the_file(store):
    """Two concurrent runs of this module must not share a store.

    Atomic bind is proven against a fresh process. The fixture used to
    create and drop one fixed name, so a sibling's teardown destroyed this
    run's store mid-module and the failures read as product defects rather
    than as the collision they are. Only the per-run suffix keeps the two
    disjoint, so that is what this pins.
    """
    mine = _dbname(store)

    assert mine.startswith(DB_PREFIX + "_" + RUN_TOKEN), mine

    with disposable_db(RUN_TOKEN, admin_dsn=_admin_dsn()) as fresh:
        assert fresh.name != mine
        assert fresh.name.startswith(DB_PREFIX + "_" + RUN_TOKEN)
        assert re.fullmatch(r"[0-9a-f]{12}", fresh.name.rsplit("_", 1)[1])
    assert mine != _dbname(LOCAL_DSN), mine


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src",
                                      ROOT / "experiments")
    return env


def _authorize(dsn, cid):
    """The grant whose allocation the proposal is executed under.

    Production opens the proposal for the campaign that runs the assessment
    and names that campaign's own allocation (`trajectory.py:833-835`). The
    name alone is not enough: the executor looks the allocation up and
    refuses an unknown one, so a proposal naming a grant nobody opened fails
    with "refused: unknown allocation" instead of exercising the panel.
    """
    from experiments.ad01 import trajectory
    return trajectory.authorize_campaign(
        dsn, cid, authorized=100000)["allocation_id"]


def _lifecycle(dsn, tag):
    from experiments.ad01 import records
    investigation = "m34-inv-%s" % tag
    proposal = records.open_revision_proposal(
        dsn, investigation_id=investigation,
        parent_digest="seed-sw-greedy",
        failure_record={"task_id": USE_TASK,
                        "parent_digest": "seed-sw-greedy",
                        "verdict": "not_preserved"},
        scope={"family": "software"},
        allocation_id=_authorize(dsn, investigation))
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
