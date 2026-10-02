from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest_isolation import dbname_of

DSN = os.environ.get(
    "INV_R3_DSN",
    "dbname=inv_r3_export host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

_SHARED_STORES = frozenset({"inv_r3_export", "inv_r3_probe", "postgres"})

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 96,
        "model_calls": 60, "construction_tokens": 2048,
        "agenda_authorized": 100000}
MODEL = "inv-c-double"
SW0 = "ad01-w0-dev-sw-00"
SW1 = "ad01-w0-dev-sw-01"


def _fresh_db(dsn: str):
    assert "live" not in dsn
    # This file destroys and rebuilds its store, so the guard is the one that
    # matters: refuse the shared study names, and accept anything a run owns.
    # It used to demand a leading ``inv_r3_`` instead, which is a naming
    # convention rather than a safety property, and no per-run name can hold it
    # -- ``conftest_isolation.derived_name`` leads with its own token.
    assert dbname_of(dsn) not in _SHARED_STORES
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(dsn, MIGRATIONS)
    E.designate_db(dsn, kind="disposable",
                   purpose="INV-R3 export gate")
    E.prepare_disposable_db(dsn, MIGRATIONS)


def _run_correction(dsn, seq=21):
    from experiments import doubles as D
    from experiments.ad01 import learner, trajectory
    scripts = [
        D.learner_text({
            "basis_references": ["obs-invented-999"],
            "question": "invented leap at %s" % SW0,
            "next_action": {"kind": "development", "diagnostic": "software",
                            "task_id": SW0, "max_queries": 4},
            "requested_resources": {"diagnostic_queries": 1}}),
        D.learner_development_text(SW0, "software"),
        D.learner_development_text(SW1, "software")]
    gateway = D.InvCQualificationDouble(
        learner_scripts=list(scripts))
    cid = trajectory.campaign_id(0, "I", seq)
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    seed = trajectory.ensure_campaign(
        dsn, cid, 0, "I", dict(CHARTER), dict(CAPS),
        tasks=[SW0, SW1])
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=seed["allocation_id"])
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0, SW1],
        propose=propose, campaign_seq=seq, dsn=dsn,
        gateway=gateway, model=MODEL, constructor="model")
    return cid, gateway, campaign


def test_correction_exports_both_requests_and_counts_both():
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, gateway, campaign = _run_correction(DSN, seq=21)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    first = export["transitions"][0]
    assert "ad01-%s-learner-0" % cid in first["operations"]
    assert "ad01-%s-learner-0-c1" % cid in first["operations"]
    assert len([o for o in first["operations"]
                if "-learner-" in o]) == 2
    texts = [r["text"] for r in first["raw_responses"]]
    assert gateway.records[
        "ad01-%s-learner-0" % cid]["response"] in texts
    assert gateway.records[
        "ad01-%s-learner-0-c1" % cid]["response"] in texts
    assert first["costs_measured"]["model_calls"] == 3


def _run_repair(dsn, seq=22):
    from experiments import doubles as D
    from experiments.ad01 import learner, trajectory
    scripts = [D.learner_development_text(SW0, "software")]
    gateway = D.InvCQualificationDouble(
        learner_scripts=list(scripts),
        init_scripts=[{"text": "not python {{{",
                       "notes": "broken init"}])
    cid = trajectory.campaign_id(0, "I", seq)
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    seed = trajectory.ensure_campaign(
        dsn, cid, 0, "I", dict(CHARTER), dict(CAPS),
        tasks=[SW0])
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=seed["allocation_id"])
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
        propose=propose, campaign_seq=seq, dsn=dsn,
        gateway=gateway, model=MODEL, constructor="model")
    return cid, gateway, campaign


def test_construction_repair_exports_both_attempts():
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, gateway, campaign = _run_repair(DSN, seq=22)
    assert campaign["episodes"][0]["disposition"] == "retained"
    assert campaign["episodes"][0]["construction_calls"] == 2
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    first = export["transitions"][0]
    init_ops = [o for o in first["operations"]
                if o.endswith("-init") and "-construct-" in o]
    repair_ops = [o for o in first["operations"]
                  if o.endswith("-repair") and "-construct-" in o]
    assert len(init_ops) == 1
    assert len(repair_ops) == 1
    texts = [r["text"] for r in first["raw_responses"]]
    assert "not python {{{" in texts
    assert gateway.records[repair_ops[0]]["response"] in texts
    assert first["costs_measured"]["model_calls"] == 3


