# CI failure causes, non-pg_dump subset — run 37305881683

**This is the cause map for the 65 non-pg_dump failures in the `heavy archived`
job of run `37305881683`.** It is the companion to
`reports/evidence/ci-failure-causes-37261826154.md` (run `37261826154`, tree
`d4eb4126`), which classified the same archived files when the job printed no
traceback bodies. This pass has the bodies and re-derives every cause from them.

Every cause below cites the traceback line range it was read from, and the
source line the mechanism was read from where the traceback alone does not
settle it. One failure is left explicitly unrooted rather than assigned a
guessed cause.

**Which tree, stated exactly.** `gh api .../runs/37305881683` reports
`head_sha = 1dc9b23cacf73d3235d3a7b505775fdeef611db6` on
`codex/agent-society`, created 2026-10-05T11:53:48Z, conclusion `cancelled`.
**This is not the `d4eb4126` the prior report measured, and the two runs are not
the same tree.** I verified rather than assumed: `git diff --stat 1dc9b23 HEAD`
over the 19 archived test files, the 4 `src/settlement` modules and the 2
`experiments/ad01` modules this document cites returns **only
`.github/workflows/ci.yml`, 14 insertions**. So every code line cited here is
byte-identical at the tree that ran and at HEAD, and this report's labels hold
at both. The 9 commits between the two SHAs touch only CI config, and 4 of
those are the `postgres-client` repair that fixes the 7 excluded pg_dump IDs.

The tooling is re-runnable and uncommitted, under `.scratch/heavy-census.js`.
It re-parses `D:/a55/heavy-failures.txt`, re-asserts the 72 and 65 counts,
re-joins each ID to a cause, and re-emits
`reports/evidence/heavy-nondump-causes.csv`. It refuses to write if any of the
65 is unassigned or if the counts do not reconcile.

**No `.py` file was edited.** Where a fix is certain it is written as a spec.

## What the artifacts actually contain

The brief stated that 6 of the 72 lines have no parseable `file::` prefix.
**They all parse. I checked every one and this is wrong.** All 72 lines match
`^(FAILED|ERROR) <file>::<test>`, and all 72 have a traceback body in
`heavy-tracebacks.log`. A naive header regex finds 71 because pytest emitted
one section header with 2 underscores (`__ test_a_confinement_capable_host... ___`,
log line 711) rather than the 3-or-more the others use, so that one looks
unmatched. It is not unmatched, it is differently-punctuated. **The unrooted
count from a header regex is 1, and that 1 is a parse artifact, not a gap.**

| Artifact | Contents |
|---|---|
| `heavy-failures.txt` | 92 lines, 72 `FAILED`/`ERROR` IDs, 20 files |
| `heavy-tracebacks.log` | 415,413 bytes, 8,390 lines, a body for all 72 |

This closes the artifact gap the prior report named as its highest-value fix.
The prior report said the `-q` flag suppressed the FAILURES block and left 60
IDs unrootable. `ci.yml:180-199` now runs `python -m pytest -p no:cacheprovider`
with no `-q` and archives the full body, and the 72 confirm it. **That repair
worked, and it is what made this document possible.** Nothing in this report is
`inferred` from a truncated summary line.

## Headline

| | |
|---|---|
| Failing IDs in the job | **72** |
| Excluded: `pg_dump` version mismatch, repaired separately | **7** |
| **Subject of this report** | **65** |
| Named causes | **13** |
| **Unrooted** | **1** |
| Verdict `code-defect` | **59** (90.8% of 65) |
| Verdict `environment` | **5** (7.7% of 65) |
| Verdict `unrooted` | **1** (1.5% of 65) |

## Cause table

Groups are disjoint and sum to **65**. Percentages are of 65.

