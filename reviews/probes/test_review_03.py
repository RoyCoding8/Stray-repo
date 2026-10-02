"""Review counterexamples at 72cfa11; passing tests assert fixed contracts, not acceptance.

Retired (defect closed; doubles stale against the fixed call shape):
- test_claim_fulfillment_omits_artifact_byte_verification -> superseded by
  tests/test_r01_fulfill.py::test_fulfill_artifact_claim_requires_root_and_bytes
  (real-DB fulfillment, missing/corrupt bytes refused, tamper check).
- test_overcharge_rolls_back_receipt_and_broker_acknowledges_delivery ->
  superseded by tests/test_settle_actual.py::test_overcharge_preserves_receipt_and_holds_liability
  (real-DB receipt preservation, liability hold, no durable ack on refusal).
"""

import importlib.util
import inspect
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from settlement import broker, evaluation, exec_profile, experiment, launcher_runsc, run, store
from settlement.common import Command, ResultCode


ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "a" * 64


def _launcher(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", lambda: SimpleNamespace(
        available=True, reason="review double", detail={}))
    return launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path)


def _op(generation=1):
    return broker.BrokerOp(operation_id="review-op", effect="sandbox-exec",
                           execution_version="v1", dispatch_generation=generation,
                           payload={"profile": "gvisor", "argv": ["python", "job.py"],
                                    "timeout_ms": 100, "max_output_bytes": 1024})


def _result(**kw):
    return exec_profile.ExecResult(**{
        "profile": "gvisor", "containment": True, "simulated": False,
        "returncode": 0, "stdout": "", "stderr": "", "timed_out": False,
        "truncated": False, "wall_ms": 1, "detail": {}, **kw})


class _Process:
    def __init__(self, timeout=False):
        self.stdout, self.stderr = io.BytesIO(b""), io.BytesIO(b"")
        self.returncode, self.waits, self.timeout = None, 0, timeout

    def wait(self, timeout=None):
        self.waits += 1
        if self.timeout and self.waits <= 2:
            raise subprocess.TimeoutExpired("docker", timeout)
        self.returncode = -9 if self.timeout else 0
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_supervisor_start_failure_refuses_execution(monkeypatch):
    # Migrated R03-002 (was test_execution_proceeds_when_supervisor_cannot_start,
    # which demonstrated unsupervised success): supervisor creation failure must
    # fence the started container and never report success. The docker-control
    # boundary is doubled because module-level Popen doubling cannot serve the
    # real stop sequence; tests/test_r03_sup.py proves it against a shim runtime.
    events = []

    def spawn(*args, **kwargs):
        events.append("docker-started")
        return _Process()

    def supervise(*args):
        events.append("supervisor-failed")
        return None

    monkeypatch.setattr(exec_profile.subprocess, "Popen", spawn)
    monkeypatch.setattr(exec_profile, "spawn_supervisor", supervise)
    monkeypatch.setattr(exec_profile, "terminate_verified",
                        lambda *a: events.append("fenced") or False)
    monkeypatch.setattr(exec_profile, "reap_supervisor", lambda *a: None)
    result = exec_profile.run_gvisor(["job"], image=DIGEST, name="review", timeout_ms=100)
    assert events == ["docker-started", "supervisor-failed", "fenced"]
    assert result.containment and result.detail["supervised"] is False
    assert result.detail["error"] == "supervision-unavailable"
    assert launcher_runsc._interpret(
        result, ["job"], DIGEST, "runsc", "review", 100)["_verdict"] == "failure"


def test_verified_stop_releases_tracking(tmp_path, monkeypatch):
    # Migrated R03-002 (first half of
    # test_timeout_loses_tracking_without_proving_container_stopped): a timeout
    # whose container is verified stopped releases tracking and reads not-live.
    launcher = _launcher(tmp_path, monkeypatch)
    stopped, reaped = [], []
    monkeypatch.setattr(exec_profile.subprocess, "Popen", lambda *a, **k: _Process(True))
    monkeypatch.setattr(exec_profile, "spawn_supervisor", lambda *a: "watchdog")
    monkeypatch.setattr(exec_profile, "reap_supervisor", reaped.append)
    monkeypatch.setattr(exec_profile, "terminate_verified",
                        lambda *a: stopped.append(a) or False)
    outcome = launcher.dispatch(_op())
    assert stopped and reaped == ["watchdog"]
    assert outcome.receipt.outcome == "failure"
    assert launcher.read_result("review-op")["data"]["timed_out"]
    assert launcher.read_result("review-op")["data"]["stop_verified"] is False
    assert not launcher._tracked("review-op")
    assert not launcher._supervise_files("review-op")
    assert launcher.is_live("review-op") is False


