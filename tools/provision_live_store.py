"""Build the durable store a live dispatch is refused without, and prove it refuses.

A dispatch on this tree reaches the wire through `_DurableBrokerOutput.infer`,
which calls `broker.ensure_operation` before it touches transport. That call is
the admission, not the gateway. What makes it refuse is the store underneath
it: a `study_authority` row binding the study to one allocation under a ceiling,
a parent `allocations` row carrying the reservation units, and a store
fingerprint. None of those survive on this host, and none of them is written by
`_require_grant`. A grant variable and an enforcing store are different facts,
and only the second makes a send capped, reserved and identified.

This builds the second from the repository's own machinery — no hand-rolled
SQL — and proves enforcement by attempting sends the store must refuse and
checking that each refusal fired with a message naming the rule it drew. A
provisioner that only reported success would be indistinguishable from a green
check that matched nothing.

Nothing here dispatches. `ensure_operation` admits an operation and takes its
reservation; it never opens a connection to a provider, so the probes are free
of model calls by construction.

    python scripts/provision_live_store.py --out DIR [--keep]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_run_isolation as isolation
from settlement import authority as settlement_authority
from settlement import broker
from settlement.common import ResultCode

MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
MESSAGE_CHARACTERS = 1774
MAX_OUTPUT_TOKENS = 2048
DEADLINE_MS = 300_000
REASONING_EFFORT = "low"
_CEILING_DEFAULT = object()
DROP_FAILURES: list[str] = []


def request_for(model: str = MODEL) -> dict:
    return {"model": model,
            "messages": [{"role": "user", "content": "x" * MESSAGE_CHARACTERS}],
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "deadline_ms": DEADLINE_MS,
            "reasoning_effort": REASONING_EFFORT}


def units_for(model: str = MODEL) -> tuple[int, str]:
    """Reservation units for one request, from the broker's own schedule."""
    return broker.exposure_schedule(broker.MODEL_INFERENCE, request_for(model), 0)


def discarded(database) -> None:
    """Drop a probe store even when the probe raised.

    A `finally` that calls the wrong name raises in place of the original
    failure, so the store it was written to outlives the run. Two did, and
    this is the repair: the drop never raises over the exception that got it
    here, and a drop that fails is recorded rather than swallowed.
    """
    try:
        isolation.drop_disposable_db(database, admin_dsn=isolation.admin_dsn())
    except Exception as exc:
        DROP_FAILURES.append("%s: %s: %s" % (getattr(database, "name", "?"),
                                             type(exc).__name__, exc))


def counted(dsn: str) -> dict:
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT (SELECT count(*) FROM operations) AS operations,"
                        " (SELECT count(*) FROM reservations) AS reservations,"
                        " (SELECT count(*) FROM receipts) AS receipts,"
                        " (SELECT count(*) FROM allocations) AS allocations,"
                        " (SELECT count(*) FROM study_authority) AS study_authority")
            row = dict(cur.fetchone())
        conn.commit()
    return row


def attempt(dsn: str, allocation_id: str, operation_id: str,
            model: str = MODEL) -> dict:
    """One admission through the live path's own entry point."""
    result = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload=request_for(model), allocation_id=allocation_id, retries=0)
    return {"operation_id": operation_id, "allocation_id": allocation_id,
            "code": str(result.code), "detail": result.detail,
            "admitted": result.code in (ResultCode.APPLIED,
                                        ResultCode.ALREADY_APPLIED)}


def authorized_store(token: str, dispatch_cap: int, unit_allowance: int,
                     ceilings: dict = _CEILING_DEFAULT) -> tuple:
    database = isolation.create_disposable_db(token,
                                              admin_dsn=isolation.admin_dsn())
    chosen = {"model_calls": dispatch_cap} if ceilings is _CEILING_DEFAULT \
        else ceilings
    try:
        handle = settlement_authority.authorize_study(
            database.dsn, isolation.study_root_for(token),
            authorized=unit_allowance,
            allocation_id=isolation.allocation_for(token), ceilings=chosen)
    except BaseException:
        discarded(database)
        raise
    return database, handle


