"""Child execution binds results to the exact staged source bytes."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, policy_step, worlds
from execution_authority import execution_authority

TASK = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")

STEP_SOURCE = (
    "def STEP(view, state):\n"
    "    action = {\"kind\": \"diagnose\", \"target\": \"requested\",\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"u\", \"question\": \"q\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"source\": \"requested\"}}\n"
)
SUBSTITUTED_STEP_SOURCE = STEP_SOURCE.replace('"requested"', '"substituted"')
MEMBER_SOURCE = (
    "def carried(task, oracle):\n"
    "    return {\"candidate\": {\"source\": \"requested\"},"
    " \"queries\": 0}\n"
)
SUBSTITUTED_MEMBER_SOURCE = MEMBER_SOURCE.replace("requested", "substituted")
INPUT_SENSITIVE_STEP_SOURCE = (
    "def STEP(view, state):\n"
    "    return {\"action\": {\"kind\": \"stop\","
    " \"inputs\": {\"purpose\": view[\"purpose\"]}}, \"state\": {}}\n"
)
INPUT_SENSITIVE_MEMBER_SOURCE = (
    "def carried(task, oracle):\n"
    "    return {\"candidate\": {\"task\": task[\"task_id\"]},"
    " \"queries\": 0}\n"
)


def _replace_before_dispatch(monkeypatch, filename: str,
                             replacement: str, expected: str) -> list:
    dispatch = method_exec.LocalLauncher.dispatch
    replaced = []

    def replace(launcher, operation):
        driver = Path(operation.payload["argv"][1])
        staged = driver.parent / filename
        assert staged.read_text(encoding="utf-8") == expected
        replaced.append(staged)
        staged.write_text(replacement, encoding="utf-8")
        return dispatch(launcher, operation)

    monkeypatch.setattr(method_exec.LocalLauncher, "dispatch", replace)
    return replaced


def test_local_step_receipt_carries_verified_source_digest():
    view = policy_step.materialize_view(
        task=TASK, observations=[], open_questions=[],
        last_result=None, eligible_methods=[], remaining={"steps": 1})

    with execution_authority("a56srcreceipt") as auth:
        stepped = method_exec.run_step_out_of_process(
            STEP_SOURCE, view, {}, dsn=auth["dsn"],
            allocation_id=auth["allocation_id"],
            operation_id=auth["operation_id"])
    expected = hashlib.sha256(STEP_SOURCE.encode("utf-8")).hexdigest()
    receipt = stepped["receipt"]
    launcher_receipt = receipt["details"]["raw_payload"]["launcher_receipt"]

    assert stepped["source_digest"] == expected
    assert stepped["operation_id"] == "a56srcreceipt-op"
    assert stepped["operation_ids"] == ["a56srcreceipt-op"]
    assert receipt["source_digest"] == expected
    assert launcher_receipt["profile"] == "local-process"
    assert launcher_receipt["containment"] is False


def test_step_rejects_source_substituted_before_dispatch(monkeypatch):
    replaced = _replace_before_dispatch(
        monkeypatch, "policy.py", SUBSTITUTED_STEP_SOURCE, STEP_SOURCE)
    view = policy_step.materialize_view(
        task=TASK, observations=[], open_questions=[],
        last_result=None, eligible_methods=[], remaining={"steps": 1})

    with execution_authority("a56srcsubst") as auth:
        with pytest.raises(method_exec.MethodExecutionError,
                           match="staged source digest mismatch"):
            method_exec.run_step_out_of_process(
                STEP_SOURCE, view, {}, dsn=auth["dsn"],
                allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])

    assert len(replaced) == 1


def test_member_rejects_source_substituted_before_dispatch(monkeypatch):
    replaced = _replace_before_dispatch(
        monkeypatch, "member.py", SUBSTITUTED_MEMBER_SOURCE, MEMBER_SOURCE)
    member = {"capability_id": "source-authority-test",
              "method_source": MEMBER_SOURCE, "entry": "carried"}

    with execution_authority("a56srcmemsubst") as auth:
        with pytest.raises(method_exec.MethodExecutionError,
                           match="staged source digest mismatch"):
            method_exec.run_member_out_of_process(
                member, TASK, dsn=auth["dsn"],
                allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])

    assert len(replaced) == 1


def test_step_rejects_driver_substitution_before_dispatch(monkeypatch):
    calls = []

    def replace(launcher, operation):
        calls.append(True)
        driver = Path(operation.payload["argv"][1])
        driver.write_text(driver.read_text(encoding="utf-8").replace(
            "payload['view']", "{'purpose': 'substituted'}"),
            encoding="utf-8")
        return dispatch(launcher, operation)

    dispatch = method_exec.LocalLauncher.dispatch
    monkeypatch.setattr(method_exec.LocalLauncher, "dispatch", replace)
    view = policy_step.materialize_view(
        task=TASK, observations=[], open_questions=[],
        last_result=None, eligible_methods=[], remaining={"steps": 1})

    with execution_authority("a56srcdrvsubst") as auth:
        with pytest.raises(method_exec.MethodExecutionError,
                           match="staged driver digest mismatch"):
            method_exec.run_step_out_of_process(
                INPUT_SENSITIVE_STEP_SOURCE, view, {}, dsn=auth["dsn"],
                allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])

    assert calls == [True]


def test_step_rejects_serialized_input_substitution_before_dispatch(
        monkeypatch):
    calls = []

    def replace(launcher, operation):
        calls.append(True)
        staged = Path(operation.payload["argv"][1]).parent / "step.json"
        payload = json.loads(staged.read_text(encoding="utf-8"))
        payload["view"]["purpose"] = "substituted"
        staged.write_text(json.dumps(payload), encoding="utf-8")
        return dispatch(launcher, operation)

    dispatch = method_exec.LocalLauncher.dispatch
    monkeypatch.setattr(method_exec.LocalLauncher, "dispatch", replace)
    view = policy_step.materialize_view(
        task=TASK, observations=[], open_questions=[],
        last_result=None, eligible_methods=[], remaining={"steps": 1})

    with execution_authority("a56srcinputsubst") as auth:
        with pytest.raises(method_exec.MethodExecutionError,
                           match="serialized input digest mismatch"):
            method_exec.run_step_out_of_process(
                INPUT_SENSITIVE_STEP_SOURCE, view, {}, dsn=auth["dsn"],
                allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])

    assert calls == [True]


def test_member_rejects_serialized_task_substitution_before_dispatch(
        monkeypatch):
    calls = []

    def replace(launcher, operation):
        calls.append(True)
        staged = Path(operation.payload["argv"][2]) / "task.json"
        payload = json.loads(staged.read_text(encoding="utf-8"))
        payload["task"] = dict(payload["task"], task_id="substituted")
        staged.write_text(json.dumps(payload), encoding="utf-8")
        return dispatch(launcher, operation)

    dispatch = method_exec.LocalLauncher.dispatch
    monkeypatch.setattr(method_exec.LocalLauncher, "dispatch", replace)
    member = {"capability_id": "task-authority-test",
              "method_source": INPUT_SENSITIVE_MEMBER_SOURCE, "entry": "carried"}

    with execution_authority("a56srcmeminputsubst") as auth:
        with pytest.raises(method_exec.MethodExecutionError,
                           match="serialized input digest mismatch"):
            method_exec.run_member_out_of_process(
                member, TASK, dsn=auth["dsn"],
                allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])

    assert calls == [True]


def test_step_payload_binds_staged_source_driver_and_input(monkeypatch):
    observed = {}
    dispatch = method_exec.LocalLauncher.dispatch

    def inspect(launcher, operation):
        observed.update(operation.payload)
        return dispatch(launcher, operation)

    monkeypatch.setattr(method_exec.LocalLauncher, "dispatch", inspect)
    view = policy_step.materialize_view(
        task=TASK, observations=[], open_questions=[],
        last_result=None, eligible_methods=[], remaining={"steps": 1})

    with execution_authority("a56srcpayload") as auth:
        stepped = method_exec.run_step_out_of_process(
            STEP_SOURCE, view, {}, dsn=auth["dsn"],
            allocation_id=auth["allocation_id"],
            operation_id=auth["operation_id"])
    assert observed["profile"] == "local-process"
    assert stepped["driver_digest"] == hashlib.sha256(
        (method_exec._STEP_DRIVER % "STEP").encode("utf-8")).hexdigest()
    assert stepped["input_digest"] == hashlib.sha256(
        stepped["serialized_input"].encode("utf-8")).hexdigest()


def test_durable_child_receipt_requires_operation_anchor(monkeypatch):
    monkeypatch.setattr(method_exec, "_durable_operation", lambda *_: None)

    with pytest.raises(method_exec.MethodExecutionError,
                       match="durable child operation is missing"):
        method_exec._durable_receipt("unused", "missing")


def test_durable_child_receipt_rejects_bad_content_digest(monkeypatch):
    import settlement.db as dbmod

    operation = {"dispatch_state": "observed", "reconcile_state": "none",
                 "settled": True, "payload": {}}
    content = {"data": {"worker": {"data": {"candidate": {}, "queries": 0}}},
               "outcome": "success"}

    class Cursor:
        def fetchall(self):
            return [("local:child", "success", content, "0" * 64)]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_):
            return Cursor()

    monkeypatch.setattr(method_exec, "_durable_operation",
                        lambda *_: operation)
    monkeypatch.setattr(dbmod, "connect", lambda _dsn: Connection())

    with pytest.raises(method_exec.MethodExecutionError,
                       match="content digest mismatch"):
        method_exec._durable_receipt("unused", "child")


def test_durable_child_receipt_rejects_unresolved_operation(monkeypatch):
    monkeypatch.setattr(method_exec, "_durable_operation", lambda *_: {
        "dispatch_state": "unresolved", "reconcile_state": "unresolved",
        "settled": False, "payload": {}})

    with pytest.raises(method_exec.MethodExecutionError,
                       match="conflicted or unresolved"):
        method_exec._durable_receipt("unused", "child")


def test_durable_child_receipt_rejects_conflicting_receipts(monkeypatch):
    from settlement.common import payload_digest
    import settlement.db as dbmod

    first = {"data": {"worker": {"data": {"candidate": {}, "queries": 0}}}}
    second = {"data": {"worker": {"data": {"candidate": {"x": 1}, "queries": 0}}}}
    rows = [("local:one", "success", first, payload_digest(first)),
            ("local:two", "success", second, payload_digest(second))]

    class Cursor:
        def fetchall(self):
            return rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_):
            return Cursor()

    monkeypatch.setattr(method_exec, "_durable_operation", lambda *_: {
        "dispatch_state": "observed", "reconcile_state": "none",
        "settled": True, "payload": {}})
    monkeypatch.setattr(dbmod, "connect", lambda _dsn: Connection())

    with pytest.raises(method_exec.MethodExecutionError,
                       match="conflicting receipts"):
        method_exec._durable_receipt("unused", "child")
