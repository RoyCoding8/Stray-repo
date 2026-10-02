# Red audit of the affected test set

Lane `z2-redaudit`, against `e442a02`. I repaired no production code and
weakened no assertion. Every number below was produced by running the
product in WSL Ubuntu against real PostgreSQL, `PYTHONPATH=src`, into
`/home/ubuntu/.venvs/as9`. No live model call, no network, no Jev.

**Scope.** The affected set is `git diff --name-only f03db5b..HEAD --
'tests/*.py'`, 51 files. They ran in eleven sequential batches, one pytest
process at a time, each with `-rs`. Counts from different batches are
never summed. No file under `reports/evidence/` was read for edit or
written; `git diff --name-only e442a02 HEAD -- reports/evidence/` is
empty.

## Verdict

**No. The three known deliberate reds are not the only reds.** The
affected set carries **16 reds across 4 classes**: 4 DELIBERATE (the
reviewer's own failing-first evidence, one of which has since been
repaired and is now green), 0 OWNED, 3 PRE-EXISTING-AND-UNDERSTOOD, and
**9 UNEXPLAINED** — reds no document on this tree records, in four
distinct files.

The headline correction to the earlier draft is that
`tests/test_inv_b4_constant_score.py` is **green**. The delivery lane
repaired it, so the deliberate-red list is one shorter than the reviewer
recorded.

The nine unexplained reds matter more than the count. Three of them are
the same shape: a repair landed correctly and the tests that depended on
the thing it removed were never migrated. One of them is worse than a
stale assertion, because it is a gate that cannot see the defect it
exists to catch.

The sixteen reconcile per batch, and the batches are never summed:
A2 gives 4 (all DELIBERATE), D gives 2 (both PRE-EXISTING), H1 gives 6
(5 UNEXPLAINED, 1 PRE-EXISTING), I gives 4 (all UNEXPLAINED).

## Batch summary lines, reported separately, never summed

```
A2  tests/test_inv_b4_constant_score.py
    tests/test_final_accept_findings.py
    tests/test_r_final_freeze_and_chain.py
    4 failed, 31 passed in 945.95s (0:15:45)

B   tests/test_inv_a_chain.py tests/test_inv_a_counterexamples.py
    tests/test_inv_a_reviewer_source.py
    29 passed in 63.05s (0:01:03)

C   tests/test_inv_x2_subscript_freeze.py
    tests/test_inv_p2_frozen_write_binding_forms.py
    tests/test_inv_c4_inheritable_construction.py
    74 passed in 93.46s (0:01:33)

D   tests/test_inv_d1_documents.py tests/test_inv_b14_retention.py
    tests/test_final_provenance.py tests/test_staging_fidelity_crlf.py
    tests/test_inv_c3_fixture_repair.py
    2 failed, 79 passed in 45.72s

E   tests/test_inv_a4b_lost_update.py tests/test_inv_a6_caller_migration.py
    tests/test_inv_a7_probe_durable.py tests/test_inv_a8_improve_authority.py
    tests/test_inv_a_action_meaning.py tests/test_inv_a_no_dsn_execution.py
    tests/test_inv_a_preflight_durable.py
    80 passed in 114.29s (0:01:54)

F   tests/test_inv_b10_cap_sheet.py tests/test_inv_b11_budget_probe.py
    tests/test_inv_b12_swe_construction.py tests/test_inv_b13b_replseed.py
    tests/test_inv_b17_budget_fit.py tests/test_inv_b18_view_contract.py
    tests/test_inv_b1_swe_view.py tests/test_inv_b2_graph_child.py
    tests/test_inv_b3_repertoire.py tests/test_inv_b8_panel_power.py
    tests/test_inv_b9_graph_driver.py
    151 passed in 138.86s (0:02:18)

G   tests/test_inv_c2_freeze.py tests/test_inv_c6_suspend_resume.py
    tests/test_inv_c7_two_domain.py tests/test_inv_p1_mission_hold_lock.py
    tests/test_inv_p2_correction_budget_race.py
    tests/test_inv_p2_mission_release_lock.py tests/test_inv_x1_call_arity.py
    42 passed in 153.42s (0:02:33)

H1  tests/test_s09_e4_channel.py tests/test_s09_e4_remediation.py
    tests/test_s09_run_isolation.py tests/test_s09_swe_binding.py
    tests/test_s09_swe_executor_capability.py
    6 failed, 62 passed in 116.25s (0:01:56)

H2  tests/test_s09_swe_experiment.py
    7 of 57 completed, no verdict — stopped by the coordinator
    (2 prior attempts killed at 5400 s and 7000 s)

I   tests/test_c14_live_already_spent_source.py
    tests/test_construction_response_envelope.py
    tests/test_invc1_method_envelope.py tests/test_m1_shared_executor.py
    tests/test_mission_entry.py tests/test_s89a1_contract.py
    4 failed, 57 passed in 70.30s (0:01:10)
```