| Cause | IDs | % of 65 | Verdict | Evidence anchor |
|---|---|---|---|---|
| A `.venv` interpreter path CI never creates | **35** | 53.8% | code-defect | `FileNotFoundError: ... /.venv/bin/python` |
| B Execution-authority refusal on out-of-process execution | **10** | 15.4% | code-defect | `refused: execution needs explicit authority and identity` / `PolicyNotProved` |
| F Committed developer-local socket DSN | **4** | 6.2% | code-defect | `connection to server on socket /var/run/postgresql/.s.PGSQL.5432 failed` |
| C Landlock ruleset install raises inside `preexec_fn` | **3** | 4.6% | environment | `child-setup-failed: SubprocessError: Exception occurred in preexec_fn.` |
| D `pg_dump` mismatch behind a `pytest.raises(match=)` assertion | **2** | 3.1% | environment | `Actual message: 'pg_dump failed: ... server version mismatch'` |
| E `run_live_abc.py` run as a script cannot import its package | **2** | 3.1% | code-defect | `ModuleNotFoundError: No module named 'experiments'` |
| G DBOS 3.0 removed `database_url` | **2** | 3.1% | code-defect | `DBOS Error 3: DBOSConfig sets database_url, which was removed` |
| H Checker scores an honest refused record | **1** | 1.5% | code-defect | `assert False` on `score-without-oracle-evidence B-gr-eva-00` |
| I `reserve` refuses an unknown operation before the capacity check | **1** | 1.5% | code-defect | `assert insufficient_resources == invalid_input` |
| J `responses` API refused on a frozen route, before the wire | **1** | 1.5% | code-defect | `AttributeError: 'GatewayError' object has no attribute 'text'` |
| K Test asserts `sent is True` on a `Popen` it made fail | **1** | 1.5% | code-defect | `child-setup-failed: OSError: parked before spawn` |
| L `scrub_env` publishes `PYTHONPATH`, the assertion predates it | **1** | 1.5% | code-defect | `At index 2 diff: 'PYTHONPATH' != 'SETTLEMENT_OPERATION'` |
| M Role name `ubuntu` that the CI service does not have | **1** | 1.5% | code-defect | `role "ubuntu" does not exist` |
| Z **Unrooted** | **1** | 1.5% | unrooted | see the unrooted section |
| **Total** | **65** | **100%** | | |

## Cause A, 35 IDs, and the two hardcoded paths that are not the same defect

35 of 65 is 53.8%, and the brief asked for this one carefully because the
earlier grouping of it was unreliable. **It is one mechanism with two
literals, and the second is worse than the first.**

The first is a derived path. `tests/_heavy_archived/test_run_bounded.py:45`
reads `PY = str(ROOT / ".venv" / "bin" / "python")`, and
`test_s09iso_stale_sweep.py:51` reads `VENV_PYTHON = REPO / ".venv" / "bin" /
"python"`. **CI installs the package with `pip install -e ".[test]"`
(`ci.yml:170`), which never creates a `.venv`.** The tests therefore spawn a
path that does not exist, and the interpreter they are trying to run a
`sys.executable` child under is the one already running them.

The second is a **committed literal absolute path to a developer's own
machine**, and it is not derived from anything the repository knows:

```
tests/_heavy_archived/test_ec02ad_verif.py:1164-1166
    collected = subprocess.run(
        ["/home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest",
         "tests/test_ec02ad_verif.py", "--collect-only", "-q"],
```

Traceback, log lines 334-337 and the `FileNotFoundError` inside the 303-530
body:

```
    collected = subprocess.run(
>       ["/home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest",
        "tests/test_ec02ad_verif.py", "--collect-only", "-q"],
tests/_heavy_archived/test_ec02ad_verif.py:1164:
...
E               FileNotFoundError: [Errno 2] No such file or directory: '/home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest'
```

**This is the path the brief asked me to name, and it is named.** It is
`/home/ubuntu/AI/Agent-Society-v2/.venv/`, which is a WSL-side checkout of this
repository belonging to the `ubuntu` user. It can never be true on the GitHub
runner, whose checkout is `/home/runner/work/Stray-repo/Stray-repo`. The same
`role "ubuntu"` assumption reappears in cause M, so the repository carries two
committed references to a WSL-local layout.

| File | IDs | Path in the failure |
|---|---|---|
| `test_run_bounded.py` | 27 | `/home/runner/work/Stray-repo/Stray-repo/.venv/bin/python` |
| `test_s09iso_stale_sweep.py` | 7 | `/home/runner/work/Stray-repo/Stray-repo/.venv/bin/python` |
| `test_ec02ad_verif.py` | 1 | `/home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest` |

