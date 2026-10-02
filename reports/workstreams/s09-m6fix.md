# S09-M6fix: binding-aware run_use plus versioned use identity

Base is 9f88fd1. This lane fixes independent review findings F1 plus F2
inside the owned regions only. No driver, executor, pilot, or CLI files
changed.

## Owned files

- experiments/ad01/trajectory.py run_use region
- experiments/ad01/selection.py helper wiring only (helper already
  existed; wiring lands at the run_use caller)
- tests/test_s09m6fix_bind.py red-first gates
- reports/workstreams/s09-m6fix.md this report

## Root cause

F1: public run_use called the binding-aware selector with repertoire
plus task only, so it always took the legacy first family match while
the active binding held the revised version. The dsn the caller passed
for execution never reached selection.

F2: run_use minted every use operation as ad01-campaign-task with no
method version, so a second revision on the same target reused the
settled operation and the broker returned the old receipt instead of
executing the new bytes. The versioned helper sat unused in
selection.py.

## Behavior

run_use takes an optional release_id and routes selection through
_select_member with dsn plus release, so the CLI path selects exactly
what direct select_member selects. Every use operation is minted with
versioned_use_op_id over campaign, task, and the selected member
capability id. Retry of one logical action reuses its identity through
the settled receipt. An intentional revision on the same target mints
a new attempt identity and executes the new bytes. Identity format
stays under the cost_union ad01-campaign-use prefix, so accounting is
unchanged.

## Gates

Run from the worktree root with uv and disposable s09_m6f_ databases.

- tests/test_s09m6fix_bind.py 4 passed. Premise guard proves direct
  selection follows the binding. F1 proves public run_use selects
  revised bytes in process and in a fresh process under the active
  binding. F2 proves retry reuses identity while a second revision
  mints a new identity and executes new bytes with different output.
- tests/test_s09m34_bind.py 2 passed.
- tests/test_s09m34_cycle.py 3 passed.
- tests/test_s09m1_driver.py 2 passed.
- Nearby suites 79 passed. test_ad01_traj plus test_aleb_construct
  plus test_bacq_method plus test_s89a3_closeout plus
  test_bdr01_host_boundary plus test_aled_campaign 64 passed.
  test_inv_c_qualification plus test_s09m34_visibility plus
  test_s09m34_exposure 15 passed.
- tests/test_invr3_export.py fails identically on the pristine base
  with missing database inv_r3_export. Pre-existing environment issue,
  unrelated to this lane.

Red-first evidence: before the fix the three finding tests failed with
run_use rejecting release_id, the fresh probe selecting stale bytes,
and the second revision reusing the settled operation. No live
inference ran. No secrets committed. Scratch .ad01-runs removed. The
s09_m6f_bind database drops after the module.

## Gaps

The CLI use subcommand threads dsn but no release flag, so exact
release pinning from the command line goes through run_use callers
that pass release_id. Single-release stores already agree. Legacy
unversioned use operation ids settled before this fix keep their old
identity under retry.
