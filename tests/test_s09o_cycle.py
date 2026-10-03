from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
TOKEN = "cycle"
CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 2, "diagnostic_queries": 16,
        "model_calls": 20}
SW_TASK = "ad01-w0-dev-sw-00"
GR_TASK = "ad01-w0-dev-gr-00"

INCUMBENT_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    if state.get('observed'):\n"
    "        action = {'kind': 'propose_revision', 'target': target,\n"
    "                  'inputs': {'motivation': 'improve'},\n"
    "                  'evidence_refs': [view['observations'][0]['observation_id']],\n"
    "                  'requested_resources': {}}\n"
    "    else:\n"
    "        action = {'kind': 'diagnose', 'target': target,\n"
    "                  'inputs': {'diagnostic': view['task_content']['family']},\n"
    "                  'evidence_refs': [], 'requested_resources': {'queries': 1}}\n"
    "    return {'action': action, 'state': {'observed': True}}\n"
)
GOOD_CANDIDATE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    action = {'kind': 'construct_method', 'target': target,\n"
    "              'inputs': {'max_queries': 4}, 'evidence_refs': [],\n"
    "              'requested_resources': {'queries': 4}}\n"
    "    return {'action': action, 'state': state}\n"
)
REJECTED_CANDIDATE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    action = {'kind': 'diagnose', 'target': target,\n"
    "              'inputs': {'diagnostic': view['task_content']['family']},\n"
    "              'evidence_refs': [], 'requested_resources': {'queries': 1}}\n"
    "    return {'action': action, 'state': state}\n"
)


def _database_name(dsn):
    return [field for field in dsn.split() if field.startswith("dbname=")][0][7:]


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    with iso.disposable_db(TOKEN) as database:
        from settlement import db
        assert "live" not in database.name
        db.apply_migrations(database.dsn, MIGRATIONS)
        yield database.dsn