**Two distinct pytest frames, same defect.** The `run_bounded` and `s09iso`
failures blame `subprocess.py:1991` (the `Popen` in `test_run_bounded._run` at
`:77`) and `subprocess.py:1820` (the `posix_spawn` in
`test_s09iso_stale_sweep._spawn_holder` at `:164`). The spawn path differs and
the missing path does not.

**The 27 in `test_run_bounded.py` are one cause, not 27.** Every one of the 27
fails at the first `_run(...)` call in the test body, before any assertion
about the tool's behaviour is reached. The `subprocess.CompletedProcess` repr
in the traceback shows what the test meant to spawn and what it did:

```
self = <Popen: returncode: 255 args: ['/home/runner/work/Stray-repo/Stray-repo/.ven...>
args = ['/home/runner/work/Stray-repo/Stray-repo/.venv/bin/python',
        '/home/runner/work/Stray-repo/Stray-repo/scripts/run_bounded.py',
        '--timeout', '30', '--',
        '/home/runner/work/Stray-repo/Stray-repo/.venv/bin/python', ...]
executable = b'/home/runner/work/Stray-repo/Stray-repo/.venv/bin/python'
```

**`PY` is the tool's interpreter *and* the child interpreter in the same argv.**
`PY = ROOT/".venv"/"bin"/"python"` at `:45` is used both as the process to run
`scripts/run_bounded.py` and, inside the test bodies, as the command the tool
is asked to bound. Fixing only the outer one would leave the inner one broken,
so the fix has to derive the interpreter once and use it for both.

**The parametrized IDs, and what they vary over.** Ten of the 27 are one
test, `test_a_child_status_is_reported_unless_it_collides_with_ours`, at
`test_run_bounded.py:588-597`:

```python
@pytest.mark.parametrize("child,expected", [
    (0, 0), (1, 1), (9, 9), (123, 123),
    (124, 128), (125, 129), (126, 130), (127, 131),
    (130, 130), (200, 200),
])
def test_a_child_status_is_reported_unless_it_collides_with_ours(child, expected):
    proc = _run("--timeout", "30", "--", PY, "-c",
                "import sys; sys.exit(%d)" % child)
    assert proc.returncode == expected, (
        "child %d surfaced as %d" % (child, proc.returncode))
```

The bracket is `[child-expected]`, **not** a range. `[124-128]` means the child
exits 124 and the tool must surface 128, because 124, 125, 126, 127 and 130
are exit codes `run_bounded` reserves for itself and remaps. `[123-123]` and
`[200-200]` are the two that must pass through untouched, and `[0-0]`, `[1-1]`,
`[9-9]` are ordinary statuses. **The ten IDs are ten cases of one remapping
table, and the assertion the test exists to make was never reached in any of
them**, because `_run` raised before `run_bounded.py` was ever started. So
`test_run_bounded`'s entire exit-status contract, which is the reason the file
exists, is untested in this run. That is the cost of the missing `.venv`, and
it is larger than "27 tests are red".

**Fix, as a spec.** Derive the interpreter from `sys.executable` at
`test_run_bounded.py:45` and `test_s09iso_stale_sweep.py:51`. At
`test_ec02ad_verif.py:1165` the committed literal has no correct CI value, so
either derive it or, if the test genuinely needs a separate environment,
name what it needs and fail with that reason rather than with `ENOENT` on a
path from someone else's machine.

## Cause B, 10 IDs, and the prior report had this one at 9 in a different file

The prior report counted 9 IDs in `test_s09_bound_use_proof.py` under causes G
and H, both read from the truncated summary. **The tracebacks put all 9 under
one guard, and the same guard explains a 10th ID in a different file that the
prior report attributed elsewhere.**

Eight of the nine raise identically. Log lines 7209-7247, and the raise is
read from the source because the traceback's own frames do not reach it:

