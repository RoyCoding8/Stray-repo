from __future__ import annotations

import sys

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from settlement import broker, capabilities, db, store
from settlement.broker import ATTEMPT_WORKFLOW_RESOURCES, LaunchOutcome, ReceiptProposal
from settlement.common import Command, CommandResult, ResultCode
from settlement.gateway import FakeGatewayAdapter


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"r01_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup(dsn, tag="r01"):
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 100000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i", "objective": "r01"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                             "investigation_id": f"{tag}-i"}))
    return f"{tag}-a", f"{tag}-att", acquired.data["ownership_generation"]


def _model(op, alloc, attempt):
    return {"operation_id": op, "effect": broker.MODEL_INFERENCE,
            "payload": {"model": "fake", "messages": [{"role": "user", "content": "hi"}],
                        "max_output_tokens": 16, "deadline_ms": 10000},
            "allocation_id": alloc, "attempt_id": attempt}


def _sandbox(op, alloc, attempt):
    return {"operation_id": op, "effect": broker.SANDBOX_EXEC,
            "payload": {"profile": "local-process", "argv": [sys.executable, "-c", "pass"],
                        "timeout_ms": 10000, "max_output_bytes": 1024},
            "allocation_id": alloc, "attempt_id": attempt}


class CountingGateway(FakeGatewayAdapter):
    def __init__(self):
        super().__init__()
        self.calls: list[str] = []
        self._lock = Lock()

    def infer(self, request):
        with self._lock:
            self.calls.append(request.operation_id)
        return super().infer(request)


class FailGateway:
    def infer(self, request):
        raise AssertionError(f"no provider send allowed for {request.operation_id}")


class CountingLauncher:
    launcher_id = "count-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.sends: list[str] = []
        self._sent: set[str] = set()
        self._lock = Lock()

    def dispatch(self, op) -> LaunchOutcome:
        with self._lock:
            self.sends.append(op.operation_id)
            self._sent.add(op.operation_id)
        return LaunchOutcome(sent=True, receipt=ReceiptProposal(
            receipt_identity=f"count:{op.operation_id}", content={"ok": True},
            outcome="success", provenance=self.launcher_id))

    def prior_send(self, operation_id: str) -> bool:
        return operation_id in self._sent

    def stop(self, operation_id: str) -> bool:
        return False

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str):
        return None


def _launchers(launcher):
    return {"local-process": launcher}


def test_r01_001_replayed_advance_sends_zero_gateway(migrated_db, monkeypatch):
    dsn = migrated_db
    alloc, attempt, _ = _setup(dsn)
    args = _model("r01a-op", alloc, attempt)
    assert broker.ensure_operation(dsn, **args).code == ResultCode.APPLIED
    barrier, lock, codes, arrivals = Barrier(2), Lock(), [], []
    row = {"dispatch_state": "prepared", "attempt_id": attempt, "execution_version": "v1",
           "reconcile_state": "none", "cancel_state": "none", "settled": False,
           "payload": {"effect": broker.MODEL_INFERENCE, "payload": args["payload"]}}

    def read(dsn_, operation_id):
        with lock:
            arrivals.append(1)
            rendezvous = len(arrivals) <= 2
        if rendezvous:
            barrier.wait(timeout=30)
        return row

    def advance(*a):
        with lock:
            code = ResultCode.APPLIED if not codes else ResultCode.ALREADY_APPLIED
            codes.append(code.value)
        return CommandResult(code=code, request_id="same-request")

    gateway = CountingGateway()
    monkeypatch.setattr(broker, "read_operation", read)
    monkeypatch.setattr(broker, "_advance", advance)
    monkeypatch.setattr(broker, "_finish_send",
                        lambda dsn_, op_, outcome, generation=None: broker.DispatchStatus(
                            operation_id=op_, dispatch_state="observed",
                            sent_this_call=True))
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(
            lambda _: broker.dispatch_operation(dsn, "r01a-op", gateway=gateway), range(2)))
    assert len(codes) == 3 and codes.count("applied") == 1
    assert gateway.calls == ["r01a-op"]
    assert sorted(s.sent_this_call for s in statuses) == [False, True]


def test_r01_001_eight_way_model_race_single_provider_request(migrated_db):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_model("r01b-op", alloc, attempt)).code == ResultCode.APPLIED
    gateway = CountingGateway()
    barrier = Barrier(8)

    def go(_):
        barrier.wait(timeout=30)
        return broker.dispatch_operation(dsn, "r01b-op", gateway=gateway,
                                         ownership_generation=gen)

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(go, range(8)))
    assert gateway.calls == ["r01b-op"]
    assert sum(s.sent_this_call for s in statuses) == 1
    assert broker.read_operation(dsn, "r01b-op")["dispatch_state"] == "observed"
    assert store.allocation_status(dsn, alloc)["reserved"] == 0


