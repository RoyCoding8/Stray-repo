import json
import subprocess
from pathlib import Path

import pytest

from experiments.ad01 import agenda_policy, policy_step, trajectory
from settlement import db
from settlement.gateway import GatewayStatus, ModelResponse, Usage


ROOT = Path(__file__).resolve().parents[1]
CHARTER = {"objective": "reduce examples while preserving their witness", "freeze_id": "ad01"}
CAPS = {"max_boundaries": 2, "diagnostic_queries": 16, "model_calls": 6}
TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"]
METHOD = 'def reduce(task, oracle, max_queries=16):\n    return reducers.reduce_software(task, oracle, method="greedy", max_queries=max_queries)\n'
USE_POLICY = '''def STEP(view, state):
    methods = view["eligible_methods"]
    action = {"kind": "use_method" if methods else "construct_method",
              "target": view["task_content"]["task_id"],
              "inputs": {"method_id": methods[0] if methods else "", "max_queries": 4},
              "evidence_refs": [], "requested_resources": {"queries": 4}}
    return {"action": action, "state": state}
'''


class Constructor:
    def __init__(self, source=METHOD):
        self.calls = []
        self.source = source

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        return ModelResponse(request.operation_id, json.dumps({"entry": self.source, "notes": "fixture"}),
                             {}, Usage(input_tokens=10, output_tokens=20), "stop")

    def cancel(self, operation_id):
        return False


@pytest.fixture(scope="module")
def store():
    name = "s09_local_actions"
    subprocess.run(["createdb", name], check=True, capture_output=True, timeout=30)
    dsn = "dbname=" + name
    try:
        db.apply_migrations(dsn, ROOT / "migrations")
        yield dsn
    finally:
        subprocess.run(["dropdb", name], check=True, capture_output=True, timeout=30)


def run(store, seq, source, gateway, tasks=TASKS):
    cid = trajectory.campaign_id(0, "I", seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    consumer = agenda_policy.step_policy_consumer(
        policy_step.make_policy_artifact(source, origin="authored-control"),
        dsn=store, cid=cid, charter=CHARTER, world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid, gateway=gateway)
    return trajectory.run_campaign(0, "I", CHARTER, CAPS, tasks=tasks, campaign_seq=seq,
                                   dsn=store, consumer=consumer, constructor="model",
                                   gateway=gateway, model="fixture")


def test_policy_uses_retained_bytes_without_reconstructing(store):
    gateway = Constructor()
    campaign = run(store, 91, USE_POLICY, gateway)
    assert len(gateway.calls) == 1
    assert len(campaign["episodes"]) == 2
    acquired, used = campaign["episodes"]
    assert acquired["disposition"] == "retained"
    assert used["kind"] == "use_method"
    assert used["source_digest"] == acquired["executable"]["source_digest"]
    assert used["construction_calls"] == 0
    assert used["check"]["verdict"] == "preserved"


def test_failed_retained_use_does_not_refund_unknown_queries(store):
    source = '''def reduce(task, oracle, max_queries=16):
    if task["task_id"].endswith("01"):
        oracle.query(task)
        raise ValueError("fixture use failure")
    return reducers.reduce_software(task, oracle, method="greedy", max_queries=max_queries)
'''
    gateway = Constructor(source)
    campaign = run(store, 95, USE_POLICY, gateway)
    assert len(gateway.calls) == 1
    failed = campaign["episodes"][1]
    assert failed["disposition"] == "refused"
    assert failed["queries"] == 4
    assert failed["query_accounting"] == "upper-bound-on-failure"
    assert campaign["boundaries"][1]["spend"] == 4


def test_unknown_method_refuses_without_constructing(store):
    source = '''def STEP(view, state):
    return {"action": {"kind": "use_method", "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": "missing", "max_queries": 4},
                       "evidence_refs": [], "requested_resources": {"queries": 4}}, "state": state}
'''
    gateway = Constructor()
    campaign = run(store, 92, source, gateway, TASKS[:1])
    assert gateway.calls == []
    assert campaign["episodes"][0]["disposition"] == "refused"
    assert "missing" in campaign["episodes"][0]["reason"]


def test_revision_without_operational_feedback_is_durable_refusal(store):
    source = '''def STEP(view, state):
    return {"action": {"kind": "propose_revision", "target": view["task_content"]["task_id"],
                       "inputs": {"motivation": "investigate better"},
                       "evidence_refs": [], "requested_resources": {}}, "state": state}
'''
    gateway = Constructor()
    campaign = run(store, 93, source, gateway, TASKS[:1])
    assert gateway.calls == []
    assert len(campaign["episodes"]) == 1
    refusal = campaign["episodes"][0]
    assert refusal["kind"] == "policy_revision"
    assert refusal["disposition"] == "refused"
    assert "feedback" in refusal["reason"]
    with trajectory._read_conn(store) as conn:
        row = conn.execute("SELECT status FROM s09_policy_state WHERE investigation_id = %s AND seq = 0",
                           (campaign["campaign_id"],)).fetchone()
    assert row["status"] == "incorporated"


def test_feedback_constructs_and_freezes_policy_without_premature_promotion(store):
    source = '''def STEP(view, state):
    action = {"kind": "propose_revision" if state else "diagnose",
              "target": view["task_content"]["task_id"],
              "inputs": {"diagnostic": "software", "motivation": "improve investigation"},
              "evidence_refs": [view["observations"][0]["observation_id"]] if state else [],
              "requested_resources": {}}
    return {"action": action, "state": {"observed": True}}
'''
    candidate = '''def STEP(view, state):
    return {"action": {"kind": "stop", "target": view["task_content"]["task_id"],
                       "inputs": {"reason": "fixture policy"}, "evidence_refs": [],
                       "requested_resources": {}}, "state": state}
'''
    gateway = Constructor(candidate)
    campaign = run(store, 94, source, gateway)
    assert len(gateway.calls) == 1
    revision = campaign["episodes"][1]
    assert revision["kind"] == "policy_revision"
    assert revision["disposition"] == "rejected"
    assert revision["freeze"]["source"] == candidate
    assert revision["freeze"]["entry"] == "STEP"
    assert revision["policy_candidate"]["policy_artifact"]["kind"] == "learning-policy"
    assert revision["policy_candidate"]["policy_artifact"]["parent_digest"] == policy_step.make_policy_artifact(source, origin="authored-control")["artifact"]["source_digest"]
    assert revision["assessment_status"] == "complete"
    assert revision["assessment"]["outcome"] == "reject"
    assert revision["assessment"]["candidate_digest"] == revision["freeze"]["candidate_digest"]
    for arm in ("incumbent", "candidate"):
        assert revision["assessment"]["arms"][arm]["resources"]["step_calls"] > 0
    assert all("executable" not in episode for episode in campaign["episodes"])
    with trajectory._read_conn(store) as conn:
        assert conn.execute("SELECT count(*) AS n FROM capability_releases").fetchone()["n"] == 0
