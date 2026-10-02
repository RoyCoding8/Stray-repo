# Long-running tests, and the tool that bounds them

A full suite run in this repository takes about four hours. A lane that
dispatches one file under a cap too low for it loses the run and learns
nothing. A lane that dispatches all 389 files at once finds out nothing for
four hours. The fastest fix to either is knowing before you start which files
are slow, which is what this file is for, and `scripts/run_bounded.py` is what
turns that knowledge into a refusal rather than a hope.

## The tool

```
scripts/run_bounded.py --timeout 280 -- .venv/bin/python -m pytest tests/test_x.py
```

The answer is one of five outcomes, and every one of them comes from the
child's own exit status or from a line the child actually wrote. It is never
"no process matches this name".

| outcome | exit code | what it means |
|---|---|---|
| `exited` | the child's own status | the child finished and reported a status |
| `timeout` | 124 | our bound was reached; the process group was killed. Not a pass |
| `refused` | 125 | we declined to start: a slow file, a held slot, a bad argument |
| `startfail` | 126 | the command could not be exec'd |
| `incomplete` | 127 | the child exited 0 but wrote no pytest summary |

A child status of 124 through 127 would collide with the four values above, so
it is shifted by 128 on the way out. A child that exits 124 surfaces as 128,
and a child that exits 127 surfaces as 131. Every other status passes through
untouched, so 9 is 9 and 130 is 130.

`--json` prints one line of the whole outcome for a lane that wants to parse
it. The default prints `run_bounded: outcome=... status=... elapsed_s=...`,
which is enough to read in a terminal.

Interrupting the runner kills the child's process group and reports `refused`,
not `timeout`. The distinction matters: nobody decided the bound was reached,
a person pressed Ctrl-C, and a lane reading the exit code should be able to
tell those apart.

The child is started with `start_new_session=True`, so it leads a process
group containing nothing but its own descendants. Every signal this tool sends
goes to that group, so a timeout can never reach another lane's work. Verified
directly: a child that spawned a grandchild has both killed, and the
grandchild's pid is gone rather than a zombie.

## Why it does not poll

Four runs in this repository were lost to one shape of mistake, and the shape
was always the same: a process that watched other work by pattern-matching
process names or log text instead of owning that work's lifetime.

Thirteen waiters ran `until ! pgrep -f ad01_r3_compare`. The waiter's own
command line carried the string it was grepping for, so every waiter matched
every other waiter and the set deadlocked. Five were still spinning twenty
minutes later. A fourth waiter declared completion on
`grep -E "passed|failed|error"`, which matches the word inside the
`plugins: hypothesis-6.168.0, timeout-2.4.0, anyio-4.15.1` header line that
pytest writes in its first second, and nearly reported nine of fifty-seven
tests as a finished run.

So the tool has no polling at all. It calls `Popen` and blocks in `wait`, which
is the kernel telling it the child is gone. The one place it looks anything up
is the concurrency slot, and there the thing it reads is a pid the holder wrote
itself, probed with signal 0. There is no search string anywhere that a second
waiter could match. `test_the_tool_never_names_a_process_to_find_work` fails
if `pgrep`, `ps`, `/proc` or `psutil` ever appear in the source.

## The completion test

A pytest run has really finished when it writes a terminal summary: a count, a
comma-separated list of more counts, and an elapsed time. The elapsed clause is
what makes it a completion test rather than a keyword search.

```python
"30 passed in 0.49s"                                        # a summary
"16 failed, 63 passed, 2 warnings in 243.92s (0:04:03)"    # a summary
"no tests ran in 0.01s"                                     # a summary

"plugins: hypothesis-6.168.0, timeout-2.4.0, anyio-4.15.1"   # not one
"tests/test_s09_study_preflight.py::"
"  test_a_database_with_no_frozen_moment_is_unknown_not_passed PASSED [ 15%]"
"collected 57 items"                                        # not one
"FAILED tests/test_x.py::test_a_thing"                      # not one
"57 passed"                                                 # not one: no elapsed time
"in 243.92s"                                                # not one: no count
```

The third line is not a contrived example. It is a real `-v` progress line out
of a real file in this repository, and 58 test functions under `tests/` have
`passed`, `failed` or `error` somewhere in their name. A `-v` run of this
suite is a log in which those three words appear in the first test that
starts. A grep for them calls that run finished, and it is a run that has just
begun.

`--expect auto` reads the command line, never the log. A command naming
`pytest` is held to the summary; a command that does not is not. A lane
wrapping pytest in its own script passes `--expect pytest` and is held to it
anyway. Reading the log to decide whether the log is a pytest log is the same
mistake one level down.

A zero exit alone is never enough. A pytest killed at second forty exits 0 or
is killed, and a run that reported nine of fifty-seven is not a pass. That case
is `incomplete`, exit 127.

## The concurrency cap

