# ENG-INV-A — durability / recovery / ops sweep (settlement store, run algebra, checkpoint/restore, scheduler, manifest, probe, leases/recovery migrations)

- Base: `f478143`; branch: `codex/eng-inva`.
- Worktree: `/tmp/asv2-eng-inva` (only directory written).
- Identity: private (`Nightjar`); unchanged.
- Skill: `diagnosing-bugs` loaded first; every confirmed defect has a red-capable repro (throwaway probes in `/tmp/probe_inva*.py`, kept out of the repo) converted to a committed regression test that was shown to fail on base and pass on the fix.
- Databases: `settlement_enginva` (probes), `settlement_enginva_test` (pytest via `SETTLEMENT_TEST_DSN`); `uv sync --extra test` in the worktree. Real PostgreSQL 16 for all state/recovery claims. No live inference; no credentials anywhere.

## Disposition summary

- Confirmed and fixed: ENG-INVA-01 (P1), ENG-INVA-02 (P2), each with a regression test.
- Confirmed and ledgered (P3–P4, no code change): ENG-INVA-03 … ENG-INVA-09.
- Rebutted with evidence (not defects): concurrent-duplicate-prepare race; checkpoint intruder acceptance; kill-resume state loss; `_db_state` empty-control crash.
- No migration numbering change; none needed (no renumber request filed).

## Findings ledger

