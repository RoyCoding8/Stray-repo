# Workstream r02-authority (W-A, coordinator-implemented)

Base `d7b46aa`. The delegated W-A worker died from model-connectivity
flakes before writing anything (worktree verified clean); the coordinator
implemented this slice directly to guarantee delivery. Single owner for all
overlapping broker/store/recovery edits, per the continuation prompt.

## Red-first baseline (pre-fix, all pass asserting bugs)

`reviews/probes/test_review_02.py -k 'sender or fulfillment or delayed or
checkpoint or http_usage'`: 5 passed pre-fix. Post-fix all 5 fail:

- sender: refused before gateway send (fails on the status read against the
  probe's fake DSN — the refusal itself is proven cleanly in
  `test_stale_generation_sender_never_sends`).
- fulfillment: `MISSING_EVIDENCE` with the witness message.
- delayed: the loop now invokes `wf_consume` (the probe's recording stub
  returns None and explodes on `.get` — fails precisely because consumption
  is wired in; clean proof in `test_clean_process_resume_...`).
- checkpoint: fails on the new release step plus the doubled verification
  calls (protocol changed underneath the scripted interleaving).
- http_usage: `actual_cost=None` with `billed: False` in the receipt.
- import-time forgery probe: still passes.

## Changes

- `migrations/0006_recovery_fence.sql` (0004/0005 taken): `control`
  gains `dispatch_paused` + `paused_reason`.
- `store.py`: one absolute deadline across connect/statements/retries/
  refusal journaling in `transact`; `_admission_checks` refuses paused
  dispatch and non-live investigations (withdrawn/fulfilled, amended
  revisions) inside the transition; `_bump_inflight_dispatch` shared by
  `checkpoint_barrier` (pauses + fences pre-barrier senders) and
  `restore_fence` (pauses post-restore); new `resume_dispatch` explicit
  resumption; `checkpoint_verify` fails on pause flips;
  `fulfill_investigation` requires witnessed obligations
  (`{"success": op}` / `{"claim": id}`), exact evidence epoch, and
  unquarantined attempts; new `attempts_with_continuations`.
- `broker.py`: `_revalidate` takes the sender's expected generation and
  refuses stale senders without sending; `ModelRequest` carries
  `dispatch_generation`; unbilled usage settles the full reservation
  (`actual_cost=None`); `_finish_send` admits the actual late receipt plus a
  fence marker; `attempt_workflow` consumes delayed results exactly once per
  round, terminates nodes at retry budget (`:failed` completion +
  observation), and `heartbeat` restores workflow resources on the
  production scheduler path.
- `scripts/checkpoint.py`: fenced twice-verified protocol (barrier, state
  read, dump, verify, write, verify, release-always); workflow stores are
  real DBOS system databases detected structurally, Settlement-shaped stores
  labeled, anything else refused.
- `scripts/restore.py`: `--workflow-target-dsn`; coordinated manifests
  without a target are refused; post-restore dispatch stays paused.
- Tests: new `tests/test_r02_authority.py` (17 tests); generalized
  `test_broker_dbos.py` DSN helpers (any base name); migrated
  `test_r01_recovery.py` (release journal row, explicit resume, preserved
  late receipts), `test_r01_fulfill.py` (unwitnessed obligations refused,
  late receipts admitted), `test_rec_checkpoint.py` (migration list).

## Checks (real PostgreSQL, serial per DB)

- New file: 17 passed.
- `test_r01_recovery test_rec_checkpoint test_rec_restore`: 17 passed.
- `test_broker_dispatch test_broker_prepare test_broker_review
  test_r01_fulfill test_r01c_redispatch test_settle_actual
  test_run_compose`: 65 passed.
- `test_broker_dbos test_state_* test_tx_* test_agenda_repair
  test_launchers test_evidence_epoch`: 50 passed.
- Review probes: 5 fail post-fix for the documented reasons, forgery passes.

## Limitations

- Same-DB fencing is complete; a sender paused on a *different* (old)
  database cannot be stopped by rows — its effects land as attributable
  uncertain receipts and are never auto-retried. Launcher claim files are
  the cross-DB fence where launchers implement them (runsc: W-B).
- runsc/gVisor and live inference never exercised here (no
  credentials/containment on this host).
- `ruff` is not a gate (140 pre-existing errors); no new lint debt added.