class Provider:
    label = "S09O-CYCLE-PROVIDER"

    def __init__(self, sources):
        from settlement.gateway import Usage
        self.sources = list(sources)
        self.calls = []
        self.usage = Usage(input_tokens=11, output_tokens=7)

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        source = self.sources[min(len(self.calls) - 1, len(self.sources) - 1)]
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source, "notes": "cycle"}),
                             {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src", ROOT / "experiments")
    return env


def _consumer(dsn, cid, source, gateway=None):
    from experiments.ad01 import policy_step, trajectory
    from experiments.ad01.agenda_policy import step_policy_consumer
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return step_policy_consumer(
        policy_step.make_policy_artifact(source, origin="authored-control"),
        dsn=dsn, cid=cid, charter=CHARTER, world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        gateway=gateway)


def _run(store, seq, task, candidate, continue_after=False):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", seq)
    provider = Provider([candidate])
    run_caps = dict(CAPS, max_boundaries=3 if continue_after else 2)
    run_tasks = [task] * (3 if continue_after else 2)
    out = trajectory.run_campaign(
        0, "I", CHARTER, run_caps, tasks=run_tasks, campaign_seq=seq, dsn=store,
        consumer=_consumer(store, cid, INCUMBENT_SOURCE), constructor="model",
        gateway=provider, model="cycle-double")
    return out, provider


def test_successful_binding_is_public_and_exact(store):
    from experiments.ad01 import records, selection
    out, provider = _run(store, 0, SW_TASK, GOOD_CANDIDATE)
    episode = out["episodes"][1]
    assert episode["disposition"] == "bound"
    assert episode["assessment_status"] == "complete"
    assert len(provider.calls) == 1
    binding = selection.active_binding_for(
        store, "software", release_id=episode["release_id"])
    assert binding is not None
    provenance = selection.binding_provenance(binding)
    freeze = records.load_freeze(store, episode["proposal_id"])
    assert provenance["candidate_digest"] == freeze["candidate_digest"]
    assert episode["bound_digest"] == freeze["candidate_digest"]


def test_rejected_candidate_has_no_release(store):
    from experiments.ad01 import selection
    out, _provider = _run(store, 1, SW_TASK, REJECTED_CANDIDATE)
    episode = out["episodes"][1]
    assert episode["disposition"] == "rejected"
    assert episode["fallback"] == "incumbent"
    assert selection.active_binding_for(
        store, "software", release_id="ad01-%s-policy-%s" % (
            out["campaign_id"], episode["freeze"]["candidate_digest"][:12])) is None


def test_invalid_constructor_is_unavailable(store):
    out, provider = _run(store, 2, SW_TASK, "not a STEP source")
    episode = out["episodes"][1]
    assert episode["disposition"] == "unavailable"
    assert episode["disposition"] != "rejected"
    assert provider.calls


def test_fresh_process_resolves_bound_policy_bytes(store, tmp_path):
    from experiments.ad01 import records, selection, trajectory
    out, _provider = _run(store, 3, SW_TASK, GOOD_CANDIDATE,
                          continue_after=True)
    episode = out["episodes"][1]
    assert episode["disposition"] == "bound"
    freeze = records.load_freeze(store, episode["proposal_id"])
    digest = freeze["candidate_digest"]
    probe = tmp_path / "resume_probe.py"
    probe.write_text(
        "import hashlib, json, sys\n"
        "from experiments.ad01 import trajectory\n"
        "dsn, cid, release, task = sys.argv[1:]\n"
        "out = trajectory.resume_campaign(dsn, cid, %r, %r, policy_release=release)\n"
        "row = trajectory._s09_get(dsn, cid, 2)\n"
        "print(json.dumps({'out': out, 'digest': row['policy_output']['source_digest']}))\n"
        % (CHARTER, CAPS))
    proc = subprocess.run(
        [sys.executable, str(probe), store, out["campaign_id"],
         episode["release_id"], SW_TASK], cwd=str(ROOT), env=_env(),
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    fresh = json.loads(proc.stdout)
    assert fresh["digest"] == digest
    binding = selection.active_binding_for(
        store, "software", release_id=episode["release_id"])
    assert selection.binding_provenance(binding)["candidate_digest"] == digest


def test_both_domains_bind(store):
    from experiments.ad01 import selection
    for seq, task, family in ((4, SW_TASK, "software"), (5, GR_TASK, "graph")):
        out, _provider = _run(store, seq, task, GOOD_CANDIDATE)
        episode = out["episodes"][1]
        assert episode["disposition"] == "bound"
        assert selection.active_binding_for(
            store, family, release_id=episode["release_id"]) is not None


def test_consumer_and_release_are_ambiguous(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 6)
    with pytest.raises(ValueError, match="mutually exclusive"):
        trajectory.run_campaign(
            0, "I", CHARTER, CAPS, tasks=[SW_TASK], campaign_seq=6,
            dsn=store, consumer=_consumer(store, cid, INCUMBENT_SOURCE),
            policy_release="missing")


def test_missing_release_is_durable_refusal(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 7)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    out = trajectory.run_campaign(
        0, "I", CHARTER, CAPS, tasks=[SW_TASK], campaign_seq=7, dsn=store,
        policy_release="missing-release")
    assert out["episodes"] == []
    assert "no active policy binding" in out["stop"]["reason"]


REQUEST_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    if not state.get('asked'):\n"
    "        action = {'kind': 'request_model', 'target': target,\n"
    "                  'inputs': {'prompt': 'continue', 'max_output_tokens': 8},\n"
    "                  'evidence_refs': [], 'requested_resources': {'model_calls': 1}}\n"
    "        return {'action': action, 'state': {'asked': True}}\n"
    "    action = {'kind': 'diagnose', 'target': target,\n"
    "              'inputs': {'diagnostic': 'software'}, 'evidence_refs': [],\n"
    "              'requested_resources': {'queries': 1}}\n"
    "    return {'action': action, 'state': state}\n"
)


DISCONNECTED_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    action = {'kind': 'request_model', 'target': target,\n"
    "              'inputs': {'prompt': 'continue', 'max_output_tokens': 8},\n"
    "              'evidence_refs': [], 'requested_resources': {'model_calls': 1}}\n"
    "    return {'action': action, 'state': state}\n"
)


def test_interrupted_accepted_effect_is_reconciled_once(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 8)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    trajectory.ensure_campaign(
        store, cid, 0, "I", CHARTER, CAPS, tasks=[SW_TASK])
    decision = {"basis_references": ["obs-%s-seed" % SW_TASK],
                "question": "diagnose", "next_action": {
                    "kind": "diagnostic", "diagnostic": "software",
                    "task_id": SW_TASK}}
    trajectory._s09_accept(store, cid, 0, decision=decision,
                           provenance="test-interrupt",
                           driver_version="s09-m1")
    trajectory.record_decision(store, cid, 0, decision)
    resumed = trajectory.resume_campaign(store, cid, CHARTER, CAPS)
    assert len(resumed["boundaries"]) == 1
    assert resumed["boundaries"][0]["decision"] == decision
    assert trajectory._s09_get(store, cid, 0)["status"] == "incorporated"


def test_settled_receipt_is_reused_at_exhausted_allowance(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 9)
    provider = Provider(["settled response"])
    consumer = _consumer(store, cid, REQUEST_SOURCE, gateway=provider)
    first = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1,
                           "diagnostic_queries": 16, "model_calls": 1},
        tasks=[SW_TASK], campaign_seq=9, dsn=store, consumer=consumer,
        gateway=provider, constructor="seed", model="cycle-double")
    assert len(provider.calls) == 1
    resumed = trajectory.resume_campaign(
        store, cid, CHARTER, {"max_boundaries": 1,
                              "diagnostic_queries": 16, "model_calls": 0})
    assert resumed["boundaries"][0]["observation_id"] == \
        first["boundaries"][0]["observation_id"]
    assert len(provider.calls) == 1


