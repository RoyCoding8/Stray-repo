import io
import tarfile
import uuid

import pytest

from settlement import artifacts, context, evidence, store
from settlement.common import Command, MissingEvidence, ResultCode


def _cmd(payload=None):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {})


def _seed(dsn, inv="inv_e", att="att_e"):
    store.admit_commitment(dsn, _cmd({"investigation_id": inv, "objective": "o"}))
    store.acquire_work(dsn, _cmd({"investigation_id": inv, "attempt_id": att}))
    return inv, att


def _warrant(dsn, claim, obs_receipt):
    evidence.propose_claim(dsn, _cmd(), claim, {"p": 1}, [])
    evidence.admit_warrant(dsn, _cmd(), f"w_{claim}", claim, "test-proc", "v1",
                           [[(obs_receipt, "observation")]])


def test_retraction_bumps_epoch_in_same_commit(migrated_db):
    dsn = migrated_db
    _, att = _seed(dsn)
    obs = evidence.register_observation(dsn, _cmd(), att, {"n": 1}, source_identity="src")
    _warrant(dsn, "c1", obs.data["receipt_id"])
    before = store.get_control(dsn)["evidence_epoch"]
    assert evidence.check_use(dsn, "c1", before)["supported"] is True
    ret = evidence.retract(dsn, _cmd(), obs.data["receipt_id"], "bad source")
    assert ret.data["evidence_epoch"] == store.get_control(dsn)["evidence_epoch"] == before + 1
    with pytest.raises(MissingEvidence):
        evidence.check_use(dsn, "c1", before)


def test_defeat_bumps_epoch_and_blocks_use(migrated_db):
    dsn = migrated_db
    _, att = _seed(dsn)
    obs = evidence.register_observation(dsn, _cmd(), att, {"n": 1}, source_identity="src")
    _warrant(dsn, "c2", obs.data["receipt_id"])
    epoch = store.get_control(dsn)["evidence_epoch"]
    out = evidence.register_opposition(dsn, _cmd(), "opp1", "c2", "defeat", {})
    assert out.data["evidence_epoch"] == epoch + 1
    with pytest.raises(MissingEvidence):
        evidence.check_use(dsn, "c2", epoch)


def test_plain_opposition_leaves_epoch_and_support(migrated_db):
    dsn = migrated_db
    _, att = _seed(dsn)
    obs = evidence.register_observation(dsn, _cmd(), att, {"n": 1}, source_identity="src")
    _warrant(dsn, "c3", obs.data["receipt_id"])
    epoch = store.get_control(dsn)["evidence_epoch"]
    out = evidence.register_opposition(dsn, _cmd(), "opp2", "c3", "opposition", {})
    assert out.data["evidence_epoch"] == epoch
    assert evidence.check_use(dsn, "c3", epoch)["supported"] is True


def test_observation_for_unknown_attempt_refused(migrated_db):
    dsn = migrated_db
    out = evidence.register_observation(dsn, _cmd(), "no_such_attempt", {"n": 1},
                                        source_identity="src")
    assert out.code == ResultCode.INVALID_INPUT


def test_support_view_defaults_to_public_scope(migrated_db, tmp_roots):
    dsn = migrated_db
    _, att = _seed(dsn)
    receipt = artifacts.stage_package(
        dsn, tmp_roots["staging"],
        manifest={"files": [{"path": "a.txt", "kind": "file",
                             "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                             "size": 4}]},
        files={"a.txt": b"test"}, access_label="hidden")
    artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], receipt)
    obs = evidence.register_observation(dsn, _cmd(), att, {"n": 1}, source_identity="src")
    evidence.propose_claim(dsn, _cmd(), "c4", {"p": 1}, [], access_label="public")
    evidence.admit_warrant(dsn, _cmd(), "w_c4", "c4", "proc", "v1",
                           [[(obs.data["receipt_id"], "observation")]])
    assert evidence.claim_support_view(dsn, "c4")["artifact_availability"] == []
    assert [a["digest"] for a in
            evidence.claim_support_view(dsn, "c4", "evaluator")["artifact_availability"]] == \
        [receipt["digest"]]


def _archive_bytes(names):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 3
            tar.addfile(info, io.BytesIO(b"xyz"))
    return buf.getvalue()


def test_archive_traversal_member_rejected(migrated_db, tmp_roots):
    dsn = migrated_db
    raw = _archive_bytes(["../evil.txt"])
    import hashlib
    manifest = {"files": [{"path": "a.tgz", "kind": "archive", "unpack": True,
                           "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]}
    with pytest.raises(Exception):
        artifacts.stage_package(dsn, tmp_roots["staging"], manifest=manifest,
                                files={"a.tgz": raw})


def test_save_continuation_unknown_investigation_leaves_no_bytes(migrated_db, tmp_roots):
    dsn = migrated_db
    before = set(p.name for p in tmp_roots["artifacts"].iterdir())
    out = context.save_continuation(
        dsn, _cmd(), tmp_roots["artifacts"], "no_such_inv", "no_such_att",
        "comp_v1", {"node": 0}, [], [], {}, {"next": "stop"})
    assert out.code == ResultCode.INVALID_INPUT
    assert set(p.name for p in tmp_roots["artifacts"].iterdir()) == before