The cap is two background shells per lane, and it is enforced rather than
advised. A runner given `--slot NAME` creates the directory
`$TMPDIR/run_bounded_slots/NAME` with `os.mkdir`, which is atomic, and writes
its own pid into it. A second runner on the same slot is refused with exit 125
and told who holds it.

```bash
scripts/run_bounded.py --slot lane-a --timeout 280 -- pytest tests/test_x.py
```

Liveness is that pid, read back and probed with signal 0, so a waiter asks
"is the process that took this slot still running" rather than searching for a
name. Two waiters on one slot cannot collide because they never share a search
string. A slot whose recorded pid is no longer running is reclaimed, so a
runner killed mid-dispatch does not wedge the next one. A slot with no
recorded pid is reclaimed only once it is an hour old, which covers a crash
between the `mkdir` and the write.

The slot is released only by the pid that took it, so a runner that was refused
cannot clear a slot on its way out.

## The slow files

Established by reading the files, not by running them. Each row below was
measured either by a timed run on this host or by tokenising the file and
reading its own source, whichever the basis column says. A `read` row is an
inference from the code, and the inference is stated so a later run can
falsify it cheaply.

`run_bounded.py` holds the same list in `SLOW_FILES` and refuses any of these
under `--timeout` without `--allow-slow`, naming the reason. A test fails if
this table and that dict disagree.

| File | Basis | Cost | Why |
|---|---|---|---|
| `test_ag01_state.py` | measured | ~4 min | 71 `migrated_db` references across 20 tests; each applies every migration and truncates every table |
| `test_ec02ad_verif.py` | measured | ~3 min | 28 tests and 11 real subprocess spawns; timed at 175s inside a six-file group |
| `test_invr2_diagnostic.py` | read | 1200s of sleep | relaunches itself as a child and waits on a 300s deadline before killing the child's process group |
| `test_invr2_correction.py` | read | 600s of sleep | same shape, one 600s sleep in a gateway stub its own child runs |
| `test_s09iso_stale_sweep.py` | read | ~10 min | 61 tests, real subprocesses waited on for 30s each, and a 600s sleep written into a holder script |
| `test_r02_exec.py` | read | ~1 min | 53 tests, real subprocesses, and a 1000s sleep written into a launcher script it kills |
| `test_r03_sup.py` | read | ~1 min | 8 tests, each writing a 1000s sleep into a supervised child |
| `test_eng_invb_launchers.py` | read | ~30s | writes 120s and 30s sleeps into grandchild scripts it then kills |
| `test_launchers.py` | read | ~5s | writes 30s sleeps into launched children it then kills |
| `test_eng_invb_gateway.py` | read | ~31s | a 30s sleep in the test's own process, in a one-test file |
| `test_d02live_episode.py` | read | ~60s | 36 `migrated_db` references plus a real subprocess spawn |
| `test_s09_e3_ladder.py` | read | ~50s | 50 `migrated_db` references |
| `test_team_runtime.py` | read | ~45s | 46 `migrated_db` references |
| `test_r02_authority.py` | read | ~40s | 38 `migrated_db` references |
| `test_r02_evalbind.py` | read | ~35s | 36 `migrated_db` references |
| `test_r01_fulfill.py` | read | ~35s | 34 `migrated_db` references |
| `test_s09_swe_experiment.py` | read | seconds, not minutes | 101 test definitions, no subprocess, no sleep, no database |

### `test_s09_swe_experiment.py` is not the file that cost two lanes their runs

Two briefs, and this lane's own, described this file as 57 real-subprocess
episode tests that a 90-minute cap killed twice. Reading it says otherwise. It
imports no `subprocess`, calls no `sleep`, and opens no database. It imports
`s09_swe_world.run_episode`, which is a `while` loop over `MAX_TURNS = 307`
turns of an in-process sandbox that `exec`s generated source under a
100 000-step alarm. Measured here, a full search episode takes 0.11s, so the
file's cost is seconds.

It stays on the list, on its compute bound rather than a subprocess one. It
already carries the repository's own `swe_matrix` marker, and
`test_the_claim_about_the_swe_file_is_pinned_to_its_own_bytes` pins the
correction to that file's own bytes, so the triage cannot go quietly stale.

### How the census was taken

Every file under `tests/` was tokenised with Python's own `tokenize`, and
`time.sleep` and `asyncio.sleep` were counted twice: once over the raw text,
and once with every string literal and comment blanked out. The difference
matters, because most of this suite's biggest sleeps are not sleeps the suite
performs. `test_r02_exec.py` contains a `time.sleep(1000)`, and it is inside a
string: the test writes a launcher script with a thousand-second sleep in it,
runs it, and kills it. A text search reads that as twenty minutes of suite
time. It is not. The same goes for the 600s in `test_s09iso_stale_sweep.py`
and the 120s in `test_eng_invb_launchers.py`.

