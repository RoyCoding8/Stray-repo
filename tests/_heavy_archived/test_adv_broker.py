from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from settlement import broker, store
from settlement.broker import BrokerOp, LaunchOutcome, ReceiptProposal
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher

REPO = Path(__file__).parents[2]


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"advb_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn, tag, authorized=10_000):
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "advb",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "advb"}, f"{tag}i"))
    gen = store.acquire_work(
        dsn, _cmd({"attempt_id": f"{tag}-att",
                   "investigation_id": f"{tag}-i"}, f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", gen


def _sandbox(tag, alloc, argv=None, attempt=None):
    return broker.ensure_operation(
        tag[0], operation_id=tag[1], effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": argv or ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt)


class FlakyLauncher:
    launcher_id = "flaky-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self, run_dir: Path):
        self.inner = LocalLauncher(run_dir)
        self.fail_first = True
        self.sends = 0

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        self.sends += 1
        if self.fail_first:
            self.fail_first = False
            raise RuntimeError("broker died before send")
        return self.inner.dispatch(op)

    def prior_send(self, operation_id: str) -> bool:
        return self.inner.prior_send(operation_id)

    def stop(self, operation_id: str) -> bool:
        return self.inner.stop(operation_id)

    def live_ids(self):
        return self.inner.live_ids()

    def is_live(self, operation_id: str) -> bool:
        return self.inner.is_live(operation_id)

    def read_result(self, operation_id: str):
        return self.inner.read_result(operation_id)


class LostLauncher(FlakyLauncher):
    launcher_id = "lost-1"

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        self.sends += 1
        return LaunchOutcome(sent=True, lost=True)


def test_death_before_advance_redispatches_exactly_once(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k1")
    _sandbox((dsn, "k1-op"), alloc, attempt="k1-att")
    assert broker.read_operation(dsn, "k1-op")["dispatch_state"] == "prepared"
    launcher = LocalLauncher(tmp_path / "runs")
    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)
    assert report.dispatched == ["k1-op"]
    assert broker.read_operation(dsn, "k1-op")["dispatch_state"] == "observed"
    assert (tmp_path / "runs" / "k1-op_exec-default.spawns").read_text().strip() == "1"


def test_death_after_advance_before_send_parks_unresolved(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k1b")
    _sandbox((dsn, "k1b-op"), alloc, attempt="k1b-att")
    launcher = FlakyLauncher(tmp_path / "runs")
    died = broker.dispatch_operation(dsn, "k1b-op",
                                     launchers={"local-process": launcher},
                                     ownership_generation=gen)
    assert died.sent_this_call is False
    assert broker.read_operation(dsn, "k1b-op")["dispatch_state"] == "dispatching"
    assert not list((tmp_path / "runs").glob("k1b-op_*"))
    decision = broker.reconcile(dsn, "k1b-op", {"local-process": launcher})
    assert decision.decision == "unresolved-liability"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0


def test_death_after_send_never_resends(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k2")
    _sandbox((dsn, "k2-op"), alloc, attempt="k2-att")
    launcher = LocalLauncher(tmp_path / "runs")
    crashed = broker.dispatch_operation(dsn, "k2-op",
                                        launchers={"local-process": launcher},
                                        ownership_generation=gen,
                                        _crash_after_send=True)
    assert crashed.dispatch_state == "dispatching" and crashed.sent_this_call is True
    spawns = (tmp_path / "runs" / "k2-op_exec-default.spawns").read_text().strip()
    assert spawns == "1"
    assert store.scan_outbox(dsn) != []
    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)
    assert "k2-op" in report.repaired
    assert broker.read_operation(dsn, "k2-op")["dispatch_state"] == "observed"
    assert store.scan_outbox(dsn) == []
    assert (tmp_path / "runs" / "k2-op_exec-default.spawns").read_text().strip() == "1"


def test_duplicate_receipt_after_commit_settles_once(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k3")
    _sandbox((dsn, "k3-op"), alloc, attempt="k3-att")
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, "k3-op", launchers={"local-process": launcher},
                              ownership_generation=gen)
    before = store.allocation_status(dsn, alloc)
    first = broker.admit_launcher_receipt(dsn, "k3-op", ReceiptProposal(
        receipt_identity="k3-replay", content={"replay": 1},
        outcome="success", provenance="local-1"))
    assert first.code == ResultCode.APPLIED
    conflict = broker.admit_launcher_receipt(dsn, "k3-op", ReceiptProposal(
        receipt_identity="k3-replay", content={"replay": 2},
        outcome="success", provenance="local-1"))
    assert conflict.code == ResultCode.APPLIED
    assert conflict.data.get("conflict") is True
    row = broker.read_operation(dsn, "k3-op")
    assert row["reconcile_state"] == "conflict"
    after = store.allocation_status(dsn, alloc)
    assert (after["consumed"], after["reserved"]) == (before["consumed"], before["reserved"])


def test_lost_response_retains_exposure_and_never_resends(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k4")
    _sandbox((dsn, "k4-op"), alloc, attempt="k4-att")
    launcher = LostLauncher(tmp_path / "runs")
    status = broker.dispatch_operation(dsn, "k4-op",
                                       launchers={"local-process": launcher},
                                       ownership_generation=gen)
    assert status.sent_this_call is True
    row = broker.read_operation(dsn, "k4-op")
    assert row["dispatch_state"] == "unresolved"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0
    repeat = broker.dispatch_operation(dsn, "k4-op",
                                       launchers={"local-process": launcher},
                                       ownership_generation=gen)
    assert repeat.sent_this_call is False
    assert launcher.sends == 1
    decision = broker.reconcile(dsn, "k4-op", {"local-process": launcher})
    assert decision.decision == "unresolved-liability"


def test_stale_worker_completion_refused_observation_open(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k5")
    _sandbox((dsn, "k5-op"), alloc, attempt="k5-att")
    launcher = LocalLauncher(tmp_path / "runs")
    refused = broker.dispatch_operation(dsn, "k5-op",
                                        launchers={"local-process": launcher},
                                        ownership_generation=int(gen) + 99)
    assert refused.next_decision == "stale-ownership"
    assert not list((tmp_path / "runs").glob("k5-op_*"))
    bad_complete = store.complete_attempt(
        dsn, _cmd({"attempt_id": "k5-att", "ownership_generation": int(gen) + 99,
                   "outcome": "completed"}, "k5bad"))
    assert bad_complete.code == ResultCode.STALE_REVISION
    obs = store.submit_observation(dsn, _cmd({"attempt_id": "k5-att",
                                              "content": {"note": "at stale gen"}}, "k5obs"))
    assert obs.code == ResultCode.APPLIED


def test_cancel_while_dispatched_keeps_charges_late_receipt_admitted(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k6")
    _sandbox((dsn, "k6-op"), alloc, attempt="k6-att")
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, "k6-op", launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    broker.request_cancel(dsn, "k6-op", {"local-process": launcher})
    broker.note_worker_stopped(dsn, "k6-op")
    broker.confirm_cancel(dsn, "k6-op")
    late = broker.admit_launcher_receipt(dsn, "k6-op", ReceiptProposal(
        receipt_identity="late:k6-op", content={"containment": False},
        outcome="success", provenance="local-1"))
    assert late.code == ResultCode.APPLIED
    row = broker.read_operation(dsn, "k6-op")
    assert row["cancel_state"] == "confirmed" and row["dispatch_state"] == "observed"


DRIVER_LINES = [
    "import sys",
    "sys.path.insert(0, __SRC__)",
    "from settlement import broker, store",
    "from settlement.common import Command",
    "from settlement.launcher_local import LocalLauncher",
    "dsn, run_dir, mode, tag = sys.argv[1:5]",
    "if mode == 'prepare':",
    "    store.seed_grant(dsn, Command(request_id=tag + '-g', payload={",
    "        'version': 1, 'charter_text': 'drv', 'authority_grant': {}, 'envelopes': {}}))",
    "    store.seed_allocation(dsn, Command(request_id=tag + '-a', payload={",
    "        'allocation_id': tag + '-a', 'domain': 'cpu', 'authorized': 100000}))",
    "    store.admit_commitment(dsn, Command(request_id=tag + '-i', payload={",
    "        'investigation_id': tag + '-i', 'objective': 'drv'}))",
    "    store.acquire_work(dsn, Command(request_id=tag + '-q', payload={",
    "        'attempt_id': tag + '-att', 'investigation_id': tag + '-i'}))",
    "    broker.ensure_operation(dsn, operation_id=tag + '-op', effect=broker.SANDBOX_EXEC,",
    "        payload={'profile': 'local-process', 'argv': ['/bin/true'],",
    "                 'timeout_ms': 30000, 'max_output_bytes': 1024},",
    "        allocation_id=tag + '-a', attempt_id=tag + '-att')",
    "elif mode == 'dispatch-crash':",
    "    launcher = LocalLauncher(run_dir)",
    "    broker.dispatch_operation(dsn, tag + '-op',",
    "        launchers={'local-process': launcher}, _crash_after_send=True)",
]


def _write_driver() -> Path:
    path = Path("/tmp") / f"adv_broker_driver_{uuid.uuid4().hex[:8]}.py"
    body = "\n".join(DRIVER_LINES).replace("__SRC__", repr(str(REPO / "src")))
    path.write_text(body + "\n")
    return path


def _run_driver(dsn: str, run_dir: Path, mode: str, tag: str) -> None:
    driver = _write_driver()
    try:
        proc = subprocess.run(
            [sys.executable, str(driver), dsn, str(run_dir), mode, tag],
            capture_output=True, text=True, timeout=120)
    finally:
        driver.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr


def test_kill_restart_before_advance_dispatches_once(migrated_db, tmp_path):
    dsn = migrated_db
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    _run_driver(dsn, run_dir, "prepare", "drv1")
    assert broker.read_operation(dsn, "drv1-op")["dispatch_state"] == "prepared"
    launcher = LocalLauncher(run_dir)
    status = broker.dispatch_operation(dsn, "drv1-op",
                                       launchers={"local-process": launcher})
    assert status.dispatch_state == "observed" and status.sent_this_call is True
    assert (run_dir / "drv1-op_exec-default.spawns").read_text().strip() == "1"


def test_kill_restart_after_send_reconciles_without_resend(migrated_db, tmp_path):
    dsn = migrated_db
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    _run_driver(dsn, run_dir, "prepare", "drv2")
    _run_driver(dsn, run_dir, "dispatch-crash", "drv2")
    assert broker.read_operation(dsn, "drv2-op")["dispatch_state"] == "dispatching"
    launcher = LocalLauncher(run_dir)
    status = broker.dispatch_operation(dsn, "drv2-op",
                                       launchers={"local-process": launcher})
    assert status.sent_this_call is False
    assert status.dispatch_state == "dispatching"
    decision = broker.reconcile(dsn, "drv2-op", {"local-process": launcher})
    assert decision.decision == "receipt-admitted"
    assert broker.read_operation(dsn, "drv2-op")["dispatch_state"] == "observed"
    assert (run_dir / "drv2-op_exec-default.spawns").read_text().strip() == "1"


def test_unresolved_without_decision_retries_exactly_once(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k7")
    _sandbox((dsn, "k7-op"), alloc, attempt="k7-att")
    store.advance_dispatch(dsn, _cmd({"operation_id": "k7-op", "launcher_id": "local-1",
                                      "provider_id": ""}, "k7adv"))
    assert broker.reconcile(dsn, "k7-op", {}).decision == "unresolved-liability"
    assert broker.read_operation(dsn, "k7-op")["dispatch_state"] == "unresolved"
    launcher = LocalLauncher(tmp_path / "runs")
    generation = int(broker.read_operation(dsn, "k7-op")["payload"]["_dispatch_generation"])
    status = broker.redispatch_after_reset(dsn, "k7-op", {"local-process": launcher},
                                           ownership_generation=gen,
                                           expected_generation=generation)
    assert status.sent_this_call is True
    assert broker.read_operation(dsn, "k7-op")["dispatch_state"] == "observed"
    assert (tmp_path / "runs" / "k7-op_exec-default.spawns").read_text().strip() == "1"
    refused = broker.redispatch_after_reset(dsn, "k7-op", {"local-process": launcher},
                                            ownership_generation=gen,
                                            expected_generation=generation + 1)
    assert refused.sent_this_call is False
    assert (tmp_path / "runs" / "k7-op_exec-default.spawns").read_text().strip() == "1"


def test_unresolved_retries_refused_when_no_launcher_can_attest(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k7x")
    _sandbox((dsn, "k7x-op"), alloc, attempt="k7x-att")
    store.advance_dispatch(dsn, _cmd({"operation_id": "k7x-op", "launcher_id": "gone",
                                      "provider_id": ""}, "k7xadv"))
    assert broker.reconcile(dsn, "k7x-op", {}).decision == "unresolved-liability"
    launcher = LocalLauncher(tmp_path / "runs")
    generation = int(broker.read_operation(dsn, "k7x-op")["payload"]["_dispatch_generation"])
    status = broker.redispatch_after_reset(dsn, "k7x-op", {"local-process": launcher},
                                           ownership_generation=gen,
                                           expected_generation=generation)
    assert status.next_decision == "refused-never-sent-proof"
    assert status.sent_this_call is False
    assert list((tmp_path / "runs").glob("*.spawns")) == []
    assert broker.read_operation(dsn, "k7x-op")["dispatch_state"] == "unresolved"
    assert int(broker.read_operation(dsn, "k7x-op")["payload"]["_dispatch_generation"]) == generation


def test_unresolved_unknown_receipt_blocks_retry_and_keeps_provenance(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k8")
    _sandbox((dsn, "k8-op"), alloc, attempt="k8-att")
    store.advance_dispatch(dsn, _cmd({"operation_id": "k8-op", "launcher_id": "local-1",
                                      "provider_id": ""}, "k8adv"))
    lost = broker.admit_launcher_receipt(dsn, "k8-op", ReceiptProposal(
        receipt_identity="lost:k8-op", content={"lost": True},
        outcome="unknown", provenance="broker"))
    assert lost.code == ResultCode.APPLIED
    assert broker.read_operation(dsn, "k8-op")["dispatch_state"] == "unresolved"
    launcher = LocalLauncher(tmp_path / "runs")
    generation = int(broker.read_operation(dsn, "k8-op")["payload"]["_dispatch_generation"])
    status = broker.redispatch_after_reset(dsn, "k8-op", {"local-process": launcher},
                                           ownership_generation=gen,
                                           expected_generation=generation)
    assert status.next_decision == "reset-refused-invalid_input"
    assert status.sent_this_call is False
    assert list((tmp_path / "runs").glob("*.spawns")) == []
    assert broker.read_operation(dsn, "k8-op")["dispatch_state"] == "unresolved"
    assert int(broker.read_operation(dsn, "k8-op")["payload"]["_dispatch_generation"]) == generation
    receipts = {r["receipt_identity"] for r in store.operation_receipts(dsn, "k8-op")}
    assert receipts == {"lost:k8-op"}, \
        "an operation carrying a receipt must be reconciled, never reset"


def test_receipt_on_never_dispatched_operation_refused(migrated_db):
    dsn = migrated_db
    alloc, _ = _env(dsn, "k9")
    _sandbox((dsn, "k9-op"), alloc, attempt="k9-att")
    before = store.allocation_status(dsn, alloc)
    refused = broker.admit_launcher_receipt(dsn, "k9-op", ReceiptProposal(
        receipt_identity="forged:k9-op", content={"text": "never ran"},
        outcome="success", provenance="anyone"))
    assert refused.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(dsn, "k9-op")["dispatch_state"] == "prepared"
    assert store.operation_receipts(dsn, "k9-op") == []
    after = store.allocation_status(dsn, alloc)
    assert (after["consumed"], after["reserved"]) == (before["consumed"], before["reserved"])


def test_workflow_ensure_conflict_never_dispatches_stale_bytes(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "k10")
    assert broker.ensure_operation(
        dsn, operation_id="k10-att:n1", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": [sys.executable, "-c", "pass"],
                 "timeout_ms": 5000, "max_output_bytes": 1024},
        allocation_id=alloc, attempt_id="k10-att").code == ResultCode.APPLIED
    run_dir = tmp_path / "runs"
    broker.ATTEMPT_WORKFLOW_RESOURCES["k10-att"] = {
        "launchers": {"local-process": LocalLauncher(run_dir)}, "gateway": None}
    try:
        summary = broker.wf_ensure_dispatch(
            dsn, {"operation_id": "k10-att:n1", "effect": broker.SANDBOX_EXEC,
                  "payload": {"profile": "local-process", "argv": ["/bin/false"],
                              "timeout_ms": 5000, "max_output_bytes": 1024},
                  "allocation_id": alloc, "attempt_id": "k10-att",
                  "execution_version": ""},
            0, gen, "n1", "k10-att")
    finally:
        broker.ATTEMPT_WORKFLOW_RESOURCES.pop("k10-att", None)
    assert summary["next_decision"] == "ensure-refused-invalid_input"
    assert summary["failed_try"] is False
    assert list(run_dir.glob("*")) == []
    stored = broker.read_operation(dsn, "k10-att:n1")
    assert stored["dispatch_state"] == "prepared"
    assert stored["payload"]["payload"]["argv"] == ["/bin/true"]


def test_prove_never_sent_sees_result_and_supervise_files(tmp_path):
    launcher = LocalLauncher(tmp_path / "runs")
    assert launcher.prove_never_sent("zv-op") is True
    (tmp_path / "runs" / "zv-op_exec-default.result.json").write_text("{}")
    assert launcher.prove_never_sent("zv-op") is False
    (tmp_path / "runs" / "zv-op_exec-default.result.json").unlink()
    (tmp_path / "runs" / "zv-op_exec-default.supervise.json").write_text("{}")
    assert launcher.prove_never_sent("zv-op") is False