def test_r01_001_admission_replay_marks_unadmitted(migrated_db):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_model("r01c-op", alloc, attempt)).code == ResultCode.APPLIED
    current = store.get_control(dsn)["authority_version"]
    first = store.advance_dispatch(dsn, _cmd({"operation_id": "r01c-op", "launcher_id": "gateway",
                                              "grant_version": current,
                                              "ownership_generation": gen}))
    assert first.code == ResultCode.APPLIED and first.data.get("admitted") is True
    replay = store.advance_dispatch(dsn, _cmd({"operation_id": "r01c-op", "launcher_id": "gateway",
                                               "grant_version": current,
                                               "ownership_generation": gen}))
    assert replay.code == ResultCode.ALREADY_APPLIED and replay.data.get("admitted") is False


def test_r01_001_crash_before_admission_redispatches_once(migrated_db, monkeypatch):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_model("r01d-op", alloc, attempt)).code == ResultCode.APPLIED
    real, calls = broker._advance, []
    gateway = CountingGateway()

    def dying(*a):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated death before admission commit")
        return real(*a)

    monkeypatch.setattr(broker, "_advance", dying)
    with pytest.raises(RuntimeError):
        broker.dispatch_operation(dsn, "r01d-op", gateway=gateway, ownership_generation=gen)
    assert broker.read_operation(dsn, "r01d-op")["dispatch_state"] == "prepared"
    status = broker.dispatch_operation(dsn, "r01d-op", gateway=gateway, ownership_generation=gen)
    assert status.sent_this_call is True and gateway.calls == ["r01d-op"]
    assert broker.read_operation(dsn, "r01d-op")["dispatch_state"] == "observed"


def test_r01_001_crash_after_send_never_resends(migrated_db):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_model("r01e-op", alloc, attempt)).code == ResultCode.APPLIED
    gateway = CountingGateway()
    crashed = broker.dispatch_operation(dsn, "r01e-op", gateway=gateway,
                                        ownership_generation=gen, _crash_after_send=True)
    assert crashed.sent_this_call is True and crashed.dispatch_state == "dispatching"
    assert gateway.calls == ["r01e-op"]
    assert store.allocation_status(dsn, alloc)["reserved"] > 0
    again = broker.dispatch_operation(dsn, "r01e-op", gateway=gateway, ownership_generation=gen)
    assert again.sent_this_call is False and gateway.calls == ["r01e-op"]
    assert broker.read_operation(dsn, "r01e-op")["dispatch_state"] == "dispatching"
    assert store.operation_receipts(dsn, "r01e-op") == []
    decision = broker.reconcile(dsn, "r01e-op", {})
    assert decision.decision == "unresolved-liability"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0


def test_r01_001_crash_during_receipt_never_resends(migrated_db, monkeypatch):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_model("r01f-op", alloc, attempt)).code == ResultCode.APPLIED
    gateway, real, armed = CountingGateway(), broker.admit_launcher_receipt, {"crash": True}

    def dying(dsn_, op_, receipt):
        if armed["crash"]:
            armed["crash"] = False
            raise RuntimeError("simulated death during receipt admission")
        return real(dsn_, op_, receipt)

    monkeypatch.setattr(broker, "admit_launcher_receipt", dying)
    with pytest.raises(RuntimeError):
        broker.dispatch_operation(dsn, "r01f-op", gateway=gateway, ownership_generation=gen)
    assert gateway.calls == ["r01f-op"]
    assert broker.read_operation(dsn, "r01f-op")["dispatch_state"] == "dispatching"
    assert store.operation_receipts(dsn, "r01f-op") == []
    again = broker.dispatch_operation(dsn, "r01f-op", gateway=gateway, ownership_generation=gen)
    assert again.sent_this_call is False and gateway.calls == ["r01f-op"]
    decision = broker.reconcile(dsn, "r01f-op", {})
    assert decision.decision == "unresolved-liability"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0


def _capability_version(dsn, version):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id) VALUES (%s)"
                        " ON CONFLICT (id) DO NOTHING", (version,))
        conn.commit()


def _mutate(dsn, mutation, attempt, gen):
    if mutation == "grant":
        return {"grant": None, "gen": None}
    if mutation == "quarantine":
        _capability_version(dsn, "r01q-cap")
        capabilities.pin_capability(dsn, attempt, "r01q-cap")
        assert capabilities.quarantine(
            dsn, _cmd({"version_id": "r01q-cap"}), "r01q-cap", "r01 probe").code == ResultCode.APPLIED
        return {"grant": None, "gen": None}
    return {"grant": None, "gen": gen + 99}


