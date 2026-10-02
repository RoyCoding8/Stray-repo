# Investigation 01 review, state, resources, evidence (lane R-state)

Scope is state, resources and evidence on tip `5ff0f1e`. Owned file is this note only. No other file was touched. Expectations below were derived from `docs/design/INVESTIGATION-01.md` and `reports/workstreams/inv-brief-evidence.md` before any lane verdict was read. Every count was recomputed from committed bytes in this session. Nothing is quoted from a lane total as evidence.

## Expectations

The design requires one resource path with post-effect reads, measured counters, and caller-supplied totals never accepted as proof. Construction and use consume admitted shares of the same study authority. Reporting derives from operation identities and measured counters. Unknown exposure stays visible and reserved or refused.

The design requires prefix-enforced replay. A matching task ID is insufficient. Dependencies, artifact, model and environment versions, action arguments and prior observations must match. A simulated branch that fails those conditions stops as unsupported. It never borrows an unrelated outcome, never charges it as live, and never scores unknown as failure or zero.

The brief-evidence survey sets the baseline to beat. It reports 11 C4 pairs not 12 with two zero byte stubs, zero use phase records, no raw model text separate from accepted source, no receipt plus input linkage, and no frozen per-episode configuration. Any closure sentence must resolve to a committed evidence identity or an explicit limitation.

## Method

 Probe rerun.

- `python3 reviews/probes/inv_a_baseline_gaps.py` exits 0 with 17 pass and 0 fail on this tip.

 Independent recompute scripts (throwaway, under `/tmp/opencode`, not committed).

- C3 use corpus parse over `evidence-ad01/c3-trajectories-merged/use-*.json`.
- C4 trace parse over `evidence-ad01/c4-live/*.json` plus per-operation accounting blocks.
- C2 acquisition parse over `evidence-live/c2-acquisition8.json` and `evidence-live/c2-acquisition8-repair.json`.
- Digest chain check with sha256 over repertoire `method_source` against use `executed_source`.
- Secret grep over tracked files. Evidence history check with `git log` on evidence paths.

 Gate reruns on disposable databases, all dropped afterwards.

- `tests/test_inv_b2_loop.py` plus `tests/test_inv_b4_trajectory.py`. 12 passed on `inv_rstate_b2`.
- `tests/test_inv_c_qualification.py`. 9 passed on `inv_rstate_c` and `inv_rstate_c2`.
- `tests/test_inv_b1_contracts.py` plus `tests/test_inv_b3_coord02_contracts.py`. 19 passed on `inv_rstate_b1` and `inv_rstate_b3`.
- Worktree sources were forced first with `PYTHONPATH` because the shared virtualenv otherwise resolves `settlement` to the outer checkout.

## Findings

INV-R-T01. Lane A gate accepted. The probe exits 0 with 17 pass and 0 fail. C4 holds 11 JSON plus 11 log with 9 readable and stubs `trace-w0-R-live11.json` and `trace-w0-R-live13.json`. All readable traces are world 0 with retained 0 and use phase records 0. Six of nine carry null aggregate tokens. C3 holds 72 use records. C2 selection is `none` with repair calls at 4 of 4 and lineage reasons differing.

INV-R-T02. INV-E-02 correction accepted. The tip commit rewrites the AD-06 row to 72 of 72 checker clean with retained byte execution 45 of 72. My parse confirms 72 records, 45 executing the requested acquired member (36 software plus 9 graph), and 27 on incumbent. The 27 split into 18 requesting incumbent from the start on I-arm graph tasks and 9 requesting the acquired graph member then falling back with an allocation refused reason. All 72 verdicts read `preserved`. The sha256 digest chain from repertoire `method_source` to use `executed_source` matches on all 9 retained records in `use-w0-R.json`. Byte identity therefore holds for 45 of 72 exactly as the corrected row states.

INV-R-T03. C4 operation total accepted with one definitional split carried forward. Accounting union model calls sum to 40 across readable traces. Top level `model_calls` fields sum to 37. The gap of 3 is exactly `resume-w0-R.json` with accounting total 5 against top level 2. Both numbers live in that file. Per-trace accounting totals match the lane A C4 ledger on every trace.
- `trace-w0-I` 6. `trace-w0-R` 3. `resume-w0-R` 5. `live7` 3. `live8` 7. `live9` 3. `live10` 7. `live11` 0 stub. `live13` 0 stub. `live14` 3. `live15` 3.
- Settled aggregates total 9129 as 1867 plus 2060 plus 5202. Sandbox operations total 5. Learner calls total 27 and construction calls total 13 by operation id shape.