The signal that survived both passes is `migrated_db`. It appears 1508 times
across the suite, and each occurrence applies every migration and then
truncates every table in the named database. That is the dominant cost in this
suite by a wide margin, and it is why `test_ag01_state.py` costs four minutes
across only 20 tests.

One tokenizer caveat, in case anyone repeats the census. On Python 3.12 an
f-string is several tokens, `FSTRING_START` through `FSTRING_END`, and
`FSTRING_MIDDLE` is not a `STRING`. A pass that blanks only `STRING` and
`COMMENT` counts an f-string's contents as code. The first pass of this census
had that bug and reported a 120s sleep in `test_eng_invb_launchers.py` that is
inside an f-string, not in the test.

## The measured anchors

Three groups were run under this repository's own bounded group runner, and
their logs are at `.s09suite/g{1,2,3}.log`. They are the only timed evidence
in this table, and each one also demonstrates the `-q` failure in
`docs/RUNBOOK-ISOLATED-FULL-SUITE.md`: all three logs end with a `FAILED` line
and a count, and a grep for `^FAILED` against the `-q` stream would have read
zero for the first 243 seconds.

| Group | Files | Wall clock | Result |
|---|---|---|---|
| g1 | 8 | 243.92s | 16 failed, 63 passed |
| g2 | 6 | 174.90s | 10 failed, 76 passed |
| g3 | 6 | 106.10s | 7 failed, 52 passed |

Those failures are pre-existing and belong to other lanes. This table is
measuring cost, not health.

A separate single-file run of `tests/test_evidence_supersession.py` through
`run_bounded.py` took 73.7s wall for 0.43s of tests. The other 73 seconds were
38 database creations and migrations by the isolation harness, before a single
test ran. That is the single most useful number in this file: a 30-test file
can cost 73 seconds, and no amount of reading the tests would have shown it.

The same floor applies to every invocation. `tests/test_run_bounded.py` is 54
tests and takes 18s with the scanner pointed at itself, against 152s
unscoped. Before timing anything, or before running the same node repeatedly:

```bash
mkdir -p /tmp/scan && ln -sf "$PWD/tests/test_foo.py" /tmp/scan/
S09ISO_SCAN_DIR=/tmp/scan pytest tests/test_foo.py
```

The scanner creates a store per redirectable seam it finds, so pointing it at
one file creates only the store that file needs. It changes no test's
semantics: each file still gets its own per-run store, named from the run's
token, and a store for a file that is not running is simply never created.
Reserve the unscoped form for a real full-suite run, where those databases are
the point.

## What to do instead of guessing

```bash
# Cheap by default. One file, one bound, one definite answer.
scripts/run_bounded.py --slot lane-a --timeout 280 -- \
  .venv/bin/python -m pytest -q tests/test_alee_learner.py

# Expensive, and you have said so.
scripts/run_bounded.py --slot lane-a --timeout 900 --allow-slow -- \
  .venv/bin/python -m pytest -q tests/test_ag01_state.py
```

`--expect none` is for a command that is not pytest. Do not reach for it to
quiet a summary you did not get, because that is the one thing the summary
exists to catch.

## Proving these checks can fail

A test that has never gone red is not evidence, so the demonstrations above are
rerunnable:

```bash
sh tools/test_run_bounded_mutations.sh
```

It rewrites `scripts/run_bounded.py` in place six times, one mechanism per
pass, runs the test that pins that mechanism, and requires it to fail. It then
restores the original and requires the same test to pass again. Each mutation
asserts that its own edit site matched before editing, so a refactor that moves
the site reports a no-op mutation rather than a silent pass.

| Mutation | What it breaks | Caught by |
|---|---|---|
| `is_summary` becomes a keyword search | the completion test fires early | the false-completion test, the non-summary parametrisation, the `incomplete` test |
| `proc.wait(timeout=timeout_s * 1000)` | the bound does not bound | the timeout test, the group-kill test |
| `slot.acquire` returns `None` | the concurrency cap is advice | the held-slot test |
| `release` clears unconditionally | a refused runner frees a foreign slot | the foreign-slot test |
| `exit_code` maps a non-zero to 127 | a child's own status is swallowed | the status test, the remap parametrisation |
| the `status is None` guard is deleted | an unreaped child reads as a zero | the unreaped-child test |

The sixth was added because the fifth fix introduced that path. A child that
survives `SIGKILL` as an unkillable kernel thread leaves `Popen.returncode` at
`None`, `_remap(None)` returned `None`, and a shell reads `None` as `0`. It was
the one route by which this tool could report a pass it had no evidence for.

Note the direction of the last row. The mutation suite found a hole in the
fixture for the `incomplete` test, not in the tool: the fake log that test fed
in carried a header and dots, and a keyword-search completion test fails to
match a header and dots too, so the mutant passed for the wrong reason. The
fixture now carries a real `-v` progress line and a `short test summary info`
banner, and asserts that its own text matches the buggy search, so the mutant
cannot pass it again.
