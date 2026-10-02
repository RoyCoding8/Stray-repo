# T3 S1 broker/execution/composition — task report

- Base: `8a435ca` (branch `codex/task-s1-broker` start, per assignment).
- Tip: `8859ec1` (this report committed on the same branch).
- Worktree: `/home/ubuntu/AI/Agent-Society-v2-s1-broker` only. No other checkout touched.

## Modified paths (owned only)

- `src/settlement/broker.py` (new, ~800 lines): effect validation, exposure
  schedule, prepare path, dispatch with advance-before-send, receipts,
  cancellation trio, bounded reconciliation, outbox dispatcher, heartbeat,
  recovery, real DBOS attempt workflow + idempotent step functions.
- `src/settlement/launcher_local.py` (new): bounded subprocess launcher,
  operation-derived identity, run-dir recovery inspection, process-group kill,
  scrubbed env, typed-JSON worker outputs, containment=False always.
- `src/settlement/launcher_runsc.py` (new): same interface, probe-gated,
  every dispatch raises IncompatibleVersion, never falls back to local.
- `src/settlement/run.py` (new, ~400 lines): versioned composition algebra
  (sequence/choice/repeat/parallel/join/suspend), recorded-continuation
  interpreter, validated revision, eligibility, continuation migration.
- `tests/test_broker_prepare.py`, `tests/test_broker_dispatch.py`,
  `tests/test_launchers.py`, `tests/test_run_compose.py`,
  `tests/test_broker_dbos.py` (new).

Shared contracts untouched. No changes outside owned paths.

## Outcomes

- `uv run pytest`: **114 passed** (31 pre-existing + 83 new), twice in a row,
  against real PostgreSQL (`settlement_t1broker`, PG16 local) with
  `SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_t1broker?host=/var/run/postgresql`.
- Effect boundaries (§15): death before advance redispatches exactly once;
  death after send never resends and the receipt reconciles; duplicate
  receipt after commit settles once (allocation consumed unchanged);
  domain-commit-before-checkpoint covered by duplicate DBOS workflow ID
  (recorded result, zero new spawns) and idempotent `wf_record` replay;
  lost response retains exposure (`reserved` unchanged) and re-ensure never
  resends; cancel while dispatched keeps uncertain charges with
  requested/worker-stopped/confirmed as distinct states and late receipts
  still admitted; stale ownership refused with no send; restored DB
  predating an effect enters reconciliation instead of resending
  (launcher `prior_send` inspected first, one spawn total).
- Launchers: operation-derived identity reused after recovery (spawn file
  reads `1`); worker env has no gateway/DB/secret keys; 100 KB output
  capped at the admitted 1024 bytes; worker stdout starting with
  `__import__` stays inert data (parse rejected, outcome failure, no file
  created); an 800 ms timeout kills the whole process group (pgid dead,
  no orphan `sleep`); unsupported gvisor profile returns
  incompatible-profile with no send and no silent local fallback.
- Composition goldens: sequence/choice/repeat/join/suspend advance
  continuations exactly as hand-written literals; parallel tracks each
  alternative; join names missing obligations (`["o1","o2"]` →
  `["o2"]` → satisfied); unknown effects, `python`-kind nodes, `exec`
  keys, and depth-7 proposals rejected without import.
- DBOS verdict: **real integration ships** (dbos 2.31.1). `attempt_workflow`
  is one genuine `@DBOS.workflow` per attempt with deterministic structure,
  nondeterministic reads/dispatches inside `DBOS.run_step`, and domain
  mutations keyed by `attempt:generation:round` command identities, against
  a dedicated system database (`settlement_t1broker_dbos`). No faked
  semantics; no outbox-only fallback was needed.

## Limitations / explicitly unverified

- runsc unverified here: `probe_gvisor` reports missing runsc/docker, so
  all gVisor behavior is the explicit IncompatibleVersion path. The real
  launcher slots into `RunscLauncher` (digest/runtime/profile declaration
  already carried) on a runsc host.
