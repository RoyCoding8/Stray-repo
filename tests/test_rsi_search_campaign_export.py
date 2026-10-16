from __future__ import annotations

import copy
import json

import pytest
from fixtures.p10_campaign import prepare_campaign
from psycopg.rows import dict_row

from rsi import agenda, campaign, genome
from settlement import db, store
from settlement.common import Command


def _stopped_policy_campaign(dsn, tmp_path, *, expected_status="stopped"):
    campaign_id = "p06-policy-export"
    case = prepare_campaign(dsn, tmp_path, campaign_id=campaign_id, round_count=1)
    policy = genome.Genome({
        "skills/explore/SKILL.md": b"---\nname: explore\ndescription: stop exploration\n---\n",
        "skills/explore/capability.json": json.dumps({
            "schema": "rsi-capability/1", "interface": "exploration-policy/1",
            "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
            "effects": ["return", "solution-files"],
            "limits": {"timeout_ms": 10_000, "max_output_bytes": 65_536},
        }).encode(),
        "skills/explore/method.py": (
            b"def invoke(request):\n"
            b"    return {'value': {'action': 'stop', 'reason': 'enough evidence'}, 'files': {}}\n"
        ),
    })
    roots = case["run"]["roots"]
    genome.publish(dsn, policy, parent=None, origin="authored-p06-test", **roots)
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT authority_grant,envelopes FROM grants WHERE version=1")
        grant = dict(cur.fetchone())
    grant["authority_grant"]["genome_ids"].append(policy.digest)
    store.seed_grant(dsn, Command(request_id="p06-export-grant", payload={
        "version": 2, "charter_text": "bounded policy export test", **grant,
    }))
    case["charter"]["grant_version"] = 2
    case["charter"]["policy"] = {
        "genome": policy.digest, "name": "explore", "interface": "exploration-policy/1",
        "timeout_ms": 10_000, "max_output_bytes": 65_536,
    }
    campaign.start(dsn, campaign_id=campaign_id, charter=case["charter"],
                   protocol=case["protocol"], **roots)
    outcome = campaign.run(dsn, case["run"]["agent"], case["run"]["checker"],
                           campaign_id, max_wakes=2, wall_seconds=30, **roots)
    assert outcome["status"] == expected_status
    bundle = campaign.export(dsn, campaign_id, artifacts_root=roots["artifacts_root"])
    admission, = [row["data"] for row in bundle["decisions"]
                   if row["kind"] == "p05.policy_admission"]
    return bundle, admission


def test_campaign_exports_native_policy_effect_and_cost(migrated_db, tmp_path):
    bundle, admission = _stopped_policy_campaign(migrated_db, tmp_path)
    operation_id = admission["operation_id"]
    operation, = [row for row in bundle["operations"] if row["id"] == operation_id]
    assert operation["attempt_id"] is None
    assert operation["settled"] is True
    assert operation["execution_version"] == admission["policy"]["execution_version"]
    assert [row for row in bundle["receipts"] if row["operation_id"] == operation_id]
    reservation, = [row for row in bundle["reservations"] if row["operation_id"] == operation_id]
    assert reservation["amount"] > 0
    assert admission["frame_digest"] in bundle["artifact_bytes"]
    assert admission["policy"]["genome"] in bundle["artifact_bytes"]
    result = campaign.recompute(bundle)
    assert result["problems"] == []
    assert result["resource_units"]["cpu"]["settled"] == reservation["amount"]
    assert result["status"] == "incomplete"  # No assessment was run after the deliberate stop.


def test_campaign_preserves_a_definitive_policy_admission_refusal(
        migrated_db, tmp_path, monkeypatch):
    from settlement.common import SettlementError

    def refuse(*args, **kwargs):
        raise SettlementError("fixture refusal before operation preparation")

    monkeypatch.setattr(agenda.capability, "invoke", refuse)
    bundle, admission = _stopped_policy_campaign(
        migrated_db, tmp_path, expected_status="deferred")
    refusal, = [row["data"] for row in bundle["decisions"]
                 if row["kind"] == "p05.policy_refusal"]
    assert refusal["operation_admitted"] is False
    assert not any(row["id"] == admission["operation_id"] for row in bundle["operations"])
    result = campaign.recompute(bundle)
    assert result["problems"] == []
    assert result["unresolved_operations"] == []
    assert result["resource_units"]["cpu"]["settled"] == 0


@pytest.mark.parametrize("mutation", ["operation", "receipt", "admission", "runtime"])
def test_offline_campaign_refuses_erased_or_rebound_policy_evidence(
        migrated_db, tmp_path, mutation):
    bundle, admission = _stopped_policy_campaign(migrated_db, tmp_path)
    assert campaign.recompute(bundle)["problems"] == []
    changed = copy.deepcopy(bundle)
    operation_id = admission["operation_id"]
    if mutation == "operation":
        changed["operations"] = [row for row in changed["operations"] if row["id"] != operation_id]
    elif mutation == "receipt":
        changed["receipts"] = [row for row in changed["receipts"] if row["operation_id"] != operation_id]
    elif mutation == "admission":
        changed["decisions"] = [row for row in changed["decisions"]
                                if row["kind"] != "p05.policy_admission"]
    else:
        next(row for row in changed["operations"] if row["id"] == operation_id)[
            "execution_version"] = "different-runtime"
    result = campaign.recompute(changed)
    assert result["status"] == "tampered"
    assert result["comparison_gain"] is False
    assert any("policy" in item or "receipt" in item for item in result["problems"])
