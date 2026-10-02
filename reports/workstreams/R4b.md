# R4b — R01-009 / R01-010 evaluator, result and release integrity

Branch: `codex/review01-r01-eval-b`, base `381346a`.
Scope: `src/settlement/trials.py`, `src/settlement/evaluation.py`,
`src/settlement/capabilities.py`, `tests/test_r01_release.py` (new),
`tests/test_s3_experiment.py` (alignment only).

## What changed

R01-009 — release evidence must be complete, authenticated, assignment-bound:

- `trials.record_result` stamps every caller-submitted row
  `detail.origin = "direct-caller-outcome"` (caller-supplied origin kept).
  Caller rows stay ledger-visible for `verdict()` but are never
  release-eligible production evidence.
- `evaluation.submit_evaluator_receipt` now enforces, before admission and
  again inside the transaction: the invocation is a real observed operation;
  a `success` claim requires a `success` broker receipt on that invocation
  (failed operation labeled success refused); one invocation backs at most
  one assignment per protocol (unrelated-operation reuse refused); one
  receipt per assignment.
- `capabilities.scoped_release` audits every protocol assignment
  transactionally: full coverage by evaluator receipts, receipt
  `invocation_ref` equals the result row's non-empty ref, receipt outcome
  equals row outcome, receipt evaluator version equals the protocol pin,
  receipts flagged `simulated` or carrying a synthetic `detail.origin` are
  ineligible, and `success` rows need a succeeding invocation. Empty
  receipt sets and unbound caller rows refuse.

R01-010 — release binds the tested versions and supported scope:

- Release requires `set(versions) == {protocol.candidate_version}`; A-trial
  evidence can no longer release B, nor mixed A/B sets. The protocol query
  selects the candidate version alongside the evaluator version, and every
  check runs pre-transaction (raising) and re-runs inside the serializable
  release transaction (authoritative against races).
- `limited`/`default` releases additionally require a non-empty scope
  contained in each released version's applicability (fallback: scope).
  Experimental/candidate/quarantined/retired dispositions store scope as
  before and do not promote to routing.

## Contract decisions (deliberate, review-relevant)

- Invocation-reuse uniqueness is per-protocol: the simulated ABC harness
  shares one grade op across its B/C comparison protocols by design, and
  per-protocol audit keeps each release internally consistent.
- Zero-assignment protocols keep prior behavior (experimental releasable;
  limited/default refused as inconclusive). All refusals with assignments
  present hold for every disposition.
- `tests/test_s3_experiment.py::test_router_mixed_with_regression` asserted
  the R01-010 bug (releasing `feat-v2`/`base-v1` from protocols testing
  generated ids). Protocols now test the released versions and stub rows
  carry matching applicability. No other existing test needed changes.

## Test evidence (real PostgreSQL 16, `settlement_r01evalb`)

- `tests/test_r01_release.py`: 14 passed — direct rows, empty set, marked
  fixture insert, simulated receipt, diverged row, unrelated operation,
  failed-op-labeled-success, evaluator-version mismatch, B-for-A, mixed
  A/B, widened/empty scope, incumbent preservation, exact-bind positive.
- Existing `test_s3_trials|evaluation|capabilities|experiment`,
  `test_learning_review`: all pass. Full `tests/` run: 239 passed plus
  `test_s0_gateway` 16 passed. `test_broker_dbos` (2 errors) fails
  identically on clean base `381346a` — pre-existing environment issue,
  unrelated.

## Open risks / residual

- Evaluator-process separation (R01-008: candidate code sharing grader
  memory) is the parallel owner's slice; this slice binds receipts to
  invocations but does not isolate execution.
- Operation payloads carry no assignment attribution, so a first-use
  unrelated-but-successful op for a same-outcome claim is structurally
  indistinguishable from the genuine grading op; per-protocol uniqueness
  plus outcome derivation is the enforced boundary.
- Experimental-scope releases with unsupported scope are stored (not
  promoted); routing changes only via explicit router policy.