- No live gateway: model ops run through `FakeGatewayAdapter`
  (estimated-budget, never hard ceiling) or scripted test doubles.
  A provider adapter reporting `provider_enforced_ceiling=True` is the
  only route to a hard-ceiling model budget.
- `artifact-io` effects validate and reserve but dispatch reports
  `awaiting-artifact-store`: execution belongs to T4's artifact store.
- Executor-kill mid-workflow was not live-tested; recovery rests on DBOS
  recorded-result dedup (tested) plus `recover()` over
  `restart_reconciliation` (tested at broker level).
- Workflow colocated resources: `ATTEMPT_WORKFLOW_RESOURCES` maps
  attempt → launchers/gateway in-process. A recovery in a fresh process
  must re-register them before resuming workflows.

## Contract change requests (for T4/T5)

1. No quarantine registry exists in `0001_schema.sql`; `check_eligibility`
   covers authority version, attempt lifecycle, and investigation
   disposition. A quarantine table/migration is T4/T5's call.
2. `note_worker_stopped` (cancel_state requested → worker_stopped) is
   implemented in `broker.py` via the public `store.transact` envelope
   because no store function covers that transition. Promote to store if
   the shape is accepted.
3. DBOS system database is separate from the domain database by design
   (TECH-DECISIONS §3 namespaces); `migrated_db`-style truncation must
   never touch it.

## API for T5/T6 (all in `src/settlement/broker.py`, `run.py`)

- Prepare: `broker.ensure_operation(dsn, *, operation_id, effect,
  payload, allocation_id, attempt_id=None, execution_version="",
  retries=0)` → `CommandResult` (data: exposure, budget_kind, effect).
  Effects: `model-inference | sandbox-exec | artifact-io |
  observation-adapter | domain-command`; anything else is INVALID_INPUT.
- Dispatch: `broker.dispatch_operation(dsn, operation_id, *,
  launchers={"local-process": LocalLauncher(...), "gvisor":
  RunscLauncher(...)}, gateway=None, ownership_generation=None,
  grant_version=None)` → `DispatchStatus` (dispatch_state,
  sent_this_call, next_decision). Non-prepared states never resend.
- Receipts: `broker.admit_launcher_receipt(dsn, operation_id,
  ReceiptProposal(...))`.
- Cancel: `broker.request_cancel(dsn, op, launchers?)` →
  `broker.note_worker_stopped(dsn, op)` → `broker.confirm_cancel(dsn, op)`.
- Sweep: `broker.heartbeat(dsn, launchers, gateway=None,
  ownership_generation=None, repair_due=False)` → `HeartbeatReport`
  (dispatched/delivered/repaired/deferred_model; never runs inference).
  `broker.dispatch_pending(...)` (outbox + prepared sweep),
  `broker.recover(dsn, launchers)` (post-restart),
  `broker.reconcile(dsn, op, launchers, supervision_left=3)` →
  `ReconcileDecision` (may stay `unresolved-liability`).
- Reads: `broker.read_operation(dsn, op)`, `broker.scan_prepared(dsn)`.
- Workflows: `broker.init_dbos(system_dsn, app_name)` /
  `broker.shutdown_dbos()`; start with `SetWorkflowID(wfid)` +
  `DBOS.start_workflow(broker.attempt_workflow, dsn, attempt_id,
  ownership_generation, composition_dict, max_rounds)`;
  register `broker.ATTEMPT_WORKFLOW_RESOURCES[attempt_id]` first.
- Compositions (`run.py`): `Composition`/`Continuation` (version `run/v1`);
  `run.fresh_continuation`, `run.advance` (events `node_completed` /
  `observation`), `run.register_ops`, `run.pending_invokes`,
  `run.invoke_to_broker_args(node, attempt_id, allocation_id,
  iteration=None)` (op id `attempt:node[:iN]`), `run.revise`
  (validated, inherits allocation/authority/budget, bounded depth),
  `run.check_eligibility(dsn, attempt_id, comp)`,
  `run.record_continuation` / `run.migrate_continuation` (old+new refs
  stored via `install_continuation`).
