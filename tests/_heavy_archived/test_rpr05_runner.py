from __future__ import annotations

import sys
import time
import uuid

import pytest

from settlement import representation as R
from settlement.common import Command, ResultCode
from settlement import store
from settlement.launcher_local import LocalLauncher


DSN_ENV = "SETTLEMENT_TEST_DSN"

ADAPTER = '''
import json, sys

def _base(req):
    return {"profile": req["profile"], "profile_version": req["profile_version"],
            "action": req["action"], "task_id": req["task_id"],
            "composition_id": req["composition_id"],
            "core_digest": req["core_digest"],
            "adapter_digest": req["adapter_digest"]}

def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"adapter": True}}))
        return 0
    req = json.load(open(argv[0], encoding="utf-8"))
    out = _base(req)
    if req["action"] == "encode":
        task = req["payload"]["source_task"]
        spec = req["payload"]["domain_spec"]
        items = task.get("items") if isinstance(task, dict) else None
        if spec.get("family") != "shrink-list" or not isinstance(items, list) \\
                or not items or any(not isinstance(x, int) for x in items):
            out.update({"status": "refuse", "reason": "unsupported",
                        "detail": "not shrink-list"})
        else:
            out.update({"status": "ok",
                        "result": {"encoded_object": {"items": list(items)},
                                   "aux": {"original": list(items),
                                           "witness_first": items[0]},
                                   "applicability": {"supported": True,
                                                     "reason": "shrink-list"}}})
    elif req["action"] == "decode":
        out.update({"status": "ok",
                    "result": {"candidate_source": req["payload"]["proposal"]}})
    else:
        out.update({"status": "refuse", "reason": "unsupported",
                    "detail": "adapter cannot start"})
    json.dump(out, open(argv[1], "w", encoding="utf-8"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

CORE = '''
import json, sys

def _base(req):
    return {"profile": req["profile"], "profile_version": req["profile_version"],
            "action": req["action"], "task_id": req["task_id"],
            "composition_id": req["composition_id"],
            "core_digest": req["core_digest"],
            "adapter_digest": req["adapter_digest"]}

