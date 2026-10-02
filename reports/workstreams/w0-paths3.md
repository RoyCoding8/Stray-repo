# w0-paths3: host-independent repository-relative paths

Lane: `w0-paths3`. Worktree `D:/AI/Agent-Society-v2/.worktrees/w0-paths3`, branch
`wt/w0-paths3`, base `60d64ae`. No merge, no push.

## What was broken

`str(path.relative_to(root))` renders with the host's separator. On Windows that
is a backslash, so a manifest builder emits `world-0\dev\task.json` where the
committed manifest says `world-0/dev/task.json`. The per-file digests stay
correct. The manifest that describes them is a different byte string on each
operating system, so a freeze verifies on Linux and refuses on Windows. A digest
that depends on the host is not a digest of the content.

## Reproduction

Environment first. The brief's warning is real and the venv `.pth` is only half
the problem. `sys.path[0]` is `''`, so the process cwd outranks `PYTHONPATH` and
`experiments` silently loaded from the main checkout even with the worktree on
`PYTHONPATH`:

```
D:\AI\Agent-Society-v2\.worktrees\w0-paths3\src\settlement\__init__.py   <- worktree
D:\AI\Agent-Society-v2\experiments\ad01\panel_variation.py               <- MAIN checkout
```

Running with the worktree as cwd, all six modules resolve under the worktree.
Every result below was produced that way.

`tests/test_ad01_panel_variation.py` before the fix, `3 failed, 14 passed`:

```
FAILED tests/test_ad01_panel_variation.py::test_a_reader_outscores_an_echoer_on_this_panel
FAILED tests/test_ad01_panel_variation.py::test_a_membership_reader_is_vacuous_on_a_panel_that_varies
FAILED tests/test_ad01_panel_variation.py::test_the_freeze_verifies_and_regenerates
```

```
>       assert panel.verify_freeze(panel.FROZEN_DIR) == []
E       AssertionError: assert ['manifest-content-mismatch'] == []
```

The exact difference. `manifest.sha256` still matches, which is what makes this
a content fault and not a corrupted pin:

```
manifest.json digest == 93d7440a816e8f918a4b62f2f9ce4e44ea5198299ab0b371bdb7841dcdf6c109
manifest.sha256 pins   = 93d7440a816e8f918a4b62f2f9ce4e44ea5198299ab0b371bdb7841dcdf6c109
committed[0][path] = 'world-0/dev/panel-w0-dev-gr-00.json'
rebuilt  [0][path] = 'world-0\\dev\\panel-w0-dev-gr-00.json'
verify_freeze -> ['manifest-content-mismatch']
```

The other two modules carry the same defect, currently latent. `worlds.build_freeze`
and `experience_axis.build_freeze` into a temp tree both produce 54 of 54 entries
with backslashes. They do not break a test today only because their
`verify_freeze` reads the committed manifest and never rebuilds it, the way
`panel_variation.verify_freeze` does at line 718. A host that regenerated either
freeze would write a manifest its own `verify_freeze` still accepts and no Linux
host would.

## Per-site verdict

| Site | Feeds | Verdict | Changed |
|---|---|---|---|
| `panel_variation.py:692` | `build_manifest` file entries, compared against committed `manifest.json` by `verify_freeze:718` | digest/manifest | yes |
| `experience_axis.py:749` | `build_freeze` file entries, written to `manifest.json` and `manifest.sha256` | digest/manifest | yes |
| `worlds.py:86` | `build_freeze` file entries, same | digest/manifest | yes |
| `s09_plan_claims.py:299` | `production_callers` list, interpolated into the strings `check_uncallable:360` and nothing else | string | yes, see below |
| `s09_e1_gates_probe.py:147` | `_grep_ddmin` list, written into `result.json` as `control_column.ddmin_files_under_evidence_ad01` by `main:396` | evidence artifact | yes |

Two of these were flagged to be judged, and the two judgments differ.

`s09_plan_claims.py:299` is genuinely only a message string. `production_callers`
returns a list whose sole consumer is `check_uncallable`, which interpolates
`callers[0]` into a human sentence. Nothing hashes it and nothing compares it to
committed data. It still changed, for one reason: line 187 of the same file
already resolves the same expression with `as_posix()` to build a `git show`
argument, which *is* machine-consumed. Leaving a backslash form three lines
below a forward-slash form of the identical expression in the same file is the
thing that lets this defect back in. The change is convergence, not a fix.

`s09_e1_gates_probe.py:147` was judged to be the same defect rather than a
different concern, and the evidence is that the output is written, not printed.
`control_column_state` puts the list into the probe payload at line 126, and
`main` serialises the payload to `reports/evidence/**/result.json` at line 396.
Both committed instances currently hold `[]`, so the separator does not appear
today, but the list is empty on a host with no `evidence-ad01/` and populated on
a host that has one, and the two would disagree byte for byte. An evidence file
that records different strings on different machines is the same host-dependent
digest one level up. Changed.

## What it converged on

`path.relative_to(root).as_posix()`, used directly. That is the form
`s09_exposure_ledger.py:1144` and `s09_plan_claims.py:187` already use, so this
adds no new convention.

No helper was added. A shared `_rel()` would wrap a one-method `Path` call and
become a third place to look for a rule that `as_posix()` already states. No
normalisation shim was added either, so nothing downstream silently rewrites a
separator; the value is correct at the moment it is constructed.

