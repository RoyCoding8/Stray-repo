# mechanism-verdict-18 — the 18 local failures are a Windows artifact

Branch: `codex/agent-society` at `eb0538fa`. Owned paths touched: this file
only. No test, no count and no source file was edited.

## Verdict

The 18 failures are host artifacts. The count expectations in
`tests/test_s09_verdict.py` (lines 533-535) are correct as written and must
not be re-pinned to a Windows run.

The hypothesis is confirmed by four independent lines of evidence, none of
which is a local test run: the refusal path is unreachable on Linux, CI's
own shard-1 artifact shows all three suites green on `ubuntu-latest`, the
pinned counts are exactly the counts a Linux collection produces, and CI's
shard-4 artifact shows the verdict test itself passing with those counts
against three real nested runs.

## What CI says, by run and artifact

Every suite job is `runs-on: ubuntu-latest` (`.github/workflows/ci.yml:19`),
so these suites only ever run on Linux in CI.

Shard 1 is the job that owns all three boolean suites. Measured, not
inferred: unpacking `d4eb4126` into a scratch tree and collecting under the
same `--splits 4` CI uses places them there and nowhere else.

| suite | test ids | collected on `d4eb4126` | shard |
|---|---|---|---|
| `tests/test_boolean_ast_arm.py` | ids 531-577 | 47 | 1 |
| `tests/test_boolean_graph_arm.py` | ids 578-589 | 12 | 1 |
| `tests/test_boolean_policy_bridge.py` | ids 590-599 | 10 | 1 |
| `tests/test_s09_verdict.py` | ids 3685-3714 | 30 | 4 |

Shard-1 conclusions across every completed run with a readable artifact:

| run | commit | shard-1 summary | boolean-suite failures |
|---|---|---|---|
| 37285167407 | `f3145187` (post-fix) | `26 failed, 1186 passed, 3 skipped, 3642 deselected in 693.53s` | 0 |
| 37261826154 | `d4eb4126` (pre-fix) | `29 failed, 1180 passed, 3 skipped, 3634 deselected in 746.87s` | 0 |
| 37251210268 | `91b36f87` (pre-fix) | `31 failed, 1162 passed, 3 skipped, 3587 deselected in 713.75s` | 0 |
| 37277929945 | `e3be0703` (pre-fix) | `26 failed, 1184 passed, 3 skipped, 3636 deselected in 870.60s` | 0 |

Artifact for each: the `suite-py3.13-1` artifact of that run, read from
`failures.txt` and `suite.log`, downloaded with
`gh run download <run> -R RoyCoding8/Stray-repo -n suite-py3.13-1`.

The post-fix row is the one that matters, and it is a clean result rather
than a lucky one. Run `37285167407` is commit `f3145187`, which contains the
deadlock fix, and its shard-1 failure set is byte-for-byte the same 26 lines
as the pre-fix run `37277929945`: 0 new failures and 0 removed. The 26
failures are in `test_a40_admission_wired.py`,
`test_a41_reuse_id.py`, `test_a42_chain_demonstration.py`,
`test_ad01_live_acquired_ddmin.py`, `test_ag01_experiment.py`,
`test_aleb_construct.py`, `test_alec_episode.py`, `test_alee_learner.py`,
`test_bacq_method.py`, `test_evidence_integrity.py`,
`test_evidence_supersession.py` and `test_final_accept_findings.py`. None is
a boolean suite. Those 26 are pre-existing and belong to other lanes.

These three artifacts carry a terminal pytest summary, which is what makes
them usable. Absence of a test from a failure list is only evidence when the
list is complete, and a truncated log is not a complete list.

The inference is one-directional and does not rely on a passing test being
named. `ci.yml` runs `pytest -q`, which prints a filename only for a test
that did not pass, so `failures.txt` is the complete set of non-passing test
ids in a run that finished. Shard 1 finished, and no boolean id is in that
set. If any of the 69 boolean tests had failed on Linux, its id would be in
`failures.txt`, because that file is produced by the same grep over the same
log that produced the summary line. Its absence from a complete list is a
pass, and the one word the log does not contain is each test's name.

## Why the local 18 fail, and why Linux cannot hit it

Two distinct refusals, both platform guards that measure a host capability
and then decline rather than run with the boundary dropped.

`tests/test_boolean_ast_arm.py` (10 failures). `child_limit_support()` in
`experiments/ad01/boolean_ast_policy.py:74` tries `import resource` and
returns `available=False` when the import fails. Measured on this host:

```
platform: Windows
resource module: ABSENT -> No module named 'resource'
child_limit_support: available=False name=rlimit
```

`tests/test_boolean_policy_bridge.py` (8 failures). `src/settlement/child_limits.py:140`
refuses with `child-setup-unavailable` because CPython refuses `preexec_fn`
on Windows. The suite asserts an exact action dict, so the refusal where a
commit was expected is the assertion failing:

