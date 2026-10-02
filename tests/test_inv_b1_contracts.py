"""INV-B1 gate: executable contracts, agreed rendering, admitted C3 path.

Real Postgres (`inv_b1_contracts` via INV_B1_DSN, never live) in every
brokered test. Recording doubles sit at the gateway seam only: every
learner and construction call travels through broker ensure, dispatch,
settled receipts and measured costs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "INV_B1_DSN",
    "dbname=inv_b1_contracts host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_SW = "ad01-w0-dev-sw-00"
DEV_GR = "ad01-w0-dev-gr-00"

CARRIED_SW = (
    "def carried_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
CARRIED_GR = (
    "def carried_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_graph(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="INV-B1 contracts gate")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _allocation(tag: str) -> str:
    from settlement import store
    from settlement.common import Command
    aid = "invb1-%s-%s" % (tag, uuid.uuid4().hex[:8])
    store.seed_allocation(
        DSN, Command(request_id="seed-%s" % aid,
                     payload={"allocation_id": aid, "domain": "cpu",
                              "authorized": 100000, "max_occupancy": 8}))
    return aid


def _packet(task_id: str):
    from experiments.ad01 import packet as P
    from experiments.ad01 import worlds
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    made = P.construction_packet(
        task=task, experience={"observations": []},
        budget={"max_output_tokens": 512}, prior_failure=None)
    return made, P.render_construction_prompt(made)


def test_rendered_construction_contract_matches_enforcement():
    from experiments.ad01 import method_exec
    from experiments.ad01 import packet as P
    for task_id in (DEV_SW, DEV_GR):
        made, prompt = _packet(task_id)
        assert made["packet_version"] == P.PACKET_VERSION
        assert made["family"] == made["task"]["family"]
        assert made["task"]["task_id"] == task_id
        rules = method_exec.entry_contract()
        assert rules["params"] in prompt
        assert "fails validation" in prompt
        for name in rules["forbidden"]["calls"]:
            assert name in prompt
        for key in made["candidate_shape"]["required_keys"]:
            assert key in prompt
        for verdict in made["preservation_objective"]["verdicts"]:
            assert verdict in prompt
        for reason in made["preservation_objective"]["reason_codes"]:
            assert reason in prompt
        assert "reduce_software" in prompt
        assert "reduce_graph" in prompt
        assert "oracle.query" in prompt


def test_entry_rule_acceptance_matches_validator():
    from experiments.ad01 import method_exec
    from experiments.ad01 import packet as P
    _, prompt = _packet(DEV_SW)
    cases = [
        ("carried_order", CARRIED_SW, True, "", ""),
        ("carried", "def carried(task, oracle):\n"
         "    return reducers.reduce_software(task, oracle)\n", True, "", ""),
        ("carried", "import os\ndef carried(task, oracle):\n    return None\n",
         False, "import", "import"),
        ("carried", "from os import path\ndef carried(task, oracle):\n    return None\n",
         False, "import", "import"),
        ("carried", "def carried(task, oracle):\n    return task.__class__\n",
         False, "dunder", "dunder"),
        ("carried", "def carried(task, oracle):\n    return getattr(task, 'ops')\n",
         False, "reflection", "getattr"),
        ("carried", "def carried(task, oracle):\n    return open('x').read()\n",
         False, "reflection", "open"),
        ("carried", "def carried(job, oracle):\n    return None\n",
         False, "arity", "parameters"),
        ("carried", "def carried(task, oracle, max_queries, extra):\n    return None\n",
         False, "arity", "parameters"),
        ("carried", "def carried(task, oracle, *rest):\n    return None\n",
         False, "arity", "parameters"),
        ("carried", "", False, "empty", "non-empty"),
        ("carried", "not python {{{", False, "parse", "parses"),
        ("carried", "X = 1\n", False, "entry", "exactly one"),
    ]
    for entry, source, accepted, exc_keyword, prompt_token in cases:
        try:
            method_exec.verify_member({"method_source": source,
                                       "entry": entry})
            outcome = True
        except method_exec.MethodExecutionError as exc:
            outcome = False
            assert exc_keyword in str(exc), (source, str(exc))
        assert outcome == accepted, source
        if not accepted:
            assert prompt_token in prompt, (source, prompt_token)


def test_parse_entry_agrees_with_renderer():
    from experiments.ad01.construct import _parse_entry
    body = json.dumps({"entry": CARRIED_SW, "notes": "carries greedy"})
    for text in (body, "```json\n%s\n```" % body):
        source, problem = _parse_entry(text)
        assert problem == ""
        assert source == CARRIED_SW
    source, problem = _parse_entry("plain prose, no object")
    assert source is None and problem.startswith("parse-failure")
    source, problem = _parse_entry(json.dumps({"notes": "no entry"}))
    assert source is None and problem.startswith("parse-failure")


def _evaluated(task_id: str, source: str, operation_id: str) -> dict:
    from experiments.ad01 import construct as C
    from experiments.ad01 import trajectory
    from experiments.ad01 import worlds
    cid = "invb1-%s" % uuid.uuid4().hex[:8]
    trajectory.authorize_campaign(DSN, cid, authorized=100000)
    trajectory.ensure_campaign(
        DSN, cid, 0, "I", dict(CHARTER),
        {"agenda_authorized": 100000, "max_boundaries": 1,
         "diagnostic_queries": 16})
    text = json.dumps({"entry": source, "notes": "gate transport"})
    return C._evaluate(
        text, operation_id, worlds.load_task(worlds.FROZEN_DIR, task_id),
        16, dsn=DSN, allocation_id=trajectory._alloc_id(cid))


def test_transport_round_trip_both_domains():
    _fresh_db()
    from experiments.ad01 import trajectory
    from experiments.ad01 import worlds
    for task_id, source in ((DEV_SW, CARRIED_SW), (DEV_GR, CARRIED_GR)):
        evaluated = _evaluated(task_id, source,
                               "invb1-transport-%s" % task_id[-5:])
        assert evaluated["failure"] is None, evaluated
        assert evaluated["checked"]["ok"] is True
        report = trajectory._check(
            worlds.load_task(worlds.FROZEN_DIR, task_id),
            evaluated["checked"]["result"]["candidate"])
        assert report["verdict"] == "preserved", report


def test_two_param_entry_executes_without_broker():
    from experiments.ad01 import method_exec
    from experiments.ad01 import trajectory
    from experiments.ad01 import worlds
    member = {"capability_id": "invb1-two-param",
              "method_source": (
                  "def carried(task, oracle):\n"
                  "    return reducers.reduce_software(task, oracle)\n"),
              "entry": "carried"}
    result = method_exec.run_member_out_of_process(
        member, worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
        max_queries=16)
    assert result["source_digest"] == hashlib.sha256(
        member["method_source"].encode("utf-8")).hexdigest()
    report = trajectory._check(
        worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
        result["candidate"])
    assert report["verdict"] == "preserved", report


class RecordingGateway:
    label = "INV-B1-RECORDING"

    def __init__(self, texts: list):
        from settlement.gateway import Usage
        self._texts = list(texts)
        self._usage = Usage(input_tokens=11, output_tokens=7)
        self.calls: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            self._texts[min(len(self.calls) - 1, len(self._texts) - 1)],
            {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def test_malformed_construction_has_visible_effects():
    _fresh_db()
    from experiments.ad01 import construct as C
    from experiments.ad01 import trajectory
    from settlement import broker
    cid = "invb1-malformed-%s" % uuid.uuid4().hex[:8]
    trajectory.authorize_campaign(DSN, cid, authorized=100000)
    trajectory.ensure_campaign(
        DSN, cid, 0, "I", dict(CHARTER),
        {"agenda_authorized": 100000, "max_boundaries": 1,
         "diagnostic_queries": 16})
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       DEV_SW)
    gateway = RecordingGateway(["not python {{{"])
    with pytest.raises(C.ConstructionFailed) as excinfo:
        C.construct_method(
            DSN, campaign_id=cid, task=task,
            experience={"observations": []},
            budget={"max_output_tokens": 512},
            gateway=gateway, model="invb1-malformed-double")
    assert excinfo.value.calls_made == 4
    assert len(gateway.calls) == 4
    prefix = "ad01-%s-b0-%s-construct-" % (cid, DEV_SW)
    with trajectory._read_conn(DSN) as conn:
        rows = conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)",
            (prefix,)).fetchall()
        assert len(rows) == 4
        for row in rows:
            assert broker.read_operation(DSN, row["id"]) is not None


def test_rejected_episode_is_visible_not_silent():
    _fresh_db()
    from experiments.ad01 import trajectory
    gateway = RecordingGateway(["not python {{{"])

    def propose(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % DEV_SW,
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": DEV_SW, "max_queries": 4},
                "requested_resources": {"diagnostic_queries": 1}}

    trajectory.authorize_campaign(
        DSN, trajectory.campaign_id(0, "I", 61), authorized=100000)
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER),
        {"agenda_authorized": 100000, "max_boundaries": 1,
         "diagnostic_queries": 16},
        tasks=[DEV_SW], propose=propose, dsn=DSN, campaign_seq=61,
        gateway=gateway, model="invb1-reject-double",
        constructor="model")
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "rejected"
    assert "construction failed" in episode["reason"]
    assert episode["construction_calls"] == 4


def _learner_ops(cid: str) -> list:
    from experiments.ad01 import trajectory
    with trajectory._read_conn(DSN) as conn:
        return conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)"
            " ORDER BY id", ("ad01-%s-learner-" % cid,)).fetchall()


def _success_receipts(operation_id: str) -> list:
    from experiments.ad01 import trajectory
    with trajectory._read_conn(DSN) as conn:
        return conn.execute(
            "SELECT receipt_identity FROM receipts"
            " WHERE operation_id = %s AND outcome = 'success'",
            (operation_id,)).fetchall()


def test_c3_trajectory_admits_every_model_call(tmp_path):
    _fresh_db()
    from experiments.ad01 import run_c3_qualification as C3
    from experiments.ad01 import trajectory
    entry = C3.run_trajectory(0, "I", tmp_path / "c3", DSN,
                              agenda_authorized=100000)
    assert entry["acquired"], entry["dispositions"]
    assert entry["use"] == 12
    assert "no-candidate" in entry["dispositions"]
    cid = trajectory.campaign_id(0, "I", 0)
    learner = _learner_ops(cid)
    assert len(entry["dispatched"]) == 3
    for row in learner:
        assert _success_receipts(row["id"]), row["id"]
    with trajectory._read_conn(DSN) as conn:
        construction = conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)",
            ("ad01-%s-b" % cid,)).fetchall()
    construction = [r for r in construction
                    if "-construct-" in r["id"]]
    assert construction
    for row in construction:
        assert _success_receipts(row["id"]), row["id"]
    assert entry["model_calls"] == len(learner) + len(construction)


def test_c3_ir_lists_share_tasks_selection_differs():
    from experiments.ad01 import rotation
    from experiments.ad01 import run_c3_qualification as C3
    for world in (0, 1, 2):
        mine = C3._arm_tasks(world, "I")
        theirs = C3._arm_tasks(world, "R")
        assert sorted(mine) == sorted(theirs)
        assert mine != theirs
        assert theirs == [s["task_id"]
                          for s in rotation.r_schedule(world)[:3]]
        assert any("-sw-" in t for t in mine)
        assert any("-gr-" in t for t in mine)


def test_seen_packet_matches_wire_packet():
    from experiments.ad01 import learner as L
    from experiments.ad01 import packet as P
    seen = P.decision_packet(
        charter=dict(CHARTER), visible=["t"], experience={"observations": []},
        retained=[], remaining={}, curriculum=None,
        boundary={"world": 0, "arm": "I", "seq": 0})
    wire = L.learner_request(dict(CHARTER), ["t"],
                             {"observations": []}, [], {}, None)
    assert set(seen) >= set(wire)
    for key in wire:
        if key == "boundary":
            continue
        assert seen[key] == wire[key], key


def _dev_packet_setup():
    from settlement import development, evidence, store
    from settlement.common import Command
    tag = "invb1-ctx-%s" % uuid.uuid4().hex[:8]
    store.seed_grant(DSN, Command(
        request_id="%s-grant" % tag,
        payload={"version": 1, "charter_text": "ctx",
                 "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(DSN, Command(
        request_id="%s-alloc" % tag,
        payload={"allocation_id": "%s-alloc" % tag, "domain": "ctx",
                 "authorized": 100000, "max_occupancy": 64}))
    store.admit_commitment(DSN, Command(
        request_id="%s-inv" % tag,
        payload={"investigation_id": "%s-inv" % tag,
                 "objective": "objective %s" % tag, "scope": {},
                 "obligations": {"finish": True}}))
    store.acquire_work(DSN, Command(
        request_id="%s-acq" % tag,
        payload={"attempt_id": "%s-att" % tag,
                 "investigation_id": "%s-inv" % tag,
                 "allocation_id": "%s-alloc" % tag}))
    development.observe(
        DSN, Command(request_id="%s-obs" % tag, payload={}),
        episode_id="%s-ep" % tag, investigation_id="%s-inv" % tag,
        trigger_refs=[{"task_id": "t1", "family": "software"}],
        bottleneck="bottleneck t1")
    development.propose(
        DSN, Command(request_id="%s-prop" % tag, payload={}),
        episode_id="%s-ep" % tag, predicted_effect="effect t1",
        competing="other")
    development.admit(
        DSN, Command(request_id="%s-admit" % tag, payload={}),
        episode_id="%s-ep" % tag, reference_version="ref-v1",
        access_policy={"families": ["software"],
                       "applicability": {"family": "software"}},
        allocation_id="%s-alloc" % tag)
    from settlement import db
    from psycopg.types.json import Json
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE development_episodes SET intervention = %s,"
                        " explanations = %s WHERE id = %s",
                        (Json({"action": "narrow the ops"}),
                         Json([{"cause": "extra ops", "support": [],
                                "counterevidence": []}]),
                         "%s-ep" % tag))
            conn.commit()
    receipts = [evidence.register_observation(
        DSN, Command(request_id="%s-obs%d" % (tag, i), payload={}),
        "%s-att" % tag, {"finding": "s%d" % i},
        source_identity="sensor").data["receipt_id"] for i in range(2)]
    evidence.propose_claim(
        DSN, Command(request_id="%s-claim" % tag, payload={}),
        "%s-c" % tag, {"text": "claim holds"},
        scope={"episode": "%s-ep" % tag}, access_label="candidate")
    evidence.admit_warrant(
        DSN, Command(request_id="%s-warrant" % tag, payload={}),
        "%s-w" % tag, "%s-c" % tag, "review", "v1",
        [[(receipt, "observation")] for receipt in receipts],
        scope={"episode": "%s-ep" % tag})
    return tag


def test_development_construct_packet_renders_enforced_contract():
    _fresh_db()
    from settlement import broker, context, development
    from settlement.common import Command, ResultCode, SettlementError
    tag = _dev_packet_setup()
    episode = development.get_episode(DSN, "%s-ep" % tag)
    packet = development._packet_for(
        DSN, episode, "construct",
        contract={
            "invocation": {"entry": "candidate.py",
                           "verify_args": ["--selftest"]},
            "applicability": {"family": "software"},
            "effect": {"sandbox": "local-process"},
            "resource": {},
        })
    assert packet["outcome"] == "ready", packet["gaps"]
    assert "candidate.py" in packet["rendered"]
    assert "--selftest" in packet["rendered"]
    assert context.revalidate_packet(
        DSN, packet["packet_id"])["valid"] is True
    ensured = broker.ensure_operation(
        DSN, operation_id="%s-infer" % tag, effect=broker.MODEL_INFERENCE,
        payload={"model": "invb1-double",
                 "messages": [{"role": "user", "content": "build"}],
                 "max_output_tokens": 64, "deadline_ms": 300_000},
        allocation_id="%s-alloc" % tag)
    assert ensured.code in (ResultCode.APPLIED,
                            ResultCode.ALREADY_APPLIED)
    bound = context.bind_packet_invocation(
        DSN, Command(request_id="%s-bind" % tag, payload={}),
        packet["packet_id"], "%s-infer" % tag)
    assert bound.code in (ResultCode.APPLIED,
                          ResultCode.ALREADY_APPLIED)
    refused = context.bind_packet_invocation(
        DSN, Command(request_id="%s-bind-bad" % tag, payload={}),
        packet["packet_id"], "no-such-operation")
    assert refused.code not in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED)
    assert "binding refused" in refused.detail
