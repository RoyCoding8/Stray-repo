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

from execution_authority import authority_for, execution_store

from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    create_disposable_db, disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "s89a3%s" % uuid.uuid4().hex[:10]

# The diagnostic rerun needs a store of its own: the campaign store above is
# scoped to the ad01 study this module runs, and a rerun of archived bytes
# under a study's allocation would charge that study for a diagnosis.
RERUN_TOKEN = "s89a3rerun"

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

FAIL_ON_USE_MEMBER_SOURCE = (
    "def acquired_sw_use_boom(task, oracle, max_queries=16):\n"
    "    if task['task_id'] == 'ad01-w0-within-sw-00':\n"
    "        raise RuntimeError(\"s89a3-use-failure\")\n"
    "    return reduce_software(task, oracle, method=\"greedy\",\n"
    "                          max_queries=max_queries)\n"
)


def _dbname(dsn: str) -> str:
    return dict(field.split("=", 1) for field in dsn.split()
                if "=" in field).get("dbname", "").strip("'\"")


def _admin_dsn() -> str:
    """The DSN names the instance to create on, never a store to empty."""
    return os.environ.get("SETTLEMENT_TEST_DSN") or LOCAL_DSN


@pytest.fixture(scope="module")
def rerun_authority():
    """The store `diag.current_tree_execute` reruns archived bytes under.

    The rerunner forwards its authority to the child executor, which refuses
    without all three. Without them the rerun reports `gate-refusal`, which
    claims the bytes were never admitted to execute rather than reporting
    what happened when they ran.
    """
    with execution_store(RERUN_TOKEN) as authority_store:
        yield authority_store


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


def _lifecycle(dsn, investigation, source, entry,
               parent_digest="seed-sw-greedy"):
    from experiments.ad01 import records, trajectory
    # `trajectory._alloc_id(investigation)` is what production names, and the
    # grant is the one `_campaign` already opened for this investigation.
    # Re-authorizing is idempotent, so this reads the campaign's own
    # allocation back rather than minting a second one.
    allocation = trajectory.authorize_campaign(
        dsn, investigation, authorized=100000)["allocation_id"]
    proposal = records.open_revision_proposal(
        dsn, investigation_id=investigation,
        parent_digest=parent_digest,
        failure_record={"task_id": USE_TASK,
                        "parent_digest": parent_digest,
                        "verdict": "not_preserved"},
        scope={"family": "software"},
        allocation_id=allocation)
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


