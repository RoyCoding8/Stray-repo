"""Evaluator-side hidden-test grader. Runs inside the sandbox worker process.

Usage: run_tests.py <candidate.py> <cases.json> [budget_ms]. Prints one typed-JSON line:
``{"status": "ok", "data": {"passed": n, "failed": m, "total": t, "failures": [...]}}``.
Any load error prints ``{"status": "error", ...}``.

Candidate code NEVER runs in this process. Each case executes in a transient
child process that receives only that case's function name and arguments over
stdin. That child runs isolated (`-I -S`, scrubbed environment, private working
directory) on the bare interpreter and standard library, so neither repository
files nor host site-packages (editable installs included) are importable. The
cases file is removed
after loading, candidate stdout is captured rather than trusted, and the
evaluator compares actuals against expected values itself before owning this
receipt.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

DEFAULT_BUDGET_MS = 25_000.0


def _child_env() -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "LANG": os.environ.get("LANG", "C.UTF-8"),
           "PYTHONSAFEPATH": "1"}
    return env

_RUNNER = """
import importlib.util as _ilu
import io as _io
import json as _json
import sys as _sys

def _run():
    req = _json.load(_sys.stdin)
    buf_out, buf_err = _io.StringIO(), _io.StringIO()
    _sys.stdout, _sys.stderr = buf_out, buf_err
    try:
        spec = _ilu.spec_from_file_location("candidate_case", req["path"])
        module = _ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        actual = getattr(module, req["fn"])(*req["args"])
        try:
            _json.dumps(actual)
        except (TypeError, ValueError):
            raise TypeError(f"non-serializable result {type(actual).__name__}")
        envelope = {"status": "ok", "actual": actual}
    except BaseException as exc:
        envelope = {"status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "captured": (buf_out.getvalue() + buf_err.getvalue())[-2000:]}
    finally:
        _sys.stdout, _sys.stderr = _sys.__stdout__, _sys.__stderr__
    _sys.stdout.write(_json.dumps(envelope) + "\\n")

_run()
"""


def _close(actual, expected) -> bool:
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(actual) - float(expected)) < 1e-9
        except (TypeError, ValueError):
            return False
    return actual == expected


def _probe(candidate_path: str, case: dict, timeout_s: float,
           child_cwd: str, child_env: dict[str, str]) -> dict:
    req = json.dumps({"path": candidate_path, "fn": case["fn"], "args": case["args"]})
    try:
        proc = subprocess.run([sys.executable, "-I", "-S", "-c", _RUNNER],
                              input=req,
                              capture_output=True, text=True, timeout=timeout_s,
                              cwd=child_cwd, env=child_env)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "candidate exceeded per-case budget"}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"status": "error",
                "error": f"candidate exited {proc.returncode}: {(proc.stderr or '')[-500:]}"}
    try:
        envelope = json.loads(proc.stdout)
    except ValueError:
        return {"status": "error", "error": "unparseable candidate channel output"}
    if not isinstance(envelope, dict) or "status" not in envelope:
        return {"status": "error", "error": "malformed candidate envelope"}
    return envelope


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: run_tests.py <candidate.py> <cases.json> [budget_ms]",
              file=sys.stderr)
        return 2
    candidate_path, cases_path = argv[0], argv[1]
    try:
        budget_ms = float(argv[2]) if len(argv) > 2 else DEFAULT_BUDGET_MS
    except ValueError:
        print(f"run_tests refused: budget {argv[2]!r} is not a number",
              file=sys.stderr)
        return 2
    try:
        with open(cases_path, encoding="utf-8") as handle:
            cases = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "data": {"passed": 0, "failed": 0,
                          "total": 0, "failures": []},
                          "error": f"load failed: {exc}"}))
        return 0
    try:
        os.unlink(cases_path)
    except OSError:
        pass
    deadline = time.monotonic() + max(1.0, budget_ms / 1000.0)
    child_cwd = tempfile.mkdtemp(prefix="grader-child-")
    child_env = _child_env()
    passed, failures = 0, []
    for idx, case in enumerate(cases):
        timeout_s = max(0.5, (deadline - time.monotonic() - 0.5) / (len(cases) - idx))
        result = _probe(candidate_path, case, timeout_s, child_cwd, child_env)
        if result.get("status") == "ok" and _close(result.get("actual"), case["expected"]):
            passed += 1
        else:
            failures.append({"case": case,
                             "actual": result.get("actual", result.get("error",
                                                                       result.get("status")))})
    print(json.dumps({"status": "ok",
                      "data": {"passed": passed, "failed": len(failures),
                               "total": len(cases), "failures": failures}}))
    shutil.rmtree(child_cwd, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
