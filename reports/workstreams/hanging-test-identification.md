# Naming the hanging test

The four shards that lost the 100-minute timeout stop at the same collection
index. This names the test at that index, with the chain that gets there and
the bounds on how wrong it can be.

## Answer

```
tests/test_s09_verdict.py::test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run
```

Collection index **3829**, file `tests/test_s09_verdict.py`, which occupies
indices 3807–3836 (30 tests). The stall begins at the first character of this
test's result: the preceding test at index 3828 completed and printed its dot.

The test body is `src/tests/test_s09_verdict.py:525`:

```python
def test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run(contaminated):
    suites = {name: verdict.run_representation_suite(REPO, test_file)
              for name, (_, test_file) in verdict.REPRESENTATION_BINDING.items()}
    mechanism = verdict.mechanism_verdict(REPO, suites)
    assert mechanism.value == 'true'
    ...
```

`run_representation_suite` (`src/experiments/ad01/s09_verdict.py:424`) shells
out to a **nested pytest**:

```python
completed = subprocess.run(
    [sys.executable, "-m", "pytest", test_file,
     "-q", "--tb=no", "-p", "no:cacheprovider"],
    cwd=str(root), env=env, capture_output=True, text=True)
```

Three nested suites are launched, `tests/test_boolean_policy_bridge.py`,
`tests/test_boolean_ast_arm.py` and `tests/test_boolean_graph_arm.py`, which is
why the test asserts `counts["step"] == 10`, `counts["policy_ast"] == 47`,
`counts["action_graph"] == 12`.

**The hang is in a test body, not in cleanup.** The nested pytest blocks
before producing output, and `subprocess.run` has no timeout, so the parent
test never returns and `pytest_unconfigure` / `IsolatedSuite.stop()` are never
reached.

## Why the nested pytest blocks

`tests/conftest.py` imports `pytest_configure` from `tests/conftest_isolation.py`,
which claims the run's identity at startup (`conftest_isolation.py:747`):

```python
def pytest_configure(config) -> None:
    if os.environ.get(DISABLE_ENV):
        return
    suite = IsolatedSuite(plan())
    config._s09iso_suite = suite
    claim = RunClaim(suite.plan.token, suite.plan.admin_dsn).acquire()
```

`RunClaim.acquire` (`conftest_isolation.py:633`) takes a PostgreSQL
**session-level advisory lock** keyed on the run token:

```python
def acquire(self) -> "RunClaim":
    conn = _admin_connection(self._admin_dsn)
    conn.execute("select pg_advisory_lock(%s)", (lock_key(self.token),))
```

`run_representation_suite` passes `env=dict(os.environ)` through to the child,
so the child inherits the same `S09ISO_TOKEN`. The child's own
`pytest_configure` therefore calls `pg_advisory_lock` on the **same key** the
parent already holds. `pg_advisory_lock` blocks indefinitely rather than
raising. The parent waits on `subprocess.run`, the child waits on the lock, and
nothing times out.

This is a self-deadlock, which is why it is deterministic and identical on every
attempt, and why the stall begins at exactly the same index in every run that
reaches this test.

The mechanism is **inferred from the source**, not measured at runtime. It is
the only path I found that produces an indefinite block with no output, and the
inherited-token precondition is directly readable in the two files above. No
lock-wait evidence appears in the CI logs, because PostgreSQL logs nothing for a
session waiting on an advisory lock it never acquires. Marked INFERRED below
where it matters.

## Evidence chain

### 1. The stall index is 3829, from two independent routes

`pytest -q` writes one character per test and flushes a line every 72. Parsing
the three unsharded `suite.log` artifacts gives 53 complete lines of 72
characters plus a partial line of 13, which is **3829** results.

`pytest-split` reported `No test durations found` and
`Splitting tests with algorithm: duration_based_chunks` in every artifact, so it
split by count. 4783 tests over 4 groups is 1196/1196/1196/1195, so group 4
starts at global index **3588** and ran **241** results, which is global index
**3828** completed and **3829** begun.

