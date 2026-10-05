# What a nested run should inherit

**Recommendation.** Option 3. A nested run takes **no claim and no databases**.
One line in `run_representation_suite` sets `S09ISO_DISABLE=1` in the child
environment, which is the switch this repository already built and already uses
for a nested pytest (`tests/_heavy_archived/test_s09iso_stale_sweep.py:401`).
It removes the deadlock rather than negotiating with it, and it *subtracts*
work: about 73 seconds of harness startup per nested suite, measured.

The deadlock is now **measured, not inferred**. The prior lane
(`reports/workstreams/hanging-test-identification.md:100-102`) recorded that no
lock-wait evidence appears in any log and that the mechanism had not been
reproduced. One line in the cancelled job's log closes that gap, and it does so
without the index arithmetic.

---

## 1. What the log settles

Read `.a53-ci/cancelled/full312.log`, the full console log of the cancelled
`suite (py3.12)` job of run `37251210268`.

| Server time | Event |
|---|---|
| `01:59:31` | last real database event (`.a53-ci/cancelled/full312.log`, pid 145123) |
| `03:03:14.707` | `##[error]The operation was canceled.` (runner wall clock) |
| `03:03:14.714` | `CREATE DATABASE "s09iso_b3120000_acct"` → `already exists`, **pid 151665** |

Seven milliseconds after the cancel, a PostgreSQL backend that appears nowhere
earlier in the log tried to create a database the parent had already created.
Four facts identify it as the nested child.

**It is a `CREATE`, and only one code path issues one.**
`IsolatedSuite.stop()` calls `drop_disposable_db`, which issues
`DROP DATABASE IF EXISTS ... WITH (FORCE)` and never a `CREATE`
(`experiments/ad01/s09_run_isolation.py:276-278`). The one `CREATE DATABASE` in
the harness is `IsolatedSuite._create` (`tests/conftest_isolation.py:683`). The
log contains exactly one `CREATE DATABASE` statement and zero `DROP DATABASE`
statements.

**The name is the *first* database a fresh run creates.** `scan()` returns its
37 seams sorted by variable name, and `IsolatedSuite.start()` creates them in
that order (`tests/conftest_isolation.py:691-694`). Executing the real scanner
over this worktree's `tests/` gives `EC02_ACCT_DSN → ec02test_acct` first, so
`derived_name("b3120000", "ec02test_acct")` is `s09iso_b3120000_acct`. That is
the name in the log, exactly.

**The token is the parent's.** `b3120000` is this job's pinned token,
`.github/workflows/ci.yml:28`, echoed into every step of the log. Only a
process running with `S09ISO_TOKEN=b3120000` can derive that name.

**The pid is new.** 151665 is the highest of the 86 backend pids in the log,
about 6500 above the next highest (145123), and it exists only for these two
lines.

### The chain this completes

`.github/workflows/ci.yml:52` puts `S09ISO_TOKEN` in the **job environment**, and
`tests/conftest_isolation.py` only ever *reads* it (`:140`), never writing it
back into `os.environ`. So the token is ambient, and
`run_representation_suite`'s `env = dict(os.environ)`
(`experiments/ad01/s09_verdict.py:427`) hands the child the parent's identity:

1. The parent's `pytest_configure` acquires
`pg_advisory_lock(lock_key("b3120000"))`
   (`tests/conftest_isolation.py:751`, `:635`).
2. The child inherits `S09ISO_TOKEN=b3120000` and its own `pytest_configure`
   calls `pg_advisory_lock` on the **same key**, which blocks rather than
raising.
3. The parent waits in `subprocess.run`, which has **no `timeout=`**
   (`experiments/ad01/s09_verdict.py:431-434`).
4. Nothing times out. 63 minutes of silence.
5. The runner cancels. `RunClaim._on_signal` fires, calls `release()`, and
   `self._conn.close()` returns the session lock to the server
   (`tests/conftest_isolation.py:644-652`).
6. Seven milliseconds later the child's blocked lock is granted and it proceeds
   into `suite.start()`, where the first `CREATE` finds the parent's database.

Step 6 is the inference, and it is tightly bounded: a cold import of this
closure measures 0.36-0.89 s (`tests/test_boolean_ast_arm.py:441-443`), so
there is no 63-minute startup story. And a child that had *not* blocked on the
lock would have issued its `CREATE` in its first second, not 7 ms after a
cancel. The release-then-proceed timing is what a blocked `pg_advisory_lock`
does.

