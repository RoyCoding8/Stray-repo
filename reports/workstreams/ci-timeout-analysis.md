# Where the CI suite's time actually goes

**Conclusion first.** The four shards that hit the 100-minute job timeout were
not slow. They stopped. Each one ran for 42.2 minutes, then produced **no
database activity at all for 57.8 minutes** while the job sat there until the
timeout killed it. A timeout raise does not fix this. It buys a longer wait in
front of the same stall.

Everything below is measured from CI run `37251210268` at `91b36f8`. Read
2026-10-05. No pytest was run on the coordinator host.

## 1. The mechanism: a 57.8-minute silent stall

Source: the full console log of the cancelled `suite (py3.12)` job
(`gh run view --job 111579054542 --log`, 1,825 timestamped lines). The
PostgreSQL service container interleaves its own `UTC [pid]` lines into the same
stream, so its inner timestamps give a clock that keeps running when the
runner's own timestamps have collapsed to a single teardown instant.

Measured from those inner timestamps:

| Window | Value |
|---|---|
| First real database event | `01:23:12` |
| Last real database event before the stall | `02:05:27` |
| Active work | **42.2 min** |
| Total silence, no SQL of any kind | **57.8 min** |
| Job killed by `timeout-minutes: 100` | `03:03:16` |

Events per hour, counting only non-checkpoint lines:

```
  01:00   136
  02:00     0     <- the stall
  03:00     2     <- teardown: CREATE DATABASE ... already exists
```

Nothing is doing work. The process is alive and holding a connection. It is
not progressing.

## 2. It is not a slow test. It is one stall, at one test index.

The cancelled shards upload their artifacts under `if: always()`, so the
partial output survives. Those artifacts are the record. Extracting the
pytest result stream (progress characters only, percent markers stripped):

| Job | Results reported | Interpretation |
|---|---|---|
| group 1 (py3.131) | 1196 | complete |
| group 2 (py3.132) | 1196 | complete |
| group 3 (py3.133) | 1196 | complete |
| **unsharded (py3.12, py3.13, py3.14)** | **3829** | **stalled** |
| group 4 (py3.13 4) | 241 | **stalled** |

All three shards carry exactly 1196 results, so CI's 4783 collected tests split
into contiguous quarters of 1196 (4783 = 4 x 1196 - 1). The unsharded shards
stopped at index 3829. Group 4 starts at index 3588, so it stopped at
3588 + 241 = **3829 as well**.

**Two independently-computed stall points agree exactly.** Group 4 reaches the
same absolute test index whether or not it starts there or runs from zero.
That is the signature of one deterministic hang at one test, not of a
uniformly slow suite.

Independent cross-check: overlaying group 4's stream onto the unsharded
stream at offset 3588 gives 238 of 241 characters identical. The three
divergences are pytest retry noise on the same tests, not a different ordering.

`py3.12` and `py3.13` produced **byte-identical** `suite.log` artifacts
(SHA-256 `1fead380d38d688a`, 4253 bytes). The stall is deterministic and
independent of Python version.

Mapping that index onto the collected order at `91b36f8` puts the stall inside
the `test_s09_verdict.py` / `test_s09_verify_provenance.py` /
`test_s09_vocab_unify.py` block.

**Caveat, stated because it bounds the claim.** CI collected 4783 tests; a
local collect at the same SHA produced 4730, a gap of 53. The platform-gated
files (`test_child_limits_platform.py`, `test_launcher_local_bounds.py`,
`test_launcher_local_preexec.py`, `test_inv_b1_contracts.py`) hold 60
conditionally-skipped tests between them, which accounts for the gap in
magnitude. So **the exact test name is NOT MEASURED**; only the index (3829)
and the file block are. Pinning the name needs one Linux collection.

## 3. Why the shards that finished were fast

| Job | pytest wall time | Tests |
|---|---|---|
| group 2 (py3.132) | 250.83s | 1196 |
| group 3 (py3.133) | 642.02s | 1196 |
| group 1 (py3.131) | 713.75s | 1196 |

The fastest completed quarter did its work in **4.2 minutes**. The slowest took
11.9. `pytest-split` reports `[pytest-split] No test durations found` in every
shard, so it splits by test **count**, not by measured time. Its "estimated
duration: 1196.00s" is a count, not a measurement. **There is no
`.test_durations` file in the repo and no `--store-durations` in `ci.yml`.**

So the sharding has no runtime data at all, and the shards that happened to
land the stall were the ones that lost.

## 4. The most likely blocking construct, and why it is only a hypothesis

In the active window before the stall, the database logged 40 occurrences of:

```
ERROR: could not serialize access due to concurrent update
STATEMENT: SELECT * FROM control WHERE id = 1 FOR UPDATE
```

