from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from settlement import representation as R
from settlement.common import Command, ResultCode
from settlement import store
from settlement.launcher_local import LocalLauncher

REPO = Path(R.__file__).resolve().parent.parent.parent
SRC = str(REPO / "src")
PY = sys.executable

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


class CountingLauncher(LocalLauncher):
    def __init__(self, run_dir):
        super().__init__(run_dir)
        self.sends: list[str] = []

    def dispatch(self, op):
        self.sends.append(op.operation_id)
        return super().dispatch(op)


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


def _compose(dsn, tmp_roots, comp_id):
    receipt = R.stage_composition(
        tmp_roots["staging"], core_bytes=CORE.encode(),
        adapter_bytes=ADAPTER.encode(), description=b"toy", dsn=dsn)
    published = R.publish_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"], receipt)
    assert published.code == ResultCode.APPLIED
    recorded = R.record_composition(
        dsn, _cmd({"n": uuid.uuid4().hex}), tmp_roots["artifacts"],
        composition_id=comp_id, package_digest=receipt["digest"],
        role="source")
    assert recorded.code == ResultCode.APPLIED
    return comp_id


def _params(run_id, comp_id, alloc, att, **kw):
    params = {"run_id": run_id, "task_id": "t1", "composition_id": comp_id,
              "source_task": {"items": [5, 1, 8, 3]},
              "domain_spec": {"family": "shrink-list",
                              "witness": "first-element"},
              "checker_bytes": CHECKER.encode(), "checker_id": "chk-1",
              "initial_incumbent": {"items": [5, 1, 8, 3]},
              "initial_measure": 4, "allocation_id": alloc,
              "attempt_id": att}
    params.update(kw)
    return params


def _receipt_count(dsn, operation_id):
    import psycopg
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts WHERE operation_id = %s",
                        (operation_id,))
            return int(cur.fetchone()[0])


def test_pause_resume_reuses_settled_steps(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "resume1")
    comp = _compose(dsn, tmp_roots, "comp-resume1")
    run_dir = str(tmp_path / "runs")
    first = R.run_task(dsn, LocalLauncher(run_dir), tmp_roots["artifacts"],
                       **_params("run-resume1", comp, alloc, att,
                                max_advances=1))
    assert first["disposition"] == "paused"
    assert first["invocations_used"] == 5
    settled = [s["op_id"] for s in first["steps"]]
    before = {op: _receipt_count(dsn, op) for op in settled}
    counting = CountingLauncher(run_dir)
    second = R.run_task(dsn, counting, tmp_roots["artifacts"],
                        **_params("run-resume1", comp, alloc, att))
    assert second["disposition"] == "improved"
    assert second["incumbent"] == {"items": [5]}
    assert second["invocations_used"] == 9
    assert second["queries_used"] == 4
    assert second["validation_used"] == 2
    resent = [op for op in counting.sends if op in settled]
    assert resent == []
    for op in settled:
        assert _receipt_count(dsn, op) == before[op]


def test_fresh_process_resume(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "resume2")
    comp = _compose(dsn, tmp_roots, "comp-resume2")
    run_dir = str(tmp_path / "runs")
    first = R.run_task(dsn, LocalLauncher(run_dir), tmp_roots["artifacts"],
                       **_params("run-resume2", comp, alloc, att,
                                max_advances=1))
    assert first["disposition"] == "paused"
    settled = {s["op_id"] for s in first["steps"]}
    fresh_dir = str(tmp_path / "fresh-runs")
    params = _params("run-resume2", comp, alloc, att)
    checker_text = params.pop("checker_bytes").decode("utf-8")
    args = {"dsn": dsn, "run_dir": fresh_dir,
            "artifacts": str(tmp_roots["artifacts"]),
            "checker_text": checker_text, "params": params}
    driver = "\n".join([
        "import json, sys",
        "sys.path.insert(0, " + repr(SRC) + ")",
        "from settlement import representation as R",
        "from settlement.launcher_local import LocalLauncher",
        "class C(LocalLauncher):",
        "    send_log = []",
        "    def dispatch(self, op):",
        "        C.send_log.append(op.operation_id)",
        "        return super().dispatch(op)",
        "args = json.loads(sys.argv[1])",
        "args['params']['checker_bytes'] = "
        "args.pop('checker_text').encode('utf-8')",
        "res = R.run_task(args['dsn'], C(args['run_dir']), args['artifacts'],"
        " **args['params'])",
        "print(json.dumps({'disposition': res['disposition'],"
        " 'incumbent': res['incumbent'],"
        " 'invocations_used': res['invocations_used'],"
        " 'queries_used': res['queries_used'],"
        " 'validation_used': res['validation_used'],"
        " 'resent': [o for o in C.send_log if o in set(args['settled'])]},"
        " sort_keys=True))",
    ])
    args["settled"] = sorted(settled)
    env = dict(os.environ, PYTHONPATH=SRC)
    proc = subprocess.run([PY, "-c", driver, json.dumps(args)],
                          capture_output=True, text=True, timeout=300, env=env)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["disposition"] == "improved"
    assert out["incumbent"] == {"items": [5]}
    assert out["invocations_used"] == 9
    assert out["queries_used"] == 4
    assert out["validation_used"] == 2
    assert out["resent"] == []


