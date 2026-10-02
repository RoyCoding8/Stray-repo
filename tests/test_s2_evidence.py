from __future__ import annotations

import uuid

import pytest

from settlement import evidence, store
from settlement.common import Command, MissingEvidence, ResultCode, SettlementError


def _cmd(payload=None, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {}, **kw)


def _setup(dsn):
    store.admit_commitment(dsn, _cmd({"investigation_id": "inv1", "objective": "o"}))
    gen = store.acquire_work(
        dsn, _cmd({"attempt_id": "att1", "investigation_id": "inv1"})).data["ownership_generation"]
    return gen


def _obs(dsn, content="seen", source="sensor-1"):
    return evidence.register_observation(
        dsn, _cmd(), "att1", {"note": content}, source_identity=source,
        conditions={"lab": "a"}).data["receipt_id"]


def test_interpretive_text_cannot_mint_authenticated_receipt(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    noted = evidence.register_observation(dsn, _cmd(), "att1", {"note": "guess"})
    assert noted.data["authenticated"] is False
    receipt = noted.data["receipt_id"]
    evidence.propose_claim(dsn, _cmd(), "c-note", {"text": "guess-true"})
    evidence.admit_warrant(dsn, _cmd(), "d-note", "c-note", "review", "v1",
                           [[(receipt, "observation")]])
    assert evidence.current_support(dsn, "c-note")["supported"] is False
    authed = _obs(dsn)
    evidence.propose_claim(dsn, _cmd(), "c-real", {"text": "seen-true"})
    evidence.admit_warrant(dsn, _cmd(), "d-real", "c-real", "review", "v1",
                           [[(authed, "observation")]])
    assert evidence.current_support(dsn, "c-real")["supported"] is True


def test_grouped_retraction_preserves_alternative_then_flips_last_route(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    a = _obs(dsn, "a")
    b = _obs(dsn, "b")
    d = _obs(dsn, "d")
    evidence.propose_claim(dsn, _cmd(), "c1", {"text": "p"})
    evidence.admit_warrant(dsn, _cmd(), "d1", "c1", "proof", "v3",
                           [[(a, "observation"), (b, "observation")]])
    evidence.admit_warrant(dsn, _cmd(), "d2", "c1", "experiment", "v1",
                           [[(d, "observation")]])
    assert evidence.current_support(dsn, "c1")["supported"] is True
    epoch_before = store.get_control(dsn)["evidence_epoch"]
    evidence.retract(dsn, _cmd(), b, "sensor faulty")
    after = evidence.current_support(dsn, "c1")
    assert after["supported"] is True and after["derivations"] == ["d2"]
    evidence.retract(dsn, _cmd(), d, "rerun failed")
    assert evidence.current_support(dsn, "c1")["supported"] is False
    with pytest.raises(MissingEvidence):
        evidence.check_use(dsn, "c1", epoch_before)
    with pytest.raises(MissingEvidence):
        evidence.check_use(dsn, "c1", store.get_control(dsn)["evidence_epoch"])


def test_same_group_joint_premises_all_required(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    a = _obs(dsn, "a")
    b = _obs(dsn, "b")
    evidence.propose_claim(dsn, _cmd(), "c2", {"text": "p"})
    evidence.admit_warrant(dsn, _cmd(), "d3", "c2", "proof", "v1",
                           [[(a, "observation"), (b, "observation")]])
    assert evidence.current_support(dsn, "c2")["supported"] is True
    evidence.retract(dsn, _cmd(), a)
    assert evidence.current_support(dsn, "c2")["supported"] is False


def test_multi_group_derivation_survives_partial_retraction(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    a = _obs(dsn, "a")
    b = _obs(dsn, "b")
    evidence.propose_claim(dsn, _cmd(), "c3", {"text": "p"})
    evidence.admit_warrant(dsn, _cmd(), "d4", "c3", "proof", "v1",
                           [[(a, "observation")], [(b, "observation")]])
    evidence.retract(dsn, _cmd(), a)
    assert evidence.current_support(dsn, "c3")["supported"] is True


def test_stale_admissibility_loses_against_fulfillment_order(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    a = _obs(dsn, "a")
    evidence.propose_claim(dsn, _cmd(), "c4", {"text": "p"})
    evidence.admit_warrant(dsn, _cmd(), "d5", "c4", "proof", "v1", [[(a, "observation")]])
    snap_epoch = store.get_control(dsn)["evidence_epoch"]
    assert evidence.check_use(dsn, "c4", snap_epoch)["supported"] is True
    evidence.retract(dsn, _cmd(), a, "withdrawn")
    store.complete_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen,
                                      "outcome": "completed"}))
    stale = store.fulfill_investigation(
        dsn, _cmd({"investigation_id": "inv1", "attempt_id": "att1",
                   "ownership_generation": gen, "evidence_epoch": snap_epoch}))
    assert stale.code == ResultCode.MISSING_EVIDENCE
    fresh = store.fulfill_investigation(
        dsn, _cmd({"investigation_id": "inv1", "attempt_id": "att1",
                   "ownership_generation": gen}))
    assert fresh.code == ResultCode.APPLIED


def test_defeat_blocks_but_opposition_does_not(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    a = _obs(dsn, "a")
    evidence.propose_claim(dsn, _cmd(), "c5", {"text": "p"})
    evidence.admit_warrant(dsn, _cmd(), "d6", "c5", "proof", "v1", [[(a, "observation")]])
    evidence.register_opposition(dsn, _cmd(), "o1", "c5", "opposition", {"note": "doubt"})
    assert evidence.current_support(dsn, "c5")["supported"] is True
    evidence.register_opposition(dsn, _cmd(), "o2", "c5", "defeat", {"note": "counterexample"})
    assert evidence.current_support(dsn, "c5")["supported"] is False


def test_relation_kinds_are_distinct_and_cyclic_claims_terminate(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    a = _obs(dsn, "a")
    evidence.propose_claim(dsn, _cmd(), "c6", {"text": "p"})
    evidence.propose_claim(dsn, _cmd(), "c7", {"text": "q"})
    evidence.admit_warrant(dsn, _cmd(), "d7", "c6", "proof", "v1",
                           [[(a, "observation"), ("c7", "claim")]])
    evidence.admit_warrant(dsn, _cmd(), "d8", "c7", "proof", "v1", [[("c6", "claim")]])
    assert evidence.current_support(dsn, "c6")["supported"] is False
    for kind in ("background", "attribution", "equivalence"):
        result = evidence.record_relation(dsn, _cmd(), "c6", "c7", kind)
        assert result.code == ResultCode.APPLIED
    with pytest.raises(SettlementError):
        evidence.record_relation(dsn, _cmd(), "c6", "c7", "vibes")
    view = evidence.claim_support_view(dsn, "c6")
    assert {p["premise_kind"] for p in view["premises"]} == {"observation", "claim"}


def test_hidden_claims_scoped_in_sql(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    evidence.propose_claim(dsn, _cmd(), "c-pub", {"text": "open"})
    evidence.propose_claim(dsn, _cmd(), "c-hid", {"text": "sealed"}, access_label="hidden")
    candidate = {row["id"] for row in evidence.scoped_claims(dsn, "candidate")}
    evaluator = {row["id"] for row in evidence.scoped_claims(dsn, "evaluator")}
    assert "c-pub" in candidate and "c-hid" not in candidate
    assert "c-hid" in evaluator
