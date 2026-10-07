"""S09-M34 full deterministic cycle plus rejection plus identity."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    admin_dsn as _route, \
    create_disposable_db, disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "m34cyc%s" % uuid.uuid4().hex[:10]

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16,
        "model_calls": 60}
DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"

ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
BROKEN_SOURCE = (
    "def broken_entry(task, oracle, max_queries=16):\n"
    "    return task\n"
)


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

    The deterministic cycle settles into the store. The fixture used to
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


class _RecordingConstructor:
    label = "S09-M34-RECORDING-CONSTRUCTOR"

    def __init__(self, sources):
        from settlement.gateway import Usage
        self._sources = list(sources)
        self._usage = Usage(input_tokens=11, output_tokens=7)
        self.calls = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        source = self._sources[min(len(self.calls) - 1,
                                   len(self._sources) - 1)]
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source,
                                         "notes": "s09-m34 recorded"}),
                             {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def test_full_deterministic_cycle_with_provider_double_only(store, tmp_path):
    from experiments.ad01 import construct, records, selection, trajectory
    from experiments.ad01 import worlds
    cid = trajectory.campaign_id(0, "I", 60)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[DEV_TASK], campaign_seq=60, dsn=store)
    assert campaign["boundaries"]
    assert campaign["boundaries"][0]["observation_id"]
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gateway = _RecordingConstructor([ACQUIRED_SOURCE])
    member = construct.construct_method(
        store, campaign_id=cid, task=task,
        experience={"observations": [], "boundary": {"seq": 0}},
        budget={"max_output_tokens": 512, "max_queries": 4,
                "model_calls": 4},
        gateway=gateway, model="s09-m34-double", study_root=cid)
    assert member["method_source"] == ACQUIRED_SOURCE
    assert len(gateway.calls) >= 1
    failure_record = {"task_id": USE_TASK,
                      "parent_digest": "seed-sw-greedy",
                      "verdict": "not_preserved",
                      "use_record": "operational-failure-pin"}
    proposal = records.open_revision_proposal(
        store, investigation_id=cid, parent_digest="seed-sw-greedy",
        failure_record=failure_record, scope={"family": "software"},
        allocation_id="ad01-campaign-%s" % cid)
    assert proposal["parent_digest"] == "seed-sw-greedy"
    assert records.load_revision_proposal(
        store, proposal["proposal_id"]) == proposal
    freeze = records.freeze_candidate(
        store, proposal_id=proposal["proposal_id"],
        source_bytes=member["method_source"],
        entry=member["entry"])
    assert freeze["candidate_digest"] == member["source_digest"]
    verdict = records.assess_frozen(
        store, proposal_id=proposal["proposal_id"], tasks=[DEV_TASK],
        evaluator_version="e1", protocol_id="s09-revision-v1")
    assert verdict["outcome"] == "bind", verdict
    version_id = "acquired-sw-%s" % freeze["candidate_digest"][:8]
    bound = selection.bind_revision(
        store, release_id="s09-cycle-bind", versions=[version_id],
        scope={"family": "software"}, disposition="default",
        fallback="seed-sw-greedy", expected_versions=None,
        policy_version="ad01-policy-model-v1",
        protocol_id="s09-revision-v1", evaluator_version="e1",
        evidence_refs=[verdict["attempt_id"]],
        proposal_id=proposal["proposal_id"],
        candidate_digest=freeze["candidate_digest"])
    assert bound["versions"] == [version_id]
    repertoire = {"campaign_id": cid, "members": [
        {"capability_id": "seed-sw-greedy",
         "scope": {"family": "software"},
         "method_source": None},
        {"capability_id": version_id,
         "scope": {"family": "software"},
         "method_source": member["method_source"],
         "entry": member["entry"],
         "source_digest": member["source_digest"],
         "authored": False}]}
    chosen = selection.select_member(
        repertoire, {"family": "software"}, dsn=store,
        release_id="s09-cycle-bind")
    assert chosen["capability_id"] == version_id
    probe_path = tmp_path / "s09_m34_fresh.py"
    probe_path.write_text(
        "import sys\n"
        "dsn, release, version, cid = sys.argv[1:5]\n"
        "from experiments.ad01 import method_exec, selection, trajectory, worlds\n"
        "repertoire = {'members': ["
        "{'capability_id': 'seed-sw-greedy',"
        " 'scope': {'family': 'software'}}, "
        "{'capability_id': version, 'scope': {'family': 'software'},"
        " 'method_source': %r, 'entry': %r, 'source_digest': %r}]}\n"
        "chosen = selection.select_member(repertoire,"
        " {'family': 'software'}, dsn=dsn, release_id=release)\n"
        "task = worlds.load_task(worlds.FROZEN_DIR, %r)\n"
        "out = method_exec.run_member_out_of_process("
        "chosen, task, max_queries=4, dsn=dsn, "
        "allocation_id=trajectory._alloc_id(cid), "
        "operation_id=selection.versioned_use_op_id("
        "cid, task['task_id'], chosen['capability_id']))\n"
        "print(__import__('json').dumps({'selected':"
        " chosen['capability_id'], 'queries': out['queries']}))\n"
        % (member["method_source"], member["entry"], member["source_digest"], DEV_TASK))
    proc = subprocess.run(
        [sys.executable, probe_path, store, "s09-cycle-bind", version_id,
         cid],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    fresh = json.loads(proc.stdout)
    assert fresh["selected"] == version_id
    assert 0 < fresh["queries"] <= 4


def test_rejection_cycle_preserves_binding(store):
    from experiments.ad01 import records, selection
    active = selection.active_binding_for(
        store, "software", release_id="s09-cycle-bind")
    assert active is not None
    before = list(active["versions"])
    failure_record = {"task_id": USE_TASK,
                      "parent_digest": before[0],
                      "verdict": "not_preserved"}
    proposal = records.open_revision_proposal(
        store, investigation_id="ad01-w0-I-60",
        parent_digest=before[0], failure_record=failure_record,
        scope={"family": "software"})
    records.freeze_candidate(
        store, proposal_id=proposal["proposal_id"],
        source_bytes=BROKEN_SOURCE, entry="broken_entry")
    verdict = records.assess_frozen(
        store, proposal_id=proposal["proposal_id"], tasks=[DEV_TASK])
    assert verdict["outcome"] == "reject", verdict
    after = selection.active_binding_for(
        store, "software", release_id="s09-cycle-bind")
    assert after["versions"] == before


def test_retry_reuses_identity_revision_gets_new_attempt(store):
    from experiments.ad01 import records, trajectory
    from experiments.ad01 import worlds
    failure = {"task_id": DEV_TASK, "parent_digest": "seed-sw-greedy",
               "verdict": "not_preserved"}
    first = records.open_revision_proposal(
        store, investigation_id="ad01-w0-I-61",
        parent_digest="seed-sw-greedy", failure_record=failure,
        scope={"family": "software"})
    again = records.open_revision_proposal(
        store, investigation_id="ad01-w0-I-61",
        parent_digest="seed-sw-greedy", failure_record=failure,
        scope={"family": "software"})
    assert again["proposal_id"] == first["proposal_id"]
    other = records.open_revision_proposal(
        store, investigation_id="ad01-w0-I-61",
        parent_digest="seed-sw-ddmin", failure_record={
            "task_id": DEV_TASK, "parent_digest": "seed-sw-ddmin",
            "verdict": "not_preserved"},
        scope={"family": "software"})
    assert other["proposal_id"] != first["proposal_id"]
    first_freeze = records.freeze_candidate(
        store, proposal_id=first["proposal_id"],
        source_bytes=ACQUIRED_SOURCE, entry="acquired_order")
    second_freeze = records.freeze_candidate(
        store, proposal_id=first["proposal_id"],
        source_bytes=ACQUIRED_SOURCE, entry="acquired_order")
    assert second_freeze == first_freeze
    with pytest.raises(ValueError, match="new revision"):
        records.freeze_candidate(
            store, proposal_id=first["proposal_id"],
            source_bytes=BROKEN_SOURCE, entry="broken_entry")
    first_id = records.execution_identity(
        investigation_id="c", logical_action="use",
        policy_version="p", method_version="m1", attempt="a1")
    assert first_id == records.execution_identity(
        investigation_id="c", logical_action="use",
        policy_version="p", method_version="m1", attempt="a1")
    assert first_id != records.execution_identity(
        investigation_id="c", logical_action="use",
        policy_version="p", method_version="m2", attempt="a2")
    target = next(p.stem for p in sorted(
        worlds.FROZEN_DIR.rglob("*.json")) if "w0-transfer-sw" in p.stem)
    proposal = {"basis_references": [],
                "unknown": "q", "question": "q",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": target},
                "requested_resources": {"queries": 1}}
    admitted = trajectory.admit_investigation(
        proposal, {"observations": []}, CHARTER,
        {"world": 0, "arm": "I", "seq": 0})
    assert admitted["decision"] == "admitted"
    cid = trajectory.campaign_id(0, "I", 62)
    trajectory.authorize_campaign(store, cid, authorized=1000)
    trajectory.ensure_campaign(store, cid, 0, "I", CHARTER,
                               {"max_boundaries": 6,
                                "diagnostic_queries": 16},
                               tasks=[DEV_TASK])
    trajectory.accept_action(store, cid, 0, proposal)
    _obs, episode, spend, _dec = trajectory.execute_pending(
        store, cid, 0, task_id=DEV_TASK,
        capability_id="seed-sw-greedy", caps={
            "max_boundaries": 6, "diagnostic_queries": 16},
        seed_obs={"observation_id": "obs-x", "task_id": DEV_TASK,
                  "capability_id": "seed-sw-greedy",
                  "verdict": "unmeasured"},
        charter=CHARTER, boundary={"world": 0, "arm": "I", "seq": 0},
        experience={"observations": []},
        state={"dev_episodes": 0, "model_calls": 0,
               "construction_calls": 0},
        study_root=cid)
    assert episode["disposition"] == "no-candidate"
    assert "protected-use target" in episode["fallback_reason"]
    assert spend == 0