```
    def execute_bound_policy(binding: PolicyBinding_, view: dict, state: dict, *,
                             authority: Mapping[str, Any] | None = None,
                             operation_id: str | None = None) -> dict:
        ...
        binding.verified()
        record = binding.as_policy_record()
        policy_step.verify_policy_record(record)
        if not isinstance(authority, Mapping) or not authority.get("dsn") \
                or not authority.get("allocation_id") or not operation_id:
>           raise PolicyNotProved(
                "this proof executes the bound policy, so it needs a store, an "
                "allocation and an operation identity: it has no refusal to show "
                "and no result without them")
E           experiments.ad01.s09_bound_use_proof.PolicyNotProved: this proof executes the bound policy, so it needs a store, an allocation and an operation identity: it has no refusal to show and no result without them
```

`experiments/ad01/s09_bound_use_proof.py:285`, blamed by pytest at every one of
the 8. **The test calls it with no authority at all.** `test:95` reads
`result = proof.execute_bound_policy(binding, proof.use_view(), {})`, and the
same shape recurs at `:124` and `:197`. The module provides
`proof_authority()` at `:297`, a context manager that mints a disposable store
and an `authorize_study` allocation, and **no test in the file uses it.** So
the guard works exactly as written and the callers are the stale half.

`git blame` puts the guard and the test in the wrong order, and the dates alone
cannot settle it, so I checked ancestry: `git merge-base --is-ancestor 54c0e4c8
9b8c5ecf` is true and `54c0e4c8` (which wrote both the test file and the
pre-guard version of the executor) is 2026-10-02, while `9b8c5ecf` "Give the
bound-use proof the authority its execution needs" is the later commit that
added the guard. **The test predates the requirement and was not migrated.** The
9th ID in the file is the same defect in a different form, at `test:189`:

```
>       assert "unknown policy action kind: 'use'" in str(step_refusal.value)
E       assert "unknown policy action kind: 'use'" in 'refused: execution needs explicit authority and identity'
```

The test wants a vocabulary rejection and gets the authority refusal instead,
because `method_exec.run_step_out_of_process` checks
`if not dsn or not allocation_id or not operation_id` at `:1651-1653` **before**
it parses the action. Same guard, earlier in the same call chain. The string
`refused: execution needs explicit authority and identity` is also raised at
`method_exec.py:1134` for `run_member_out_of_process`, which is the path the
10th ID takes.

That 10th ID is `test_aled_campaign.py::test_campaign_constructs_and_retains_acquired`,
which the prior report put in cause AA, "Use path refuses where acquired bytes
were expected". **It is this guard, not a use-path regression.** The chain is
fully traceable in the source and I verified each link: the test calls
`trajectory.run_use(repertoire, 0, "I", [USE_TASK], {...}, policy=first_eligible)`
at `test:269-271` with **no `dsn=` and no `allocation_id=`**; `run_use` at
`trajectory.py:2102` only refuses `dsn` without `allocation_id`, and passes
`dsn=None` down; `trajectory.py:2127` therefore sets `execution = None`; and
`_run_member` at `:1844` calls
`method_exec.run_member_out_of_process(member, task, ..., dsn=None, ...)`, which
raises at `:1132-1134`. `MethodExecutionError` is caught at `:2137` and turned
into `_member_refused_record`, whose `executed_source` is the literal
`"refused"` at `trajectory.py:2060`. That is the string the assertion sees.
**The sibling test in the same file that passes,
`test_use_is_metered...` at `:221-231`, does not exercise this at all, because
it monkeypatches `T._run_member` with its own `metered_member` at `:221` and
so never reaches the guard.** The passing neighbour is not evidence the code
works.

**One cause, 10 IDs, two files, one stale migration.** The remedy is to pass an
authority at the call sites, or to delete the archived files if the staged
experiment is finished. It is not to weaken the guard, which is doing its job.

## Causes D and the 7 that are excluded, because the exclusion is narrower than it looks

The brief excludes 7 pg_dump IDs. **Two more of the 65 fail with the pg_dump
mismatch, and they are counted here.** They are not in the 7 because their
summary line reads `AssertionError: Regex pattern did not match` rather than
`SystemExit: pg_dump failed`, which is why they are easy to miss:

