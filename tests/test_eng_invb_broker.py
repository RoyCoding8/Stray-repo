from __future__ import annotations

import uuid

from settlement import broker, store
from settlement.common import Command, ResultCode


def _cmd(payload: dict) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _setup(dsn, authorized=1000):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu",
                                     "authorized": authorized}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1",
                                             "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _sandbox(dsn, op_id="op1"):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 5_000, "max_output_bytes": 64},
        allocation_id="a1", attempt_id="att1")


def _model(dsn, op_id="opm"):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect="model-inference",
        payload={"model": "m1", "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id="a1", attempt_id="att1")


class RaisingGateway:
    def __init__(self):
        self.calls: list[str] = []

    def infer(self, request):
        self.calls.append(request.operation_id)
        raise RuntimeError("boom inside gateway client")

    def cancel(self, operation_id: str) -> bool:
        return True


class RecordingGateway:
    def __init__(self):
        self.cancelled: list[str] = []

    def infer(self, request):
        raise AssertionError("must not run inference")

    def cancel(self, operation_id: str) -> bool:
        self.cancelled.append(operation_id)
        return True


class ScriptLauncher:
    launcher_id = "fake-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.stops: list[str] = []

    def prior_send(self, operation_id: str) -> bool:
        return False

    def stop(self, operation_id: str) -> bool:
        self.stops.append(operation_id)
        return True

    def live_ids(self):
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str):
        return None


def test_gateway_raise_is_contained_as_unknown_receipt(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _model(dsn)
    gateway = RaisingGateway()
    status = broker.dispatch_operation(dsn, "opm", launchers={},
                                       gateway=gateway,
                                       ownership_generation=gen)
    assert status.dispatch_state == "unresolved"
    assert status.sent_this_call is True
    assert gateway.calls == ["opm"]
    row = broker.read_operation(dsn, "opm")
    assert row["dispatch_state"] == "unresolved"
    again = broker.dispatch_operation(dsn, "opm", launchers={},
                                      gateway=gateway,
                                      ownership_generation=gen)
    assert again.sent_this_call is False
    assert gateway.calls == ["opm"]
    assert store.allocation_status(dsn, "a1")["reserved"] > 0


def test_request_cancel_reaches_gateway_and_launchers(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    launcher = ScriptLauncher()
    gateway = RecordingGateway()
    result = broker.request_cancel(dsn, "op1",
                                   launchers={"local-process": launcher},
                                   gateway=gateway)
    assert result.code == ResultCode.APPLIED
    assert launcher.stops == ["op1"]
    assert gateway.cancelled == ["op1"]
    assert broker.read_operation(dsn, "op1")["cancel_state"] == "requested"


def test_ensure_operation_rejects_non_int_retries(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    result = broker.ensure_operation(
        dsn, operation_id="op-bad", effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"]},
        allocation_id="a1", attempt_id="att1", retries=None)
    assert result.code == ResultCode.INVALID_INPUT