def test_unverified_stop_retains_tracking_until_termination(tmp_path, monkeypatch):
    # Migrated R03-002 (second half): when termination cannot be established,
    # tracking is retained, the operation still reads live, and a later repair
    # pass keeps retrying instead of dropping the exposure.
    launcher = _launcher(tmp_path, monkeypatch)
    monkeypatch.setattr(exec_profile.subprocess, "Popen", lambda *a, **k: _Process(True))
    monkeypatch.setattr(exec_profile, "spawn_supervisor", lambda *a: "watchdog")
    monkeypatch.setattr(exec_profile, "reap_supervisor", lambda *a: None)
    monkeypatch.setattr(exec_profile, "terminate_verified", lambda *a: None)
    monkeypatch.setattr(launcher_runsc, "terminate_verified", lambda *a: None)
    monkeypatch.setattr(launcher_runsc, "docker_container_running", lambda *a: True)
    outcome = launcher.dispatch(_op())
    assert outcome.receipt.outcome == "failure"
    assert launcher._tracked("review-op")
    assert launcher._supervise_files("review-op")
    assert launcher.is_live("review-op") is True
    report = launcher.enforce_deadlines()
    assert launcher._tracked("review-op")
    assert report["unverified"]


def test_stale_sender_refused_when_generation_advances_before_send(tmp_path, monkeypatch):
    # Migrated R03-001 (was test_new_generation_cannot_stop_sender_past_file_check,
    # which demonstrated the stale send): the final pre-send ownership check now
    # refuses the stale sender, releases its claim, and lets the newer generation
    # resume on retry. Only the scripted interleaving is doubled.
    launcher = _launcher(tmp_path, monkeypatch)
    original, newer, sends = launcher._supervise_state, [], []

    def interleave(*args):
        newer.append(launcher.dispatch(_op(2)))
        return original(*args)

    monkeypatch.setattr(launcher, "_supervise_state", interleave)
    monkeypatch.setattr(launcher_runsc, "run_gvisor", lambda *a, **k: sends.append(a) or _result())
    old = launcher.dispatch(_op(1))
    assert newer[0].refused_reason == "superseded-claim"
    assert launcher._paths("review-op", "v1")["generation"].read_text() == "2"
    assert not old.sent and old.refused_reason == "superseded-generation"
    assert sends == []
    monkeypatch.setattr(launcher, "_supervise_state", original)
    resumed = launcher.dispatch(_op(2))
    assert resumed.sent and len(sends) == 1


def test_tcp_connection_wait_respects_command_deadline():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(3)
    port = listener.getsockname()[1]

    def server():
        try:
            conn, _ = listener.accept()
            with conn:
                time.sleep(0.8)
        finally:
            listener.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        result = store.transact(f"host=127.0.0.1 port={port} dbname=review user=review sslmode=disable",
                                Command(request_id="deadline", deadline_ms=200), lambda *a: None)
        assert result.code == ResultCode.UNAVAILABLE_DEPENDENCY
        assert "deadline" in result.detail
        assert time.monotonic() - started < 1.5
    finally:
        thread.join(timeout=4)


def test_positive_retry_budget_terminates_without_rereading_failed_op(monkeypatch):
    # R03-009 migration: the corrected contract bounds retries with fresh operation
    # identities per try and records an explicit terminal failure; it never
    # re-reads one immutable failed operation until the round cap.
    composition = {"root": {"kind": "invoke", "node_id": "n", "retry_max": 1,
                             "effect": "sandbox-exec", "payload": {"profile": "local-process",
                             "argv": ["false"], "timeout_ms": 1000, "max_output_bytes": 100}},
                   "allocation_id": "allocation"}
    state, dispatches, seen = {}, [], []
    monkeypatch.setattr(broker, "DBOS", SimpleNamespace(run_step=lambda _, fn, *a: fn(*a)))
    monkeypatch.setitem(broker.ATTEMPT_WORKFLOW_RESOURCES, "attempt", {"launchers": {}})
    monkeypatch.setattr(broker, "wf_snapshot", lambda *a: {
        "lifecycle": "running", "continuation": state.get("continuation")})
    monkeypatch.setattr(run, "record_continuation", lambda d, a, c, *rest:
                        state.update(continuation=c.model_dump(mode="json")))
    def _outcome(dsn, operation_id):
        seen.append(operation_id)
        return {"found": True, "outcome": "failure", "dispatch_state": "observed",
                "receipts": [{"receipt_identity": "r", "outcome": "failure"}]}
    monkeypatch.setattr(run, "operation_outcome", _outcome)
    monkeypatch.setattr(broker, "ensure_operation", lambda *a, **k: None)
    monkeypatch.setattr(broker, "dispatch_operation", lambda d, op, **k:
                        dispatches.append(op) or broker.DispatchStatus(
                            operation_id=op, dispatch_state="observed", next_decision="done"))
    monkeypatch.setattr(broker, "wf_finish", lambda *a: {"code": "applied", "detail": "probe"})
    result = inspect.unwrap(broker.attempt_workflow)("unused", "attempt", 1, composition, 4)
    assert result["outcome"] == "completed"
    assert dispatches == []
    assert seen == ["attempt:n", "attempt:n:retry1"]
    assert state["continuation"]["completed"] == {"n": "op:attempt:n:retry1:failed"}
    assert state["continuation"]["observations"]["n:tries"] == ["attempt:n", "attempt:n:retry1"]


