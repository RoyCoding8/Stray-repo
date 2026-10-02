# INV-G2: F1 refusal ripple check over owned coord02 tests

Worktree `.worktrees/inv-g2`, branch `wt/inv-g2-coord02`. Base tip `8a14a46`
verified clean (`git status` empty) before any work. No disposable `inv_g2_*`
database was needed: every owned suite carries its own `ec02test_*` DSN and
truncates its own tables per fixture, so no scratch DB was created or dropped.

## Scope

Owned files exercised on this tip, `PYTHONPATH=<worktree root>` with
`uv run --extra test pytest`: `tests/test_coord02_learning.py`,
`tests/test_coord02_m2_qualification.py`,
`tests/test_coord02_m3_acquisition.py`, `tests/test_coord02_m4_frozen.py`,
`tests/test_coord02_state.py`, `tests/test_eacq_repair.py`,
`tests/test_ec02ad_verif.py`. 114 tests collected.

## Per-file verdicts

- `test_eacq_repair.py`: 4 passed, untouched. The lone `dev_constructor`
  use pins the repair path, which never depended on unattested success.
- `test_coord02_m4_frozen.py`: 8 passed, untouched.
- `test_coord02_state.py`: 16 passed, untouched.
- `test_ec02ad_verif.py`: 28 passed, untouched. Its `solved_child_factory`
  and `dev_constructor` uses already assert non-success shapes.
- `test_coord02_m2_qualification.py`: 10 passed, 2 failed on the tip;
  migrated, now 12 passed.
- `test_coord02_learning.py`: 18 passed, 1 failed on the tip; migrated,
  now 19 passed.
- `test_coord02_m3_acquisition.py`: 26 passed, 1 failed on the tip;
  migrated, now 27 passed.

## Migrations (all contract change, no old bug)

F1 made `dev_constructor` and `solved_child_factory` return `None`, so every
unattested episode takes `submit-refused` with `no constructor artifact for
<node>` and a constructor liability. Each failure below pinned the old
unattested-success behavior and was migrated to that refusal shape, mirroring
the coordinator migration of `test_canned_seam_carries_no_admission`.

- m2 `test_m2_ec06_integration_join_and_failed_join`: the `solved=True` leg
  asserted `success` with a nonempty candidate digest; now asserts
  `submit-refused`, the `no constructor artifact` reason, and a `None`
  candidate (zero unattested success). The `solved=False` leg asserted
  `join-failed-terminal`; both constructor variants now refuse before any
  join runs, so it asserts the same refusal shape with `None` candidate and
  the surviving constructor liability. The `revision >= 2` line is deleted:
  revision counts join-loop iterations and refusal exits at child submission,
  so no revision exists on this path; demanding one would contradict the F1
  contract. The `run_cell` refusal leg already passed unmodified.
- m2 `test_m2_ec07_same_db_resume_preserves_sentinel_and_settled_ops`: first
  and resumed episodes assert `submit-refused` with reason. The test's real
  requirement, sentinel and settled-receipt equality across resume, is
  unchanged and passes, so resume idempotence holds for refused episodes.
- learning `test_selection_ordering_and_none_path`: `good` keeps
  `valid_execution is True` but `solved_count` is now `0` with empty
  `solved_tasks` and `executed == tasks`. Added a pin that every failure
  entry is `submit-refused` with the refusal reason, proving the zero comes
  from explicit refusal rather than breakage. Ordering, ranking, tie-break,
  and none-path assertions pass unmodified on `valid_execution`.
- m3 `test_selection_winner_links_lineage_exposure_and_accounting`: same
  `solved_count == 0` migration plus the failures refusal pin. Selection,
  ranking, exposure linkage, accounting, and freeze verification pass
  unmodified.

No old bug surfaced: every failure traced to the intended F1 refusal, and no
production file was touched. No new `test_inv_g2_*` file was needed.
