# Workstream inv-c2: one study authority, feedback and recovery (M2, M3)

Owner: Nightjar. Worktree `.worktrees/inv-c2`, branch `wt/inv-c2-authority`,
base `692af23`. Owned paths only: `src/settlement/authority.py` (new),
`src/settlement/loop.py`, `migrations/0015_study_authority.sql` (own tables),
`tests/test_invc2_authority.py`, `tests/test_invc2_recovery.py`, this note.
`broker.py`, `store.py`, `context.py` needed no change; the fix lives in the
new ledger plus small `loop.py` wiring. `experiments/**` untouched by design.

## Model

One row per study in `study_authority`: root name, backing allocation,
authorized amount, ceilings, correction budget, and the fingerprint of the
designating store (`store_identity`, one UUID per database). Authority is
seeded once by an explicit grant act. Everything else reconnects or refuses.

- `authorize_study(dsn, study_root, *, authorized, allocation_id=None,
  ceilings=None, correction_budget=2) -> StudyHandle` seeds the root
  allocation and the authority row idempotently. Same parameters replay to
  the same handle. Diverging parameters raise instead of reseeding.
- `bind_study(dsn, study_root) -> StudyHandle` reconnects only. A database
  with no row, or a row bound to another store fingerprint, raises
  `MissingAuthority`. It never creates anything.
- `admit_study_call(dsn, study_root, *, kind, operation_id, effect, payload,
  attempt_id=None, execution_version="", retries=0) -> Grant | Refusal`
  is the lane call. `kind` is one of `calibration`, `development`, `repair`,
  `use`. Each operation provisions a child allocation subdivided from
  remaining parent authority, then admits through the normal broker path.
  Missing authority, unknown kind, and exhausted parents return `Refusal`
  with `missing-authority`, `unknown-kind`, or `insufficient-authority`.
  Re-admission of the same operation identity returns the existing grant
  without re-charging. Episode tags only name children; they fund nothing.
- `study_remaining`, `verify_ledger`, `note_phase`, `phase_status`,
  `correction_state`, `take_correction`, `corrections_total` support
  budgets, independent receipt/liability sums, phase checkpoints, and the
  durable correction budget.

`ResourceEnvelope.bind` now delegates to `authorize_study`, so reopening a
database reconnects to the same authority instead of reseeding. All
signatures the campaign entry uses are unchanged: `run_campaign`,
`ensure_campaign`, `resume_campaign`, `run_use`, `cost_union`,
`sequence_construction_allowance`, `admit_effect`, `run_boundary`
(`LoopState` gains optional `corrections` and `last_failure` fields).
Transition journal identity is content-addressed, so distinct corrections
of one decision journal distinctly while identical retries replay.

## For lane C1 (campaign entry, owns `experiments/ad01/`)

Replace `construct._construction_allocation` (per-call `seed_allocation`
of 16384 with no parent) with `admit_study_call` using
`study_root=<campaign study root>`, `kind="development"` for init and
`kind="repair"` for repair, keeping operation ids stable so resume reuses
settled receipts. Calibration and use already pass explicit allocations;
point them at the same study root with `kind="calibration"` / `"use"`.
Call `authorize_study` once per study before the first boundary and
`note_phase` for diagnostic completion and candidate validation before
dependent work; on resume, `phase_status` decides what to skip. Rejected
learner proposals arrive at the next `propose` call through
`state.last_failure` (`reason`, `target`, `decision`); render it into the
next request and return a valid proposal within `correction_budget`.

## For lane C3 (qualification)

`verify_ledger` recomputes measured charges, expected consumption, pending
exposure, and unknown receipts from receipts and reservations independently
of the allocation counters and reports `match`. `phase_status` and
`correction_state` are read-only resume proofs. Completed-boundary replay
stays separate from interruption recovery; do not use one to prove the
other.

## Gates (real Postgres, real subprocesses, doubles at provider seam only)

- `tests/test_invc2_authority.py`: 4 passed. Exhausted parent refuses
  init, repair, and use. Same study on a fresh database refuses bind and
  admit with zero reproduced calls or rows; reopening the home database
  reconnects with unchanged authority; retagged episodes subdivide from
  the same parent. Children carry parent linkage and exact exposure.
  Ledger sums match independent SQL cent for cent.
- `tests/test_invc2_recovery.py`: 3 passed. An invalid proposal returns
  its reason into the next propose call and the next gateway prompt, then
  admits with one durable correction. Correction budget 1: first process
  spends it over two propose calls and refuses exhausted; a new process
  gets no further correction and the count stays 1. Crash recovery:
  process one dispatches diagnostic, checkpoints, and dies with exit 13;
  process two reuses the settled diagnostic with zero new model calls,
  validates once, checkpoints, and dies with exit 14; process three
  finishes with 2 operations, 2 receipts, single-spend consumption, and
  exact remaining authority.
- Nearby, unmodified: `test_inv_b2_loop` plus `test_inv_f2_loop` 11
  passed, `test_inv_c_qualification` 9 passed, `test_inv_b4_trajectory`
  4 passed. Nearby suites ran with their DSN variables pointed at
  disposable `inv_c2_*` databases because their default databases do not
  exist in this cluster (pre-existing provisioning gap, unrelated).
- TDD trail: M2 tests failed first on the missing module, then twice on
  behavior (re-admit double charge fixed by returning the existing grant;
  ledger remainder freed at settle, not retained). M3 tests failed first
  on all three behaviors, then once on journal identity collision across
  distinct refusals (fixed with content-addressed identities).

Recreate databases with
`for d in inv_c2_auth inv_c2_auth2 inv_c2_rec; do createdb -h
/var/run/postgresql $d; done`, then
`uv run --extra test pytest tests/test_invc2_authority.py
tests/test_invc2_recovery.py -q`.

## Remaining gaps

- `construct._construction_allocation` still seeds per-call authority. It
  is C1-owned and must migrate to `admit_study_call` as specified above.
  Until then the M2 gate holds for the settlement path, not for live
  construction calls.
- No live inference or containment validation here. Doubles only.
- `probe_allowance` keeps its fixed child identity. Untouched as out of
  scope; flagging for the lane that owns probes.
- Correction budget caps corrections per decision, not initial proposals.
  Each new boundary attempt gets one proposal; only retries spend budget.