Five lines changed across five files. Nothing was deleted, because there was no
dead branch to remove: the defect was one wrong call shape repeated, not a
duplicated authority.

## Regression

`tests/test_posix_manifest_paths_panel.py`, 8 tests. Each asserts a literal
expected path string, so every one fails if a builder returns the host-native
form. None imports a constant and restates it.

Red, with all five source edits stashed and committed data untouched, `8 failed`:

```
E  AssertionError: assert 'world-0\\dev...ev-gr-00.json' == 'world-0/dev/...ev-gr-00.json'
E  AssertionError: assert {'freeze_id':...dget': 8, ...} == {'budget': 8,...anel-v1', ...}
E  AssertionError: assert ['manifest-content-mismatch'] == []
E  AssertionError: assert ['world-0\\de...02.json', ...] == ['world-0/dev...02.json', ...]
E  AssertionError: assert ['experiments...s09_pilot.py'] == ['experiments...s09_pilot.py']
E  AssertionError: assert ['evidence-ad...lds\\plan.md'] == ['evidence-ad...rlds/plan.md']
```

Green after, `8 passed in 55.82s`.

The two `verify_freeze` assertions would still pass if every function returned
`undefined`, so each sits beside a literal first-path assertion on the same
call.

## Test counts, per file

| File | Before | After |
|---|---|---|
| `tests/test_ad01_panel_variation.py` | 3 failed, 14 passed | 2 failed, 15 passed |
| `tests/test_s09_merged_tip_regression.py` + `tests/test_s09_frozen_at.py` | 2 failed, 37 passed | 2 failed, 37 passed |
| `tests/test_m0_plan_claims.py` | 2 failed, 19 passed | 2 failed, 19 passed |
| `tests/test_posix_manifest_paths_panel.py` (new) | 8 failed | 8 passed |

Only `test_the_freeze_verifies_and_regenerates` changed state. It moved from
failing to passing.

I did not measure a whole-suite total. The suite ran past 25 minutes twice on
this host, and a number I stopped waiting for is not a number. The four files
above are the ones this change can reach: the three manifest builders, the two
judged string sites, and the regressions guarding them.

## What still fails, and why

Not this lane, and not this defect. Each was measured with my source edits
stashed, so the comparison is against the same base commit.

`test_a_reader_outscores_an_echoer_on_this_panel` and
`test_a_membership_reader_is_vacuous_on_a_panel_that_varies` in
`tests/test_ad01_panel_variation.py` fail with
`ValueError: preexec_fn is not supported on Windows platforms`, raised from
`src/settlement/launcher_local.py:746` and `src/settlement/exec_profile.py:160`.
CPython refuses `preexec_fn` on Windows. Both files are in `src/settlement/`,
outside this lane's owned scope.

`test_intersection_is_discovered_and_stable` and `test_db_skip_is_visible_not_silent`
in `tests/test_s09_merged_tip_regression.py` need `SETTLEMENT_TEST_DSN` and
`SETTLEMENT_TEST_TRUNCATE_DSN`, which the brief requires unset.

`test_every_citation_still_holds_its_line` and
`test_a_committed_path_change_invalidates_the_table` in
`tests/test_m0_plan_claims.py` fail on line drift in the M0 citation table, for
example `experiments/ad01/live_construct.py:615 does not hold
construct_live_policy; it is now at line 808`. Symbols moved and the recorded
line numbers did not. Nothing to do with separators, and the table is owned by
another lane.

## Freeze verification on this host

Measured after the fix, on this Windows host:

```
panel  FROZEN_DIR      -> []
worlds FROZEN_DIR      -> []
```

`panel_variation.AD01_FROZEN_DIR` reports `['wrong-freeze-id',
'manifest-content-mismatch']` and that is correct, not a leftover. It points at
`experiments/ad01/worlds`, which holds the `ad01` freeze, while this module's
`FREEZE_ID` is `ad01-panel-v1`. `tests/test_ad01_panel_variation.py:480`
already asserts the two directories are distinct. No test calls
`verify_freeze(AD01_FROZEN_DIR)`.

The stronger form of the same fact: regenerating each committed freeze into a
temp tree and re-serialising it reproduces the committed `manifest.json` byte
for byte, on Windows.

```
worlds           regenerated manifest == committed bytes: True
experience_axis  regenerated manifest == committed bytes: True
```

So the fix did not re-pin anything to make a test pass. A Windows host now
produces the same bytes a Linux host produced when these files were committed,
which is the condition that was missing.

`git status --porcelain` over `experiments/` shows only the five source files
this lane edited. No committed manifest, pin, or evidence file was modified.

## Incident during this lane

While writing the regression I called `worlds.build_freeze(FROZEN_DIR)`, which
is a writer, on the committed directory. It rewrote
`experiments/ad01/worlds/manifest.json` and `manifest.sha256` with
backslash-separated paths. `git status` showed both as modified, I restored both
with `git checkout --`, and every result above was measured after that restore.
The regression now builds only into a temp tree.

## Unresolved

`experiments/representation/splits.py:319` has the identical
`str(target.relative_to(root))` manifest shape and is not in this lane's scope.
`experiments/representation/acquire/contexts.py:74` does too.
`scripts/checkpoint.py:135,146` and `scripts/restore.py:275` do, in tar
arcnames. The first two are the same digest defect in a sibling freeze and
should be a follow-up lane. I did not touch them.
