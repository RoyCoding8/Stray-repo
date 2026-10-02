"""Run the study with the control arm, into a new evidence directory.

The database name is derived per run by `s09_run_isolation.create_disposable_db`
and dropped in a `finally`, so a killed run still leaves a name the next
`drop_disposable_db` can remove and this script prints for cleanup. Nothing
is hardcoded and nothing outside `s09iso_` is touched.

Two changes from the runner this replaces, both about what the run records
rather than what it spends.

**The result artifact is written into a new directory, never over an old
one.** `control_arm_result.build` refuses a destination that exists, which
is the right default, so the caller names a new one. The study output goes
to a run-scoped directory under the scratch root and the result artifact
lands beside it, so `reports/evidence/inv_r1_e1_control_arm/` and the run
that produced its twelve ties are never modified by a later run.

**The gate reads the run's own traces.** Nothing here reconstructs a walk
after the fact. `method_exec` records each query on the host side of the
oracle channel, `trajectory.run_use` carries it onto the record, and
`control_distinct` reads it from the same file it reads the candidates
from.
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

TOKEN_RE = "ctlwalk"


def main():
    from experiments.ad01 import control_arm_result as result
    from experiments.ad01 import s09_run_isolation as isolation
    from scripts import inv01_study as study

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "reports" / "evidence" / "inv_r1_e1_control_walk")
    if out.exists():
        print("refusing to write over an existing %s" % out, file=sys.stderr)
        return 2
    # The library's own resolution: SETTLEMENT_TEST_DSN when set, else its
    # default. Resolved once and passed to both create and drop, so the two
    # cannot land on different PostgreSQL instances mid-run.
    admin = isolation.admin_dsn()
    token = "%s%s" % (TOKEN_RE, uuid.uuid4().hex[:8])
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    print("DISPOSABLE_DB=%s" % database.name, flush=True)
    study_root = isolation.study_root_for(token)
    print("STUDY_ROOT=%s" % study_root, flush=True)
    # Derived, not typed: the study refuses a grant that does not cover
    # one subdivision per campaign plus one per control arm, and a literal
    # here would silently drift from that.
    authorized = study._v1_study_units(study._v1_campaign_count(0))
    study_out = ROOT / ".ad01-walk-runs" / token
    try:
        cmd = [sys.executable, "scripts/inv01_study.py",
               "--dsn", database.dsn,
               "--out", str(study_out),
               "--agenda-authorized", str(authorized),
               "--study-root", study_root,
               "--provider", "recording",
               "--model", "inv01-study-double",
               "--max-boundaries", "6",
               "--deadline-s", "3000"]
        print("RUN: %s" % " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=2400)
        print("RC=%d" % proc.returncode)
        print("STDOUT:\n%s" % proc.stdout[-6000:])
        print("STDERR:\n%s" % proc.stderr[-6000:])
        if proc.returncode != 0:
            return proc.returncode
        # Cost is read while the store still exists. The study's outputs
        # name no operation count and the freeze carries no billing, so a
        # result artifact built after the drop would report every currency
        # UNMEASURED and the run's actual spend would be lost with the
        # database.
        cost = result.cost_currencies(dsn=database.dsn,
                                      study_root=study_root)
        (study_out / "run_cost.json").write_text(
            json.dumps(cost, sort_keys=True, indent=1, default=str) + "\n",
            encoding="utf-8")
        print("COST: %s" % json.dumps(
            {name: body.get("status", "REPORTED")
             for name, body in cost.items()}, sort_keys=True), flush=True)
        summary = result.build(study_out, out, dsn=database.dsn,
                               study_root=study_root)
        print("RESULT: %s" % json.dumps(summary, sort_keys=True,
                                        default=str), flush=True)
        return 0
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
        print("DROPPED=%s" % database.name, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
