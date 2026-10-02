"""INV-C1 M1: one public lifecycle owns packets, admission, correction, stopping.

Real Postgres (inv_c1_lifecycle, never live) in every brokered test.
Doubles sit at the provider seam only: a scripted gateway answers learner
and construction operations; every call travels through broker ensure,
dispatch and settled receipts. Each test names a literal durable outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DSN = os.environ.get(
    "INV_C1_DSN",
    "dbname=inv_c1_lifecycle host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 96,
        "model_calls": 60, "construction_tokens": 512,
        "agenda_authorized": 100000}
MODEL = "inv-c1-double"
SW0 = "ad01-w0-dev-sw-00"
SW1 = "ad01-w0-dev-sw-01"
GR0 = "ad01-w0-dev-gr-00"


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="INV-C1 integrated lifecycle gate")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _learner_text(proposal: dict) -> str:
    return json.dumps(proposal, sort_keys=True)


def _diagnostic_text(task_id: str, family: str) -> str:
    return _learner_text({
        "basis_references": ["obs-%s-seed" % task_id],
        "question": "diagnose %s" % task_id,
        "next_action": {"kind": "diagnostic", "diagnostic": family,
                        "task_id": task_id},
        "requested_resources": {"diagnostic_queries": 1}})


def _development_text(task_id: str, family: str,
                      max_queries: int = 8) -> str:
    return _learner_text({
        "basis_references": ["obs-%s-seed" % task_id],
        "question": "develop %s" % task_id,
        "next_action": {"kind": "development", "diagnostic": family,
                        "task_id": task_id, "max_queries": max_queries},
        "requested_resources": {"diagnostic_queries": 1}})


class ScriptedGateway:
    """Provider-seam double with learner/construction streams in order."""

    label = "INV-C1-SCRIPTED"

    def __init__(self, learner_scripts, construction_scripts=()):
        self._learner = list(learner_scripts)
        self._construction = list(construction_scripts)
        self._used = {"learner": 0, "construction": 0}
        self.calls = []
        self.prompts = {}

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        self.calls.append(request)
        stream = ("learner" if "-learner-" in request.operation_id
                  else "construction")
        scripts = (self._learner if stream == "learner"
                   else self._construction)
        position = self._used[stream]
        self._used[stream] += 1
        script = scripts[min(position, len(scripts) - 1)]
        text = script.get("text", "") if isinstance(script, dict) \
            else script
        try:
            prompt = request.messages[-1]["content"]
        except (IndexError, TypeError, KeyError):
            prompt = ""
        self.prompts[request.operation_id] = prompt
        return ModelResponse(
            request.operation_id, text, {"simulated": True}, Usage(),
            "stop")

    def cancel(self, operation_id):
        return False


def _study(ids):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(DSN) as conn:
        return conn.execute(
            "SELECT authorized FROM allocations WHERE id = %s",
            (trajectory._alloc_id(ids),)).fetchone()


def test_shared_consumer_decides_both_domains():
    from experiments.ad01 import agenda_policy, trajectory
    _fresh_db()
    tasks = [SW0, GR0]
    gateway = ScriptedGateway(
        [_diagnostic_text(SW0, "software"),
         _diagnostic_text(GR0, "graph")])
    cid = trajectory.campaign_id(0, "I", 21)
    trajectory.authorize_campaign(DSN, trajectory.campaign_id(0, "I", 21),
    authorized=100000)
    seed = trajectory.ensure_campaign(
        DSN, cid, 0, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks))
    consumer = agenda_policy.DecisionConsumer(
        dsn=DSN, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=seed["allocation_id"], study_root=cid)
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks),
        campaign_seq=21, dsn=DSN, consumer=consumer,
        gateway=gateway, model=MODEL)
    assert [e["disposition"] for e in campaign["episodes"]] == \
        ["inspected", "inspected"]
    assert consumer.decided == [SW0, GR0]
    assert campaign["study_root"] == cid


def test_disconnected_consumer_refuses_both_domains():
    from experiments.ad01 import agenda_policy, trajectory
    _fresh_db()
    tasks = [SW0, GR0]
    gateway = ScriptedGateway(
        [_diagnostic_text(SW0, "software"),
         _diagnostic_text(GR0, "graph")])
    trajectory.authorize_campaign(
        DSN, trajectory.campaign_id(0, "I", 22), authorized=100000)
    consumer = agenda_policy.disconnected_consumer("double-unplugged")
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks),
        campaign_seq=22, dsn=DSN, consumer=consumer,
        gateway=gateway, model=MODEL)
    assert [e["disposition"] for e in campaign["episodes"]] == \
        ["no-candidate", "no-candidate"]
    for episode in campaign["episodes"]:
        assert "double-unplugged" in episode["fallback_reason"]
    assert gateway.calls == []


def test_rejected_proposal_corrected_on_same_target():
    from experiments.ad01 import trajectory
    calls = []

    def flaky(seen, asked):
        prior = seen.get("prior_failure")
        calls.append({"task": (seen["observations"][0]["task_id"]),
                      "prior": prior})
        target = seen["observations"][0]["task_id"]
        family = "software"
        if prior is None:
            return {"basis_references": ["obs-invented-999"],
                    "question": "leap at %s" % target,
                    "next_action": {"kind": "diagnostic",
                                    "diagnostic": family,
                                    "task_id": target},
                    "requested_resources": {"diagnostic_queries": 1}}
        seed = seen["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "diagnose %s again" % target,
                "next_action": {"kind": "diagnostic",
                                "diagnostic": family,
                                "task_id": target},
                "requested_resources": {"diagnostic_queries": 1}}

    seed_obs = {"observation_id": "obs-%s-seed" % SW0,
                "task_id": SW0, "capability_id": "seed-sw-greedy",
                "verdict": "unmeasured"}
    experience = {"observations": [], "retained": [],
                  "remaining": {"queries": 16, "model_calls": 60}}
    state = {"dev_episodes": 0, "model_calls": 0,
             "construction_calls": 0}
    observation, episode, _spend = trajectory._run_boundary(
        SW0, "seed-sw-greedy",
        {"diagnostic_queries": 16, "model_calls": 60}, seed_obs,
        propose=flaky, charter={"objective": "x"},
        boundary={"world": 0, "arm": "I", "seq": 0},
        experience=experience, state=state,
        journal={"dsn": None, "cid": None, "decision": None})
    assert episode["disposition"] == "inspected"
    assert [c["task"] for c in calls] == [SW0, SW0]
    assert calls[0]["prior"] is None
    assert "invented basis references" in calls[1]["prior"]["reason"]


def test_correction_budget_survives_restart():
    from experiments.ad01 import trajectory

    def stubborn(seen, asked):
        target = seen["observations"][0]["task_id"]
        return {"basis_references": ["obs-invented-999"],
                "question": "leap at %s" % target,
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": target},
                "requested_resources": {"diagnostic_queries": 1}}

    _fresh_db()
    trajectory.authorize_campaign(
        DSN, trajectory.campaign_id(0, "I", 23), authorized=100000)
    first = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
        propose=stubborn, campaign_seq=23, dsn=DSN)
    assert [e["disposition"] for e in first["episodes"]] == \
        ["no-candidate"]
    assert "correction" in first["episodes"][0]["fallback_reason"]

    def must_not_run(seen, asked):
        pytest.fail("correction budget must survive restart")

    resumed = trajectory.resume_campaign(
        DSN, first["campaign_id"], dict(CHARTER), dict(CAPS),
        tasks=[SW0], propose=must_not_run)
    assert [e["disposition"] for e in resumed["episodes"]] == \
        ["no-candidate"]
    assert "correction" in resumed["episodes"][0]["fallback_reason"]


def test_cli_runs_both_domains(tmp_path):
    from experiments.ad01 import trajectory
    from test_invc1_method_envelope import ENVELOPE_SW_SOURCE
    _fresh_db()
    recordings = [
        {"text": _development_text(SW0, "software")},
        {"text": json.dumps({"entry": ENVELOPE_SW_SOURCE,
                             "notes": "independent sweep."})},
        {"text": _development_text(GR0, "graph")},
        {"text": json.dumps({"entry": ENVELOPE_SW_SOURCE,
                             "notes": "independent sweep."})},
    ]
    rec_path = tmp_path / "inv-c1-cli-recordings.json"
    rec_path.write_text(json.dumps(recordings) + "\n")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "experiments.ad01.cli", "run",
             "--dsn", DSN, "--world", "0", "--arm", "I", "--seq", "24",
             "--agenda-authorized", "100000",
             "--tasks", "%s,%s" % (SW0, GR0),
             "--recordings", str(rec_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONPATH": "%s:%s/src" % (ROOT, ROOT)})
    finally:
        rec_path.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert [b["task_id"] for b in out["boundaries"]] == [SW0, GR0]
    assert _study(out["campaign_id"]) is not None


def test_cli_refuses_off_curriculum_proposals(tmp_path):
    from experiments.ad01 import rotation
    _fresh_db()
    schedule = rotation.r_schedule(0)
    first, second = schedule[0]["task_id"], schedule[1]["task_id"]
    first_family = "software" if "-sw-" in first else "graph"
    second_family = "software" if "-sw-" in second else "graph"

    def _poach(seed_task: str, target: str, family: str) -> dict:
        return {"text": _learner_text({
            "basis_references": ["obs-%s-seed" % seed_task],
            "question": "poach %s" % target,
            "next_action": {"kind": "development",
                            "diagnostic": family,
                            "task_id": target, "max_queries": 4},
            "requested_resources": {"diagnostic_queries": 1}})}

    recordings = [_poach(first, second, second_family)] * 3 + \
        [_poach(second, first, first_family)] * 3
    rec_path = tmp_path / "inv-c1-cli-refusal.json"
    rec_path.write_text(json.dumps(recordings) + "\n")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "experiments.ad01.cli", "run",
             "--dsn", DSN, "--world", "0", "--arm", "R", "--seq", "25",
             "--agenda-authorized", "100000",
             "--tasks", "%s,%s" % (first, second),
             "--recordings", str(rec_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONPATH": "%s:%s/src" % (ROOT, ROOT)})
    finally:
        rec_path.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert [e["disposition"] for e in out["episodes"]] == \
        ["no-candidate", "no-candidate"]
    for episode in out["episodes"]:
        assert "curriculum" in episode["fallback_reason"]


def test_construction_needs_parent_study_authority():
    from experiments.ad01 import construct, trajectory
    from test_invc1_method_envelope import ENVELOPE_SW_SOURCE
    _fresh_db()
    gateway = ScriptedGateway(
        [], [{"text": json.dumps({"entry": ENVELOPE_SW_SOURCE,
                                  "notes": "no parent."})}])
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    with pytest.raises(construct.ConstructionFailed,
                       match="study authority"):
        construct.construct_method(
            DSN, campaign_id="ad01-w0-I-77", task=task,
            experience={"observations": [],
                        "boundary": {"seq": 0}},
            budget={"max_output_tokens": 512, "max_queries": 16,
                    "model_calls": 4},
            gateway=gateway, model=MODEL)


def test_study_root_threads_to_construction():
    from experiments.ad01 import agenda_policy, trajectory
    from test_invc1_method_envelope import ENVELOPE_SW_SOURCE
    _fresh_db()
    gateway = ScriptedGateway(
        [_development_text(SW0, "software", 8)],
        [{"text": json.dumps({"entry": ENVELOPE_SW_SOURCE,
                              "notes": "threaded."})}])
    cid = trajectory.campaign_id(0, "I", 26)
    trajectory.authorize_campaign(DSN, trajectory.campaign_id(0, "I", 26),
                                    authorized=100000,
                                    study_root="inv-c1-study")
    seed = trajectory.ensure_campaign(
        DSN, cid, 0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
        study_root="inv-c1-study")
    consumer = agenda_policy.DecisionConsumer(
        dsn=DSN, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=seed["allocation_id"],
        study_root="inv-c1-study")
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
        campaign_seq=26, dsn=DSN, consumer=consumer,
        gateway=gateway, model=MODEL, constructor="model",
        study_root="inv-c1-study")
    assert campaign["study_root"] == "inv-c1-study"
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "retained"
    assert episode["executable"]["construction"]["study_root"] == \
        "inv-c1-study"
    with trajectory._read_conn(DSN) as conn:
        row = conn.execute(
            "SELECT parent_id FROM allocations WHERE id = %s",
            ("ad01-%s-b0-%s-construct" % (cid, SW0),)).fetchone()
    assert row is not None and row["parent_id"] == \
        trajectory._alloc_id(cid)