def test_fresh_database_is_not_resume(migrated_db, tmp_roots, tmp_path):
    import psycopg
    dsn = migrated_db
    alloc, att = _setup(dsn, "resume3")
    comp = _compose(dsn, tmp_roots, "comp-resume3")
    run_dir = str(tmp_path / "runs")
    first = R.run_task(dsn, LocalLauncher(run_dir), tmp_roots["artifacts"],
                       **_params("run-resume3", comp, alloc, att,
                                max_advances=1))
    assert first["disposition"] == "paused"
    fresh_name = "settlement_cb01exec_fresh"
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{fresh_name}"')
            cur.execute(f'CREATE DATABASE "{fresh_name}" OWNER ubuntu')
    import urllib.parse
    parts = urllib.parse.urlsplit(dsn)
    fresh_dsn = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, "/" + fresh_name, parts.query, ""))
    try:
        from settlement import db
        db.apply_migrations(fresh_dsn, REPO / "migrations")
        fresh_roots = {"artifacts": tmp_path / "fart",
                       "staging": tmp_path / "fstaging"}
        fresh_roots["artifacts"].mkdir()
        fresh_roots["staging"].mkdir()
        falloc, fatt = _setup(fresh_dsn, "fresh")
        receipt = R.stage_composition(
            fresh_roots["staging"], core_bytes=CORE.encode(),
            adapter_bytes=ADAPTER.encode(), description=b"toy",
            dsn=fresh_dsn)
        R.publish_composition(fresh_dsn, _cmd({"n": uuid.uuid4().hex}),
                              fresh_roots["artifacts"], receipt)
        R.record_composition(fresh_dsn, _cmd({"n": uuid.uuid4().hex}),
                             fresh_roots["artifacts"], composition_id=comp,
                             package_digest=receipt["digest"], role="source")
        counting = CountingLauncher(str(tmp_path / "freshdb-runs"))
        result = R.run_task(
            fresh_dsn, counting, fresh_roots["artifacts"],
            **_params("run-resume3", comp, falloc, fatt))
        assert result["disposition"] == "improved"
        assert "rpr:run-resume3:t1:encode:0000" in counting.sends
        assert R.task_usage(dsn, "run-resume3", "t1")["invocations"] == 5
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{fresh_name}"')


def test_operator_view_pending_then_complete(migrated_db, tmp_roots,
                                             tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "opview")
    comp = _compose(dsn, tmp_roots, "comp-opview")
    run_dir = str(tmp_path / "runs")
    R.run_task(dsn, LocalLauncher(run_dir), tmp_roots["artifacts"],
               **_params("run-opview", comp, alloc, att, max_advances=1))
    pending = R.operator_view(dsn, "run-opview", "t1")
    assert pending["disposition"] == "pending"
    assert pending["next_action"] == "advance:2"
    assert pending["composition"]["composition_id"] == "comp-opview"
    assert pending["composition"]["core_digest"] != \
        pending["composition"]["adapter_digest"]
    assert pending["witness"]["domain_spec"]["family"] == "shrink-list"
    assert pending["budget"]["invocations_used"] == 5
    assert pending["budget"]["invocations_max"] == 64
    assert pending["budget"]["queries_used"] == 2
    assert pending["budget"]["queries_max"] == 16
    done = R.run_task(dsn, LocalLauncher(run_dir), tmp_roots["artifacts"],
                      **_params("run-opview", comp, alloc, att))
    assert done["disposition"] == "improved"
    view = R.operator_view(dsn, "run-opview", "t1")
    assert view["disposition"] == "complete"
    assert view["next_action"] == "done"
    assert view["witness"]["last_verdict"] == "preserved"
    assert view["result"]["best_measure"] == 1
    assert view["result"]["verified_candidate"] is True


def test_unsupported_scope_falls_back_to_incumbent(migrated_db, tmp_roots,
                                                   tmp_path):
    dsn = migrated_db
    alloc, att = _setup(dsn, "unsupported")
    comp = _compose(dsn, tmp_roots, "comp-unsupported")
    launcher = LocalLauncher(str(tmp_path / "runs"))
    result = R.run_task(
        dsn, launcher, tmp_roots["artifacts"],
        **_params("run-unsupported", comp, alloc, att,
                 domain_spec={"family": "other", "witness": "none"}))
    assert result["disposition"] == "unsupported"
    assert result["incumbent"] == {"items": [5, 1, 8, 3]}
    assert result["verified"] is False
    assert result["validation_used"] == 1
    view = R.operator_view(dsn, "run-unsupported", "t1")
    assert view["disposition"] == "unsupported"
