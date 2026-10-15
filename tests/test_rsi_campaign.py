from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rsi import campaign
from settlement.common import SettlementError


def _round(after_turn=1):
    return {
        "id": "round-1",
        "after_turn": after_turn,
        "epoch": "e" * 64,
        "parent": "p" * 64,
        "candidate": "c" * 64,
        "model": "fixture:free",
        "route_identity": hashlib.sha256(b"http://fixture/v1").hexdigest(),
    }


def test_protocol_pins_ordered_bounded_rounds_and_route_identity():
    protocol = {"schema": "p10-assessment/1", "rounds": [_round(0), _round(1)]}
    protocol["rounds"][1]["id"] = "round-2"
    parsed, raw = campaign._parse_protocol(protocol, 1)
    assert parsed == protocol
    assert json.loads(raw) == protocol
    assert campaign.route_identity("http://fixture/v1/") == campaign.route_identity(
        "http://fixture/v1"
    )


@pytest.mark.parametrize("rounds", [
    [_round(-1)],
    [_round(2)],
    [{**_round(1), "id": "round-1"}, {**_round(0), "id": "round-2"}],
])
def test_protocol_rejects_out_of_order_or_out_of_bound_milestones(rounds):
    with pytest.raises(SettlementError, match="milestone"):
        campaign._parse_protocol({"schema": "p10-assessment/1", "rounds": rounds}, 1)


def test_route_identity_never_accepts_embedded_credentials():
    with pytest.raises(SettlementError) as raised:
        campaign.route_identity("https://user:secret@example.test/v1")
    assert "secret" not in str(raised.value)


def test_start_publishes_only_digest_and_inspection_hides_protocol_inputs(
    migrated_db, tmp_path
):
    from fixtures.p10_campaign import prepare_campaign

    case = prepare_campaign(migrated_db, tmp_path / "prepare", campaign_id="p10-start", round_count=1)
    result = campaign.start(
        migrated_db, campaign_id="p10-start", charter=case["charter"],
        protocol=case["protocol"], **case["run"]["roots"],
    )
    inspected = campaign.inspect(migrated_db, "p10-start")
    assert result["protocol_digest"] == inspected["protocol_digest"]
    assert inspected["status"] == "active"
    assert "charter" not in inspected and "protocol" not in inspected
    assert "opportunities" not in inspected and "rounds" not in inspected
    assert campaign.start(
        migrated_db, campaign_id="p10-start", charter=case["charter"],
        protocol=case["protocol"], **case["run"]["roots"],
    ) == result


def test_protocol_anchor_content_cannot_repeat_between_rounds(migrated_db, tmp_path):
    from fixtures.p10_campaign import prepare_campaign

    case = prepare_campaign(migrated_db, tmp_path / "prepare", campaign_id="p10-anchor-repeat")
    case["protocol"]["rounds"][1]["epoch"] = case["protocol"]["rounds"][0]["epoch"]
    with pytest.raises(SettlementError, match="anchor content repeats"):
        campaign.start(
            migrated_db, campaign_id="p10-anchor-repeat", charter=case["charter"],
            protocol=case["protocol"], **case["run"]["roots"],
        )


def test_recompute_rejects_changed_protocol_identity_without_gain(migrated_db, tmp_path):
    from fixtures.p10_campaign import prepare_campaign

    case = prepare_campaign(migrated_db, tmp_path / "prepare", campaign_id="p10-export")
    campaign.start(
        migrated_db, campaign_id="p10-export", charter=case["charter"],
        protocol=case["protocol"], **case["run"]["roots"],
    )
    bundle = campaign.export(migrated_db, "p10-export",
                             artifacts_root=case["run"]["roots"]["artifacts_root"])
    result = campaign.recompute(bundle)
    assert result["status"] == "incomplete"
    assert result["comparison_gain"] is False
    assert result["learning_gain"] is False

    changed = copy.deepcopy(bundle)
    changed["protocol_digest"] = "0" * 64
    recomputed = campaign.recompute(changed)
    assert recomputed["status"] == "tampered"
    assert recomputed["comparison_gain"] is False