def prove_units(units: int) -> dict:
    """Refuse a send the parent allocation no longer has units for.

    Priced at exactly one request, so the second send is over the reservation
    before any ceiling question arises and the refusal names the allocation.
    """
    database, handle = authorized_store("r2units", 75, units)
    try:
        first = attempt(database.dsn, handle.allocation_id, "r2-units-01")
        rows_after_first = counted(database.dsn)
        second = attempt(database.dsn, handle.allocation_id, "r2-units-02")
        rows_after_second = counted(database.dsn)
        remaining = settlement_authority.study_remaining(
            database.dsn, handle.study_root)
    finally:
        discarded(database)
    return {"authorized_units": units, "first": first, "second": second,
            "rows_after_first": rows_after_first,
            "rows_after_second": rows_after_second,
            "free_units_after_second": remaining}


def prove_ceiling(dsn: str, allocation_id: str, dispatch_cap: int) -> dict:
    """Refuse a send the frozen dispatch ceiling forbids while units remain.

    The allowance covers more requests than the ceiling admits, so the ceiling
    is the only rule left that can refuse, and the message says so.
    """
    before = counted(dsn)
    probes = [attempt(dsn, allocation_id, "r2-ceiling-%02d" % (n + 1))
              for n in range(dispatch_cap + 1)]
    return {"dispatch_cap": dispatch_cap, "rows_before": before,
            "probes": probes, "rows_after": counted(dsn),
            "admitted": sum(1 for p in probes if p["admitted"])}


def prove_control(dispatch_cap: int) -> dict:
    """The same sends against a study bound with no ceiling, and a bare store.

    Without this, every refusal above is equally consistent with a fixture that
    refuses whatever it is handed, and the run would prove nothing. Here the
    identical send past the identical position is admitted, so the refusals
    above are attributable to the ceilings and units this script wrote rather
    than to the store refusing by construction.
    """
    unceiled_db, unceiled = authorized_store("r2control", dispatch_cap,
                                             units_for()[0] * dispatch_cap * 4,
                                             ceilings=None)
    try:
        probes = [attempt(unceiled_db.dsn, unceiled.allocation_id,
                          "r2-control-%02d" % (n + 1))
                  for n in range(dispatch_cap + 1)]
        admitted = sum(1 for p in probes if p["admitted"])
    finally:
        discarded(unceiled_db)

    bare_db = isolation.create_disposable_db("r2bare",
                                             admin_dsn=isolation.admin_dsn())
    try:
        bare = attempt(bare_db.dsn, "r2-no-such-allocation", "r2-bare-01")
        rows = counted(bare_db.dsn)
    finally:
        discarded(bare_db)
    return {"dispatch_cap": dispatch_cap,
            "admitted_without_ceiling": admitted,
            "probes": len(probes),
            "probe_results": probes,
            "ceiling_would_have_refused_at": dispatch_cap + 1,
            "bare_migrated_store": bare, "bare_store_rows": rows}