`store.py:270` takes `SELECT * FROM control WHERE id = 1 FOR UPDATE` under
`SERIALIZABLE` with a `lock_timeout` derived from the command deadline
(`store.py:266-268`). A row every writer must take is a serializing point, and
40 serialization failures in 42 minutes says contention on it is real and
recurring.

**This is NOT MEASURED as the cause of the 57.8-minute stall.** The evidence
for it is circumstantial: contention is present, and the stall follows a period
of it. The log cannot say which test was running, because the job was killed
before pytest printed a result or flushed a name. Naming
`test_s09_verdict.py` as the culprit would be a guess.

Two facts argue against the obvious reading. The last events before the stall
are `DELETE ... violates foreign key constraint` on `allocations` and
`operations` (`01:59:15`), which are cleanup-style statements, and they are
errors the test presumably handles. And the two database events *after* the
stall, at `03:03:14`, are `CREATE DATABASE "s09iso_b3120000_acct"` failing with
`already exists` — the session teardown of `IsolatedSuite.stop()` discovering a
database it could not drop. That points at the isolation teardown, not at a
single test.

## 5. Is this session's doing? No.

| Question | Answer |
|---|---|
| Commits between baseline `0ee4699` and tip `e177f6c4` | 88 |
| Commits touching `tests/` | 21 |
| Commits touching `tests/_heavy_archived/` | **0** |
| Did the stall-window files exist at baseline? | yes, all three |

No commit since the baseline added, removed, or edited the isolation
machinery. `tests/conftest_isolation.py`, `tests/conftest.py`'s fixture
wiring, and `pyproject.toml` are unchanged in their isolation behaviour; the
only `conftest.py` change since baseline is the addition of a `live_mission`
fixture helper.

**And the baseline behaves the same way.** Run `37172638343` at `0ee4699`,
taken before any of this session's work, lost the same four shards
(`suite (py3.12)`, `suite (py3.13)`, `suite (py3.14)`, and group 4) to the same
100-minute timeout. The defect predates the session.

## 6. `cancel-in-progress: true` — verified, and the figure is different from yours

Derived from `gh run view --json jobs` over eight runs, classifying each
cancelled job by whether it reached the 100-minute timeout:

**16 jobs hit the timeout** across 4 runs, exactly 4 per run, always the same
four shards:

| Run | Jobs that timed out |
|---|---|
| `37172638343` (baseline) | py3.12, py3.13, py3.14, py3.134 |
| `37228382802` | py3.12, py3.13, py3.14, py3.134 |
| `37236035655` | py3.12, py3.13, py3.14, py3.134 |
| `37251210268` | py3.12, py3.13, py3.14, py3.134 |

**21 jobs were cancelled short of the timeout** across 4 runs. Those are the
`cancel-in-progress` victims:

| Run | Jobs cancelled early | Elapsed |
|---|---|---|
| `37218826436` | 5 (all four suites + heavy) | ~30 min |
| `37220706587` | 4 (all four unsharded) | ~90 min |
| `37226556699` | 5 (all four suites + heavy) | ~29 min |
| `37235096706` | 7 (everything) | ~15 min |

**So `cancel-in-progress` cost this session 21 cancelled jobs, not four.** The
figure of four describes the timeout victims, which are a different mechanism.
Run `37220706587` is the sharpest case: those four jobs ran **90 minutes**
before being superseded, spending almost the whole timeout budget producing
nothing that was kept.

The honest reading is that `cancel-in-progress` is doing its job — these are
fast successive pushes to a long-running branch — and the cost is real but is
the price of not queueing 30-minute jobs behind each other. Two of those four
runs were superseded within 15-30 minutes, so a `cancel-in-progress: false`
would have queued them and burned the minutes anyway, just later. **This is a
judgement call about workflow latency, not a defect.**

## 7. `heavy archived`

**Yes, archived on purpose, and yes, it should keep running — but not for the
reason it is currently valuable.**

`tests/_heavy_archived/README.md` states the reason: 85 files moved there on
2026-09-29 because each spawns real child processes and a full run saturated
the host. They are excluded from default collection via `norecursedirs`
(`pyproject.toml:31`) because the cost is CPU and memory, not correctness.
They are not deleted and not expected to pass.

Measured cost, from the job's own step boundaries:

| Step | Duration |
|---|---|
| `heavy archived` total | 49.6 min |
| of which the 85-file loop | 48.9 min |
| Install | 0.23 min |
| Container start/stop | 0.34 min |

So the archived job consumes **49.6 minutes of a 120-minute budget** and
finishes with room to spare. It is not the timeout problem.

Per-file durations (measured between `=== <file>` markers):