B reproduces the reviewer's R1 baseline (`29 passed`) and C reproduces
R2 (`74 passed`) exactly, on a different base. That is the check that
this environment measures what the reviewer measured.

Batch H originally ran as one process over six files and was **killed at
the 2400 s timeout** with no summary line, at 57% complete. It was split
into H1 and H2 on the evidence, because a batch that can be killed at 57%
is not a batch that reports. H1 is the same file set minus the slow
out-of-process lineage file, and it completed in under two minutes.

H2 is `tests/test_s09_swe_experiment.py` alone: 55 of its 57 tests carry
`@pytest.mark.swe_matrix`, and each runs a full out-of-process SWE matrix
where a supported lineage spends sixty `code.try` turns per episode in a
child interpreter. The file's own comment says so. It is reported
separately for that reason, and its first two attempts were killed by
their own timeouts (5400 s, then 7000 s) rather than by a defect. The
marker is deliberately not registered in `pyproject.toml`, and the file
says that omission is left visible rather than suppressed.

The eleven batches cover the 50 affected files exactly once each, with no
overlap and nothing outside the set. The 51st,
`tests/test_s09_swe_experiment.py`, is H2 and has **no verdict**: seven of
its 57 tests completed, none red, and the batch was stopped on the
coordinator's instruction rather than by a defect. Its 50 unrun tests are
an open gap in this audit, not a green result.

## The red table

Sixteen rows. `file::test — classification — owner or reason`.

### DELIBERATE (4) — asserts a defect is present, owner named

| file::test | owner or reason |
|---|---|
| `test_final_accept_findings.py::test_the_b4_freeze_artifact_its_own_gate_reads_is_committed` | FA-02. Asserts `b4-crossover-mean.json` is committed. It is not, and it should not be fabricated: the one `control_competence(40)` sweep was cancelled for resource reasons. Recorded not repaired. |
| `test_final_accept_findings.py::test_the_archived_e4_generator_cannot_run_against_the_deleted_menu` | FA-04. Asserts `channel.REACHABLE_EVIDENCE` exists. Lane C4 deleted it with the fixed menu, which is the correct repair. The archived generator at `reports/evidence/inv_r1_e4/make_evidence.py:238` still reads the name. |
| `test_r_final_freeze_and_chain.py::test_the_guard_refuses_a_frozen_write_made_through_a_dict_method` | RF-01, reviewer r-final. `_attempts_frozen_write` returns `False` for `view.update({"grant": ...})`, which writes the key anyway. |
| `test_r_final_freeze_and_chain.py::test_a_revision_writing_a_frozen_field_is_not_admitted_as_eligible` | RF-01, reviewer r-final. `admit_revision_under_freeze` returns `eligibility: eligible`, `informs_decision: True` for the smuggled write. Confirmed live in A2. |

**One recorded finding is not a red.**
`test_r_final_freeze_and_chain.py::test_the_policy_states_effect_id_names_no_operation`
(RF-02) **passes**. The defect it names is a *missing join*, so a detector
asserting the join's absence is green until someone adds it. It is named
here so its absence from the red list is deliberate rather than an
omission.

### OWNED (0)

