# inv-g1: r03 restore failures

## Verdict

Pre-existing and environmental. No defect in owned source.

## Root cause

`tests/test_r03_flow.py` helpers `_fresh_db` / `_fresh_domain` /
`_fresh_workflow_shape` issue `CREATE DATABASE` through the admin path of
`SETTLEMENT_TEST_DSN`. Only the two restore tests use them:
`test_restore_rebinds_dbos_workflow_inputs` and
`test_restore_refuses_mixed_recovery_set`. A DSN role without `CREATEDB`
fails exactly those two, identically, with cryptic
`psycopg.errors.InsufficientPrivilege: permission denied to create database`.

## Evidence

- Tip `8a14a46` with a capable DSN
  (`postgresql://ubuntu@/inv_g1_r03?host=/var/run/postgresql`): 8 passed.
- Same tip with a `CREATEDB`-less role over TCP: the two restore tests
  failed identically at `CREATE DATABASE` with `InsufficientPrivilege`.
  (Two checkpoint tests also failed there, but only because a
  password DSN trips the checkpoint script's peer-auth guard. That is a
  probe artifact, not a product defect.)
- Nothing to stash-test: the tip passes and this lane changed no `src/**`,
  so there is no fix to stash and no base-only defect to isolate.

## Change (tests/test_r03_flow.py only)

- New `test_r03_database_prerequisite_explicit`, following the
  `test_database_prerequisite_explicit` pattern in
  `tests/test_ag01_experiment.py`. It exercises the exact CREATE/DROP
  DATABASE capability `_fresh_db` needs and fails with a clear
  `missing database prerequisite` message. The DSN in the message is
  redacted past `@` so password DSNs never leak.
- `_fresh_db` converts `InsufficientPrivilege` on `CREATE DATABASE` into
  the same explicit failure instead of a cryptic traceback.

## Invariant restored

Restore tests fail with a diagnosable prerequisite message when the
database role cannot create databases, instead of cryptic errors.

## Verification

- Failing-before (CREATEDB-less role): prerequisite test plus both
  restore tests fail with `missing database prerequisite`.
- Passing-after (capable DSN): 9 passed in `tests/test_r03_flow.py`.
- No `src/**` change, so no nearby store suite rerun was required.
