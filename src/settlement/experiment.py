"""S3 §11 A/B/C harness: exact-lookup baseline vs textual lessons vs invocable methods.

Development runs first under fresh workers: dev tasks execute through the
broker, the lesson is authored by a broker-routed model call over the dev
transcripts (or a caller-supplied draft recorded as such), and the retained
method is synthesized from the dev model texts and grades, then staged,
sandbox-verified and published through artifacts/capabilities. Pre-existing
registry entries are never reused as the retained method. Only then do
independent panel/transfer workers run A/B/C with matched within-task
tools: every arm issues exactly one model-inference operation carrying the
same bounded tool envelope and the same staged grader invocation under
identical caps, and every arm is graded on its own model text. Arms differ
only in retained context (none / frozen lesson / frozen invocable method);
C's method invocation is an additional broker-routed sandbox operation
whose cost counts under ``use``, and C's prompt carries that invocation's
actual retained result, never just the method source. A no-op method
ablation replays the same invocation path with an identity repair. The
default synthesis is an exact source-hash lookup labeled as a baseline; a
caller-supplied synthesizer may propose any other procedure. Evaluation
invokes the exact version frozen by this development run, never a registry
re-query; panel/transfer protocols freeze after development against those
actual versions (multi-family groups name a ``multi:`` set), and each trial
binds the actual immutable candidate before scoring.

Every model and sandbox effect routes through broker admission, reservation
and receipts. Reported costs derive from actual receipts and reservation
states, split into reservations, settled usage and unresolved exposure;
failed trials count under ``failed_trials`` and C invocations under ``use``.
Token counts are reported separately as labeled estimates, never as a
monetary ceiling. An insufficient grant refuses at admission, before
provider dispatch. Scripted doubles label everything ``simulated=True``; a
real gateway adapter may be passed unchanged with ``simulated=False``.
Sandbox children run outside the repository root with a scrubbed
environment: every argv file (grader, candidate, per-task cases) is staged
through the launcher interface into the run inputs mount and addressed by
its execution-visible path with the launcher's python, never a host path;
method outputs come back through the outputs mount. The cases file is a
protected evaluator input: the grader removes it after loading and each
candidate case runs in a private directory under `-I` receiving only its
own function name and arguments.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from . import artifacts, broker, capabilities, db, evaluation, store, trials
from .common import Command, ResultCode, SettlementError, payload_digest

GRADER_TIMEOUT_MS = 30_000
GRADER_MAX_BYTES = 65_536
MODEL_TOKENS = 512


def model_token_budget() -> int:
    raw = os.environ.get("SETTLEMENT_MODEL_TOKENS", "")
    if not raw:
        return MODEL_TOKENS
    try:
        budget = int(raw)
    except ValueError:
        raise SettlementError(f"SETTLEMENT_MODEL_TOKENS={raw!r} is not an integer")
    if budget <= 0:
        raise SettlementError(
            f"SETTLEMENT_MODEL_TOKENS={raw!r} must be a positive integer")
    return budget

LIVE_COMMAND = ("uv run python experiments/run_live_abc.py --dsn $SETTLEMENT_DSN"
                " --allocation live-abc --artifacts-root $ARTIFACT_ROOT")
LIVE_INPUTS = ("SETTLEMENT_GATEWAY_URL (endpoint URL), SETTLEMENT_GATEWAY_KEY"
               " (key env var), SETTLEMENT_GRANT_UNITS (monetary grant cap)")


def live_blocker() -> dict:
    return {"blocked": True, "command": LIVE_COMMAND, "required_inputs": LIVE_INPUTS}


def _sandbox_receipt(dsn: str, operation_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows[-1] if rows else None


def _ensure_sandbox_op(dsn: str, launcher: Any, operation_id: str,
                       argv: list[str], allocation_id: str,
                       attempt_id: str | None, timeout_ms: int,
                       execution_version: str = "") -> str:
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile, "argv": argv,
                 "timeout_ms": timeout_ms,
                 "max_output_bytes": GRADER_MAX_BYTES},
        allocation_id=allocation_id, attempt_id=attempt_id,
        execution_version=execution_version)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(
            f"operation {operation_id} not admitted: {ensured.detail}")
    return operation_id


def _run_sandbox(dsn: str, launcher: Any, operation_id: str, argv: list[str],
                 allocation_id: str, attempt_id: str | None,
                 timeout_ms: int = GRADER_TIMEOUT_MS,
                 execution_version: str = "") -> tuple[str, dict | None]:
    _ensure_sandbox_op(dsn, launcher, operation_id, argv, allocation_id,
                       attempt_id, timeout_ms, execution_version)
    broker.dispatch_operation(dsn, operation_id,
                              launchers={launcher.profile: launcher})
    return operation_id, _sandbox_receipt(dsn, operation_id)


def _within_task_tools() -> dict:
    return {"grade_selfcheck": {"timeout_ms": GRADER_TIMEOUT_MS,
                                "max_output_bytes": GRADER_MAX_BYTES,
                                "model_tokens": MODEL_TOKENS}}


def _worker_data(receipt: dict | None) -> dict:
    content = dict((receipt or {}).get("content") or {})
    worker = (content.get("data") or {}).get("worker") or {}
    return worker if isinstance(worker, dict) else {}


def _authenticated(receipt: dict | None, total: int) -> bool:
    content = dict((receipt or {}).get("content") or {})
    if (receipt or {}).get("outcome") != "success" or \
            content.get("parse") != "typed-json":
        return False
    worker = ((content.get("data") or {}).get("worker") or {})
    if not isinstance(worker, dict) or worker.get("status") != "ok":
        return False
    data = worker.get("data")
    return isinstance(data, dict) and total > 0 and \
        data.get("total") == total and data.get("passed") == total and \
        data.get("failed", 1) == 0 and not data.get("failures")


SOLVER_SOURCE_CONTRACT = (
    "Respond with Python source only: the complete repaired module as raw "
    "source bytes. No prose, no Markdown fences, no commentary, no JSON "
    "wrapper. The response bytes are written verbatim to candidate.py and "
    "graded; anything that is not parseable Python is a format error, not "
    "a task result.")

SOLVER_OK = "ok"
SOLVER_TRANSPORT = "transport"
SOLVER_TRUNCATED = "truncated"
SOLVER_FORMAT = "format"

GRADE_PASS = "pass"
GRADE_TIMEOUT = "timeout"
GRADE_IMPORT_EXECUTION = "import-execution"
GRADE_WRONG_ANSWER = "wrong-answer"
GRADE_UNGRADED = "ungraded"

_EXECUTION_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Interrupt|Exit)\b")


def validate_solver_output(raw: Any, *, stop_reason: str = "") -> dict:
    stop = stop_reason or ""
    if raw is None or not isinstance(raw, str):
        return {"status": SOLVER_TRANSPORT,
                "detail": "no usable model text reached the solver stage",
                "source": ""}
    if stop == "length" or stop.startswith("incomplete"):
        return {"status": SOLVER_TRUNCATED,
                "detail": f"provider stop reason {stop!r} signals truncation",
                "source": raw}
    if not raw.strip():
        return {"status": SOLVER_FORMAT,
                "detail": "empty response carries no source",
                "source": raw}
    try:
        compile(raw, "<solver-response>", "exec")
    except (SyntaxError, ValueError, RecursionError) as exc:
        return {"status": SOLVER_FORMAT,
                "detail": f"response is not parseable Python: {exc}",
                "source": raw}
    return {"status": SOLVER_OK,
            "detail": "response is parseable Python",
            "source": raw}


def _looks_like_execution(actual: Any) -> bool:
    if not isinstance(actual, str):
        return False
    if actual in ("timeout", "error"):
        return True
    if actual.startswith("candidate "):
        return True
    if actual in ("unparseable candidate channel output",
                  "malformed candidate envelope"):
        return True
    return _EXECUTION_RE.match(actual) is not None


def attribute_grade_receipt(receipt: dict | None,
                            total_cases: int) -> tuple[str, str, str]:
    if _authenticated(receipt, total_cases):
        return ("success", GRADE_PASS,
                f"{total_cases}/{total_cases} cases passed")
    content = dict((receipt or {}).get("content") or {})
    data = dict(content.get("data") or {})
    if (receipt or {}).get("outcome") == "failure" and data.get("timed_out"):
        return ("timeout", GRADE_TIMEOUT,
                "grader exceeded its sandbox budget")
    worker = data.get("worker") or {}
    result = worker.get("data") if isinstance(worker, dict) else None
    failures = result.get("failures") if isinstance(result, dict) else None
    if not isinstance(failures, list) or not failures:
        return ("failure", GRADE_UNGRADED,
                "grader receipt carries no case payload")
    if any(_looks_like_execution(f.get("actual")) for f in failures
           if isinstance(f, dict)):
        return ("failure", GRADE_IMPORT_EXECUTION,
                "at least one case failed in import or execution")
    return ("failure", GRADE_WRONG_ANSWER,
            "every failed case executed and returned a wrong value")


def model_stop_reason(dsn: str, operation_id: str) -> str:
    receipt = _sandbox_receipt(dsn, operation_id)
    content = dict((receipt or {}).get("content") or {})
    stop = content.get("stop_reason", "")
    return stop if isinstance(stop, str) else ""


def begin_solver_grade(dsn: str, launcher: Any, *, model_op: str, raw: Any,
                       cases: list, tag: str, allocation_id: str,
                       attempt_id: str | None, grader_path: str) -> tuple:
    validation = validate_solver_output(
        raw, stop_reason=model_stop_reason(dsn, model_op))
    operation_id, staged = _prepare_grade(
        dsn, launcher, validation["source"], cases, tag, allocation_id,
        attempt_id, grader_path)
    return (validation, operation_id, staged)


def finish_solver_grade(dsn: str, launcher: Any, operation_id: str,
                        total_cases: int,
                        staged: dict | None = None) -> dict:
    if staged:
        _verify_staged(operation_id, staged)
    broker.dispatch_operation(dsn, operation_id,
                              launchers={launcher.profile: launcher})
    receipt = _sandbox_receipt(dsn, operation_id)
    outcome, grade_class, detail = attribute_grade_receipt(
        receipt, total_cases)
    return {"outcome": outcome, "grade_class": grade_class,
            "grade_detail": detail}


def _prepare_grade(dsn: str, launcher: Any, candidate_code: str,
                   cases: list, tag: str, allocation_id: str,
                   attempt_id: str | None, grader_path: str,
                   grader_budget_ms: int = GRADER_TIMEOUT_MS,
                   execution_version: str = "") -> tuple[str, dict]:
    operation_id = f"grade-{tag}"
    inputs = (("grader.py", Path(grader_path).read_bytes()),
              ("candidate.py", candidate_code.encode()),
              ("cases.json", json.dumps(cases).encode()))
    staged: dict[str, tuple[str, str]] = {}
    for relpath, data in inputs:
        host_path = launcher.stage_input(operation_id, execution_version,
                                         relpath, data)
        staged[relpath] = (str(host_path),
                           hashlib.sha256(data).hexdigest())
    in_dir, _ = launcher.exec_dirs(operation_id, execution_version)
    _ensure_sandbox_op(
        dsn, launcher, operation_id,
        [launcher.staged_python(), f"{in_dir}/grader.py",
         f"{in_dir}/candidate.py", f"{in_dir}/cases.json",
         str(max(1000, grader_budget_ms - 2000))],
        allocation_id, attempt_id, grader_budget_ms, execution_version)
    return operation_id, staged


def _verify_staged(operation_id: str, staged: dict) -> None:
    for relpath, (host_path, digest) in staged.items():
        if hashlib.sha256(Path(host_path).read_bytes()).hexdigest() != digest:
            raise SettlementError(
                f"staged input {relpath} for {operation_id} changed after"
                " binding: launch refused")


def _dispatch_grade(dsn: str, launcher: Any, operation_id: str,
                    total_cases: int, staged: dict | None = None) -> str:
    return finish_solver_grade(
        dsn, launcher, operation_id, total_cases, staged)["outcome"]


def _grade(dsn: str, launcher: Any, workdir: Any, candidate_code: str,
           cases: list, tag: str, allocation_id: str,
           attempt_id: str | None, grader_path: str,
           grader_budget_ms: int = GRADER_TIMEOUT_MS) -> tuple[str, str]:
    _ = workdir
    operation_id, staged = _prepare_grade(
        dsn, launcher, candidate_code, cases, tag, allocation_id,
        attempt_id, grader_path, grader_budget_ms)
    return operation_id, _dispatch_grade(dsn, launcher, operation_id,
                                         len(cases), staged)


def _synthesize_method(transcripts: list[dict]) -> str | None:
    wins = [t for t in transcripts
            if t.get("outcome") == "success" and isinstance(t.get("text"), str)
            and t["text"]]
    if not wins:
        return None
    repairs = {hashlib.sha256(t["broken"].encode()).hexdigest(): t["text"]
               for t in wins}
    samples = [[t["broken"], t["text"]] for t in wins]
    return (
        "from __future__ import annotations\n"
        "import hashlib\nimport json\nimport sys\n"
        f"REPAIRS = {json.dumps(repairs, sort_keys=True)}\n"
        f"SAMPLES = {json.dumps(samples)}\n"
        "def repair(source):\n"
        "    return REPAIRS.get(hashlib.sha256(source.encode()).hexdigest(), source)\n"
        "def main(argv):\n"
        "    if argv == ['--selftest']:\n"
        "        ok = all(repair(broken) == fixed for broken, fixed in SAMPLES)\n"
        "        print(json.dumps({'status': 'ok' if ok else 'error',"
        " 'data': {'repairs': len(REPAIRS)}}))\n"
        "        return 0 if ok else 1\n"
        "    if len(argv) != 2:\n"
        "        print(json.dumps({'status': 'error', 'data': {},"
        " 'error': 'need [input output]'}))\n"
        "        return 2\n"
        "    with open(argv[0], encoding='utf-8') as handle:\n"
        "        source = handle.read()\n"
        "    with open(argv[1], 'w', encoding='utf-8') as handle:\n"
        "        handle.write(repair(source))\n"
        "    print(json.dumps({'status': 'ok',"
        " 'data': {'known': hashlib.sha256(source.encode()).hexdigest() in REPAIRS}}))\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv[1:]))\n"
    )


def _synthesize_noop() -> str:
    return (
        "from __future__ import annotations\n"
        "import json\nimport sys\n"
        "def repair(source):\n"
        "    return source\n"
        "def main(argv):\n"
        "    if argv == ['--selftest']:\n"
        "        probe = 'def f(x): return x\\n'\n"
        "        ok = repair(probe) == probe\n"
        "        print(json.dumps({'status': 'ok' if ok else 'error',"
        " 'data': {'repairs': 0}}))\n"
        "        return 0 if ok else 1\n"
        "    if len(argv) != 2:\n"
        "        print(json.dumps({'status': 'error', 'data': {},"
        " 'error': 'need [input output]'}))\n"
        "        return 2\n"
        "    with open(argv[0], encoding='utf-8') as handle:\n"
        "        source = handle.read()\n"
        "    with open(argv[1], 'w', encoding='utf-8') as handle:\n"
        "        handle.write(repair(source))\n"
        "    print(json.dumps({'status': 'ok', 'data': {'known': False}}))\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv[1:]))\n"
    )


def _invoke_method(dsn: str, launcher: Any, artifacts_root: Path,
                   capability: dict, broken_code: str, tag: str,
                   allocation_id: str, attempt_id: str,
                   execution_version: str = "") -> tuple[str, str]:
    raw = (artifacts_root / capability["artifact_digest"]).read_bytes()
    package = json.loads(raw.decode())
    files = {rel: bytes.fromhex(h) for rel, h in package["files"].items()}
    manifest = package["manifest"]
    entry = next(e["path"] for e in manifest["files"]
                 if e.get("kind", "file") != "dir" and e["path"].endswith(".py"))
    operation_id = f"invoke-{tag}"
    method_bytes = files[entry]
    launcher.stage_input(operation_id, execution_version, "method.py",
                         method_bytes)
    launcher.stage_input(operation_id, execution_version, "broken.py",
                         broken_code.encode())
    in_dir, out_dir = launcher.exec_dirs(operation_id, execution_version)
    operation_id, receipt = _run_sandbox(
        dsn, launcher, operation_id,
        [launcher.staged_python(), f"{in_dir}/method.py",
         f"{in_dir}/broken.py", f"{out_dir}/fixed.py"],
        allocation_id, attempt_id,
        execution_version=execution_version)
    worker = _worker_data(receipt)
    if worker.get("status") != "ok":
        raise SettlementError(f"method invocation {operation_id} failed")
    try:
        fixed = launcher.read_output(
            operation_id, execution_version, "fixed.py").decode()
    except OSError:
        raise SettlementError(
            f"method invocation {operation_id} left no exported output")
    proven = broker.read_operation(dsn, operation_id) or {}
    if proven.get("dispatch_state") not in ("observed", "reconciled") or receipt is None:
        raise SettlementError(f"method invocation {operation_id} left no receipt")
    return fixed, method_bytes.decode()


def _allocation_preflight(dsn: str, allocation_id: str) -> None:
    store.allocation_status(dsn, allocation_id)
    if int(store.get_control(dsn).get("authority_version", 0)) < 1:
        raise SettlementError(f"allocation {allocation_id} has no installed grant")


def _fresh_worker(dsn: str, *, tag: str, investigation_id: str,
                  allocation_id: str) -> str:
    attempt_id = f"{tag}-worker"
    acquired = store.acquire_work(dsn, Command(
        request_id=f"{tag}-acquire",
        payload={"attempt_id": attempt_id,
                 "investigation_id": investigation_id,
                 "allocation_id": allocation_id}))
    if acquired.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"fresh worker {attempt_id} refused: {acquired.detail}")
    return attempt_id


def _infer_via_broker(dsn: str, adapter: Any, *, operation_id: str, model: str,
                      prompt: str, allocation_id: str,
                      attempt_id: str | None) -> tuple[str, str | None, int]:
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": model_token_budget(), "deadline_ms": 300_000},
        allocation_id=allocation_id, attempt_id=attempt_id)
    if ensured.code == ResultCode.INSUFFICIENT_RESOURCES:
        raise SettlementError(
            f"operation {operation_id} refused before dispatch: {ensured.detail}")
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"operation {operation_id} not admitted: {ensured.detail}")
    broker.dispatch_operation(dsn, operation_id, gateway=adapter)
    receipt = _sandbox_receipt(dsn, operation_id)
    if receipt is None:
        return operation_id, None, 0
    content = dict(receipt.get("content") or {})
    usage = dict(content.get("usage") or {})
    charge = usage.get("charge_units", 0)
    return operation_id, content.get("text"), int(charge or 0)


def _op_accounting(dsn: str, operation_id: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT dispatch_state, reservation_id FROM operations"
                        " WHERE id = %s", (operation_id,))
            op = cur.fetchone()
            reservation = None
            if op is not None and op["reservation_id"]:
                cur.execute("SELECT amount, state FROM reservations WHERE id = %s",
                            (op["reservation_id"],))
                reservation = cur.fetchone()
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (operation_id,))
            receipts = [dict(r) for r in cur.fetchall()]
            conn.commit()
    reserved = int(reservation["amount"]) if reservation else 0
    terminal = receipts[-1] if receipts else None
    tokens = _receipt_tokens(terminal)
    if op is None:
        return {"operation_id": operation_id, "dispatch_state": "missing",
                "reserved": 0, "settled": 0, "unresolved": 0,
                "outcome": "missing", "tokens": tokens,
                "billed": False, "provider_charge_units": None}
    terms = [r for r in receipts if r["outcome"] in ("success", "failure")]
    if reservation is not None and reservation["state"] == "settled" and terms:
        usage = dict((terms[-1].get("content") or {}).get("usage") or {})
        raw_charge = usage.get("charge_units")
        verified = (bool(usage.get("billed")) and isinstance(raw_charge, int)
                    and not isinstance(raw_charge, bool)
                    and 0 <= raw_charge <= reserved)
        charge = raw_charge if verified else None
        settled = charge if verified else reserved
        return {"operation_id": operation_id,
                "dispatch_state": op["dispatch_state"], "reserved": reserved,
                "settled": settled, "unresolved": 0, "outcome": terms[-1]["outcome"],
                "tokens": _receipt_tokens(terms[-1]),
                "billed": verified, "provider_charge_units": charge}
    outcome = receipts[-1]["outcome"] if receipts else op["dispatch_state"]
    return {"operation_id": operation_id, "dispatch_state": op["dispatch_state"],
            "reserved": reserved, "settled": 0, "unresolved": reserved,
            "outcome": outcome, "tokens": tokens,
            "billed": False, "provider_charge_units": None}


def _receipt_tokens(receipt: dict | None) -> dict[str, int]:
    usage = dict(((receipt or {}).get("content") or {}).get("usage") or {})
    try:
        return {"input": int(usage.get("input_tokens", 0) or 0),
                "output": int(usage.get("output_tokens", 0) or 0)}
    except (TypeError, ValueError):
        return {"input": 0, "output": 0}


def _settle_costs(dsn: str, protocol_ids: list[str], operation_id: str,
                  category: str, note: str) -> dict:
    entry = _op_accounting(dsn, operation_id)
    for pid in set(protocol_ids):
        trials.record_expenditure(dsn, pid, category, entry["settled"],
                                  f"{note} [{operation_id}]")
    return entry


def _freeze_method(dsn: str, *, launcher: Any, workdir: Path, artifacts_root: Path,
                   allocation_id: str, family: str, method_code: str,
                   version_stem: str,
                   protocol_prefix: str) -> tuple[str, str, bool, dict | None]:
    raw = method_code.encode()
    name = f"{family}_method.py"
    staging = workdir / f"{protocol_prefix}-stage-{family}"
    staging.mkdir(parents=True, exist_ok=True)
    manifest = {"files": [{"path": name, "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(),
                           "size": len(raw)}],
                "entry": name, "verify_args": ["--selftest"]}
    receipt = artifacts.stage_package(dsn, staging, manifest=manifest,
                                      files={name: raw}, access_label="public")
    artifacts.publish_package(
        dsn, Command(request_id=f"{protocol_prefix}-pub-{version_stem}-{family}"),
        artifacts_root, receipt)
    version_id = version_stem
    conflict = None
    row = capabilities.get_version(dsn, version_id)
    if row is not None and row.get("artifact_digest") != receipt["digest"]:
        conflict = {"stem": version_stem,
                    "occupied_by": row.get("artifact_digest", "")}
        version_id = f"{version_stem}-{receipt['digest'][:8]}"
        row = capabilities.get_version(dsn, version_id)
        if row is not None and row.get("artifact_digest") != receipt["digest"]:
            raise SettlementError(
                f"method version {version_id} already freezes other bytes")
    if row is None:
        capabilities.publish_candidate(
            dsn, Command(request_id=f"{protocol_prefix}-pubcap-{version_id}"),
            artifacts_root, launcher, allocation_id, version_id=version_id,
            family=family, invocation={"entry": name},
            effect={"sandbox": "local-process"}, resource={},
            artifact_digest=receipt["digest"], applicability={"family": family},
            reference_version="baseline-v0", change="development retention",
            hypothesis=f"retained method helps {family}",
            protocol_id=f"{protocol_prefix}-dev", budget={"units": 500})
        return version_id, receipt["digest"], True, conflict
    return version_id, receipt["digest"], False, conflict


def _run_development(dsn: str, *, launcher: Any, adapter: Any, model: str,
                     workdir: Path, artifacts_root: Path, allocation_id: str,
                     investigation_id: str, tasks: list[dict], dev_ids: list[str],
                     grader_path: str, protocol_prefix: str,
                     supplied_lessons: dict | None,
                     method_version: str, protocols: list[str],
                     synthesize: Any = None,
                     dev_transcripts: dict | None = None) -> dict:
    by_id = {t["id"]: t for t in tasks}
    reused = dict(dev_transcripts or {})
    development: dict[str, Any] = {"outcomes": {}, "ops": [], "methods": {},
                                   "reused": sorted(reused),
                                   "acquisition": {},
                                   "transcripts": {}}
    for dev_id in dev_ids:
        task = by_id[dev_id]
        if dev_id in reused:
            prior = reused[dev_id]
            development["ops"].extend(
                [op for op in (prior.get("model_op"), prior.get("grade_op"))
                 if op])
            development["outcomes"][dev_id] = {
                "outcome": prior["outcome"], "grade_op": prior["grade_op"],
                "model_op": prior["model_op"],
                "solver_status": prior.get("solver_status"),
                "grade_class": prior.get("grade_class")}
            development["transcripts"][dev_id] = {
                "task_id": dev_id, "family": task["family"],
                "broken": task["broken"],
                "model_text": prior.get("model_text"),
                "outcome": prior["outcome"], "model_op": prior["model_op"],
                "grade_op": prior["grade_op"],
                "solver_status": prior.get("solver_status"),
                "grade_class": prior.get("grade_class")}
            continue
        tag = f"{protocol_prefix}-DEV-{dev_id}"
        attempt_id = _fresh_worker(dsn, tag=tag, investigation_id=investigation_id,
                                   allocation_id=allocation_id)
        model_op, text, _ = _infer_via_broker(
            dsn, adapter, operation_id=f"model-{tag}", model=model,
            prompt=json.dumps({"arm": "DEV", "task_id": dev_id,
                               "prompt": task["broken"],
                               "response_contract": SOLVER_SOURCE_CONTRACT}),
            allocation_id=allocation_id, attempt_id=attempt_id)
        development["ops"].append(model_op)
        _settle_costs(dsn, protocols, model_op, "construction",
                      f"development inference {dev_id}")
        validation, op_id, staged = begin_solver_grade(
            dsn, launcher, model_op=model_op, raw=text, cases=task["cases"],
            tag=tag, allocation_id=allocation_id, attempt_id=attempt_id,
            grader_path=grader_path)
        finished = finish_solver_grade(
            dsn, launcher, op_id, len(task["cases"]), staged)
        outcome = finished["outcome"]
        development["ops"].append(op_id)
        _settle_costs(dsn, protocols, op_id,
                      "construction" if outcome == "success" else "failed_trials",
                      f"development grade {dev_id}")
        development["outcomes"][dev_id] = {
            "outcome": outcome, "grade_op": op_id, "model_op": model_op,
            "solver_status": validation["status"],
            "grade_class": finished["grade_class"]}
        development["transcripts"][dev_id] = {
            "task_id": dev_id, "family": task["family"], "broken": task["broken"],
            "model_text": text, "outcome": outcome, "model_op": model_op,
            "grade_op": op_id, "solver_status": validation["status"],
            "grade_class": finished["grade_class"]}
    if supplied_lessons:
        lessons, provenance = dict(supplied_lessons), "supplied"
    else:
        dev_record = [
            {"task_id": i, "family": by_id[i]["family"],
             "outcome": development["outcomes"][i]["outcome"],
             "model_text": (development["transcripts"][i]["model_text"] or "")[:2000]}
            for i in dev_ids]
        lesson_op, text, _ = _infer_via_broker(
            dsn, adapter, operation_id=f"{protocol_prefix}-DEV-lesson", model=model,
            prompt=json.dumps({"author_lesson": True,
                               "dev_transcripts": dev_record}),
            allocation_id=allocation_id, attempt_id=None)
        development["ops"].append(lesson_op)
        _settle_costs(dsn, protocols, lesson_op, "construction", "lesson authoring")
        lessons, provenance = {"off_by_one": text or ""}, "model-authored"
    development["lessons"] = lessons
    development["lesson_provenance"] = provenance
    development["lesson_digest"] = hashlib.sha256(
        json.dumps(lessons, sort_keys=True).encode()).hexdigest()[:16]
    for family in sorted({by_id[i]["family"] for i in dev_ids}):
        transcripts = [development["transcripts"][i] for i in dev_ids
                       if by_id[i]["family"] == family]
        attempts = [{"task_id": t["task_id"], "outcome": t["outcome"],
                     "model_op": t["model_op"], "grade_op": t["grade_op"]}
                    for t in transcripts]
        build = synthesize or _synthesize_method
        method_code = build(
            [{"broken": t["broken"], "text": t["model_text"],
              "outcome": t["outcome"]} for t in transcripts])
        if method_code is None:
            development["acquisition"][family] = {
                "status": "no-successful-transcript", "version_id": None,
                "artifact_digest": None, "attempts": attempts,
                "provenance": "synthesized-from-dev-transcripts"}
            continue
        transcript_digest = hashlib.sha256(
            json.dumps(transcripts, sort_keys=True, default=str).encode()
        ).hexdigest()
        version_id, digest, fresh, conflict = _freeze_method(
            dsn, launcher=launcher, workdir=workdir, artifacts_root=artifacts_root,
            allocation_id=allocation_id, family=family, method_code=method_code,
            version_stem=method_version, protocol_prefix=protocol_prefix)
        development["methods"][family] = version_id
        development["acquisition"][family] = {
            "status": "synthesized", "version_id": version_id,
            "artifact_digest": digest, "transcript_digest": transcript_digest,
            "attempts": attempts,
            "method_kind": "custom" if synthesize else "exact-lookup-baseline",
            "version_conflict": conflict,
            "provenance": "synthesized-from-dev-transcripts"}
        if fresh:
            development["ops"].append(f"cap-verify-{version_id}")
            entry = _settle_costs(dsn, protocols, f"cap-verify-{version_id}",
                                  "construction", f"method verification {family}")
            development["acquisition"][family]["verification_op"] = \
                f"cap-verify-{version_id}"
            development["acquisition"][family]["verification_settled"] = \
                entry["settled"]
    development["noop_ablation"] = {}
    for family in sorted(development["methods"]):
        noop_version, _, noop_fresh, _ = _freeze_method(
            dsn, launcher=launcher, workdir=workdir, artifacts_root=artifacts_root,
            allocation_id=allocation_id, family=family,
            method_code=_synthesize_noop(),
            version_stem=f"{method_version}-noop",
            protocol_prefix=protocol_prefix)
        development["noop_ablation"][family] = noop_version
        if noop_fresh:
            development["ops"].append(f"cap-verify-{noop_version}")
            _settle_costs(dsn, protocols, f"cap-verify-{noop_version}",
                          "construction", f"noop verification {family}")
    return development


def _freeze_eval_protocol(dsn: str, pid: str, candidate: str, group: str,
                          evaluator_version: str, supersedes: str | None = None,
                          frozen_groups: list | None = None,
                          group_tasks: tuple = ()) -> None:
    if supersedes is None:
        trials.freeze_protocol(
            dsn, Command(request_id=f"{pid}-freeze"), protocol_id=pid,
            candidate_version=candidate, reference_version="baseline-v0",
            evaluator_version=evaluator_version,
            task_groups=[{"name": "development", "kind": "development"},
                         {"name": group, "kind": "protected-eval"}],
            budgets={"per_task_sandbox_ms": GRADER_TIMEOUT_MS,
                     "per_task_tokens": MODEL_TOKENS,
                     "amortization_horizon": {"tasks": 50}},
            metrics=["success_rate"], stopping={"rule": "fixed-panel"},
            exclusions=[], uncertainty={"treatment": "finite-panel-only"})
        return
    wanted = sorted(group_tasks)
    for frozen in frozen_groups or []:
        if not isinstance(frozen, dict):
            continue
        if frozen.get("name") == group:
            if sorted(frozen.get("tasks") or []) != wanted:
                raise SettlementError(
                    f"protocol {pid}: {group} tasks differ from the"
                    " admission-frozen panel policy")
    development_group = {"name": "development", "kind": "development",
                         "tasks": [t for frozen in frozen_groups or []
                                   if isinstance(frozen, dict)
                                   and frozen.get("name") == "development"
                                   for t in (frozen.get("tasks") or [])]}
    protected = {"name": "protected-eval", "kind": "protected-eval",
                 "evaluator_version": evaluator_version}
    trials.amend_protocol(
        dsn, Command(request_id=f"{pid}-freeze"), protocol_id=pid,
        supersedes=supersedes, candidate_version=candidate,
        task_groups=[development_group,
                     {"name": group, "kind": "visible-regression",
                      "tasks": list(group_tasks)}, protected])


def _group_candidate(group_ids: list[str], by_id: dict,
                     methods: dict) -> str:
    versions = sorted({methods[t["family"]] for t in (by_id[i] for i in group_ids)
                       if t["family"] in methods})
    if len(versions) == 1:
        return versions[0]
    if versions:
        return "multi:" + "+".join(versions)
    return ""


def _arm_prompt(harness_arm: str, task: dict, lessons_map: dict,
                retained: dict | None) -> dict:
    tools = _within_task_tools()
    if harness_arm == "C":
        return {"arm": "C", "task_id": task["id"], "prompt": task["broken"],
                "retained_method": (retained or {}).get("source"),
                "retained_invocation": (retained or {}).get("invocation"),
                "response_contract": SOLVER_SOURCE_CONTRACT,
                "tools": tools}
    if harness_arm == "B":
        return {"arm": "B", "task_id": task["id"],
                "prompt": lessons_map.get(task["family"], "") + "\n"
                + task["broken"],
                "response_contract": SOLVER_SOURCE_CONTRACT,
                "tools": tools}
    return {"arm": harness_arm, "task_id": task["id"],
            "prompt": task["broken"],
            "response_contract": SOLVER_SOURCE_CONTRACT, "tools": tools}


def _maybe_release(dsn: str, *, artifacts_root: Path, allocation_id: str,
                   investigation_id: str, protocol_prefix: str,
                   evaluator_version: str, simulated: bool,
                   protocols: dict, group_candidate: dict,
                   group_families: dict, verdicts: dict) -> dict:
    releases = {}
    for name in ("panel-C", "transfer-C"):
        pid = protocols[name]
        candidate = group_candidate[name]
        label = verdicts[name]["label"]
        if simulated:
            releases[name] = {"status": "skipped-synthetic",
                              "protocol_id": pid,
                              "reason": "synthetic evidence stays non-promotable"}
            continue
        families = group_families[name]
        row = capabilities.get_version(dsn, candidate) \
            if candidate and not candidate.startswith("multi:") else None
        if label != "observed-gain" or row is None:
            releases[name] = {"status": "ineligible", "protocol_id": pid,
                              "label": label, "candidate": candidate}
            continue
        if capabilities.quarantine_status(dsn, candidate) is not None:
            releases[name] = {"status": "ineligible", "protocol_id": pid,
                              "label": label, "candidate": candidate,
                              "reason": f"{candidate} quarantined"}
            continue
        release_id = f"{protocol_prefix}-{name}-rel"
        try:
            scope = dict(row.get("applicability") or row.get("scope") or {})
            capabilities.scoped_release(
                dsn, Command(request_id=f"{release_id}-cmd"),
                release_id=release_id, protocol_id=pid, versions=[candidate],
                scope=scope, disposition="limited", fallback="baseline-v0",
                policy_version=f"{protocol_prefix}-sel", invalidation={},
                evidence_refs=[], evaluator_version=evaluator_version)
            policy = f"{protocol_prefix}-router"
            mapping = {family: candidate for family in families}
            capabilities.save_router_policy(
                dsn, Command(request_id=f"{policy}-cmd"), version=policy,
                mapping=mapping)
            attempt_id = _fresh_worker(
                dsn, tag=f"{release_id}-reuse",
                investigation_id=investigation_id,
                allocation_id=allocation_id)
            routed = {family: capabilities.route(dsn, policy, family)
                      for family in families}
            for family in families:
                if routed[family].get("version_id"):
                    capabilities.pin_capability(dsn, attempt_id,
                                                routed[family]["version_id"])
            releases[name] = {"status": "released", "protocol_id": pid,
                              "release_id": release_id, "candidate": candidate,
                              "router_policy": policy, "routed": routed,
                              "reuse_attempt": attempt_id}
        except SettlementError as exc:
            releases[name] = {"status": "refused", "protocol_id": pid,
                              "candidate": candidate, "detail": str(exc)}
    return releases


def episode_cost_union(dsn: str, phases: dict[str, list[str]]) -> dict:
    claimed: dict[str, list[str]] = {}
    ordered: list[str] = []
    for phase, ops in (phases or {}).items():
        for op in ops or []:
            if not op:
                continue
            claimed.setdefault(op, []).append(phase)
            if op not in ordered:
                ordered.append(op)
    entries = {op: _op_accounting(dsn, op) for op in ordered}
    totals = {key: sum(entry[key] for entry in entries.values())
              for key in ("reserved", "settled", "unresolved")}
    tokens = {"input": sum(entry["tokens"]["input"]
                           for entry in entries.values()),
              "output": sum(entry["tokens"]["output"]
                            for entry in entries.values())}
    sums = {}
    for phase, ops in (phases or {}).items():
        unique = [op for op in dict.fromkeys(ops or []) if op]
        sums[phase] = {
            "ops": unique,
            "reserved": sum(entries[op]["reserved"] for op in unique),
            "settled": sum(entries[op]["settled"] for op in unique),
            "unresolved": sum(entries[op]["unresolved"] for op in unique)}
    return {"scope": "whole-episode-unique-operation-union",
            "unique_ops": ordered, "unique_op_count": len(ordered),
            "shared_ops": sorted(op for op, owners in claimed.items()
                                 if len(owners) > 1),
            "phases": sums, "totals": {**totals, "tokens": tokens},
            "unresolved_exposure": totals["unresolved"]}


def _resolve_use_selection(dsn: str, *, artifacts_root: str | Path,
                           task_family: str, disposition: dict | None,
                           bindings: dict | None) -> tuple[str, dict | None, str]:
    disp = dict(disposition or {})
    if disp.get("trial") is True:
        version = str((bindings or {}).get("version_id") or "")
        candidate = capabilities.get_version(dsn, version) if version else None
        if candidate is None:
            return ("incumbent", None,
                    f"trial-unavailable-unknown-{version or 'none'}")
        if capabilities.quarantine_status(dsn, candidate["id"]) is not None:
            return ("incumbent", None,
                    f"trial-unavailable-quarantined-{version}")
        if not artifacts.artifact_available(
                dsn, artifacts_root, candidate.get("artifact_digest", "")):
            return ("incumbent", None,
                    f"trial-unavailable-missing-bytes-{version}")
        return ("trial", candidate, f"explicit-trial-{version}")
    version = (disp.get("released") or {}).get(task_family)
    if not version:
        return ("incumbent", None, f"unreleased-no-release-for-{task_family}")
    policy = (disp.get("router_policies") or {}).get(task_family)
    if not policy:
        return ("incumbent", None,
                f"unreleased-no-router-policy-for-{task_family}")
    try:
        routed = capabilities.route(dsn, policy, task_family)
    except SettlementError:
        return ("incumbent", None,
                f"unreleased-router-refused-{task_family}")
    if routed.get("decision") != "select" \
            or routed.get("version_id") != version:
        detail = routed.get("reason") or f"got-{routed.get('version_id')}"
        return ("incumbent", None,
                f"unreleased-router-diverged-{task_family}-{detail}")
    candidate = capabilities.get_version(dsn, version)
    if candidate is None:
        return ("incumbent", None, f"unreleased-unknown-version-{version}")
    if capabilities.quarantine_status(dsn, version) is not None:
        return ("incumbent", None, f"unreleased-quarantined-{version}")
    scope = dict(candidate.get("applicability")
                 or candidate.get("scope") or {})
    if scope.get("family", task_family) != task_family:
        return ("incumbent", None,
                f"unreleased-wrong-scope-{version}-for-{task_family}")
    if not artifacts.artifact_available(
            dsn, artifacts_root, candidate.get("artifact_digest", "")):
        return ("incumbent", None, f"unreleased-missing-bytes-{version}")
    return ("selected", candidate, f"released-{version}-via-{policy}")


def run_subsequent_use(dsn: str, *, artifacts_root: str | Path,
                       launcher: Any, adapter: Any, model: str,
                       allocation_id: str, investigation_id: str,
                       episode_id: str, bindings: dict, use_task: dict,
                       grader_path: str, protocol_prefix: str,
                       prior_exposure: str = "",
                       disposition: dict | None = None) -> dict:
    task_id = str(use_task["id"])
    tag = f"{protocol_prefix}-use-{task_id}"
    attempt_id = _fresh_worker(dsn, tag=tag,
                               investigation_id=investigation_id,
                               allocation_id=allocation_id)
    use_pid = f"{protocol_prefix}-use-{task_id}"
    trials.freeze_protocol(
        dsn, Command(request_id=f"{use_pid}-freeze"), protocol_id=use_pid,
        candidate_version=str((bindings or {}).get("version_id") or ""),
        reference_version="baseline-v0", evaluator_version="v1",
        task_groups=[{"name": f"use-{task_id}", "kind": "development",
                      "tasks": [task_id]},
                     {"name": "protected-eval", "kind": "protected-eval"}],
        budgets={"per_task_sandbox_ms": GRADER_TIMEOUT_MS,
                 "per_task_tokens": MODEL_TOKENS},
        metrics=["success_rate"], stopping={"rule": "fixed-panel"},
        exclusions=[], uncertainty={"treatment": "finite-panel-only"})
    evaluation.propose_hidden_answer(
        dsn, Command(request_id=f"{use_pid}-answer"),
        task_id, {"cases": use_task["cases"]})
    roots = Path(artifacts_root)
    method, capability, reason = _resolve_use_selection(
        dsn, artifacts_root=roots, task_family=str(use_task.get("family", "")),
        disposition=disposition, bindings=bindings)
    trial = bool((disposition or {}).get("trial") is True)
    ops: dict[str, str] = {}
    solver: dict[str, Any] = {"solver_status": None, "solver_detail": "",
                              "grade_class": None, "grade_detail": "",
                              "raw_text": None}
    if capability is None:
        method = "incumbent"
        model_op, text, _ = _infer_via_broker(
            dsn, adapter, operation_id=f"model-{tag}", model=model,
            prompt=json.dumps(_arm_prompt("A", use_task, {}, None)),
            allocation_id=allocation_id, attempt_id=attempt_id)
        ops["model_op"] = model_op
        _settle_costs(dsn, [use_pid], model_op, "use",
                      f"subsequent incumbent inference {task_id}")
        validation, grade_op, staged = begin_solver_grade(
            dsn, launcher, model_op=model_op, raw=text,
            cases=use_task["cases"], tag=tag, allocation_id=allocation_id,
            attempt_id=attempt_id, grader_path=grader_path)
        finished = finish_solver_grade(
            dsn, launcher, grade_op, len(use_task["cases"]), staged)
        outcome = finished["outcome"]
        solver = {"solver_status": validation["status"],
                  "solver_detail": validation["detail"],
                  "grade_class": finished["grade_class"],
                  "grade_detail": finished["grade_detail"],
                  "raw_text": text}
    else:
        capabilities.pin_capability(dsn, attempt_id, capability["id"])
        fixed, _ = _invoke_method(
            dsn, launcher, roots, capability, use_task["broken"], tag,
            allocation_id, attempt_id)
        ops["invoke_op"] = f"invoke-{tag}"
        _settle_costs(dsn, [use_pid], ops["invoke_op"], "use",
                      f"subsequent {'trial' if method == 'trial' else 'method'}"
                      f" invocation {task_id}")
        grade_op, outcome = _grade(dsn, launcher, None, fixed,
                                   use_task["cases"], tag, allocation_id,
                                   attempt_id, grader_path)
        _, grade_class, grade_detail = attribute_grade_receipt(
            _sandbox_receipt(dsn, grade_op), len(use_task["cases"]))
        solver = {"solver_status": None, "solver_detail": "",
                  "grade_class": grade_class, "grade_detail": grade_detail,
                  "raw_text": None}
    ops["grade_op"] = grade_op
    _settle_costs(dsn, [use_pid], grade_op,
                  "use" if outcome == "success" else "failed_trials",
                  f"subsequent grade {task_id}")
    recon = store.restart_reconciliation(dsn)
    settled_disp = {"released": dict((disposition or {}).get("released") or {}),
                    "router_policies": dict((disposition or {}).get(
                        "router_policies") or {}),
                    "trial": trial}
    use = {"episode_id": episode_id, "task_id": task_id,
           "method": method,
           "version_id": capability["id"] if capability is not None else "",
           "outcome": outcome, "reason": reason, "trial": trial,
           "disposition": settled_disp, "ops": ops, "protocol_id": use_pid,
           "prior_exposure": prior_exposure, **solver,
           "pending_operations": sorted(
               str(op.get("id", "")) for op in
               recon.get("unfinished_operations", []))}

    def _fn(cur, control):
        return (ResultCode.APPLIED, f"episode {episode_id} subsequent use",
                dict(use),
                [("development.subsequent_use", dict(use))], [])
    store.transact(dsn, Command(request_id=f"{tag}-record", payload={}), _fn)
    return use


def run_abcs(dsn: str, *, launcher: Any, artifacts_root: str | Path,
             allocation_id: str, investigation_id: str, tasks: list[dict],
             dev_ids: list[str], panel_ids: list[str], transfer_ids: list[str],
             lessons: dict[str, str] | None = None, double: Any = None,
             gateway: Any = None,
             grader_path: str, protocol_prefix: str = "abc",
             fixer_version: str = "", evaluator_id: str = "s3-eval",
             evaluator_version: str = "v1", simulated: bool = True,
             model: str = "scripted", synthesize: Any = None,
             dev_transcripts: dict | None = None,
             panel_protocol: dict | None = None) -> dict:
    adapter = double if double is not None else gateway
    if adapter is None:
        raise SettlementError("run_abcs needs a gateway adapter via gateway= or double=")
    _allocation_preflight(dsn, allocation_id)
    roots = Path(artifacts_root)
    workdir = Path(tempfile.mkdtemp(prefix="abc-"))
    method_version = fixer_version or "fixer-v1"
    grader_digest = hashlib.sha256(
        Path(grader_path).read_bytes()).hexdigest()
    evaluation.register_evaluator(
        dsn, Command(request_id=f"{protocol_prefix}-eval"),
        evaluator_id, evaluator_version, {"scope": "protected-eval"},
        code_digest=grader_digest)
    by_id = {t["id"]: t for t in tasks}
    for task in tasks:
        evaluation.propose_hidden_answer(
            dsn, Command(request_id=f"{protocol_prefix}-answer-{task['id']}"),
            task["id"], {"cases": task["cases"]})
    dev_pid = f"{protocol_prefix}-dev"
    _freeze_eval_protocol(dsn, dev_pid, "", "dev-heldout", evaluator_version)
    development = _run_development(
        dsn, launcher=launcher, adapter=adapter, model=model, workdir=workdir,
        artifacts_root=roots, allocation_id=allocation_id,
        investigation_id=investigation_id, tasks=tasks, dev_ids=dev_ids,
        grader_path=grader_path, protocol_prefix=protocol_prefix,
        supplied_lessons=lessons, method_version=method_version,
        protocols=[dev_pid], synthesize=synthesize,
        dev_transcripts=dev_transcripts)
    group_tasks = {"panel": panel_ids, "transfer": transfer_ids}
    group_candidate, group_families, protocols = {}, {}, {}
    frozen = panel_protocol or {}
    for name in ("panel-B", "panel-C", "transfer-B", "transfer-C"):
        group = "panel" if name.startswith("panel") else "transfer"
        cand = "lessons-v1" if name.endswith("-B") else _group_candidate(
            group_tasks[group], by_id, development["methods"])
        group_candidate[name] = cand
        group_families[name] = sorted({by_id[i]["family"]
                                       for i in group_tasks[group]})
        pid = f"{protocol_prefix}-{name}"
        _freeze_eval_protocol(
            dsn, pid, cand, group, evaluator_version,
            supersedes=frozen.get("eval_protocol"),
            frozen_groups=frozen.get("groups"),
            group_tasks=tuple(group_tasks[group]))
        protocols[name] = pid
    lessons_map = development["lessons"]
    report: dict[str, Any] = {"arms": {}, "verdicts": {}, "budgets": {},
                              "invocations": [], "invocation_results": {},
                              "ablation_noop": {}, "simulated": simulated,
                              "attempts": {}, "grade_ops": {}, "model_ops": {},
                              "tool_spec": _within_task_tools(),
                              "selection": {"group_candidate": dict(group_candidate),
                                            "method_set": dict(development["methods"])},
                              "development": development,
                              "accounting": {"ops": {}, "totals": {}}}
    for op_id in development["ops"]:
        report["accounting"]["ops"][op_id] = {
            **_op_accounting(dsn, op_id), "arm": "dev", "kind": "construction"}
    seq = 0
    for task_id in panel_ids + transfer_ids:
        task = by_id[task_id]
        group = "panel" if task_id in panel_ids else "transfer"
        for harness_arm in ("A", "B", "C"):
            seq += 1
            tag = f"{protocol_prefix}-{harness_arm}-{task_id}-{seq}"
            attempt_id = _fresh_worker(dsn, tag=tag,
                                       investigation_id=investigation_id,
                                       allocation_id=allocation_id)
            report["attempts"].setdefault(harness_arm, []).append(attempt_id)
            invoke_op = None
            retained = None
            actual = None
            if harness_arm == "C":
                frozen = development["methods"].get(task["family"])
                capability = capabilities.get_version(dsn, frozen) \
                    if frozen else None
                if capability is None:
                    report.setdefault("abstentions", []).append(
                        f"no-applicable-method-{tag}")
                else:
                    capabilities.pin_capability(dsn, attempt_id, capability["id"])
                    fixed, method_source = _invoke_method(
                        dsn, launcher, roots, capability, task["broken"], tag,
                        allocation_id, attempt_id)
                    invoke_op = f"invoke-{tag}"
                    report["invocations"].append(invoke_op)
                    report["invocation_results"][invoke_op] = {
                        "version": frozen, "fixed": fixed}
                    retained = {"source": method_source,
                                "invocation": {"invoke_op": invoke_op,
                                               "fixed": fixed}}
                    actual = {"version": frozen,
                              "artifact_digest": capability["artifact_digest"]}
                    invoke_entry = _settle_costs(
                        dsn, [protocols[f"{group}-C"]], invoke_op, "use",
                        f"method invocation {task_id}")
                    report["accounting"]["ops"][invoke_op] = {
                        **invoke_entry, "arm": "C", "kind": "invoke",
                        "task_id": task_id}
            prompt = json.dumps(
                _arm_prompt(harness_arm, task, lessons_map, retained))
            model_op, text, _ = _infer_via_broker(
                dsn, adapter, operation_id=f"model-{tag}", model=model,
                prompt=prompt, allocation_id=allocation_id, attempt_id=attempt_id)
            report["model_ops"].setdefault(harness_arm, {})[task_id] = model_op
            validation, op_id, staged = begin_solver_grade(
                dsn, launcher, model_op=model_op, raw=text,
                cases=task["cases"], tag=tag, allocation_id=allocation_id,
                attempt_id=attempt_id, grader_path=grader_path)
            report["grade_ops"].setdefault(harness_arm, {})[task_id] = op_id
            pids = [protocols[f"{group}{suffix}"]
                    for suffix in (("-B", "-C") if harness_arm == "A" else
                                   (("-B",) if harness_arm == "B" else ("-C",)))]
            suffixes = (("-B", "-C") if harness_arm == "A" else
                        (("-B",) if harness_arm == "B" else ("-C",)))
            assignment_ids = [
                _open_assignment(dsn, pid, task, group, harness_arm,
                                 validation["source"],
                                 f"{tag}{suffix}", evaluator_id,
                                 evaluator_version, op_id,
                                 executable_digest=staged["grader.py"][1],
                                 input_digest=staged["cases.json"][1],
                                 method=actual)
                for suffix, pid in zip(suffixes, pids)]
            finished = finish_solver_grade(dsn, launcher, op_id,
                                           len(task["cases"]), staged)
            outcome = finished["outcome"]
            model_entry = _settle_costs(dsn, pids, model_op, "evaluation",
                                        f"{harness_arm} inference {task_id}")
            report["accounting"]["ops"][model_op] = {
                **model_entry, "arm": harness_arm, "kind": "inference",
                "task_id": task_id}
            grade_entry = _settle_costs(
                dsn, pids, op_id,
                "evaluation" if outcome == "success" else "failed_trials",
                f"grade {tag}")
            report["accounting"]["ops"][op_id] = {
                **grade_entry, "arm": harness_arm, "kind": "grade",
                "task_id": task_id}
            for assignment_id, suffix in zip(assignment_ids, suffixes):
                _close_assignment(
                    dsn, assignment_id, task, op_id, outcome,
                    f"{tag}{suffix}", evaluator_id, evaluator_version,
                    simulated,
                    {"model": model, "arm": harness_arm,
                     "env": {"launcher": launcher.profile,
                             "method": (actual or {}).get("version")
                             if harness_arm == "C" else None}},
                    cost={"settled_units": grade_entry["settled"],
                          "reservation_units": grade_entry["reserved"]},
                    retention={"lesson_digest": development["lesson_digest"],
                               "method": development["methods"].get(task["family"]),
                               "artifact_digest": (actual or {}).get("artifact_digest")})
            report["arms"].setdefault(harness_arm, {})[task_id] = {
                "outcome": outcome, "grade_op": op_id, "model_op": model_op,
                "simulated": simulated,
                "solver_status": validation["status"],
                "solver_detail": validation["detail"],
                "grade_class": finished["grade_class"],
                "grade_detail": finished["grade_detail"],
                "raw_text": text,
                "source_digest": staged["candidate.py"][1]}
            if harness_arm == "C" and actual is not None:
                _run_noop_ablation(
                    dsn, launcher=launcher, roots=roots, task=task, group=group,
                    tag=tag, allocation_id=allocation_id, attempt_id=attempt_id,
                    grader_path=grader_path, protocols=protocols,
                    noop_version=development["noop_ablation"][task["family"]],
                    report=report)
    for name, pid in protocols.items():
        report["verdicts"][name] = trials.verdict(dsn, pid)
    for arm in ("A", "B", "C"):
        pids = ([protocols["panel-B"], protocols["transfer-B"]] if arm == "B" else
                [protocols["panel-C"], protocols["transfer-C"]] if arm == "C" else
                [protocols["panel-B"], protocols["panel-C"],
                 protocols["transfer-B"], protocols["transfer-C"]])
        by_cat: dict[str, int] = {}
        for pid in set(pids):
            for cat, amount in trials.development_expenditure(
                    dsn, pid)["by_category"].items():
                by_cat[cat] = by_cat.get(cat, 0) + amount
        arm_ops = [e for e in report["accounting"]["ops"].values()
                   if e["arm"] == arm]
        report["budgets"][arm] = {
            "ledger_by_category": by_cat,
            "unique_op_cost": sum(e["settled"] for e in arm_ops),
            "reservations": sum(e["reserved"] for e in arm_ops),
            "settled_usage": sum(e["settled"] for e in arm_ops),
            "unresolved_exposure": sum(e["unresolved"] for e in arm_ops),
            "token_estimates": {
                "input_tokens": sum(e["tokens"]["input"] for e in arm_ops),
                "output_tokens": sum(e["tokens"]["output"] for e in arm_ops),
                "basis": "token-length estimate; not a monetary ceiling"},
            "matched_caps": {"sandbox_ms": GRADER_TIMEOUT_MS,
                             "tokens": MODEL_TOKENS}}
    totals = {k: sum(e[k] for e in report["accounting"]["ops"].values())
              for k in ("reserved", "settled", "unresolved")}
    totals["tokens"] = {
        "input": sum(e["tokens"]["input"]
                     for e in report["accounting"]["ops"].values()),
        "output": sum(e["tokens"]["output"]
                      for e in report["accounting"]["ops"].values())}
    report["accounting"]["totals"] = totals
    report["releases"] = _maybe_release(
        dsn, artifacts_root=roots, allocation_id=allocation_id,
        investigation_id=investigation_id, protocol_prefix=protocol_prefix,
        evaluator_version=evaluator_version, simulated=simulated,
        protocols=protocols, group_candidate=group_candidate,
        group_families=group_families, verdicts=report["verdicts"])
    return report


def _run_noop_ablation(dsn: str, *, launcher: Any, roots: Path, task: dict,
                       group: str, tag: str, allocation_id: str,
                       attempt_id: str, grader_path: str, protocols: dict,
                       noop_version: str, report: dict) -> None:
    capability = capabilities.get_version(dsn, noop_version)
    noop_fixed, _ = _invoke_method(dsn, launcher, roots, capability,
                                   task["broken"], f"{tag}-noop",
                                   allocation_id, attempt_id)
    noop_invoke_op = f"invoke-{tag}-noop"
    noop_op, noop_staged = _prepare_grade(dsn, launcher, noop_fixed,
                                          task["cases"], f"{tag}-noop",
                                          allocation_id, attempt_id,
                                          grader_path)
    noop_outcome = _dispatch_grade(dsn, launcher, noop_op, len(task["cases"]),
                                   noop_staged)
    noop_invoke_entry = _settle_costs(dsn, [protocols[f"{group}-C"]],
                                      noop_invoke_op, "use",
                                      f"method invocation noop {task['id']}")
    report["accounting"]["ops"][noop_invoke_op] = {
        **noop_invoke_entry, "arm": "C", "kind": "invoke",
        "task_id": task["id"]}
    noop_grade_entry = _settle_costs(
        dsn, [protocols[f"{group}-C"]], noop_op,
        "evaluation" if noop_outcome == "success" else "failed_trials",
        f"grade {tag}-noop")
    report["accounting"]["ops"][noop_op] = {
        **noop_grade_entry, "arm": "C", "kind": "grade",
        "task_id": task["id"]}
    report["ablation_noop"][task["id"]] = {"invoke_op": noop_invoke_op,
                                           "grade_op": noop_op,
                                           "outcome": noop_outcome}


def _open_assignment(dsn: str, protocol_id: str, task: dict, group: str,
                     harness_arm: str, code: str, tag: str,
                     evaluator_id: str, evaluator_version: str,
                     op_id: str, *, executable_digest: str = "",
                     input_digest: str = "",
                     method: dict | None = None) -> str:
    arm = "candidate" if harness_arm in ("B", "C") else "reference"
    assignment_id = f"{protocol_id}:{arm}:{task['id']}"
    trials.assign(dsn, Command(request_id=f"{tag}-assign"), protocol_id,
                  task["id"], group, arm, {"entry_fn": task["entry_fn"]})
    content = {"code": code}
    if method is not None:
        content["method"] = method
    evaluation.submit_candidate(dsn, Command(request_id=f"{tag}-cand"),
                                assignment_id, content)
    evaluation.bind_evaluation(
        dsn, Command(request_id=f"{tag}-bind"), assignment_id,
        candidate_digest=payload_digest(content),
        evaluator_id=evaluator_id, evaluator_version=evaluator_version,
        invocation_ref=op_id, executable_digest=executable_digest,
        input_digest=input_digest)
    return assignment_id


def _close_assignment(dsn: str, assignment_id: str, task: dict, op_id: str,
                      outcome: str, tag: str, evaluator_id: str,
                      evaluator_version: str, simulated: bool,
                      conditions: dict | None = None,
                      cost: dict | None = None,
                      retention: dict | None = None) -> None:
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-receipt"), receipt_id=f"eval-{tag}",
        assignment_id=assignment_id, evaluator_id=evaluator_id,
        evaluator_version=evaluator_version, invocation_ref=op_id,
        result={"outcome": outcome,
                "detail": {"task_id": task["id"], **(retention or {})},
                "conditions": conditions or {}, "cost": cost or {},
                "simulated": simulated})
