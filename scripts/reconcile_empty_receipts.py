"""M0 reconciliation lever for the seven live operations without settled receipts.

Reads only the frozen live bundle. Distinguishes never-sent preparation,
observed provider failure, unknown response, receipt-admission refusal and
export omission from surviving source records. Writes a separate supplement
and never modifies the original evidence bytes.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SETTLED = ("success", "failure")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(bundle: Path, name: str):
    return json.loads((bundle / ("%s.json" % name)).read_text())


def _claimed_ops(bundle: Path) -> dict:
    claimed: dict[str, list[str]] = {}
    for episode in _load(bundle, "development"):
        for op_id in episode.get("operations", []) or []:
            claimed.setdefault(op_id, []).append(
                "development:%s" % episode.get("episode_id", "?"))
    for arm, entry in _load(bundle, "construction").items():
        if isinstance(entry, dict):
            for op_id in entry.get("operations", []) or []:
                claimed.setdefault(op_id, []).append("construction:%s" % arm)
    for episode in _load(bundle, "assessment"):
        for op_id in episode.get("operations", []) or []:
            claimed.setdefault(op_id, []).append(
                "assessment:%s" % episode.get("episode_id", "?"))
    for record in _load(bundle, "use_records"):
        if isinstance(record, dict):
            for op_id in record.get("operation_ids", []) or []:
                claimed.setdefault(op_id, []).append(
                    "use:%s" % record.get("record_id", "?"))
    return claimed


def _reasons(bundle: Path) -> dict:
    reasons: dict[str, str] = {}
    for episode in _load(bundle, "development"):
        for op_id in episode.get("operations", []) or []:
            reasons[op_id] = "disposition=%s status=%s" % (
                episode.get("dispositions", "?"), episode.get("status", "?"))
    for arm, entry in _load(bundle, "construction").items():
        if isinstance(entry, dict):
            for op_id in entry.get("operations", []) or []:
                reasons[op_id] = "arm=%s status=%s reason=%s" % (
                    arm, entry.get("status", "?"), entry.get("reason", ""))
    for episode in _load(bundle, "assessment"):
        for op_id in episode.get("operations", []) or []:
            reasons[op_id] = "assessment status=%s" % episode.get(
                "status", "?")
    return reasons


def reconcile(bundle: Path) -> dict:
    files = ("freeze", "development", "construction", "assessment",
             "use_records", "operations", "accounting",
             "refusal_probes", "conformance_replay")
    digests = {name: _sha(bundle / ("%s.json" % name)) for name in files}
    operations = _load(bundle, "operations")
    claimed = _claimed_ops(bundle)
    reasons = _reasons(bundle)
    buckets: dict[str, list[dict]] = {
        "never-sent preparation": [],
        "observed provider failure": [],
        "unknown response": [],
        "receipt-admission refusal": [],
        "export omission": [],
    }
    for op_id in sorted(claimed):
        row = operations.get(op_id)
        entry = {"operation_id": op_id, "claimed_by": claimed[op_id],
                 "context": reasons.get(op_id, "")}
        if row is None:
            entry["evidence"] = "claimed but absent from operations map"
            buckets["export omission"].append(entry)
            continue
        receipts = row.get("receipts", []) if isinstance(row, dict) else []
        settled = [r for r in receipts if isinstance(r, dict)
                   and r.get("outcome") in SETTLED]
        if settled:
            continue
        if not receipts:
            entry["evidence"] = ("exported with zero receipts; surviving bundle"
                                 " cannot separate never-dispatched from refused"
                                 " admission, live store is dropped")
            buckets["never-sent preparation"].append(entry)
            continue
        outcomes = sorted({r.get("outcome") for r in receipts
                           if isinstance(r, dict)})
        entry["evidence"] = ("exported with %d receipt(s), outcomes=%s, none"
                             " settled; raw provider bytes unavailable, live"
                             " store is dropped" % (len(receipts), outcomes))
        entry["receipt_identities"] = [r.get("receipt_identity") for r in receipts
                                       if isinstance(r, dict)]
        buckets["unknown response"].append(entry)
    return {"bundle": str(bundle), "bundle_sha256": digests,
            "settled_outcomes": list(SETTLED),
            "buckets": buckets,
            "counts": {key: len(value) for key, value in buckets.items()},
            "limits": [
                "receipt-admission refusal leaves no export trace and is"
                " undetectable from the bundle alone; count 0 means none"
                " observed, not none occurred",
                "unknown response cannot be split into timeout, empty"
                " completion or transport failure: the export slim usage"
                " carries no error text and the live store is dropped",
                "never-sent preparation with zero receipts cannot be split"
                " from admission refusal without the durable journal",
            ]}


def main(argv: list | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 2:
        print("usage: reconcile_empty_receipts.py <bundle-dir> <supplement-out>",
              file=sys.stderr)
        return 2
    bundle = Path(args[0])
    out = Path(args[1])
    result = reconcile(bundle)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, sort_keys=True, indent=1) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
