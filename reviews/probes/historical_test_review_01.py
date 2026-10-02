"""Superseded REVIEW-01 defect probes (all four assert the old bugs).

Preserved as historical evidence; not a correctness test and not collected
(pytest only collects test_*.py). Superseded by tests/test_r01_grader.py
(probe 1, R01-008), tests/test_r01_authority.py (probe 2, R01-001),
tests/test_r01_runsc.py (probe 3, R01-005), tests/test_r01_evidence.py
(probe 4, R01-007). Each probe is expected to FAIL on fixed code."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier, Lock
from types import SimpleNamespace

from settlement import broker, evidence, experiment, launcher_runsc
from settlement.common import CommandResult, IncompatibleVersion, ResultCode
from settlement.gateway import FakeGatewayAdapter


ROOT = Path(__file__).resolve().parents[2]


def test_candidate_forges_grader_success(tmp_path, monkeypatch):
    candidate = "import json, sys\nprint(json.dumps({'status':'ok','data':{'passed':999,'failed':0}}))\nsys.exit(0)\n"
    observed = {}

    def execute(dsn, launcher, tag, argv, allocation_id, attempt_id):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        observed.update(exit_code=result.returncode, output=json.loads(result.stdout))
        return "probe-op", {"outcome": "success", "content": {"data": {"worker": observed["output"]}}}

    monkeypatch.setattr(experiment, "_run_sandbox", execute)
    _, verdict = experiment._grade("unused", None, tmp_path, candidate,
                                  [{"fn": "missing", "args": [], "expected": 42}],
                                  "forged", "unused", None, str(ROOT / "experiments/run_tests.py"))
    assert observed["exit_code"] == 0
    assert observed["output"]["data"]["passed"] == 999
    assert verdict == "success"


def test_model_dispatch_sends_on_both_advance_outcomes(monkeypatch):
    barrier, lock, calls = Barrier(2), Lock(), []
    row = {"dispatch_state": "prepared", "attempt_id": None, "execution_version": "v1",
           "payload": {"effect": broker.MODEL_INFERENCE, "payload": {
               "model": "fake", "messages": [], "max_output_tokens": 10, "deadline_ms": 1000}}}

    def read(dsn, operation_id):
        barrier.wait(timeout=10)
        return row

    def advance(*args):
        with lock:
            code = ResultCode.APPLIED if not calls else ResultCode.ALREADY_APPLIED
            calls.append(code.value)
        return CommandResult(code=code, request_id="same-request")

    class Gateway(FakeGatewayAdapter):
        def infer(self, request):
            with lock:
                sends.append(request.operation_id)
            return super().infer(request)

    sends = []
    monkeypatch.setattr(broker, "read_operation", read)
    monkeypatch.setattr(broker, "_advance", advance)
    monkeypatch.setattr(broker, "_finish_send", lambda *args: None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: broker.dispatch_operation("unused", "same-op", gateway=Gateway()), range(2)))
    assert calls == ["applied", "already_applied"]
    assert sends == ["same-op", "same-op"]


def test_gvisor_dispatch_is_missing_even_with_successful_probe(monkeypatch):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor",
                        lambda: SimpleNamespace(available=True, reason="probe succeeded"))
    launcher = launcher_runsc.RunscLauncher("sha256:" + "a" * 64)
    assert launcher.available
    try:
        launcher.dispatch(None)
    except IncompatibleVersion as exc:
        assert "probe succeeded" in str(exc)
    else:
        raise AssertionError("Expected the submitted launcher's unconditional refusal")


def test_retracted_claim_is_supported_as_root_but_not_as_premise():
    class Cursor:
        def execute(self, sql, params=()):
            self.sql = sql

        def fetchone(self):
            if "FROM retractions" in self.sql:
                return {"present": 1}
            if "FROM claims" in self.sql:
                return {"scope": {}}
            if "FROM observations" in self.sql:
                return {"authenticated": True}
            return None

        def fetchall(self):
            if "FROM derivations" in self.sql:
                return [{"id": "derivation", "scope": {}}]
            if "FROM derivation_premises" in self.sql:
                return [{"group_id": 1, "premise_ref": "obs", "premise_kind": "observation"}]
            raise AssertionError(self.sql)

    cursor = Cursor()
    original_execute = cursor.execute

    def execute(sql, params=()):
        original_execute(sql, params)
        if "FROM retractions" in sql and params == ("obs",):
            cursor.sql = "unretracted observation"

    cursor.execute = execute
    assert evidence._supported(cursor, "retracted-claim", frozenset(), None)[0]
    assert not evidence._live_premise(cursor, "retracted-claim", "claim", frozenset(), None)
