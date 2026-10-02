# EC02 M4 frozen study (none-selection fallback panels)

Branch `wt/ecr2-m4`, base tip `e149123` (learn+evid+M2+M3 merged). DB
`ec02test_m4` only; doubled gateway only (`FakeGatewayAdapter`). Never
touches `ec02test_live` (verified 16 receipts after the run). Battery:
`tests/test_coord02_m4_frozen.py` (8 tests, green in ~248s: eval chunk
~142s, transfer chunk ~71s). Production delta: one genuine fix in
`experiments/coord02/entry.py` (L-slot trial records carry the scheduled
arm so fallback attribution cannot collide with genuine S cells) plus one
shadowing fix in `checker.py` (loop variable renamed so the panel filter
uses the argument, found via the cross-panel audit while proving order).

M3 verdict is `none`: neither candidate executable under the contract
(see `reports/EC02-M3-ACQUISITION.md`). So no authored bytes stand in
for L; all 36 L slots execute the explicitly-attributed S-fallback path
(`failures` carry `{"reason": "none-selection:S-fallback"}`), never
labeled learned success. Zero records mention `learned` or
`retained-acquired`.

## Per-claim table

| Behavior claimed | Production entry/call path | Observed run + revision | Live-vs-doubled deps | Countercheck (would expose a stand-in) |
|---|---|---|---|---|
| freeze manifest from none selection | `freeze_selection` → `freeze.write_freeze`/`verify_freeze` | 8 passed @ `wt/ecr2-m4`, `test_m4_freeze_manifest_from_none_selection` | doubled: manifest/oracle/checker digests of real files, 96+48+96 schedule from `build_schedule` | drifted-rules and truncated-schedule freezes fail `verify_freeze`; a hand-written manifest would lack the digest chain |
| full schedule executed, no silent skips | `entry.run_panel` → `run_cell` per schedule cell, `checker.check_evidence` clean | same run, `test_m4_full_schedule_executed_no_silent_skips`; harvest: total=144 eval=96 transfer=48 | doubled: real subprocess episodes on `ec02test_m4`, receipts + operations per cell, ceiling check per cell | `have == scheduled` asserted as sets; a skipped cell breaks the equality and the checker `missing-pair` fires |
| L slots run attributed S-fallback | `run_cell` `decision["kind"]=="none"` branch: `arm="S"` execution, record keeps scheduled arm + fallback marker | same run, `test_m4_l_slots_run_attributed_s_fallback`; harvest: l_slots=36 marked=36 | doubled: L branch needs no acquired package; without the fix all L records collide with S | pre-fix the test failed on production (arm "S" records); `"learned" not in blob` asserted on every record |
| resume same-DB: reconcile/skip/rerun | `SE.resume_plan` + `store.reconcile_operation` + rerun via `run_cell` | same run, `test_m4_resume_same_db` | real DB rows: pending op reconciled `APPLIED`, rerun receipts disjoint from originals, tampered digest reruns, freeze tamper detected | tampered `procedure_digest` and missing key must land in `run`, not `skip`; truncated schedule trips `hash mismatch` then `schedule-drift` |
| transfer fresh-process load + bindings | `controller.load_frozen_package` in a `sys.executable -c` child (no dev transcripts) + `check_bindings` | same run, `test_m4_transfer_fresh_process_and_bindings` | child prints sha256 of loaded bytes, matched to pinned bytes; zero `coord:m4-transfer-child%` ops leaked | digest mismatch fails; incompatible `requires` declines `unsupported` with no candidate digest and a refused trial record |
| interventions bounded and honest | target scan over retained executions (empty: no L cell ran retained bytes) | same run, `test_m4_interventions_bounded_and_honest`; executed=0, ceiling=12 | probe-unavailable / all-child-rework targets cannot activate without retained execution; S probe traffic (36 cells) explicitly excluded | targets derived from `retained_executions==[]`, not asserted zero; force-running an intervention with no target would break the derivation |
| failures carry costs | every failure record validated: settled settlement, numeric costs, receipts | same run, `test_m4_failures_carry_costs` | real `_cell_costs`/`_cell_receipts` per cell | `UNKNOWN` or missing receipts fail per-cell; unsettled costs rejected by `require_settled_failure` counter-assertions |
| panel/arm accounting exact | set-equality on all 144 (panel,arm) slots by panel | same run, `test_m4_summary_counts_by_panel_and_arm` | counts from executed records, not the schedule | any missing/duplicated slot breaks the 12-key exact dict |

