from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "o-export"
MIGRATIONS = ROOT / "migrations"
CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 3, "diagnostic_queries": 16,
        "model_calls": 20}
TASK = "ad01-w0-dev-sw-00"

INCUMBENT_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    if state.get('observed'):\n"
    "        action = {'kind': 'propose_revision', 'target': target,\n"
    "                  'inputs': {'motivation': 'improve'},\n"
    "                  'evidence_refs': [view['observations'][0]['observation_id']], 'requested_resources': {}}\n"
    "    else:\n"
    "        action = {'kind': 'diagnose', 'target': target,\n"
    "                  'inputs': {'diagnostic': 'software'},\n"
    "                  'evidence_refs': [], 'requested_resources': {}}\n"
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
    "              'inputs': {'diagnostic': 'software'}, 'evidence_refs': [],\n"
    "              'requested_resources': {'queries': 1}}\n"
    "    return {'action': action, 'state': state}\n"
)


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


class Provider:
    def __init__(self, source):
        from settlement.gateway import Usage
        self.source = source
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
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": self.source}), {},
                             self.usage, "stop")

    def cancel(self, operation_id):
        return False


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src", ROOT / "experiments")
    return env


def _consumer(dsn, cid):
    from experiments.ad01 import policy_step, trajectory
    from experiments.ad01.agenda_policy import step_policy_consumer
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return step_policy_consumer(
        policy_step.make_policy_artifact(INCUMBENT_SOURCE,
                                         origin="authored-control"),
        dsn=dsn, cid=cid, charter=CHARTER, world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        model="export-double")


def _run(store, seq, source):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", seq)
    provider = Provider(source)
    run_caps = dict(CAPS)
    run_tasks = [TASK] * 3
    if source == "not STEP source":
        run_caps["max_boundaries"] = 2
        run_tasks = [TASK] * 2
    out = trajectory.run_campaign(
        0, "I", CHARTER, run_caps, tasks=run_tasks, campaign_seq=seq,
        dsn=store, consumer=_consumer(store, cid), constructor="model",
        gateway=provider, model="export-double")
    return out, provider


def _export(store, out):
    from experiments.ad01 import records
    return records.export_campaign(
        store, out, model="export-double", charter=CHARTER, caps=CAPS)


def _verify(export):
    from experiments.ad01 import records
    return records.verify_campaign(export, export.get("use_records", []))


def test_bound_export_is_complete_and_offline(store, tmp_path):
    from experiments.ad01 import records
    out, provider = _run(store, 0, GOOD_CANDIDATE)
    exported = _export(store, out)
    policy = exported["policy"]
    assert out["episodes"][1]["disposition"] == "bound"
    assert provider.calls
    assert set(policy) >= {"source", "source_digest", "artifact", "freeze",
                            "proposal", "panel", "rule", "assessment",
                            "arms", "binding", "refusal", "journal"}
    assert set(policy["artifact"]) >= {"kind", "entry", "abi", "origin",
                                        "parent_digest", "applicability"}
    assert policy["freeze"]["candidate_digest"] == policy["source_digest"]
    assert policy["assessment"]["outcome"] == "bind"
    assert policy["binding"]["evidence_refs"] == [
        policy["assessment"]["attempt_id"]]
    assert policy["arms"]["candidate"]["panel_task_ids"] == \
        policy["panel"]["task_ids"]
    assert policy["arms"]["incumbent"]["panel_task_ids"] == \
        policy["panel"]["task_ids"]
    assert policy["arms"]["candidate"]["resources"]["step_calls"] > 0
    assert policy["arms"]["incumbent"]["resources"]["step_calls"] > 0
    result = _verify(exported)
    assert result["status"] == "pass", result["problems"]
    path = tmp_path / "bound.json"
    records.write_export(exported, path)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "s09_verify.py"),
         str(path)],
        cwd=str(ROOT), env=_env(), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert json.loads(proc.stdout)["status"] == "pass"