```
At index 0 diff: {'action': {'kind': 'stop', ... 'bridge_refusal':
  {'stage': 'policy-step', 'reason': 'refused: child-setup-unavailable:
  cpu_seconds: CPython refuses preexec_fn on Windows'}}}
```

Neither is reachable on Linux. `resource` is a POSIX module and
`preexec_fn` is accepted there, so both guards take the available branch.
`tests/test_boolean_graph_arm.py` passes 12/12 on this host because it drives
the action-graph representation directly and spawns no capped child, which is
the control case that shows the other two suites are refusing for the
platform and not failing for their own logic.

Local totals: `graph_arm` 12 passed / 0 failed, `ast_arm` 37 passed / 10
failed, `policy_bridge` 2 passed / 8 failed. The 18 is 10 + 8 + 0.

## The counts are the Linux counts

`REPRESENTATION_BINDING` (`experiments/ad01/s09_verdict.py:398`) maps the
three names the test asserts on:

- `step` -> `tests/test_boolean_policy_bridge.py`, pinned `== 10`
- `policy_ast` -> `tests/test_boolean_ast_arm.py`, pinned `== 47`
- `action_graph` -> `tests/test_boolean_graph_arm.py`, pinned `== 12`

Collection on Linux gives 10, 47 and 12 for those three files. The pinned
values are that count. They are not a tuned constant that happened to go
green; they are what a passing Linux run of the three suites reports.

The Windows run reports the same totals but splits them differently, because
`SuiteResult.passed` counts the `passed` line while the totals include
failures. That is the whole mechanism by which a local run could tempt a
re-pin, and it is why re-pinning would replace a correct expectation with a
platform artifact.

## Why the ownership claim survives a 224-test collection gap

This host collects 4622 ids where CI collected 4846 on the same commit, so a
local assignment could in principle be the wrong one. It is not, and the
margin is the reason. Collection is alphabetical by path, so the three
suites sit at ids 531-599 against a group-1 boundary of 1155. A 556-test
margin cannot be moved by a 224-test difference in total collection, and the
suites are contiguous at the front of the ordering. This is the reason the
claim is measured on the commit CI ran rather than on the worktree head.

## Can a test hang invisibly here? Yes, and nothing guards it

This is the more valuable finding, and it is not the same finding as the 18.

`run_representation_suite` (`experiments/ad01/s09_verdict.py:442`) calls
`subprocess.run` with **no `timeout=`**. A child that never exits therefore
never returns. Measured directly: a probe test that loops forever was not
reported by pytest in any form, and only an external killer ended the
process (`rc=9` from an `os._exit(9)` timer). pytest produced no output about
the test at all.

Nothing in the configuration would catch it:

- `pytest-timeout` is **not** a declared dependency. `pyproject.toml` has
  `test = ["pytest>=8.0", "hypothesis>=6.0"]` and no timeout entry, and
  `pip show pytest-timeout` reports not found in this environment.
- `pyproject.toml` sets `testpaths` and `norecursedirs` and registers the
  `swe_matrix` marker. There is no `addopts`, no `timeout`, and no
  `--timeout` anywhere in the repo's config or workflow.
- `docs/LONG-RUNNING-TESTS.md` describes `scripts/run_bounded.py`, which
  bounds a whole process. Its doc quotes a `timeout-2.4.0` plugin in a
  pytest header line, which is where that reading comes from. CI does not
  call `run_bounded.py` for the suite at all.
- The only bound that fires is `timeout-minutes: 100` on the job
  (`.github/workflows/ci.yml:35`).

So the job timeout is not a safety net for a hanging test; it is the only
thing that ends the job, and by then the artifact is a truncated log.

### The consequence, measured across run history

A `cancelled` conclusion on `suite (py3.134)` after exactly 100 minutes
means the job hit the timeout, not that pytest exited. In 9 of the last 25
runs that is exactly what happened:

| run | py3.134 conclusion | elapsed |
|---|---|---|
| 37261826154 | cancelled | 100 min |
| 37251210268 | cancelled | 100 min |
| 37236035655 | cancelled | 100 min |
| 37228382802 | cancelled | 100 min |
| 37172638343 | cancelled | 100 min |
| 37169028242 | cancelled | 100 min |
| 37157176367 | cancelled | 100 min |
| 37156961474 | cancelled | 100 min |
| 37156401502 | cancelled | 100 min |

Every one of those nine is a run whose overall conclusion is `failure`. The
job that owns `test_s09_verdict.py` never once finished on its own pytest
exit across that window. Each of its artifacts is a 615 or 630-byte
truncated progress fragment, and none has a `failures.txt` at all, so the
run names no test as failed. Checked on 37261826154 (630 bytes),
37251210268 (615 bytes) and 37277929945 (630 bytes).

This is precisely the vacuous green. `test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run`
could not reach its own assertions for the whole life of the test, and the
only signal was a job that went red for an unrelated reason in the same run.
Nothing said "this test hung". A red run was readable as "some tests failed"
and the hang was indistinguishable from a slow suite.

### Why the deadlock went unnoticed for that long