**Confirmed on an independent run.** Run `37261826154`, job `111610465515`,
same commit family: cancel at `05:42:54.192`, `CREATE DATABASE
"s09iso_b3120000_acct"` → `already exists` at `05:42:54.198`, pid 151739. Six
milliseconds. The signature is identical across runs.

**What this dissolves.** The prior report's largest caveat was that index 3829
rests on a reconstruction verified only to index 3523, leaving a 306-index
unanchored window
(`reports/workstreams/hanging-test-identification.md:26-30`). That caveat was
about *naming the test from its position*. The mechanism is now established
from the log itself, so the repair no longer depends on the name being right.
Re-running the collection tool against this worktree confirms why. It puts
index 3829 at
`test_contaminated_utility_is_not_comparable_on_the_executed_digest`, because
this tree is not the CI tree. The name and the mechanism have come
apart, and only the mechanism is load-bearing.

---

## 2. Is the token a correctness mechanism or an isolation mechanism?

**Isolation, and specifically garbage-collection safety.** The module docstring
states the purpose: two runs sharing a store is "a serialization failure or a
deadlock", and the fix is "one store per run, not a longer timeout"
(`tests/conftest_isolation.py:6-7`). The token supplies the uniqueness, and it is
half of `derived_name` (`tests/conftest_isolation.py:149-169`).

`RunClaim` is narrower than that. Its docstring says what it is for: the
databases cannot be reclaimed by age alone, because a run that has been going
ninety minutes is indistinguishable from one killed an hour ago, and "what
separates them is that the first still has a process attached"
(`tests/conftest_isolation.py:617-624`). The lock is a **liveness proof the
stale sweep reads**. `stale_plan` refuses to touch any database whose token
`_token_locked` reports as held (`tests/conftest_isolation.py:546`, `:572`).

So the claim is not mutual exclusion between rival runs. It is a receipt that
says "some process is alive and owns these names". Two consequences follow.

**The databases were never at risk from each other.** They are unique by name
before any lock is taken. The lock adds nothing to uniqueness; it adds only
"and here is proof the owner is breathing".

**A nested child is not a peer run.** It is a step inside a run. Requiring it
to present its own receipt is a category error: it makes a subprocess look like
a rival process. This is the shape of the bug, and it is the premise worth
attacking.

### The premise, written down

> A nested pytest must go through the same isolation machinery as a top-level
> pytest, so it needs the token, so it needs the claim.

Two facts falsify the premise's first clause.

**The child already has isolated databases without doing anything.** The
parent's `apply_environment` rewrote 37 seam variables plus
`SETTLEMENT_TEST_DSN` and `SETTLEMENT_TEST_TRUNCATE_DSN` into its own
environment *before* any test ran (`tests/conftest_isolation.py:691-697`,
`:699-727`). `dict(os.environ)` copies those already-redirected values. So the
child is pointed at `s09iso_b3120000_*` whether or not it runs any isolation
machinery of its own. Under this option the child shares the parent's per-run
names. It never touches the shared `ec02test_*` names.

**The bug only exists because CI pins the token.** Unpinned, `run_token()`
falls through to `secrets.token_hex(4)` (`tests/conftest_isolation.py:138-146`),
so the child derives a *different* token and there is no deadlock at all. The
failure is created by `.github/workflows/ci.yml:52` making run identity ambient
environment state rather than something the process owns. Verified in the log:
`S09ISO_TOKEN: b3120000` is present in every step of every cancelled job.

That is the accidental coupling to remove. It explains why this never appeared
in local runs, and it means the "fix the token" framing is aimed one level below
where the fault lies.

---

## 3. The options

### Option 1. A distinct token for the child

`env.pop("S09ISO_TOKEN", None)`, matching
`tests/test_a42_chain_demonstration.py:152`, which already does exactly this
for a nested `experiments.ad01.cli`. The child then derives a fresh token, takes
its own claim, creates its own 38 databases, and drops them on exit.

**What it costs.** `docs/LONG-RUNNING-TESTS.md:222` measured a single-file run
at 73.7 s wall for 0.43 s of tests, where "the other 73 seconds were 38
database creations and migrations by the isolation harness". Three nested suites
means roughly **219 seconds and 114 databases per occurrence**. The test runs
once per shard that contains it; `test_s09_verdict.py` sits at collected index
3826 and group 4 starts at 3588, so that is the four shards that hang today.
Call it **about 15 runner-minutes per push**, permanently, for suites that read
no database.

