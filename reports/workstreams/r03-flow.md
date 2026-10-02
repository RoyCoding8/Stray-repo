# R03-flow (W-FLOW) workstream — Review-03 findings R03-007/008/009

Worktree: /tmp/asv2-r03-r03-flow, branch codex/r03-flow, base 20017f2.
DB: settlement_r03flow (disposable). Python: /tmp/asv2-r03-impl/.venv/bin/python,
PYTHONPATH=/tmp/asv2-r03-r03-flow/src.

## Step 1 — assessment

All three findings confirmed against production entry points; the defect probes
reproduced pre-fix (3 passed as defect demonstrations).

- R03-007 confirmed. scripts/checkpoint.py `_workflow_barrier`/`_workflow_verify`
  queried only ENQUEUED/PENDING ids; store.checkpoint_barrier unconditionally
  overwrote paused_reason and run_checkpoint unconditionally resumed; store
  checkpoint_verify omitted dispatch_paused from its SELECT while comparing a
  default; scripts/restore.py checked neither workflow dump/manifest
  correspondence nor persisted workflow args.
- R03-008 confirmed. No production caller of attempt_workflow/start_workflow
  exists under src/scripts/experiments (only tests); heartbeat restored
  resources and dispatched but never resumed a waiting workflow.
- R03-009 confirmed. broker.wf_ensure_dispatch exhausted only when failure
  receipts outnumbered retry_max, so retry_max=1 with one failure redispatched
  the same immutable operation until the round cap.

## Step 2 — fixes

- R03-007: DBOS barrier/verify now capture full workflow statuses plus an
  operation_outputs step digest; settlement barrier snapshots live continuation
  digests; checkpoint_barrier preserves a pre-existing pause owner and records
  pre_paused/pause_owner; resume_dispatch honors only_reason so checkpoint
  release cannot resume a restore-owned pause; checkpoint_verify selects and
  compares dispatch_paused/paused_reason plus continuations; run_checkpoint
  releases only pauses it owns; manifest records source DSNs; run_restore
  verifies restored domain/workflow state against the manifest barrier and
  rebinds DBOS workflow inputs from source to target DSNs.
- R03-008: broker.wake_waiting_workflows consumes newly observed outcomes for
  unresolved continuations under idempotent wake:{attempt}:{op}:{receipt}
  journal identities and resumes via deterministic attempt:{id}:gen{generation}
  workflow IDs; heartbeat runs it after dispatch/repair. Composition is read
  from attempts.composition persisted at acquire_work.
- R03-009: retries use fresh {base}:retry{k} operation identities keyed off a
  durable per-node tries log; proven failure beyond retry_max advances an
  explicit terminal failed decision; uncertain (receipt-less) operations never
  gain retry identities. Removed the failed-count exhaustion branch.

## Probes migrated (one-line comment each, corrected contracts only)

- test_dbos_checkpoint_detects_changed_step_results
- test_heartbeat_wakes_waiting_workflow_through_repair_path
- test_positive_retry_budget_terminates_without_rereading_failed_op

New regressions: tests/test_r03_flow.py (8 tests; real-DB checkpoint/restore,
scheduler-subprocess restart wake, real-launcher bounded retry; DBOS-shaped
schema with scripted executor progress, no launched executor).

## Verification

- tests/test_r03_flow.py + reviews/probes/test_review_03.py: 20 passed.
- Area files (r02_authority, broker_dispatch/prepare/review/dbos, adv_broker,
  r01_recovery, rec_checkpoint/restore, reconcile_reset, run_compose,
  agenda_repair/policy, tx_outbox/journal, state_operations): 111 passed.
- Full suite not run per lane instructions; no DB besides settlement_r03flow
  and its scratch siblings used.

## Residual risks

- Live-DBOS-executor interleaving during backup is scripted via SQL, not a
  running executor; a lane owning DBOS launch should add that run.
- Wake resume needs DBOS launched in the repairing process; otherwise resume
  is deferred while continuation advancement stays durable.
- Attempts acquired without persisted composition are skipped by the wake scan.
