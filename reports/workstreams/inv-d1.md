# Workstream inv-d1: resume reclaims receipt-less dispatching ops (INV-C1)

Owner: Nightjar. Worktree `.worktrees/inv-d1`, branch
`wt/inv-d1-dispatch`, base `b67ecbf`. Owned paths only:
`src/settlement/broker.py` (the `dispatch_operation` resume path),
`tests/test_invd1_dispatch.py` (new), this note. Untouched: `store.py`,
other `src/**`, `experiments/**`, `scripts/**`, other tests,
`pyproject.toml`, `uv.lock`, `reports/PLAN.md`, `evidence*/**`.

## Root cause

Kill during validation dispatch leaves the validation operation in
`dispatching` with no receipt. On resume `dispatch_operation` returned
early for every non-`prepared` row, so the op never relaunched,
`run_member_out_of_process` read no result, the interruption scored as
a validation failure, and the run spent a repair plus a fresh lineage.
Reproduced on this tip through the public AD01 trajectory with a real
process-group SIGKILL: control `calls 1, lineage {1}, ops 2, receipts
2, retained` became resumed `calls 2, repair op present, receipts 3`.

## Fix

`dispatch_operation` now routes non-`prepared` rows through
`_resume_dispatching` (+39/-1 lines, receipt construction and settle
lines untouched). A `dispatching` op with zero receipts relaunches via
the existing `redispatch_after_reset` (generation-fenced reset, so a
concurrent resume loses the reset and never sends) only when the
launcher proves nothing settled: no result file, nothing live, and
`prove_never_sent` (or, for launchers without that contract, no
`prior_send`). Any receipt, a live execution, a recovered result, a
missing launcher, and all model-inference ops keep the old early
return, so settled ops keep exactly-once and providers are never
re-invoked on unprovable state.

## Gates

`tests/test_invd1_dispatch.py`: 6 passed (real Postgres `inv_d1_*`,
dropped after; real `LocalLauncher`; real process-group SIGKILL on the
public path with kill-point verification and bounded fresh-DB retries).

- Receipt-less `dispatching` sandbox op relaunches exactly once
  (observed, one spawn, one receipt; third dispatch sends nothing).
  Failed before the fix with `dispatching / sent_this_call=False`.
- Op with a decided receipt, op with a launcher-side result but no DB
  receipt, and receipt-less model op never resend (pass before and
  after; pins `test_death_after_send` behavior at this layer).
- Public path, kill during validation: resumed run is identical to the
  uninterrupted control (`model_calls 1`, `construction_calls 1`,
  `dev_episodes 1`, same op ids and states, same receipt ids,
  `retained`, zero repair ops, zero new model calls in the resume
  process). Failed before the fix with a `construct-l1-repair` call.
- Public path, kill after validation receipt (pre-boundary-publish):
  resumes `retained` and identical with zero new model calls.

Nearby, unmodified: `test_invc2_recovery.py` 3 passed,
`test_broker_dispatch.py` plus `test_r01c_redispatch.py` 15 passed
with `SETTLEMENT_TEST_DSN` on disposable `inv_d1_nearby` (dropped
after; 13 skip without the variable, pre-existing), `test_aled_campaign.py`
resume/lineage/cap/identity selection 7 passed.

## Boundaries

- A kill landing after the launcher spawns (stale pid claim, dead
  child, no result) still parks for reconciliation instead of
  relaunching: clearing a stale launcher claim needs launcher-side
  support outside this lane. The committed kill test verifies the
  pre-spawn staging (dispatching, zero receipts, zero launcher files)
  and retries on a fresh DB otherwise.
- No live inference or containment validation; recording doubles at
  the provider seam only.