I confirmed the group boundaries by aligning the per-test outcome strings rather
than trusting the arithmetic. Group 1's outcome string is byte-identical to the
unsharded string's first 1196 characters, group 2's to the next 1196, group 3's
to the next 1196, and group 4's to positions 3588–3828 with 238 of 241
characters agreeing (the three disagreements are `.`/`F` pairs where a test is
flaky under sharding, not an ordering difference). No other offset comes close:
the next best for group 4 scores 228 of 241.

The two routes agree, and they were computed from different evidence.

### 2. The collection order is reproduced, and the reproduction is verified

`pyproject.toml:27` sets `testpaths = ["tests"]`, `norecursedirs` excludes
`tests/_heavy_archived`, and there are no `Test` classes and no platform-gated
conditional test definitions. `tests/conftest.py` has no `skipif` and no
`sys.platform` branch, and all 34 module-level `if` blocks in the tree contain
zero test functions. So collection is: `tests/` in sorted filename order, and
inside each file the module-level `test_*` functions in definition order.

That order alone is not enough. Mapping an index to a file also needs the number
of tests each file collects, and 151 `parametrize` sites make that a real
computation. `reports/workstreams/hang-tool/collection_order.py` resolves each
site's arity structurally, because only the count of a parametrize's argvalues
matters and never their values:

| shape | arity |
|---|---|
| `[a, b, c]`, or any literal container | element count |
| a module constant | its length, literal or measured |
| `sorted(X)`, `list(X)`, `tuple(range(N))` | `len(X)`, `N` |
| `[f(x) for x in X]` | `len(X)` |
| `[... for k, v in D.items() for x in v]` | `sum(len(v) for v in D.values())` |

Three defects had to be fixed to make it agree, and each was found by the
verification step rather than by inspection:

- A dict of `%`-formatted strings fails `ast.literal_eval` as a whole, so 38
  module constants read as length 0. A dict's arity is its key count.
- `[(mod, sym) for mod, syms in sorted(D.items()) for sym in syms]` multiplies
  the two generators when the second ranges over a value unpacked from the
  first. It sums them.
- pytest appends `[param-id]` with no space, so stripping it needs `split('[')`,
  not `split(' [')`.

**Validation.** The three completed shards each print a short summary naming
every failed and erroring test. Pairing those node ids, in report order, with
the positions of `F` and `E` in their outcome strings yields **174 anchors**, each
a (collection index, node id) pair that CI reported directly. The reproduction
places **all 174 at exactly the indices CI reported**, with zero mismatches and
zero unmatched.

The anchors are not all at one end. They span indices 0 to 3523, across 57
files, and they are dense enough to catch an off-by-one in any single file: an
earlier version of the tool matched 1 of 174 and each fix moved the count
(19, then 43, then 169, then 174). The residual between the reproduction and
CI's indices is zero at every anchor from index 0 to index 3523.

### 3. The bound on the error

The reproduction accounts for 4763 of CI's 4783 tests. The 20-test gap is three
`parametrize` sites whose arity is not statically derivable:

| file | site | reason unresolved |
|---|---|---|
| `tests/test_s09ast_contingent.py` | `test_every_admitted_action_came_from_the_typed_program` | `SEEDS` is a module import |
| `tests/test_s09o_export.py` | `test_mutations_name_the_failed_check` | `_mutations(None)`, a local function |
| `tests/test_s09swe_world.py` | `test_exceeding_any_tool_budget_is_refused` | `world.BUDGET_LIMITS.items()`, cross-module |

These sit at reproduced indices 3937, 4252 and 4415. **All three are after
index 3829.** They can only add tests to indices beyond the stall, so they
cannot move the test at 3829 in either direction. The residual is zero at every
anchor, and the nearest anchor after the correction is at index 3523, with no
shortfall file anywhere between 3523 and 3829.