### ENG-INVA-01 (P1, confirmed/fixed) — receipt identity not bound to operation
- Trigger: `admit_receipt` with a `receipt_identity` + content already recorded for operation A, submitted for operation B.
- Expected: refusal or conflict record against B.
- Actual (base): `ALREADY_APPLIED` "duplicate receipt" attributed to B, while B has zero receipts (`operation_receipts(B) == []`, B's `reconcile_state` untouched). A real effect's evidence for B is silently dropped and the caller is told it is recorded.
- Root cause: the duplicate branch compared only `content_digest`, never `operation_id` (`src/settlement/store.py`, `admit_receipt`).
- Consequence: evidence misattribution; B stalls unreconciled with exposure retained (fail-closed financially, evidence lost).
- Fix: same-identity admission is a duplicate only when both `operation_id` and `content_digest` match; otherwise it follows the existing conflict path (`receipt_conflicts` + `reconcile_state='conflict'` + `operation.receipt_conflict` event). Fail-closed, one condition.
- Repro: `/tmp/probe_inva1.py` probe A. Regression: `tests/test_inva_recovery.py::test_receipt_identity_bound_to_operation` (fails on base, passes on fix) plus `test_receipt_duplicate_same_operation_still_acknowledged` (passes both, guards the preserved fast path).
- Note: the broker path builds `request_id` from (identity, content digest), so cross-op replays via broker surface as `ConflictPayload`; the store boundary itself now refuses to misattribute.

### ENG-INVA-02 (P2, confirmed/fixed) — `reconcile_operation` strands a merely-prepared operation
- Trigger: `reconcile_operation` on an operation in `prepared` (never dispatched).
- Expected: refusal — there is nothing dispatched to reconcile.
- Actual (base): `APPLIED`, `dispatch_state` becomes `reconciled`; the op can never dispatch afterward (`advance_dispatch` → `INVALID_INPUT`). REC-4/repair misuse permanently destroys the op's future.
- Root cause: no dispatch-state guard in `store.reconcile_operation`.
- Fix: refuse `prepared` and `cancelled` with `SettlementError` (bounded `INVALID_INPUT` result). `dispatching`/`sent`/`unresolved`/`observed` still reconcile — this matches the only production caller (`broker.reconcile`, which returns `awaiting-dispatch` for `prepared` and `already-terminal` for `observed`/`reconciled`/`cancelled` without calling the store), and the existing `test_r01_fulfill.py` case that reconciles from `observed`.
- Repro: `/tmp/probe_inva1.py` probe B. Regression: `tests/test_inva_recovery.py::test_reconcile_prepared_operation_refused` (fails on base, passes on fix) plus `test_reconcile_dispatched_operation_still_applies` (passes both).

### ENG-INVA-03 (P3, confirmed/ledgered) — `seed_allocation` leaks raw `CheckViolation` on negative inputs
- `seed_allocation` with `authorized: -5` (or `max_occupancy: -1`) raises raw `psycopg.errors.CheckViolation` instead of the documented bounded `CommandResult`. Siblings (`seed_grant` version, `subdivide_allocation` amount, `_take_reservation` amount) validate app-side and return typed errors. Fail-closed (nothing journaled, txn rolls back) but violates the `(dsn, cmd) -> CommandResult` contract and leaks DB internals. No fix per P3-ledger scope; recommended fix is app-side positivity checks mirroring `subdivide_allocation`.

### ENG-INVA-04 (P3, confirmed/ledgered) — post-settlement contradictory receipt under a new identity is not flagged
- After a `success` receipt settles a reservation, a later `failure` receipt with a *different* identity is stored with detail "receipt recorded, reservation already settled"; `reconcile_state` stays `none`. Both receipts remain queryable and `run.operation_outcome` reports `unknown`, so the contradiction is observable but nothing flags it (same-identity contradictions do get `conflict`). The broker owns late-receipt policy (`broker.py` late/fenced receipt paths), so store semantics were left unchanged. Evidence: `/tmp/probe_inva3.py` probe D output.

### ENG-INVA-05 (P4, confirmed/ledgered) — `Composition.max_depth` unenforced on initial validation
- `max_depth` (default 4) is enforced only by `revise()`; `validate_composition` checks duplicate node ids and join targets but not depth, and the production path (`broker.attempt_workflow`) uses `model_validate` without `validate_composition`. Absurd depths fail closed at parse time (depth-300+ → pydantic `ValidationError`); moderate depths (tested 50) validate and interpret fine with linear recursion. No fix; if the bound is meant to be load-bearing, enforce it in `validate_composition` and route creation through it.

### ENG-INVA-06 (P4, confirmed/ledgered) — unbounded waits on read-only paths
- `get_control`, `allocation_status`, `scan_outbox`, `read_events`, `restart_reconciliation`, `operation_receipts`, `attempts_with_continuations` (store.py) and `check_eligibility`, `operation_outcome` (run.py) connect/query with no `connect_timeout`/`statement_timeout`, unlike `transact`'s deadline/lock-timeout/statement-timeout machinery. A wedged DB hangs operator/recovery reads forever. No fix per scope.

### ENG-INVA-07 (P4, confirmed/ledgered) — unbounded growth, no pruning
- `command_journal`, `domain_events`, `outbox` (delivered rows retained), `attempt_observations`, `receipt_conflicts` grow without bound; `attempts.continuation_ref` grows per repeat iteration (one key per iteration, bounded only by `max_iterations`); `acquire_work` generations and attempts per investigation unbounded. Schema review + probe evidence; no workload measurement taken. No fix per scope.

### ENG-INVA-08 (P3, pre-existing, for coordinator) — `test_r02_authority.py` fixture builds an unparseable DSN
- `_sibling_dsn`/`_make_database` use `urlunsplit` with an empty netloc, which drops the `//` (`postgresql:/postgres`), so psycopg rejects it with `ProgrammingError: missing "=" after ...`. Fails identically on base (verified: 14 passed + same 3 errors with base `store.py`). Only manifests with socket-style DSNs; TCP DSNs have a netloc and work. The remaining DBOS tests additionally need a TCP/SQLAlchemy path unavailable here. Test file is outside this lane's owned paths; not edited.

### ENG-INVA-09 (P4, confirmed/ledgered) — orphaned connection attempt leaks on connect deadline
- `_connect_before` daemonizes a connection attempt that outlives the caller deadline; if it later succeeds, the connection is never closed (bounded: one socket per deadline expiry, GC-timed). No fix per scope.

## Rebutted with evidence (not defects)
- Concurrent duplicate `prepare_operation` (8 threads, distinct request ids, same op): 1 `applied` + 7 `already_applied`, no exception. The single control-row `FOR UPDATE` lock serializes all writers, so the check-then-insert race cannot interleave; journal-PK races retry through the `found` path. (`/tmp/probe_inva2.py`.)
- Checkpoint accepts an intruder write: refused — `run_checkpoint(..., _between=intruder)` exits nonzero with `barrier violated: events moved ... journal moved ...`. Journal count is the catch-all movement detector, including for `SettlementError` paths that also journal. (`/tmp/probe_inva3.py`.)
- Kill-and-resume loses state: no in-memory state exists to lose — `restart_reconciliation` in a fresh process surfaces the `dispatching` op and live attempt from persisted rows only; stale dispatchers are fenced by `_dispatch_generation` bumps (`_revalidate` → `stale-dispatch-generation`) plus `restore_fence` ownership bumps and the persisted dispatch pause. (`/tmp/probe_inva3.py`.)
- `_db_state` crashes on a missing control row: unreachable — `run_checkpoint` establishes the barrier (which inserts the control row) before reading state.

## Coverage matrix (techniques A–H per owned file)

| File | Techniques used | Evidence | Disposition |
|---|---|---|---|
| `src/settlement/store.py` | A (tx/control-row map, op lifecycle), B (digests, identity binding, boundary values incl. negative money), C (8-thread race, kill-resume, barrier/fence, journal-outbox-receipt reconciliation under duplicates, bounded transact waits, orphan leak), D (pause/grant/ownership fencing), F (4 new + neighboring suites), G (read-path timeouts, growth), H (dead `is None` check after `_get_attempt`, `assert last` unreachable in scheduler — see scheduler row) | probes 1–3 outputs; `tests/test_inva_recovery.py` (4); suites below | ENG-INVA-01, -02 fixed; -03, -04, -06, -07, -09 ledgered |
| `src/settlement/run.py` | A (algebra/frontier map), B (event validation, forbidden-key scan, depth), C (continuation resume from persisted ref only; `suspend_for_barrier`), F (`test_run_compose`, r01 barrier tests), G/H (max_depth note) | depth probes (50 ok, 300+ pydantic-refused); 8 passed `test_r03_flow.py` incl. scheduler CLI | ENG-INVA-05 ledgered; no change |
| `scripts/checkpoint.py` | A (barrier journey), B (DSN parsing, password refusal), C (double `checkpoint_verify`, intruder probe, pause release in `finally`), D (peer-auth-only, env scrubbed of `PGPASSWORD`), F/G (`test_rec_checkpoint` green) | intruder refusal output; suite green | no change |
| `scripts/restore.py` | A/C (fresh-target + source-name guards, manifest re-verify, `restore_fence` pause), D (no dispatch/replay; tar-escape check), F/G (`test_rec_restore` green) | suite green | no change |
| `scripts/scheduler.py` | A (one-shot wakeup/repair journey), C (rounds bounded by `max(1, rounds)`; `redispatch_reset` couples `prove_never_sent` to generation-checked `reset_dispatch`, fail-closed on race), F (`test_agenda_repair`, `test_r03_flow` green) | 8 + agenda suites green | no change (P4 nits ledgered: `assert last is not None` unreachable since the loop always runs ≥1 iteration; `totals` dedup is O(n²) on repair lists) |
| `scripts/manifest.py` | G (runs clean; no secrets — endpoint as bool, versions only), H (thin wrapper) | manual run output (python/limits/sandbox JSON) | no change |
| `scripts/probe_sandbox.py` | G (thin probe wrapper, truthful unavailable verdict) | manual run: `gvisor unavailable: missing runsc, docker` | no change |
| `migrations/0001_schema.sql` | A (state map), B (CHECK bounds; PK/FK coverage), C (journal PK dedup, outbox PK, attempts revision FK), H | fresh apply (9 files); negative-input probe → ENG-INVA-03 | no numbering change |
| `migrations/0004_leases.sql` | A/C (`worker_leases` live via steward expiry/revocation paths — read-only check), H | applied; usage grep | no change |
| `migrations/0006_recovery_fence.sql` | A/C (pause columns back `checkpoint_barrier`/`restore_fence`; `ADD COLUMN ... DEFAULT` safe on populated tables; store uses `.get` fallbacks pre-migration) | applied; barrier/resume/restore suites green | no change |

Technique E (experimental meaning/model integration) is inapplicable to these files by construction: `store.transact` performs no model calls/container runs/external writes inside retried transactions (docstring contract, verified by code read), and `scheduler.run_once` forces `gateway=None` so only mechanical work converges.

## Checks (exact commands, worktree `/tmp/asv2-eng-inva`)
- `uv sync --extra test` — ok.
- `db.apply_migrations('dbname=settlement_enginva', 'migrations')` — 9 files applied.
- New: `SETTLEMENT_TEST_DSN=... uv run pytest tests/test_inva_recovery.py -q` — 4 passed; with base `store.py` — 2 failed / 2 passed (red-capable confirmed).
- Neighboring (final code): 14 files, 91 passed (`test_inva_recovery`, `test_state_operations`, `test_settle_actual`, `test_tx_journal`, `test_tx_outbox`, `test_tx_events`, `test_rec_checkpoint`, `test_rec_restore`, `test_r01c_redispatch`, `test_reconcile_reset`, `test_run_compose`, `test_r01_recovery`, `test_r01_fulfill`, `test_agenda_repair`) plus `test_r03_flow.py` — 8 passed.
- `scripts/manifest.py`, `scripts/probe_sandbox.py` — manual runs ok, no secrets.
- No linter gate is configured for tests/src beyond ruff line-length (no ruff config gate found in CI files checked); `pyproject.toml` names pytest only, which was run.

## Verification limits
- `tests/test_r02_authority.py`: 15 passed, 2 errors — both are DBOS-system tests needing a TCP/SQLAlchemy path unavailable in this environment (fixture connects via SQLAlchemy to a sibling DB; pre-existing, fails identically on base). 1 further test in that file was recovered by using a socket-dir URL DSN.
- No live-inference or containment claims are made: fake/local launchers only; `probe_sandbox` truthfully reports gvisor unavailable here.
- Pre-existing worktree modifications outside this lane (`experiments/run_dev_episode.py`, `experiments/run_live_abc.py`, `experiments/run_use.py`, `tests/test_dev01_ops.py`) were present before this task's edits, were not touched, and are not committed here.
- Throwaway probes (`/tmp/probe_inva*.py`, `/tmp/store_inva_fixed.py`) are scratch only and intentionally uncommitted.
