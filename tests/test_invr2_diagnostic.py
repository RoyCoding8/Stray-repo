"""INV-R2 S2: a diagnostic completed before a crash is never redone.

The public trajectory persists diagnostic completion, observation and
consumed queries before construction through authority phase state. Resume
in a fresh process reuses the saved result instead of rerunning the
diagnostic: zero duplicate queries, unchanged observation, no renewed
allowance. Real Postgres in databases named inv_r2_*; doubles sit at the
provider seam only.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from settlement import db  # noqa: E402

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 60,
        "construction_tokens": 512, "agenda_authorized": 100000}
FUNDED = 100000
MODEL = "inv-r2-double"
SW0 = "ad01-w0-dev-sw-00"
ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
MAINT = "dbname=postgres host=/var/run/postgresql user=ubuntu"


def _dsn(name):
    return "dbname=%s host=/var/run/postgresql user=ubuntu" % name


def _create(name):
    conn = db.connect(MAINT)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute('CREATE DATABASE "%s"' % name)
    conn.close()


def _drop(name):
    conn = db.connect(MAINT)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
        cur.execute('DROP DATABASE IF EXISTS "%s"' % name)
    conn.close()


def _fresh_db(dsn, seq):
    from experiments.ad01 import trajectory as T
    from experiments.coord02 import experience as E
    assert "live" not in dsn
    db.apply_migrations(dsn, ROOT / "migrations")
    E.designate_db(dsn, kind="disposable", purpose="inv-r2 diagnostic")
    E.prepare_disposable_db(dsn, ROOT / "migrations")
    T.authorize_campaign(dsn, T.campaign_id(0, "I", seq), authorized=FUNDED)


def _develop_text():
    return json.dumps({
        "basis_references": ["obs-%s-seed" % SW0],
        "question": "develop %s" % SW0,
        "next_action": {"kind": "development", "diagnostic": "software",
                        "task_id": SW0, "max_queries": 4},
        "requested_resources": {"diagnostic_queries": 1}}, sort_keys=True)


def _runs_root():
    from experiments.ad01 import method_exec
    return Path(method_exec.__file__).resolve().parent.parent.parent \
        / ".ad01-runs"


def _run_dirs_snapshot():
    root = _runs_root()
    if not root.is_dir():
        return set()
    return set(os.listdir(root))


def _clean_run_dirs(before):
    root = _runs_root()
    if not root.is_dir():
        return
    for name in set(os.listdir(root)) - before:
        shutil.rmtree(root / name, ignore_errors=True)


class _SplitGateway:
    label = "INV-R2-SPLIT"

    def __init__(self, learner_texts, sources, stall_construction=False):
        self._learner = list(learner_texts)
        self._sources = list(sources)
        self._stall = stall_construction
        self._used = {"learner": 0, "construction": 0}
        self.calls = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        self.calls.append(request.operation_id)
        stream = ("learner" if "-learner-" in request.operation_id
                  else "construction")
        position = self._used[stream]
        self._used[stream] += 1
        if stream == "construction" and self._stall and position == 0:
            time.sleep(600)
        if stream == "learner":
            text = self._learner[min(position, len(self._learner) - 1)]
            usage = Usage(input_tokens=5, output_tokens=5)
        else:
            source = self._sources[min(position, len(self._sources) - 1)]
            text = json.dumps({"entry": source})
            usage = Usage(input_tokens=11, output_tokens=7)
        return ModelResponse(request.operation_id, text, {}, usage, "stop")

    def cancel(self, operation_id):
        return False


def _propose_kwargs(dsn, cid, gateway):
    from experiments.ad01 import trajectory as T
    from experiments.ad01.learner import propose_from_model
    seed = T.ensure_campaign(dsn, cid, 0, "I", dict(CHARTER), dict(CAPS),
                             tasks=[SW0])
    propose = propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL, charter=dict(CHARTER),
        world=0, arm="I", allocation_id=seed["allocation_id"])
    return propose


def _summarize(dsn, campaign, gateway):
    from experiments.ad01 import trajectory as T
    with T._read_conn(dsn) as conn:
        receipts = [dict(r) for r in conn.execute(
            "SELECT operation_id, outcome FROM receipts"
            " ORDER BY receipt_identity").fetchall()]
    [episode] = campaign["episodes"]
    [boundary] = campaign["boundaries"]
    return {
        "queries": campaign["queries"],
        "model_calls": campaign["model_calls"],
        "construction_calls": campaign["construction_calls"],
        "dev_episodes": campaign["dev_episodes"],
        "disposition": episode.get("disposition"),
        "observation_id": boundary["observation_id"],
        "spend": boundary["spend"],
        "learner_calls": [op for op in gateway.calls
                          if "-learner-" in op],
        "receipts": sorted((r["operation_id"], r["outcome"])
                           for r in receipts),
    }


def _launch(mode, *args):
    return subprocess.Popen(
        [sys.executable, __file__, mode, *map(str, args)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True)


def _phase_detail(dsn, study_root, decision_id):
    from experiments.ad01 import trajectory as T
    with T._read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT detail FROM study_phases"
            " WHERE study_root = %s AND decision_id = %s"
            " AND phase = 'diagnostic'",
            (study_root, decision_id)).fetchone()
    return dict(row["detail"] or {})


def _wait_diagnostic_phase(dsn, study_root, decision_id, deadline_s=300):
    from settlement import authority as _authority
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        status = _authority.phase_status(dsn, study_root, decision_id)
        if status.get("diagnostic") is not None:
            return status
        time.sleep(0.5)
    raise AssertionError("victim never persisted its diagnostic checkpoint")


def test_kill_after_diagnostic_reuses_checkpoint_without_redo(tmp_path):
    from experiments.ad01 import trajectory as T
    before_dirs = _run_dirs_snapshot()
    _create("inv_r2_diag_ctrl")
    _create("inv_r2_diag")
    try:
        ctrl_dsn = _dsn("inv_r2_diag_ctrl")
        _fresh_db(ctrl_dsn, 60)
        ctrl_gw = _SplitGateway([_develop_text()], [ACQUIRED_SOURCE])
        ctrl_propose = _propose_kwargs(
            ctrl_dsn, T.campaign_id(0, "I", 60), ctrl_gw)
        control = T.run_campaign(
            0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0], campaign_seq=60,
            dsn=ctrl_dsn, propose=ctrl_propose, gateway=ctrl_gw,
            model=MODEL, constructor="model")
        expected = _summarize(ctrl_dsn, control, ctrl_gw)
        assert expected["disposition"] == "retained", expected

        dsn = _dsn("inv_r2_diag")
        seq = 61
        cid = T.campaign_id(0, "I", seq)
        _fresh_db(dsn, seq)
        victim = _launch("victim_diag", dsn, str(seq))
        try:
            saved = _wait_diagnostic_phase(dsn, cid, "att-%s-0" % cid)
        except BaseException:
            if victim.poll() is None:
                victim.kill()
            raise
        assert saved["diagnostic"]["operation_id"].startswith(
            "ad01-%s-learner-0" % cid)
        os.killpg(os.getpgid(victim.pid), signal.SIGKILL)
        victim.wait()
        settled, pending = T._read_campaign(dsn, cid)
        assert settled == {}
        assert list(pending) == [0]
        detail = _phase_detail(dsn, cid, "att-%s-0" % cid)
        assert detail["observation"]["observation_id"] == \
            expected["observation_id"]
        out = str(tmp_path / "resumed.json")
        resumed = _launch("resume_diag", dsn, cid, out)
        rc = resumed.wait(timeout=300)
        assert rc == 0, resumed.stdout.read().decode()[-3000:]
        got = json.loads(Path(out).read_text())
        assert got["diag_calls"] == 0
        assert got["learner_calls"] == []
        assert got["disposition"] == "retained"
        assert got["observation_id"] == expected["observation_id"]
        assert got["queries"] == expected["queries"]
        assert got["model_calls"] == expected["model_calls"]
        assert got["construction_calls"] == expected["construction_calls"]
        assert got["spend"] == expected["spend"]
        construct_receipts = [r for r in got["receipts"]
                              if "-construct-" in r[0]]
        assert construct_receipts, got["receipts"]
        assert len(construct_receipts) == len(set(r[0] for r in
                                                 construct_receipts))
        after = T._read_campaign(dsn, cid)
        assert len(after[0]) == 1
        reread = _wait_diagnostic_phase(dsn, cid, "att-%s-0" % cid,
                                        deadline_s=10)
        assert reread["diagnostic"]["operation_id"] == \
            saved["diagnostic"]["operation_id"]
    finally:
        _drop("inv_r2_diag_ctrl")
        _drop("inv_r2_diag")
        _clean_run_dirs(before_dirs)


def _driver_victim_diag(dsn, seq):
    from experiments.ad01 import construct as C
    from experiments.ad01 import trajectory as T
    cid = T.campaign_id(0, "I", int(seq))
    gateway = _SplitGateway([_develop_text()], [ACQUIRED_SOURCE])
    propose = _propose_kwargs(dsn, cid, gateway)
    orig = C.construct_method

    def stalled(*args, **kwargs):
        time.sleep(600)
        return orig(*args, **kwargs)

    C.construct_method = stalled
    try:
        T.run_campaign(0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
                       campaign_seq=int(seq), dsn=dsn, propose=propose,
                       gateway=gateway, model=MODEL, constructor="model")
    finally:
        C.construct_method = orig


def _driver_resume_diag(dsn, cid, out):
    from experiments.ad01 import trajectory as T
    calls = []
    orig = T.run_diagnostic

    def counting(*args, **kwargs):
        calls.append(1)
        return orig(*args, **kwargs)

    T.run_diagnostic = counting
    try:
        gateway = _SplitGateway([_develop_text()], [ACQUIRED_SOURCE])
        propose = _propose_kwargs(dsn, cid, gateway)
        campaign = T.resume_campaign(
            dsn, cid, dict(CHARTER), dict(CAPS), tasks=[SW0],
            propose=propose, gateway=gateway, model=MODEL,
            constructor="model")
    finally:
        T.run_diagnostic = orig
    summary = _summarize(dsn, campaign, gateway)
    summary["diag_calls"] = len(calls)
    Path(out).write_text(json.dumps(summary))


def _main(argv):
    mode = argv[1]
    if mode == "victim_diag":
        _driver_victim_diag(argv[2], argv[3])
    elif mode == "resume_diag":
        _driver_resume_diag(argv[2], argv[3], argv[4])
    else:
        raise SystemExit("unknown mode %r" % mode)


if __name__ == "__main__":
    _main(sys.argv)
