"""C2 live acquisition driver (tracked; env supplies secrets, never code).

Runs development episodes + construction lineages through the integrated
`experience.acquire` path with the live gateway, then validates and
selects. Grant declarations come from the environment; the run refuses
without them (preflight). Usage: set the four documented env vars, then
`python -m experiments.coord02.run_live_acquisition --dsn ...`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from settlement.config import Settings
from settlement.gateway_http import HttpGatewayAdapter

from . import experience as E
from . import preflight
from .controller import seed_episode
from .entry import refuse_gateway_error


def _gateway():
    return HttpGatewayAdapter.from_settings(
        Settings.from_env(), api="responses")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="C2 live acquisition")
    parser.add_argument("--dsn", default=os.environ.get(
        "EC02_C2_DSN",
        "dbname=ec02test_c2live host=/var/run/postgresql user=ubuntu"))
    parser.add_argument("--campaign", default="c2live")
    parser.add_argument("--out", default="evidence-live/c2-acquisition.json")
    args = parser.parse_args(argv)
    verdict = preflight.require_live(
        panels=("development",),
        construction_calls=preflight.CONSTRUCTION_CALLS)
    print(json.dumps({"admitted": True,
                      "grant": verdict["grant"]}, indent=1))
    from settlement import db
    db.apply_migrations(args.dsn, Path("migrations"))
    gw = _gateway()
    refuse_gateway_error(gw.check_auth(), check="auth")
    from settlement.launcher_local import LocalLauncher
    scratch = Path("evidence-live/c2-scratch").resolve()
    scratch.mkdir(parents=True, exist_ok=True)

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(scratch / tag)}

    granted_calls = int(verdict["grant"]["construction_calls"])
    if granted_calls > preflight.CONSTRUCTION_CALLS:
        raise ValueError("grant %d exceeds the %d-call study ceiling"
                         % (granted_calls, preflight.CONSTRUCTION_CALLS))
    budget = E.construction_budget(max_output_tokens=16384,
                                   reasoning_effort=E.live_reasoning_effort(),
                                   live_calls_authorized=granted_calls)
    child_seed = E.seed_episode(
        args.dsn, "L-episode-children-%s" % args.campaign, {"m": "1"})
    from .entry import run_child_factory

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

    acquired = E.acquire(
        args.dsn, scratch, task_ids=list(E.DEV_SELECTION_TASKS),
        launcher_factory=launcher_factory,
        construction_gateway=gw, budget=budget,
        campaign_root=args.campaign)
    results = []
    for rec in acquired["lineages"]:
        for stage in E.validation_stages(rec):
            cand = rec["kept"] if stage == "init" \
                else rec["repair_kept"]
            if cand is None or not cand.get("usable"):
                continue
            validation = E.validate_on_development(
                args.dsn, entry_bytes=cand["entry_bytes"],
                requires={}, task_ids=list(E.DEV_SELECTION_TASKS),
                launcher_factory=launcher_factory,
                constructor_factory=constructor_factory,
                validation_root=rec[stage]["operation_id"])
            results.append({"lineage": rec["lineage"], "stage": stage,
                            "validation": validation,
                            "entry_bytes": cand["entry_bytes"].decode(
                                "utf-8", "replace")})
    selection = E.select_candidate(results)
    out = {"campaign": args.campaign, "grant": verdict["grant"],
           "selection": selection,
           "accounting": acquired["ledger"].accounting(),
           "results": [{k: v for k, v in r.items()
                        if k != "entry_bytes"} for r in results]}
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items()
                      if k != "results"}, indent=1))
    seed = seed_episode(args.dsn, "c2-done", {"m": "1"})
    print("ledger:", json.dumps(acquired["ledger"].accounting()))
    _ = seed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
