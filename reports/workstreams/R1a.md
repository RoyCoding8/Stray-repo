# R1a — R01-001 / R01-002 admission authority fixes

Branch: `codex/review01-r01-admit`. Owned paths only:
`src/settlement/store.py`, `src/settlement/broker.py`,
`tests/test_r01_authority.py` (+ this report).

## What changed

R01-001 (`fbec1c5`): the actual sender holds exclusive durable dispatch
authority. `broker._send_model` returns existing state on
`ALREADY_APPLIED` with zero new `gateway.infer` calls; only `APPLIED`
authorizes a send. `broker._advance` uses a unique request identity per
dispatch attempt, so race losers replay state instead of sending while a
legitimate post-`reset_dispatch` redispatch re-admits under a fresh
identity. `store.advance_dispatch` reports `admitted` True/False in its
result data. No provider idempotency assumption.

R01-002 (this commit): grant freshness, owner generation, and
quarantine/release eligibility are unavoidable in the authoritative
`advance_dispatch` transition. `prepare_operation` pins the current
`authority_version` into the stored operation body (`_authority_version`,
outside the intent digest, so prepare idempotency is unchanged);
admission refuses when the pin no longer equals current authority, when
a supplied `grant_version` is stale, when a supplied
`ownership_generation` mismatches, and when the bound attempt carries a
pinned capability present in `quarantine_registry`. Missing values are
resolved authoritatively inside the transaction (grant to the pin rule,
generation to the attempt's current generation, quarantine unconditionally
from state), never skipped — this keeps every existing direct
`advance_dispatch` caller green. Attempt lifecycle (`running`/`suspended`)
is still enforced. Scheduler (`dispatch_pending`) and workflow
(`wf_ensure_dispatch`) paths inherit the checks with no signature changes;
`run.check_eligibility` remains a preflight only.

## Test results (real PostgreSQL 16, `settlement_r01admit`)

`tests/test_r01_authority.py`: 17 passed — probe-2 replica (APPLIED +
ALREADY_APPLIED, same request id, exactly one `gateway.infer`), 8-way
threaded model race (exactly one provider request, once-settled
reservation), store `admitted` True/False, crash before admission (prepared,
single redispatch send), crash after send and during receipt admission
(no resend, `unresolved-liability`, exposure retained); scheduler +
workflow + direct-model refusal matrices for grant revocation, pinned
capability quarantine, and stale owner generation (zero sends, operation
stays `prepared`); validation-vs-admission grant race (`stale-grant`);
missing-input resolution contract.

Existing suite: 242 passed on `settlement_r01admit` (full `tests/`
minus `test_broker_dbos.py`/`test_s0_gateway.py`); those two files pass
separately (19 passed) on alias DB `settlement_t1broker`, whose name the
dbos fixture requires — a pre-existing environment constraint, not a code
regression. No existing test was modified.

## Contract requests (other owners' files, not touched)

- `reviews/probes/test_review_01.py` probe 2
  (`test_model_dispatch_sends_on_both_advance_outcomes`) asserts the old
  defective double-send and now fails; it is superseded by
  `test_r01_001_replayed_advance_sends_zero_gateway`. Preserve or retire it
  explicitly; it is no longer a correctness test.
- `_send_sandbox` / `_run_inline` still treat `ALREADY_APPLIED` as
  send permission. Sandbox is partly covered by launcher-level atomic
  claim (`test_concurrent_dispatch_spawns_exactly_once`); extending the
  R01-001 gate there is recommended follow-up outside this scope.
- `run.check_eligibility` (incl. composition `authority_version`) stays a
  preflight; composition authority is not threaded into `wf_ensure_dispatch`.
  Operation-level pin covers revocation at admission.
- Owner generation is per-attempt immutable (only `acquire_work` mints it),
  so "changed generation" is enforced as supplied-vs-current mismatch;
  there is no in-place bump to race against — documented, not implemented.

## Open risks

- Fake gateways/adapters stand in for live provider semantics; no live
  inference containment claim is made.
- Quarantine check assumes S3 migrations applied (true for `migrated_db`
  and production migration sets); no `UndefinedTable` fallback was added.
- Journal rows grow one per dispatch attempt by design (unique advance
  identity); no retention change made.