The identified test is therefore the test at index 3829 exactly, not
approximately.

## Where the prior analysis stood, and what changed

The prior lane refused to name the file, and its reason was sound: a local
collect at the same SHA gives 4730 against CI's 4783, so index-to-file mapping
is not uniform and an approximate reproduction would be worthless. That is
correct and it is why this took a reconstruction rather than a guess.

Its index of 3829 I confirmed rather than assumed. The `3588 + 241 = 3829`
arithmetic is right, and the character-level alignment above is independent
corroboration of it.

One correction to the prior framing. The prior work reported the three unsharded
logs as byte-identical across interpreters and treated that as "one deterministic
hang". Two of the three are byte-identical; `py3.14` differs from `py3.12` and
`py3.13` at line 6, at collection index 424, where one test passes on 3.14 and
fails on 3.12/3.13. All three still stop at 3829 with the same test count, so the
hang is common to all three and the divergence is an unrelated flaky test.

## The serialization contention at store.py:266-274

**Refuted as the cause of the hang.** The evidence is timing and design.

The 40 `could not serialize access due to concurrent update` errors span
01:30:13.629 to 01:44:44.931. The stall begins after the run reached collection
index 3829, which is well past that window. The errors are also the mechanism
working: `src/settlement/store.py:267` sets a per-command `lock_timeout` from
the command's own deadline, so a serialized-out transaction is retried or
reported, not left hanging. 23 of them failed on
`SELECT * FROM control WHERE id = 1 FOR UPDATE` and 18 on
`UPDATE agenda_cursors SET tick = tick + 1, ...`, from 40 distinct backends, and
the run continued past all of them to index 3829.

Contention on the control row is real and worth its own look. It is not this
hang.

## Timing, from the container's own timestamps

The PostgreSQL container's interleaved log lines carry their own clock, which is
independent of the runner's. From `suite (py3.12)` job log
`37251210268:111579054542`, de-duplicated (the runner echoes each container line
twice):

- First real DB event `01:23:12`, collection finished `01:24:26`.
- Serialize storm `01:30:13`–`01:44:44`.
- FK-violation `DELETE`s `01:53:01`–`01:59:15`, from
  `tests/test_s09_swe_experiment.py`-style store teardown.
- Last event before silence `01:59:31` (a `database ... does not exist` FATAL).
- `The operation was canceled.` at `03:03:14`, the job's 100-minute timeout.
- Silence `01:59:31` → `03:03:14` is **63 minutes** with no database event.

The two post-silence events are **not** evidence about the hang. The single
`CREATE DATABASE "s09iso_<token>_acct"` that failed with "already exists" is
timestamped `03:03:14.714`, which is **after** the `##[error]The operation was
canceled.` at `03:03:14.707`. It belongs to the job being torn down, not to the
stall. The prior lane's reading that these point at `IsolatedSuite.stop()` is
refuted on timestamp order.

That `##[error]The operation was canceled.` line is also the direct evidence
that the stall was not slow-but-progressing: the runner cancelled a step that
had been producing no output for 63 minutes.

## Test body or cleanup

**Test body.** The stall is inside the nested `subprocess.run`, so
`pytest_unconfigure` never runs. Two independent supports:

- `pytest_unconfigure` (`conftest_isolation.py:799`) prints
  `S09ISO: dropped N database(s) for this run` on completion. Every completed
  shard prints it, all three of the cancelling shards print nothing.