def test_fresh_public_source_policy_joins_release_receipts(store, tmp_path):
    """A fresh public use joins source policy, release bytes, and receipts."""
    from experiments.ad01 import construct as C
    from experiments.ad01 import trajectory, worlds
    from settlement import db

    cid = "ad01-w0-I-62"
    _campaign(store, cid)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gateway = ScriptedModelBoundaryDouble([SIMULATED_MODEL_SW_SOURCE])
    member = C.construct_method(
        store, campaign_id=cid, task=task,
        experience={"observations": []},
        budget={"max_output_tokens": 512},
        gateway=gateway, model="s89a3-source-policy")
    episode = trajectory.dev_episode(
        DEV_TASK, "seed-sw-greedy", max_queries=16,
        member=member, result=member["validation"]["result"])
    assert episode["disposition"] == "retained"
    executable = episode["executable"]
    life = _lifecycle(store, cid, SIMULATED_MODEL_SW_SOURCE,
                      member["entry"])
    release = "s89a3-source-policy"
    _bind(store, life, release, [member["capability_id"]])
    repertoire = {"campaign_id": cid, "members": [executable]}
    frozen = tmp_path / "source-policy-repertoire.json"
    trajectory.freeze_repertoire(
        {"campaign_id": cid, "queries": 0, "episodes": [episode]}, frozen)
    allocation = "ad01-campaign-%s" % cid
    policy_source = (
        "def STEP(view, state):\n"
        "    task = view['task_content']\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': task['task_id'],\n"
        "                      'inputs': {'method_id': %r, 'max_queries': 4},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 4}},\n"
        "            'state': {}}\n" % member["capability_id"])
    policy_path = tmp_path / "use-policy.py"
    policy_path.write_text(policy_source, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--dsn", store,
         "--allocation-id", allocation, "--release", release,
         "--policy-source", str(policy_path), "--world", "0", "--arm", "I",
         "--tasks", USE_TASK],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    [record] = json.loads(proc.stdout)
    assert record["selected"] == member["capability_id"]
    assert record["executed"] == member["capability_id"]
    assert record["executed_source"] == SIMULATED_MODEL_SW_SOURCE
    assert executable["source_digest"] == hashlib.sha256(
        SIMULATED_MODEL_SW_SOURCE.encode("utf-8")).hexdigest()
    assert record["verdict"] == "preserved"
    assert record["release_id"] == release
    assert record["policy_source_digest"] == hashlib.sha256(
        policy_source.encode("utf-8")).hexdigest()
    assert len(record["operation_ids"]) == 2
    with db.connect(store) as conn:
        for operation_id in record["operation_ids"]:
            assert conn.execute(
                "SELECT count(*) FROM receipts WHERE operation_id = %s",
                (operation_id,)).fetchone()[0] == 1
    union = trajectory.cost_union(repertoire, [record], dsn=store)
    assert union["use"]["sandbox_ops"] == 2

    repeat = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--dsn", store,
         "--allocation-id", allocation, "--release", release,
         "--policy-source", str(policy_path), "--world", "0", "--arm", "I",
         "--tasks", USE_TASK],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert repeat.returncode == 0, repeat.stderr
    [replayed] = json.loads(repeat.stdout)
    assert replayed["operation_ids"] == record["operation_ids"]
    with db.connect(store) as conn:
        assert conn.execute(
            "SELECT count(*) FROM operations WHERE id LIKE %s",
            ("ad01-%s-use-%%" % repertoire["campaign_id"],)).fetchone()[0] == 2
        for operation_id in record["operation_ids"]:
            assert conn.execute(
                "SELECT count(*) FROM receipts WHERE operation_id = %s",
                (operation_id,)).fetchone()[0] == 1

    refused = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id="ad01-campaign-s09c-unbound", release_id=release,
        policy_source=policy_source)
    assert refused[0]["status"] == "refused"
    assert refused[0]["operation_ids"] == []
    with db.connect(store) as conn:
        assert conn.execute(
            "SELECT count(*) FROM operations WHERE id LIKE %s",
            ("ad01-%s-use-%%" % repertoire["campaign_id"],)).fetchone()[0] == 2

    revised_source = SIMULATED_MODEL_SW_SOURCE + "\n# revised bytes\n"
    revised_life = _lifecycle(
        store, cid, revised_source, member["entry"],
        parent_digest="seed-sw-greedy-revised")
    revised_release = "s89a3-source-policy-revised"
    _bind(store, revised_life, revised_release, [member["capability_id"]])
    revised_member = dict(executable,
                          method_source=revised_source,
                          source_digest=hashlib.sha256(
                              revised_source.encode("utf-8")).hexdigest())
    [stale] = trajectory.run_use(
        {"campaign_id": cid, "members": [revised_member]}, 0, "I",
        [USE_TASK], {}, dsn=store, allocation_id=allocation,
        release_id=revised_release, policy_source=policy_source)
    assert stale["status"] == "refused"
    assert stale["executed"] == "refused"
    assert "member execution failed" in stale["fallback_reason"]
    assert stale["operation_ids"] == [record["operation_ids"][0]]
    with db.connect(store) as conn:
        assert conn.execute(
            "SELECT count(*) FROM operations WHERE id LIKE %s",
            ("ad01-%s-use-%%" % repertoire["campaign_id"],)).fetchone()[0] == 2


