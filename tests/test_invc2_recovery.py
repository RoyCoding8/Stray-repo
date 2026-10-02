"""INV-C2 M3 gate: feedback and crash recovery.

Real Postgres (`inv_c2_rec`, never live) in every test. Doubles sit at the
provider seam only: a recording gateway answers model calls and the local
launcher runs sandboxes. Crash recovery runs in real subprocesses that die
mid-workflow: the test asserts exit codes proving an unfinished workflow,
then resumes in a new process without redoing model calls or validation.
Completed-boundary replay stays a separate behavior and is not used here
as a recovery proof.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "INV_C2_REC_DSN",
    "dbname=inv_c2_rec host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

DIAG_PAYLOAD = {"model": "scripted",
                "messages": [{"role": "user", "content": "look"}],
                "max_output_tokens": 8, "deadline_ms": 10_000}
SANDBOX_PAYLOAD = {"profile": "local-process", "argv": ["/bin/true"],
                   "timeout_ms": 10_000, "max_output_bytes": 1024}


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                " AND tablename != 'schema_migrations'")
            for (table,) in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()


class RecordingGateway:
    def __init__(self, texts, charge_units=0, billed=False):
        from settlement.gateway import Usage
        self._texts = list(texts)
        self._usage = Usage(input_tokens=11, output_tokens=7,
                            charge_units=charge_units, billed=billed)
        self.calls: list = []

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            self._texts[min(len(self.calls) - 1, len(self._texts) - 1)],
            {"simulated": True}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _packet():
    from experiments.ad01.packet import decision_packet
    return decision_packet(
        charter={"objective": "x", "freeze_id": "ad01"},
        visible=["t1"],
        experience={"observations": [{"observation_id": "obs-0",
                                      "task_id": "t1",
                                      "capability_id": "seed",
                                      "verdict": "unmeasured",
                                      "detail": "d"}]},
        retained=[], remaining={"queries": 6, "model_calls": 60},
        curriculum="t1", boundary={"world": 0, "arm": "I", "seq": 0})


def test_rejected_proposal_returns_reason_in_next_request():
    from settlement import authority
    from settlement.loop import ExperienceTransition, run_boundary
    _fresh_db()
    authority.authorize_study(DSN, "study-corr", authorized=100_000)
    gateway = RecordingGateway(['{"answer": 1}'])
    seen = []

    def _propose(materialized, state):
        failure = state.last_failure
        seen.append(failure["reason"] if failure else None)
        if failure is None:
            return {"target": "t1", "instrument": "teleport",
                    "inputs": {}, "dependencies": [],
                    "requested": {}, "hypothesis": None}
        return {"target": "t1", "instrument": "diagnose",
                "inputs": {"model": "scripted",
                           "prompt": "retry after refusal: %s"
                                     % failure["reason"],
                           "max_output_tokens": 8},
                "dependencies": [], "requested": {}, "hypothesis": None}

    transition, state = run_boundary(
        DSN, study_root="study-corr", allocation_id="study-corr",
        packet=_packet(), propose=_propose, gateway=gateway)
    assert transition.admission == "admitted"
    assert seen == [None, "unknown instrument 'teleport'"]
    assert len(gateway.calls) == 1
    prompt = gateway.calls[0].messages[-1]["content"]
    assert "unknown instrument 'teleport'" in prompt
    assert state.corrections_used == 1
    assert authority.correction_state(
        DSN, "study-corr", transition.packet_id)["used"] == 1
    [journaled] = ExperienceTransition.read_journal(DSN, "study-corr")
    assert journaled["admission"] == "admitted"
    assert journaled["proposal"]["corrections"] == [
        {"error": "unknown instrument 'teleport'"}]


DRIVER = r"""
import json
import os
import sys

ROOT = sys.argv[1]
MODE = sys.argv[2]
DSN = sys.argv[3]
WORK = sys.argv[4]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from settlement import authority, broker, db, store
from settlement.gateway import ModelResponse, Usage


