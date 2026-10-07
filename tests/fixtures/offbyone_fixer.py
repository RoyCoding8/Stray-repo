"""Retained executable method for fault family ``off_by_one``.

Reads a broken Python file, applies bound-inclusion rewrites, writes the
repaired file, and reports typed JSON. Knows nothing about hidden tests.
"""

from __future__ import annotations

import json
import sys

REWRITES = [
    ("range(n)", "range(n + 1)"),
    ("range(1, n)", "range(1, n + 1)"),
    ("while i < n:", "while i <= n:"),
]

SELFTEST_BROKEN = "def f(n):\n    return sum(range(n))\n"


def repair(source: str) -> tuple[str, list[str]]:
    applied = []
    for old, new in REWRITES:
        if old in source:
            source = source.replace(old, new)
            applied.append(f"{old} -> {new}")
    return source, applied


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        fixed, applied = repair(SELFTEST_BROKEN)
        ok = "range(n + 1)" in fixed and applied
        print(json.dumps({"status": "ok" if ok else "error",
                          "data": {"applied": applied}}))
        return 0 if ok else 1
    if len(argv) != 2:
        print(json.dumps({"status": "error", "data": {},
                          "error": "need [input output]"}))
        return 2
    with open(argv[0], encoding="utf-8") as handle:
        source = handle.read()
    fixed, applied = repair(source)
    with open(argv[1], "w", encoding="utf-8") as handle:
        handle.write(fixed)
    print(json.dumps({"status": "ok", "data": {"applied": applied}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