**The strongest argument against it.** It pays the full isolation bill to
protect something the child does not use, and it leaves a second redundant copy
of 38 databases alive for the duration of three pure-logic suites. It converts
a hang into overhead rather than removing the hang's cause.

**Its one genuine advantage**, and it is a real one: if a nested test ever does
touch a store, it gets its own rather than the parent's.

### Option 2. `pg_try_advisory_lock`, failing loudly

Change `acquire` to try, and raise on failure
(`tests/conftest_isolation.py:633-635`). The child cannot wait, so it refuses
in seconds instead of 63 minutes, and the failure is named.

**What it costs.** This changes the contract for **every run in the programme**,
including every top-level run. Today a token collision produces two runs quietly
sharing databases. Afterwards it produces a hard startup failure. That is arguably more
correct. Silent contamination is what the isolation mechanism exists to
prevent, so failing loudly is defensible, but it is a programme-wide semantic
change and the human owns it.

It is also not sufficient alone. `try` makes this hang loud; it does not make
this test pass. The four shards would go red in seconds rather than in 100
minutes, which is a real improvement and a red gate either way.

**My read.** This is the right *detector* and the wrong *repair*. It is worth
doing, and it is worth doing **after** the repair, not instead of it. I am not
recommending it now because it does not remove the deadlock and because the
brief's tradeoff is exactly this: a local change versus a programme-wide
contract.

### Option 3. The nested run takes no claim *(recommended)*

`env["S09ISO_DISABLE"] = "1"` in the child. `pytest_configure` returns
immediately (`tests/conftest_isolation.py:745-747`). No claim, no sweep, no
databases, no teardown.

**Why the child does not need a claim.** The three nested suites
(`test_boolean_policy_bridge.py`, `test_boolean_ast_arm.py`,
`test_boolean_graph_arm.py`) are checked in `tests/`, are collected by the
parent in group 1 at indices 577-646, and pass there today. What they measure
is three policy representations: `policy_step`, `boolean_ast_policy`,
`boolean_graph_policy`. Measured on this tree:

- **No database reference in the three test files.** No `psycopg`, `connect(`,
  `DSN`, `dsn`, `dbname`, `migrated_db`, or `Store(` in any of them.
- **No test requests a fixture.** Every argument across all their test
  functions is a `parametrize` parameter. The only database fixtures in
  `tests/conftest.py` are `dsn` and `migrated_db` (`:23-43`), and neither can
  fire.
- **No database reference in the eight modules they exercise.**
  `boolean_active`, `boolean_policy`, `boolean_rule`, `policy_action`,
  `policy_step`, `worlds`, `boolean_ast_policy`, `boolean_graph_policy`, and
  `rule_learner` contain no `psycopg`, no `SETTLEMENT_`, no `dbname=`, and no
  `connect(`.
- **Nothing connects at import time anywhere in the repository.** Verified by
  AST over every `.py` file, matching both `connect(...)` and
`psycopg.connect(...)`
  at module scope, with a positive control to prove the detector fires.

**What it costs.** One line, and one real risk: if a future test in those three
files needs a database, it would share the parent's stores rather than get its
own. That risk is bounded, and smaller than it first looks. The child is
already pointed at the parent's per-run databases through `dict(os.environ)`, so
option 3 does not expose it to the shared `ec02test_*` names. The difference
between options 1 and 3 is *a second copy* versus *no second copy*, not
*isolated* versus *unisolated*.

It also saves runner-minutes rather than spending them, and it composes with
the per-test timeout: under option 1 a 300 s bound sits uncomfortably close to
the ~219 s of added harness overhead, and under option 3 it does not.

### The comparison

| | removes the deadlock | changes a programme-wide contract | runner-minutes per push | databases created per occurrence |
|---|---|---|---|---|
| **1. distinct token** | yes | no | **+15** | 114 |
| **2. `try` + fail loudly** | no, makes it loud | **yes** | ~0 (fails fast) | 38 more than today |
| **3. no claim (recommended)** | yes | no | **−15** | **0** |

---

## 4. The exact diff

Not applied. This changes which databases a research verdict is measured
against, `AGENTS.md` says not to erase uncertainty to unblock a study, and I
cannot execute the suite on this host to verify it
(`reports/workstreams/windows-env.md`).
The human owns that call.

In `experiments/ad01/s09_verdict.py`, inside `run_representation_suite`:

```python
 def run_representation_suite(root: os.PathLike | str,
                              test_file: str) -> SuiteResult:
     root = Path(root)
     env = dict(os.environ)
+    # This is a step inside a run, not a run. It shares the parent's already
+    # redirected per-run databases through dict(os.environ) above, and taking
+    # its own claim would deadlock: RunClaim.acquire blocks on the parent's
+    # token lock, which is why the four shards that reach this test sat silent
+    # for 63 minutes. The three suites measure policy representations and open
+    # no database, so there is nothing here for isolation to protect.
+    env["S09ISO_DISABLE"] = "1"
     env["PYTHONPATH"] = os.pathsep.join(
         [str(root), str(root / "src"),
          env["PYTHONPATH"] if env.get("PYTHONPATH") else ""])
     completed = subprocess.run(
         [sys.executable, "-m", "pytest", test_file,
          "-q", "--tb=no", "-p", "no:cacheprovider"],
         cwd=str(root), env=env, capture_output=True, text=True)
```

Four consequences worth stating, because a reader should not have to derive
them.

- `S09ISO_DISABLE` is documented at `docs/RUNBOOK-ISOLATED-FULL-SUITE.md:209`
  and already used for a nested pytest at
  `tests/_heavy_archived/test_s09iso_stale_sweep.py:401`. This is the existing
  idiom, not a new switch.
- `SETTLEMENT_TEST_DSN` and `SETTLEMENT_TEST_TRUNCATE_DSN` keep the parent's
  per-run values, because `dict(os.environ)` copied them after the parent's
  `apply_environment`. `migrated_db` would still work in the child, against the
  parent's store.
- The child's `_startup_sweep` does not run. It cannot drop anything.
- The parent still holds its claim and still runs `pytest_unconfigure`, so the
  `S09ISO: dropped 38 database(s) for this run` line returns.

**One thing I would add, and it is not this diff.** `subprocess.run` here has no
`timeout=`, which is why a child that hangs costs 63 minutes rather than 30
seconds. `run_pytest` in `experiments/ad01/m1_behaviour_gate.py:395` uses
`timeout=1800` and `tests/test_a42_chain_demonstration.py:157` uses
`timeout=900`, so a bound on a spawned suite is an established idiom here. I am
not proposing it as the fix, because it is additive and it does not remove the
cause. It is worth knowing that `m1_behaviour_gate.run_pytest` has the same
unbounded shape and the same unhandled `S09ISO_TOKEN`.

---

## 5. The per-test timeout

**I agree, with a number and a prerequisite.** It is worth having regardless of
which repair is chosen, because it converts an unmeasured stretch of the suite
into a measurement.

**Why, on this evidence.**

- A hang currently produces a cancelled job with no record of which test
  produced it. `pytest-timeout` produces a named failed test. The 63 minutes of
  silence in section 1 is what a *lack* of this flag looks like.
- `--store-durations` fixes the sharding, which is broken today. There is no
  `.test_durations` in the tree, `.gitignore` does not mention one, and every
  artifact carries `No test durations found`, so `pytest-split` splits by count.
  Its `estimated duration: 1196.00s` is a count wearing a unit. The cost of that
  is visible in the spread: the three shards that finished took 4.2, 10.7 and
  11.9 minutes for 1196 tests each. A 2.8× spread across equal-count shards.

**The number: 300 seconds.** Grounded on
`docs/LONG-RUNNING-TESTS.md:145-160`, whose slowest-table file is
`test_d02live_episode.py` at about 60 s. Everything slower in that table, so
`test_ec02ad_verif.py` at ~3 min, `test_s09iso_stale_sweep.py` at ~10 min,
`test_invr2_diagnostic.py` with a 300 s child deadline, lives in
`tests/_heavy_archived/`, which `norecursedirs` excludes from the suite job
(`pyproject.toml`). So 300 s clears the largest currently-collected file by 5×.

**What it costs in runner-minutes: nothing, and it saves a great deal.** Four of
seven shards currently burn the full 100-minute `timeout-minutes` and return
nothing, which is 400 runner-minutes per push, of which roughly 231 is pure
silence. Bounded at 300 s per test, a shard that hits the hang fails at the
hanging test and completes the rest of its work. Against the measured
completed-shard range of 4.2 to 11.9 minutes, those four shards land somewhere
in that band. The saving is on the order of 300 runner-minutes per push.

