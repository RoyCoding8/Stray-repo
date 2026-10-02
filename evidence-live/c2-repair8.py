"""C2 live degeneracy repair driver (tracked live evidence script).

Replays the c2live8 development episodes from the command journal (no new
episode spend), then spends the 2 remaining granted construction calls as
one repair per lineage with concrete degeneracy feedback: both init
candidates parse and profile but probe once and stop without planning.
Repair validates on development through the live child factory, reselects
over init + repair results, and writes the repair evidence file. Grant
comes from the environment; the run refuses without it (preflight).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from settlement.config import Settings
from settlement.gateway_http import HttpGatewayAdapter

from experiments.coord02 import experience as E
from experiments.coord02 import preflight
from experiments.coord02.controller import seed_episode
from settlement.representation import sha_hex


def _gateway():
    return HttpGatewayAdapter.from_settings(
        Settings.from_env(), api="responses")


DEGENERACY_REASON = (
    "candidate parses and profiles but validation on all 6 development "
    "tasks ends stopped with reason acquisition probe only: it probes "
    "once then stops without ever proposing a plan or solving a task. "
    "Repair: author a policy that proposes a plan after probing and "
    "solves development tasks.")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="C2 live repair round")
    parser.add_argument("--dsn", default=os.environ.get(
        "EC02_C2_DSN",
        "dbname=ec02test_c2live8 host=/var/run/postgresql user=ubuntu"))
    parser.add_argument("--campaign", default="c2live8")
    parser.add_argument("--prior", default="evidence-live/c2-acquisition8.json")
    parser.add_argument("--out",
                        default="evidence-live/c2-acquisition8-repair.json")
    args = parser.parse_args(argv)
    verdict = preflight.require_live(
        panels=("development",),
        construction_calls=preflight.CONSTRUCTION_CALLS)
    granted_calls = int(verdict["grant"]["construction_calls"])
    if granted_calls > preflight.CONSTRUCTION_CALLS:
        raise ValueError("grant %d exceeds the %d-call study ceiling"
                         % (granted_calls, preflight.CONSTRUCTION_CALLS))
    from settlement import db
    db.apply_migrations(args.dsn, Path("migrations"))
    gw = _gateway()
    assert gw.check_auth() is not None
    from settlement.launcher_local import LocalLauncher
    scratch = Path("evidence-live/c2-scratch").resolve()
    scratch.mkdir(parents=True, exist_ok=True)

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(scratch / tag)}

    budget = E.construction_budget(max_output_tokens=16384,
                                   reasoning_effort=E.live_reasoning_effort(),
                                   live_calls_authorized=granted_calls)
    episodes = E.acquire_episodes(
        args.dsn, scratch, task_ids=list(E.DEV_SELECTION_TASKS),
        campaign_root=args.campaign, launcher_factory=launcher_factory,
        constructor=None)
    seed = E.seed_construction_campaign(args.dsn, args.campaign, budget)
    ledger = E.ConstructionLedger(
        args.dsn, seed["allocation_id"],
        attempt_prefix=f"coord02-L-construct-{args.campaign}",
        authorized_calls=int(budget.get("live_calls_authorized",
                                        E.MAX_CONSTRUCTION_CALLS)))
    child_seed = seed_episode(
        args.dsn, "L-episode-children-%s" % args.campaign, {"m": "1"})
    from experiments.coord02.entry import run_child_factory

    def constructor_factory(task_id: str):
        inner = run_child_factory(
            args.dsn, task_id=task_id, gateway=gw,
            model=E.live_model(),
            allocation_id=child_seed["allocation_id"])

        def _build(node, child, rendered, operation_id=None,
                   attempt_id=None):
            return inner(node, child, rendered,
                         operation_id=operation_id,
                         attempt_id=attempt_id)

        return _build

    prior = json.loads(Path(args.prior).read_text())
    results = [{"lineage": r["lineage"], "stage": r["stage"],
                "validation": r["validation"]} for r in prior["results"]]
    repairs = []
    for lineage in (1, 2):
        init_op = "coord02-L-construct-%s-l-%d-init-%d" % (
            args.campaign, lineage, lineage)
        failure = {"kind": "behavior", "reason": DEGENERACY_REASON,
                   "operation_id": init_op, "lineage": lineage,
                   "stage": "validation"}
        rep = ledger.repair_call(
            episodes, budget, lineage=lineage, prior_failure=failure,
            gateway=gw, replay=True)
        kept = E.keep_response(rep)
        parsed = E.parse_candidate(kept["entry_bytes"])
        profile = None
        if kept["usable"] and parsed["ok"]:
            profile = E._acquisition_step(
                args.dsn, f"{rep['operation_id']}:profile",
                {"entry_digest": sha_hex(kept["entry_bytes"])},
                lambda: E._profile_check(
                    args.dsn, entry_bytes=kept["entry_bytes"],
                    identity=rep["operation_id"], requires={},
                    launcher_factory=launcher_factory))
        rec = {"lineage": lineage, "repair": rep,
               "repair_kept_usable": bool(kept.get("usable")),
               "repair_parsed_ok": bool(parsed.get("ok")),
               "repair_profile_ok": bool(profile["ok"]) if profile else None}
        repairs.append(rec)
        if kept.get("usable") and parsed.get("ok"):
            validation = E.validate_on_development(
                args.dsn, entry_bytes=kept["entry_bytes"],
                requires={}, task_ids=list(E.DEV_SELECTION_TASKS),
                launcher_factory=launcher_factory,
                constructor_factory=constructor_factory,
                validation_root=rep["operation_id"])
            results.append({"lineage": lineage, "stage": "repair",
                            "validation": validation})
    selection = E.select_candidate(results)
    out = {"campaign": args.campaign, "grant": verdict["grant"],
           "repair_reason": DEGENERACY_REASON,
           "effort": E.live_reasoning_effort(),
           "selection": selection,
           "accounting": ledger.accounting(),
           "repairs": [{k: v for k, v in r.items() if k != "repair"}
                       for r in repairs],
           "results": results}
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("results", "repairs")}, indent=1))
    print("ledger:", json.dumps(ledger.accounting()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
