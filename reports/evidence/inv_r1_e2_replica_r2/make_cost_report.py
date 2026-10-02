"""Cost the E2 re-run in the four currencies the campaign keeps apart.

The four are not the same number, and a run that reports one of them as if it
were another is the ledger failure this campaign has already paid for once.
Every figure here is read from the durable store after the run rather than
predicted before it, so a process that died mid-dispatch cannot report a
number it never spent.

    dispatch allowance      physical sends, counted from the operations table
                            against the cap sheet's ceiling
    internal reservation   the broker's own estimated-budget units, from the
                            reservation rows tied to each operation
    provider billing        what the gateway reported per receipt, classified
                            REPORTED / NOT_REPORTED / UNMEASURED, with a lost
                            response counted as UNCERTAIN and never as zero
    held units              what the study still holds against its
                            authorization, which is not what it spent

Run with the disposable store's DSN. This module never creates or drops a
database.
"""

from __future__ import annotations

import json
import sys

OPERATIONS = """
    SELECT o.id AS operation_id, o.dispatch_state, o.settled,
           o.payload->>'effect' AS effect,
           r.receipt_identity, r.outcome, r.provenance,
           r.content->>'response_class' AS response_class,
           r.content->'usage' AS usage
    FROM operations o
    LEFT JOIN receipts r ON r.operation_id = o.id
    ORDER BY o.created_at, o.id
"""


def _query(dsn: str, sql: str, params: tuple = ()) -> list[dict]:
    import psycopg
    import psycopg.rows

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def _tally(values) -> dict:
    counts: dict = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def dispatch_allowance(dsn: str) -> dict:
    """Physical sends made, against the cap sheet's ceiling.

    Counted from the operations table rather than from this process's own
    log, because a process that died between the send and its write would
    otherwise report fewer sends than the provider saw.
    """
    rows = _query(dsn, OPERATIONS)
    probes = [r for r in rows if r["operation_id"].endswith("-probe")]
    builds = [r for r in rows if "-construct-" in r["operation_id"]]
    return {
        "currency": "dispatch allowance",
        "operations_in_store": len(rows),
        "construction_sends": len(builds),
        "route_probes": len(probes),
        "physical_sends": len(rows),
        "dispatch_states": _tally(r["dispatch_state"] for r in rows),
        "settled": _tally(r["settled"] for r in rows),
        "per_operation": {r["operation_id"]: {
            "dispatch_state": r["dispatch_state"],
            "settled": r["settled"],
            "receipt": r["receipt_identity"],
        } for r in rows},
    }


def internal_reservation(dsn: str, *, unit_allowance: dict) -> dict:
    """The broker's estimated-budget units, derived from the same schedule.

    The store does not persist a per-operation unit count, so the units are
    recomputed from each operation's own payload with
    `broker.exposure_schedule`, the same function that charged the run. That
    is a recomputation and is labelled as one; it is not a reading of a
    ledger the broker wrote.
    """
    from settlement import broker

    rows = _query(dsn, "SELECT id AS operation_id, payload FROM operations "
                       "ORDER BY created_at, id")
    per_operation, total, unpriced = {}, 0, []
    for row in rows:
        envelope = row["payload"] or {}
        # The store keeps the request under `payload.payload`, with the
        # effect and retry count beside it. An operation whose payload does
        # not carry that shape is named rather than priced at zero.
        effect = str(envelope.get("effect") or "")
        request = envelope.get("payload") or {}
        if not isinstance(request, dict) or "messages" not in request:
            unpriced.append(row["operation_id"])
            continue
        units, kind = broker.exposure_schedule(
            effect, request, int(envelope.get("retries") or 0))
        per_operation[row["operation_id"]] = {"units": units, "kind": kind}
        total += int(units)
    allowed = int(unit_allowance.get("units") or 0)
    return {
        "currency": "internal reservation",
        "unit_kind": "estimated-budget",
        "note": "recomputed with settlement.broker.exposure_schedule, the same"
                " function that charged the run; a reservation estimate, not a"
                " price and not a dispatch count",
        "units_total": total,
        "allowed_units": allowed or None,
        "headroom_units": (allowed - total) if allowed else None,
        "operations_not_priced": unpriced,
        "per_operation": per_operation,
    }


