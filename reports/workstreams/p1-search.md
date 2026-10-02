# p1-search: independent search/repair pass 1

Base `3138408` (merged tip of the ~49-lane consolidation batch). This pass
assumes the batch is defective and looks for what no lane's own gate could
see. Two passes were planned; this is the first.

Everything below was read off the source or executed against real
PostgreSQL. Nothing was confirmed from a filename or a workstream report.

## Findings

| ID | file:line | defect | why it matters | disposition |
|---|---|---|---|---|
| P1-01 | `src/settlement/run.py:599-634` (pre-fix) | `_hold_on_mission_entry` did a read-modify-write of `investigations.in_flight` across two separate connections with no row lock, while the module that owns that column (`experiments/ad01/mission.py`, `admit_operation` and `resume_operation`) takes `FOR UPDATE` before reading. | Two barriers suspending two attempts of the same investigation both read the pre-barrier list and the second write silently drops the first barrier's `status="suspended"` and `barrier_ref`. The lost hold reads back as `held` with an empty barrier_ref, so a resume routes on a record that never says it was waiting. This is the same lost update lane A4b repaired on the other side of this batch, reintroduced by a second writer to a column that already had one owner, and the C6 docstring's claim that "the record exists if the write is refused" does not describe what a lost write does. Invalidates the C6 claim that a pending operation crosses a restart keeping its identity. | **Fixed.** Read and write moved into one transaction under `FOR UPDATE`, matching the owning module. Regression: `tests/test_inv_p1_mission_hold_lock.py::test_two_concurrent_barriers_both_leave_their_hold`, real PostgreSQL with two racing threads. Watched fail first: the first attempt read back `'held'` with `barrier_ref ''`. |
| P1-02 | `experiments/ad01/improve_channel.py:1243-1244` | `_targets_frozen` recurses into `ast.Subscript.value` but never inspects `ast.Subscript.slice`, so `view["grant"] = {...}` passes `_attempts_frozen_write` undetected. The same class of gap reaches `FROZEN_FIELDS` via any subscript key. | The freeze is a claim that revision bytes cannot write trusted authority. A revision that writes `view["used"]` or `view["execution_limits"]` is admitted as eligible. This is a live hole, not latent: `learner_revision._admit` calls `admit_revision_under_freeze` on real campaign sources. | **Recorded, not fixed.** Path ownership: another lane owns this region right now and the brief names it as in-progress. Duplicating the fix would collide. The regression that would pin it belongs with that fix. |
| P1-03 | `experiments/ad01/improve_channel.py:1211-1235` | `_attempts_frozen_write` matches only `ast.Assign` and `ast.AugAssign`. A write through `ast.AnnAssign` (`grant: int = 0`) or `ast.NamedExpr` in a comprehension is not examined. | Same claim as P1-02, second syntax path. Lower severity than P1-02 because `AnnAssign` at module scope on these names is an unusual revision shape, but it is the same authority the freeze exists to protect and the gap is in the batch's own new freeze code. | **Recorded, not fixed.** Same path ownership as P1-02. |
| P1-04 | `tests/test_inv_c2_freeze.py:236-257`, `tests/test_s09rev_boundary.py:317-347` | No test in the tree exercises a subscript write target against `_attempts_frozen_write`. The existing frozen-write tests use attribute and name targets only, so P1-02 was invisible to every gate in the batch. | A test that cannot fail is worse than no test. The freeze gate reports green while the freeze has a hole, which is the "missing policy passed as a method release" shape: the gate's green is being read as coverage of a write path it never touches. | **Recorded.** The absence is the finding; the fix belongs with P1-02. |

## Verified clean, and what that rests on

These were checked because the brief named them, and each was checked by
running or reading the thing itself rather than by trusting its label.