```
tests/_heavy_archived/test_r01_recovery.py:162
>       with pytest.raises(SystemExit, match="barrier"):
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'barrier'
E         Actual message: 'pg_dump failed: pg_dump: error: aborting because of server version mismatch\npg_dump: detail: server version: 18.6 (Debian 18.6-1.pgdg13+2); pg_dump version: 16.15 (Ubuntu 16.15-1.pgdg24.04+2)'
```

`test_r03_flow.py:227` is the same, expecting `continuations moved` and getting
the mismatch text. The version numbers in that message, server 18.6 against
`pg_dump` 16.15, are the whole diagnosis: the `postgres:18` service is newer
than the client's `pg_dump`, so every backup aborts before it writes, and the
`match=` assertion is the first place that abort surfaces in a form pytest can
report as a failed test rather than an errored fixture.

**So the real pg_dump blast radius in this run is 9, not 7.** The
`.github/actions/postgres-client` repair installs major-18 `pg_dump` in both
jobs (`ci.yml:162-165`), and it will fix these 2 as well as the 7, because the
mechanism is identical. **They are listed in this report because the brief
scoped them out of it, not because the repair will not reach them.** A reader
who trusts the 7 would re-open two reds after the client lands.

## Cause C, 3 IDs, and the one place this report refuses to guess

`ci-failure-causes-37261826154.md` already did cause K for these 3 IDs, and its
narrowing stands: the child raises inside `preexec_fn`, CPython discards the
child's exception, and the parent sees only
`SubprocessError: Exception occurred in preexec_fn.`. This pass does not
improve on that and does not pretend to. What it adds is the count check and
the environment verdict.

The three: `test_n36_containment.py:70` twice and
`test_n36_refusal_strand.py:257` once, all with the identical
`refused_reason='child-setup-failed: SubprocessError: Exception occurred in
preexec_fn.'`. All three declare `read_deny`, all three are reached only because
`probe_landlock().available` is true on this kernel, and the prior report's
five candidate sites all sit below `launcher_local.py:256-258`:

```python
    probe = probe_landlock()
    if not probe.available:
        raise OSError(_errno.ENOSYS, probe.reason)
```

**Verdict `environment`, and specifically a kernel-capability question CI can
answer.** One of these five sites failed, and which one is not recoverable from
this log or any log, because the child exception is destroyed before the parent
sees it. A run that captured child-side stderr would separate them in a single
run. I did not run it.

## Cause E, 2 IDs, and it is a defect in the script, not the test

Both fail inside the child process the test spawned, at the same line:

```
>       assert demo.returncode == 0, demo.stdout + demo.stderr
E       AssertionError: Traceback (most recent call last):
E         File ".../experiments/run_live_abc.py", line 417, in <module>
E           raise SystemExit(main())
E         File ".../experiments/run_live_abc.py", line 263, in main
E           adapter, dev_ids, panel_ids, transfer_ids = _demo_double()
E                                                         ~~~~~~~~~~~~~~
E         File ".../experiments/run_live_abc.py", line 135, in _demo_double
E           from experiments.doubles import ScriptedDouble
E         ModuleNotFoundError: No module named 'experiments'
```

`test_r01_experiment.py:221` and `test_r02_explearn.py:246`, byte-identical
inner tracebacks, log lines 763-811 and 1035-1083. Both tests run
`sys.executable experiments/run_live_abc.py` with `cwd=EXPERIMENTS.parent`, and
`run_live_abc.py:40-41` puts `"src"` and `"experiments"` on `sys.path` as
**relative strings**. That works when the process's cwd is the repository root
and fails when it is not, because `python experiments/run_live_abc.py` puts
`experiments/` itself on `sys.path[0]`, making the top-level package name
`run_live_abc` and never `experiments`. **`experiments/` has no `__init__.py`**
(verified absent), so it is a namespace package reachable only from the parent
directory. `tests/test_s09_sibling_imports.py:87-88` shows the working form,
`sys.path.insert(0, ".")` then `from experiments import run_live_abc`, and that
test is not in the heavy job. The two relative `sys.path` insertions at
`run_live_abc.py:40-41` are the defect; the tests are calling a documented
entry point the way its own docstring shows.

