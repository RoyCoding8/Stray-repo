# Workstream r02-explearn — REVIEW-02 experiment/learning fixes (R02-007/010/011)

Owner: W-D. Branch: `codex/r02-explearn`. Base: `d7b46aa`.
Tip: 4d2979b4b124ff6539665c5c4a720c2c4a371fe9

Isolated DB: `settlement_r02exp` via
`SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_r02exp?host=/var/run/postgresql`.

## Red-first baseline (before source changes)

`reviews/probes/test_review_02.py::test_candidate_reads_protected_fixture_answers_from_repository`
passed pre-fix: a candidate that only looks up `experiments/fault_tasks.py` passed all
three `panel-triangular` cases through the real grader. Recorded as buggy behavior.

## Modified paths (owned only)

- `src/settlement/experiment.py`
- `experiments/run_live_abc.py`
- `experiments/run_tests.py`
- `src/settlement/launcher_local.py`
- `tests/test_r02_explearn.py` (new, 9 tests)

Untouched by design: `experiments/fault_tasks.py` (protection comes from
runtime isolation, not fixture edits), `experiments/doubles.py` (already
labels everything simulated).

## What changed

R02-007: `run_tests.py` spawns each candidate case under `python -I` with a
scrubbed environment (`PATH`/`LANG` only), cwd in a private
`grader-child-*` directory; cases arrive only as per-task case files over
stdin and the cases file is unlinked after loading. `experiment.py` copies
the grader into the isolated workdir so repository paths stay off
`sys.path`. `launcher_local.py` never inherits the controller cwd
(payload `cwd` or the caller-created isolated run directory) and keeps the
scrubbed environment. The live CLI selects its launcher explicitly
(`--launcher runsc|local`, default `runsc`): live local execution needs
`--allow-uncontained`, runsc needs a pinned `--runsc-image`, and an
unavailable containment boundary refuses with a clear error instead of
running exposed. `--deterministic` still runs the scripted demo, labeled
simulated.

R02-010: development synthesizes the retained method from DEV model texts
and grades (`_synthesize_method`, exact-repair map with `--selftest`),
freezes that artifact (`_freeze_method`, digest-suffixed version on
conflict, never a silent registry reuse), and the arm loop invokes the
exact frozen version via `get_version` (no registry re-query). Every arm
gets one model call with arm-differing context and every arm is graded on
its own model text (the `if harness_arm != 'C'` discard is deleted). The
lesson prompt now carries dev transcripts, and the report records
per-family acquisition (version, artifact digest, transcript digest,
attempts, verification op and settled cost) plus the evaluated artifact id
in each trial receipt.

R02-011 (CLI side): `SETTLEMENT_GRANT_UNITS` binds to a capped
sub-allocation `min(grant, available net of children)`; the whole run
executes under the child and admission refusal stops it when exceeded
(`transact` returns refusal codes instead of raising, so the helper checks
result codes). Reports separate billed-money `settled_usage` from
`unresolved_exposure` and `token_estimates` labeled "token-length
estimate; not a monetary ceiling". Unpriced-usage settlement inside the
broker/gateway is owned by another workstream and untouched here.

## Checks (real PostgreSQL unless noted)

- `tests/test_r02_explearn.py`: 9 passed.
- Answer-lookup probe now FAILS (required): candidate dies with
  `FileNotFoundError: .../grader-child-*/experiments/fault_tasks.py`.
- Original forgery rejection probe: passes. `tests/test_r01_grader.py`: passes.
- CLI refusals verified without network/DB: `--launcher local` without the
  flag and default runsc without an image both exit 3 with explicit errors.
- Deterministic CLI end to end: runs, labeled simulated, acquisition and
  token labels present (covered by committed test).
- Affected suites: `test_launchers.py`, `test_learning_review.py` pass.
  `test_r01_experiment.py` (4 tests) and `test_s3_experiment.py::test_full_simulated_abc`
  fail on intended contract changes outside this ownership: removed
  `method_sources` kwarg (loud `TypeError`, kept removed rather than an
  ignored shim) and C now graded on its own model text, so C-incompetent
  doubles no longer show `observed-gain` and pre-published registry entries
  are no longer picked up. These tests encode the old unfair comparison and
  need coordinator-owned updates.

## Remaining limitations

- Live inference never exercised (no provider credentials); live behavior
  is proven only up to gateway discovery/refusal paths.
- Real runsc containment unavailable on this host (`RunscLauncher.available`
  is false); contained live execution is refusal-tested, not run.
- A candidate guessing absolute fixture paths or exfiltrating over the
  network is contained only behind the runsc boundary, not by the local
  process isolation.
- Broker-side billing of unpriced HTTP usage (charge 0 vs conservative
  exposure) belongs to the billing owner; this workstream only separates
  and labels money vs token estimates on the experiment/CLI side.
