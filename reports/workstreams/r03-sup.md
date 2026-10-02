# R03-sup (W-SUP) workstream — Review-03 findings R03-001/002

Branch: `codex/r03-sup`, base `20017f2`. Worktree: `/tmp/asv2-r03-r03-sup`
(temp). DB: `settlement_t1broker` (shared disposable integration DB).
Python: `/tmp/asv2-r03-impl/.venv/bin/python`,
`PYTHONPATH=<worktree>/src`.

## Dispositions

Both findings assessed **confirmed** against production entry points
(`dispatch_operation` → `_send_sandbox` → `RunscLauncher.dispatch` →
`exec_profile.run_gvisor`). No rebuttals.

- R03-001 confirmed. The generation file was checked mid-preparation
  (`launcher_runsc.py` old line 361) and the sender then launched
  unconditionally; the review's scripted interleaving (newer generation
  claims between check and send) reproduced through the real launcher
  method with only container execution doubled.
- R03-002 confirmed. `spawn_supervisor` returning `None` still executed
  and could report success with `supervised=False`; on timeout a failed
  `docker stop` killed only the Docker CLI while tracking was dropped and
  `is_live` read false from the mere existence of a result.

## Changes

- `src/settlement/launcher_runsc.py`: single final pre-send ownership
  check after all file writes; a superseded stale sender unwinds its
  container claim and supervise file and is refused
  `superseded-generation`, so the newer generation resumes on retry
  (early re-read deleted as subsumed). Same-host concurrent starts keep
  the deterministic docker `--name` collision as executor-side backstop.
- `src/settlement/exec_profile.py`: supervisor creation failure fences
  via `terminate_verified` and returns `supervision-unavailable` (never
  success); timeout path uses `terminate_verified` with tri-state
  `stop_verified`; docker control ceilings named as constants with
  `STOP_SETTLE_S` (30 + 2*15 + 15 + 5 = 80).
- `src/settlement/launcher_runsc.py` (tracking): container/supervision
  tracking retained while `stop_verified` is unknown; `is_live` consults
  the runtime while tracking is retained; `enforce_deadlines` re-verifies
  retained exposures and releases them once death is established.
- `src/settlement/broker.py`: `_sandbox_exposure` accounts
  `STOP_SETTLE_S` instead of the fixed 5 s allowance.
- `src/settlement/launcher_runsc.py` (`_interpret`): launcher-reported
  `detail["error"]` forces the failure verdict/parse (covers the
  fast-exit race where returncode alone would read success).

## Probes migrated (one-line comment each, corrected contracts only)

- `test_stale_sender_refused_when_generation_advances_before_send`
  (was `test_new_generation_cannot_stop_sender_past_file_check`):
  stale sender refused, no executor call, newer generation resumes.
- `test_supervisor_start_failure_refuses_execution`
  (was `test_execution_proceeds_when_supervisor_cannot_start`):
  container fenced, `supervision-unavailable`, verdict failure.
- `test_verified_stop_releases_tracking` /
  `test_unverified_stop_retains_tracking_until_termination`
  (split of `test_timeout_loses_tracking_without_proving_container_stopped`).

New regressions: `tests/test_r03_sup.py` (4 tests against a shim docker
runtime: fail-closed fence, retain-then-release repair loop, end-to-end
generation fence with exactly one executor `run`, exposure formula).
Migrated pins: `test_broker_dispatch.py` reservation `11` →
`5 + STOP_SETTLE_S + 1`; `test_broker_prepare.py` exposure `28` →
formula; `test_s3_experiment.py` quarantine fixture funds the honest
bound (100 → 1000).

## Verification

- `reviews/probes/test_review_03.py` (all) + `tests/test_r03_sup.py` +
  `tests/test_r02_exec.py` + `tests/test_broker_prepare.py`: green.
- Full suite on `settlement_t1broker` (minus nothing): see
  `reports/VERIFICATION.md` R03 section (integrated run).

## Residual risks

- Generation change during `run_gvisor` itself (past the final file
  check) relies on the docker `--name` collision on shared hosts; cross-host
  old-sender fencing needs operator `stop()` plus restore fencing.
- Crash between container-claim write and result write leaves a
  claim-without-result state recoverable via `stop()` (pre-existing shape).
- Writable output/scratch limits need a real runsc host (blocked here).