def test_export_binds_delivered_request_and_pinned_identities():
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, gateway, campaign = _run_correction(DSN, seq=23)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    assert export["identities"]["versions"]["model"] == MODEL
    assert export["identities"]["freeze_id"] == "ad01"
    assert export["identities"]["source"]["export_version"] == \
        records.EXPORT_VERSION
    assert export["identities"]["source"]["git_sha"]
    assert export["identities"]["effective"]["model"] == MODEL
    assert export["identities"]["effective"]["reasoning_effort"] in (
        "low", "medium", "high")
    assert export["identities"]["effective"]["caps"]["model_calls"] == 60
    first = export["transitions"][0]
    assert first["packet_source"] == "reconstructed"
    delivered = {d["operation_id"]: d for d in
                 first["delivered_requests"]}
    base = delivered["ad01-%s-learner-0" % cid]
    correction = delivered["ad01-%s-learner-0-c1" % cid]
    assert base["model"] == MODEL
    assert "PRIOR FAILURE" not in base["prompt"]
    assert "PRIOR FAILURE" in correction["prompt"]
    assert "invented basis references" in correction["prompt"]
    assert correction["prompt_digest"] != base["prompt_digest"]
    corrections = first["corrections"]
    assert len(corrections) == 1
    assert corrections[0]["number"] == 1
    assert "invented basis references" in corrections[0][
        "failure"]["reason"]


def _admit(method_id: str):
    """A use policy that admits one named method, the way a real one would.

    `run_use` takes the method identity from an admitted policy action and
    refuses without one (`77001fc`), so a test of the export and the byte
    chain has to supply the decision its use phase needs. The admitted id
    still has to be in the repertoire, carry the task's family and satisfy
    the release binding, so this admits a method; it does not admit one the
    repertoire would not have carried anyway.
    """
    def step(view, state):
        return {
            "action": {
                "kind": "use_method",
                "target": view["task_content"]["task_id"],
                "inputs": {"method_id": method_id, "max_queries": 16},
                "evidence_refs": [],
                "requested_resources": {"queries": 16}},
            "state": dict(state or {})}
    return step


def _run_pilot(dsn, seq, tmp_path):
    from experiments.ad01 import trajectory
    cid, _gateway, campaign = _run_correction(dsn, seq=seq)
    frozen = tmp_path / ("repertoire-%d.json" % seq)
    repertoire = trajectory.freeze_repertoire(campaign, frozen)
    assert repertoire["members"]
    member_id = repertoire["members"][0]["capability_id"]
    member_task = SW0
    retained_batch = trajectory.run_use(
        repertoire, 0, "I", [member_task], {},
        dsn=dsn, allocation_id=trajectory._alloc_id(cid),
        policy=_admit(member_id))
    assert retained_batch[0]["selected"] == member_id
    empty = {"campaign_id": cid, "members": [], "queries": 0}
    # An empty repertoire is a refusal, not a fallback. The test asserted
    # `selected == "incumbent"` here from before `77001fc` made the method
    # identity a thing only a policy can supply, and that commit deleted
    # the incumbent path an empty repertoire used to reach. A policy
    # admitting the member it *would* have run is refused by name, which
    # is the decided rule: see reviews/STAGE-09-EMPTY-REPERTOIRE.md.
    fallback_batch = trajectory.run_use(
        empty, 0, "I", [SW1], {},
        dsn=dsn, allocation_id=trajectory._alloc_id(cid),
        policy=_admit(member_id))
    assert fallback_batch[0]["status"] == "refused"
    assert fallback_batch[0]["selected"] == "refused"
    assert fallback_batch[0]["executed"] == "refused"
    assert fallback_batch[0]["output"] == {}
    assert fallback_batch[0]["costs"]["witness_queries"] == 0
    assert member_id in fallback_batch[0]["fallback_reason"]
    assert "absent from the repertoire" in fallback_batch[0]["fallback_reason"]
    return cid, campaign, retained_batch + fallback_batch


def test_valid_pilot_verifies_from_independent_identities(tmp_path):
    import copy
    from experiments.ad01 import records
    from experiments.ad01 import trajectory
    _fresh_db(DSN)
    cid, campaign, use_records = _run_pilot(DSN, 31, tmp_path)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_id": cid,
                "seqs": [t["index"] for t in export["transitions"]],
                "use_record_ids": [r["record_id"] for r in use_records]}
    result = records.verify_campaign(export, use_records, expected)
    assert result["status"] == "pass", result["problems"]
    with trajectory._read_conn(DSN) as conn:
        rows = conn.execute(
            "SELECT id, payload FROM operations WHERE starts_with(id, %s)",
            ("ad01-%s-" % cid,)).fetchall()
    independent_model = sum(
        1 for r in rows
        if dict(r["payload"] or {}).get("effect") == "model-inference"
        and ("-learner-" in r["id"] or "-construct-" in r["id"])
        and not r["id"].startswith("ad01-%s-use-" % cid))
    assert result["recomputed"]["model_calls"] == independent_model
    assert independent_model == 5
    copied = copy.deepcopy(export)
    copied_uses = copy.deepcopy(use_records)
    again = records.verify_campaign(copied, copied_uses, copy.deepcopy(
        expected))
    assert again["status"] == "pass"
    assert again["recomputed"] == result["recomputed"]


def test_missing_use_record_fails_for_named_reason(tmp_path):
    import copy
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, campaign, use_records = _run_pilot(DSN, 32, tmp_path)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_id": cid,
                "seqs": [t["index"] for t in export["transitions"]],
                "use_record_ids": [r["record_id"] for r in use_records]}
    trimmed = copy.deepcopy(use_records[:-1])
    result = records.verify_campaign(copy.deepcopy(export), trimmed,
                                     copy.deepcopy(expected))
    assert result["status"] == "fail"
    assert any("missing-use-record" in p for p in result["problems"])


