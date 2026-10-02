"""S09-M2 constructor plus trust gates: model bytes lineage, broker
model effects, fences, validation, child-only execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, policy_step
from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    create_disposable_db, disposable_db, drop_disposable_db

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "m2cons%s" % uuid.uuid4().hex[:10]

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16,
        "model_calls": 60}
TASK = "ad01-w0-dev-sw-00"

GOOD_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"built\": True}}\n"
)

BAD_SOURCE = (
    "def STEP(view, state):\n"
    "    import os\n"
    "    return {\"action\": {}, \"state\": {}}\n"
)

MODEL_ROUNDTRIP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    if not state.get(\"asked\"):\n"
    "        action = {\"kind\": \"request_model\", \"target\": target,\n"
    "                  \"inputs\": {\"prompt\": \"summarize witness\",\n"
    "                             \"max_output_tokens\": 64},\n"
    "                  \"evidence_refs\": [],\n"
    "                  \"requested_resources\": {\"model_calls\": 1}}\n"
    "        return {\"action\": action, \"state\": {\"asked\": True}}\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"asked\": True}}\n"
)
MEMBER_RECEIPT_SOURCE = (
    "def carried(task, oracle):\n"
    "    report = oracle.query(task)\n"
    "    return {\"candidate\": {\"source\": \"requested\","
    " \"verdict\": report[\"verdict\"]}, \"queries\": 1}\n"
)


def _script(entry: str) -> dict:
    return {"text": json.dumps({"entry": entry, "notes": "double"}),
            "usage": {"input_tokens": 10, "output_tokens": 10}}


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
    here re-derives the directory it needs rather than reading the tree. The
    sweep that used to remove it read the directory names present at setup and
    deleted everything new, which is wrong whenever a sibling runs: its
    directories look new too, so this run deleted staged bytes the sibling was
    about to execute. The failure surfaced as an unreadable staged source or a
    conflicted durable operation, and neither names the sweep that caused it.
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

    Constructor lineage and broker fences settle receipts. The fixture used
    to create and drop one fixed name, so a sibling's teardown destroyed
    this run's store mid-module and the failures read as product defects
    rather than as the collision they are. Only the per-run suffix keeps
    the two disjoint, so that is what this pins.
    """
    mine = _dbname(store)

    assert mine.startswith(DB_PREFIX + "_" + RUN_TOKEN), mine

    with disposable_db(RUN_TOKEN, admin_dsn=_admin_dsn()) as fresh:
        assert fresh.name != mine
        assert fresh.name.startswith(DB_PREFIX + "_" + RUN_TOKEN)
        assert re.fullmatch(r"[0-9a-f]{12}", fresh.name.rsplit("_", 1)[1])
    assert mine != _dbname(LOCAL_DSN), mine