- **`invr1b12-swe/` is not fixture bytes relabelled live.** Its
  `store-rows.json` carries five operations, five receipts with distinct
  `response_class` values (`lost-response` on a 60s read timeout, four
  `observed-provider-failure` on http 502) and five reservations of 2700 to
  2771 units against a 65352-authorized allocation that consumed 10899.
  `campaign.json` claims `acquired_lineages: 0` and its own
  `use_rows` say `outcome: "no-acquisition"` for all four lineages. The
  artifact is consistent with its store rows and reports a null result
  honestly. It is a negative result with real provenance, which is the
  opposite of the failure mode.
- **`invr1b14-retention/` records unknown billing as unknown.**
  `invr1b14_retention.py:461-465` sets `billed: None` and `charge_units:
  None` with the reading spelled out, and `carried_in_true_exposure: ">= 5563"`.
  Null billing is not reported as a measured zero.
- **`invr1b8-panel-census/` is a real panel computation.** 14 panels carry
  `cluster_count`, `minimum_p`, `max_attainable_positive_delta` and
  `open_rows`, recomputed by a named production function
  (`w2_retention_campaign.panel_power_verdict`), with `dispatches: 0` and
  `model_calls: 0`. It is an offline census that says so.
- **`reports/evidence/invr1b17-budgetfit/` and `src/settlement/method_exec.py`
  do not exist.** No lane claimed B17 or that path anywhere in the tree
  (`grep` over `*.md` and `*.py` returns nothing). The brief's list was
  inaccurate on these two items; there is no missing artifact and no lane
  report over a directory it never wrote. Recorded so the next pass does
  not re-search for them.
- **The C2/C3 freeze gates are not weakened.** Lane C3 deleted one
  assertion (`informs_decision is True`) and replaced the hand-written STEP
  fixture with the incumbent carrying only its probed input replaced. Both
  are correct: `improve_channel.py:604-605` derives `informs_decision` from
  `selected_evidence`, which requires executing the revision, and that
  harness has no execution authority. Asserting `True` asserted a
  measurement the gate cannot make. This closes the standing N-26 finding in
  `reviews/STAGE-09-FINDINGS.md:121`.
- **Every new test file asserts literal values.** All 29 files added in the
  batch were scanned. None is skip- or xfail-gated, and none asserts only
  `is not None`. `tests/test_inv_a_reviewer_source.py` has no tests by
  design: it is the reviewer-written policy-source module that
  `test_inv_a_chain.py` and `test_inv_a_counterexamples.py` import, and both
  state that no lane's own fixture is reused there.
- **`exec_profile.package_search_path()` containment claim is true.** The
  docstring argues `src/` does not publish `experiments/ad01/worlds.py`.
  Run on this checkout, the published path contains exactly one top-level
  entry (`settlement`) and neither `experiments` nor `ad01` resolves under
  it. The claim is measured, not asserted.
- **`launcher_local` `child-failed` is a real distinction.** A nonzero exit
  now records `parse: "child-failed"` rather than reading as a program that
  ran and printed nothing, and `s09_graph_budget.py:130` acts on it.

## Gates run on the merged tip

| file | result |
|---|---|
| `tests/test_inv_p1_mission_hold_lock.py` (new) + `tests/test_inv_c6_suspend_resume.py` + `tests/test_mission_entry.py` | `11 passed in 30.62s` |
| `tests/test_inv_a8_improve_authority.py` `test_inv_a4b_lost_update.py` `test_inv_a6_caller_migration.py` `test_inv_a_no_dsn_execution.py` | `31 passed in 36.47s` |
| 9 B/C lane files (b8, b10, b11, b12, b14, b18, c2, c3, c4) | `121 passed in 133.06s` |

All with `-rs` so a skip could not read as a pass. Zero skips in every run.

## Not fixed, and why

- P1-02 and P1-03 are in `improve_channel.py`'s frozen-write region, which
  another lane owns right now. Recording rather than colliding is the
  cheaper repair here; the fix is a few lines once that lane lands.