def test_missing_transition_pair_fails_for_named_reason(tmp_path):
    import copy
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, campaign, use_records = _run_pilot(DSN, 33, tmp_path)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_id": cid,
                "seqs": [t["index"] for t in export["transitions"]],
                "use_record_ids": [r["record_id"] for r in use_records]}
    assert len(export["transitions"]) == 2
    pruned = copy.deepcopy(export)
    pruned["transitions"] = pruned["transitions"][:1]
    result = records.verify_campaign(pruned, copy.deepcopy(use_records),
                                     copy.deepcopy(expected))
    assert result["status"] == "fail"
    assert any("missing-transition" in p for p in result["problems"])


def test_duplicate_use_record_fails_for_named_reason(tmp_path):
    import copy
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, campaign, use_records = _run_pilot(DSN, 34, tmp_path)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_id": cid,
                "seqs": [t["index"] for t in export["transitions"]],
                "use_record_ids": [r["record_id"] for r in use_records]}
    doubled = copy.deepcopy(use_records) + [copy.deepcopy(use_records[0])]
    result = records.verify_campaign(copy.deepcopy(export), doubled,
                                     copy.deepcopy(expected))
    assert result["status"] == "fail"
    assert any("duplicate-record" in p for p in result["problems"])


def test_altered_query_totals_fail_for_named_reason(tmp_path):
    import copy
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, campaign, use_records = _run_pilot(DSN, 35, tmp_path)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_id": cid,
                "seqs": [t["index"] for t in export["transitions"]],
                "use_record_ids": [r["record_id"] for r in use_records]}
    forged = copy.deepcopy(export)
    forged["transitions"][0]["episode"] = dict(
        forged["transitions"][0]["episode"])
    forged["transitions"][0]["episode"]["queries"] = 999999
    result = records.verify_campaign(forged, copy.deepcopy(use_records),
                                     copy.deepcopy(expected))
    assert result["status"] == "fail"
    assert any("query-total-mismatch" in p for p in result["problems"])


def test_omitted_correction_receipt_fails_for_named_reason(tmp_path):
    import copy
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid, campaign, use_records = _run_pilot(DSN, 36, tmp_path)
    export = records.export_campaign(
        DSN, campaign, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_id": cid,
                "seqs": [t["index"] for t in export["transitions"]],
                "use_record_ids": [r["record_id"] for r in use_records]}
    target = "ad01-%s-learner-0-c1" % cid
    stripped = copy.deepcopy(export)
    first = stripped["transitions"][0]
    assert target in first["operations"]
    first["receipts"] = [r for r in first["receipts"]
                         if r.get("operation_id") != target]
    first["raw_responses"] = [r for r in first["raw_responses"]
                              if r.get("operation_id") != target]
    result = records.verify_campaign(stripped, copy.deepcopy(use_records),
                                     copy.deepcopy(expected))
    assert result["status"] == "fail"
    assert any("missing-receipt" in p for p in result["problems"])


def test_missing_study_trajectory_fails_for_named_reason(tmp_path):
    import copy
    from experiments.ad01 import records
    _fresh_db(DSN)
    cid_a, campaign_a, uses_a = _run_pilot(DSN, 37, tmp_path)
    from experiments.ad01 import trajectory
    from experiments import doubles as D
    from experiments.ad01 import learner
    scripts = [D.learner_development_text(SW0, "software")]
    gateway = D.InvCQualificationDouble(learner_scripts=list(scripts))
    cid_b = trajectory.campaign_id(0, "I", 38)
    trajectory.authorize_campaign(DSN, cid_b, authorized=100000)
    seed = trajectory.ensure_campaign(
        DSN, cid_b, 0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0])
    propose = learner.propose_from_model(
        DSN, cid=cid_b, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=seed["allocation_id"])
    campaign_b = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
        propose=propose, campaign_seq=38, dsn=DSN,
        gateway=gateway, model=MODEL, constructor="model")
    export_a = records.export_campaign(
        DSN, campaign_a, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    export_b = records.export_campaign(
        DSN, campaign_b, model=MODEL, charter=dict(CHARTER),
        caps=dict(CAPS))
    expected = {"campaign_ids": [cid_a, cid_b],
                "use_record_ids": [r["record_id"] for r in uses_a]}
    full = records.verify_study([export_a, export_b],
                                copy.deepcopy(uses_a),
                                copy.deepcopy(expected))
    assert full["status"] == "pass", full["problems"]
    pruned = records.verify_study([export_b], copy.deepcopy(uses_a),
                                  copy.deepcopy(expected))
    assert pruned["status"] == "fail"
    assert any("missing-trajectory" in p for p in pruned["problems"])


def test_unavailable_evidence_is_incomplete_never_pass():
    from experiments.ad01 import records
    assert records.verify_campaign(
        {}, [])["status"] == "incomplete"
    assert records.verify_campaign(
        {"transitions": [], "operations": [],
         "identities": {}}, None)["status"] == "incomplete"
    assert records.verify_study([], [])["status"] == "incomplete"