## Cause F, 4 IDs, and it is a committed DSN to a developer's machine

`test_rec_restore.py:20-22` hardcodes a default, and the fixture at `:27` uses it:

```python
FENCE_DSN = os.environ.get(
    "SETTLEMENT_RESTORE_DSN",
    "postgresql://ubuntu@/settlement_restore_probe?host=/var/run/postgresql")
```

All 4 fail at setup, in the `fence` fixture, before any test body:

```
E           psycopg.OperationalError: connection is bad: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: No such file or directory
```

The CI job runs a `postgres:18` **service container**, which listens on
`127.0.0.1:5432` and not on a local unix socket. The env var that would fix it
is not set in the job's `env:` block (`ci.yml:143-147` sets `PYTHONPATH`,
`S09ISO_TOKEN`, `SETTLEMENT_TEST_DSN` and `S09ISO_ADMIN_DSN` only), so the
default is taken and the default cannot work. **Same `user=ubuntu` and same
`/var/run/postgresql` layout as cause A's hardcoded path, in a different file.**
Three committed references to one developer's WSL PostgreSQL now, which is worth
recording as a pattern rather than as three unrelated typos.

## Causes G, H, I, J, K, L, M: one each, and each is a distinct defect

| ID | What the traceback says | Root read from |
|---|---|---|
| G, `test_broker_dbos.py` x2 | `DBOS Error 3: DBOSConfig sets database_url, which was removed in DBOS 3.0` | `broker.py:1422-1424` builds `database_url` **and** `system_database_url`; the pinned `dbos>=1.0` resolved to a 3.x that rejects the first. Blamed at `dbos/_dbos_config.py:172` inside `_reject_removed_database_url_keys` |
| H, `test_rpr13_endtoend.py:466` | `assert False` with `['score-without-oracle-evidence B-gr-eva-00', ...]` | `checker.py:166-168` flags a record whose `oracle_queries` is empty while `result.verified` is true. The B-arm record is built by `_refused_record` (`run.py:489-493`), which writes `"oracle_queries": []` with `"best_measure": initial` and `"verified": False` — and `_refused_record` is what an unbound B arm is supposed to produce (`run.py:512-516`). **The checker penalises a correct refusal.** The test itself asserts the refusal is correct at `:1674`, so the test and the checker disagree about the same artifact |
| I, `test_s3_experiment.py:237` | `assert insufficient_resources == invalid_input` | `store.reserve` at `store.py:872-875` checks `SELECT 1 FROM operations WHERE id = 's3d-other'` first and raises `SettlementError`, which carries `INVALID_INPUT`. The test names `'s3d-other'`, an operation that does not exist, so the unknown-operation guard fires before the capacity check at `_take_reservation`. **The test cannot reach the budget it is testing without registering the operation first** |
| J, `test_eng_invb_dispatch.py:194` | `AttributeError: 'GatewayError' object has no attribute 'text'` | `infer` returns `ModelResponse | GatewayError` (`gateway_http.py:935`). `_pre_dispatch_route_error` refuses at `:924-932` because the `responses` API publishes no `provider`, so a frozen route cannot be attested. The test builds a frozen stub route and a `responses` endpoint, so it is refused before the socket. **The refusal is a deliberate, documented decision at `:887-923` and the test predates it** |
| K, `test_s09_n201_claim_ledger.py:257` | `sent is False`, `refused_reason='child-setup-failed: OSError: parked before spawn'` | The test monkeypatches `subprocess.Popen` with a stub that always raises `OSError("parked before spawn")` at `:239-242`, then asserts `holder["out"].sent is True` at `:257`. The launcher correctly reports the spawn failure (`launcher_local.py:888-933`). **The test's own stub guarantees the assertion cannot hold.** Its docstring says the window is checked by parking inside `Popen`, and the claim assertion at `:251` is the one that matters; `:257` was written before `dispatch` began reporting a failed spawn as `sent=False` |
| L, `test_adv_isolation.py:86` | `At index 2 diff: 'PYTHONPATH' != 'SETTLEMENT_OPERATION'` | `scrub_env` at `exec_profile.py:133-136` returns `PATH`, `LANG` and `PYTHONPATH`, and the launcher passes it at `launcher_local.py:884`. `PYTHONPATH` was added by `8e06980a`; the assertion is from `fefa2a1b`. **The secret the test is really guarding against is not leaked**, and the next line `:87` still checks that |
| M, `test_rpr07_resume.py:302` | `psycopg.errors.UndefinedObject: role "ubuntu" does not exist` | `CREATE DATABASE "settlement_cb01exec_fresh" OWNER ubuntu` at `:302` against the service container, which authenticates as `postgres` (`POSTGRES_HOST_AUTH_METHOD: trust`, `ci.yml:133-135`). **The role name is committed, not derived**, so it is the same class as cause A and F |