**The honest caveat: it does not fix anything.** With the deadlock still in
place, those four shards go *red faster* instead of cancelled slower. The
repair is what makes them green. The timeout is what tells you the repair
worked, and what names the next hang instead of hiding it for an hour. They are
complementary and the order matters: repair first, timeout immediately after.

**Prerequisite for whoever owns `ci.yml`, which I did not touch.**
`pytest-timeout` is **not** a declared dependency. `pyproject.toml` has
`test = ["pytest>=8.0", "hypothesis>=6.0"]` and the workflow installs
`pip install -e ".[test]"` plus `pytest-split`. It appears in a plugin header
at `docs/LONG-RUNNING-TESTS.md:59`, so it exists in some environments by
accident. It needs to be added to the `test` extra before `--timeout` means
anything in CI.

**`--store-durations` also carries an operational step.**
`pytest-split` reads `.test_durations` from the repository root. It does not
exist, so the first run writes it and **nothing benefits until it is
committed**. A run that writes it and does not commit it leaves the sharding
exactly as blind as before, while looking like the change landed.

---

## 6. What I could not determine

1. **Whether the three nested suites would ever need a database.** The static
   evidence in section 3 is strong and I trust it, but I cannot prove it by
   running, and the child never reached a test in either cancelled run, so
   there is no runtime evidence either way. This is the load-bearing
   uncertainty behind option 3. If it is wrong, option 3 points those suites at
   the parent's stores, which is degraded rather than incorrect.
2. **Whether the deeper import closure implies latent database use.** Walking
   imports from the eight modules reaches 59 files, including
   `experiments/ad01/trajectory.py` and `src/settlement/store.py`, which
   reference `psycopg`. Nothing connects at import time, verified with a
   positive control. But a *called* path could in principle reach one, and I
   did not trace call graphs, only imports.
3. **The index-to-name mapping at 3829.** I did not confirm it and I do not
   think it now matters. The prior bound stands. It is verified to 3523 with 306 indices
   unanchored, and re-running the tool against this worktree yields a
   *different* test at 3829 because this is not the CI tree. Section 1 makes
   the name unnecessary for the repair.
4. **The group-4 orphan pids.**
`reports/workstreams/hanging-test-identification.md:331-335`
   reports `Terminate orphan process` for the nested pytest and its parent in
   the group-4 teardown. I did not re-derive that. The unsharded logs carry
   only the generic `Cleaning up orphan processes`, so the identification there
   still rests on the group-4 artifact alone.
5. **Whether other nested-pytest spawns share the bug.** I censused them. Three
   are already correct: `tests/test_a42_chain_demonstration.py:152` pops the
   token, `tests/_heavy_archived/test_s09iso_stale_sweep.py:401` sets
   `S09ISO_DISABLE`, and `tests/test_conftest_isolation.py:74-76` sets or pops
   the token per case. `run_representation_suite` is the only live instance.
   `experiments/ad01/m1_behaviour_gate.py:390` has the same unhandled
   `S09ISO_TOKEN` and no `timeout=`, but nothing under `tests/` calls it, so it
   is latent rather than firing.

---

## Provenance

Worktree `.worktrees/hangfix` at `980e3c26`, branch `wt/hangfix`. No pytest was
run on this host and no PostgreSQL was contacted, per
`reports/workstreams/windows-env.md`. No model or provider call was made. No
credential was read, printed, or written.

Evidence read this session, in the worktree unless stated:
`tests/conftest_isolation.py` (full, 822 lines),
`experiments/ad01/s09_verdict.py:424-441`,
`tests/test_s09_verdict.py:160-200`, `:500-540`,
`.github/workflows/ci.yml` (read only, not modified),
`experiments/ad01/s09_run_isolation.py:267-289`,
`docs/LONG-RUNNING-TESTS.md:139-232`,
`docs/RUNBOOK-ISOLATED-FULL-SUITE.md:30-60`, `:200-220`,
`reports/workstreams/hanging-test-identification.md`,
`reports/workstreams/ci-timeout-analysis.md`,
`.a53-ci/cancelled/full312.log`,
and run `37261826154` job `111610465515` via `gh run view --log`.

Derived by running the repository's own code, not by reading it:
`conftest_isolation.scan()` over `tests/` (37 redirectable seams, first is
`EC02_ACCT_DSN`),
`derived_name("b3120000", "ec02test_acct")` = `s09iso_b3120000_acct`,
`reports/workstreams/hang-tool/collection_order.py` over this worktree,
an AST census of module-level `connect()` calls,
and an AST import-closure walk from the three nested suites.