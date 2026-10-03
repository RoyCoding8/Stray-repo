from __future__ import annotations

import json
import uuid

import pytest

from settlement import broker, launcher_runsc, store
from settlement import representation as R
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import GatewayError, ModelRequest
from settlement.launcher_local import LocalLauncher

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                       / "experiments"))
from doubles import ScriptedDouble


DIGEST = "sha256:" + "a" * 64


def _cmd(payload: dict) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _setup(dsn, tag):
    store.seed_allocation(dsn, _cmd({"allocation_id": f"a-{tag}",
                                     "domain": "cpu", "authorized": 20000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"i-{tag}",
                                      "objective": "o"}))
    store.acquire_work(dsn, _cmd({"attempt_id": f"att-{tag}",
                                  "investigation_id": f"i-{tag}"}))
    return f"a-{tag}", f"att-{tag}"


CHECKER_V1 = (
    "import json, sys\n"
    "json.load(open(sys.argv[1], encoding='utf-8'))\n"
    "json.dump({'verdict': 'preserved', 'measure': 1, 'reason': 'ok'},\n"
    "          open(sys.argv[2], 'w', encoding='utf-8'))\n"
)

CHECKER_V2 = CHECKER_V1.replace("'measure': 1", "'measure': 2")


def _checker_call(dsn, launcher, run_id, checker_src, alloc, att):
    return R.run_checker(
        dsn, launcher, run_id=run_id, task_id="t1", seq=0,
        checker_bytes=checker_src.encode(), checker_id="chk-1",
        candidate_doc={"candidate": {"items": [5]}},
        allocation_id=alloc, attempt_id=att)


def test_checker_reuse_same_bytes(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "p2dsame")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    first = _checker_call(dsn, launcher, "run-p2d-same", CHECKER_V1,
                          alloc, att)
    assert first["reused"] is False and first["measure"] == 1
    second = _checker_call(dsn, launcher, "run-p2d-same", CHECKER_V1,
                           alloc, att)
    assert second["reused"] is True and second["measure"] == 1


def test_checker_reuse_changed_bytes_refused(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "p2dstale")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    first = _checker_call(dsn, launcher, "run-p2d-stale", CHECKER_V1,
                          alloc, att)
    assert first["reused"] is False
    with pytest.raises(SettlementError):
        _checker_call(dsn, launcher, "run-p2d-stale", CHECKER_V2,
                      alloc, att)


ADAPTER_V1 = (
    "import json, sys\n"
    "req = json.load(open(sys.argv[1], encoding='utf-8'))\n"
    "out = {k: req[k] for k in ('profile', 'profile_version', 'action',\n"
    "      'task_id', 'composition_id', 'core_digest', 'adapter_digest')}\n"
    "out.update({'status': 'ok',\n"
    "            'result': {'candidate_source': {'items': [1]}}})\n"
    "json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'))\n"
)

ADAPTER_V2 = ADAPTER_V1.replace("[1]", "[999]")


def _compose(dsn, tmp_roots, comp_id, adapter_src):
    receipt = R.stage_composition(
        tmp_roots["staging"], core_bytes=b"core",
        adapter_bytes=adapter_src.encode(), description=b"toy", dsn=dsn)
    published = R.publish_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"],
        receipt)
    assert published.code == ResultCode.APPLIED
    recorded = R.record_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"],
        composition_id=comp_id, package_digest=receipt["digest"],
        role="source")
    assert recorded.code == ResultCode.APPLIED
    return comp_id


def _invoke(dsn, launcher, tmp_roots, comp_id, run_id, entry_src, alloc,
            att):
    checked = R.check_composition(dsn, tmp_roots["artifacts"], comp_id)
    request = R.build_request(
        "decode", task_id="t1", composition_id=comp_id,
        core_digest=checked["core_digest"],
        adapter_digest=checked["adapter_digest"], state=None,
        payload={"proposal": {}, "source_task": {}, "aux": None},
        remaining={})
    return R._invoke_entry(
        dsn, launcher, run_id=run_id, task_id="t1", action="decode",
        seq=0, role="adapter", entry_bytes=entry_src.encode(),
        request=request, allocation_id=alloc, attempt_id=att)


def test_invoke_reuse_same_bytes(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "p2disame")
    comp = _compose(dsn, tmp_roots, "comp-p2d-isame", ADAPTER_V1)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    first = _invoke(dsn, launcher, tmp_roots, comp, "run-p2d-isame",
                    ADAPTER_V1, alloc, att)
    assert first["reused"] is False
    assert first["response"]["result"] == {"candidate_source": {"items": [1]}}
    second = _invoke(dsn, launcher, tmp_roots, comp, "run-p2d-isame",
                     ADAPTER_V1, alloc, att)
    assert second["reused"] is True
    assert second["response"]["result"] == {"candidate_source": {"items": [1]}}


def test_invoke_reuse_changed_bytes_refused(migrated_db, tmp_roots,
                                            tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "p2distale")
    comp = _compose(dsn, tmp_roots, "comp-p2d-istale", ADAPTER_V1)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    first = _invoke(dsn, launcher, tmp_roots, comp, "run-p2d-istale",
                    ADAPTER_V1, alloc, att)
    assert first["reused"] is False
    with pytest.raises(SettlementError):
        _invoke(dsn, launcher, tmp_roots, comp, "run-p2d-istale",
                ADAPTER_V2, alloc, att)


def test_runsc_prove_voided_by_generation_record(monkeypatch, tmp_path):
    from types import SimpleNamespace

    def _ok_probe():
        return SimpleNamespace(available=True, reason="test",
                               detail={"docker": "docker"})

    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    monkeypatch.setattr(launcher_runsc.RunscLauncher, "_ps_names",
                        lambda self, prefix: [])
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "gop_exec-default.gen").write_text("3")
    local = LocalLauncher(str(runs))
    assert local.prove_never_sent("gop") is False
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=runs)
    assert launcher.prove_never_sent("gop") is False
    assert launcher.prove_never_sent("fresh-op") is True


def _double_request(op_id):
    body = json.dumps({"arm": "DEV", "task_id": "dev-sum"})
    return ModelRequest(model="m", messages=({"role": "user",
                                             "content": body},),
                        max_output_tokens=16, deadline_ms=10_000,
                        operation_id=op_id)


def test_scripted_double_cancel_refuses_infer():
    double = ScriptedDouble({("DEV", "dev-sum"): True},
                            {"dev-sum": "fixed"}, {})
    ok = double.infer(_double_request("op-new"))
    assert not isinstance(ok, GatewayError)
    assert double.cancel("op-doomed") is True
    refused = double.infer(_double_request("op-doomed"))
    assert isinstance(refused, GatewayError)
    assert refused.kind.value == "cancelled"
    again = double.infer(_double_request("op-new"))
    assert not isinstance(again, GatewayError)