## The unrooted list, 1 ID

The prior report's format requires that a cause not determinable from the log
be named as such rather than assigned. One qualifies.

**`test_eacq_repair.py::test_validation_child_work_comes_from_the_model`**
(log lines 247-290, blamed `test_eacq_repair.py:222`)

```
>       assert gw.calls, "validation child work never reached the model"
E       AssertionError: validation child work never reached the model
E       assert []
E        +  where [] = <test_eacq_repair.ModelChildAdapter object at 0x7fccd5597770>.calls
```

**What the log does establish.** The assertion at `:278`,
`assert validation["execution_admitted"]`, **passed**, and
`execution_admitted` is computed at `experience.py:1089` from `admitted`,
which `experience.py:1072` sets only when `_candidate_admitted(outcome)` is
true, which at `:1027-1030` requires `outcome["plan_id"] is not None`. So the
episode produced a plan and was admitted. Yet the gateway double recorded no
call at all.

**What it does not, and why I stopped.** `validate_on_development` reaches the
model only through
`experiments/coord02/entry.dispatch_admitted_child`, and that function has
**four** early returns before `gateway.infer` is reached: `settled is None` and
`ensured.code not in (APPLIED, ALREADY_APPLIED)` at `:402-404`, a second
`settled is None` at `:414-415`, and `_require_live_spend` at `:393`. Any of
the four produces exactly the observed `calls == []` with an admitted episode
and no exception. **The traceback records the assertion, not which of the four
fired, and nothing in the artifact distinguishes them.** Naming one would be a
guess with a traceback stapled to it, which is the failure this format exists
to prevent.

The one narrowing the source supports, stated as narrowing and not as cause:
`_require_live_spend` at `entry.py:393` calls `_is_live_gateway`, which at
`:228` returns False for any adapter carrying a `label`. `ModelChildAdapter`
sets `label = "ACQ-MODEL-CHILD"` (`test_eacq_repair.py:87`), so that
particular gate does **not** fire. **That eliminates one of the four and leaves
three, which is why this stays unrooted.** A run that logged the operation row
or the `settled` text would settle it in one run.

## The 20 files, and where each of the 65 sits

| File | IDs | Cause |
|---|---|---|
| `test_run_bounded.py` | 27 | A |
| `test_s09_bound_use_proof.py` | 9 | B |
| `test_s09iso_stale_sweep.py` | 7 | A |
| `test_rec_restore.py` | 4 | F |
| `test_n36_containment.py` | 2 | C |
| `test_broker_dbos.py` | 2 | G |
| `test_r01_experiment.py` | 2 | E |
| `test_adv_isolation.py` | 1 | L |
| `test_aled_campaign.py` | 1 | B |
| `test_eacq_repair.py` | 1 | **unrooted** |
| `test_ec02ad_verif.py` | 1 | A |
| `test_eng_invb_dispatch.py` | 1 | J |
| `test_n36_refusal_strand.py` | 1 | C |
| `test_r01_recovery.py` | 1 | D |
| `test_r02_explearn.py` | 1 | E |
| `test_r03_flow.py` | 1 | D |
| `test_rpr07_resume.py` | 1 | M |
| `test_rpr13_endtoend.py` | 1 | H |
| `test_s09_n201_claim_ledger.py` | 1 | K |
| `test_s3_experiment.py` | 1 | I |
| **Total** | **65** | |

