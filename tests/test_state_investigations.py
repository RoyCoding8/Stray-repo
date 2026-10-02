from __future__ import annotations

import uuid

from settlement import store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _admit(dsn, inv="i1"):
    return store.admit_commitment(dsn, _cmd({"investigation_id": inv, "objective": "reduce failures"}))


def _acquire(dsn, att, inv="i1", **kw):
    return store.acquire_work(dsn, _cmd({"attempt_id": att, "investigation_id": inv, **kw}))


def test_amend_advances_revision_and_stale_is_refused(migrated_db):
    dsn = migrated_db
    assert _admit(dsn).data["revision"] == 1
    ok = store.amend_commitment(dsn, Command(request_id="a1", expected_revision=1,
                                             payload={"investigation_id": "i1", "objective": "v2"}))
    assert ok.code == ResultCode.APPLIED and ok.data["revision"] == 2
    stale = store.amend_commitment(dsn, Command(request_id="a2", expected_revision=1,
                                                payload={"investigation_id": "i1", "objective": "v3"}))
    assert stale.code == ResultCode.STALE_REVISION
    current = store.amend_commitment(dsn, Command(request_id="a3", expected_revision=2,
                                                  payload={"investigation_id": "i1", "objective": "v3"}))
    assert current.data["revision"] == 3


def test_withdraw_blocks_further_work(migrated_db):
    dsn = migrated_db
    _admit(dsn)
    assert store.withdraw_commitment(dsn, _cmd({"investigation_id": "i1"})).code == ResultCode.APPLIED
    assert _acquire(dsn, "attX").code == ResultCode.INVALID_INPUT
    assert store.amend_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "z"})).code \
        == ResultCode.INVALID_INPUT


def test_stale_generation_completion_refused_while_observation_allowed(migrated_db):
    dsn = migrated_db
    _admit(dsn)
    first = _acquire(dsn, "att1", owner="w1")
    second = _acquire(dsn, "att2", owner="w2")
    assert (first.data["ownership_generation"], second.data["ownership_generation"]) == (1, 2)
    stale = store.complete_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": 99}))
    assert stale.code == ResultCode.STALE_REVISION
    observed = store.submit_observation(dsn, _cmd({"attempt_id": "att1", "content": {"note": "partial"}}))
    assert observed.code == ResultCode.APPLIED
    done = store.complete_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": 1}))
    assert done.code == ResultCode.APPLIED


def test_fulfillment_twice_refused_and_needs_completed_attempt(migrated_db):
    dsn = migrated_db
    _admit(dsn)
    acquired = _acquire(dsn, "att1")
    gen = acquired.data["ownership_generation"]
    early = store.fulfill_investigation(dsn, Command(
        request_id="f0", expected_revision=1,
        payload={"investigation_id": "i1", "attempt_id": "att1", "ownership_generation": gen}))
    assert early.code == ResultCode.INVALID_INPUT
    store.complete_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen}))
    first = store.fulfill_investigation(dsn, Command(
        request_id="f1", expected_revision=1,
        payload={"investigation_id": "i1", "attempt_id": "att1", "ownership_generation": gen}))
    assert first.code == ResultCode.APPLIED
    second = store.fulfill_investigation(dsn, Command(
        request_id="f2", expected_revision=1,
        payload={"investigation_id": "i1", "attempt_id": "att1", "ownership_generation": gen}))
    assert second.code == ResultCode.INVALID_INPUT
    stale_rev = store.fulfill_investigation(dsn, Command(
        request_id="f3", expected_revision=7, payload={"investigation_id": "i1"}))
    assert stale_rev.code == ResultCode.STALE_REVISION


def test_fulfillment_after_amend_targets_new_revision(migrated_db):
    dsn = migrated_db
    _admit(dsn)
    a1 = _acquire(dsn, "att1")
    store.complete_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": a1.data["ownership_generation"]}))
    assert store.fulfill_investigation(dsn, Command(
        request_id="f1", expected_revision=1, payload={"investigation_id": "i1"})).code == ResultCode.APPLIED
    reopened = store.amend_commitment(dsn, Command(
        request_id="am1", expected_revision=1,
        payload={"investigation_id": "i1", "objective": "follow-up"}))
    assert reopened.code == ResultCode.APPLIED and reopened.data["revision"] == 2
    refilled = store.fulfill_investigation(dsn, Command(
        request_id="f2", expected_revision=2, payload={"investigation_id": "i1"}))
    assert refilled.code == ResultCode.APPLIED
    assert store.fulfill_investigation(dsn, Command(
        request_id="f3", expected_revision=2, payload={"investigation_id": "i1"})).code \
        == ResultCode.INVALID_INPUT


def test_suspend_resume_lifecycle(migrated_db):
    dsn = migrated_db
    _admit(dsn)
    acquired = _acquire(dsn, "att1")
    gen = acquired.data["ownership_generation"]
    assert store.suspend_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen})).code \
        == ResultCode.APPLIED
    assert store.suspend_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen})).code \
        == ResultCode.INVALID_INPUT
    assert store.resume_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen})).code \
        == ResultCode.APPLIED
    assert store.install_continuation(
        dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen,
                   "continuation_ref": "cont-9"})).code == ResultCode.APPLIED


def test_evidence_epoch_hook_refuses_stale_snapshot(migrated_db):
    dsn = migrated_db
    bumped = store.register_evidence_change(dsn, _cmd({}))
    assert bumped.data["evidence_epoch"] == 1
    stale = store.admit_commitment(
        dsn, _cmd({"investigation_id": "i1", "objective": "o", "evidence_epoch": 0}))
    assert stale.code == ResultCode.MISSING_EVIDENCE
    fresh = store.admit_commitment(
        dsn, _cmd({"investigation_id": "i1", "objective": "o", "evidence_epoch": 1}))
    assert fresh.code == ResultCode.APPLIED


def test_occupancy_limit_blocks_acquire(migrated_db):
    dsn = migrated_db
    _admit(dsn)
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 1000,
                                     "max_occupancy": 1}))
    assert _acquire(dsn, "att1", allocation_id="a1").code == ResultCode.APPLIED
    assert _acquire(dsn, "att2", allocation_id="a1").code == ResultCode.INSUFFICIENT_RESOURCES
