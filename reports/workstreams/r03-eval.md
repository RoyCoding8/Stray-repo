# Workstream r03-eval — Review-03 evaluation lane (R03-003/004/005/006)

Branch: `codex/r03-eval`, base `20017f2`. DB: `settlement_r03eval` (disposable).
Python: `/tmp/asv2-r03-impl/.venv/bin/python`,
`PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests`.

## Dispositions

All four findings assessed **confirmed** against production entry points
before fixing. A positive learning result was not pursued; the experiment is
honest but inconclusive under scripted doubles by design.

- R03-003 confirmed. `_prepare_grade`/`_invoke_method` wrote host workdir
  paths and passed `sys.executable`; `stage_input` had no production caller,
  so `_mounts` was empty under runsc. Reproduced by
  `test_contained_grading_prepares_only_unmounted_host_paths` (passed
  pre-fix), then migrated.
- R03-004 confirmed. `_check_claimed_outcome` accepted success with zero
  tallies; validators bound metadata but no executable/candidate/input
  digests; `run_abcs` registered the evaluator with no code digest.
  Reproduced by `test_unrelated_successful_process_can_back_evaluation_binding`
  (passed pre-fix), then migrated.
- R03-005 confirmed by source trace. The arm loop discarded
  `_invoke_method`'s return and prompted with method source text; synthesis
  was a fixed exact lookup; no shared within-task tool envelope existed.
  `test_synthesized_method_returns_unseen_broken_input_unchanged` passed
  pre-fix and is kept as the labeled-baseline contract.
- R03-006 confirmed. Scratch run (`/tmp/r06_scratch.py`, not committed):
  stem occupied by another family's artifact froze `fixer-v1-bb37d59e`
  while protocols pinned `fixer-v1`. Protocols froze pre-development; no
  release/router reuse existed in `run_abcs`.

## Changes

- `src/settlement/broker.py` (Launcher Protocol block only): one staging
  interface — `stage_input`, `exec_dirs` (execution-visible
  inputs/outputs dirs), `staged_python`, `read_output`.
- `src/settlement/launcher_runsc.py` (ctor param + new methods only):
  `image_python` ctor param defaulting to PATH-resolved `python3`;
  `exec_dirs` returns the `/work` mounts; `staged_python`; `read_output`
  from the outputs mount. `stage_input`/dispatch/retention/supervision
  untouched.
- `src/settlement/launcher_local.py`: same layout under its run_dir with
  the host interpreter.
- `src/settlement/experiment.py`: grading/method invocation stage through
  the interface and address execution-visible paths; outputs return via the
  outputs mount; staged digests bind pre-launch and are re-hashed at launch
  (`_verify_staged`); evaluator registered with the grader digest; all arms
  share one inference plus an identical tool envelope and staged grader
  path; C prompts carry the real invocation result; no-op ablation replays
  the invocation path per C task; default synthesis labeled
  `exact-lookup-baseline` with a caller-supplied synthesizer hook;
  panel/transfer protocols freeze post-development against actual frozen
  versions (`multi:` set for multi-family groups); trials bind the actual
  immutable candidate (version + artifact digest); eligible non-synthetic
  evidence exercises limited release plus router/fresh-worker reuse,
  otherwise recorded as skipped/ineligible.
- `src/settlement/evaluation.py`: `bind_evaluation` accepts
  executable/input digests persisted on the assignment instance (no schema
  change); validators refuse proof-less executables against pinned
  evaluator digests at bind and receipt time; digest-bound success claims
  need tallies — bare process success cannot certify them. Unpinned
  (legacy/test) bindings keep prior semantics; `register_evaluator` fills
  a previously empty code digest monotonically.
- `src/settlement/capabilities.py`: verification stages the entry through
  the launcher and runs the launcher python; removed host temp staging;
  release gate accepts `multi:` tested sets.
- `experiments/run_live_abc.py`: `--runsc-python` (env
  `SETTLEMENT_RUNSC_PYTHON`) forwarded to `image_python`.
- `reviews/probes/test_review_03.py`: migrated only the three named
  probes (renamed `test_r03_*`, one-line migration note each); no other
  probe touched.
- `tests/test_r03_eval.py` (new, 12 tests): staged/bound grading,
  tamper-at-launch refusal, pinned-executable refusal, bare-success
  refusal, legacy boundary, mounted method outputs, missing-output
  refusal, shared tool envelope, noop identity, multi-set gate, full-run
  actual-version binding, stem-conflict freeze.

## Compatibility notes

- `experiment._grade` keeps its `workdir` parameter (ignored) because
  `tests/test_r01_grader.py` (outside this lane) calls it positionally.
  New code stages via the launcher. Remove the parameter together with
  that file's migration in a later pass.
- `run_live_abc._select_launcher` reads `runsc_python` via `getattr` so
  existing namespace-based callers keep working.

## Verification

Focused plus area suites, all green on `settlement_r03eval`:

- `tests/test_r03_eval.py`: 12 passed
- `reviews/probes/test_review_03.py -k r03_`: 3 passed
- `tests/test_r02_evalbind.py` + `test_s3_evaluation.py` +
  `test_s3_capabilities.py` + `test_s3_trials.py`: 35 passed
- `tests/test_r01_experiment.py` + `tests/test_s3_experiment.py`: 7 passed
- `tests/test_r02_explearn.py` + `test_r02_exec.py` +
  `tests/test_launchers.py` + `tests/test_r01_grader.py` +
  `tests/test_r01_runsc.py` + `tests/test_learning_review.py`: 61 passed
- `reviews/probes/test_review_03.py` (all 12, incl. other lanes) +
  `tests/test_r03_eval.py` + `tests/test_r02_evalbind.py`: 44 passed

Command shape for each run:

```sh
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_r03eval?host=/var/run/postgresql" \
PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests \
/tmp/asv2-r03-impl/.venv/bin/python -m pytest <files> -q
```

Full suite intentionally not run (integration owns it).

## Residual risks

- Legacy unpinned evaluator bindings still accept bare success; production
  entry points always pin, but a direct API caller can still register
  without a digest. Tracked as the documented boundary in
  `test_unpinned_binding_keeps_legacy_behavior`.
- No real runsc containment, live inference, or multi-family live release
  exercised here; `_maybe_release` beyond `skipped-synthetic` is
  implemented but unexecuted against a live backend.
- Same-process staged-file tamper after launch verification is outside the
  threat model (single trust domain); cross-boundary bytes are covered by
  mounts, digests, and tally authentication.
- `experiment._grade`'s ignored `workdir` shim (see above).
