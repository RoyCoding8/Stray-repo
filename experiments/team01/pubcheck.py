"""Public-case tool runner for the live solver loop.

Standalone (no repository imports): executed inside a broker-routed
sandbox operation with argv [tree_dir, cases_json]. Prints one worker
envelope line: {"status": "ok"|"error", "data": {passed, failed, total,
failures: [{input, expected, got}]}, "error": ""}. Failures are capped so
receipts stay small.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_FAILURES = 5
TIMEOUT_S = 20


def _emit(status: str, data: dict, error: str = "") -> None:
    print(json.dumps({"status": status, "data": data, "error": error}))


def main(argv: list) -> int:
    tree = Path(argv[1])
    try:
        cases = json.loads(Path(argv[2]).read_text())
    except (ValueError, OSError) as exc:
        _emit("error", {"passed": 0, "failed": 0, "total": 0,
                        "failures": []}, "bad cases file: %s" % exc)
        return 0
    if not isinstance(cases, list):
        _emit("error", {"passed": 0, "failed": 0, "total": 0,
                        "failures": []}, "cases file is not a list")
        return 0
    app = tree / "src" / "app.py"
    passed, failures = 0, []
    total = len(cases)
    for case in cases:
        got = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                req = Path(tmp) / "req.json"
                resp = Path(tmp) / "resp.json"
                req.write_text(json.dumps(case["input"]))
                proc = subprocess.run(
                    [sys.executable, str(app), str(req), str(resp)],
                    capture_output=True, text=True, timeout=TIMEOUT_S)
                if proc.returncode == 0 and resp.exists():
                    got = json.loads(resp.read_text())
        except Exception as exc:  # noqa: BLE001 - tool must not crash
            got = {"tool_error": str(exc)[:200]}
        if got == case.get("expected"):
            passed += 1
        elif len(failures) < MAX_FAILURES:
            failures.append({"input": case.get("input"),
                             "expected": case.get("expected"), "got": got})
    _emit("ok", {"passed": passed, "failed": total - passed,
                  "total": total, "failures": failures})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
