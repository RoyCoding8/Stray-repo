# inv-r1 — S1 real resumable study entry

Branch: `wt/inv-r1-entry` (base `8d2b2a5`). Owned paths only:
`scripts/inv01_study.py`, `migrations/0016_study_run.sql`,
`tests/test_invr1_study_entry.py` (+ this report).

## What changed

The public entry `scripts/inv01_study.py` gained an explicit
recording/live choice through the same command. `--provider
recording|live`, `--model`, `--reasoning-effort`, `--study-root`,
`--agenda-authorized`, `--deadline-s`, `--max-trajectories` and
`--max-boundaries` are real inputs. Model, effort, effective
configuration, study identity, grant and frozen panel are recorded in
`study.json`. The live path builds the configured HTTP adapter and
refuses without endpoint, key, or an explicit non-double model. No
recording fallback exists on that path.

Every trajectory and use operation binds one already-authorized study
root through the existing authority machinery (`authorize_study` once,
`bind_study` plus `subdivide_allocation` per campaign). Consumption and
wall deadline persist in the new `inv_r1_study_runs` row
(`migrations/0016_study_run.sql`). Admission runs before each
trajectory and each use batch against 360 model calls, 24 construction
calls, 960 witness queries, 5328 execution units, remaining wall time
and allocation balance. Restart reuses the row, refuses grant, deadline
or config changes, keeps one `study_authority` row and never clears the
database. The study path refuses `--prepare-disposable`. The cap sheet
derives from effective settings and runner constants with the four
accounting kinds (estimate, measured, internal charge, provider
billing) kept separate. Totals recompute from operation and receipt
identities and call the merged `records.verify_study` gate when the
checked-out `records.py` provides it.

## Test results (real PostgreSQL 16, disposable `inv_r1_` databases)

`tests/test_invr1_study_entry.py`: 5 passed in 16.46s. Controlled-HTTP
live response traced to a stored receipt effect. Missing endpoint and
default-double live model both refuse with zero operations and zero
simulated receipts. Restart keeps one authority row, identical op count
and unchanged deadline plus consumption. Expired deadline and exhausted
caps each refuse with zero new effects. Cap sheet keeps 360/24 ceilings
and per-trajectory limits with billing split and no replenishment on
grant or deadline change.

Nearby: `test_invc3_study`, `test_invc2_authority`,
`test_r01_authority`, `test_r02_authority`, `test_ad01_traj`: 40 passed,
33 skipped (`SETTLEMENT_TEST_DSN`-gated) in 38.35s.

Full recording pilot through the public command (6 trajectories, 24
protected use records): study rc 0, `--recompute` rc 0, 39 model calls
and 12 construction calls against the 360/24 ceilings. Scratch
`.ad01-runs/` removed. No `inv_r1_` databases remain.

## Remaining gaps

Live qualification still needs a human grant and provider credentials.
The `pending_*` columns in `0016_study_run.sql` stage reservation
semantics that no path enforces yet. The `verify_study` call activates
only after the R3 merge supplies it in `records.py`.

## Re-verification at `98c45a3` (same tree, real PostgreSQL 16)

Per-file, all on disposable or suite-owned databases, zero failures,
zero skips: `test_invr1_study_entry` 5 passed in 15.49s,
`test_invc3_study` 3 passed in 15.81s, `test_invc2_authority` 5 passed
in 11.13s, `test_ad01_traj` 31 passed in 10.83s. No fallout touched;
no owned-path fix was needed.

Public command proven twice. Small shape with restart plus refusal
checks on disposable `inv_r1_cli_33006`:

`.venv/bin/python scripts/inv01_study.py --dsn "dbname=inv_r1_cli_33006
host=/var/run/postgresql user=ubuntu" --out <out>
--agenda-authorized 2000000 --study-root inv-r1-cli --provider
recording --model inv01-study-double --deadline-s 600
--max-trajectories 1 --max-boundaries 1`

First run rc 0 with 3 operations and one `study_authority` row. Same
command rerun rc 0 with operation count unchanged at 3 and the
`inv_r1_study_runs` row identical. Expired wall deadline rerun rc 2
with zero new operations. Exhausted caps (360 model, 24 construction)
rerun rc 2 with zero new operations. Database dropped after the run.

Full shape via `bash /tmp/opencode/inv-r1-full-probe.sh`: study rc 0,
`--recompute` rc 0, full export set present, database dropped. Two
`inv_r1_` databases (`inv_r1_full`, `inv_r1_probe`) predate this
worker and were left untouched. Scratch `.ad01-runs/` removed.