None. The two `test_r_final_freeze_and_chain.py` reds a prior draft
attributed to lanes X3 and X4 are not owned by a running lane in this
tree; they are the reviewer's recorded findings, still open and still
correct as written. RF-02 passes, so X4 has nothing to turn red.

### PRE-EXISTING-AND-UNDERSTOOD (3)

| file::test | commit and why it is correct |
|---|---|
| `test_inv_b14_retention.py::test_the_parent_cap_sheet_is_untouched_by_this_lane` | Predicted in `reports/FINAL-ACCEPTANCE.md:323-343`. The test pins `b-live-cap.md` to its blob at `794520f`; closing FA-01 corrected the panel-count sentence, so the pin necessarily fails. I confirmed the cause: the content diff is confined to lines 48-53 and is a pure line-shift from the inserted paragraph. |
| `test_inv_b14_retention.py::test_this_lane_owns_only_its_own_paths` | Same acceptance-pass section, second consequence. `reports/evidence/invr1b17-budgetfit/` appears in the evidence diff because lane B17 merged after B14 wrote the pin. The test's own docstring says it reads HEAD and the index together, so a later lane's committed evidence is indistinguishable from B14 having written it. |
| `test_s09_e4_remediation.py::test_a_gap_inside_its_own_noise_is_not_reported_as_measurable` | The E4 estimator's noise guard: `delta 0.009722` does not clear `paired_se 0.009543`, so the fixture's stated premise (a gap inside its own noise) no longer holds on the current cohort. Sensitive to the substrate lane C4 changed. |

### UNEXPLAINED (9) — the finding

| file::test | root cause |
|---|---|
| `test_c14_live_already_spent_source.py::test_the_dead_name_is_no_longer_a_reader_anywhere` | **A gate that cannot see its own defect.** `:104` skips any path with `".worktrees" in path.parts`, intending to exclude sibling lane worktrees. `ROOT` is the tree the file lives in, so inside `.worktrees/<lane>/` that predicate is true for **every** file. The scan returns `[]` and asserts `hits == ["scripts/s09_pilot.py:1101"]` — comparing empty to empty. The reader is still at `scripts/s09_pilot.py:1101`; the gate simply cannot see it from a lane worktree. |
| `test_m1_shared_executor.py::test_same_program_same_step_action_in_both_profiles` | `1e0dd44` (A2, "Close the dsn-is-None execution hole in method_exec") made `dsn`, `allocation_id` and `operation_id` mandatory. This test calls `run_policy_step(record, view, {})` with none of them, so it raises `MethodExecutionError` at `method_exec.py:1413` instead of comparing two profiles. |
| `test_m1_shared_executor.py::test_shared_assessment_arm_feeds_settled_model_result_to_next_step` | Same repair, reached indirectly. `_shared_assessment_arm` receives a `dsn` and an `allocation_id` and does not forward them, so the `request_model` action is refused before staging and `model_calls` reads `0` where the test asserts `1`. |
| `test_m1_shared_executor.py::test_production_revision_assessment_uses_shared_dispatcher` | Same omission in `_construct_policy_revision`. `spend` reads `0` where the test asserts `16`. |
| `test_s09_e4_remediation.py::test_a_substrate_with_a_real_effect_is_reported_as_measurable` | `7c7b335` (C4) deleted `_STRATEGY_EVIDENCE` from `improve_channel.py` along with `REACHABLE_EVIDENCE`. FA-04 records the loss of `REACHABLE_EVIDENCE`; nothing records this one. The fixture at `:142` still copies it, so it raises `AttributeError`. |
| `test_s09_e4_remediation.py::test_the_old_estimator_would_have_missed_the_planted_effect` | Same fixture, same `AttributeError`. |
| `test_s09_e4_remediation.py::test_a_non_empty_evidence_set_is_what_makes_the_admission_say_it_informed` | N-26, recorded but not repaired. `classify_revision` returns `changes-an-unauthorised-decision` for a revision the test expects to be `eligible`. |
| `test_s09_run_isolation.py::test_disposable_name_carries_the_caller_token` | Asserts `count(*) FROM schema_migrations == 18`; the tree carries **20**. `e4d4c1c` (C1) added 0019 and `b0363c7` (C6) added 0020, and both are in the affected set. Understood, but no document records it, and a literal schema version is a pin on the wrong thing. |
| `test_s09_run_isolation.py::test_disposable_db_is_dropped_even_when_the_body_raises` | Same cause, same commit pair. |

