"""Deterministic reconciliation checker for CLOSE-2 smoke bundles.

Reads a bundle JSON (smoke_close2.json shape) and verifies, over unique
operations only:
  1. each operation appears once (no double counting),
  2. settled + unresolved == reserved per operation,
  3. allocation consumed delta == settled sum over unique operations.

Exits 0 with a JSON verdict. Stdlib only; no live calls, no DB.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def check(bundle: dict) -> dict:
    accounting = bundle.get("accounting", {})
    seen: set[str] = set()
    duplicates: list[str] = []
    for op_id in accounting:
        if op_id in seen:
            duplicates.append(op_id)
        seen.add(op_id)
    per_op = {}
    parts_ok = True
    for op_id in sorted(seen):
        entry = accounting[op_id] or {}
        reserved = int(entry.get("reserved", 0) or 0)
        settled = int(entry.get("settled", 0) or 0)
        unresolved = int(entry.get("unresolved", 0) or 0)
        ok = settled + unresolved == reserved
        parts_ok = parts_ok and ok
        per_op[op_id] = {"reserved": reserved, "settled": settled,
                         "unresolved": unresolved, "parts_ok": ok}
    before = bundle.get("allocation_before") or {}
    after = bundle.get("allocation_after") or {}
    delta = int(after.get("consumed", 0) or 0) - int(
        before.get("consumed", 0) or 0)
    settled_sum = sum(v["settled"] for v in per_op.values())
    delta_ok = delta == settled_sum
    verdict = not duplicates and parts_ok and delta_ok
    return {"unique_operations": sorted(seen),
            "unique_operation_count": len(seen),
            "duplicates": duplicates, "per_operation": per_op,
            "parts_ok": parts_ok, "consumed_delta": delta,
            "settled_sum": settled_sum, "delta_ok": delta_ok,
            "reconciled": verdict}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: check_reconcile.py <bundle.json>")
    bundle = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = check(bundle)
    print(json.dumps(result, indent=2))
    return 0 if result["reconciled"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