## Cell accounting (harvest run, doubled, denominators exact)

All 144 executed, 0 open (open = scheduled − evidenced = ∅). Outcome is
`failure` on all 144 — genuine doubled behavior, not a defect: the
production `run_panel` path wires cells through `solved_child_factory`
(raw snapshot bytes, no solver repair), so oracle protected cases fail
while receipts, operations, costs and failure records are all real. The
fixture `dev_constructor(solved=True)` (which returns oracle-valid trees)
is intentionally NOT on this path — routing panels through it would be
the stand-in this contract forbids.

| panel | arm | executed | open | failed | solved |
|---|---|---|---|---|---|
| evaluation | S | 24 | 0 | 24 | 0 |
| evaluation | A | 24 | 0 | 24 | 0 |
| evaluation | F | 24 | 0 | 24 | 0 |
| evaluation | L (S-fallback) | 24 | 0 | 24 | 0 |
| transfer | S | 12 | 0 | 12 | 0 |
| transfer | A | 12 | 0 | 12 | 0 |
| transfer | F | 12 | 0 | 12 | 0 |
| transfer | L (S-fallback) | 12 | 0 | 12 | 0 |

Fallback attribution: 36/36 L-slot records carry
`none-selection:S-fallback`; 0/144 records mention `learned`. S cells
with probe traffic: 36/36 (probe path live; only its target — retained
execution — is absent). Wall clock: eval ~142s, transfer ~71s.

## Interventions

Executed 0 of ceiling 12. Both commissioned interventions
(`probe-unavailable`, `all-child-rework`) disposition `inactive` with
reason: no L-slot cell executed retained bytes, so neither target
activates; S-fallback probe traffic is explicitly not the L target.
No intervention was force-triggered to fill the quota.

## Fallback evidence

The none-selection freeze (`package.kind == "none"` + reason
"neither candidate executable under the contract") flows into
`run_cell`, which executes S machinery and stamps the record with the
scheduled L arm plus the fallback marker. `stage_record` copies trial
failures verbatim into staged evidence, so the marker survives to the
checker-clean record. Fresh-process transfer loads pinned S-policy bytes
(explicitly not learned) through `load_frozen_package`.

## Fresh-checkout reproduction (read from `pyproject.toml`, not memory)

`pyproject.toml` sets pytest `testpaths = ["tests"]`; package layout is
`src/` (`tool.setuptools.packages.find where = ["src"]`), Python ≥ 3.12.

```sh
git clone <origin-url> Agent-Society-v2 && cd Agent-Society-v2
git checkout wt/ecr2-m4
uv sync                      # provides .venv with pytest>=8.0
createdb ec02test_m4         # Postgres reachable at /var/run/postgresql
.venv/bin/python -m pytest tests/test_coord02_m4_frozen.py -q
```

Expected: `8 passed` (~4 min: eval ~142s + transfer ~71s). The suite
designates `ec02test_m4` disposable and truncates all tables on setup;
it never opens `ec02test_live`. No `TEAM01_LIVE_API_KEY` required
(doubled gateway only).

## Red→green log (TDD, against real seams)

1. Stand-in first: assertions written against imagined seams (guessed
   record shapes, invented schedule sizes) — red.
2. Real seam, real failure: the L-slot identity test failed on
   production code — fallback records carried arm "S", colliding with
   genuine S cells and breaking stable
   (freeze, panel, task, repeat, arm) identity. Fixed in `entry.py`:
   records carry `scheduled_arm`; execution still uses S machinery.
3. Shadowing fix in `checker.py`: `for short, panels in ...` shadowed
   the `panels` argument, so post-loop panel filtering iterated the last
   set instead of the caller's filter. Renamed to `seen`.
4. `stage_record` audit (lane's open question): resolved by reading —
   line 433 copies `trial["failures"]` verbatim and the marker is
   appended before the trial record is built, so it survives staging.
   No code change needed.
5. Green via existing machinery: `freeze_selection`,
   `run_panel`/`run_cell`, `resume_plan`, `load_frozen_package`,
   `check_evidence` — the battery is additive plus the two fixes above.

## Regressions (same worktree code)

- `tests/test_coord02_m2_qualification.py`: 12 passed.
- `tests/test_coord02_learning.py`: 19 passed.

## Pre-existing failure (not fixed, not caused by this commit)

`tests/test_coord02_experiment.py::test_entry_write_evidence_round_trip:531`
fails at base (recorded in M2/M3 tasking). Out of M4 scope.