Four files carry an unexplained red: `test_c14_live_already_spent_source.py`
(1), `test_m1_shared_executor.py` (3), `test_s09_e4_remediation.py` (3),
and `test_s09_run_isolation.py` (2).

Three distinct root causes, and all three are the same shape at the
ownership boundary:

1. **A repair landed and the dependent tests were not migrated.** `1e0dd44`
   and `7c7b335` are both correct repairs. The tests that read the removed
   surface were not in either commit's file list, so nothing in the batch
   was red when they landed and nothing recorded the debt afterwards.
2. **A migration landed and a version literal did not move.** `e4d4c1c` and
   `b0363c7` each added a migration; the literal `18` in a file owned by
   neither lane stayed.
3. **An anti-copy guard is unscoped.** The `.worktrees` exclusion is the
   only one of the three that makes a gate *weaker* rather than a test
   *stale*, and it is the one that will survive every future fix.

## The skip and xfail sweep

Swept every `tests/**/*.py` tracked file for `pytest.mark.skip`,
`pytest.mark.xfail`, `pytest.mark.skipif`, `pytest.skip(`,
`pytest.xfail(`, `pytest.importorskip`, `@unittest.skip` and
`unittest.expectedFailure`.

**60 occurrences in live tests, 10 in `tests/_heavy_archived/`.** No
`@unittest.skip` and no `unittest.expectedFailure` anywhere. **Zero skip
or xfail machinery in any of the 51 affected-set files**, so nothing in
the changed surface is skipped: a green file in that set is a file that
ran.

### What each cluster hides, as `file:line — what it hides`

- `test_launcher_local_bounds.py` (13), `test_launcher_local_preexec.py`
  (13), `test_child_limits_platform.py` (3) — **nothing on this host.**
  Every `skipif` is keyed to `POSIX` or `WINDOWS` and each carries the
  opposite branch in the same file. A WSL run skips the Windows refusal
  branch and executes the POSIX enforcement branch.
- `test_s09c1_continuity.py:382` — **nothing; it is a change detector.**
  `test_settled_receipt_stays_attributable_on_empty_text` is
  `strict=True`, its reason names the commit that made the store refuse
  an empty-text success receipt, and a store admitting them again turns
  the suite red. A strict xfail cannot pass quietly. This is the only
  `xfail` in the tree.
- `conftest.py:20` — **the hazard N-415, and it is closed here.**
  Skips when `SETTLEMENT_TEST_DSN` is unset. `conftest_isolation.py:653-681`
  (`_apply_conftest_stores`) exists to close it, setting both DSN
  variables to a per-run disposable store so those files run rather than
  skip. Its docstring says it plainly: "A skip is not a failure, so 101
  files reported without running." On this tree, with the plugin active,
  zero of those 101 skipped.
- `test_s09_merged_tip_regression.py:460`, `test_s09_durable_state.py:31`
  — **nothing; deliberately loud.** Both are "LOUD SKIP" markers, and the
  durable-state one is `allow_module_level`. Neither hid anything in these
  runs.
- `test_ad01_e2_contrast.py` (5), `test_w1_e1_campaign_r2.py` (5),
  `test_w1_e1_claim_rederivation.py` (2) — **a campaign-not-run state.**
  Artifact-conditional skips. A real gap, but a declared one. None of
  these files is in the affected set.
- **`test_inv_b1_contracts.py:24` — the broadest guard in the tree, and
  the one worth naming.** A module-level `skipif` on `INV_B1_DSN` makes a
  whole file of B1 contracts invisible unless that variable is set. Not in
  the affected set, so it did not run here. This is a standing hazard for
  whoever next reports a suite total.
