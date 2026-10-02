# T2 S1 durable state — task report

- Base: `783dc9f` (branch `codex/task-s1-state` start, per assignment).
- Code commit: `1b06a2a` — migrations, `store.py`, all `test_tx_*` / `test_state_*`.
- This report: follow-up commit on the same branch (tip = this commit).
- Worktree: `/home/ubuntu/AI/Agent-Society-v2-s1-state` only. No other checkout touched.

## Modified paths (owned only)

- `migrations/0001_schema.sql` (new)
- `src/settlement/store.py` (new, ~810 lines, single deep module)
- `tests/test_tx_journal.py`, `tests/test_tx_events.py`, `tests/test_tx_outbox.py`,
  `tests/test_state_allocations.py`, `tests/test_state_investigations.py`,
  `tests/test_state_operations.py` (new)

Shared contracts untouched. No contract change requests.

## Outcomes

- `uv run pytest`: **31 passed** against real PostgreSQL
  (`settlement_t1state`, PG16 local; SQL is portable, no PG18-only features).
- Adversarial checks covered: last-units race (8 threads × 5 on 10 units →
  exactly 2 applied, 6 `insufficient_resources`, balances `(10, 0, 10)`);
  duplicate identity same-payload → `already_applied` with original data,
  different-payload → `ConflictPayload` raised; stale `expected_revision` and
  stale ownership generation refused while observation submission stays open;
  duplicate receipt idempotent, conflicting receipt preserved in
  `receipt_conflicts` with `reconcile_state='conflict'`, settle-once verified;
  outbox intent survives pre-delivery crash, redelivers idempotently
  (`record_delivery` twice → second `already_applied`); cursor pagination equals
  full scan and a late-committing transaction's event is never skipped
  (epochs assigned under the control-row lock in commit order, so no gaps);
  fulfillment twice refused; Hypothesis sequences of reserve/settle/release
  (40 examples) hold `consumed + reserved <= authorized`.
- Full requirement map: TX-1 (one SERIALIZABLE txn through locked control row
  per transition), TX-2 (whole-txn retry on 40001/40P01 bounded by
  `Command.deadline_ms`; journal-race `UniqueViolation` re-reads),
  TX-3 (locked `event_epoch` increment + ordinal; `read_events` cursor),
  TX-4 (`evidence_epoch` payload hook + `register_evidence_change`),
  TX-5 (`scan_outbox` / `claim_outbox` / `record_delivery`, enqueue in the
  same commit), TX-6 (fulfill checks authority/generation/revision/unfulfilled,
  one terminal fulfillment per revision); IF-1, IF-2, IF-5; EFF-1 (reservation
  precedes dispatch; settle converts once; `unknown` retains exposure),
  EFF-2 (`dispatching` + outbox intent committed before any send),
  EFF-4 (duplicate/conflict/settle-once); BOOT-5 (`restart_reconciliation` from
  registry tables only); money as scaled integers (`BIGINT` + `amount_scale`).

## Limitations / notes for reviewers

- Refusals (stale/insufficient/unauthorized/invalid) are journaled and replayed
  with their original code; only stored `applied` maps to `already_applied` on
  duplicate. Request-identity reuse with a different payload raises
  `ConflictPayload`; semantic conflicts (e.g. clashing operation intent) return
  `invalid_input` results instead.
- Amend-after-fulfill is allowed and opens a new revision (fulfillment is
  terminal per revision, not per investigation); amend/withdraw on withdrawn
  stays refused. Attempt deadline is stored, not enforced — T6/broker policy
  decides expiry.
- `transact` re-creates a missing `control` row (the shared `migrated_db`
  fixture truncates it between tests); harmless in production.
- Artifact/claims/trial tables are intentionally absent — T4/T5 add their own
  migrations (`0002`, …) on top.

## Public surface for T3/T4 (all in `src/settlement/store.py`)

Calling convention: every mutating function takes `(dsn: str, cmd: Command)`
with inputs in `cmd.payload`, returns `CommandResult` (`code` is a shared
`ResultCode`). Payload keys per function:

- Control/grants/evidence: `get_control(dsn)`, `seed_grant` (`version`,
  `charter_text`, `authority_grant`, `envelopes`),
  `register_evidence_change` (no keys). Any payload may carry `evidence_epoch`
  for the TX-4 staleness check.
- Stewardship IF-1: `admit_commitment` (`investigation_id`, `objective`,
  `scope`, `obligations`, `sponsor`, `origin`), `amend_commitment` (+
  `cmd.expected_revision`), `withdraw_commitment`, `seed_allocation`
  (`allocation_id`, `parent_id?`, `domain`, `epoch?`, `authorized`,
  `amount_scale?`, `max_occupancy?`, `owner_scope?`), `subdivide_allocation`
  (`parent_id`, `child_id`, `authorized`, …), `reserve` (`allocation_id`,
  `reservation_id`, `amount`, `operation_id?`), `settle_reservation`
  (`reservation_id`, `outcome`), `release_reservation` (`reservation_id`).
- Investigations/attempts IF-2: `acquire_work` (`attempt_id`,
  `investigation_id`, `allocation_id?`, `composition?`, `model?`, `env?`,
  `owner?`, `deadline?`) → `data.ownership_generation`;
  `submit_observation` (no generation check), `install_continuation`
  (`attempt_id`, `ownership_generation?`, `continuation_ref`),
  `complete_attempt` (`attempt_id`, `ownership_generation?`,
  `outcome=completed|failed|cancelled`), `suspend_attempt`,
  `resume_attempt`, `fulfill_investigation` (`investigation_id`,
  `attempt_id?`, `ownership_generation?`, `authority_version?` +
  `cmd.expected_revision`).
- Operations IF-5: `prepare_operation` (`operation_id`, `attempt_id?`,
  `allocation_id?`, `reservation_id?`, `exposure?`, `operation` dict,
  `execution_version?`), `advance_dispatch` (`operation_id`, `launcher_id?`,
  `provider_id?`, `grant_version?`, `ownership_generation?`) — enqueues
  `dispatch:<id>`; `admit_receipt` (`operation_id`, `receipt_identity`,
  `content`, `outcome`, `provenance?`), `request_cancellation`,
  `confirm_cancellation`, `reconcile_operation`
  (`operation_id`, `resolution=reconciled|unresolved`).
- Dispatcher TX-5: `scan_outbox(dsn, limit)`, `claim_outbox`,
  `record_delivery` (payload `workflow_identity`).
- Reads: `read_events(dsn, cursor_epoch=0, cursor_ordinal=-1, limit=100)` →
  `{events, cursor_epoch, cursor_ordinal}`; `restart_reconciliation(dsn)` →
  `{unfinished_operations, live_attempts, execution_versions}`.
- Generic entry: `transact(dsn, cmd, fn, *args)` for future transitions reusing
  the journal/lock/retry envelope.
