"""The r4 run, rehearsed against a recording double. No live dispatch.

A frozen study cannot be un-run, and three lanes were killed mid-investigation
here. So the parts of `scripts/ad01_r4_compare.py` that do not need a provider
are exercised first, end to end, in one process: the authority is subdivided,
the control arm runs, the acquired arms run, the gate runs, and both verdicts
run. The only substitution is `_v1_select_provider`, which returns the
recording double instead of the http adapter.

What this cannot check is whether the model returns an admissible ENTRY.
That is the question the live route answers and the double cannot.

Run: python -m scripts.ad01_r4_rehearse
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

OUT = ROOT / ".ad01-r4-rehearsal"


def main() -> int:
    from experiments import doubles
    from experiments.ad01 import s09_run_isolation as isolation
    from scripts import ad01_r4_compare as driver
    from scripts import inv01_study as study

    # The double answers on the same operation, settles the same receipt and
    # carries `simulated: True`, so `acquisition_origin` must read it as a
    # stand-in. That is the whole point: the rehearsal must produce
    # `live_acquisition: unproven`, and if it produced `true` the rehearsal
    # would be measuring nothing.
    #
    # The double's metadata is `simulated` plus the stream name, so it cannot
    # attest the four route fields `LiveGuard._route_failure` checks and the
    # guard refuses on `route` before the call settles. `expected_route=None`
    # turns that check off, which is the only difference between rehearsing
    # and running: the route attestation is what the live route is for, and
    # it is asserted at dispatch time rather than configured here.
    original = study._v1_select_provider

    def double_select(provider, model, learner_scripts, *, route=None):
        return doubles.InvCQualificationDouble(
            learner_scripts=[],
            init_scripts=[{"text": doubles.construction_text()}
                          for _ in range(8)],
            repair_scripts=[{"text": doubles.construction_text()}
                            for _ in range(8)])

    # `ad01_r4_compare` imports `inv01_study` lazily inside its functions and
    # caches it on the package, so patching the module attribute once is
    # enough for every call site in both modules.
    study._v1_select_provider = double_select

    if OUT.exists():
        shutil.rmtree(OUT)
    admin = isolation.admin_dsn()
    token = "r4rehearse%s" % uuid.uuid4().hex[:8]
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    root = isolation.study_root_for(token)
    dsn = database.dsn
    scratch = ROOT / ".ad01-r4-rehearsal-run" / token
    try:
        study._v1_ensure_run(
            dsn, root, driver.study_units(), 3600,
            study._v1_effective_config("live", "recorded-double", "", 3600),
            study._v1_panel(), driver.ceilings())
        arms, guard = driver.acquire(dsn, root, "recorded-double", None)
        control = driver.run_control_use(dsn, root, scratch)
        acquired = driver.use_acquired_arms(dsn, root, arms, scratch)
        print("REHEARSAL acquired=%d earned=%d control=%d acquired_use=%d"
              % (sum(1 for a in arms if a["acquired"]),
                 sum(1 for a in arms
                     if (a.get("evidence") or {}).get("earned") is True),
                 len(control), len(acquired)))
        for arm in arms:
            if not arm["acquired"]:
                print("  refused %s: %s" % (arm["task_id"],
                                            arm["reason"][:160]))
            elif arm.get("use_error"):
                print("  use failed %s: %s" % (arm["task_id"],
                                                arm["use_error"][:160]))

        from experiments.ad01 import control_arm_result as result
        gate = result.gate_control_distinct(control, acquired)
        print("REHEARSAL_GATE=%s" % json.dumps(
            driver.gate_split(gate), sort_keys=True))
        print("REHEARSAL_DISTINCT=%s" % gate.get("distinct"))
        paired = result.per_task(result.arm_rows(control),
                                 result.arm_rows(acquired))
        print("REHEARSAL_UTILITY=%s paired=%d"
              % (result.utility(paired)["value"], len(paired)))

        out = OUT
        out.mkdir(parents=True, exist_ok=True)
        written = driver.write_verdict_bundle(
            dsn, root, arms, control, acquired, out, "recorded-double",
            {"endpoint": "local", "provider": "double", "tier": "recording",
             "requested_model": "recorded-double",
             "resolved_model": "recorded-double"})
        verdicts = written["verdicts"]
        print("REHEARSAL_LIVE_ACQUISITION=%s (must be unproven: a recording"
              " double is not a live provider)" % verdicts["live_acquisition"])
        print("REHEARSAL_TASK_UTILITY=%s" % verdicts["task_utility"])
        for leg in verdicts["task_utility_legs"]:
            print("  %-42s %s" % (leg["name"], leg["status"]))
            print("      %s" % leg["evidence"][:220])
        cost = driver.write_cost(dsn, root, guard, out)
        print("REHEARSAL_COST=%s" % json.dumps(
            {k: v.get("status") for k, v in cost.items()
             if isinstance(v, dict)}, sort_keys=True))
        return 0
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
        if scratch.exists():
            shutil.rmtree(scratch)
        print("DROPPED=%s" % database.name)


if __name__ == "__main__":
    raise SystemExit(main())