- `test_w1_live_preflight.py` (2), `test_ad01_experience_axis.py` (3),
  `test_r02_authority.py` (3), `test_ag01_demo.py:14`,
  `test_ag01_experiment.py:32`, `test_coord02_workload.py`,
  `test_s09o_export.py`, `test_state_allocations.py`, `test_team_live.py`
  — **a missing live DSN or a live gateway.** All declared, none in the
  affected set.
- `tests/_heavy_archived/` (10 occurrences across 7 files) — **not
  collected by default.** `pyproject.toml` sets `norecursedirs`. The one
  archived `xfail` (`test_team_solver.py:311`) is also `strict=True`, for
  an uncommitted `acquire2.py` whose executed source is unrecoverable.

**A skip is not a pass.** The broadest guard in the tree is
`test_inv_b1_contracts.py:24`, and the loudest is
`conftest.py:20`; both are honest, and the second is now closed by
`conftest_isolation.py`. Neither appears in the affected set, so no
finding in this audit rests on a skip.

## The failing-first record, and what became of it

Every unexplained red above is pinned as a detector in
`tests/test_inv_z2_red_audit.py`, which this lane owns. At `e442a02` it read:

```
4 failed, 2 passed in 4.23s
FAILED test_no_shared_executor_test_still_calls_without_execution_authority
FAILED test_the_production_callers_forward_the_authority_the_executor_now_demands
FAILED test_no_test_pins_the_migration_count_as_a_literal
FAILED test_the_e4_remediation_fixture_does_not_hold_a_deleted_reference
```

The two that passed were staleness guards. Each names the exact commit and
line, so a later repair that makes it unnecessary says so rather than
leaving a detector nobody can interpret.

**Revision (lane `z2-retarget`, against `2c33320`).** This file was never
merged, so none of the above was visible to the tree until now. At the
current tip the guard file reads `5 failed, 1 passed`, and **five of the six
guards are red because their subjects were repaired**, not because a defect
regressed. A guard of the form "this condition no longer holds" has to go
red the moment the condition stops holding. That is the tripwire working,
and the answer is to re-aim it, not to delete it and not to leave it red.

| guard | at `2c33320` | determination |
|---|---|---|
| `test_no_shared_executor_test_still_calls_without_execution_authority` | **passes** | Stale, and stale only about one file. See the open finding below. |
| `test_the_production_callers_forward_the_authority_the_executor_now_demands` | fails | Stale. The authority is still forwarded, through a splat. |
| `test_no_test_pins_the_migration_count_as_a_literal` | fails | **The subject is repaired and the predicate is wrong.** |
| `test_the_e4_remediation_fixture_does_not_hold_a_deleted_reference` | fails | Stale. It is matching prose. |
| `test_the_dead_name_gate_is_not_vacuous_inside_a_lane_worktree` | fails | Stale, and **location-dependent**: it asserts `.worktrees` is in the tree's own path, which is true from `.worktrees/z2-redaudit` and false from `.claude/worktrees/`. |
| `test_the_exclusion_names_a_descendant_worktree_not_a_path_component` | fails | The same location dependence. |

The brief this revision answers predicted four reds and two passes. The
measured state is five reds and one pass. The two the brief did not name are
the Z2-01 pair. They are not red because a repair was missed. They are red
because they assert a defect that **has** been repaired, and they only
reproduce from a checkout under `.worktrees`. The brief also predicted the
`test_m1_shared_executor` guard as failing. It passes.

### What was repaired after `e442a02`, and by which lane

Each repair is named from its own commit, not inferred.

- **`c883d7d` (MIG-MIGRATE)** migrated `tests/test_m1_shared_executor.py`,
  `tests/test_s09_e4_remediation.py` and `tests/test_s09_run_isolation.py` —
  all three files this audit named. It added `expected_migrations()` and
  replaced both `== 18` literals with it.
- **`84c826c` (C14-FIX)** replaced the `".worktrees" in path.parts`
  exclusion with `tests/worktree_checkouts.py`, which resolves the canonical
  root structurally and asks git for each checkout's tracked and untracked
  paths.