| File | Seconds |
|---|---|
| `test_rpr13_endtoend.py` | 637 |
| `test_coord02_m4_frozen.py` | 169 |
| `test_coord02_experiment.py` | 125 |
| `test_rpr08_resume.py` | 122 |
| `test_rpr05_runner.py` | 74 |

The top file alone is 10.6 minutes. Half the total is reached by file 13 of 85.

**On its 143 failures.** The figure comes from the prior run's tally, not from
this run's log, and I could not corroborate it: `.a53-ci/ALL.failures` and
`heavy_archived.failures` are both present but the former contains no
`FAILED`/`ERROR` lines and the latter is 0 bytes. **NOT MEASURED.** What this
run does show is `files run: 85, files failing: 21, recorded failure lines:
94`. A 21-of-85 file failure rate, not 143 distinct tests.

The README's own claim that these files are "not failing" is contradicted by
this run. Several failures are environmental rather than real — the baseline
note already identifies 35 `.venv`-path failures where a test hardcodes a
developer's home directory, and 10 `pg_dump` server-version mismatches. Those
are worth fixing because a permanently red gate teaches reviewers to ignore
red.

## 8. Recommendation

**Do not raise `timeout-minutes`.** The evidence contradicts the premise that
the suite is too slow. A shard that completes 1196 tests in 4.2 minutes is not
slow. Raising the budget from 100 to, say, 180 would convert a 42-minute
detected stall into a 120-minute undetected one, and cost 80 extra minutes per
affected runner on every push — roughly **11 runner-hours per push** across the
four doomed shards, forever, in exchange for nothing.

**Do not split further either.** `pytest-split` is already dividing the suite
into quarters. Splitting into eighths does not help when a single test hangs:
the eighth containing it still hangs, and you pay twice the runner minutes to
find out.

### The fix that the evidence supports: bound every shard's wall clock

The shards that finish are bounded by nothing but the timeout. A hang becomes
a 100-minute outage precisely because nothing inside the job notices. Two
changes, both in `ci.yml`, both small:

1. **`--durations=50 --store-durations` on the suite run.** pytest-split then
   splits by measured time instead of test count, and the next run carries the
   evidence about which tests are actually slow. Today the sharding is blind.
   This also makes the `1196.00s` estimate mean something.
2. **`--timeout` on the pytest invocation** (pytest-timeout), set well under
   `timeout-minutes`. A test that cannot finish in N seconds is failed and
   named, so the run completes and produces a **measurement** instead of a
   cancellation. This is the change that converts "a cancelled measurement is
   not a null measurement" from a standing loss into a red test.

Cost: two pip installs and two flags. No extra runner minutes. It makes the
suite *report* the hang instead of dying on it, which is what actually unblocks
the coverage.

**The follow-up this unblocks, not implemented here.** Once a hang is named,
the real fix is in test code or fixtures, which this lane does not own. The
candidate the evidence points at, to be checked once the hang is named:
`store.py:266-274` serialises every command on `SELECT * FROM control WHERE
id = 1 FOR UPDATE`, and 40 serialization failures in 42 minutes says that
contention is real. Whether the hang is a lock wait, a lock_timeout expiry
loop, or the `IsolatedSuite.stop()` teardown that failed to drop
`s09iso_b3120000_acct` cannot be settled from the log, and should not be
guessed at.

### On `heavy archived` specifically

Keep it. 49.6 minutes inside a 120-minute budget is affordable, and it is the
only job that executes those 85 files. If the cost ever matters, the lever is
`test_rpr13_endtoend.py` at 637 seconds — one file, 10.6 minutes — not the
whole job. I would not change it as part of this fix.

## 9. Honest gaps

1. **The exact hanging test is NOT MEASURED.** Index 3829 of 4783 is measured.
   The name is not, because CI collects 53 more tests than a Windows
   collection and platform skips make the mapping non-uniform.
2. **The cause of the 57.8-minute stall is NOT MEASURED.** The serialization
   contention is real and precedes it; the causal link is inference.
3. Whether a lock wait, a `lock_timeout` retry loop, or the isolation teardown
   is responsible is unresolved.
4. The 143-failure figure for `heavy archived` could not be reproduced from
   the available artifacts. This run shows 21 of 85 files failing.
5. Per-test durations are **NOT MEASURED** anywhere. No shard passed
   `--durations`, and the `pytest -q` progress output carries no per-test
   timing. The "which tests dominate" question is answered at shard
   granularity only; the per-test answer requires the `--store-durations`
   change recommended above.
6. All measurements are from run `37251210268` at `91b36f8`. The baseline
   `37172638343` was not re-measured for stall position, only for the fact
   that it lost the same four shards.