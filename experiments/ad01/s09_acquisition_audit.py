"""Recompute the recorded live-acquisition result from committed evidence.

Stage 9 M3's live-acquisition result is a negative: of 24 sealed use
records, 16 are `arm-unavailable` and none shows model acquisition. A
harness defect was found and fixed at `ca5aa74`, where the S09 pilot built
its gateway adapter without a route contract and every request was refused
before dispatch. All three arms are available under the fixed harness.

That makes the recorded negative a harness artifact rather than a
capability result, which means the committed evidence has to be read
before anything is re-derived, and read for what it can actually support.

This module recomputes the record-level census from the committed bytes
and answers a three-way question: is the recorded negative a harness
artifact, a genuine capability result, or undecidable on this evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

EVIDENCE = Path(__file__).resolve().parents[2] / "evidence_s09_live_opus"

HARNESS_ARTIFACT = "harness-artifact"
CAPABILITY_RESULT = "capability-result"
UNDECIDABLE = "undecidable"

# The fix that established the harness explanation, for the record.
GATEWAY_FIX_COMMIT = "ca5aa74"


def _load(name: str) -> Any:
    return json.loads((EVIDENCE / name).read_text())


def domain_of(record: Mapping[str, Any]) -> str:
    declared = record.get("domain")
    if declared:
        return str(declared)
    task_id = str(record.get("task_id", ""))
    return "graph" if "-gr-" in task_id else "software"


def census() -> dict[str, Any]:
    """Recompute the record-level census from the committed bytes."""
    records = _load("use_records.json")
    by_domain: dict[str, dict[str, int]] = {}
    by_arm: dict[str, dict[str, int]] = {}
    executed, unavailable, preserved = [], [], []
    for record in records:
        domain = domain_of(record)
        verdict = str(record.get("verdict"))
        by_domain.setdefault(domain, {}).setdefault(verdict, 0)
        by_domain[domain][verdict] += 1
        by_arm.setdefault(str(record.get("arm")), {}).setdefault(verdict, 0)
        by_arm[str(record.get("arm"))][verdict] += 1
        if record.get("fallback_reason"):
            unavailable.append(record)
        else:
            preserved.append(record)
        if record.get("executed_source") not in ("incumbent", "", None):
            executed.append(record)
    return {
        "record_count": len(records),
        "by_domain": by_domain,
        "by_arm": by_arm,
        "unavailable": len(unavailable),
        "preserved": len(preserved),
        "executed": len(executed),
        "executed_digests": sorted({
            str(r.get("executed_source_digest")) for r in executed}),
    }


def digest_integrity() -> dict[str, Any]:
    """Whether every record that ran bytes names exactly those bytes."""
    records = _load("use_records.json")
    verified, unverifiable = [], []
    for record in records:
        source = record.get("executed_source")
        digest = record.get("executed_source_digest")
        if source in ("incumbent", "", None) or not digest:
            unverifiable.append(str(record.get("record_id")))
            continue
        computed = hashlib.sha256(str(source).encode()).hexdigest()
        if computed == digest:
            verified.append(str(record.get("record_id")))
        else:
            unverifiable.append("%s MISMATCH" % record.get("record_id"))
    return {"verified": len(verified), "unverifiable": unverifiable}


def unknown_outcome_operations() -> dict[str, Any]:
    """Model-inference receipts that carry no response at all.

    `outcome` of `unknown` with entirely null usage is the only trace a
    request that never came back leaves. There is no `response_received`
    field and no `response_digest`, so the evidence records *that* a
    response is missing and not *why*, which is the whole question.
    """
    operations = _load("operations.json")
    unknown, success = [], []
    for operation_id, record in operations.items():
        for receipt in record.get("receipts") or []:
            if record.get("effect") != "model-inference":
                continue
            entry = {"operation_id": operation_id,
                     "outcome": receipt.get("outcome"),
                     "usage": receipt.get("usage")}
            (unknown if receipt.get("outcome") == "unknown"
             else success).append(entry)
    fields = set()
    for record in operations.values():
        for receipt in record.get("receipts") or []:
            fields |= set(receipt)
    return {
        "unknown": unknown,
        "success": success,
        "receipt_fields": sorted(fields),
        "records_response_received": "response_received" in fields,
        "records_response_digest": "response_digest" in fields,
    }


def acquisition_possible() -> dict[str, Any]:
    """Whether any record shows a model actually producing a policy."""
    records = _load("use_records.json")
    acquired = []
    for record in records:
        costs = record.get("costs") or {}
        if (record.get("executed_source") not in ("incumbent", "", None)
                and int(costs.get("model_calls", 0) or 0) > 0):
            acquired.append(str(record.get("record_id")))
    return {"records_showing_model_acquisition": acquired,
            "count": len(acquired)}


def freeze_digest_discrepancy() -> dict[str, Any]:
    """The one discrepancy I could not resolve earlier."""
    freeze = _load("freeze.json")
    records = _load("use_records.json")
    committed = freeze.get("freeze_digest")
    carried = sorted({str(r.get("freeze_digest")) for r in records
                      if r.get("freeze_digest")})
    return {
        "freeze_json_digest": committed,
        "record_digests": carried,
        "agree": carried == [committed],
        "status": "UNVERIFIED" if carried != [committed] else "CONFIRMED",
        "note": ("the records name a freeze digest the committed freeze.json "
                 "does not carry; the artifacts cannot distinguish a subset "
                 "digest from a stale freeze"),
    }


def verdict() -> dict[str, Any]:
    """The three-way answer, with the evidence that produced it."""
    counts = census()
    unknown = unknown_outcome_operations()
    acquired = acquisition_possible()
    integrity = digest_integrity()

    reasons = []
    reasons.append(
        "%d of %d records are unavailable and %d executed program bytes"
        % (counts["unavailable"], counts["record_count"], counts["executed"]))
    reasons.append(
        "%d records show a model producing a policy"
        % acquired["count"])
    reasons.append(
        "%d model-inference receipts are outcome=unknown with null usage"
        % len(unknown["unknown"]))
    reasons.append(
        "receipts record %s"
        % ("response_received" if unknown["records_response_received"]
           else "no response_received field")
        + (" and a response digest"
           if unknown["records_response_digest"]
           else " and no response digest"))

    if acquired["count"] > 0:
        outcome = CAPABILITY_RESULT
    elif unknown["unknown"] and not unknown["records_response_received"]:
        outcome = UNDECIDABLE
    else:
        outcome = HARNESS_ARTIFACT

    return {
        "outcome": outcome,
        "reasons": reasons,
        "census": counts,
        "digest_integrity": integrity,
        "unknown_operations": {
            "count": len(unknown["unknown"]),
            "receipt_fields": unknown["receipt_fields"],
        },
        "acquisition": acquired,
        "freeze_digest": freeze_digest_discrepancy(),
        "harness_fix_commit": GATEWAY_FIX_COMMIT,
        "recorded_run_preceded_the_fix": True,
        "conclusion": (
            "The recorded negative cannot be a capability result, because no "
            "record shows a model producing a policy at all. It also cannot be "
            "attributed to the route defect from these bytes alone: the only "
            "trace of the missing responses is outcome=unknown with null "
            "usage, and the receipts record neither whether a response was "
            "received nor a response digest, so a pre-dispatch refusal and a "
            "response that was lost in flight are indistinguishable here. The "
            "route defect is a confirmed, mechanically sufficient explanation "
            "for the controlled study, and the negative is void as a "
            "capability claim either way. Re-derivation against the fixed "
            "harness is required, and no re-run has happened."),
    }


def main(argv=None) -> int:
    print(json.dumps(verdict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
