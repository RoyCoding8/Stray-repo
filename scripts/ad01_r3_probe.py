"""One live dispatch, to learn whether the route can produce an ENTRY source.

The memory `unblock-study-plumbing-before-running` is the reason this exists.
A frozen study cannot be un-run, and the unit suite is green against fixtures
whose replies are an authored solver, so a study can burn its ceiling against
a route that never had a chance of answering. One cheap call answers the
question: can the pinned model return a member that `verify_member` and the
ENTRY contract accept?

Nothing here writes evidence and nothing here constructs a study. It derives a
disposable database so the probe's operation, reservation and receipt are
durable and are then dropped with it, and it reports only counts, digests and
pass/fail. No prompt, no response body and no key is printed.

Run: python -m scripts.ad01_r3_probe
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

TOKEN_RE = "r3probe"

# The construction prompt runs the free reasoning model past 150s on a 1560
# character prompt, and the adapter's read default is 60s, so a probe at the
# default is a measurement of the timeout rather than of the model. The
# router's own upstream header timeout is 60.0s, so a read above that is the
# only value that can wait for the reasoning to finish.
READ_TIMEOUT_MS = 240_000


def _load_live_environment() -> None:
    """The four documented variables, from the file, without printing them."""
    path = Path("/home/ubuntu/.config/agent-society-live.env")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    _load_live_environment()
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_READ_MS"] = str(READ_TIMEOUT_MS)
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_TOTAL_MS"] = str(READ_TIMEOUT_MS + 60_000)

    from experiments.ad01 import construct, live_construct, method_exec
    from experiments.ad01 import s09_run_isolation as isolation
    from experiments.ad01 import worlds
    from scripts import inv01_study as study

    model = os.environ.get("INVL02_LIVE_MODEL", "").strip()
    if not model:
        print("PROBE_REFUSED: INVL02_LIVE_MODEL names no model")
        return 2
    route = study._v1_route_from_env(model)
    print("PROBE_ROUTE_OK requested=%s provider=%s tier=%s"
          % (route["requested_model"], route["provider"], route["tier"]))
    print("PROBE_READ_TIMEOUT_MS=%d" % READ_TIMEOUT_MS)

    admin = isolation.admin_dsn()
    token = "%s%s" % (TOKEN_RE, uuid.uuid4().hex[:8])
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    print("PROBE_DB=%s" % database.name, flush=True)
    dsn = database.dsn
    report: dict = {}
    try:
        study._v1_ensure_run(
            dsn, isolation.study_root_for(token),
            study._v1_study_units(study._v1_campaign_count(0)),
            900, study._v1_effective_config("live", model, "", 900),
            study._v1_panel(), study._v1_ceilings(study._v1_use_arms()))

        # The campaign id here is the study campaign, not the construction
        # episode. `construct_method` builds the episode name itself and
        # takes its authority from `_alloc_id(campaign_id)`, so handing it
        # the episode asks for a parent that no caller ever created. That
        # refusal is pre-gateway and costs no dispatch, which is how it was
        # found.
        cid = "r3probe-c0"
        study._v1_ensure_campaign_alloc(
            dsn, isolation.study_root_for(token), cid,
            study._v1_campaign_units())
        trajectory = __import__(
            "experiments.ad01.trajectory", fromlist=["x"])
        trajectory.ensure_campaign(
            dsn, cid, 0, "I", dict(study.CHARTER),
            {"max_boundaries": 2, "diagnostic_queries": 16,
             "model_calls": 60, "construction_tokens": 2048,
             "agenda_authorized": study._v1_study_units(
                 study._v1_campaign_count(0))},
            tasks=[study._use_tasks(0)[0]],
            study_root=isolation.study_root_for(token))

        gateway = study._v1_select_provider(
            "live", model, [], route=route)
        guard = live_construct.LiveGuard(
            gateway, pinned_model=model, ceiling=1,
            expected_route=route)
        task = worlds.load_task(worlds.FROZEN_DIR, study._use_tasks(0)[0])
        member = live_construct.construct_live_method(
            dsn, campaign_id=cid,
            task=task, experience={"observations": [], "retained": [],
                                   "remaining": {"queries": 16, "steps": 12,
                                                 "model_calls": 60}},
            budget={"max_output_tokens": 2048, "deadline_ms": READ_TIMEOUT_MS,
                    "max_queries": 4, "model_calls": 4},
            gateway=guard, model=model,
            study_root=isolation.study_root_for(token))
        source = str(member.get("method_source") or "")
        evidence = dict(member.get("acquisition_evidence") or {})
        report = {
            "acquired": True,
            "capability_id": member.get("capability_id"),
            "source_bytes": len(source),
            "source_digest": hashlib.sha256(
                source.encode("utf-8")).hexdigest()[:12],
            "origin": member.get("origin"),
            "evidence_earned": evidence.get("earned"),
            "evidence_reason": evidence.get("reason"),
            "simulated": evidence.get("simulated"),
            "adapter": (evidence.get("route") or {}).get("model"),
            "guard_spent_dispatches": guard.spent_dispatches,
            "guard_refusal": guard.refusal_reason or None,
        }
        # The two gates the study applies to a member before it is retained.
        # A probe that stops at "the provider answered" is a probe of
        # transport, not of the path this study runs.
        try:
            method_exec.verify_member({"method_source": source,
                                       "entry": member.get("entry")})
            report["verify_member"] = "pass"
        except Exception as exc:
            report["verify_member"] = "fail: %s" % exc
    except Exception as exc:
        report = {"acquired": False,
                  "error_class": type(exc).__name__,
                  "error": str(exc)[:400]}
    finally:
        with __import__("psycopg").connect(admin, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT o.id, o.settled, o.dispatch_state,"
                            " r.outcome FROM receipts r JOIN operations o"
                            " ON o.id = r.operation_id WHERE r.outcome"
                            " IS NOT NULL ORDER BY o.id")
                rows = cur.fetchall()
        report["receipts"] = [{"operation_id": r[0], "settled": r[1],
                               "dispatch_state": r[2], "outcome": r[3]}
                              for r in rows]
        isolation.drop_disposable_db(database, admin_dsn=admin)
        report["dropped"] = database.name
    print("PROBE_RESULT=%s" % json.dumps(report, sort_keys=True, default=str))
    return 0 if report.get("acquired") else 1


if __name__ == "__main__":
    raise SystemExit(main())