def provider_billing(dsn: str) -> dict:
    """What the gateway reported per receipt, and what is simply unknown.

    The gateway reports token `usage` on a settled send and reports no cost
    at all, so the provider currency here is token usage and its absence. A
    receipt whose `response_class` is `lost-response` spent a real request
    and returned nothing to bill against. That is uncertain, never zero, and
    it is reported in its own bucket so it cannot be averaged into the
    reported ones or read as a free request.
    """
    rows = _query(dsn, OPERATIONS)
    classified = {"REPORTED": 0, "NOT_REPORTED": 0, "UNMEASURED": 0,
                  "UNCERTAIN": 0}
    uncertain, usage_totals, unreported = [], {}, []
    for row in rows:
        operation = row["operation_id"]
        if str(row.get("response_class") or "") == "lost-response":
            classified["UNCERTAIN"] += 1
            uncertain.append(operation)
            continue
        usage = row["usage"] or {}
        if not isinstance(usage, dict) or not usage:
            classified["UNMEASURED"] += 1
            unreported.append({"operation_id": operation,
                               "reason": "no usage on the receipt",
                               "outcome": row["outcome"]})
            continue
        classified["REPORTED"] += 1
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                usage_totals[key] = usage_totals.get(key, 0) + value
    return {
        "currency": "provider billing",
        "unit": "gateway-reported token usage; the gateway reports no price",
        "receipts": sum(1 for r in rows if r["receipt_identity"]),
        "classification": classified,
        "reported_usage_totals": usage_totals,
        "uncertain_operations": uncertain,
        "unmeasured_detail": unreported,
        "note": "a lost response is UNCERTAIN, not zero: a request was sent"
                " and nothing came back to bill against",
    }


def held_units(dsn: str, *, allocation_id: str) -> dict:
    """What the study still holds against its own authorization."""
    rows = _query(dsn, """
        SELECT a.id AS allocation_id, a.domain, a.authorized, a.consumed,
               a.reserved, a.occupancy, a.max_occupancy,
               s.authorized AS study_authorized, s.ceilings
        FROM allocations a
        LEFT JOIN study_authority s ON s.allocation_id = a.id
        WHERE a.id = %s
    """, (allocation_id,))
    if not rows:
        return {"currency": "held units",
                "error": "no allocation %r in this store" % allocation_id}
    row = rows[0]
    authorized = int(row["authorized"] or 0)
    consumed = int(row["consumed"] or 0)
    return {
        "currency": "held units",
        "allocation_id": allocation_id,
        "authorized": authorized,
        "consumed": consumed,
        "reserved": int(row["reserved"] or 0),
        "occupancy": row["occupancy"],
        "max_occupancy": row["max_occupancy"],
        "study_authorized": row["study_authorized"],
        "unconsumed_units": authorized - consumed,
        "note": "held is not spent: units the study may still draw against",
    }


def cost_report(dsn: str, *, allocation_id: str, cap_sheet: dict) -> dict:
    allowance = cap_sheet.get("allowance") or {}
    units = cap_sheet.get("unit_allowance") or {}
    dispatches = dispatch_allowance(dsn)
    return {
        "schema": "e2-replica-r2-cost-v1",
        "cap_sheet_allowance": allowance,
        "cap_sheet_unit_allowance": units,
        "dispatch_allowance": dispatches,
        "internal_reservation": internal_reservation(dsn,
                                                     unit_allowance=units),
        "provider_billing": provider_billing(dsn),
        "held_units": held_units(dsn, allocation_id=allocation_id),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: make_cost_report.py DSN ALLOCATION_ID CAP_SHEET_JSON")
        return 2
    with open(argv[3], encoding="utf-8") as handle:
        cap = json.load(handle)
    report = cost_report(argv[1], allocation_id=argv[2], cap_sheet=cap)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