- **`89c3559` (SIB-FIX)** and **`d41234d` (SIB2-FIX)** migrated four tests
  asserting the removed two-member menu and two naming it by label. Neither
  file is in this audit's red table.
- **`8d3a5af` (DOC-APPLY)**, **`54efd8d` (X6B-SCAN)**, **`2dd176e`
  (DECOY-FIX)**, **`e8a9fb1` (TOKEN-GRAMMAR)** and **`b62b070` (GIVEAWAY)**
  touch no subject of this audit.

### The nine unexplained reds, one by one, at `2c33320`

Six are cleared. Three are not, and one of the three is a finding this lane
did not expect.

| red at `e442a02` | state at `2c33320` | evidence |
|---|---|---|
| `test_c14_...::test_the_dead_name_is_no_longer_a_reader_anywhere` | **cleared** | `tests/test_c14_live_already_spent_source.py` runs **12 passed** from this worktree. `scripts/s09_pilot.py:1101` is still the one reader and the census still returns exactly `['scripts/s09_pilot.py:1101']`, so the gate is not vacuous. |
| the three `test_m1_shared_executor.py` reds | **cleared** | `tests/test_m1_shared_executor.py` runs **21 passed**. All three call sites now carry authority. |
| the two `test_s09_run_isolation.py` migration-count reds | **cleared** | No `schema_migrations` comparison anywhere in the test tree is against an integer literal. Both sites call `expected_migrations()`, which reads `sorted(Path(iso.MIGRATIONS).glob("*.sql"))` — the same expression `settlement.db.apply_migrations` runs at line 88. |
| the two `test_s09_e4_remediation.py` `_STRATEGY_EVIDENCE` reds | **cleared** | The fixture loads nothing named `_STRATEGY_EVIDENCE`. The one remaining mention sits inside the `_planted_effect` docstring at line 138, naming the symbol to explain what replaced it (`construction_from_evidence`, at `improve_channel.py:879`). |

**Still open. This is the finding.** The authority mandate from `1e0dd44`
was migrated in the one file the original guard watched and left in place in
three others. Nine tests now fail on the refusal at `method_exec.py:1412`,
which is unconditional and fires before a byte is staged:

```
tests/test_s09step_arm.py::test_policy_state_survives_a_fresh_interpreter
tests/test_s09step_arm.py::test_the_cpu_bound_kills_a_spinning_policy_without_a_wall_timeout
tests/test_s09step_arm.py::test_a_bounded_policy_completes_under_a_one_second_cpu_budget
tests/test_s09step_arm.py::test_the_output_bound_is_the_exact_cap_and_not_a_soft_hint
tests/test_s09step_arm.py::test_the_receipt_does_not_claim_os_containment
tests/test_s09step_arm.py::test_stdout_is_the_channel_so_a_printing_policy_is_refused
tests/test_s09c3_policy_pilot.py::test_incumbent_step_does_real_method_work_and_arms_share_input_task
tests/test_s09c_policy_boundary.py::test_real_child_timeout_is_a_refusal
tests/test_s09c_policy_boundary.py::test_fresh_process_rehydrates_source_digest_and_receipt
```

Two of the nine are not call sites `ast` reports. They are policy steps
written into a `subprocess` probe's source string
(`test_s09step_arm.py:457`, `test_s09c_policy_boundary.py:93`), which a
`Call`-node scan sees only as a `Constant`. A guard reading `Call` nodes
counts seven of nine and would be *trusted* for the two it missed, so the
re-aimed guard scans embedded scripts too and reports all nine.

The condition the original guard names is true. It was asked about one file
and answered about that file. It went green the moment `c883d7d` migrated
`test_m1_shared_executor.py` and said nothing about the three files beside
it. **A guard scoped to the file that was repaired stops being evidence the
moment that file is repaired.**

### Item 3: the guard whose subject was repaired and stayed red

The brief asked for this one to be thought about hardest, on the reasoning
that a repaired subject should turn its guard green. It did not, and the
reason is that the repair was complete while the guard was wrong.

