# EC02 M2 qualification battery

Branch `wt/ecr2-m2`, base tip `59608c4` (learn+evid merged). DB `ec02test_m2`
only; doubled gateway only (`FakeGatewayAdapter`). Never touches
`ec02test_live`. Battery: `tests/test_coord02_m2_qualification.py` (12 tests,
green in ~22s). Production delta in this commit: one-line F-policy quote fix
(see EC-01 countercheck row).

## Per-EC path + countercheck table

| EC | Production path exercised | Countercheck (would expose a stand-in) |
|---|---|---|
| EC-01 causation | `entry.arm_policy_entry` S/F bytes executed as real subprocesses; S→`single`, F→`decompose` on multi-file task | S twice deterministically equal; F quote bug produced `SyntaxError` exit 1 instead of silently passing — the battery executes bytes, never compares strings |
| EC-02 actual bytes | `entry.arm_decision("A", …)` twice through broker `MODEL_INFERENCE` against scripted `FakeGatewayAdapter` texts; distinct texts → distinct submitted child node ids | non-JSON gateway text falls back to the visible default `w1` plan (recorded, not silent success); reused broker operation identity is refused, forcing unique `run_id` per decision |
| EC-03 admission ordering | `team.propose_team_plan`: empty children refused, no plans/subs in `team_state`; accepted plan precedes any submission | refusal returns `INVALID_INPUT`/raises before any child node exists; submissions stay empty after admission |
| EC-04 binding/eligibility | `controller.check_bindings`: renamed-compatible binds; missing digest/ABI mismatch declines; `stage_gate`→publish then `revoke_binding_eligibility`→quarantine blocks reuse | quarantine of a nonexistent version raises (`unknown capability version`); the decline path needs a genuinely published version |
| EC-05 diagnostic sensitivity | `policy_exec.run_probe_call` with the two `oracle.DIA_PROBES["c02-t11"]` inputs → different observation bytes, no errors | both observations assert `error is None`; inactive-policy case is measured, not assumed (S post-probe proposal recorded) |
| EC-06 integration/rework | valid constructor → `success` + frozen `candidate_digest`; broken submissions → `join-failed-terminal`, no candidate, liabilities, revision ≥ 2; entry `run_cell` S → honest `failure` record with quoted failures, receipts, ceilings clean | entry fixture submits raw snapshot bytes, so its join fails openly — the battery asserts the recorded failure instead of manufacturing success |
| EC-07 continuity | `run_episode` then `resume_episode` on the same DB with a fresh config object: same sentinel, identical step receipts, `success` again; `resume_plan` skips evidenced cells, runs the rest | receipt list equality proves no redispatch; `resume_plan` pending keys land in `reconcile`, not `run` |
| EC-08 bounded failure | garbage bytes → `policy-empty`; response-file garbage → `policy-invalid`; both carry policy-party liabilities and admit zero plans; `refused_trial_record` + `require_settled_failure` reject unresolved/unknown-cost settlements | `print`-to-stdout yields `policy-empty` (stdout is not the response channel) — outcome vocabulary distinguishes transport classes |
| EC-09 reconstruction | `checker.make_record` + `check_evidence`: baseline problems equal exactly the unstaged `missing-pair` set; deleting a record re-adds its `missing-pair`; digest tamper → `wrong-procedure-digest`; shared receipts → `receipt-reuse` | editing the freeze schedule trips `schedule-drift`, so the battery stages records against an unedited freeze and proves detection instead |
| EC-10 retention | `stage_gate` publish → `load_frozen_package` returns identical entry bytes; unknown version and quarantined version both raise `SettlementError` | tampered/quarantined bytes refuse at load; no source substitution path exists in the loader |
| workload pressure | all six families present in the evaluation split; held-out dia tasks (`t13/14/15`) carry two `DIA_PROBES` each; F decomposes / S stays single on the `cpl` development task | family assertion is exact (`["cpl","dia","rw","sco","sep","sng"]`), probe counts exact |
| counterbalanced schedule | `build_schedule` shift `(index+repeat)%len(ARMS)`; every `(panel,task,repeat)` sees all four arms; `select_panel_cells` preserves order without mutating the freeze | first-arm rotation checked per cell against the formula; freeze JSON byte-identical before/after selection |

## Pre-existing failure (not fixed, not caused by this commit)

`tests/test_coord02_experiment.py::test_entry_write_evidence_round_trip:531`
fails at base `59608c4` (recorded in the M2 tasking). Likely mechanism, observed
while converging EC-06 but not proven by running the 96-cell panel: the
fixture child factory (`solved_child_factory`) submits raw snapshot bytes,
which fail public checks, so entry-path cells end in `join-failed-terminal`;
whatever the checker then rejects cascades to `clean == False`. Fixing it
(e.g. fixture submitting valid bytes, or checker tolerating fixture-labeled
failures) is a lane-E decision, out of M2 scope.

## Fresh-checkout reproduction (read from `pyproject.toml`, not memory)

`pyproject.toml` sets pytest `testpaths = ["tests"]`; package layout is
`src/` (`tool.setuptools.packages.find where = ["src"]`), Python ≥ 3.12.

```sh
git clone <origin-url> Agent-Society-v2 && cd Agent-Society-v2
git checkout wt/ecr2-m2
uv sync                      # provides .venv with pytest>=8.0
createdb ec02test_m2         # Postgres reachable at /var/run/postgresql
.venv/bin/python -m pytest tests/test_coord02_m2_qualification.py -q
```

Expected: `12 passed`. The suite truncates all tables in `ec02test_m2` on
setup; it never opens `ec02test_live`. No `TEAM01_LIVE_API_KEY` is required
(doubled gateway only); evaluation/transfer panels via `main()` without
`--doubled` correctly refuse with exit 2 when no grant exists.

## Red→green log (TDD, against real seams)

1. F-policy quote bug → `SyntaxError` exit 1. Fixed production
   (`experiments/coord02/entry.py`, one line); deleted zero lines elsewhere.
2. Broker refuses reused operation identity → unique `run_id` per A decision.
3. `_dev_join_rules` carries `conjunctive`, rejected for `single` shape →
   set `accept` (mirrors production `_join_rules_for_shape`).
4. Quarantine needs a published version → publish via `stage_gate` first.
5. `print` is not the response channel → write garbage to `argv[2]`.
6. Freeze schedule edits trip `schedule-drift` → prove detection instead.
7. Entry-path S cell joins fail honestly (fixture submits snapshot bytes) →
   assert the recorded failure, not manufactured success.

Net: one production line changed (a misplaced quote), zero new shims, zero
new branches; the battery is additive in `tests/` + this report.
