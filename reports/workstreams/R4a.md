# R4a — R01-008 evaluator/candidate separation

## Changes

- `experiments/run_tests.py`: rewritten as evaluator-only. Candidate code never
  imports into the grader process. Each case runs in a transient child process
  (`python -c` runner) that receives only that case's function name and args
  over stdin. The runner captures candidate stdout/stderr before import, emits
  exactly one envelope line on the restored stdout, and any exit/crash leaves
  no parseable envelope. The evaluator loads hidden cases, removes the cases
  file, enforces a per-case slice of the argv-supplied budget, compares
  actuals itself with `_close`, and prints the owned receipt including
  `total`. Fail-closed throughout: spoof bytes, missing envelopes, non-zero
  exits, and timeouts all become case failures, never success.
- `src/settlement/experiment.py` (`_grade`/`_run_sandbox`/receipt region only):
  added `_authenticated`, which grants success only on receipt
  `outcome == success` + launcher `parse == typed-json` + worker
  `status == ok` + `total == passed == len(cases) > 0` + `failed == 0` +
  empty failures. `_run_sandbox` accepts a `timeout_ms` override;
  `_grade` accepts `grader_budget_ms` (default preserves existing behavior)
  and forwards the worker budget as an evaluator-owned argv element.
  `run_abcs` and the CLI are untouched.
- `tests/test_r01_grader.py` (new): 9 regression tests through the real
  sandbox launcher covering probe 1's exact exploit, hidden-answer access
  (argv/file-scan/`evaluation.hidden_answer`, plus cases-file removal),
  stdout and fd-1 spoofing with a wrong implementation, exit/crash variants,
  per-case timeout, and an honest-candidate positive control.

## Test results

- `tests/test_r01_grader.py`: 9 passed.
- `tests/test_s3_experiment.py` + `tests/test_s3_evaluation.py`: 7 passed,
  including the full simulated A/B/C over the new grader.
- `ruff check` on all touched files: passed (`ruff` resolved via uvx; not in
  the locked venv). `ruff format --check` drift is pre-existing repo-wide and
  was left alone.
- Env: worktree venv from `uv sync --locked --extra test`;
  `SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_r01evalexp?host=/var/run/postgresql`
  (PostgreSQL 16).

## Invalidated review probes

- `reviews/probes/test_review_01.py::test_candidate_forges_grader_success`
  now FAILS (verified): it asserts the old forgeable verdict and is preserved
  as historical evidence. `tests/test_r01_grader.py` supersedes it — same
  exploit candidate through the real channel now yields failure.

## Open risks / contract notes

- Filesystem co-tenancy under the `local-process` profile is not a security
  boundary: a candidate that guesses workdir paths could observe the candidate
  file itself. Hidden answers are no longer reachable (never in child argv or
  env, cases file unlinked after evaluator load, per-case stdin carries only
  inputs), but true containment for agent-authored code needs the R01-005
  contained launcher, still missing.
- No per-case CPU/memory caps are set on candidate children beyond the
  launcher operation timeout and evaluator budget slicing; a fork/resource
  attack is out of this slice's scope.
- Needed contract change for the R01-009/011/012 owners: `_grade`'s success
  verdict now additionally requires `passed == total == len(cases)`; any
  consumer that relied on partial-pass success must treat those outcomes as
  failure. No caller changes were required (`run_abcs` uses the default).