def test_gateway_disconnect_is_durable_refusal(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 10)
    consumer = _consumer(store, cid, DISCONNECTED_SOURCE)
    out = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1,
                           "diagnostic_queries": 16, "model_calls": 1},
        tasks=[SW_TASK], campaign_seq=10, dsn=store, consumer=consumer)
    assert len(out["boundaries"]) == 1
    episode = out["episodes"][0]
    assert episode["disposition"] == "no-candidate"
    assert "policy step" in episode["fallback_reason"]
    assert trajectory._s09_get(store, cid, 0)["status"] == "incorporated"


def test_cycle_parser_has_no_consumer_injection():
    from experiments.ad01 import cli
    with pytest.raises(SystemExit):
        cli.main(["cycle", "--help"])


def test_the_store_is_one_this_run_created(store):
    """A dropped store must never be a store somebody else still runs on.

    A fixed database name is shared state: any other suite that creates the
    same name destroys this run's rows, and the failures read as product
    defects in crash-resume and receipt reuse rather than as the collision
    they are. The name carries a per-run token, so only this run's name is
    ever destroyed.
    """
    name = _database_name(store)

    assert name.startswith("s09iso_cycle_"), name
    assert store.count(name) == 1, name


def test_the_store_survives_a_second_module_scope(store):
    """Re-deriving the store must not reuse this module's database.

    The collision that produced the original failures was two runs of this
    file at once. Each run's fixture mints its own name, so a second fixture
    can never observe or destroy the first one's database.
    """
    from experiments.ad01 import s09_run_isolation as iso

    other = iso.create_disposable_db(TOKEN)

    assert other.name != _database_name(store)
    assert other.name.startswith("s09iso_cycle_")
    iso.drop_disposable_db(other)
