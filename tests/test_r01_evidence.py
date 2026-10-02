from __future__ import annotations

import threading
import pytest
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from settlement import db, evidence, store
from settlement.common import Command, MissingEvidence


def _cmd(payload=None, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {}, **kw)


def _setup(dsn):
    store.admit_commitment(dsn, _cmd({"investigation_id": "inv1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "inv1"}))


def _obs(dsn, content="seen"):
    return evidence.register_observation(
        dsn, _cmd(), "att1", {"note": content},
        source_identity="sensor-1", conditions={"lab": "a"}).data["receipt_id"]


def _claim_with_obs(dsn, claim_id, derivation_id, receipt):
    evidence.propose_claim(dsn, _cmd(), claim_id, {"text": claim_id})
    evidence.admit_warrant(dsn, _cmd(), derivation_id, claim_id, "proof", "v1",
                           [[(receipt, "observation")]])


def test_retracted_claim_root_is_not_supported(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    _claim_with_obs(dsn, "c-root", "d-root", _obs(dsn))
    assert evidence.current_support(dsn, "c-root")["supported"] is True
    evidence.retract(dsn, _cmd(), "c-root", "claim withdrawn")
    assert evidence.current_support(dsn, "c-root")["supported"] is False
    with pytest.raises(MissingEvidence):
        evidence.check_use(dsn, "c-root", store.get_control(dsn)["evidence_epoch"])


def test_derivation_only_retraction_preserves_alternate_support(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    a, b = _obs(dsn, "a"), _obs(dsn, "b")
    evidence.propose_claim(dsn, _cmd(), "c-alt", {"text": "p"})
    evidence.admit_warrant(dsn, _cmd(), "d-alt1", "c-alt", "proof", "v1",
                           [[(a, "observation")]])
    evidence.admit_warrant(dsn, _cmd(), "d-alt2", "c-alt", "proof", "v1",
                           [[(b, "observation")]])
    evidence.retract(dsn, _cmd(), "d-alt1", "bad run")
    after = evidence.current_support(dsn, "c-alt")
    assert after["supported"] is True and after["derivations"] == ["d-alt2"]
    evidence.retract(dsn, _cmd(), b, "rerun failed")
    assert evidence.current_support(dsn, "c-alt")["supported"] is False


def test_retracted_premise_claim_kills_dependent_support(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    _claim_with_obs(dsn, "c-base", "d-base", _obs(dsn))
    evidence.propose_claim(dsn, _cmd(), "c-dep", {"text": "q"})
    evidence.admit_warrant(dsn, _cmd(), "d-dep", "c-dep", "proof", "v1",
                           [[("c-base", "claim")]])
    assert evidence.current_support(dsn, "c-dep")["supported"] is True
    evidence.retract(dsn, _cmd(), "c-base", "basis withdrawn")
    assert evidence.current_support(dsn, "c-base")["supported"] is False
    assert evidence.current_support(dsn, "c-dep")["supported"] is False


def _control_waiter_present(dsn) -> bool:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_locks WHERE NOT granted AND pid <> pg_backend_pid()")
            return cur.fetchone() is not None


def test_concurrent_invalidation_never_labels_stale_true_with_new_epoch(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _setup(dsn)
    receipt = _obs(dsn)
    _claim_with_obs(dsn, "c-race", "d-race", receipt)
    epoch_before = store.get_control(dsn)["evidence_epoch"]
    assert evidence.current_support(dsn, "c-race")["supported"] is True
    entered, release, committed = (threading.Event(), threading.Event(),
                                   threading.Event())
    real_supported = evidence._supported

    def hooked(cur, claim_id, stack, artifacts_root):
        out = real_supported(cur, claim_id, stack, artifacts_root)
        entered.set()
        assert release.wait(timeout=60)
        return out

    monkeypatch.setattr(evidence, "_supported", hooked)

    def invalidate():
        evidence.retract(dsn, _cmd(), receipt, "withdrawn")
        committed.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(evidence.current_support, dsn, "c-race")
        assert entered.wait(timeout=60)
        worker = threading.Thread(target=invalidate)
        worker.start()
        deadline = time.monotonic() + 15
        while not committed.is_set() and not _control_waiter_present(dsn):
            if time.monotonic() > deadline:
                break
            time.sleep(0.05)
        release.set()
        snap = fut.result(timeout=60)
        worker.join(timeout=60)
    assert committed.is_set()
    fresh = evidence.current_support(dsn, "c-race")
    assert fresh["supported"] is False
    assert not (snap["supported"] and snap["epoch"] == fresh["epoch"]
                and not fresh["supported"]), snap
    if snap["supported"]:
        assert snap["epoch"] == epoch_before, snap
    else:
        assert snap["epoch"] > epoch_before, snap