`c883d7d` removed both `== 18` literals and put `expected_migrations()` in
their place. Nothing about the migration count is pinned any more. The
guard's predicate was *"any comparison whose comparator is an integer
literal"*, which collects eleven ordinary assertions and no migration count:

```
line  61  len(found) == 1
line 196  verdict.operations_scanned == 0
line 197  verdict.receipts_scanned == 0
...      11 hits in total, none of them a schema version
```

Counts of operations scanned, receipts scanned, rows found. The guard was
red for a reason that was never true, and would have stayed red after any
number of correct repairs.

Re-aimed, it asks whether a comparison *about migrations* is against an
integer, across the whole test tree rather than one file. That reads zero
hits today, which is the finding holding rather than the guard being weak.
The plant that proves it is in the non-vacuity table below.

## Non-vacuity proof

Every guard kept here was planted, confirmed red, reverted, and confirmed
green. A guard that cannot fail is worse than no guard, because it is
reported as coverage.

**The table below states the intended result for each plant. Only the rows
marked measured are finished; the rest are the claim the proof is for, and
the run that establishes them is `tests/test_inv_z2_red_audit.py` run under
the plant in the `plant` column.** A row is only promoted to "measured"
once it has actually been observed, because a table of unrun assertions
reading as a table of results is the same failure this audit is about.

| guard | what was planted | red? | green after revert? |
|---|---|---|---|
| `test_the_reader_census_is_not_vacuous_inside_a_lane_worktree` | `tracked_paths` returns nothing, so the census finds no reader — the vacuous shape Z2-01 named | **yes, measured** (42.46s red / 31.28s green) | **yes, measured** |
| `test_the_census_scans_the_repository_rather_than_the_directory_it_lives_in` | `tracked_paths` drops `scripts/s09_pilot.py`, so the reader is unreachable from the tracked set | **yes, measured** (2 failed in 27.78s, both Z2-01 guards) | **yes, measured** (2 passed in 23.71s) |
| `test_the_execution_authority_reaches_the_executor_through_whichever_helper_forwards_it` | `_step_authority` drops `operation_id` from the dict it returns | **yes, measured** (1 failed in 3.76s) | **yes, measured** |
| " | `_use_policy_action` rebuilds the dict at the call site with `dsn` only | **yes, measured** (1 failed in 3.41s) | **yes, measured** (1 passed in 1.98s) |
| `test_no_test_pins_the_migration_count_as_a_literal` | `== expected_migrations()` becomes `== 18` | **yes, measured** (1 failed in 3.65s) | **yes, measured** (1 passed in 4.42s) |
| `test_the_e4_remediation_fixture_loads_no_private_a_repair_deleted` | the fixture loads `module._STRATEGY_EVIDENCE` | **yes, measured** (1 failed in 2.56s) | **yes, measured** (1 passed in 2.12s) |
| " | `improve_channel` defines `_STRATEGY_EVIDENCE` again (the staleness check) | **yes, measured** (1 failed in 9.34s) | **yes, measured** |
| `test_no_test_calls_the_executor_without_execution_authority` | already red; its nine sites are the live condition | **yes, measured** (fails at baseline) | n/a, the condition is live |

**What the Z2-01 plants could not reproduce from here, and why that
matters.** `sibling_checkouts` returns **0** from this checkout, so the
phantom-sibling half of the finding cannot be replayed without a sibling on
this mount. The two Z2-01 plants therefore work through `tracked_paths`,
which is the set the census actually reads from here. A plant that cannot
fire from the checkout proving the guard is worth as little as a guard that
cannot fail, and the original Z2-01 guards are themselves an instance of the
problem: they assert `.worktrees` is in the tree's own path, which is true
under `.worktrees/` and false under `.claude/worktrees/`. **They were
location-dependent, so a red from them was never evidence about this tree
and a green from them never would have been either.**

The first trial, measured: `tracked_paths` returning nothing turns
`test_the_reader_census_is_not_vacuous_inside_a_lane_worktree` **red in
42.46s**, and restoring it turns the guard **green in 31.28s**.