def test_heartbeat_wakes_waiting_workflow_through_repair_path(monkeypatch):
    # R03-008 migration: the corrected contract consumes newly observed outcomes
    # into the waiting continuation and resumes the workflow under an idempotent
    # identity; heartbeat no longer restores resources without waking.
    composition = {"version": "run/v1", "revision": 1, "allocation_id": "allocation",
                   "authority_version": 1,
                   "root": {"kind": "invoke", "node_id": "n", "effect": "sandbox-exec",
                            "payload": {"profile": "local-process", "argv": ["/bin/true"],
                                        "timeout_ms": 1000, "max_output_bytes": 100}}}
    cont = {"attempt_id": "waiting-attempt", "composition_version": "run/v1",
            "composition_revision": 1, "position": [], "completed": {},
            "observations": {}, "unresolved_ops": ["n:op1"], "obligations": {},
            "next": {"decision": "awaiting-op", "detail": "n:op1"}}
    restored, consumed, starts = [], [], []
    monkeypatch.setattr(store, "attempts_with_continuations",
                        lambda *a: [{"id": "waiting-attempt", "ownership_generation": 3}])
    monkeypatch.setattr(broker, "ATTEMPT_WORKFLOW_RESOURCES", {})
    def _restore(dsn, attempt_id, launchers, gateway=None):
        restored.append(attempt_id)
        broker.ATTEMPT_WORKFLOW_RESOURCES[attempt_id] = {"launchers": {},
                                                        "composition": composition}
    monkeypatch.setattr(broker, "restore_workflow_resources", _restore)
    monkeypatch.setattr(broker, "wf_snapshot", lambda *a: {
        "lifecycle": "running", "continuation": cont})
    monkeypatch.setattr(run, "operation_outcome", lambda *a: {
        "found": True, "outcome": "success", "dispatch_state": "observed",
        "receipts": [{"receipt_identity": "delayed", "outcome": "success"}]})
    def _consume(dsn, attempt_id, comp, cont_dict, node_id, operation_id, base, *rest):
        consumed.append((node_id, operation_id, base))
        done = dict(cont_dict)
        done["completed"] = {"n": "op:op1"}
        done["next"] = {"decision": "done", "detail": "invoke-complete"}
        done["unresolved_ops"] = []
        return {"continuation": done, "applied": True, "outcome": {"outcome": "success"}}
    monkeypatch.setattr(broker, "wf_consume", _consume)
    monkeypatch.setattr(broker, "dispatch_pending", lambda *a: broker.HeartbeatReport())
    monkeypatch.setattr(broker, "DBOS", SimpleNamespace(start_workflow=lambda *a: starts.append(a)))
    report = broker.heartbeat("unused", {})
    assert restored == ["waiting-attempt", "waiting-attempt"]
    assert consumed == [("n", "op1", "wake:waiting-attempt")]
    assert len(starts) == 1 and starts[0][2] == "waiting-attempt"
    assert "wake:waiting-attempt" in report.repaired


def test_dbos_checkpoint_detects_changed_step_results(monkeypatch):
    # R03-007 migration: the corrected barrier observes workflow step progress,
    # so a still-PENDING workflow committing a step mid-backup refuses to certify.
    spec = importlib.util.spec_from_file_location("review03_checkpoint", ROOT / "scripts/checkpoint.py")
    checkpoint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checkpoint)
    queries = []
    state = {"step_output": "old"}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, *args):
            queries.append(query)
            self.query = query

        def fetchall(self):
            if "information_schema" in self.query:
                return [("dbos",)]
            if "operation_outputs" in self.query:
                return [{"workflow_uuid": "same-pending-workflow", "function_id": 1,
                         "output": state["step_output"], "error": "", "child": ""}]
            return [{"workflow_uuid": "same-pending-workflow", "status": "PENDING"}]

    class Connection(Cursor):
        def cursor(self, **kwargs):
            return Cursor()

        def commit(self):
            pass

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: Connection())
    barrier, schema = checkpoint._workflow_barrier("unused")
    assert barrier["kind"] == "dbos-system"
    assert any("operation_outputs" in query for query in queries)
    assert checkpoint._workflow_verify("unused", barrier, schema) == []
    state["step_output"] = "new"
    violations = checkpoint._workflow_verify("unused", barrier, schema)
    assert any("steps moved" in item for item in violations)


