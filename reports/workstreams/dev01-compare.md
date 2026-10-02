# Workstream dev01-compare — D-CMP comparison/use lane (DEV-05..DEV-10)

Branch: `codex/dev01-compare`, base `c4ec6f7`. DB: `settlement_dev01cmp` (disposable).
Python: `/tmp/asv2-dev01-impl/.venv/bin/python`,
`PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests`.

Consumes `run_abcs` and the episode/capability/trial/evaluation APIs read-only.
No edits to `src/settlement/experiment.py`, `development.py`, `broker.py`,
launchers, `store.py`, `reviews/probes/`, or other lanes' files.

## Owned paths

- `experiments/dev01_tasks.py` (new): third fixture family `missing_guard`
  (missing precondition guard on degenerate input), source group
  `dev01-guard`, with recorded `GROUPING_RULE` declaring disjointness by
  task ID and by fault structure from `off_by_one` and `wrong_operator`.
- `tests/test_dev01_compare.py` (new): 7 tests covering the use-side half
  below. All doubles deterministic (`ScriptedDouble`, `simulated: True`);
  real PostgreSQL + real subprocess sandboxes (`LocalLauncher`); live
  inference blocked environment-wide, so all outcomes stay labeled fixture
  evidence and simulated runs never release.

## Dispositions

- DEV-05 done. Fresh-process resume after publication: after a full
  `run_abcs` episode, a `sys.executable -c` child process receives only
  durable coordinates (DSN, artifacts root, version id) and re-derives the
  capability row plus artifact bytes (digest-checked), invokes the method
  through a fresh launcher run dir, and reproduces the in-process
  invocation bytes. `cap-verify-*` receipt count, capability-version count
  and the version row are unchanged: no repeated settled construction.
- DEV-06 done. A/B/C run on the declared common experience with one
  shared within-task tool envelope (asserted identical across all 21
  arm/task prompts); C prompts carry the actual retained invocation bytes.
  Per-arm standalone cost = common acquisition (charged to each arm) +
  arm spend; cash ledger counts acquisition once and ties to
  `report["accounting"]["totals"]` and `allocation_status`. Labeled
  `exact-lookup-baseline` kept; no-op ablation replays the invocation
  path with distinct ops. Simulated releases stay `skipped-synthetic`.
- DEV-07 done. Splits frozen by source group (dev `off_by_one` IDs,
  panel `off_by_one` IDs with recorded shared structure, use
  `missing_guard` IDs with disjoint structure). All protocols frozen with
  exact candidate bindings; every assignment has an outcome and a
  version-linked receipt; isolation shown by hidden-answer scope refusal,
  evaluator-scope service, candidate-view exclusion, and dev-only
  transcripts in the lesson call.
- DEV-08 done, both branches with labeled `dev01cmp-fixture-` protocols.
  Release: observed-gain on real grading admits a `limited` release, the
  router selects the exact version, and a fresh worker consumes the
  artifact's actual output (graded success). Rejection: a regressing
  candidate is refused for `limited` and `default`; no release row exists
  and the incumbent scope is untouched.
- DEV-09 (use half) done. A crashing fixture method raises through
  `_invoke_method`; the incumbent fallback grades within the remaining
  budget and is recorded under `reference` with
  `routing: incumbent-fallback` conditions; both costs land in truthful
  expenditure categories. Unknown family routes to abstain (no version)
  while the known family still selects. Execution success and evaluation
  success are asserted as separate levels: a successful grade execution
  with failing tallies is an honest evaluation failure.
- DEV-10 done. A rejected episode stays fully inspectable (frozen
  protocol pins, lineage/hypothesis on the version row, artifact bytes,
  verdict, per-category costs, receipts, submissions) with zero pins,
  zero releases, and router abstention: nothing activated, nothing erased.

## Verification (settlement_dev01cmp, revision c4ec6f7 + lane commits)

- `tests/test_dev01_compare.py`: 7 passed.
- Area: `test_s3_experiment.py` + `test_s3_trials.py` +
  `test_r02_explearn.py` + `test_learning_review.py` + `test_r03_eval.py`:
  38 passed.
- Command shape per run:
  `SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_dev01cmp?host=/var/run/postgresql"`
  `PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests`
  `/tmp/asv2-dev01-impl/.venv/bin/python -m pytest <files> -q`

## Residual risks

- No live inference, runsc containment, or multi-family live release
  exercised; release-path mechanics are proven with labeled fixtures
  plus real grading/PG/sandbox, not live evidence.
- Exact-lookup C fails unseen panel hashes by design; the comparison
  result on this panel is an honest null, not a method win.
- `run_abcs` per-arm `budgets` do not fold common acquisition into each
  arm; the DEV-06 test computes the §6-correct view read-only from
  receipts plus the dev protocol ledger.

## Coordinator change requests

- None required for D-CMP. Optional, for the integrator: consider folding
  the DEV-06 per-arm acquisition attribution (common acquisition charged
  to each standalone arm, once in cash) into `run_abcs`'s reported
  `budgets` so consumers do not re-derive it; current harness behavior
  is preserved untouched by this lane either way.
