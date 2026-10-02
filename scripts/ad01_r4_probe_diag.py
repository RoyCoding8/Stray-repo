"""The r3 probe, plus what the guard's ledger says when it refuses.

`scripts/ad01_r3_probe.py` answers one question -- can the route produce an
ENTRY source -- and on a refusal it replaces the whole report with the
exception string. That loses the two things worth reading: how long the
attempt took, and what the guard recorded for it. A refused dispatch that
cost nothing and one that burned four attempts look identical in that
report.

This is the same single dispatch, with the guard's ledger, the broker
operation row and the receipts read out before the database is dropped. No
prompt, no response body, no key.

Run: python -m scripts.ad01_r4_probe_diag
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

TOKEN_RE = "r4diag"

READ_TIMEOUT_MS = 240_000


def _load_live_environment() -> None:
    for line in Path("/home/ubuntu/.config/agent-society-live.env").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_READ_MS"] = str(READ_TIMEOUT_MS)
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_TOTAL_MS"] = str(READ_TIMEOUT_MS + 60_000)


def main(argv: list[str] | None = None) -> int:
    _load_live_environment()

    from experiments.ad01 import live_construct, s09_run_isolation as isolation
    from experiments.ad01 import worlds
    from scripts import inv01_study as study
    from psycopg.rows import dict_row
    from settlement import db

    model = os.environ.get("INVL02_LIVE_MODEL", "").strip()
    if not model:
        print("DIAG_REFUSED: INVL02_LIVE_MODEL names no model")
        return 2
    route = study._v1_route_from_env(model)
    admin = isolation.admin_dsn()
    token = "%s%s" % (TOKEN_RE, uuid.uuid4().hex[:8])
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    root = isolation.study_root_for(token)
    dsn = database.dsn
    report: dict = {"db": database.name}
    started = time.monotonic()
    try:
        units = study._v1_study_units(study._v1_campaign_count(0))
        study._v1_ensure_run(
            dsn, root, units, 900,
            study._v1_effective_config("live", model, "", 900),
            study._v1_panel(), study._v1_ceilings(study._v1_use_arms()))
        cid = "r4diag-c0"
        study._v1_ensure_campaign_alloc(
            dsn, root, cid, study._v1_campaign_units())
        from experiments.ad01 import trajectory
        trajectory.ensure_campaign(
            dsn, cid, 0, "I", dict(study.CHARTER),
            {"max_boundaries": 2, "diagnostic_queries": 16,
             "model_calls": 60, "construction_tokens": 2048,
             "agenda_authorized": units},
            tasks=[study._use_tasks(0)[0]], study_root=root)

        gateway = study._v1_select_provider("live", model, [], route=route)
        guard = live_construct.LiveGuard(
            gateway, pinned_model=model, ceiling=1, expected_route=route,
            automatic_retries=0)
        task = worlds.load_task(worlds.FROZEN_DIR, study._use_tasks(0)[0])
        try:
            member = live_construct.construct_live_method(
                dsn, campaign_id=cid, task=task,
                experience={"observations": [], "retained": [],
                            "remaining": {"queries": 16, "steps": 12,
                                          "model_calls": 60}},
                budget={"max_output_tokens": 2048, "deadline_ms": READ_TIMEOUT_MS,
                        "max_queries": 4, "model_calls": 4},
                gateway=guard, model=model, study_root=root)
            evidence = dict(member.get("acquisition_evidence") or {})
            report["acquired"] = True
            report["capability_id"] = member.get("capability_id")
            report["source_bytes"] = len(str(member.get("method_source") or ""))
            report["earned"] = evidence.get("earned")
            report["simulated"] = evidence.get("simulated")
        except Exception as exc:
            report["acquired"] = False
            report["error_class"] = type(exc).__name__
            report["error"] = str(exc)[:500]
        report["elapsed_s"] = round(time.monotonic() - started, 1)
        report["guard"] = guard.guard_status()
        report["ledger"] = [
            {k: entry.get(k) for k in
             ("operation_id", "kind", "outcome", "attempt", "response_received",
              "response_status", "parse_outcome", "route_error",
              "pre_gateway_refusal", "diagnosis")}
            for entry in guard.ledger]
        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, settled, dispatch_state,"
                            " reconcile_state FROM operations ORDER BY id")
                report["operations"] = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT operation_id, receipt_identity, outcome FROM"
                    " receipts ORDER BY operation_id, receipt_identity")
                report["receipts"] = [dict(r) for r in cur.fetchall()]
            conn.commit()
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
        report["dropped"] = database.name
    print("DIAG_RESULT=%s" % json.dumps(report, sort_keys=True, default=str))
    return 0 if report.get("acquired") else 1


if __name__ == "__main__":
    raise SystemExit(main())