class LoggingGateway:
    def __init__(self, path):
        self._path = path

    def infer(self, request):
        with open(self._path, "a") as handle:
            handle.write(json.dumps(
                {"operation_id": request.operation_id,
                 "prompt": request.messages[-1]["content"]}) + "\n")
        return ModelResponse(
            request.operation_id, "ok", {"simulated": True},
            Usage(input_tokens=11, output_tokens=7,
                  charge_units=3, billed=True), "stop")

    def cancel(self, operation_id):
        return False


DIAG = {"model": "scripted",
        "messages": [{"role": "user", "content": "look"}],
        "max_output_tokens": 8, "deadline_ms": 10_000}
SANDBOX = {"profile": "local-process", "argv": ["/bin/true"],
           "timeout_ms": 10_000, "max_output_bytes": 1024}

if MODE == "diagnose":
    authority.authorize_study(DSN, "study-crash", authorized=100_000)
    granted = authority.admit_study_call(
        DSN, "study-crash", kind="calibration",
        operation_id="study-crash-diag",
        effect=broker.MODEL_INFERENCE, payload=DIAG)
    status = broker.dispatch_operation(
        DSN, "study-crash-diag", launchers={},
        gateway=LoggingGateway(os.path.join(WORK, "gateway.log")))
    assert status.dispatch_state == "observed", status
    receipts = store.operation_receipts(DSN, "study-crash-diag")
    authority.note_phase(
        DSN, "study-crash", "dec-crash-0", "diagnostic",
        "study-crash-diag",
        detail={"receipts": [r["receipt_identity"] for r in receipts]})
    os._exit(13)

if MODE == "resume-diagnosed":
    status = authority.phase_status(DSN, "study-crash", "dec-crash-0")
    assert status["diagnostic"] is not None
    assert status["validation"] is None
    granted = authority.admit_study_call(
        DSN, "study-crash", kind="calibration",
        operation_id="study-crash-diag",
        effect=broker.MODEL_INFERENCE, payload=DIAG)
    assert granted.already is True
    from settlement.launcher_local import LocalLauncher
    broker.dispatch_operation(
        DSN, "study-crash-diag", launchers={},
        gateway=LoggingGateway(os.path.join(WORK, "gateway.log")))
    granted = authority.admit_study_call(
        DSN, "study-crash", kind="development",
        operation_id="study-crash-val",
        effect=broker.SANDBOX_EXEC, payload=SANDBOX)
    outcome = broker.dispatch_operation(
        DSN, "study-crash-val",
        launchers={"local-process": LocalLauncher(
            os.path.join(WORK, "runs"))},
        gateway=LoggingGateway(os.path.join(WORK, "gateway.log")))
    assert outcome.dispatch_state == "observed", outcome
    with open(os.path.join(WORK, "validator.log"), "a") as handle:
        handle.write("study-crash-val\n")
    authority.note_phase(
        DSN, "study-crash", "dec-crash-0", "validation",
        "study-crash-val",
        ref_digest=__import__("hashlib").sha256(
            b"candidate-bytes").hexdigest())
    os._exit(14)

if MODE == "finish":
    status = authority.phase_status(DSN, "study-crash", "dec-crash-0")
    assert status["diagnostic"] is not None
    assert status["validation"] is not None
    diag = store.operation_receipts(DSN, "study-crash-diag")
    val = store.operation_receipts(DSN, "study-crash-val")
    assert [r["outcome"] for r in diag] == ["success"]
    assert [r["outcome"] for r in val] == ["success"]
    print(json.dumps({
        "diagnostic": status["diagnostic"]["operation_id"],
        "validation": status["validation"]["operation_id"],
        "remaining": authority.study_remaining(DSN, "study-crash"),
        "ledger": authority.verify_ledger(DSN, "study-crash")}))