def test_source_policy_cost_survives_member_refusal(store, monkeypatch):
    """A failed member keeps the admitted policy child in its cost union."""
    from experiments.ad01 import trajectory
    from settlement import db

    cid = "ad01-w0-I-63"
    capability = "acquired-sw-s89a3-use-boom"
    entry = "acquired_sw_use_boom"
    _campaign(store, cid)
    life = _lifecycle(store, cid, FAIL_ON_USE_MEMBER_SOURCE, entry)
    release = "s89a3-source-policy-failure"
    _bind(store, life, release, [capability])
    member = {"capability_id": capability,
              "method_source": FAIL_ON_USE_MEMBER_SOURCE,
              "entry": entry, "params": {"max_queries": 16},
              "scope": {"family": "software"}, "authored": False,
              "source_digest": hashlib.sha256(
                  FAIL_ON_USE_MEMBER_SOURCE.encode("utf-8")).hexdigest()}
    policy_source = (
        "def STEP(view, state):\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': %r,\n"
        "                      'inputs': {'method_id': %r, 'max_queries': 4},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 4}},\n"
        "            'state': {}}\n" % (USE_TASK, capability))
    allocation = "ad01-campaign-%s" % cid
    [record] = trajectory.run_use(
        {"campaign_id": cid, "members": [member]}, 0, "I", [USE_TASK], {},
        dsn=store, allocation_id=allocation, release_id=release,
        policy_source=policy_source)
    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert "member execution failed" in record["fallback_reason"]
    assert record["policy_source_digest"] == hashlib.sha256(
        policy_source.encode("utf-8")).hexdigest()
    assert len(record["operation_ids"]) == 2
    with db.connect(store) as conn:
        for operation_id in record["operation_ids"]:
            assert conn.execute(
                "SELECT count(*) FROM receipts WHERE operation_id = %s",
                (operation_id,)).fetchone()[0] == 1
    union = trajectory.cost_union(
        {"campaign_id": cid, "members": [member]}, [record], dsn=store)
    assert union["use"]["sandbox_ops"] == 2

    from settlement import broker
    original_dispatch = broker.dispatch_operation

    def hold_member(dsn, operation_id, **kwargs):
        if capability not in operation_id:
            return original_dispatch(dsn, operation_id, **kwargs)
        with db.connect(dsn) as conn:
            conn.execute(
                "UPDATE operations SET dispatch_state = 'dispatching',"
                " settled = FALSE WHERE id = %s", (operation_id,))
            conn.commit()
        return broker.DispatchStatus(
            operation_id=operation_id, dispatch_state="dispatching",
            next_decision="awaiting-receipt")

    monkeypatch.setattr(
        broker, "dispatch_operation", hold_member)
    pending_policy = policy_source.replace(USE_TASK, DEV_TASK)
    [pending] = trajectory.run_use(
        {"campaign_id": cid, "members": [member]}, 0, "I", [DEV_TASK], {},
        dsn=store, allocation_id=allocation, release_id=release,
        policy_source=pending_policy)
    assert pending["status"] == "refused"
    assert pending["executed"] == "refused"
    assert len(pending["operation_ids"]) == 2
    assert pending["costs"]["sandbox_ops"] == 2
    pending_member = next(op for op in pending["operation_ids"]
                          if capability in op)
    with db.connect(store) as conn:
        state, settled, reservation_id = conn.execute(
            "SELECT dispatch_state, settled, reservation_id FROM operations"
            " WHERE id = %s", (pending_member,)).fetchone()
        reservation_state, amount = conn.execute(
            "SELECT state, amount FROM reservations WHERE id = %s",
            (reservation_id,)).fetchone()
    assert (state, settled) == ("dispatching", False)
    assert reservation_state == "reserved"
    assert amount > 0


def test_archived_model_bytes_execute_through_fixed_child(rerun_authority):
    from scripts import s89_diagnose as diag
    export_dir = str(ROOT / "evidence_inv01_live" / "exports")
    [candidate] = [c for c in diag.extract_candidates(export_dir)
                   if c["digest"].startswith("d8fa9e5e")]
    assert "NameError" in candidate["old_failure"]
    report = diag.run_candidate(
        candidate, execute_fn=diag.current_tree_execute, max_queries=16,
        authority=authority_for(rerun_authority,
                                "s89a3-archived-fixed-child"))
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
