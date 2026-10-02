"""S89-A3 closeout: one proven public acquisition/check/retention/use path.

Provenance labels used here and in the workstream report:
SIMULATED_MODEL_SW_SOURCE is an authored control standing in for model
bytes at the gateway boundary only; every other layer is production code.
ARCHIVED_MODEL_SOURCE entries are actual live model bytes from
evidence_inv01_live and are never edited. A delegating wrapper counts as
valid execution through the fixed child path, not a novel algorithm.
"""

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

from test_s09_migrate_callers import admit

from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    create_disposable_db, disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "s89a3%s" % uuid.uuid4().hex[:10]

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"
ACQ_CID = "ad01-w0-I-60"
REJ_CID = "ad01-w0-I-61"
PROTOCOL = "s09-revision-v1"
EVALUATOR = "ad01-method-exec-v1"

SIMULATED_MODEL_SW_SOURCE = (
    "def acquired_sw_bare(task, oracle, max_queries=16):\n"
    "    return reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)

INVALID_SOURCE = "not python {{{"

FAILING_MEMBER_SOURCE = (
    "def acquired_sw_boom(task, oracle, max_queries=16):\n"
    "    raise RuntimeError(\"s89a3-control-failure\")\n"
)


def _dbname(dsn: str) -> str:
    return dict(field.split("=", 1) for field in dsn.split()
                if "=" in field).get("dbname", "").strip("'\"")


def _admin_dsn() -> str:
    """The DSN names the instance to create on, never a store to empty."""
    return os.environ.get("SETTLEMENT_TEST_DSN") or LOCAL_DSN


@pytest.fixture(scope="module")
def store():
    """A store this run creates, on whichever cluster the operator named.

    The staging tree under ``.ad01-runs`` is deliberately left alone. It is
    keyed by DSN, so a per-run store gives a per-run directory, and every test
    here re-derives the directory it needs rather than reading the tree. A
    whole-tree delete removes a sibling's staged bytes, and the failure
    surfaces as an unreadable staged source rather than as the deletion that
    caused it.
    """
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

    The closeout path binds and runs one acquisition. The fixture used to
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


class ScriptedModelBoundaryDouble:
    label = "S89A3-SCRIPTED-MODEL-BOUNDARY"

    def __init__(self, sources, usage=None):
        from settlement.gateway import Usage
        self._sources = list(sources)
        self._usage = usage or Usage(input_tokens=11, output_tokens=7)
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
                                         "notes": "s89a3 scripted bytes"}),
                             {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _lifecycle(dsn, investigation, source, entry):
    from experiments.ad01 import records
    proposal = records.open_revision_proposal(
        dsn, investigation_id=investigation,
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


def _campaign(dsn, cid):
    from experiments.ad01 import trajectory
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return trajectory.ensure_campaign(
        dsn, cid, 0, "I", CHARTER,
        {"agenda_authorized": 100000, "max_boundaries": 6,
         "diagnostic_queries": 16})


def test_public_acquisition_check_retention_use(store, tmp_path):
    from experiments.ad01 import construct as C
    from experiments.ad01 import method_exec, trajectory, worlds
    contract = method_exec.child_contract()
    assert contract["callables"]["reduce_software"]["binding"] == \
        "reducers.reduce_software"
    _campaign(store, ACQ_CID)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gateway = ScriptedModelBoundaryDouble([SIMULATED_MODEL_SW_SOURCE])
    member = C.construct_method(
        store, campaign_id=ACQ_CID, task=task,
        experience={"observations": []},
        budget={"max_output_tokens": 512},
        gateway=gateway, model="s89a3-scripted-double")
    assert member["authored"] is False
    assert member["method_source"] == SIMULATED_MODEL_SW_SOURCE
    assert member["capability_id"].startswith("acquired-sw-")
    assert member["source_digest"] == hashlib.sha256(
        SIMULATED_MODEL_SW_SOURCE.encode("utf-8")).hexdigest()
    assert member["lineage"]["init_operation"]
    assert len(gateway.calls) == 1
    episode = trajectory.dev_episode(
        DEV_TASK, "seed-sw-greedy", max_queries=16,
        member=member, result=member["validation"]["result"])
    assert episode["disposition"] == "retained"
    assert episode["check"]["verdict"] == "preserved"
    assert episode["final_size"] < episode["initial_size"]
    executable = episode["executable"]
    assert executable["authored"] is False
    assert executable["method_source"] == SIMULATED_MODEL_SW_SOURCE
    assert executable["scope"] == {"family": "software"}
    life = _lifecycle(store, ACQ_CID, SIMULATED_MODEL_SW_SOURCE,
                      member["entry"])
    assert life["freeze"]["candidate_digest"] == member["source_digest"]
    release = "s89a3-acq"
    _bind(store, life, release, [member["capability_id"]])
    repertoire = {"campaign_id": ACQ_CID, "members": [executable]}
    frozen = tmp_path / "s89a3-repertoire.json"
    trajectory.freeze_repertoire(
        {"campaign_id": ACQ_CID, "queries": 0, "episodes": [episode]},
        frozen)
    loaded = trajectory.load_repertoire(frozen)
    assert loaded["members"] == repertoire["members"]
    allocation = "ad01-campaign-%s" % ACQ_CID
    [record] = trajectory.run_use(
        loaded, 0, "I", [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        policy=admit(member["capability_id"]), dsn=store,
        allocation_id=allocation, release_id=release)
    assert record["selected"] == member["capability_id"]
    assert record["executed"] == member["capability_id"]
    assert record["executed_source"] == SIMULATED_MODEL_SW_SOURCE
    assert record["fallback_reason"] == ""
    assert record["release_id"] == release
    assert record["verdict"] == "preserved"
    assert record["operation_ids"]
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--dsn", store,
         "--allocation-id", allocation, "--release", release,
         "--world", "0", "--arm", "I",
         "--tasks", USE_TASK],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    [fresh] = json.loads(proc.stdout)
    # `ad01-traj use` has no policy argument and this file may not give it
    # one, so the shipped surface holds no policy and owes a refusal. The
    # run_use call above is where the policy belongs. The merged CLI grows
    # `--policy-source`; until it lands this assertion describes the shipped
    # surface rather than the one a merged cli.py will have.
    assert fresh["status"] == "refused"
    assert fresh["selected"] == "refused"
    assert fresh["executed"] == "refused"
    assert fresh["output"] == {}
    assert fresh["costs"]["witness_queries"] == 0
    assert "no policy" in fresh["fallback_reason"]


def test_archived_model_bytes_execute_through_fixed_child():
    from scripts import s89_diagnose as diag
    export_dir = str(ROOT / "evidence_inv01_live" / "exports")
    [candidate] = [c for c in diag.extract_candidates(export_dir)
                   if c["digest"].startswith("d8fa9e5e")]
    assert "NameError" in candidate["old_failure"]
    report = diag.run_candidate(
        candidate, execute_fn=diag.current_tree_execute, max_queries=16)
    assert report["new_outcome"] == "executed"
    assert report["next_failure"] is None


def test_invalid_candidate_refused_and_use_refuses_it(store):
    from experiments.ad01 import construct as C
    from experiments.ad01 import trajectory, worlds
    _campaign(store, REJ_CID)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gateway = ScriptedModelBoundaryDouble([INVALID_SOURCE])
    with pytest.raises(C.ConstructionFailed):
        C.construct_method(
            store, campaign_id=REJ_CID, task=task,
            experience={"observations": []},
            budget={"max_output_tokens": 512},
            gateway=gateway, model="s89a3-scripted-double")
    assert len(gateway.calls) == 4
    broken = trajectory.dev_episode(
        DEV_TASK, "seed-sw-greedy", max_queries=1, break_candidate=True)
    assert broken["disposition"] == "rejected"
    assert broken["check"]["verdict"] != "preserved"
    assert broken["reason"]
    [empty] = trajectory.run_use(
        {"campaign_id": REJ_CID, "members": []}, 0, "I",
        [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        policy=admit("seed-sw-greedy"))
    assert empty["status"] == "refused"
    assert empty["selected"] == "refused"
    assert empty["executed"] == "refused"
    assert empty["costs"]["witness_queries"] == 0
    assert "absent from the repertoire" in empty["fallback_reason"]
    life = _lifecycle(store, REJ_CID, SIMULATED_MODEL_SW_SOURCE,
                      "acquired_sw_bare")
    release = "s89a3-rej"
    _bind(store, life, release, ["acquired-sw-s89a3boom"])
    failing = {"capability_id": "acquired-sw-s89a3boom",
               "method_source": FAILING_MEMBER_SOURCE,
               "entry": "acquired_sw_boom",
               "params": {"max_queries": 16},
               "scope": {"family": "software"}, "authored": False,
               "source_digest": hashlib.sha256(
                   FAILING_MEMBER_SOURCE.encode("utf-8")).hexdigest()}
    [pinned] = trajectory.run_use(
        {"campaign_id": REJ_CID, "members": [failing]}, 0, "I",
        [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        policy=admit("acquired-sw-s89a3boom"), dsn=store,
        allocation_id="ad01-campaign-%s" % REJ_CID, release_id=release)
    assert pinned["status"] == "refused"
    assert pinned["selected"] == "refused"
    assert pinned["executed"] == "refused"
    assert pinned["output"] == {}
    assert "pins bytes" in pinned["fallback_reason"]
    assert release in pinned["fallback_reason"]
    _bind(store, life, release, ["acquired-sw-s89a3good"],
          ["acquired-sw-s89a3boom"])
    broken_entry = {"capability_id": "acquired-sw-s89a3good",
                    "method_source": SIMULATED_MODEL_SW_SOURCE,
                    "entry": "acquired_sw_boom",
                    "params": {"max_queries": 16},
                    "scope": {"family": "software"}, "authored": False,
                    "source_digest": hashlib.sha256(
                        SIMULATED_MODEL_SW_SOURCE.encode(
                            "utf-8")).hexdigest()}
    [fallback] = trajectory.run_use(
        {"campaign_id": REJ_CID, "members": [broken_entry]}, 0, "I",
        [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        policy=admit("acquired-sw-s89a3good"), dsn=store,
        allocation_id="ad01-campaign-%s" % REJ_CID, release_id=release)
    assert fallback["requested"] == "acquired-sw-s89a3good"
    assert fallback["selected"] == "acquired-sw-s89a3good"
    assert fallback["executed"] == "incumbent"
    assert "member execution failed" in fallback["fallback_reason"]
