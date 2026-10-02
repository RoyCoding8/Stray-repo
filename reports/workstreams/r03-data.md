# R03-DATA — store deadlines, artifact bytes, overcharge liability

- Base: `20017f2` (review-03 merge). Branch: `codex/r03-data`.
- Worktree: `/tmp/asv2-r03-r03-data` (temp, deleted after merge). DB: `settlement_r03data`.

## Owned requirements and verdicts

- R03-010 CONFIRMED and fixed: `transact` now opens connections in a
  worker thread joined on the remaining command budget (fast failures
  still raise; only a stalled wait returns `UNAVAILABLE_DEPENDENCY`),
  re-arms `statement_timeout` from the remaining budget before every
  statement, and reinstalls timeouts on the refusal-recording path.
- R03-011 CONFIRMED and fixed: new `evidence.check_use_verified`
  refuses artifact-backed claims admitted without an artifacts root and
  re-hashes package bytes when a root is supplied; `fulfill_investigation`
  accepts an optional `artifacts_root` payload field.
- R03-012 CONFIRMED and fixed: `admit_receipt` inserts the receipt first
  and, when settlement is infeasible (e.g. over-reservation), preserves
  the receipt, holds the reservation, and marks the operation
  `observed`/`unresolved` with a `settlement_infeasible` event instead of
  rolling everything back. `broker._finish_send` only acknowledges
  durable delivery when admission applied; otherwise it reports
  `needs-reconciliation`.
- EFF-8 second half assessed HOLDING: seed/subdivide use plain INSERTs,
  so no budget admission can downgrade an older reserved liability;
  duplicate `seed_allocation` now returns a journaled refusal instead of
  leaking `UniqueViolation` (matches `admit_commitment`).

## Tests

- Migrated `test_tcp_connection_wait_outlives_command_deadline` →
  `test_tcp_connection_wait_respects_command_deadline` (bounded result,
  elapsed < 1.5 s against a 200 ms budget; observed ~0.2 s).
- New `test_overcharge_preserves_receipt_and_holds_liability`,
  `test_seed_existing_allocation_refuses_without_downgrade`
  (both in `tests/test_settle_actual.py`),
  `test_fulfill_artifact_claim_requires_root_and_bytes`
  (in `tests/test_r01_fulfill.py`, including a post-fulfillment
  byte-tamper check).

## Checks with outcomes

- `test_settle_actual.py`, `test_r01_fulfill.py`,
  `test_state_allocations.py`, `test_broker_dispatch.py`,
  `test_broker_prepare.py`: all pass on `settlement_r03data`.
- Full verification deferred to the integration suite run.

## Contracts for other streams

- `store.restore_fence` (attempt bump + inflight fence + pause) is
  unchanged and available for restore-path work.
- Release-path `evidence.check_use` (capabilities.py:469) is intentionally
  untouched here; the eval stream applies `check_use_verified` with an
  `evidence_artifacts_root` release argument.

## Remaining limitations

- Filesystem TOCTOU: byte reverification runs during the fulfillment
  transaction, not atomically with the commit.
- Orphaned stalled connection attempts are daemonized and bounded by a
  driver-level timeout, not killed at the command deadline.