def _setup(store, seq):
    from experiments.ad01 import trajectory, worlds
    cid = trajectory.campaign_id(0, "I", seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    task = worlds.load_task(worlds.FROZEN_DIR, TASK)
    return cid, task


def _tamper_launcher_results(monkeypatch) -> list:
    original = method_exec.LocalLauncher.read_result
    operation_ids = []

    def read_result(launcher, operation_id):
        operation_ids.append(operation_id)
        receipt = original(launcher, operation_id)
        if receipt is None or receipt.get("outcome") != "success":
            return receipt
        output = receipt["data"]["worker"]["data"]
        if "action" in output:
            output["action"] = {
                "kind": "stop", "target": "tampered", "inputs": {},
                "evidence_refs": [], "requested_resources": {}}
            output["state"] = {"source": "tampered"}
        else:
            output["candidate"] = {"source": "tampered"}
            output["queries"] = 99
        return receipt

    monkeypatch.setattr(method_exec.LocalLauncher, "read_result", read_result)
    return operation_ids


def test_model_constructor_returns_checked_bytes_with_repair(store):
    from experiments.ad01 import construct, trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid, task = _setup(store, 70)
    gateway = RecordingGatewayAdapter(
        [_script(BAD_SOURCE), _script(GOOD_SOURCE)])
    member = construct.construct_policy(
        store, campaign_id=cid, task=task,
        experience={"boundary": {"seq": 0}, "observations": []},
        budget={"max_output_tokens": 512, "model_calls": 4},
        gateway=gateway, model="recorded-double", study_root=cid,
        applicability={"family": "software"})
    assert member["policy_source"] == GOOD_SOURCE
    assert member["entry"] == "STEP"
    assert member["authored"] is False
    assert member["source_digest"] == hashlib.sha256(
        GOOD_SOURCE.encode()).hexdigest()
    assert member["policy_artifact"]["origin"] == "fixture-stand-in"
    assert member["acquisition_evidence"]["earned"] is False
    assert member["acquisition_evidence"]["reason"] == (
        "response carries no route metadata for model, provider, tier")
    assert member["policy_artifact"]["abi"] == \
        policy_step.POLICY_STEP_VERSION
    lineage = member["lineage"]
    assert lineage["init_operation"].endswith("-init")
    assert lineage["repair_operation"].endswith("-repair")
    assert lineage["init_failure"]["stage"] == "gate"
    assert lineage["init_response_digest"] == hashlib.sha256(
        json.dumps({"entry": BAD_SOURCE,
                    "notes": "double"}).encode()).hexdigest()
    assert lineage["response_digest"] == hashlib.sha256(
        json.dumps({"entry": GOOD_SOURCE,
                    "notes": "double"}).encode()).hexdigest()
    assert lineage["calls_made"] == 2
    assert member["validation"]["gate"] == "ok"
    assert member["validation"]["dry_run"]["action_kind"] == "diagnose"
    stepped = method_exec.run_step_out_of_process(
        member["policy_source"],
        policy_step.materialize_view(
            task=task, observations=[], open_questions=[],
            last_result=None, eligible_methods=[],
            remaining={"steps": 1}),
        {})
    assert stepped["action"]["kind"] == "diagnose"
    assert stepped["operation_ids"] == []
    ops = [op["id"] for op in trajectory._campaign_operations(
        store, cid) if "-policy-l" in op["id"]]
    assert len([o for o in ops if o.endswith("-init")]) == 1
    assert len([o for o in ops if o.endswith("-repair")]) == 1
    assert len([o for o in ops if o.endswith("-validate")]) == 1


def test_failed_construction_returns_no_authored_bytes(store):
    from experiments.ad01 import construct
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid, task = _setup(store, 71)
    gateway = RecordingGatewayAdapter(
        [_script(BAD_SOURCE), _script("not json at all")])
    with pytest.raises(construct.ConstructionFailed):
        construct.construct_policy(
            store, campaign_id=cid, task=task,
            experience={"boundary": {"seq": 0}, "observations": []},
            budget={"max_output_tokens": 512, "model_calls": 4},
            gateway=gateway, model="recorded-double",
            study_root=cid)


def test_model_request_is_broker_effect_feeding_next_step(store):
    from experiments.ad01 import trajectory
    from experiments.ad01.agenda_policy import step_policy_consumer
    from experiments.ad01.learner import RecordingGatewayAdapter
    from experiments.ad01.policy_step import make_policy_artifact
    cid = trajectory.campaign_id(0, "I", 72)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    gateway = RecordingGatewayAdapter([{"text": "witness kept here"}])
    record = make_policy_artifact(
        MODEL_ROUNDTRIP_SOURCE, origin="authored-control",
        applicability={"world": 0, "arm": "I"})
    consumer = step_policy_consumer(
        record, dsn=store, cid=cid, charter=dict(CHARTER),
        world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        gateway=gateway, model="recorded-double")
    assert consumer._proposer is None
    out = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=72, dsn=store, consumer=consumer)
    assert out["episodes"][0]["disposition"] == "inspected"
    with trajectory._read_conn(store) as conn:
        model_ops = conn.execute(
            "SELECT id FROM operations WHERE id = %s",
            ("ad01-%s-policy-s0-model-k0" % cid,)).fetchall()
        step_ops = conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)"
            " ORDER BY id",
            ("ad01-%s-policy-s0-k" % cid,)).fetchall()
        row = conn.execute(
            "SELECT * FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = %s",
            (cid, 0)).fetchone()
    assert len(model_ops) == 1
    assert len(step_ops) == 2
    assert row is not None
    results = dict(row["policy_output"])["results"]
    assert [r["action"]["kind"] for r in results] == [
        "request_model", "diagnose"]
    assert dict(row["policy_input"])["views"][1][
        "last_result"]["digest"] == hashlib.sha256(
        "witness kept here".encode()).hexdigest()