The stall is a per-token advisory lock. `run_representation_suite` copies the
parent environment, so the child inherits `S09ISO_TOKEN` and asks for the
lock the parent holds for the whole suite. `9e164b29` fixed it by setting
`S09ISO_DISABLE` in the child. That commit is dated 2026-10-05 04:15:52
-0400 and `d4eb4126` is dated 00:01:30 -0400 the same day, so run
`37261826154` predates the fix and cannot show the corrected behaviour. The
fix is an ancestor of `eb0538fa` and of `f3145187`.

The fix is confirmed working by the run cited above: shard 4 produced a
171 KB artifact with a terminal summary in 32 minutes where it previously
produced a 615-byte fragment in 100. The defect that hid the 18 is itself
now closed.

### The guard is still missing

`9e164b29` fixed this instance. It did not add a bound, so the next
`subprocess.run` that waits on something that never returns will stall the
same way and be equally invisible. Nothing in the current tree would name the
hung test. The probe above is the evidence for that: a test that never
finishes produces no pytest output at all, and the only signal is a job that
goes red for an unrelated reason.

## What was run, what was read, what is inferred

**Run locally.** `import resource` on this host (absent) and
`child_limit_support()` (available=False, quoted above). The three boolean
suites via `python -m pytest` with `S09ISO_DISABLE=1`, giving the 12/0,
37/10 and 2/8 split. The hang probe, giving `rc=9` with no pytest report. A
collection of `d4eb4126` from a `git archive` scratch tree under
`--splits 4`, giving the id ranges and the shard assignment.

**Read.** Shard-1 `suite.log` and `failures.txt` from runs 37285167407,
37261826154, 37251210268 and 37277929945. Shard-4 `suite.log` and
`failures.txt` from those four runs (615- and 630-byte fragments pre-fix,
171 KB post-fix). The job list and timing of 25 runs via `gh api`.
`boolean_ast_policy.py`, `child_limits.py`, `s09_verdict.py`, `ci.yml`,
`pyproject.toml`, `docs/LONG-RUNNING-TESTS.md`.

**CI confirmed for all four suites, post-fix.** Run `37285167407`, commit
`f3145187`, which contains the deadlock fix.

- Shard 1, artifact `suite-py3.13-1`: `26 failed, 1186 passed, 3 skipped,
  3642 deselected in 693.53s`, and `grep -c '^FAILED tests/test_boolean_'` is
  0. That job's failure set is byte-for-byte the same 26 lines as the
  pre-fix run `37277929945`: 0 new, 0 removed. The 26 sit in
  `test_a40_admission_wired.py`, `test_a41_reuse_id.py`,
  `test_a42_chain_demonstration.py`, `test_ad01_live_acquired_ddmin.py`,
  `test_ag01_experiment.py`, `test_aleb_construct.py`,
  `test_alec_episode.py`, `test_alee_learner.py`, `test_bacq_method.py`,
  `test_evidence_integrity.py`, `test_evidence_supersession.py` and
  `test_final_accept_findings.py`. None is a boolean suite. Those 26 are
  pre-existing and belong to other lanes.
- Shard 4, artifact `suite-py3.13-4`: `52 failed, 1157 passed, 2 skipped,
  3645 deselected, 1 xfailed in 1929.57s (0:32:09)`, and
  `grep -c '^FAILED tests/test_s09_verdict.py::'` is **0**. The 52 sit in 16
  unrelated s09/s89 files.

Shard 4 is the more decisive of the two, because it is the job that owns
`test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run`. Its
artifact is 171 KB with a terminal summary and a `failures.txt`, against the
615- and 630-byte fragments with no `failures.txt` in every pre-fix run. That
test asserts `mechanism.value == 'true'` and the literal counts 10, 47 and 12
against three real nested pytest runs on Linux, and it passed. The deadlock
is fixed and the pinned counts hold on the platform CI runs.

One caveat on this run: it reports `cancelled`, at 33 minutes, because
`concurrency: cancel-in-progress: true` on group `ci-${{ github.ref }}`
killed it when push `75c8f778` landed. The cancel came after pytest had
already written its summary, so the shard-1 and shard-4 artifacts are
complete and the conclusions above are read from real pytest output, not from
the cancelled status. Runs 37284225263 and 37282831111 were cancelled the
same way, earlier, before they produced any artifact.

**Inferred, and labelled as such.** That the truncated 615-byte shard-4 logs
are the hang rather than a crash is inferred from the 100-minute elapsed time
matching `timeout-minutes: 100` exactly in nine runs. The causal link to the
advisory lock is read from `9e164b29`'s own measurement, not re-measured here.

## Recommendation

Do not re-pin the counts. If a guard is wanted against the next hanging test,
the smallest change that fails on a genuinely hanging test is a `timeout=` on
the `subprocess.run` at `experiments/ad01/s09_verdict.py:442`, or declaring
`pytest-timeout` and setting it in `pyproject.toml`. Either turns a silent
100-minute stall into a named failure. Neither is in this lane's owned scope,
and neither is made here: this file is the whole diff.