def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"core": True}}))
        return 0
    req = json.load(open(argv[0], encoding="utf-8"))
    out = _base(req)
    if req["action"] == "start":
        items = list(req["payload"]["encoded_object"]["items"])
        if len(items) <= 1:
            out.update({"status": "final",
                        "result": {"final_object": {"items": items}}})
        else:
            last = items[:-1]
            out.update({"status": "ok",
                        "result": {"proposal": {"items": last}},
                        "state": {"current": items, "last": last}})
    elif req["action"] == "advance":
        fb = req["payload"]["feedback"] or {}
        state = req["state"] or {}
        current = list(state.get("current", []))
        last = list(state.get("last", current))
        if fb.get("verdict") == "preserved":
            current = last
        if len(current) <= 1:
            out.update({"status": "final",
                        "result": {"final_object": {"items": current}}})
        else:
            last = current[:-1]
            out.update({"status": "ok",
                        "result": {"proposal": {"items": last}},
                        "state": {"current": current, "last": last}})
    else:
        out.update({"status": "refuse", "reason": "unsupported",
                    "detail": "core cannot encode"})
    json.dump(out, open(argv[1], "w", encoding="utf-8"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

CHECKER = '''
import json, sys
from collections import Counter

def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"checker": True}}))
        return 0
    doc = json.load(open(argv[0], encoding="utf-8"))
    cand = doc.get("candidate") or {}
    items = cand.get("items") if isinstance(cand, dict) else None
    orig = (doc.get("source_task") or {}).get("items")
    first = orig[0] if isinstance(orig, list) and orig else None
    if not isinstance(items, list) or not items \\
            or any(not isinstance(x, int) or isinstance(x, bool) for x in items):
        verdict = ("invalid", None, "not-a-nonempty-int-list")
    elif not isinstance(orig, list) or list((Counter(items) - Counter(orig)).elements()):
        verdict = ("invalid", None, "not-a-sublist")
    elif items[0] != first or len(items) >= len(orig):
        verdict = ("not_preserved", len(items), "witness-or-measure-lost")
    else:
        verdict = ("preserved", len(items), "strict-shrink-first-kept")
    json.dump({"verdict": verdict[0], "measure": verdict[1],
               "reason": verdict[2]}, open(argv[1], "w", encoding="utf-8"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

CORE_FIRST_BAD = CORE.replace(
    '''        if len(items) <= 1:
            out.update({"status": "final",
                        "result": {"final_object": {"items": items}}})
        else:
            last = items[:-1]''',
    '''        if len(items) <= 1:
            out.update({"status": "final",
                        "result": {"final_object": {"items": items}}})
        else:
            last = [999]''')

CORE_NEVER_FINAL = CORE.replace(
    'last = items[:-1]',
    'last = list(items)').replace(
    'last = current[:-1]',
    'last = list(current)')

CORE_SLEEP = CORE.replace(
    '    req = json.load(open(argv[0], encoding="utf-8"))',
    '    req = json.load(open(argv[0], encoding="utf-8"))\n'
    '    import time as _t\n'
    '    _t.sleep(6)')

ADAPTER_REFUSE_DECODE = ADAPTER.replace(
    '''    elif req["action"] == "decode":
        out.update({"status": "ok",
                    "result": {"candidate_source": req["payload"]["proposal"]}})''',
    '''    elif req["action"] == "decode":
        out.update({"status": "refuse", "reason": "unsupported",
                    "detail": "cannot-decode"})''')

CHECKER_CRASH = 'import sys\nsys.exit(1)\n'
CHECKER_SLEEP = 'import time\ntime.sleep(6)\n'


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


def _compose(dsn, tmp_roots, comp_id, core=CORE, adapter=ADAPTER,
             role="source"):
    receipt = R.stage_composition(
        tmp_roots["staging"], core_bytes=core.encode(),
        adapter_bytes=adapter.encode(), description=b"toy", dsn=dsn)
    published = R.publish_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"], receipt)
    assert published.code == ResultCode.APPLIED
    recorded = R.record_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"],
        composition_id=comp_id, package_digest=receipt["digest"], role=role)
    assert recorded.code == ResultCode.APPLIED
    return comp_id


def _run(dsn, launcher, tmp_roots, run_id, comp_id, alloc, att, **kw):
    params = {"run_id": run_id, "task_id": "t1", "composition_id": comp_id,
              "source_task": {"items": [5, 1, 8, 3]},
              "domain_spec": {"family": "shrink-list",
                              "witness": "first-element"},
              "checker_bytes": CHECKER.encode(), "checker_id": "chk-1",
              "initial_incumbent": {"items": [5, 1, 8, 3]},
              "initial_measure": 4, "allocation_id": alloc,
              "attempt_id": att}
    params.update(kw)
    return R.run_task(dsn, launcher, tmp_roots["artifacts"], **params)


def test_happy_path_improved(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "happy")
    comp = _compose(dsn, tmp_roots, "comp-happy")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = _run(dsn, launcher, tmp_roots, "run-happy", comp, alloc, att)
    assert result["disposition"] == "improved"
    assert result["best_measure"] == 1
    assert result["incumbent"] == {"items": [5]}
    assert result["verified"] is True
    assert result["invocations_used"] == 9
    assert result["queries_used"] == 4
    assert result["validation_used"] == 2
    assert "core" not in sys.modules and "adapter" not in sys.modules


def test_failed_proposal_keeps_incumbent(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "badfirst")
    comp = _compose(dsn, tmp_roots, "comp-badfirst", core=CORE_FIRST_BAD)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = _run(dsn, launcher, tmp_roots, "run-badfirst", comp, alloc, att)
    assert result["disposition"] == "improved"
    assert result["best_measure"] == 1
    assert result["incumbent"] == {"items": [5]}
    bad = [s for s in result["steps"]
           if (s.get("verdict") or {}).get("reason") == "not-a-sublist"]
    assert len(bad) == 1


def test_checker_crash_is_unknown(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "chkcrash")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    out = R.run_checker(dsn, launcher, run_id="run-chkcrash", task_id="t1",
                        seq=0, checker_bytes=CHECKER_CRASH.encode(),
                        checker_id="chk-x",
                        candidate_doc={"candidate": {"items": [5]}},
                        allocation_id=alloc, attempt_id=att)
    assert out["verdict"] == "unknown"
    assert out["reason"] == "checker-failure"


def test_checker_timeout_is_unknown(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "chksleep")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    started = time.monotonic()
    out = R.run_checker(dsn, launcher, run_id="run-chksleep", task_id="t1",
                        seq=0, checker_bytes=CHECKER_SLEEP.encode(),
                        checker_id="chk-x",
                        candidate_doc={"candidate": {"items": [5]}},
                        allocation_id=alloc, attempt_id=att)
    assert out["verdict"] == "unknown"
    assert out["reason"] == "timeout"
    assert time.monotonic() - started < 30


def test_witness_query_budget_exhausted(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "qbudget")
    comp = _compose(dsn, tmp_roots, "comp-qbudget", core=CORE_NEVER_FINAL)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = _run(dsn, launcher, tmp_roots, "run-qbudget", comp, alloc, att)
    assert result["disposition"] == "budget_exhausted"
    assert result["queries_used"] == R.MAX_WITNESS_QUERIES == 16
    assert result["invocations_used"] == 35
    assert result["incumbent"] == {"items": [5, 1, 8, 3]}


def test_invocation_budget_exhausted(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "ibudget")
    comp = _compose(dsn, tmp_roots, "comp-ibudget",
                    adapter=ADAPTER_REFUSE_DECODE)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = _run(dsn, launcher, tmp_roots, "run-ibudget", comp, alloc, att)
    assert result["disposition"] == "budget_exhausted"
    assert result["invocations_used"] == R.MAX_INVOCATIONS == 64
    assert result["queries_used"] == 0


def test_elapsed_budget_exhausted(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "elapsed")
    comp = _compose(dsn, tmp_roots, "comp-elapsed")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    ticks = [0.0] * 4 + [200.0] * 100
    clock = lambda: ticks.pop(0) if ticks else 200.0  # noqa: E731
    result = _run(dsn, launcher, tmp_roots, "run-elapsed", comp, alloc, att,
                  now=clock, started_at=0.0)
    assert result["disposition"] == "budget_exhausted"
    assert "elapsed" in result["reason"]
    assert result["invocations_used"] == 2


def test_per_invocation_timeout(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "timeout")
    comp = _compose(dsn, tmp_roots, "comp-timeout", core=CORE_SLEEP)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    started = time.monotonic()
    result = _run(dsn, launcher, tmp_roots, "run-timeout", comp, alloc, att,
                  max_advances=0)
    assert time.monotonic() - started < 60
    assert result["invocations_used"] == 2
    timed = [s for s in result["steps"] if s.get("timed_out")]
    assert len(timed) == 1


def test_oversize_request_refused_before_dispatch(migrated_db, tmp_roots,
                                                  tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "oversize")
    comp = _compose(dsn, tmp_roots, "comp-oversize")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = _run(dsn, launcher, tmp_roots, "run-oversize", comp, alloc, att,
                  source_task={"items": list(range(30000))})
    assert result["disposition"] == "refused"
    assert result["reason"] == "oversize"
    assert R.task_usage(dsn, "run-oversize", "t1")["invocations"] == 0


def _direct_invoke(dsn, launcher, tmp_roots, comp_id, run_id, action, seq,
                   role, entry_src, alloc, att):
    checked = R.check_composition(dsn, tmp_roots["artifacts"], comp_id)
    request = R.build_request(
        action, task_id="t1", composition_id=comp_id,
        core_digest=checked["core_digest"],
        adapter_digest=checked["adapter_digest"], state=None,
        payload={"proposal": {}, "source_task": {}, "aux": None},
        remaining={})
    return R._invoke_entry(
        dsn, launcher, run_id=run_id, task_id="t1", action=action, seq=seq,
        role=role, entry_bytes=entry_src.encode(), request=request,
        allocation_id=alloc, attempt_id=att)


@pytest.mark.parametrize("variant,reason", [
    ("bad-version", "unknown-version"),
    ("garbage", "malformed"),
    ("stale", "stale-identity"),
    ("huge", "oversize"),
])
def test_entry_refusal_taxonomy(migrated_db, tmp_roots, tmp_path, variant,
                                reason):
    dsn = migrated_db
    alloc, att = _setup(dsn, f"invoke-{variant}")
    comp = _compose(dsn, tmp_roots, f"comp-{variant}")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    src = ADAPTER
    if variant == "bad-version":
        src = ADAPTER.replace('"profile_version": req["profile_version"],',
                              '"profile_version": "representation-01/999",')
    elif variant == "garbage":
        src = 'import sys\nopen(sys.argv[2], "wb").write(b"\\x00nope")\n'
    elif variant == "stale":
        src = ADAPTER.replace('"task_id": req["task_id"],',
                              '"task_id": "someone-else",')
    elif variant == "huge":
        src = ADAPTER.replace(
            '''    elif req["action"] == "decode":
        out.update({"status": "ok",
                    "result": {"candidate_source": req["payload"]["proposal"]}})''',
            '''    elif req["action"] == "decode":
        out.update({"status": "ok", "state": "x" * 70000,
                    "result": {"candidate_source": req["payload"]["proposal"]}})''')
    with pytest.raises(R.ProfileRefusal) as exc:
        _direct_invoke(dsn, launcher, tmp_roots, comp, f"run-{variant}",
                       "decode", 40, "adapter", src, alloc, att)
    assert exc.value.reason == reason


def test_host_never_imports_entries(migrated_db, tmp_roots, tmp_path):
    marker = tmp_path / "marker.txt"
    src = ADAPTER.replace(
        "import json, sys",
        f"import json, sys\nopen({str(marker)!r}, 'a').write('main\\n')", 1)
    dsn = migrated_db
    alloc, att = _setup(dsn, "noimport")
    comp = _compose(dsn, tmp_roots, "comp-noimport", adapter=src)
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = _run(dsn, launcher, tmp_roots, "run-noimport", comp, alloc, att)
    assert result["disposition"] == "improved"
    assert marker.exists()
    assert "marker_adapter" not in sys.modules
    assert "noimport" not in "".join(sys.modules)