def test_protected_target_never_executes(store):
    from experiments.ad01 import trajectory, worlds
    from experiments.ad01.agenda_policy import step_policy_consumer
    from experiments.ad01.policy_step import make_policy_artifact
    target = next(p.stem for p in sorted(
        worlds.FROZEN_DIR.rglob("*.json")) if "w0-transfer-sw" in p.stem)
    source = (
        "def STEP(view, state):\n"
        "    action = {\"kind\": \"diagnose\", \"target\": \"%s\",\n"
        "              \"inputs\": {\"diagnostic\": \"software\",\n"
        "                         \"unknown\": \"u\", \"question\": \"q\"},\n"
        "              \"evidence_refs\": [],\n"
        "              \"requested_resources\": {\"queries\": 1}}\n"
        "    return {\"action\": action, \"state\": {}}\n" % target)
    proposal = {"unknown": "u", "basis_references": [],
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": target},
                "requested_resources": {"queries": 1}}
    refused = trajectory.admit_investigation(
        proposal, {"observations": []}, CHARTER,
        {"world": 0, "arm": "I", "seq": 0})
    assert refused["decision"] == "admitted"
    assert refused["reason"] == "explicit exploratory"
    cid = trajectory.campaign_id(0, "I", 73)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    record = make_policy_artifact(
        source, origin="authored-control",
        applicability={"world": 0, "arm": "I"})
    consumer = step_policy_consumer(
        record, dsn=store, cid=cid, charter=dict(CHARTER),
        world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid)
    out = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK], campaign_seq=73, dsn=store, consumer=consumer)
    assert out["episodes"][0]["disposition"] == "no-candidate"
    assert "protected-use target" in out["episodes"][0][
        "fallback_reason"]
    assert out["boundaries"][0]["task_id"] == TASK
    with trajectory._read_conn(store) as conn:
        seen = conn.execute(
            "SELECT count(*) AS n FROM attempt_observations o"
            " JOIN attempts a ON a.id = o.attempt_id"
            " WHERE a.investigation_id = %s"
            " AND o.content->>'kind' = 'boundary'",
            (cid,)).fetchone()
    assert int(seen["n"]) == 1


@pytest.mark.parametrize("source,fragment", [
    ("def STEP(view, state):\n    import os\n"
     "    return {\"action\": {}, \"state\": {}}\n",
     "imports-forbidden"),
    ("def STEP(view, state):\n    handle = open('x')\n"
     "    return {\"action\": {}, \"state\": {}}\n",
     "io-or-reflection-forbidden"),
    ("def STEP(view, state):\n    return {\"action\": {}, \"state\": {}}\n"
     "def STEP(view, state):\n    return {\"action\": {}, \"state\": {}}\n",
     "missing-entry-function"),
    ("def RUN(view, state):\n    return {\"action\": {}, \"state\": {}}\n",
     "missing-entry-function"),
    ("def STEP(view):\n    return {\"action\": {}, \"state\": {}}\n",
     "entry-arity"),
    ("def STEP(view, state, extra):\n"
     "    return {\"action\": {}, \"state\": {}}\n",
     "entry-arity"),
])
def test_step_source_validation_refuses_host_risks(source, fragment):
    with pytest.raises(method_exec.MethodExecutionError) as excinfo:
        method_exec.verify_step_source(source)
    assert fragment in str(excinfo.value)


