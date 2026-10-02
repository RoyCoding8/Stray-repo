from __future__ import annotations

import json
import uuid

import pytest

from settlement import representation as R
from settlement.common import Command, ResultCode
from settlement import store


def _cmd(payload: dict) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _ctx():
    return {"task_id": "t1", "composition_id": "c1",
            "core_digest": "c" * 64, "adapter_digest": "a" * 64}


def _encode_ok(**over):
    base = {"profile": R.PROFILE, "profile_version": R.PROFILE_VERSION,
            "action": "encode", "task_id": "t1", "composition_id": "c1",
            "core_digest": "c" * 64, "adapter_digest": "a" * 64,
            "status": "ok",
            "result": {"encoded_object": {"items": [5, 1]},
                       "aux": {"original": [5, 1]},
                       "applicability": {"supported": True,
                                         "reason": "shrink-list"}}}
    base.update(over)
    return base


def test_version_accepted_once():
    assert R.check_version(R.PROFILE_VERSION) == R.PROFILE_VERSION
    assert R.SUPPORTED_VERSIONS == ("representation-01/1",)


def test_unknown_version_refused():
    with pytest.raises(R.ProfileRefusal) as exc:
        R.check_version("representation-01/999")
    assert exc.value.reason == "unknown-version"


@pytest.mark.parametrize("action", list(R.ACTIONS))
def test_unknown_version_consistent_across_actions(action):
    resp = _encode_ok(action=action, profile_version="representation-01/2")
    if action != "encode":
        resp["result"] = {"proposal": {}} if action in ("start", "advance") \
            else {"candidate_source": {}}
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response(action, resp, **_ctx())
    assert exc.value.reason == "unknown-version"


def test_malformed_bodies():
    ctx = _ctx()
    with pytest.raises(R.ProfileRefusal) as exc:
        R.parse_response_bytes("encode", b"not json", **ctx)
    assert exc.value.reason == "malformed"
    bad = _encode_ok()
    bad["profile"] = "something-else"
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("encode", bad, **ctx)
    assert exc.value.reason == "malformed"
    bad = _encode_ok()
    bad["action"] = "decode"
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("encode", bad, **ctx)
    assert exc.value.reason == "malformed"
    bad = _encode_ok()
    bad["result"] = {"encoded_object": {}}
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("encode", bad, **ctx)
    assert exc.value.reason == "malformed"
    bad = _encode_ok()
    bad["status"] = "refuse"
    bad["reason"] = "telepathy"
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("encode", bad, **ctx)
    assert exc.value.reason == "malformed"
    bad = _encode_ok()
    bad["status"] = "refuse"
    bad["reason"] = "unsupported"
    bad["detail"] = "x" * (R.MAX_REASON_CHARS + 1)
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("encode", bad, **ctx)
    assert exc.value.reason == "malformed"


@pytest.mark.parametrize("key", ["task_id", "composition_id",
                                 "core_digest", "adapter_digest"])
def test_stale_identity_on_any_echo_field(key):
    ctx = _ctx()
    bad = _encode_ok()
    bad[key] = "stale"
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("encode", bad, **ctx)
    assert exc.value.reason == "stale-identity"


def test_oversize_request_and_response():
    ctx = _ctx()
    big = {"profile": R.PROFILE, "profile_version": R.PROFILE_VERSION,
           "action": "encode", "task_id": "t1", "composition_id": "c1",
           "core_digest": "c" * 64, "adapter_digest": "a" * 64,
           "state": None, "payload": {"pad": "x" * R.MAX_MESSAGE_BYTES},
           "budget": {}}
    with pytest.raises(R.ProfileRefusal) as exc:
        R.request_bytes(big)
    assert exc.value.reason == "oversize"
    raw = b'{"a": "' + b"x" * R.MAX_MESSAGE_BYTES + b'"}'
    with pytest.raises(R.ProfileRefusal) as exc:
        R.parse_response_bytes("encode", raw, **ctx)
    assert exc.value.reason == "oversize"
    with pytest.raises(R.ProfileRefusal) as exc:
        R.build_request("teleport", task_id="t", composition_id="c",
                        core_digest="c", adapter_digest="a", state=None,
                        payload={}, remaining={})
    assert exc.value.reason == "malformed"


def test_final_only_for_core_actions():
    ctx = _ctx()
    resp = _encode_ok(status="final", result={"final_object": {}})
    with pytest.raises(R.ProfileRefusal) as exc:
        R.validate_response("decode", resp, **ctx)
    assert exc.value.reason == "malformed"


def test_verdict_vocabulary():
    for verdict in R.FEEDBACK_VERDICTS:
        out = R.validate_verdict({"verdict": verdict, "measure": 3,
                                  "reason": "checked"})
        assert out["verdict"] == verdict
    for bad in ({"verdict": "maybe", "measure": 1, "reason": "r"},
                {"verdict": "preserved", "measure": -1, "reason": "r"},
                {"verdict": "preserved", "measure": 1, "reason": ""},
                {"verdict": "preserved", "measure": 1,
                 "reason": "r" * (R.MAX_REASON_CHARS + 1)}):
        with pytest.raises(R.ProfileRefusal):
            R.validate_verdict(bad)


