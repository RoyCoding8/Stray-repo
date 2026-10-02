"""AGENDA-4 one-shot scheduler: wakeups plus one single-driver sweep.

Runs once and exits; schedule externally (cron/systemd) for the periodic
cadence. Performs no model inference: gateway is always None, so model ops
defer and only mechanical work converges. Reconcile never resets an
advanced-but-unsent op back to prepared; redispatch needs the explicit
operator path in redispatch_reset, which couples a never-sent proof to a
generation-fenced store reset before dispatching once.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from settlement import agenda
from settlement.launcher_local import LocalLauncher


def run_once(dsn: str, run_dir: str | Path, rounds: int = 3) -> dict:
    from settlement import broker

    launcher = LocalLauncher(Path(run_dir))
    launchers = {"local-process": launcher, launcher.launcher_id: launcher}
    wakeups = agenda.collect_wakeups(dsn)
    passed = broker.sweep(dsn, launchers, gateway=None, repair=True, wake=True)
    return {"wakeups": wakeups["wakeups"],
            "cursor_epoch": wakeups["cursor_epoch"],
            "cursor_ordinal": wakeups["cursor_ordinal"],
            "rounds": 1,
            "dispatched": list(passed.dispatched), "delivered": list(passed.delivered),
            "repaired": list(passed.repaired),
            "deferred_model": list(passed.deferred_model),
            "next_decision": passed.next_decision}


def redispatch_reset(dsn: str, run_dir: str | Path, operation_id: str,
                     expected_generation: int) -> dict:
    from settlement import broker

    launcher = LocalLauncher(Path(run_dir))
    if not launcher.prove_never_sent(operation_id, expected_generation):
        return {"operation_id": operation_id, "dispatch_state": "dispatching",
                "sent_this_call": False, "next_decision": "refused-prior-claim"}
    launchers = {"local-process": launcher, launcher.launcher_id: launcher}
    status = broker.redispatch_after_reset(dsn, operation_id, launchers,
                                           expected_generation=expected_generation)
    return {"operation_id": operation_id, "dispatch_state": status.dispatch_state,
            "sent_this_call": status.sent_this_call, "next_decision": status.next_decision}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--run-dir", default=os.environ.get("SETTLEMENT_RUN_DIR",
                                                            "var/launcher-runs"))
    args = parser.parse_args(argv)
    print(json.dumps(run_once(args.dsn, args.run_dir), indent=2, sort_keys=True,
                     default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