def test_step_result_envelope_and_state_cap_enforced():
    view = {"task_content": {"task_id": TASK}, "observations": [],
            "open_questions": [], "last_result": None,
            "eligible_methods": [], "remaining": {},
            "contract_versions": {}}
    unknown_kind = (
        "def STEP(view, state):\n"
        "    return {\"action\": {\"kind\": \"teleport\",\n"
        "                        \"target\": \"x\", \"inputs\": {},\n"
        "                        \"evidence_refs\": [],\n"
        "                        \"requested_resources\": {}},\n"
        "            \"state\": {}}\n")
    with pytest.raises(method_exec.MethodExecutionError) as excinfo:
        method_exec.run_step_out_of_process(unknown_kind, view, {})
    assert "unknown policy action kind" in str(excinfo.value)
    big_state = (
        "def STEP(view, state):\n"
        "    return {\"action\": {\"kind\": \"stop\",\n"
        "                        \"target\": \"x\", \"inputs\": {},\n"
        "                        \"evidence_refs\": [],\n"
        "                        \"requested_resources\": {}},\n"
        "            \"state\": {\"blob\": \"x\" * 9000}}\n")
    with pytest.raises(method_exec.MethodExecutionError) as excinfo:
        method_exec.run_step_out_of_process(big_state, view, {})
    assert "exceeds" in str(excinfo.value)


def test_step_receipt_labels_bounded_child_execution(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 74)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    view = policy_step.materialize_view(
        task={"task_id": TASK, "family": "software"},
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={})
    stepped = method_exec.run_step_out_of_process(
        GOOD_SOURCE, view, {}, dsn=store,
        allocation_id=trajectory._alloc_id(cid),
        operation_id="ad01-%s-policy-s0-k0" % cid)
    assert stepped["action"]["kind"] == "diagnose"
    assert stepped["source_digest"] == hashlib.sha256(
        GOOD_SOURCE.encode()).hexdigest()
    with trajectory._read_conn(store) as conn:
        receipt = conn.execute(
            "SELECT content FROM receipts WHERE operation_id = %s"
            " ORDER BY receipt_identity LIMIT 1",
            ("ad01-%s-policy-s0-k0" % cid,)).fetchone()
    content = dict(receipt["content"])
    assert content["profile"] == "local-process"
    assert content["containment"] is False


def test_durable_step_uses_admitted_receipt_after_dispatch_and_replay(
        store, monkeypatch):
    from experiments.ad01 import trajectory
    cid, task = _setup(store, 75)
    operation_id = "ad01-%s-policy-s0-k0" % cid
    allocation_id = trajectory._alloc_id(cid)
    view = policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 1})
    read_operations = _tamper_launcher_results(monkeypatch)

    dispatched = method_exec.run_step_out_of_process(
        GOOD_SOURCE, view, {}, dsn=store, allocation_id=allocation_id,
        operation_id=operation_id, arm="I", task_id=TASK)
    replayed = method_exec.run_step_out_of_process(
        GOOD_SOURCE, view, {}, dsn=store, allocation_id=allocation_id,
        operation_id=operation_id, arm="I", task_id=TASK)

    assert dispatched["action"] == replayed["action"]
    assert dispatched["state"] == replayed["state"] == {"built": True}
    assert dispatched["action"]["kind"] == "diagnose"
    assert dispatched["action"]["target"] == TASK
    assert dispatched["operation_ids"] == replayed["operation_ids"] == [
        operation_id]
    raw = dispatched["receipt"]["details"]["raw_payload"]
    assert raw["action"] == dispatched["action"]
    assert raw["state"] == dispatched["state"]
    assert read_operations == [operation_id]


def test_durable_member_uses_admitted_receipt_after_dispatch_and_replay(
        store, monkeypatch):
    from experiments.ad01 import trajectory
    cid, task = _setup(store, 76)
    operation_id = "ad01-%s-member-k0" % cid
    allocation_id = trajectory._alloc_id(cid)
    member = {"capability_id": "durable-receipt-member",
              "method_source": MEMBER_RECEIPT_SOURCE, "entry": "carried"}
    read_operations = _tamper_launcher_results(monkeypatch)

    dispatched = method_exec.run_member_out_of_process(
        member, task, dsn=store, allocation_id=allocation_id,
        operation_id=operation_id)
    replayed = method_exec.run_member_out_of_process(
        member, task, dsn=store, allocation_id=allocation_id,
        operation_id=operation_id)

    expected = {"source": "requested", "verdict": "preserved"}
    assert dispatched["candidate"] == replayed["candidate"] == expected
    assert dispatched["queries"] == replayed["queries"] == 1
    assert dispatched["operation_id"] == replayed["operation_id"] == operation_id
    assert dispatched["operation_ids"] == replayed["operation_ids"] == [
        operation_id]
    assert read_operations == [operation_id]