**One trial first reported a green guard and was wrong.** The
`_step_authority` plant came back `1 passed`, which would have meant the
guard was vacuous. It was not: the harness's `replace()` needle was written
with `\n` while the file on disk is CRLF, so the plant silently applied
nothing and the guard was asked about an unmodified tree. Every file in
`tests/` is CRLF (80 of 80 in the sample taken), so a `\n` needle against
these files matches nothing and a plant that "passes" proves only that the
needle did not fire. The harness now reads with CRLF normalised, writes CRLF
back, and **asserts the anchor actually changed** before running anything.
Re-run with a working plant, the guard is red in 3.76s with
`_step_authority returns ['allocation_id', 'dsn']`, naming the dropped key.

That is the same shape as the finding this section started with. A green
result from a mechanism that did not run is not coverage, and a plant that
cannot fire is worth exactly as little as a guard that cannot fail.

**The final baseline, after every plant was reverted.** Each guard run alone,
one pytest at a time, in the order the table lists them:

```
test_the_reader_census_is_not_vacuous_inside_a_lane_worktree   1 passed  41.84s
test_the_census_scans_the_repository_...                        1 passed   4.24s
test_the_execution_authority_reaches_the_executor_...          1 passed   4.48s
test_no_test_calls_the_executor_without_execution_authority    1 FAILED   7.97s
test_no_test_pins_the_migration_count_as_a_literal              1 passed   8.80s
test_the_e4_remediation_fixture_loads_no_private_...            1 passed   8.20s
```

Five green, one red, and the red is the live finding rather than a defect in
a guard. Every revert restored the tree exactly; `git status` after the run
shows only this report modified.

## What this revision changed, and what it did not

Re-aimed, never deleted. All six findings keep a guard, and each now asserts
the invariant positively instead of asserting the defect's absence. The one
guard that was genuinely pointing at a live condition was extended in scope
until it covered the condition again, and is left red on purpose.

No production code was modified. No assertion anywhere in the tree was
weakened. `git diff --name-only -- reports/evidence/` is empty.

## Per-file verdicts from this revision

Three of the affected-set files this audit named as carrying unexplained reds
were re-run individually. These are per-file results and are never summed.

- `tests/test_c14_live_already_spent_source.py` — **12 passed**.
- `tests/test_m1_shared_executor.py` — **21 passed**.
- `tests/test_s09step_arm.py`, `tests/test_s09c3_policy_pilot.py`,
  `tests/test_s09c_policy_boundary.py`, as one process — **9 failed, 22 passed**,
  and all nine failures are the authority refusal.
- `tests/test_s09_e4_remediation.py` and `tests/test_s09_run_isolation.py`
  were not re-run here. Their subjects are verified structurally (no loaded
  deleted name; no migration count against a literal), which is the weaker of
  the two kinds of evidence and is labelled as such.

## Process and hygiene

One pytest process at a time, always. No Monitor armed, no subagent
spawned. The stalled `z1-redaudit` lane left an orphan pytest process
running the identical batch H from its own worktree against the same
PostgreSQL; I identified it by `cwd` and reclaimed it rather than
competing with it, which is what had been starving this lane. One H2
attempt outlived its `timeout` wrapper and was reclaimed the same way.

`git diff --name-only e442a02 HEAD -- reports/evidence/` is empty. No
production code was modified. The only files this lane changes are
`reports/workstreams/z2-red-audit.md` and
`tests/test_inv_z2_red_audit.py`.

## Final live process count

**0.** No pytest process of this lane's remains. Verified by `ps` after
the H2 stop, filtered on this worktree's path.

## What this audit did not finish

`tests/test_s09_swe_experiment.py` (57 tests, 55 of them
`@pytest.mark.swe_matrix`) has no verdict. Seven completed with no red;
the remaining 50 are unmeasured. Three attempts were stopped by their own
timeouts, the last by the coordinator on a CPU/thermal budget, and each
one is a real out-of-process SWE matrix rather than a stuck process. **A
batch that cannot finish inside an hour on this host is a finding about
the host, and it is reported here as a gap rather than as a pass.**
