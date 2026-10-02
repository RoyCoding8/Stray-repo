"""Acquired methods run through the bounded local-process profile (BDR-01).

The host owns the query budget and exposes only JSON oracle verdicts.
Local-process provides process separation, not hostile-code containment.
"""

from __future__ import annotations

import ast
import hashlib
import json
import socket
import sys
import tempfile
import threading
from contextlib import nullcontext
from pathlib import Path

from experiments.representation import checkers
from settlement import broker
from settlement.common import ResultCode
from settlement.launcher_local import PROFILE, LocalLauncher

DEFAULT_TIMEOUT_MS = 30_000
MAX_FRAME_BYTES = 4 * 1024 * 1024

_FORBIDDEN_CALLS = frozenset([
    "open", "exec", "eval", "compile", "__import__", "input",
    "breakpoint", "exit", "quit", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir", "help", "type", "memoryview"])


class MethodExecutionError(Exception):
    pass


CHILD_CONTRACT_VERSION = "ad01-child-v1"


def child_contract() -> dict:
    return {
        "version": CHILD_CONTRACT_VERSION,
        "entry": entry_contract()["params"],
        "callables": {
            "reduce_software": {
                "signature": ("reduce_software(task, oracle, *, "
                              "method=\"ddmin\"|\"greedy\", "
                              "max_queries=16)"),
                "returns": ("dict with candidate (software-shaped) and "
                            "queries used"),
                "origin": "authored-supplied-rpr01",
                "binding": "reducers.reduce_software",
            },
            "reduce_graph": {
                "signature": ("reduce_graph(task, oracle, *, "
                              "method=\"ddmin\"|\"greedy\", "
                              "max_queries=16)"),
                "returns": ("dict with candidate (graph-shaped) and "
                            "queries used"),
                "origin": "authored-supplied-rpr01",
                "binding": "reducers.reduce_graph",
            },
            "oracle.query": {
                "signature": "oracle.query(candidate)",
                "returns": ("the verdict report for that candidate; "
                            "past the query budget it returns unknown "
                            "with reason budget-exhausted"),
                "origin": "host-oracle",
            },
        },
    }


def _child_wrapper_source() -> str:
    lines = []
    for name, spec in child_contract()["callables"].items():
        target = spec.get("binding")
        if target is None:
            continue
        lines.append(
            "def %s(task, oracle, *, method=\"ddmin\", max_queries=16):\n"
            "    return %s(task, oracle, method=method,"
            " max_queries=max_queries)" % (name, target))
    return "\n".join(lines) + "\n" if lines else ""


def _child_binding_source() -> str:
    return ("\n".join(
        "module.__dict__[%r] = %s" % (name, name)
        for name, spec in child_contract()["callables"].items()
        if spec.get("binding") is not None) + "\n")


def entry_contract() -> dict:
    return {
        "params": "ENTRY(task, oracle, max_queries=16)",
        "param_rule": ("the first two parameters must be named task and "
                       "oracle, at most three parameters in total, no "
                       "*args, **kwargs, or keyword-only parameters"),
        "result_envelope": {
            "shape": {"candidate": "candidate-shaped object",
                      "queries": "nonnegative integer"},
            "rule": ("the entry function must return its own result "
                     "envelope shaped {\"candidate\": <candidate-shaped "
                     "object>, \"queries\": <nonnegative integer of oracle "
                     "queries used>}; returning the candidate object "
                     "directly fails execution with "
                     "malformed-result-envelope"),
        },
        "forbidden": {
            "import_statements": "import statements fail validation",
            "dunder": ("attribute access starting with a single "
                       "underscore and variable names starting with a "
                       "double underscore fail validation"),
            "calls": sorted(_FORBIDDEN_CALLS),
        },
        "source_rule": ("non-empty python source that parses with exactly "
                        "one module-level function carrying the entry name"),
    }


def verify_member(member: dict) -> str:
    source = member.get("method_source")
    entry = member.get("entry")
    if not isinstance(source, str) or not source.strip():
        raise MethodExecutionError("refused: empty-method-source")
    if not isinstance(entry, str) or not entry:
        raise MethodExecutionError("refused: missing-entry")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        raise MethodExecutionError("refused: unparseable-python")
    targets = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == entry]
    if len(targets) != 1:
        raise MethodExecutionError("refused: missing-entry-function")
    params = list(targets[0].args.posonlyargs) + list(targets[0].args.args)
    names = [p.arg for p in params]
    if len(names) < 2 or names[0] != "task" or names[1] != "oracle" \
            or len(names) > 3 or targets[0].args.vararg is not None \
            or targets[0].args.kwarg is not None \
            or targets[0].args.kwonlyargs:
        raise MethodExecutionError("refused: entry-arity")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise MethodExecutionError("refused: imports-forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FORBIDDEN_CALLS:
            raise MethodExecutionError("refused: io-or-reflection-forbidden")
    return entry


_DRIVER = '''import importlib.util, json, socket, sys
work, sock_path, root = sys.argv[1:]
sys.path.insert(0, root)
from experiments.representation import reducers
__S89A1_WRAPPERS__spec = importlib.util.spec_from_file_location('acquired_member', work + '/member.py')
module = importlib.util.module_from_spec(spec)
module.__dict__['reducers'] = reducers
__S89A1_BINDINGS__class Proxy:
    def __init__(self):
        self._queries = 0
    def query(self, candidate):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as link:
            link.connect(chr(0) + sock_path)
            frame = json.dumps({'candidate': candidate}).encode()
            link.sendall(len(frame).to_bytes(4, 'big') + frame)
            size = int.from_bytes(read(link, 4), 'big')
            if size > 4194304:
                raise RuntimeError('oversize verdict')
            response = json.loads(read(link, size))
            self._queries = response['queries']
            return response['verdict']
def read(link, size):
    data = bytearray()
    while len(data) < size:
        chunk = link.recv(size - len(data))
        if not chunk:
            raise RuntimeError('oracle channel closed')
        data.extend(chunk)
    return bytes(data)
try:
    spec.loader.exec_module(module)
    envelope = json.load(open(work + '/task.json'))
    proxy = Proxy()
    _entry = getattr(module, %r)
    if %d == 3:
        out = _entry(envelope['task'], proxy, max_queries=envelope['max_queries'])
    else:
        out = _entry(envelope['task'], proxy)
    if not isinstance(out, dict) or not isinstance(out.get('candidate'), dict):
        print(json.dumps({'status': 'error', 'error': 'malformed-result-envelope: entry must return {"candidate": <candidate>, "queries": <int>}'}))
    else:
        print(json.dumps({'status': 'ok', 'data': {'candidate': out['candidate'], 'queries': proxy._queries}}))
except Exception as exc:
    print(json.dumps({'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)}))
'''

_DRIVER = _DRIVER.replace(
    "__S89A1_WRAPPERS__", _child_wrapper_source()).replace(
    "__S89A1_BINDINGS__", _child_binding_source())


def _read_exact(link, size: int) -> bytes:
    if size > MAX_FRAME_BYTES:
        raise ValueError("oversize-query")
    data = bytearray()
    while len(data) < size:
        piece = link.recv(size - len(data))
        if not piece:
            raise OSError("short frame")
        data.extend(piece)
    return bytes(data)


def _result(receipt: dict | None, member: dict, operation_id: str | None) -> dict:
    data = (receipt or {}).get("data", {})
    if receipt is None or receipt.get("outcome") != "success":
        raise MethodExecutionError("%s: %s" % (
            "timeout" if data.get("timed_out") else "member-failed", data))
    output = data.get("worker", {}).get("data", {})
    if not isinstance(output.get("candidate"), dict):
        raise MethodExecutionError("member-failed: malformed-result")
    return {"candidate": output["candidate"], "queries": output.get("queries", 0),
            "operation_id": operation_id, "operation_ids": [operation_id] if operation_id else [],
            "capability_id": member.get("capability_id", "")}


def run_member_out_of_process(member: dict, task: dict, *,
                              max_queries: int = 16,
                              timeout_ms: int = DEFAULT_TIMEOUT_MS,
                              dsn: str | None = None,
                              allocation_id: str | None = None,
                              operation_id: str | None = None) -> dict:
    entry = verify_member(member)
    if dsn is not None and (not allocation_id or not operation_id):
        raise MethodExecutionError("refused: execution needs explicit authority and identity")
    operation_id = operation_id or "member"
    argc = next(len(n.args.args) for n in ast.parse(
        member["method_source"]).body
        if isinstance(n, ast.FunctionDef) and n.name == entry)
    oracle_type = checkers.GraphOracle if task.get("family") == "graph" else checkers.SoftwareOracle
    oracle = oracle_type(task, max_queries=max_queries)
    root = str(Path(__file__).resolve().parent.parent.parent)
    generation = None
    if dsn is not None:
        from settlement import db
        with db.connect(dsn) as conn:
            allocation = conn.execute("SELECT created_at FROM allocations WHERE id = %s",
                                      (allocation_id,)).fetchone()
        if allocation is None:
            raise MethodExecutionError("refused: unknown allocation")
        generation = str(allocation[0])
    identity = hashlib.sha256(json.dumps(
        [dsn, allocation_id, generation, operation_id, member, task, max_queries, timeout_ms, _DRIVER],
        sort_keys=True).encode()).hexdigest()
    directory = Path(root) / ".ad01-runs" / identity
    context = nullcontext(directory) if dsn else tempfile.TemporaryDirectory(prefix="ad01-")
    with context as directory:
        work = Path(directory)
        work.mkdir(parents=True, exist_ok=True)
        (work / "member.py").write_text(member["method_source"])
        (work / "task.json").write_text(json.dumps({"task": task, "max_queries": max_queries}))
        driver = work / "driver.py"
        driver.write_text(_DRIVER % (entry, argc))
        socket_path = "ad01-" + hashlib.sha256(str(work).encode()).hexdigest()
        launcher = LocalLauncher(work / "launcher")
        payload = {"profile": PROFILE, "argv": [sys.executable, str(driver), str(work),
                   str(socket_path), root], "timeout_ms": timeout_ms}
        if dsn is not None:
            ensured = broker.ensure_operation(
                dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                payload=payload, allocation_id=allocation_id)
            if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise MethodExecutionError("refused: %s" % ensured.detail)
            from settlement import db
            with db.connect(dsn) as conn:
                row = conn.execute(
                    "SELECT outcome, content FROM receipts WHERE operation_id = %s"
                    " ORDER BY receipt_identity LIMIT 1", (operation_id,)).fetchone()
            if row is not None:
                return _result({**row[1], "outcome": row[0]}, member, operation_id)
        stopped = threading.Event()
        errors = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(chr(0) + socket_path)
            server.listen(1)
            server.settimeout(0.1)

            def serve():
                try:
                    while not stopped.is_set():
                        try:
                            link, _ = server.accept()
                        except socket.timeout:
                            continue
                        with link:
                            link.settimeout(0.1)
                            size = int.from_bytes(_read_exact(link, 4), "big")
                            message = json.loads(_read_exact(link, size))
                            if not isinstance(message, dict) or set(message) != {"candidate"} \
                                    or not isinstance(message["candidate"], dict):
                                raise ValueError("query-needs-candidate")
                            verdict = oracle.query(message["candidate"])
                            reply = json.dumps({"verdict": verdict,
                                                "queries": oracle.queries_used}).encode()
                            link.sendall(len(reply).to_bytes(4, "big") + reply)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append(str(exc))

            host = threading.Thread(target=serve)
            host.start()
            try:
                if dsn is None:
                    launcher.dispatch(broker.BrokerOp(
                        operation_id=operation_id, effect=broker.SANDBOX_EXEC, payload=payload))
                else:
                    broker.dispatch_operation(dsn, operation_id, launchers={PROFILE: launcher})
            finally:
                stopped.set()
                host.join()
        receipt = launcher.read_result(operation_id)
        if errors:
            raise MethodExecutionError("bad-frame: %s" % errors[0])
        result = _result(receipt, member, operation_id if dsn else None)
        result["queries"] = oracle.queries_used
        return result


STEP_TIMEOUT_MS = 10_000
STEP_CPU_SECONDS = 10
STEP_MAX_OUTPUT_BYTES = 65_536


def step_contract() -> dict:
    from . import policy_step
    return {
        "version": policy_step.POLICY_STEP_VERSION,
        "entry": "%s(view, state)" % policy_step.STEP_ENTRY,
        "param_rule": ("the two parameters must be named view and state,"
                       " no *args, **kwargs, or keyword-only parameters"),
        "result_envelope": {
            "shape": {"action": "policy action object",
                      "state": "bounded JSON object"},
            "rule": ("the entry function must return its own result"
                     " envelope shaped {\"action\": <policy action object>,"
                     " \"state\": <bounded JSON object>}; anything else"
                     " fails execution with malformed-step-envelope"),
        },
        "forbidden": entry_contract()["forbidden"],
        "source_rule": ("non-empty python source that parses with exactly"
                        " one module-level function carrying the entry name"),
        "limits": {"cpu_seconds": STEP_CPU_SECONDS,
                   "wall_ms": STEP_TIMEOUT_MS,
                   "output_bytes": STEP_MAX_OUTPUT_BYTES,
                   "state_bytes": policy_step.STATE_LIMIT_BYTES},
    }


def verify_step_source(source: str, entry: str = "STEP") -> str:
    if not isinstance(source, str) or not source.strip():
        raise MethodExecutionError("refused: empty-policy-source")
    if not isinstance(entry, str) or not entry:
        raise MethodExecutionError("refused: missing-entry")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        raise MethodExecutionError("refused: unparseable-python")
    targets = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == entry]
    if len(targets) != 1:
        raise MethodExecutionError("refused: missing-entry-function")
    params = list(targets[0].args.posonlyargs) + list(targets[0].args.args)
    names = [p.arg for p in params]
    if names != ["view", "state"] \
            or targets[0].args.vararg is not None \
            or targets[0].args.kwarg is not None \
            or targets[0].args.kwonlyargs:
        raise MethodExecutionError("refused: entry-arity")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise MethodExecutionError("refused: imports-forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FORBIDDEN_CALLS:
            raise MethodExecutionError("refused: io-or-reflection-forbidden")
    return entry


_STEP_DRIVER = '''import importlib.util, json, sys
work = sys.argv[1]
__STEP_POLICY__spec = importlib.util.spec_from_file_location('acquired_policy', work + '/policy.py')
module = importlib.util.module_from_spec(__STEP_POLICY__spec)
try:
    __STEP_POLICY__spec.loader.exec_module(module)
    payload = json.load(open(work + '/step.json'))
    _entry = getattr(module, %r)
    out = _entry(payload['view'], payload['state'])
    if not isinstance(out, dict) or not isinstance(out.get('action'), dict) \\
            or not isinstance(out.get('state'), dict):
        print(json.dumps({'status': 'error', 'error': 'malformed-step-envelope: STEP must return {"action": <action object>, "state": <object>}'}))
    else:
        print(json.dumps({'status': 'ok', 'data': {'action': out['action'], 'state': out['state']}}))
except Exception as exc:
    print(json.dumps({'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)}))
'''


def _step_result(receipt: dict | None, operation_id: str | None) -> dict:
    from . import policy_step
    data = (receipt or {}).get("data", {})
    if receipt is None or receipt.get("outcome") != "success":
        raise MethodExecutionError("%s: %s" % (
            "timeout" if data.get("timed_out") else "step-failed", data))
    output = data.get("worker", {}).get("data", {})
    if not isinstance(output.get("action"), dict) \
            or not isinstance(output.get("state"), dict):
        raise MethodExecutionError(
            "step-failed: malformed-step-envelope")
    try:
        policy_step.validate_step_result(
            {"action": output["action"], "state": output["state"]})
    except ValueError as exc:
        raise MethodExecutionError("step-failed: refused: %s" % exc)
    return {"action": output["action"], "state": output["state"],
            "operation_id": operation_id,
            "operation_ids": [operation_id] if operation_id else []}


def run_step_out_of_process(source: str, view: dict, state: dict, *,
                            entry: str = "STEP",
                            timeout_ms: int = STEP_TIMEOUT_MS,
                            cpu_seconds: int = STEP_CPU_SECONDS,
                            max_output_bytes: int = STEP_MAX_OUTPUT_BYTES,
                            memory_bytes: int | None = None,
                            dsn: str | None = None,
                            allocation_id: str | None = None,
                            operation_id: str | None = None) -> dict:
    from . import policy_step
    entry = verify_step_source(source, entry)
    policy_step.validate_view(view)
    policy_step.validate_state(state)
    if dsn is not None and (not allocation_id or not operation_id):
        raise MethodExecutionError(
            "refused: execution needs explicit authority and identity")
    operation_id = operation_id or "step"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    root = str(Path(__file__).resolve().parent.parent.parent)
    generation = None
    if dsn is not None:
        from settlement import db
        with db.connect(dsn) as conn:
            allocation = conn.execute(
                "SELECT created_at FROM allocations WHERE id = %s",
                (allocation_id,)).fetchone()
        if allocation is None:
            raise MethodExecutionError("refused: unknown allocation")
        generation = str(allocation[0])
    identity = hashlib.sha256(json.dumps(
        [dsn, allocation_id, generation, operation_id, digest, view,
         state, timeout_ms, cpu_seconds, max_output_bytes, memory_bytes,
         _STEP_DRIVER],
        sort_keys=True).encode()).hexdigest()
    directory = Path(root) / ".ad01-runs" / identity
    context = nullcontext(directory) if dsn else tempfile.TemporaryDirectory(prefix="ad01-step-")
    with context as directory:
        work = Path(directory)
        work.mkdir(parents=True, exist_ok=True)
        (work / "policy.py").write_text(source)
        (work / "step.json").write_text(json.dumps(
            {"view": view, "state": state}))
        driver = work / "driver.py"
        driver.write_text(_STEP_DRIVER % (entry,))
        launcher = LocalLauncher(work / "launcher")
        payload = {"profile": PROFILE, "argv": [sys.executable, str(driver), str(work)],
                   "timeout_ms": timeout_ms,
                   "max_output_bytes": max_output_bytes,
                   "cpu_seconds": cpu_seconds,
                   "memory_bytes": memory_bytes}
        if dsn is not None:
            ensured = broker.ensure_operation(
                dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                payload=payload, allocation_id=allocation_id)
            if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise MethodExecutionError("refused: %s" % ensured.detail)
            from settlement import db
            with db.connect(dsn) as conn:
                row = conn.execute(
                    "SELECT outcome, content FROM receipts WHERE operation_id = %s"
                    " ORDER BY receipt_identity LIMIT 1", (operation_id,)).fetchone()
            if row is not None:
                return {**_step_result({**row[1], "outcome": row[0]}, operation_id),
                        "source_digest": digest}
            broker.dispatch_operation(dsn, operation_id, launchers={PROFILE: launcher})
        else:
            launcher.dispatch(broker.BrokerOp(
                operation_id=operation_id, effect=broker.SANDBOX_EXEC, payload=payload))
        receipt = launcher.read_result(operation_id)
        return {**_step_result(receipt, operation_id if dsn else None),
                "source_digest": digest}
