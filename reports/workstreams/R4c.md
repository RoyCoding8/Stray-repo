# R4c — R01-011 live A/B/C execution, R01-012 broker-routed experiment costs

Branch: `codex/review01-r01-eval-c`, base `749d737` (R4a + R4b merged).
Scope: `src/settlement/experiment.py` (run path/CLI wiring only),
`experiments/run_live_abc.py`, `experiments/doubles.py` (lesson-authoring
branch), `tests/test_r01_experiment.py` (new), `reports/workstreams/R4c.md`.

## What changed

R01-011 — the CLI executes the protocol end to end:

- `run_abcs` accepts `gateway=` (the CLI's adapter argument) alongside the
  legacy `double=` alias; a missing adapter raises instead of silently
  skipping. The `gateway=`/`double=` mismatch is gone.
- Development runs first under fresh workers: every `dev_ids` task gets a
  broker-routed model call plus the R4a grader, the lesson is authored by a
  broker-routed model call over the dev transcripts (or recorded as
  `supplied` when the caller passes drafts), and the method is staged,
  sandbox-verified (`--selftest`) and published through
  artifacts/capabilities, or reused when already published. Products freeze
  before any panel/transfer worker starts.
- Panel/transfer arms use matched within-task tools: every arm issues
  exactly one model-inference operation plus identical grader calls under
  identical caps. Arms differ only in retained context (none / frozen
  lesson / frozen invocable method); C's method invocation is an extra
  broker-routed sandbox op. A/B no longer bypass the broker.
- `run_live_abc.py` executes `run_abcs` instead of printing a suggestion.
  Live mode requires endpoint/key/positive grant plus explicit `--model`
  (or `SETTLEMENT_MODEL`), checks discovery/auth, verifies the allocation
  and installed grant, then runs with `simulated=False`. Missing live
  inputs exit 2; failed probes, missing grant/allocation, or experiment
  refusal exit 3. `--deterministic` runs the same path on scripted
  adapters with no endpoint.

R01-012 — every experiment effect routes through the broker contract:

- All model calls go through `broker.ensure_operation` (admission +
  reservation) and `broker.dispatch_operation(gateway=adapter)` (receipt).
  `INSUFFICIENT_RESOURCES` at admission raises before provider dispatch;
  the double records zero calls in that case.
- Costs derive from actual receipts and reservation states via
  `_op_accounting`: model usage settles to receipt `charge_units`,
  sandbox usage settles to its consumed ceiling, anything else stays
  unresolved exposure. The report carries per-op entries plus
  reserved/settled/unresolved totals; arm budgets report the same split.
- Ledger categories fixed: grade costs go to `evaluation` on success and
  `failed_trials` on failure (including construction-phase failures), C
  method invocations go to `use` (was: mislabeled `retrieval`), and the
  synthetic `exposure_schedule` estimates plus the B `retrieval` charges
  are gone (retrieval ledger is zero; lesson reads are DB claims, not
  broker effects). A inference is counted in arm totals.
- Evaluator receipts now carry the grade op's settled/reservation cost
  and the frozen retention binding (`lesson_digest`, method version) in
  `detail`, alongside the R4b invocation binding (unchanged).

R4a/R4b regions preserved: `_grade`/`_run_sandbox`/`_authenticated`
untouched; `_bind_assignment` still binds each assignment to its observed
grade invocation under the pinned evaluator version; `run_abcs` reuses
(rather than republishes) preinstalled methods, so `test_s3_experiment.py`
passes unmodified.

## Test evidence (real PostgreSQL 16, `settlement_r01evalc`, real subprocesses)

- `tests/test_r01_experiment.py`: 4 passed — full deterministic run
  reconciles every op's settled cost against independent DB queries with
  zero unresolved exposure, verdicts preserved (panel-B/C gain, transfer
  inconclusive), 19 broker-routed model calls with per-arm counts;
  insufficient grant (authorized=5) raises with zero provider calls and
  zero receipts; experiment evidence refuses release three ways
  (synthetic harness data, deleted receipt → "without authenticated
  evaluator results", wrong version → "candidate version pin mismatch");
  CLI subprocess demo exits 0 with `panel-C: observed-gain` and
  `transfer-C: inconclusive`, CLI without live inputs exits 2.
- Existing `test_s3_experiment|evaluation|trials|capabilities`,
  `test_r01_grader`, `test_r01_release`, `test_learning_review`:
  48 passed.
- `ruff check` on touched files: only the repo-wide pre-existing drift
  classes (nested-`with`, non-enabled `noqa`, import sort); no new
  violation classes.

## Contract requests (no broker.py edits made)

- Read-only `broker.op_cost(dsn, operation_id)` helper wanted: per-op
  settled consumption is currently re-derived in `_op_accounting` from
  reservations/receipts SQL because receipts do not store `actual_cost`.
  Behavior is identical; a helper would remove the raw SQL.
- Retained-lesson durability: the frozen lesson lives in the report plus
  a digest bound into each receipt's `detail`. If lessons need a
  first-class versioned registry like capabilities, that is a coordinator
  design decision.

## Open risks / still needs a live endpoint

- No live gateway run yet: provider `charge_units`, live-authored
  lessons, and a `simulated=False` release-eligibility positive all need
  endpoint + key + funded grant. The deterministic double's lesson is
  canned guidance plus enacted dev counts; B/C effectiveness in the
  harness comes from the scripted competence map, not from the text.
- Harness (`simulated=True`) evidence is correctly non-releasable by the
  merged R4b gate; only live evidence with exact tested versions can
  promote. Live release has not been exercised.
- No per-op CPU/memory caps beyond launcher timeouts; dev-phase failure
  does not gate retention (outcomes are recorded, method verification is
  still genuinely sandbox-enforced).
