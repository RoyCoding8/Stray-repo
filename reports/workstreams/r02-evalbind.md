# W-C R02-008/009 evaluation binding + release scope — task report

- Base: `d7b46aa` (branch `codex/r02-evalbind` start, per assignment).
- Code commit: TBD — `evaluation.py`, `capabilities.py`, `trials.py`,
  `migrations/0005_eval_binding.sql`, `tests/test_r02_evalbind.py`.
- This report: follow-up commit on the same branch (tip = this commit).
- Worktree: `/tmp/asv2-r02-r02-evalbind` only. No other checkout touched.
- Test DB: `settlement_r02eval` via
  `SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_r02eval?host=/var/run/postgresql`
  (PostgreSQL 16 cluster, real server; no skips).

## Modified paths (owned only)

- `migrations/0005_eval_binding.sql` (new): `trial_assignments` gains
  `candidate_digest`, `evaluator_id`, `evaluator_version`, `evaluation_op`;
  `trial_protocols` gains `supported_scope JSONB NOT NULL DEFAULT '{}'`.
- `src/settlement/evaluation.py`: immutable pre-launch binding
  (`bind_evaluation`), bound-invocation receipts, grader-tally verdict
  derivation, candidate-divergence refusal.
- `src/settlement/capabilities.py`: implication-direction scope check for
  version applicability and trial supported scope; release-path
  re-verification of the evaluation binding.
- `src/settlement/trials.py`: `freeze_protocol`/`amend_protocol` carry
  `supported_scope` (optional, default `{}`).
- `tests/test_r02_evalbind.py` (new): 20 regression tests for the corrected
  contracts.

No other paths touched. No contract change requests: the only production
caller of the changed functions is W-D-owned `experiment.py`, whose call
signatures remain backward compatible (see handoff below).

## R02-008: actual invocation binding (fixed)

Binding model: `evaluation.bind_evaluation(dsn, cmd, assignment_id, *,
candidate_digest, evaluator_id, evaluator_version, invocation_ref)` records
the assignment's immutable binding BEFORE launch. It requires a prior
candidate submission matching `candidate_digest`, a registered evaluator
package whose version equals the protocol pin, and an operation row in
`prepared` state with a `sandbox-exec` effect; one same-protocol clash check
covers both bound assignments and existing receipts. Identical rebinds return
`ALREADY_APPLIED`; anything else refuses (rebinding, post-hoc binding after
a receipt exists, ghost/prepared-state/effect violations).

`submit_evaluator_receipt` keeps its signature and now verifies, outside the
transaction (raising) and identically inside it (guarding the insert): bound
op equality, bound evaluator equality, protocol pin and registered package
version, latest-submission digest equality, `result.detail.task_id` equality
with the assignment task, and verdict derivation from the bound invocation's
broker receipts. Success needs a broker success receipt plus clean grader
tallies when tallies are recorded (`failed == 0`, `passed == total > 0`);
a successful grader process with failed cases is refused. Non-success claims
are refused against clean tallies and against bare successes with no recorded
test outcome. `submit_candidate` returns `content_digest`, refuses bytes that
diverge from a bound digest (outside and inside the transaction), and keeps
the unknown-assignment refusal. Direct/synthetic-origin refusals stay at the
release path, which now additionally re-verifies binding equality, evaluator
equality, submission digest, task identity and tally derivation per
assignment, so hand-inserted receipt/result rows cannot release.

## R02-009: release scope implication (fixed)

`_check_supported_scope` keeps its signature and now requires the release
scope to imply every supported restriction: each key of the version's
supported applicability/scope must be present with an equal value; extra
requested keys (legitimate narrowing) are allowed. Dropping or changing a
constraint raises naming the constraint, e.g. `drops supported constraint
'language'`. New `_check_trial_scope` enforces the same implication against
the protocol's frozen `supported_scope` (empty means no trial-side
constraint). Both checks run pre-transaction and inside `scoped_release`.

## Verification

- New suite `tests/test_r02_evalbind.py`: 20/20 pass on real PostgreSQL,
  covering bound-flow acceptance and limited release, fresh/wrong-op refusal,
  real-grader dirty-tally refusal (via `experiments/run_tests.py` through the
  broker + `LocalLauncher`) and clean-pass acceptance, candidate mismatch at
  submit and at receipt, evaluator replacement and rebinding refusal, task
  mismatch, bind rules (ghost/prepared/effect/idempotent), SQL-tampered
  receipt and invocation refusal at release, bare-success failure-claim
  refusal, scope drop/change refusal, narrowing acceptance, trial-scope drop
  and change refusal, experimental skip, empty-applicability refusal, and
  protocol scope round-trip through amend.
- C4: `test_release_scope_can_drop_a_supported_constraint` now FAILS with
  `SettlementError: release scope {'family': 'software-repair'} drops
  supported constraint 'language' ...`; 
...[truncated 3010 chars]
## Coordinator integration note

Legacy suites migrated to the binding contract (same branch, pre-merge):
`test_r01_release.py` (bind-before-launch `_grade`, bind-time clash test,
`broadening release refused` message), `test_s3_evaluation.py` and
`test_s3_capabilities.py` (bind before launch, `detail.task_id` on
receipts, reordered assign/register before grade), plus a shared
`bind_assignment` helper in `test_s3_helpers.py`. Receipt-time clash
checks remain as defense in depth; the "already backs" property now
surfaces at bind time.
