from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest_isolation import dbname_of

DSN = os.environ.get(
    "INV_C3_DSN",
    "dbname=inv_c3_export host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

# The three stores this battery shares with a sibling study, read off the
# cluster rather than guessed. `_fresh_db` truncates, so refusing them is the
# property that matters.
_SHARED_STORES = frozenset({"inv_c3_export", "inv_c3_study", "inv_c3_cli",
                            "postgres"})

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 96,
        "model_calls": 60, "construction_tokens": 2048,
        "agenda_authorized": 100000}
MODEL = "inv-c-double"
SW0 = "ad01-w0-dev-sw-00"
SW1 = "ad01-w0-dev-sw-01"
GR0 = "ad01-w0-dev-gr-00"


def _fresh_db(dsn: str):
    assert "live" not in dsn
    # This file destroys and rebuilds its store, so the guard that matters is
    # the one refusing a store a sibling battery also uses. It used to demand a
    # leading ``inv_c3_`` instead, which is a naming convention rather than a
    # safety property, and no per-run name can hold it --
    # ``conftest_isolation.derived_name`` leads with its own token, so
    # ``s09iso_<token>_inv_c3_export`` never starts with ``inv_c3_``. The
    # assertion refused a name the run itself owns, which is the wrong
    # direction for a truncating file. Same fix as test_invr3_export.py:32.
    assert dbname_of(dsn) not in _SHARED_STORES, dbname_of(dsn)
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(dsn, MIGRATIONS)
    E.designate_db(dsn, kind="disposable",
                   purpose="INV-C3 export gate")
    E.prepare_disposable_db(dsn, MIGRATIONS)


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


def test_export_emits_doubles_transitions():
    from experiments.ad01 import records
    from experiments import doubles as D
    _fresh_db(DSN)
    cid, gateway, campaign = _run(DSN, seq=11)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
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


def test_replay_refuses_mismatches_from_export():
    from experiments.ad01 import records
    from experiments import doubles as D
    _fresh_db(DSN)
    _cid, _gateway, campaign = _run(DSN, seq=12)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
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


def test_byte_identity_at_receipt_validation_retention_and_use(tmp_path):
    from experiments.ad01 import records, trajectory
    _fresh_db(DSN)
    cid, gateway, campaign = _run(DSN, seq=13)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    chain = records.verify_byte_chain(export)
    assert chain["problems"] == [], chain
    assert chain["checked"] >= 1
    frozen = tmp_path / "repertoire.json"
    repertoire = trajectory.freeze_repertoire(campaign, frozen)
    assert repertoire["members"]
    use_tasks = [SW0]
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--world", "0", "--arm", "I",
         "--tasks", ",".join(use_tasks), "--dsn", DSN,
         "--allocation-id", trajectory._alloc_id(cid)],
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


def test_cli_export_and_offline_replay(tmp_path):
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, _gateway, campaign = _run(DSN, seq=14)
    out_path = tmp_path / "export.json"
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "export",
         "--dsn", DSN, "--campaign", cid, "--out", str(out_path),
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
