"""Evaluator-side hidden-test grader. Runs inside the sandbox worker process.

Usage: run_tests.py <candidate.py> <cases.json>. Prints one typed-JSON line:
``{"status": "ok", "data": {"passed": n, "failed": m, "failures": [...]}}``.
Any load error prints ``{"status": "error", ...}``. Importing the candidate
here is safe: this process is the untrusted worker, not the controller.
"""

from __future__ import annotations

import importlib.util
import json
import sys


def _close(actual, expected) -> bool:
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(actual) - float(expected)) < 1e-9
        except (TypeError, ValueError):
            return False
    return actual == expected


def main(argv: list[str]) -> int:
    candidate_path, cases_path = argv[0], argv[1]
    try:
        with open(cases_path, encoding="utf-8") as handle:
            cases = json.load(handle)
        spec = importlib.util.spec_from_file_location("candidate", candidate_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "data": {"passed": 0, "failed": 0},
                          "error": f"load failed: {exc}"}))
        return 0
    passed, failures = 0, []
    for case in cases:
        try:
            actual = getattr(module, case["fn"])(*case["args"])
            if _close(actual, case["expected"]):
                passed += 1
            else:
                failures.append({"case": case, "actual": actual})
        except Exception as exc:  # noqa: BLE001
            failures.append({"case": case, "actual": f"raised {exc!r}"})
    print(json.dumps({"status": "ok",
                      "data": {"passed": passed, "failed": len(failures),
                               "failures": failures}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
