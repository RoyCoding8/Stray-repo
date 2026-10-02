# INV-X-AG01: test_ag01_experiment.py 24-failure root cause

Branch: `wt/inv-x-ag01`. Worktree: `/home/ubuntu/AI/Agent-Society-v2/.worktrees/inv-xag01`.
Base commit: `5f75ef6`.
Owned paths only: `experiments/agenda01/**`, `tests/test_ag01_experiment.py`, this note.
No `src/**`, `scripts/**`, `pyproject.toml`, or evidence changes.

## Reproduction

Full file with the provisioned database is green: 36 passed in 166 s.
The reported failure was reproduced exactly by pointing the suite at a
missing base database:

`SETTLEMENT_TEST_DSN=postgresql://ubuntu@/inv_xag01_nonexistent?host=/var/run/postgresql`
`python -m pytest tests/test_ag01_experiment.py -q` gives 24 failed,
12 passed in 6 s. Every failure is `psycopg.OperationalError: FATAL:
database "inv_xag01_nonexistent" does not exist`.

## Root cause (one sentence)

The suite assumes the `BASE_DSN` database exists and the role can
`CREATE`/`DROP` databases but never asserts it, so an unprovisioned or
unreachable database surfaces as 24 cryptic `psycopg` errors instead of
one explicit prerequisite failure.

Why this and not a system bug: the failure count is identical with and
without lane changes because connectivity is code independent; every one
of the 24 failures raises at the first `psycopg.connect`/`CREATE
DATABASE` before any settlement logic runs; the 12 survivors are exactly
the tests that never open a database connection. The observation method
(`simulate_value`, `public_observation`) and the scored paths are sound:
all 36 pass against the provisioned `agenda01_exp` database.

## Fix

One added test, zero changed tests:
`test_database_prerequisite_explicit` in `tests/test_ag01_experiment.py`.
It drops/creates/drops a disposable `agenda01_prereq_<pid>` database
through the same `runner.create_db`/`runner.drop_db` helpers the suite
uses, failing with `missing database prerequisite: CREATE/DROP DATABASE
failed via BASE_DSN=...` naming the cause. Placed directly before the
first database test so it is the first failure in file order. A
restricted-role variant was not executed because creating roles would
mutate shared server state; the create/drop probe covers that class by
construction with distinct messages per step.

## Verification

Red: new test fails in 0.6 s under the missing-database DSN with the
explicit prerequisite message above.
Green: new test passes in 0.9 s against the provisioned database.
Full file after the fix: 37 passed in 191 s against the provisioned database.
No `inv_xag01_*` databases created or retained; the probe is dropped in
the test. Pre-existing stale `agenda01_scratch_*` databases from other
PIDs were left untouched.