def test_manifest_names_entries_explicitly():
    manifest = R.manifest_for(b"core", b"adapter", b"desc")
    assert R.resolve_entry(manifest, "core") == "core.py"
    assert R.resolve_entry(manifest, "adapter") == "adapter.py"
    assert R.manifest_component_digests(manifest)["core"] != \
        R.manifest_component_digests(manifest)["adapter"]
    with pytest.raises(Exception):
        R.resolve_entry({"files": [{"path": "core.py"}]}, "core")
    with pytest.raises(R.ProfileRefusal) as exc:
        R.manifest_for(b"c", b"a", b"d", version="representation-01/9")
    assert exc.value.reason == "unknown-version"


def test_step_and_check_identities():
    assert R.step_op_id("run1", "task1", "advance", 3) == \
        "rpr:run1:task1:advance:0003"
    assert R.check_op_id("run1", "task1", 3) == "rpr:run1:task1:check:0003"
    assert R.validation_op_id("run1", "task1", 1) == \
        "rpr:run1:task1:validate:0001"
    with pytest.raises(R.ProfileRefusal):
        R.step_op_id("run:1", "task1", "advance", 0)


CORE = b"print('core')"
ADAPTER = b"print('adapter')"
TRANSFER_ADAPTER = b"print('transfer-adapter')"
DESC = b"shrink-list interpretation"


def _stage_publish(dsn, tmp_roots, core=CORE, adapter=ADAPTER):
    receipt = R.stage_composition(tmp_roots["staging"], core_bytes=core,
                                  adapter_bytes=adapter, description=DESC,
                                  dsn=dsn)
    published = R.publish_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"], receipt)
    assert published.code == ResultCode.APPLIED
    return receipt


def test_composition_lifecycle(migrated_db, tmp_roots):
    dsn = migrated_db
    receipt = _stage_publish(dsn, tmp_roots)
    recorded = R.record_composition(
        dsn, _cmd({"n": "rec1"}), tmp_roots["artifacts"],
        composition_id="comp-src", package_digest=receipt["digest"],
        role="source", protocol_id="proto-1")
    assert recorded.code == ResultCode.APPLIED
    assert recorded.data["role"] == "source"
    row = R.get_composition(dsn, "comp-src")
    assert row["artifact_digest"] == receipt["digest"]
    checked = R.check_composition(dsn, tmp_roots["artifacts"], "comp-src")
    assert checked["ok"] is True
    assert checked["core_digest"] != checked["adapter_digest"]
    again = R.record_composition(
        dsn, _cmd({"n": "rec2"}), tmp_roots["artifacts"],
        composition_id="comp-src", package_digest=receipt["digest"],
        role="source")
    assert again.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    assert "already recorded" in again.detail


def test_transfer_pair_shares_core_bytes(migrated_db, tmp_roots):
    dsn = migrated_db
    src = _stage_publish(dsn, tmp_roots)
    R.record_composition(dsn, _cmd({"n": "r1"}), tmp_roots["artifacts"],
                         composition_id="pair-src",
                         package_digest=src["digest"], role="source")
    dst = _stage_publish(dsn, tmp_roots, adapter=TRANSFER_ADAPTER)
    assert dst["digest"] != src["digest"]
    R.record_composition(dsn, _cmd({"n": "r2"}), tmp_roots["artifacts"],
                         composition_id="pair-xfer",
                         package_digest=dst["digest"], role="transfer")
    first = R.check_composition(dsn, tmp_roots["artifacts"], "pair-src")
    second = R.check_composition(dsn, tmp_roots["artifacts"], "pair-xfer")
    assert R.compositions_share_core(first, second) is True
    assert first["adapter_digest"] != second["adapter_digest"]
    assert first["role"] == "source" and second["role"] == "transfer"


def test_binding_invalid_on_drift(migrated_db, tmp_roots):
    import psycopg
    dsn = migrated_db
    receipt = _stage_publish(dsn, tmp_roots)
    R.record_composition(dsn, _cmd({"n": "r1"}), tmp_roots["artifacts"],
                         composition_id="drift",
                         package_digest=receipt["digest"], role="source")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE capability_versions SET applicability = %s"
                        " WHERE id = %s",
                        (json.dumps({"role": "source",
                                     "core_digest": "0" * 64,
                                     "adapter_digest": "0" * 64}), "drift"))
        conn.commit()
    with pytest.raises(Exception, match="binding invalid"):
        R.check_composition(dsn, tmp_roots["artifacts"], "drift")


def test_record_refuses_unknown_package(migrated_db, tmp_roots):
    dsn = migrated_db
    with pytest.raises(Exception):
        R.record_composition(dsn, _cmd({"n": "rx"}), tmp_roots["artifacts"],
                             composition_id="ghost",
                             package_digest="0" * 64, role="source")
    with pytest.raises(Exception):
        R.publish_composition(dsn, _cmd({"n": "px"}), tmp_roots["artifacts"],
                              {"manifest": {"profile": "other"}, "digest": "x"})