def test_r03_unrelated_process_cannot_back_pinned_evaluation(tmp_path, monkeypatch):
    """Migrated from test_unrelated_successful_process_can_back_evaluation_binding: a pinned evaluator now refuses proof-less executables and bare success."""
    from settlement import launcher_local
    from settlement.common import SettlementError

    if os.name == "nt":
        monkeypatch.setattr(launcher_local, "_child_setup", lambda *a: None)
    launcher = launcher_local.LocalLauncher(tmp_path)
    payload = {"profile": "local-process", "argv": [sys.executable, "-c",
               "print('{\"status\": \"ok\", \"data\": {}}')"],
               "timeout_ms": 2000, "max_output_bytes": 1024}
    issued = broker.BrokerOp(operation_id="not-a-grader", effect="sandbox-exec", payload=payload)
    operation = {"dispatch_state": "prepared", "payload": {"effect": "sandbox-exec", **payload}}
    assignment = {"protocol_id": "p", "task_id": "task", "evaluation_op": "",
                  "candidate_digest": "", "evaluator_id": "", "evaluator_version": ""}
    package = {"version": "v1", "code_digest": "digest-of-a-different-program"}
    binding = evaluation._bind_state(assignment, ["candidate-digest"], None, False,
                                     operation, "v1", package)
    with pytest.raises(SettlementError, match="proves no executable"):
        evaluation._verify_bind(binding, assignment_id="a", candidate_digest="candidate-digest",
                                evaluator_id="e", evaluator_version="v1",
                                invocation_ref="not-a-grader")
    assert evaluation._verify_bind(
        binding, assignment_id="a", candidate_digest="candidate-digest",
        evaluator_id="e", evaluator_version="v1", invocation_ref="not-a-grader",
        executable_digest="digest-of-a-different-program") is False
    outcome = launcher.dispatch(issued)
    assert outcome.receipt.outcome == "success"
    assignment.update(candidate_digest="candidate-digest", evaluator_id="e",
                      evaluator_version="v1", evaluation_op="not-a-grader",
                      instance={"evaluation_binding":
                                {"executable_digest": "digest-of-a-different-program",
                                 "input_digest": "inputs-digest"}})
    operation["dispatch_state"] = "observed"
    state = evaluation._receipt_state(assignment, ["candidate-digest"], None, False,
                                      operation, [outcome.receipt.model_dump()], "v1", package)
    assert state["tallies"] == []
    with pytest.raises(SettlementError, match="bare process success"):
        evaluation._verify_receipt(state, assignment_id="a", evaluator_id="e",
                                   evaluator_version="v1", invocation_ref="not-a-grader",
                                   result={"outcome": "success", "detail": {"task_id": "task"}})


def test_r03_contained_grading_stages_mounted_inputs(tmp_path, monkeypatch):
    """Migrated from test_contained_grading_prepares_only_unmounted_host_paths: grading now stages through the launcher interface."""
    launcher = _launcher(tmp_path / "runs", monkeypatch)
    workdir = tmp_path / "work"
    workdir.mkdir()
    prepared = []
    monkeypatch.setattr(experiment, "_ensure_sandbox_op", lambda *a: prepared.append(a) or a[2])
    op_id, staged = experiment._prepare_grade(
        "unused", launcher, "def f(): return 0",
        [{"fn": "f", "args": [], "expected": 0}],
        "task", "allocation", "attempt", str(ROOT / "experiments/run_tests.py"))
    argv = prepared[0][3]
    assert op_id == "grade-task"
    assert argv[0] == launcher.staged_python()
    assert all(p.startswith("/work/inputs/") for p in argv[1:4])
    assert [m[1] for m in launcher._mounts(op_id, "")] == ["/work/inputs", "/work/outputs"]
    assert set(staged) == {"grader.py", "candidate.py", "cases.json"}
    assert list(workdir.rglob("*")) == []


def test_r03_exact_lookup_baseline_returns_unseen_input_unchanged(tmp_path):
    """Migrated from test_synthesized_method_returns_unseen_broken_input_unchanged: exact lookup stays as the labeled baseline."""
    method = tmp_path / "method.py"
    method.write_text(experiment._synthesize_method([
        {"outcome": "success", "broken": "def f(x): return x - 1\n",
         "text": "def f(x): return x + 1\n"}]))
    unseen = "def g(y): return y - 1\n"
    input_path, output_path = tmp_path / "input.py", tmp_path / "output.py"
    input_path.write_text(unseen)
    result = subprocess.run([sys.executable, str(method), str(input_path), str(output_path)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"status": "ok", "data": {"known": False}}
    assert output_path.read_text() == unseen