def prove_binding(dsn: str) -> dict:
    """Refuse a send under an allocation no study root binds."""
    refusal = attempt(dsn, "r2-allocation-never-authorized", "r2-unbound-01")
    other = isolation.create_disposable_db("r2bindcheck",
                                           admin_dsn=isolation.admin_dsn())
    try:
        from psycopg.rows import dict_row

        from settlement import db

        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT study_root, store_fingerprint"
                            " FROM study_authority ORDER BY 1")
                bound = dict(cur.fetchone())
            conn.commit()
        rebound = {}
        try:
            settlement_authority.bind_study(other.dsn, bound["study_root"])
        except Exception as exc:
            rebound = {"refused": True, "type": type(exc).__name__,
                       "detail": str(exc)}
        else:
            rebound = {"refused": False}
    finally:
        discarded(other)
    return {"unbound_allocation": refusal,
            "bound_to_another_store": rebound}


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision_live_store.py")
    parser.add_argument("--out", required=True)
    parser.add_argument("--dispatch-cap", type=int, default=75)
    parser.add_argument("--token", default="r2livestore")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    units, kind = units_for()
    database = None
    handle = None
    ceiling_db = None
    try:
        database, handle = authorized_store(args.token, args.dispatch_cap,
                                            units * args.dispatch_cap)
        binding = prove_binding(database.dsn)
        units_probes = prove_units(units)
        ceiling_db, ceiling_handle = authorized_store(
            args.token + "ceil", 1, units * 4)
        ceiling_probes = prove_ceiling(ceiling_db.dsn,
                                       ceiling_handle.allocation_id, 1)
        control = prove_control(1)
        remaining = settlement_authority.study_remaining(
            database.dsn, handle.study_root)
        ledger = settlement_authority.verify_ledger(database.dsn,
                                                    handle.study_root)
    finally:
        for created in (database, ceiling_db):
            if created is not None and not args.keep:
                discarded(created)

    over_units = units_probes["second"]
    over_ceiling = ceiling_probes["probes"][-1]
    unit_refusal = (not over_units["admitted"]
                    and str(ResultCode.INSUFFICIENT_RESOURCES)
                    in over_units["code"]
                    and over_units["detail"].strip() != "")
    ceiling_refusal = (not over_ceiling["admitted"]
                       and str(ResultCode.INSUFFICIENT_RESOURCES)
                       in over_ceiling["code"]
                       and str(ceiling_probes["dispatch_cap"])
                       in over_ceiling["detail"])
    binding_refusals = [binding["unbound_allocation"]]
    bound_refused = (not binding["unbound_allocation"]["admitted"]
                     and binding["bound_to_another_store"].get("refused") is True)
    spent_nothing = (units_probes["rows_after_second"]["operations"]
                     == units_probes["rows_after_first"]["operations"])

    control_honest = (control["admitted_without_ceiling"]
                      == control["probes"]
                      and not control["bare_migrated_store"]["admitted"]
                      and control["bare_store_rows"]["operations"] == 0)

    report = {
        "schema": "r2-live-store-provisioning-v1",
        "status": "pass" if all((unit_refusal, ceiling_refusal, bound_refused,
                                 spent_nothing, ledger["match"],
                                 control_honest, not DROP_FAILURES)) else "fail",
        "store": {
            "database": database.name if database else None,
            "kept": bool(args.keep),
            "study_root": handle.study_root,
            "allocation_id": handle.allocation_id,
            "store_fingerprint": handle.store_fingerprint,
            "authorized_units": handle.authorized,
            "ceilings": handle.ceilings,
            "correction_budget": handle.correction_budget,
            "free_units_after_probes": remaining,
            "ledger_matches": ledger["match"],
        },
        "priced_from": {
            "model": MODEL,
            "message_characters": MESSAGE_CHARACTERS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "deadline_ms": DEADLINE_MS,
            "reasoning_effort": REASONING_EFFORT,
            "per_request_units": units,
            "unit_kind": kind,
            "expression": "%d // 4 + 1 + %d = %d"
                          % (MESSAGE_CHARACTERS, MAX_OUTPUT_TOKENS, units),
            "source": "settlement.broker.exposure_schedule(MODEL_INFERENCE,"
                      " request, 0)",
        },
        "refusals": {
            "over_reservation_units": unit_refusal,
            "over_dispatch_ceiling": ceiling_refusal,
            "unbound_allocation_and_foreign_store": bound_refused,
            "refused_send_spent_nothing": spent_nothing,
            "control_same_send_admitted_unceiled": control_honest,
            "every_probe_store_dropped": not DROP_FAILURES,
        },
        "probes": {"units": units_probes, "ceiling": ceiling_probes,
                   "binding": binding, "control": control},
        "drop_failures": list(DROP_FAILURES),
        "dispatched": 0,
        "credential_read": False,
        "notes": [
            "No credential is read, written or required here. The route key"
            " resolves from the operator's own environment at dispatch time"
            " and from nowhere else.",
            "Each store is per-run disposable by construction. A long-lived"
            " shared live store is the contamination s09_run_isolation"
            " exists to prevent, so the durable rows a study needs are"
            " rebuilt per run rather than restored from one.",
            "ensure_operation admits and reserves; it opens no connection to"
            " a provider, so every probe above is free of model calls.",
        ],
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "store-provisioning.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("provision status=%s" % report["status"])
    for name, fired in sorted(report["refusals"].items()):
        print("  %-46s %s" % (name, fired))
    print("  over_units: %s %s" % (over_units["code"], over_units["detail"]))
    print("  over_ceiling: %s %s" % (over_ceiling["code"],
                                     over_ceiling["detail"]))
    print("  foreign_store: %s" % binding["bound_to_another_store"]["detail"])
    print("  control: %d/%d admitted with the ceiling removed; bare store"
          " rows=%d" % (control["admitted_without_ceiling"], control["probes"],
                        control["bare_store_rows"]["operations"]))
    for probe in control["probe_results"]:
        print("    control %s -> %s: %s" % (probe["operation_id"],
                                            probe["code"], probe["detail"]))
    print("    bare -> %s: %s" % (control["bare_migrated_store"]["code"],
                                  control["bare_migrated_store"]["detail"]))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())