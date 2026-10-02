"""INV-D1: resume reclaims receipt-less dispatching validation ops (INV-C1).

Kill during validation dispatch leaves the validation operation in
`dispatching` with no receipt. Resume must reclaim and relaunch that
operation exactly once instead of scoring a validation failure and
spending a repair plus a fresh lineage. Ops that settled keep
exactly-once: anything with a receipt never relaunches.
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
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from settlement import broker, db, store
from settlement.broker import LaunchOutcome, ReceiptProposal
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher

RUN_TOKEN = "invd1%s" % uuid.uuid4().hex[:8]
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"
FUNDED = 100000
ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


def _create():
    from experiments.ad01.s09_run_isolation import create_disposable_db

    return create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)


def _drop(database):
    from experiments.ad01.s09_run_isolation import drop_disposable_db

    drop_disposable_db(database)


def _fresh_db(dsn, seq=0):
    from experiments.ad01 import trajectory as T
    from experiments.coord02 import experience as E
    assert "live" not in dsn
    db.apply_migrations(dsn, MIGRATIONS)
    E.designate_db(dsn, kind="disposable", purpose="inv-d1 dispatch")
    E.prepare_disposable_db(dsn, MIGRATIONS)
    T.authorize_campaign(dsn, T.campaign_id(0, "I", seq), authorized=FUNDED)


def test_the_dispatch_stores_are_named_for_this_run_not_for_the_file():
    """`inv_d1_unit` and `inv_d1_ctrl` name databases that outlive this
    process, so a later run collides on create and destroys the victim's rows
    on teardown. Every store here must carry the per-run token, and two of
    them must differ.
    """
    first = _create()
    try:
        second = _create()
        try:
            assert first.name.startswith("s09iso_"), first.name
            assert RUN_TOKEN in first.name, first.name
            assert "inv_d1_" not in first.name, first.name
            assert second.name != first.name
        finally:
            _drop(second)
    finally:
        _drop(first)


def _cmd(payload):
    import uuid
    return Command(request_id="req_%s" % uuid.uuid4().hex[:12],
                   payload=payload)


def _seed(dsn):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu",
                                     "authorized": 100000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1",
                                      "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1",
                                             "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _sandbox_op(dsn, op_id="op1", argv=None):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process",
                 "argv": argv or [sys.executable, "-c", "pass"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        allocation_id="a1", attempt_id="att1")


def _op_state(dsn, op_id):
    row = broker.read_operation(dsn, op_id)
    return row["dispatch_state"], len(store.operation_receipts(dsn, op_id))


def _develop(target):
    def propose(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % target,
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": target,
                                "max_queries": 4},
                "requested_resources": {"diagnostic_queries": 1}}
    return propose


class RecordingConstructorAdapter:
    label = "AD01-RECORDING-CONSTRUCTOR"

    def __init__(self, sources):
        from settlement.gateway import Usage
        self._sources = list(sources)
        self._usage = Usage(input_tokens=11, output_tokens=7)
        self.calls = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request.operation_id)
        source = self._sources[min(len(self.calls) - 1,
                                   len(self._sources) - 1)]
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source}),
                             {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


class ResultRecordingLauncher:
    launcher_id = "fake-result-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.sends = []
        self.results = {}
        self.live = set()

    def dispatch(self, op):
        self.sends.append(op.operation_id)
        receipt = ReceiptProposal(
            receipt_identity="fake:%s" % op.operation_id,
            content={"ok": True}, outcome="success",
            provenance=self.launcher_id)
        self.results[op.operation_id] = {"outcome": "success"}
        return LaunchOutcome(sent=True, receipt=receipt)

    def prior_send(self, operation_id):
        return operation_id in self.sends

    def stop(self, operation_id):
        self.live.discard(operation_id)
        return True

    def live_ids(self):
        return sorted(self.live)

    def is_live(self, operation_id):
        return operation_id in self.live

    def read_result(self, operation_id):
        return self.results.get(operation_id)


def _caps():
    return {"agenda_authorized": FUNDED, "max_boundaries": 1,
            "diagnostic_queries": 16}


def _run_control(dsn):
    from experiments.ad01 import trajectory as T
    _fresh_db(dsn)
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    campaign = T.run_campaign(
        0, "I", CHARTER, _caps(), tasks=[DEV_TASK],
        propose=_develop(DEV_TASK), dsn=dsn, campaign_seq=0,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    return campaign_summary(dsn, campaign, list(gw.calls))


def campaign_summary(dsn, campaign, gw_calls):
    from experiments.ad01 import trajectory as T
    with T._read_conn(dsn) as conn:
        ops = [dict(r) for r in conn.execute(
            "SELECT id, payload->>'effect' AS effect, dispatch_state"
            " FROM operations ORDER BY id").fetchall()]
        receipts = [dict(r) for r in conn.execute(
            "SELECT receipt_identity, operation_id, outcome FROM receipts"
            " ORDER BY receipt_identity").fetchall()]
    [episode] = campaign["episodes"]
    return {
        "campaign_id": campaign["campaign_id"],
        "model_calls": campaign["model_calls"],
        "construction_calls": campaign["construction_calls"],
        "dev_episodes": campaign["dev_episodes"],
        "disposition": episode.get("disposition"),
        "reason": episode.get("reason", ""),
        "gw_calls": list(gw_calls),
        "op_ids": sorted(o["id"] for o in ops),
        "op_states": sorted([o["id"], o["effect"], o["dispatch_state"]]
                            for o in ops),
        "receipt_ids": sorted(r["receipt_identity"] for r in receipts),
    }


def _runs_root():
    from experiments.ad01 import method_exec
    return Path(method_exec.__file__).resolve().parent.parent.parent / ".ad01-runs"


def _run_dirs_snapshot():
    root = _runs_root()
    if not root.is_dir():
        return set()
    return set(os.listdir(root))


def _clean_run_dirs(before):
    root = _runs_root()
    for name in set(os.listdir(root)) - before:
        shutil.rmtree(root / name, ignore_errors=True)


def _driver_victim(dsn, seq):
    from experiments.ad01 import trajectory as T
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    T.run_campaign(0, "I", CHARTER, _caps(), tasks=[DEV_TASK],
                   propose=_develop(DEV_TASK), dsn=dsn, campaign_seq=seq,
                   gateway=gw, model="ad01-campaign-double",
                   constructor="model")


def _driver_resume(dsn, cid, out):
    from experiments.ad01 import trajectory as T
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    campaign = T.resume_campaign(
        dsn, cid, CHARTER, _caps(), tasks=[DEV_TASK],
        propose=_develop(DEV_TASK), gateway=gw,
        model="ad01-campaign-double", constructor="model")
    Path(out).write_text(json.dumps(
        campaign_summary(dsn, campaign, list(gw.calls))))


def _launch(mode, *args):
    return subprocess.Popen(
        [sys.executable, __file__, mode, *map(str, args)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True)


def _query(dsn, sql, params=()):
    with db.connect(dsn) as conn:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return rows


def _kill_staged_victim(proc, dsn, poll_sql, poll_params, accept, deadline_s=300):
    conn = db.connect(dsn)
    try:
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read().decode()[-2000:]
                raise AssertionError("victim exited rc=%s: %s"
                                     % (proc.returncode, out))
            with conn.cursor() as cur:
                cur.execute(poll_sql, poll_params)
                rows = cur.fetchall()
            conn.commit()
            if rows and accept(rows):
                break
        else:
            raise AssertionError("victim never reached kill point")
    finally:
        conn.close()
    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    proc.wait()


def test_receiptless_dispatching_sandbox_relaunches_exactly_once(tmp_path):
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        gen = _seed(dsn)
        _sandbox_op(dsn)
        launcher = LocalLauncher(tmp_path / "runs")
        launchers = {"local-process": launcher}
        advanced = store.advance_dispatch(
            dsn, _cmd({"operation_id": "op1", "launcher_id": "local-1",
                       "provider_id": ""}))
        assert advanced.code == ResultCode.APPLIED
        assert _op_state(dsn, "op1") == ("dispatching", 0)
        assert launcher.prove_never_sent("op1") is True
        resumed = broker.dispatch_operation(
            dsn, "op1", launchers=launchers, ownership_generation=gen)
        assert resumed.sent_this_call is True
        assert _op_state(dsn, "op1") == ("observed", 1)
        assert (tmp_path / "runs" / "op1_exec-default.spawns").read_text().strip() == "1"
        again = broker.dispatch_operation(
            dsn, "op1", launchers=launchers, ownership_generation=gen)
        assert again.sent_this_call is False
        assert _op_state(dsn, "op1") == ("observed", 1)
        assert (tmp_path / "runs" / "op1_exec-default.spawns").read_text().strip() == "1"
    finally:
        _drop(database)


def test_dispatching_with_decided_receipt_never_relaunches(tmp_path):
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        gen = _seed(dsn)
        _sandbox_op(dsn)
        launcher = LocalLauncher(tmp_path / "runs")
        launchers = {"local-process": launcher}
        broker.dispatch_operation(dsn, "op1", launchers=launchers,
                                  ownership_generation=gen,
                                  _crash_after_send=True)
        admitted = broker.admit_launcher_receipt(dsn, "op1", ReceiptProposal(
            receipt_identity="fake:op1", content={"ok": True},
            outcome="success", provenance="fake-1"))
        assert admitted.code == ResultCode.APPLIED
        resumed = broker.dispatch_operation(
            dsn, "op1", launchers=launchers, ownership_generation=gen)
        assert resumed.sent_this_call is False
        assert _op_state(dsn, "op1") == ("observed", 1)
        assert (tmp_path / "runs" / "op1_exec-default.spawns").read_text().strip() == "1"
    finally:
        _drop(database)


def test_dispatching_with_launcher_result_parks_without_resend():
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        gen = _seed(dsn)
        _sandbox_op(dsn)
        fake = ResultRecordingLauncher()
        launchers = {"local-process": fake}
        crashed = broker.dispatch_operation(
            dsn, "op1", launchers=launchers, ownership_generation=gen,
            _crash_after_send=True)
        assert crashed.dispatch_state == "dispatching"
        assert _op_state(dsn, "op1") == ("dispatching", 0)
        assert fake.read_result("op1") is not None
        resumed = broker.dispatch_operation(
            dsn, "op1", launchers=launchers, ownership_generation=gen)
        assert resumed.sent_this_call is False
        assert fake.sends == ["op1"]
        assert _op_state(dsn, "op1") == ("dispatching", 0)
    finally:
        _drop(database)


def test_receiptless_dispatching_model_op_does_not_resend():
    from settlement.gateway import FakeGatewayAdapter
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        gen = _seed(dsn)
        broker.ensure_operation(
            dsn, operation_id="opm", effect=broker.MODEL_INFERENCE,
            payload={"model": "m", "messages": [{"role": "user",
                                                 "content": "hi"}],
                     "max_output_tokens": 8, "deadline_ms": 60_000},
            allocation_id="a1", attempt_id="att1")

        class CountingGateway(FakeGatewayAdapter):
            def __init__(self):
                super().__init__(text="answer")
                self.infers = []

            def infer(self, request):
                self.infers.append(request.operation_id)
                return super().infer(request)

        gateway = CountingGateway()
        crashed = broker.dispatch_operation(
            dsn, "opm", launchers={}, gateway=gateway,
            ownership_generation=gen, _crash_after_send=True)
        assert crashed.dispatch_state == "dispatching"
        assert _op_state(dsn, "opm") == ("dispatching", 0)
        resumed = broker.dispatch_operation(
            dsn, "opm", launchers={}, gateway=gateway,
            ownership_generation=gen)
        assert resumed.sent_this_call is False
        assert gateway.infers == ["opm"]
        assert _op_state(dsn, "opm") == ("dispatching", 0)
    finally:
        _drop(database)


def _compare_resumed(control, got, resume_gw_calls):
    assert got["disposition"] == "retained", got
    for key in ("model_calls", "construction_calls", "dev_episodes",
                "op_ids", "op_states", "receipt_ids"):
        assert got[key] == control[key], (key, got[key], control[key])
    assert not [op for op in got["op_ids"] if "-repair" in op], got["op_ids"]
    assert resume_gw_calls == [], resume_gw_calls


def test_kill_during_validation_resumes_identical_to_control(tmp_path):
    ctrl = _create()
    created = [ctrl]
    before_dirs = _run_dirs_snapshot()
    try:
        control = _run_control(ctrl.dsn)
        assert control["disposition"] == "retained", control
        assert control["model_calls"] == 1, control
        staged = None
        for _attempt in range(5):
            attempt_store = _create()
            created.append(attempt_store)
            dsn = attempt_store.dsn
            _fresh_db(dsn)
            attempt_files = set(glob.glob(str(_runs_root() / '*' / 'launcher' / '*')))
            victim = _launch("victim", dsn, 0)
            try:
                _kill_staged_victim(
                    victim, dsn,
                    "SELECT id FROM operations WHERE id LIKE '%%-validate-%%'"
                    " AND dispatch_state = 'dispatching'", (),
                    lambda rows: len(rows) == 1)
            except AssertionError:
                if victim.poll() is None:
                    victim.kill()
                continue
            op_id = _query(
                dsn, "SELECT id FROM operations WHERE id LIKE '%%-validate-%%'")[0][0]
            state, receipts = _op_state(dsn, op_id)
            new_files = set(glob.glob(
                str(_runs_root() / "*" / "launcher") + "/*%s*" % op_id)) - attempt_files
            if state == "dispatching" and receipts == 0 and not new_files:
                staged = (dsn, op_id)
                break
        assert staged is not None, "no clean pre-spawn kill staged"
        dsn, op_id = staged
        from experiments.ad01 import trajectory as T
        out = str(tmp_path / "resumed.json")
        resumed_proc = _launch("resume", dsn, T.campaign_id(0, "I", 0), out)
        rc = resumed_proc.wait(timeout=300)
        assert rc == 0, resumed_proc.stdout.read().decode()[-3000:]
        got = json.loads(Path(out).read_text())
        _compare_resumed(control, got, got["gw_calls"])
    finally:
        for database in created:
            _drop(database)
        _clean_run_dirs(before_dirs)


def test_kill_after_validation_receipt_resumes_with_zero_new_calls(tmp_path):
    ctrl = _create()
    created = [ctrl]
    before_dirs = _run_dirs_snapshot()
    try:
        control = _run_control(ctrl.dsn)
        assert control["disposition"] == "retained", control
        staged = None
        for _attempt in range(5):
            attempt_store = _create()
            created.append(attempt_store)
            dsn = attempt_store.dsn
            _fresh_db(dsn)
            victim = _launch("victim", dsn, 0)
            try:
                _kill_staged_victim(
                    victim, dsn,
                    "SELECT operation_id FROM receipts WHERE operation_id"
                    " LIKE '%%-validate-%%' AND outcome = 'success'", (),
                    lambda rows: len(rows) == 1)
            except AssertionError:
                if victim.poll() is None:
                    victim.kill()
                continue
            from experiments.ad01 import trajectory as T
            settled, _ = T._read_campaign(dsn, T.campaign_id(0, "I", 0))
            if settled:
                continue
            staged = dsn
            break
        assert staged is not None, "no pre-publish post-receipt kill staged"
        dsn = staged
        from experiments.ad01 import trajectory as T
        out = str(tmp_path / "resumed.json")
        resumed_proc = _launch("resume", dsn, T.campaign_id(0, "I", 0), out)
        rc = resumed_proc.wait(timeout=300)
        assert rc == 0, resumed_proc.stdout.read().decode()[-3000:]
        got = json.loads(Path(out).read_text())
        _compare_resumed(control, got, got["gw_calls"])
    finally:
        for database in created:
            _drop(database)
        _clean_run_dirs(before_dirs)


def _main(argv):
    mode = argv[1]
    if mode == "victim":
        _driver_victim(argv[2], int(argv[3]))
    elif mode == "resume":
        _driver_resume(argv[2], argv[3], argv[4])
    else:
        raise SystemExit("unknown mode %r" % mode)


if __name__ == "__main__":
    _main(sys.argv)