- The group-4 shard's teardown logs `Terminate orphan process: pid (2952)
  (python)` and `pid (67024) (python)`. Those are the nested pytest and its
  parent, still alive at cancel. The three unsharded shards' logs carry no such
  line, which is consistent with their children having been reaped earlier or
  never surviving to the teardown sweep; I did not establish which.

The orphan evidence is direct for group 4 and absent for the other three. I am
not going to dress that up: the conclusion "test body" rests on the collection
index plus the source path, and on the orphan pids for group 4. It is not
independently corroborated by the unsharded teardowns.

## What is NOT established

- **The advisory-lock deadlock is inferred, not measured.** No lock-wait appears
  in any log, and I could not reproduce it: this host has no PostgreSQL, and
  `reports/workstreams/windows-env.md` forbids running pytest here. The
  inference is from the two source sites and the absence of any other
  indefinite-block path, which is strong but is not a measurement.
- **The reproduction is not verified past index 3523.** The last CI-reported
  anchor is at 3523. From there to 3829 the reproduction rests on the
  collection model plus the absence of any unresolvable site in that window,
  not on a CI-reported index. The three known unresolvable sites are all beyond
  3829, so the bound holds, but it is a bound derived from the model rather
  than from a measurement in the window itself.
- **No per-test duration data exists.** Confirmed, not assumed. No shard passes
  `--durations`, `pytest -q` carries no per-test timing, and every artifact
  contains `No test durations found`, which is why `pytest-split` split by
  count. There was no timing artifact to mine.
- **Why only four shards.** Groups 1, 2 and 3 never reach index 3829 and pass in
  4.2, 10.7 and 11.9 minutes. The unsharded runs and group 4 do reach it. I did
  not investigate whether groups 1–3 would hang given enough time.
- **Whether the fix is the lock or the nested pytest.** Two candidate repairs
  exist and I am not choosing between them, per scope. The test could give the
  child a distinct token, or `RunClaim` could take `pg_try_advisory_lock` and
  fail loudly instead of blocking. Which is correct depends on whether a nested
  run is meant to share the parent's databases, which is a design question I
  did not settle.

## Smallest experiment that would settle the inference

One command in CI, on a shard that reaches index 3829:

```
S09ISO_TOKEN= <distinct token> python -m pytest -q -p no:cacheprovider \
  tests/test_s09_verdict.py::test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run
```

If it completes with the shared token and hangs with a distinct one, the
advisory-lock deadlock is confirmed and the index is confirmed at the same time.
If it hangs either way, the cause is in the nested suite and not the lock. A
variant that runs `SELECT pg_locks` from a second connection during the stall
would show the waiter directly.

## Reproducing this

```
git archive 91b36f8755cafc8281e152a29b9c0117b38f0908 tests src experiments scripts | tar -x
python reports/workstreams/hang-tool/collection_order.py <dir>/tests \
    --verify reports/workstreams/hang-tool/anchors.json
```

`91b36f8` is the head SHA of run `37251210268`, the run that hung, not the
worktree's `d4eb4126`. The tree differs by 5 test files including
`tests/test_s09_normalizers.py` at +875 lines.

Artifacts read, all from run `37251210268`:
- `suite-py3.12-`, `suite-py3.13-`, `suite-py3.14-`, `suite-py3.13-1/2/3/4`
  `suite.log`, downloaded with `gh run download`. The four partial logs are
  byte-identical to the copies already on disk under `.a53-ci/cancelled/`
  (SHA-256 `1fead380d38d688a` for `py3.12-` and `py3.13-`).
- Full job logs for the four cancelled jobs, via
  `gh run view 37251210268 --log --job <id>`. The `py3.12` job log is
  byte-identical to `.a53-ci/cancelled/full312.log`.

The `cancelled/` and `full/` directories that already existed were populated by
an earlier lane from the same run, so the earlier attempt was not mistaken about
which run these came from; it had only read the summary lines.

## Fix, described and not applied

Scope says identify, not repair. The precise change: `RunClaim.acquire`
(`tests/conftest_isolation.py:633`) blocks forever on a lock its own child
process is guaranteed to want. Either the child gets a distinct token, or
`acquire` uses `pg_try_advisory_lock` and raises on failure so a token collision
surfaces as an error instead of a hang. The first is a one-line change in
`run_representation_suite`; the second changes the contract of every run, and
would turn a rare silent hang into a loud failure across the whole suite.