def _revoke_grant(dsn):
    version = int(store.get_control(dsn)["authority_version"])
    assert store.seed_grant(
        dsn, _cmd({"version": version + 1, "charter_text": "r01 revoke"})).code == ResultCode.APPLIED


@pytest.mark.parametrize("mutation", ["grant", "quarantine", "generation"])
def test_r01_002_scheduler_refuses_without_send(migrated_db, mutation):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_sandbox("r01s-op", alloc, attempt)).code == ResultCode.APPLIED
    if mutation == "grant":
        _revoke_grant(dsn)
    kw = _mutate(dsn, mutation, attempt, gen)
    launcher = CountingLauncher()
    report = broker.dispatch_pending(dsn, _launchers(launcher), gateway=FailGateway(),
                                     ownership_generation=kw["gen"] if kw["gen"] is not None else gen,
                                     grant_version=kw["grant"])
    assert launcher.sends == [] and report.dispatched == []
    assert broker.read_operation(dsn, "r01s-op")["dispatch_state"] == "prepared"


@pytest.mark.parametrize("mutation", ["grant", "quarantine", "generation"])
def test_r01_002_workflow_refuses_without_send(migrated_db, mutation):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    args = _sandbox("r01w-op", alloc, attempt)
    assert broker.ensure_operation(dsn, **args).code == ResultCode.APPLIED
    if mutation == "grant":
        _revoke_grant(dsn)
    kw = _mutate(dsn, mutation, attempt, gen)
    launcher = CountingLauncher()
    key = f"r01w-{mutation}-{uuid.uuid4().hex[:8]}"
    ATTEMPT_WORKFLOW_RESOURCES[key] = {"launchers": _launchers(launcher),
                                       "gateway": FailGateway()}
    try:
        summary = broker.wf_ensure_dispatch(dsn, dict(args), 0,
                                            kw["gen"] if kw["gen"] is not None else gen,
                                            "n1", key)
    finally:
        ATTEMPT_WORKFLOW_RESOURCES.pop(key, None)
    assert launcher.sends == []
    assert summary["dispatch_state"] == "prepared"


@pytest.mark.parametrize("mutation", ["grant", "quarantine", "generation"])
def test_r01_002_model_refuses_without_provider_send(migrated_db, mutation):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_model("r01m-op", alloc, attempt)).code == ResultCode.APPLIED
    if mutation == "grant":
        _revoke_grant(dsn)
    kw = _mutate(dsn, mutation, attempt, gen)
    status = broker.dispatch_operation(dsn, "r01m-op", gateway=FailGateway(),
                                       ownership_generation=kw["gen"] if kw["gen"] is not None else gen,
                                       grant_version=kw["grant"])
    assert status.sent_this_call is False
    assert status.dispatch_state == "prepared"
    assert broker.read_operation(dsn, "r01m-op")["dispatch_state"] == "prepared"


def test_r01_002_validation_admission_race_refuses(migrated_db):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_sandbox("r01r-op", alloc, attempt)).code == ResultCode.APPLIED
    validated_grant = int(store.get_control(dsn)["authority_version"])
    _revoke_grant(dsn)
    launcher = CountingLauncher()
    status = broker.dispatch_operation(dsn, "r01r-op", launchers=_launchers(launcher),
                                       ownership_generation=gen,
                                       grant_version=validated_grant)
    assert status.sent_this_call is False and status.dispatch_state == "prepared"
    assert launcher.sends == []
    assert status.next_decision == "stale-grant"


def test_r01_002_missing_inputs_resolve_and_admit_when_eligible(migrated_db):
    dsn = migrated_db
    alloc, attempt, gen = _setup(dsn)
    assert broker.ensure_operation(dsn, **_sandbox("r01e-op", alloc, attempt)).code == ResultCode.APPLIED
    launcher = CountingLauncher()
    status = broker.dispatch_operation(dsn, "r01e-op", launchers=_launchers(launcher))
    assert status.sent_this_call is True and launcher.sends == ["r01e-op"]
    assert broker.read_operation(dsn, "r01e-op")["dispatch_state"] == "observed"
    assert broker.ensure_operation(dsn, **_sandbox("r01g-op", alloc, attempt)).code == ResultCode.APPLIED
    bare = store.advance_dispatch(dsn, _cmd({"operation_id": "r01g-op", "launcher_id": "L1"}))
    assert bare.code == ResultCode.APPLIED and bare.data.get("admitted") is True