"""


def _run_driver(work: Path, mode: str):
    return subprocess.run(
        [sys.executable, "-c", DRIVER, str(ROOT), mode, DSN, str(work)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)


def test_crash_recovery_reuses_diagnostic_and_validation(tmp_path):
    from settlement import authority, broker, db
    _fresh_db()
    authority.authorize_study(DSN, "study-crash", authorized=100_000)
    work = tmp_path / "crash"
    work.mkdir()
    first = _run_driver(work, "diagnose")
    assert first.returncode == 13, first.stderr
    second = _run_driver(work, "resume-diagnosed")
    assert second.returncode == 14, second.stderr
    third = _run_driver(work, "finish")
    assert third.returncode == 0, third.stderr
    finished = json.loads(third.stdout)
    assert finished["diagnostic"] == "study-crash-diag"
    assert finished["validation"] == "study-crash-val"
    assert (work / "gateway.log").read_text().strip().splitlines() == [
        json.dumps({"operation_id": "study-crash-diag",
                    "prompt": "look"})]
    assert (work / "validator.log").read_text().splitlines() == [
        "study-crash-val"]
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM operations")
            assert cur.fetchone()[0] == 2
            cur.execute("SELECT count(*) FROM receipts")
            assert cur.fetchone()[0] == 2
            conn.commit()
    sandbox_exposure = broker.exposure_schedule(
        broker.SANDBOX_EXEC, SANDBOX_PAYLOAD)[0]
    diag_exposure = broker.exposure_schedule(
        broker.MODEL_INFERENCE, DIAG_PAYLOAD)[0]
    assert finished["ledger"]["consumed"] == 3 + sandbox_exposure
    assert finished["ledger"]["unknown"] == []
    assert finished["ledger"]["match"] is True
    assert finished["remaining"] == 100_000 - diag_exposure - sandbox_exposure


CORRECTION_DRIVER = r"""
import json
import sys

ROOT = sys.argv[1]
DSN = sys.argv[2]
STUDY = sys.argv[3]
MARKER = sys.argv[4]
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/src")

from experiments.ad01.packet import decision_packet
from settlement.loop import run_boundary


def _packet():
    return decision_packet(
        charter={"objective": "x", "freeze_id": "ad01"},
        visible=["t1"],
        experience={"observations": [{"observation_id": "obs-0",
                                      "task_id": "t1",
                                      "capability_id": "seed",
                                      "verdict": "unmeasured",
                                      "detail": "d"}]},
        retained=[], remaining={"queries": 6, "model_calls": 60},
        curriculum="t1", boundary={"world": 0, "arm": "I", "seq": 0})


def _propose(materialized, state):
    with open(MARKER, "a") as handle:
        handle.write("propose\n")
    return {"target": "t1", "instrument": "teleport",
            "inputs": {}, "dependencies": [],
            "requested": {}, "hypothesis": None}


transition, _ = run_boundary(
    DSN, study_root=STUDY, allocation_id=STUDY, packet=_packet(),
    propose=_propose, max_corrections=1)
print(json.dumps({"admission": transition.admission,
                  "continuation": transition.continuation}))
"""


def test_correction_limit_survives_restart(tmp_path):
    from settlement import authority, db
    _fresh_db()
    authority.authorize_study(
        DSN, "study-limit", authorized=100_000, correction_budget=1)
    marker = tmp_path / "proposals.log"
    marker.write_text("")

    def _drive():
        return subprocess.run(
            [sys.executable, "-c", CORRECTION_DRIVER, str(ROOT), DSN,
             "study-limit", str(marker)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300)

    first = _drive()
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["admission"] == "refused:malformed-action"
    assert json.loads(first.stdout)["continuation"]["correction"] == \
        "correction-budget-exhausted"
    assert len(marker.read_text().splitlines()) == 2
    second = _drive()
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["admission"] == "refused:malformed-action"
    assert json.loads(second.stdout)["continuation"]["correction"] == \
        "correction-budget-exhausted"
    assert len(marker.read_text().splitlines()) == 2
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT used FROM study_corrections"
                        " WHERE study_root = 'study-limit'")
            rows = cur.fetchall()
            conn.commit()
    assert [row[0] for row in rows] == [1]
