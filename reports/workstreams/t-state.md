# T-STATE workstream report (ECA-02/04/05/06 + schema side of 03)

Owner: T-STATE. Branch `wt/ec02-state`, worktree `.worktrees/state`,
base `fa777d5`. Owned paths only:
`experiments/coord02/schemas_evidence.py`,
`experiments/coord02/experience.py`, `tests/test_coord02_state.py`
(new), this report. `entry.py`/`controller.py` untouched (T-EXEC /
coordinator-shared). Identity Nightjar <nightjar@authors.invalid>.
Lane DBs `ec02test_state` + `ec02test_sentinel2` only; `ec02test_live`
never touched.

## Per-claim table

| Req | Claim | Evidence (real PG + real subprocesses) | Status |
|---|---|---|---|
| ECA-02 | Campaign union recomputes exactly from durable operation rows: distinct usages summed once, shared/replayed op counted once with attribution, missing-usage op stays unknown (never zero), failed + cancelled ops preserved with settlement/refusal | `test_eca02_nonuniform_union_recomputes_exactly_from_db_rows`, `test_eca02_unknown_usage_stays_unknown_never_zero`, `test_eca04_from_store_union_marks_known_usage_totals_but_not_nullables` in `tests/test_coord02_state.py` (16/16 green). New `reconcile_campaign_union_from_store` reads `operations` + `receipts` rows, maps usage/settlement/refusal/liability via `build_operation_record`, unions by operation identity | Done, with one change request below |
| ECA-04 | Skip iff `procedure_digest == freeze.package.package_digest` with outcome present; success via `frozen_digest` match, settled failure explicitly admitted; fabricated digest-only records RUN; `freeze_selection` writes one canonical `package_digest` (sha of entry bytes, no `entry_digest`) | `test_eca04_unmodified_saved_record_skips_but_fabricated_runs`, `test_eca04_settled_failure_skips_unresolved_runs`, `test_eca04_resume_reads_canonical_package_digest_not_legacy`, `test_eca04_freeze_writes_single_canonical_package_digest` (green). Attribution gate: `resume_plan(..., reconciled_operation_ids=...)`; without the set, legacy digest+outcome rule preserved for M2/M4 fixture callers | Done |
| ECA-03 schema | `arm` / `executed_treatment` / `fallback_reason` validated on trial records and preserved through `validate_trial_record` + `from_checker_record` round-trips (entry.py writes them; T-EXEC owns that side) | `test_eca03_provenance_fields_survive_validate_round_trip`, `test_eca03_from_checker_record_preserves_provenance` (green). `S-fallback` requires its reason; only `S-fallback` carries one | Done (schema side; entry-side write is T-EXEC's) |
| ECA-05 | Stable campaign root in `acquire` (caller-supplied, replaces fresh UUID); ledger re-entry sees consumed attempts + unresolved effects; `request_call` reconcile-then-admit inside one PG-advisory-lock section, unresolved sends hold capacity, concurrent final-slot admits exactly one; `designate_db` refuses evidence→disposable relabel before any mutation on the isolated sentinel | `test_eca05_acquire_reentry_same_root_sees_consumed_attempts`, `test_eca05_unresolved_send_holds_capacity` (stranded op via real `_crash_after_send`), `test_eca05_concurrent_final_slot_admits_exactly_one` (threads, admitted+refused), `test_eca05_designate_refuses_evidence_to_disposable_relabel` on `ec02test_sentinel2` (history byte-identical after refusal) — all green | Done |
| ECA-06 | `validate_on_development` reports `parse_ok` / `profile_ok` (real `stage_gate`) / `execution_admitted` (candidate plan admitted, S-fallback excluded) / `solved_count` / `fallback_count` distinctly; `select_candidate` keeps the frozen ordering on quality given validity: valid-but-failing selectable, fallback-alone never valid, unparsable never valid | `test_eca06_valid_but_failing_candidate_is_selectable` (admitted plan + failing children → selectable, not "neither executable"), `test_eca06_fallback_alone_never_establishes_validity`, `test_eca06_unparsable_candidate_reports_parse_failure` (green) | Done |

## Regression

Green: `test_coord02_state` (16), `test_coord02_m3_acquisition` (9),
`test_coord02_learning` (19), `test_coord02_m2_qualification` (12),
`test_coord02_experiment` (31, incl. `test_entry_write_evidence_round_trip`
— the recorded base failure does NOT reproduce in this worktree),
`test_coord02_runtime` + `test_coord02_workload` + `test_coord02_ecr201_205`
(34 passed, 2 skipped), `test_coord02_ecr202` (6/7).
M4 battery: 7/8 on this branch; `test_m4_resume_same_db` errors on a
stale-DB `team_joins` foreign-key violation in the shared `ec02test_m4`
database. The same error reproduces with my changes stashed (base
`fa777d5`), so it is environmental, not caused by this lane; left for the
coordinator (owns `ec02test_m4`).

## Change requests (contract blocks — not redefined unilaterally)

1. `tests/test_coord02_ecr202.py::test_union_nonuniform_shared_replayed_counts_once`
   asserts exact usage totals (960/180/7) over a union containing an
   explicit unknown-usage op. The pinned contract ("unknown stays unknown,
   never zero") requires usage-derived totals to read UNKNOWN in that
   case; my implementation follows the contract, so those three lines now
   fail. Request: coordinator amends those lines to assert UNKNOWN (or
   refines the contract). `by_kind`, attribution, dedup and nullable
   assertions in the same test still pass; no other existing test is
   affected.
2. `resume_plan` keeps a legacy read fallback (`package.digest` when
   `package.package_digest` is absent) and a `None`-digest skip solely so
   the M2/M4 fixture callers pass unmodified. The canonical write path
   (`freeze_selection`) emits only `package_digest`. If the coordinator
   prefers a hard break, the two fixture call sites need updating (M2
   `test_m2_ec07...`, M4 digest-freeze edit) — coordinator-owned files.
3. The ECA-02 entry side (constants in `_cell_costs`, run-ID receipt
   substitutes, per-op cost copy in `write_evidence`) is T-EXEC's per the
   ownership map; this lane supplies the loader + union the entry path
   should consume. No entry.py edit was made.

## Commits (additive, pushed, Nightjar identity)

Listed in the final handoff with tip/base SHAs. No merges, no other
branches touched, no force-push.
