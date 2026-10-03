# a59 — the archived tree's repo-root derivation

## The defect

`tests/_heavy_archived/*.py` sits two levels below the checkout root, so the
depth that was correct at `tests/*.py` is one short here. 27 derivations in 26
files read `Path(__file__).resolve().parent.parent`, which from
`tests/_heavy_archived/` resolves to `tests/`.

That directory has no `migrations/` and no `src/`. Anything feeding it to
`apply_migrations` raised `MigrationSetEmpty` at runtime; anything feeding it
to `sys.path` put the wrong tree on the path.

The idiom one level up is correct there and is untouched. One control case:
`tests/test_c15_member_parse.py:402` uses `parents[2]`, which is right, because
its `__file__` is `experiments/ad01/method_exec.py`, not the test's.

## What was changed

`parents[2]`, one derivation per file, no helper and no fallback, matching the
29 files in the same directory that already used it.

Three derivations walk up from *another module's* `__file__`
(`settlement.representation`, `experiments/ad01/method_exec`) and already
land on the root from `src/`. They are left alone and still read
`.parent.parent.parent`. That is not an offender.

One further site of the same cause: `test_ec02ad_verif.py` asserted its own
driver was tracked by a path written before the tree moved into
`tests/_heavy_archived/`. It is now named at its archived location.

## Measurement

Windows, `--collect-only`, `S09ISO_DISABLE=1`, per file, same interpreter
before and after. The pre-fix tree was materialised from git as a detached
worktree rather than by an in-place revert.

All 85 archived files:

| | before | after |
|---|---|---|
| files collecting clean | 83 | 84 |
| files erroring at collection | 2 | 1 |
| tests collected | 919 | 925 |

The single per-file change is `test_p2d_b_resweep.py`, which could not be
collected at all (`ModuleNotFoundError: doubles`, via
`sys.path.insert(tests/experiments)`) and now collects 6 and runs 2.

Runtime, 21 of the 26 changed files that run on Windows at all:

| | before | after |
|---|---|---|
| passed | 52 | 63 |
| failed | 78 | 69 |
| skipped | 28 | 32 |

Files whose pass count moved, all upward:

- `test_p2d_b_resweep.py` 0 → 2 passed
- `test_s09graph_representation.py` 20 → 23 passed, 3 → 0 failed
- `test_team_world.py` 3 → 7 passed, 4 → 0 failed
- `test_ec02ad_verif.py` 4 → 6 passed, 4 → 2 failed

No file lost a passing test.

The pre-fix failure is the defect verbatim:
`FileNotFoundError: ...\tests\experiments\team01\manifest.json`.

The 5 files that need POSIX child execution cannot run on Windows at all.
Measured anyway, since 4 of the 5 turned out not to need it:

| file | before | after |
|---|---|---|
| `test_run_bounded.py` | 23 passed / 31 failed | 27 passed / 27 failed |
| `test_invd1_dispatch.py` | 0 / 7 | 0 / 7 |
| `test_invr2_correction.py` | 0 / 4 | 0 / 4 |
| `test_invr2_diagnostic.py` | 0 / 2 | 0 / 2 |
| `test_s09ast_boundary.py` | 9 / 7 | 9 / 7 |

The four that stopped failing in `test_run_bounded.py`, by name:

- `test_the_claim_about_the_swe_file_is_pinned_to_its_own_bytes`
- `test_the_names_that_caught_it_are_real_names_in_this_repository`
- `test_the_slow_file_list_and_the_doc_agree`
- `test_the_tool_never_names_a_process_to_find_work`

No test newly fails in any file.

Over all 26 changed files the totals are 84 → 99 passed and 129 → 116
failed. The residual failures are the host, itemised below.

## What is still failing, and why it is not this fix

**116 failures remain across the 26 changed files.** They are not the path
defect. No file raises `MigrationSetEmpty`, and none raises the stale-path
assertion either. Classified by the error text at tip `ef0db1e`:

- 11 files: `psycopg.OperationalError` on socket `/var/run/postgresql`.
  There is no database on Windows; these are CI's.
- 1 file: `git clone`/checkout refused (`unable to create file
  experiments/team01/evidence-live/...`), a Windows path constraint inside a
  fresh-clone test.
- 1 file: no POSIX resource module, so the child caps cannot be installed.
  `tests/_heavy_archived/test_s09ast_boundary.py` fails 7 before and 7
  after, identically.

8 of the 21 Windows-runnable files finish with no failure:
`test_p2d_b_resweep.py` (2 passed), `test_s09graph_representation.py` (23),
`test_team_world.py` (7), `test_s09m2_construct.py` (6), `test_team_solver.py` (4),
and `test_rpr06_transfer.py`, `test_rpr08_resume.py`, `test_rpr13_endtoend.py`
(0 passed, all skipped for want of `SETTLEMENT_TEST_DSN`).

The classification above covers the 13 of those 21 that still fail. The
remaining 47 failures are in the 5 POSIX-group files, by cause:

- 3 files (`test_invd1_dispatch.py`, `test_invr2_correction.py`,
  `test_invr2_diagnostic.py`): the missing database.
- 1 file (`test_s09ast_boundary.py`, 7): the absent POSIX resource module.
- 1 file (`test_run_bounded.py`, 27): every failure is
  `FileNotFoundError [WinError 2]` from `CreateProcess`. The file spawns
  `ROOT / ".venv" / "bin" / "python"` (line 45), a POSIX venv layout that
  cannot exist on Windows. That is the host, not the root derivation; the
  four tests this fix repaired in the same file are listed above.

**The archived suite is not green.** It was not green before and these
failures are not what this fix addresses.

## A separate defect, found and not fixed here

`tests/_heavy_archived/test_s09iso_stale_sweep.py` cannot be collected:

```
ModuleNotFoundError: No module named 'tests.conftest_isolation'
```

It imports `tests.conftest_isolation` at lines 37 and 39 and inside four
subprocess drivers, while three other archived files import the same module
plainly as `conftest_isolation`. `tests/` has no `__init__.py`, so the dotted
form is unimportable from the repository root. Confirmed identical on the
commit before any change in this lane, so it predates the work and is
separate from it. Its root derivation is already `parents[2]` and correct.

It is left as a finding rather than absorbed: fixing an import contract is a
different repair from the path-depth defect, and it needs an owner.

## Checking this again

```
python reports/workstreams/a59-root-eval.py
```

Evaluates every own-`__file__` derivation in the tree and exits nonzero if
any misses the root. It reports the file count it scanned as well as the
derivation count, because an earlier version printed "0 derivations" and
exited 0 when it was moved and stopped finding the tree at all.

## Two things that will cost the next lane time

**A push cancels the run it supersedes.** `.github/workflows/ci.yml` sets
`concurrency: ci-${{ github.ref }}` with `cancel-in-progress: true`. Pushing
twice to one branch cancels the first run about 90 seconds in, before the
heavy job gets anywhere. Five runs of this lane were cancelled this way and
none produced an artifact. Push the final commit once, then leave it alone
and read the artifact when it lands.

**The heavy job needs PostgreSQL and cannot be replaced locally.** It runs
85 files one at a time and holds a 120-minute budget, so its result is CI's
alone. Everything above was measured on Windows with `S09ISO_DISABLE=1`,
which skips the conftest's advisory-lock claim and therefore measures
collection and execution but not anything database-backed.