def _mutations(export):
    def source_byte(data):
        source = data["policy"]["source"]
        data["policy"]["source"] = source[:-1] + (" " if source[-1] != " " else "\n")

    def entry(data):
        data["policy"]["artifact"]["entry"] = "ENTRY"

    def panel(data):
        data["policy"]["arms"]["incumbent"]["panel_task_ids"] = \
            data["policy"]["panel"]["task_ids"][:-1]

    def steps(data):
        data["policy"]["arms"]["incumbent"]["resources"]["step_calls"] = 0

    def quality(data):
        data["policy"]["arms"]["candidate"]["quality"]["preserved"] += 1

    def outcome(data):
        data["policy"]["assessment"]["outcome"] = "bind"

    def use_digest(data):
        data["use_records"][0]["executed_source_digest"] = "x" * 64
        data["use_records"][0]["fallback_reason"] = ""

    def leak(data):
        from experiments.ad01 import worlds
        task = worlds.load_task(worlds.FROZEN_DIR,
                                data["policy"]["panel"]["task_ids"][0])
        data["innocuous"] = task["witness"]

    def decisions(data):
        data["policy"]["arms"]["candidate"]["decisions"].pop()

    def refs(data):
        data["policy"]["binding"]["evidence_refs"] = []

    return [(index, check, mutate) for index, (check, mutate) in enumerate((
            ("V1", source_byte), ("V2", entry), ("V11", panel),
            ("V11", steps), ("V5a", quality), ("V5a", outcome),
            ("V8", use_digest), ("V9a", leak), ("V12", decisions),
            ("V7", refs)))]


@pytest.mark.parametrize("case", _mutations(None),
                         ids=lambda value: "%s-%s" % (value[0], value[1]))
def test_mutations_name_the_failed_check(store, case):
    from experiments.ad01 import records
    index, check, mutate = case
    source = REJECTED_CANDIDATE if index == 5 else GOOD_CANDIDATE
    out, _provider = _run(store, 1 + index, source)
    exported = _export(store, out)
    if check == "V8":
        if not exported["use_records"]:
            pytest.skip("bound run did not produce a policy use record")
    mutated = copy.deepcopy(exported)
    mutate(mutated)
    result = records.verify_campaign(mutated, mutated.get("use_records", []))
    assert result["status"] == "fail"
    assert any(check in problem for problem in result["problems"])


def test_rejected_export_has_durable_refusal_and_no_release(store):
    out, _provider = _run(store, 20, REJECTED_CANDIDATE)
    exported = _export(store, out)
    policy = exported["policy"]
    assert policy["assessment"]["outcome"] == "reject"
    assert policy["binding"] is None
    assert policy["refusal"]["outcome"] == "reject"
    assert policy["refusal"]["reason"]
    assert _verify(exported)["status"] == "pass"


def test_unavailable_export_is_distinct_and_durable(store):
    out, provider = _run(store, 21, "not STEP source")
    exported = _export(store, out)
    policy = exported["policy"]
    assert provider.calls
    assert out["episodes"][1]["disposition"] == "unavailable"
    assert policy["assessment"] is None
    assert policy["binding"] is None
    assert policy["refusal"]["outcome"] == "unavailable"
    assert policy["refusal"]["durable"] is True
    assert _verify(exported)["status"] == "pass"


def test_the_store_is_named_for_this_run_not_for_the_file():
    """A fixed name is shared state; a sibling run's teardown destroys it.

    Two runs of this file on one cluster collided on one name, and the first
    teardown dropped the store the second was still writing to. The name
    carries a per-run token, so only a name this run minted is ever dropped
    and a second fixture can never reuse the first one's database.
    """
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    first = iso.create_disposable_db(TOKEN, admin_dsn=admin_dsn,
                                     migrations_dir=ROOT / "migrations")
    try:
        assert first.name.startswith(iso.DB_PREFIX + "_"), first.name
        assert TOKEN in first.name, first.name
        again = iso.create_disposable_db(TOKEN, admin_dsn=admin_dsn,
                                         migrations_dir=ROOT / "migrations")
        try:
            assert again.name != first.name
        finally:
            iso.drop_disposable_db(again, admin_dsn=admin_dsn)
    finally:
        iso.drop_disposable_db(first, admin_dsn=admin_dsn)
