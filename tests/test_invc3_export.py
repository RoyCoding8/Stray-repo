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
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tests"))

from execution_authority import execution_store as make_execution_store

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 96,
        "model_calls": 60, "construction_tokens": 2048,
        "agenda_authorized": 100000}
MODEL = "inv-c-double"
SW0 = "ad01-w0-dev-sw-00"
SW1 = "ad01-w0-dev-sw-01"
GR0 = "ad01-w0-dev-gr-00"


@pytest.fixture
def execution_store():
    with make_execution_store("ci-invc3export") as store:
        yield store


def _run(dsn, seq=0):
    from experiments import doubles as D
    from experiments.ad01 import learner, trajectory
    tasks = [SW0, SW1]
    scripts = [D.learner_diagnostic_text(SW0, "software"),
               D.learner_development_text(SW1, "software")]
    gateway = D.InvCQualificationDouble(learner_scripts=list(scripts))
    cid = trajectory.campaign_id(0, "I", seq)
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    seed = trajectory.ensure_campaign(
        dsn, cid, 0, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks))
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=seed["allocation_id"])
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks),
        propose=propose, campaign_seq=seq, dsn=dsn,
        gateway=gateway, model=MODEL, constructor="model")
    return cid, gateway, campaign


def test_export_emits_doubles_transitions(execution_store):
    from experiments.ad01 import records
    from experiments import doubles as D
    dsn = execution_store["dsn"]
    cid, gateway, campaign = _run(dsn, seq=11)
    export = records.export_campaign(
        dsn, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    assert export["campaign_id"] == cid
    assert len(export["transitions"]) == len(campaign["boundaries"])
    for transition in export["transitions"]:
        assert transition["packet_digest"]
        assert transition["proposal"]["target"]
        assert transition["proposal"]["instrument"] in (
            "diagnostic", "development", "stop")
        assert "model" in transition["proposal"]["inputs"]
        assert isinstance(transition["operations"], list)
        assert isinstance(transition["results"], list)
    recorded = D.recorded_from_export(export)
    assert len(recorded) == len(export["transitions"])
    for index, rec in enumerate(recorded):
        probe = {
            "index": index,
            "packet_digest": rec["packet_digest"],
            "action": {"target": rec["proposal"]["target"],
                       "instrument": rec["proposal"]["instrument"],
                       "inputs": dict(rec["proposal"]["inputs"]),
                       "dependencies": list(
                           rec["proposal"].get("dependencies", [])),
                       "requested": dict(
                           rec["proposal"].get("requested", {}))},
            "versions": dict(export["identities"]["versions"]),
            "observations": [],
        }
        if index:
            prior = recorded[index - 1]
            probe["observations"] = list(prior.get("operations", []))[:0]
        verdict = D.check_replay_prefix(recorded, probe)
        assert verdict["verdict"] == "supported", verdict
        assert verdict["results"] == rec["results"]


def test_replay_refuses_mismatches_from_export(execution_store):
    from experiments.ad01 import records
    from experiments import doubles as D
    dsn = execution_store["dsn"]
    _cid, _gateway, campaign = _run(dsn, seq=12)
    export = records.export_campaign(
        dsn, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    recorded = D.recorded_from_export(export)
    assert len(recorded) >= 1
    rec = recorded[0]
    base_action = {"target": rec["proposal"]["target"],
                   "instrument": rec["proposal"]["instrument"],
                   "inputs": dict(rec["proposal"]["inputs"]),
                   "dependencies": list(
                       rec["proposal"].get("dependencies", [])),
                   "requested": dict(rec["proposal"].get("requested", {}))}
    base_versions = dict(export["identities"]["versions"])
    base = {"index": 0, "packet_digest": rec["packet_digest"],
            "action": base_action, "versions": base_versions,
            "observations": []}
    future_probe = dict(base, observations=["no-such-future-op"])
    future = D.check_replay_prefix(recorded, future_probe)
    assert future["verdict"] == "unsupported"
    assert "hidden-future" in future["reason"]
    assert future["results"] == []
    reordered_deps = list(base_action["dependencies"])
    if reordered_deps and len(reordered_deps) >= 1:
        probe_deps = {"index": 0, "packet_digest": rec["packet_digest"],
                      "action": {**base_action, "dependencies": list(
                          reversed(reordered_deps)) if len(
                          reordered_deps) > 1 else ["other-dep"]},
                      "versions": base_versions, "observations": []}
        out = D.check_replay_prefix(recorded, probe_deps)
        assert out["verdict"] == "unsupported"
        assert out["results"] == []
    forged_inputs = dict(base_action["inputs"])
    forged_inputs["prompt"] = "forged-bytes-not-recorded"
    forged = D.check_replay_prefix(recorded, {
        "index": 0, "packet_digest": rec["packet_digest"],
        "action": {**base_action, "inputs": forged_inputs},
        "versions": base_versions, "observations": []})
    assert forged["verdict"] == "unsupported"
    assert "new-code-bytes" in forged["reason"]
    assert forged["results"] == []
    stale_versions = dict(base_versions, model="other-model")
    stale = D.check_replay_prefix(recorded, {
        "index": 0, "packet_digest": rec["packet_digest"],
        "action": base_action, "versions": stale_versions,
        "observations": []})
    assert stale["verdict"] == "unsupported"
    assert "version-mismatch" in stale["reason"]
    assert stale["results"] == []
    malformed = D.check_replay_prefix(recorded, {"index": 0})
    assert malformed["verdict"] == "refused"
    assert malformed["results"] == []


def test_byte_identity_at_receipt_validation_retention_and_use(tmp_path, execution_store):
    from experiments.ad01 import records, trajectory
    dsn = execution_store["dsn"]
    cid, gateway, campaign = _run(dsn, seq=13)
    export = records.export_campaign(
        dsn, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    chain = records.verify_byte_chain(export)
    assert chain["problems"] == [], chain
    assert chain["checked"] >= 1
    frozen = tmp_path / "repertoire.json"
    repertoire = trajectory.freeze_repertoire(campaign, frozen)
    assert repertoire["members"]
    use_tasks = [SW0]
    selected_member = repertoire["members"][0]
    policy_path = tmp_path / "use-policy.py"
    policy_source = (
        "def STEP(view, state):\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': view['task_content']['task_id'],\n"
        "                      'inputs': {'method_id': %r, 'max_queries': 16},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 16}},\n"
        "            'state': {}}\n" % selected_member["capability_id"])
    policy_path.write_text(policy_source, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--world", "0", "--arm", "I",
         "--tasks", ",".join(use_tasks), "--dsn", dsn,
         "--allocation-id", trajectory._alloc_id(cid),
         "--policy-source", str(policy_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    use_records = json.loads(proc.stdout)
    chain_use = records.verify_byte_chain(export, use_records=use_records)
    assert chain_use["problems"] == [], chain_use
    for record in use_records:
        retained = next(
            m for m in repertoire["members"]
            if m["capability_id"] == record["selected"])
        assert record["executed_source"] == retained["method_source"]
        assert hashlib.sha256(
            record["executed_source"].encode()).hexdigest() == retained[
            "source_digest"]
        assert record["selected"] == retained["capability_id"]
        assert record["policy_source_digest"] == hashlib.sha256(
            policy_source.encode("utf-8")).hexdigest()
        policy_authority = hashlib.sha256(
            trajectory._alloc_id(cid).encode("utf-8")).hexdigest()[:12]
        expected_operations = [
            trajectory._versioned_use_op_id(
                cid, SW0, "policy-%s-%s" % (
                    record["policy_source_digest"][:16], policy_authority)),
            trajectory._versioned_use_op_id(
                cid, SW0, retained["capability_id"])]
        assert record["operation_ids"] == expected_operations


def test_cli_export_and_offline_replay(tmp_path, execution_store):
    from experiments.ad01 import records
    dsn = execution_store["dsn"]
    cid, _gateway, campaign = _run(dsn, seq=14)
    out_path = tmp_path / "export.json"
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "export",
         "--dsn", dsn, "--campaign", cid, "--out", str(out_path),
         "--model", MODEL],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    export = json.loads(out_path.read_text())
    assert export["campaign_id"] == cid
    assert export["transitions"]
    probe_path = tmp_path / "probe.json"
    recorded = export["transitions"]
    rec = recorded[0]
    probe = {"index": 0, "packet_digest": rec["packet_digest"],
             "action": {"target": rec["proposal"]["target"],
                        "instrument": rec["proposal"]["instrument"],
                        "inputs": rec["proposal"]["inputs"],
                        "dependencies": rec["proposal"].get(
                            "dependencies", []),
                        "requested": rec["proposal"].get("requested", {})},
             "versions": export["identities"]["versions"],
             "observations": []}
    probe_path.write_text(json.dumps(probe) + "\n")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "replay",
         "--export", str(out_path), "--probe", str(probe_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    verdict = json.loads(proc.stdout)
    assert verdict["verdict"] == "supported"
    assert verdict["results"] == rec["results"]
    loaded = records.load_export(str(out_path))
    assert loaded["campaign_id"] == cid
