"""AD01-LEARN-E: model-backed learner, CLI seams, fresh-process use.

The learner packet reaches the model through the broker; malformed
learner output refuses without work; the CLI configures learner and
constructor from flags with recording doubles at the same seams; the
use subcommand loads frozen bytes in a fresh process. DB ec02test_ad01c
only for the brokered parts, never ec02test_live.

The use invocation passes `--policy-source`. Since a60798d the use phase
takes its method from a policy or refuses, and `ad01-traj use` holds no
policy of its own, so without the flag every record reads `refused` and
the sandbox-ops accounting this file checks is never charged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "EC02_AD01C_DSN",
    "dbname=ec02test_ad01c host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"

LEARNER_PROPOSAL = {"basis_references": ["obs-ad01-w0-dev-sw-00-seed"],
                    "question": "model chooses the second task",
                    "next_action": {"kind": "development",
                                    "diagnostic": "software",
                                    "task_id": "ad01-w0-dev-sw-01",
                                    "max_queries": 2},
                    "requested_resources": {"diagnostic_queries": 1}}


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="AD01-LEARN construction+campaign")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _allocation(dsn=DSN, tag="alee"):
    import uuid
    from settlement import store
    from settlement.common import Command
    seed = {"allocation_id": "alee-%s-%s" % (tag, uuid.uuid4().hex[:8])}
    store.seed_allocation(
        dsn, Command(request_id="seed-%s" % seed["allocation_id"],
                     payload={"allocation_id": seed["allocation_id"],
                              "domain": "cpu", "authorized": 100000,
                              "max_occupancy": 8}))
    return seed["allocation_id"]


def test_r_first_boundary_packet_matches_admission(monkeypatch):
    from experiments.ad01 import learner as L, trajectory as T
    packets = []

    def model_propose(*args, **kwargs):
        packets.append(kwargs)
        return {"basis_references": ["obs-ad01-w0-dev-sw-00-seed"],
                "next_action": {"kind": "diagnostic", "diagnostic": "software",
                                "task_id": kwargs["curriculum"]}}

    monkeypatch.setattr(L, "model_propose", model_propose)
    propose = L.propose_from_model(
        DSN, cid="ad01-w0-R-00", gateway=None, model="double",
        charter=CHARTER, world=0, arm="R", allocation_id="test")
    out = T.run_campaign(0, "R", CHARTER,
                         {"agenda_authorized": 1000, "max_boundaries": 1, "diagnostic_queries": 16},
                         tasks=[DEV_TASK], propose=propose)
    assert packets[0]["seq"] == 0
    assert packets[0]["curriculum"] == "ad01-w0-dev-sw-00"
    assert packets[0]["curriculum"] != "ad01-w0-dev-gr-00"
    assert out["episodes"][0]["disposition"] == "inspected"


def test_diagnostic_detail_changes_packet():
    from experiments.ad01.learner import learner_request
    observation = {"observation_id": "same", "task_id": DEV_TASK,
                   "capability_id": "seed-sw-greedy", "verdict": "same"}
    packets = [learner_request(CHARTER, [DEV_TASK],
               {"observations": [{**observation, "detail": detail}]},
               [], {}, None) for detail in ("first explanation", "second explanation")]
    assert packets[0] != packets[1]


def test_invalid_action_refuses_before_dependent_work(monkeypatch):
    from experiments.ad01 import trajectory as T
    work = []
    monkeypatch.setattr(T, "run_diagnostic", lambda *args: work.append("diagnostic"))
    proposal = {**LEARNER_PROPOSAL, "next_action": {
        "kind": "development", "task_id": DEV_TASK, "max_queries": "many"}}
    out = T.run_campaign(0, "I", CHARTER,
                         {"agenda_authorized": 1000, "max_boundaries": 1, "diagnostic_queries": 16},
                         tasks=[DEV_TASK], propose=lambda *args: proposal)
    assert work == []
    assert out["episodes"][0]["disposition"] == "no-candidate"


def test_learner_calls_count_toward_campaign_cap():
    _fresh_db()
    from experiments.ad01 import learner as L, trajectory as T
    cid = T.campaign_id(0, "I", 52)
    T.authorize_campaign(DSN, cid, authorized=1000)
    gw = L.RecordingGatewayAdapter([{"text": json.dumps({
        **LEARNER_PROPOSAL, "next_action": {"kind": "diagnostic",
        "diagnostic": "software", "task_id": DEV_TASK}})}])
    propose = L.propose_from_model(
        DSN, cid=cid, gateway=gw, model="double", charter=CHARTER,
        world=0, arm="I", allocation_id=_allocation())
    out = T.run_campaign(0, "I", CHARTER,
                         {"agenda_authorized": 1000, "max_boundaries": 2,
                          "diagnostic_queries": 16, "model_calls": 1},
                         tasks=[DEV_TASK, DEV_TASK], dsn=DSN,
                         campaign_seq=52, propose=propose)
    assert len(gw.calls) == out["model_calls"] == 1
    assert out["stop"]["reason"] == "model call cap reached"
    again = T.resume_campaign(DSN, cid, CHARTER,
                              {"max_boundaries": 2, "diagnostic_queries": 16,
                               "model_calls": 1}, tasks=[DEV_TASK, DEV_TASK],
                              propose=propose)
    assert len(gw.calls) == again["model_calls"] == 1


def test_learner_packet_reaches_model_and_selects():
    _fresh_db()
    from experiments.ad01 import learner as L
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 50)
    trajectory.authorize_campaign(DSN, cid, authorized=1000)
    trajectory.ensure_campaign(DSN, cid, 0, "I", CHARTER,
                               {"agenda_authorized": 1000, "max_boundaries": 6,
                                "diagnostic_queries": 16})
    gw = L.RecordingGatewayAdapter([{"text": json.dumps(LEARNER_PROPOSAL)}])
    allocation = _allocation()
    proposal = L.model_propose(
        DSN, cid=cid, seq=0, gateway=gw, model="ad01-learner-double",
        charter=CHARTER, visible=[DEV_TASK, "ad01-w0-dev-sw-01"],
        experience={"observations": [
            {"observation_id": "obs-ad01-w0-dev-sw-00-seed",
             "task_id": DEV_TASK, "capability_id": "seed-sw-greedy",
             "verdict": "unmeasured"}]},
        retained=[], remaining={"dev_episodes": 3},
        curriculum=None, allocation_id=allocation)
    assert proposal["next_action"]["task_id"] == "ad01-w0-dev-sw-01"
    [call] = gw.calls
    packet = json.loads(call.messages[0]["content"].split("\n", 1)[1])
    assert packet["charter"]["objective"] == CHARTER["objective"]
    assert packet["visible_opportunities"] == [DEV_TASK,
                                               "ad01-w0-dev-sw-01"]
    assert packet["observations"][0]["verdict"] == "unmeasured"
    assert packet["curriculum_item"] is None
    assert packet["remaining"] == {"dev_episodes": 3}


def test_malformed_learner_output_refuses():
    _fresh_db()
    from experiments.ad01 import learner as L
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 51)
    trajectory.authorize_campaign(DSN, cid, authorized=1000)
    trajectory.ensure_campaign(DSN, cid, 0, "I", CHARTER,
                               {"agenda_authorized": 1000, "max_boundaries": 6,
                                "diagnostic_queries": 16})
    gw = L.RecordingGatewayAdapter([{"text": "not json at all"}])
    with pytest.raises(L.LearnerRefused):
        L.model_propose(
            DSN, cid=cid, seq=0, gateway=gw, model="ad01-learner-double",
            charter=CHARTER, visible=[DEV_TASK],
            experience={"observations": []}, retained=[], remaining={},
            curriculum=None, allocation_id=_allocation())
    assert len(gw.calls) == 1


def test_cli_run_doubled_and_use_fresh_process(tmp_path):
    _fresh_db()
    from experiments.ad01 import trajectory
    member = {"capability_id": "acquired-sw-alee01",
              "method_source": (
                  "def acquired_order(task, oracle, max_queries=16):\n"
                  "    return reducers.reduce_software(task, oracle,"
                  " method=\"greedy\", max_queries=max_queries)\n"),
              "entry": "acquired_order",
              "params": {"max_queries": 16},
              "scope": {"family": "software"}, "authored": False,
              "qualified_on": DEV_TASK,
              "source_digest": "",
              "lineage": {"campaign_id": "alee", "lineage": 1,
                          "init_operation": "op-init",
                          "repair_operation": None,
                          "init_failure": None, "calls_made": 1}}
    import hashlib
    member["source_digest"] = hashlib.sha256(
        member["method_source"].encode("utf-8")).hexdigest()
    campaign = {"campaign_id": "alee",
                "episodes": [{"disposition": "retained",
                               "executable": member}]}
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    trajectory.authorize_campaign(DSN, "alee", authorized=1000)
    authority = trajectory.ensure_campaign(DSN, "alee", 0, "I", CHARTER,
                                           {"agenda_authorized": 1000})
    accounting_path = tmp_path / "accounting.json"
    policy_path = tmp_path / "policy.py"
    policy_path.write_text(
        "def STEP(view, state):\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': view['task_content']['task_id'],\n"
        "                      'inputs': {'method_id': 'acquired-sw-alee01',\n"
        "                                 'max_queries': 16},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 16}},\n"
        "            'state': {'chosen': 'acquired-sw-alee01'}}\n")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--world", "0", "--arm", "I",
         "--tasks", "ad01-w0-within-sw-00", "--dsn", DSN,
         "--allocation-id", authority["allocation_id"],
         "--policy-source", str(policy_path),
         "--accounting-out", str(accounting_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    [record] = json.loads(proc.stdout)
    assert record["executed"] == "acquired-sw-alee01"
    assert record["executed_source"] == member["method_source"]
    assert record["fallback_reason"] == ""
    accounting = json.loads(accounting_path.read_text())
    assert len(record["operation_ids"]) == 1
    assert record["costs"]["sandbox_ops"] == accounting["use"]["sandbox_ops"] == 1
    assert accounting["total"]["sandbox_ops"] == 1
    assert accounting["acquisition"]["sandbox_ops"] == 0
    run = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "run",
         "--dsn", DSN, "--world", "0", "--arm", "I", "--seq", "60",
         "--agenda-authorized", "1000", "--max-boundaries", "1", "--tasks", DEV_TASK],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["campaign_id"] == "ad01-w0-I-60"
    assert out["episodes"][0]["disposition"] == "inspected"
