"""S09-M2 constructor plus trust gates: model bytes lineage, broker
model effects, fences, validation, child-only execution."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, policy_step

DB = "s09_m2_construct"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"
RUNS = ROOT / ".ad01-runs"

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


def _script(entry: str) -> dict:
    return {"text": json.dumps({"entry": entry, "notes": "double"}),
            "usage": {"input_tokens": 10, "output_tokens": 10}}


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


def _setup(store, seq):
    from experiments.ad01 import trajectory, worlds
    cid = trajectory.campaign_id(0, "I", seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    task = worlds.load_task(worlds.FROZEN_DIR, TASK)
    return cid, task


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
    assert member["policy_artifact"]["origin"] == "model-acquired"
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