INV-R-T04. C2 ledger accepted. The init export carries `calls_used` 2 and the repair export carries `calls_used` 4, both with selection `none`. Lineage 1 fails stopped with acquisition probe only and lineage 2 fails policy invalid with plan carries only action plus shape plus children. Both repairs report `repair_parsed_ok` false with `repair_kept_usable` false. The G7 defect stands as written. Both lineages received the lineage 1 probe text as repair feedback.

INV-R-T05. Single remaining envelope accepted. `src/settlement/loop.py` binds one allocation per study root and reads remaining from `store.allocation_free`, which is durable post-effect state rather than a caller dict. `sequence_construction_allowance` returns remaining minus reserve minus measured diagnostic spend. `experiments/ad01/trajectory.py` routes both hand rolled grants and the post-diagnostic re-sequence through that function, and zero budget probes refuse through `admit_probe` without touching study lineage. The sequenced allowance check `sequence_construction_allowance(6, 4) == 1` is exercised by the green B2, B4 and C gates. Cross-database behavior matches the design rule. Same store reuse returns `ALREADY_APPLIED` with zero new gateway calls on resume. The second store run takes its own equal-sized grant and reproduces equal `cost_union` dicts, which is separately authorized work rather than silent renewal of the first authority.

INV-R-T06. Post-effect reads accepted. `read_measured_costs` derives measured and unknown costs from settled receipts only. Unknown receipt identities stay listed and are never zeroed. `run_boundary` admits through `ensure_operation` before effects, then reads receipts and journals measured plus unknown costs into the transition. The envelope admission test from post-effect reads passed on the disposable database.

INV-R-T07. Replay boundaries accepted. `check_replay_prefix` in `experiments/doubles.py` enforces packet digest, target and instrument, version fields, exact dependency order, code-carrying inputs and prefix-available observations. Hidden future, version mismatch, reordered dependents and new code bytes each return `unsupported` with empty results. Malformed probes return `refused` with empty results. The supported path returns recorded results verbatim with unknown costs preserved. The six-probe gate plus the stale packet version refusal passed on the disposable database. A stopped branch therefore cannot borrow an unrelated outcome or charge it as live.

INV-R-T08. Raw evidence untouched accepted. `git log` from `84d2094` to this tip shows zero commits touching `evidence-ad01` or `evidence-live`. No commit since the lane A merge touches the lane A ledgers, the lane A note, or the baseline probe. The correction history touches reports only.

INV-R-T09. No secrets accepted. The pattern grep over tracked files returns prose matches only. No endpoint address, bearer value, private key block or grant document is committed. Configuration examples carry setting names with empty values.

INV-R-T10. Durable accounting of unselected failures accepted. The `c2live7` run log ends `EXIT=1` on `ConstructionBudgetExhausted` with consumed versus reserved spend unknown, and the lane A and D notes label it unknown rather than filling a number. The `live11` log carries an assertion traceback inside `controls.diagnostic_resolves`, recorded as an implementation failure rather than infrastructure loss. The `live13` pair is zero bytes with no surviving cause, recorded as unclassified. Each disposition matches the committed bytes.

INV-R-T11. Lane D token floor needs a one-line correction. Lane D lists per-trace settled per-operation tokens of 1884, 1841, 1867, 4529, 2060 and 5202. Those components are correct and match my parse exactly. Their sum is 17383, not the 18383 stated as the study total and repeated in the historical settled token floor. The floor is overstated by 1000 units. Witness queries total 20 and sandbox operations total 5 were recomputed and match. Learner 27 plus construction 13 matches by operation id shape.

## Rulings

- Single remaining envelope across stages, repair and databases. Holds.
- Post-effect reads only. Holds.
- Replay boundaries stopping unsupported branches instead of borrowing outcomes. Holds.
- Raw evidence untouched. Holds.
- No secrets committed. Holds.

## Verification boundaries

The 1329 passed plus 1 xfailed suite baseline was not rerun here. The checker clean verdict at 72 of 72 was counted by verdict field, not re-executed against task witnesses. Doubled gate runs prove doubled behavior only. Live inference and containment remain unvalidated by these gates. No Postgres object created in this review survives. All five disposable databases were dropped.

## Verdict

Accept with findings. Eleven findings stand above. Ten accept claims outright. INV-R-T11 requires one correction owned by the coordinator. Change the lane D study total and the historical settled token floor from 18383 to 17383, or show the missing 1000 units with a file reference. No other rework is required by this lane.