This matches `heavy-failures.txt` exactly, and the per-file rows in
`reports/evidence/heavy-nondump-causes.csv` reproduce this table one ID at a
time.

## Three corrections to the brief, and to the prior report

Stated plainly because each would have produced a wrong census.

1. **The 6 unparseable lines do not exist.** All 72 parse, and all 72 have
   bodies. The one that looks unmatched is a section header pytest wrote with
   2 underscores instead of 3, at log line 711. Handling it as an artifact
   rather than a gap is the difference between 1 unrooted and 6.
2. **The 2 `test_rpr07_resume`-adjacent pg_dump failures are inside the 65.**
   `test_r01_recovery::test_checkpoint_detects_concurrent_write` and
   `test_r03_flow::test_checkpoint_refuses_continuation_commit_mid_backup` fail
   with the version mismatch as their *actual message* behind a `match=`
   assertion. The brief's 7-by-`SystemExit`-message rule misses them, and the
   real pg_dump blast radius is 9.
3. **The prior report's cause I, 8 IDs, and cause H, 8 IDs, were one guard.**
   The `-q` suppression the prior report diagnosed has been repaired, and with
   bodies the split collapses: 9 IDs in `test_s09_bound_use_proof.py` plus 1 in
   `test_aled_campaign.py`, all reaching the same
   `refused: execution needs explicit authority and identity` check. The prior
   report's `test_aled_campaign.py:272` attribution to a use-path regression is
   wrong for the reason traced in cause B.

## What a repair lane should do, in order

1. **Cause A, 35 IDs, 53.8% of the subset.** Derive the interpreter from
   `sys.executable` at `test_run_bounded.py:45` and
   `test_s09iso_stale_sweep.py:51`, and replace the committed literal at
   `test_ec02ad_verif.py:1165`. This is the largest single win and it unblocks
   27 tests whose actual subject, the exit-status remapping table, is
   currently untested.
2. **Causes D, 2 IDs, already in flight.** The `postgres-client` action fixes
   them with the 7, because the mechanism is the same abort.
3. **Cause B, 10 IDs.** Pass an authority at the call sites, or delete the
   archived files. Do not weaken `s09_bound_use_proof.py:283-285` or
   `method_exec.py:1651-1653`; both are correct and the callers are stale.
4. **Cause F and cause M, 5 IDs, and cause A's third file.** Three committed
   references to one developer's WSL layout. Set the DSNs in `ci.yml`, and
   derive the role from the env rather than committing `ubuntu`.
5. **Cause E, 2 IDs.** Make `run_live_abc.py:40-41` resolve `src` and
   `experiments` from `WORKTREE` at `:38`, which the file already computes, so
   the entry point works from any cwd.
6. **Cause H, 1 ID.** Decide whether an honest refusal may carry
   `best_measure`. That is a semantic call about the checker, so it is left to
   the owner rather than specified here.
7. **Cause C, 3 IDs.** Needs a kernel-level answer CI can give, and child-side
   stderr to identify which of the five sites failed.

## Not verified

Stated so a repair lane does not read these as measured.

- **NOT RUN:** any of the 65. No test suite, no WSL, no local PostgreSQL, as
  instructed. Every cause here is read from a traceback body plus a source
  line, never from a reproduction.
- **The 65 are all traceback-rooted or bounded.** Nothing in this report is
  read from a truncated summary line, which is the improvement on the prior
  pass's 65 `inferred` rows.
- **Cause C's failing syscall is not identifiable from any log**, because
  CPython discards the child exception before the parent sees it. Five
  candidate sites, one of which fired, unnamed.
- **The 1 unrooted ID narrows from four candidate returns to three** by
  excluding `_require_live_spend` on a source reading. That is a narrowing, not
  a cause, and it is labelled as such above.
- **The pg_dump client repair is credited as already landed**, not as
  predicted to work. I did not run it. The 2 IDs in cause D are grouped with it
  because the traceback names the identical abort, not because a repaired run
  has been observed.
