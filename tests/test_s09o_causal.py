"""Causal discrimination: bound STEP bytes must change durable decisions and effects."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = "s09o_causal"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"
CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 4, "diagnostic_queries": 16,
        "model_calls": 20}
SW_TASK = "ad01-w0-dev-sw-00"

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

CANDIDATE_TEMPLATE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    if state.get('causal_done'):\n"
    "        action = {'kind': 'stop', 'target': target,\n"
    "                  'inputs': {'reason': 'causal test complete'},\n"
    "                  'evidence_refs': [], 'requested_resources': {}}\n"
    "    else:\n"
    "        action = {'kind': '%s', 'target': target,\n"
    "                  'inputs': {'method_id': 'seed-sw-greedy',\n"
    "                             'max_queries': 4},\n"
    "                  'evidence_refs': [],\n"
    "                  'requested_resources': {'queries': 4}}\n"
    "    return {'action': action, 'state': {'causal_done': True}}\n"
)
CONSTRUCT_CANDIDATE = CANDIDATE_TEMPLATE % "construct_method"
USE_CANDIDATE = CANDIDATE_TEMPLATE % "use_method"
WHITESPACE_CANDIDATE = CONSTRUCT_CANDIDATE + "\n"


@pytest.fixture(scope="module")
def store():
    assert DB.startswith("s09o_causal")
    subprocess.run(["createdb", "-h", "/var/run/postgresql", "-U", "ubuntu", DB],
                   check=True, capture_output=True, text=True, timeout=60)
    try:
        from settlement import db
        db.apply_migrations(DSN, MIGRATIONS)
        yield DSN
    finally:
        subprocess.run(["dropdb", "-h", "/var/run/postgresql", "-U", "ubuntu", DB],
                       check=True, capture_output=True, text=True, timeout=60)


class Provider:
    label = "S09O-CAUSAL-PROVIDER"

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
                             json.dumps({"entry": source, "notes": "causal"}),
                             {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src", ROOT / "experiments")
    return env


def _consumer(dsn, cid, source):
    from experiments.ad01 import policy_step, trajectory
    from experiments.ad01.agenda_policy import step_policy_consumer
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return step_policy_consumer(
        policy_step.make_policy_artifact(source, origin="authored-control"),
        dsn=dsn, cid=cid, charter=CHARTER, world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        model="causal-double")


def _run(store, seq, candidate):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", seq)
    provider = Provider([candidate])
    out = trajectory.run_campaign(
        0, "I", CHARTER, CAPS, tasks=[SW_TASK] * 4,
        campaign_seq=seq, dsn=store,
        consumer=_consumer(store, cid, INCUMBENT_SOURCE), constructor="model",
        gateway=provider, model="causal-double")
    return out, provider


def _rows(store, cid):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(store) as conn:
        return conn.execute(
            "SELECT * FROM s09_policy_state"
            " WHERE investigation_id = %s ORDER BY seq", (cid,)).fetchall()


def _action_kinds(store, cid):
    kinds = []
    for row in _rows(store, cid):
        output = dict(row["policy_output"] or {})
        kinds.extend(result["action"]["kind"]
                     for result in output.get("results", []))
    return kinds


def _candidate_digest(store, out):
    from experiments.ad01 import records
    revision = out["episodes"][1]
    freeze = records.load_freeze(store, revision["proposal_id"])
    assert revision["disposition"] == "bound"
    assert freeze["candidate_digest"] == revision["bound_digest"]
    return freeze["candidate_digest"]


def _effect_episode(store, cid, seq=2):
    row = next(row for row in _rows(store, cid) if row["seq"] == seq)
    record = dict(row["effect_record"] or {})
    return dict(record["episode"])


def test_different_bound_policies_produce_different_decisions(store):
    construct, construct_provider = _run(store, 0, CONSTRUCT_CANDIDATE)
    use, use_provider = _run(store, 1, USE_CANDIDATE)
    construct_digest = _candidate_digest(store, construct)
    use_digest = _candidate_digest(store, use)
    construct_kinds = _action_kinds(store, construct["campaign_id"])
    use_kinds = _action_kinds(store, use["campaign_id"])
    assert construct_kinds == ["diagnose", "propose_revision",
                               "construct_method", "stop"]
    assert use_kinds == ["diagnose", "propose_revision", "use_method", "stop"]
    assert construct_kinds != use_kinds
    construct_rows = _rows(store, construct["campaign_id"])
    use_rows = _rows(store, use["campaign_id"])
    construct_candidate_rows = [row for row in construct_rows if row["seq"] >= 2]
    use_candidate_rows = [row for row in use_rows if row["seq"] >= 2]
    assert [dict(row["policy_output"])["source_digest"]
            for row in construct_candidate_rows] == [construct_digest, construct_digest]
    assert [dict(row["policy_output"])["source_digest"]
            for row in use_candidate_rows] == [use_digest, use_digest]
    assert construct_digest != use_digest
    construct_effect = _effect_episode(store, construct["campaign_id"])
    use_effect = _effect_episode(store, use["campaign_id"])
    assert construct_effect["disposition"] == "rejected"
    assert construct_effect["construction_calls"] == 4
    assert use_effect["kind"] == "use_method"
    assert use_effect["construction_calls"] == 0
    assert construct_provider.calls
    assert len(use_provider.calls) == 1


def test_perturbing_candidate_bytes_changes_the_executed_decision(store):
    first, _first_provider = _run(store, 2, CONSTRUCT_CANDIDATE)
    second, _second_provider = _run(store, 3, USE_CANDIDATE)
    first_digest = _candidate_digest(store, first)
    second_digest = _candidate_digest(store, second)
    assert first_digest != second_digest
    first_release = first["episodes"][1]["release_id"]
    second_release = second["episodes"][1]["release_id"]
    assert first_release != second_release
    assert _action_kinds(store, first["campaign_id"]) == [
        "diagnose", "propose_revision", "construct_method", "stop"]
    assert _action_kinds(store, second["campaign_id"]) == [
        "diagnose", "propose_revision", "use_method", "stop"]
    second_rows = [row for row in _rows(store, second["campaign_id"])
                   if row["seq"] >= 2]
    assert [dict(row["policy_output"])["source_digest"]
            for row in second_rows] == [second_digest, second_digest]
    assert all(dict(row["policy_output"])["source_digest"] != first_digest
               for row in second_rows)


def test_recorded_decision_sequence_is_not_reproducible_from_the_digest_alone(store):
    first, _first_provider = _run(store, 4, CONSTRUCT_CANDIDATE)
    second, _second_provider = _run(store, 5, WHITESPACE_CANDIDATE)
    first_digest = _candidate_digest(store, first)
    second_digest = _candidate_digest(store, second)
    assert first_digest != second_digest
    assert _action_kinds(store, first["campaign_id"]) == [
        "diagnose", "propose_revision", "construct_method", "stop"]
    assert _action_kinds(store, second["campaign_id"]) == [
        "diagnose", "propose_revision", "construct_method", "stop"]
    assert _action_kinds(store, first["campaign_id"]) == \
        _action_kinds(store, second["campaign_id"])
    assert _effect_episode(store, first["campaign_id"])["disposition"] == "rejected"
    assert _effect_episode(store, second["campaign_id"])["disposition"] == "rejected"
    assert _effect_episode(store, first["campaign_id"])["construction_calls"] == 4
    assert _effect_episode(store, second["campaign_id"])["construction_calls"] == 4
    assert hashlib.sha256(CONSTRUCT_CANDIDATE.encode()).hexdigest() == first_digest
    assert hashlib.sha256(WHITESPACE_CANDIDATE.encode()).hexdigest() == second_digest
