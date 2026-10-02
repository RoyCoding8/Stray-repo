> Historical batch report. Its commits do not resolve in the current
> repository. Current scoped status is reconciled in
> [PROJECT-LEDGER.md](PROJECT-LEDGER.md) and
> [STAGE-09-10-COMPLETION-MATRIX.md](STAGE-09-10-COMPLETION-MATRIX.md). Read it
> for that campaign's own no-acquisition disposition against a doubled empty
> gateway, which is a different observation from the 2026-10-01 batch's.

# EC02 M3 acquisition/disposition

Branch `wt/ecr2-m3`, base tip `63090c8` (learn+evid+M2 merged). DB
`ec02test_m3` only; doubled gateway only (`FakeGatewayAdapter`). Never
touches `ec02test_live`. Battery:
`tests/test_coord02_m3_acquisition.py` (9 tests, green in ~20s).
Production delta in this commit: zero lines — all required behaviors
already hold on existing `experience.py` machinery; the battery is
additive in `tests/` + this report.

Selection verdict: **none** — with the doubled empty gateway neither
lineage produces usable bytes, so `select_candidate` returns
`{"selection": "none", "reason": "neither candidate executable under
the contract"}` and `freeze_selection` writes a machine-readable
`{"kind": "none"}` package carrying that reason. The old
no-acquisition verdict (`evidence-live/NO-ACQUISITION.md`) stands ONLY
because the live grant is absent (see preflight refusal below); no live
retest occurred on this lane.

## Per-claim table

| Behavior claimed | Production entry/call path | Observed run + revision | Live-vs-doubled deps | Countercheck (would expose a stand-in) |
|---|---|---|---|---|
| 2+ dev tasks acquired end-to-end | `experience.acquire_episodes(dsn, scratch, task_ids=["c02-t16","c02-t01"], ...)` | 9 passed @ `wt/ecr2-m3` (this commit), `test_acquire_two_dev_tasks` | doubled: real episodes on `ec02test_m3`, `LocalLauncher` subprocesses; no model text | packet `task_id`/`run_id` linkage asserted per episode; wrong wiring returns mismatched ids |
| both lineages init+repair | `experience.construct_lineages(episodes, budget, ledger, gateway=FakeGatewayAdapter(text=""))` | same run, `test_construct_both_lineages_init_and_repair` | doubled empty gateway; 4 broker `MODEL_INFERENCE` ops receipted | repair gated on concrete init failure (lineage + op id + reason); a canned policy with no failure link fails the lineage assertions |
| ledger consumption durable | fresh `ConstructionLedger(dsn, allocation_id, attempt_prefix)` on same campaign | same run, `test_ledger_attempt_consumption_durable_across_fresh_ledger` | DB-backed `_operation_ids` scan, not memory | fresh ledger re-reads `operations`; an in-memory list would report 0 |
| invalid/empty requests consume budget | `ledger.request_call(construction_request(..., lineage=99))` → `INVALID_INPUT` + raise | same run, `test_invalid_requests_consume_defined_budget` | same broker machinery | `calls_used()==1` after refusal; a non-consuming guard would report 0 |
| none selection + reason | `select_candidate` → `freeze_selection` → `freeze.verify_freeze` | same run, `test_selection_none_when_neither_candidate_executes`, `test_end_to_end_none_disposition` | validation executes inert bytes as real subprocesses on dev tasks | inert bytes produce recorded failures, not `valid_execution`; a hand-waved none would lack the frozen `kind:none` record |
| winner linkage (when executable) | same path with `DOUBLED_EXECUTABLE` vs `DOUBLED_INERT` | same run, `test_selection_winner_links_lineage_exposure_and_accounting` | real `validate_on_development` solves ≥1 task | ranking `[2,1]`, exposure `prior_lineage_results==[1]`, construction accounting round-trip asserted |
| S-fallback never learned success | `validate_on_development` `fallback_tasks`/`failures` fields | same run, `test_s_fallback_attributed_never_learned_success` | real episode outcomes | inert run asserts `fallback_tasks==[]` plus non-empty failures with no `success`/`learned` status |

## Preflight refusal verdict (verbatim, no secrets)

`TEAM01_LIVE_API_KEY` absent in this environment. `preflight_live()`
with the real environment:

```json
{"admitted": false,
 "problems": ["no gateway endpoint configured (SETTLEMENT_GATEWAY_ENDPOINT)",
              "no live key configured (TEAM01_LIVE_API_KEY)",
              "no live model declared (TEAM01_LIVE_MODEL)",
              "no finite episode grant declared (EC02_LIVE_GRANT_EPISODES)"],
 "blocked_command": "TEAM01_LIVE_API_KEY=<grant> EC02_LIVE_GRANT_EPISODES=<n> SETTLEMENT_GATEWAY_ENDPOINT=<endpoint> uv run python -m experiments.coord02.entry --panel <evaluation|transfer> --model <model>",
 "remaining_cells": {"evaluation": 96, "transfer": 48},
 "grant": {"episodes": null, "construction_calls": 0}}
```

`experience.preflight_live()`: `{"live_grant": false, "reason": "no
TEAM01_LIVE_API_KEY: 4 live construction calls + G2 acquisition
blocked; doubled path only"}`. No live call attempted, no fake
credentials set. Construction budget confirmed by reading (not
re-tuned): `max_output_tokens=65536`, `reasoning_effort=low`,
`label=DOUBLED`, `live_calls_used=0`, `live_calls_authorized=4`.

## Fallback evidence

`validate_on_development` separates `solved_tasks`, `fallback_tasks`
and `failures`; the inert-byte runs record failures with status and
reason, never `success`. `freeze_selection` none path is a durable
machine-readable record (`kind: none` + reason), verified by
`freeze.verify_freeze == []`. S fallback within remaining capacity is
available through this same honest vocabulary, not a relabeled learned
success.

## Fresh-checkout reproduction (read from `pyproject.toml`, not memory)

`pyproject.toml` sets pytest `testpaths = ["tests"]`; package layout is
`src/` (`tool.setuptools.packages.find where = ["src"]`), Python ≥ 3.12.

```sh
git clone <origin-url> Agent-Society-v2 && cd Agent-Society-v2
git checkout wt/ecr2-m3
uv sync                      # provides .venv with pytest>=8.0
createdb ec02test_m3         # Postgres reachable at /var/run/postgresql
.venv/bin/python -m pytest tests/test_coord02_m3_acquisition.py -q
```

Expected: `9 passed`. The suite designates `ec02test_m3` disposable
and truncates all tables on setup; it never opens `ec02test_live`. No
`TEAM01_LIVE_API_KEY` is required (doubled gateway only).

## Red→green log (TDD, against real seams)

1. Stand-in first: assertions written against imagined seams (guessed
   episode status `success`, invented ledger/selection records) — red.
2. Actual seam: acquisition episodes terminate `stopped` (probe-only
   constructor ends in `stop`); corrected the test, not the code.
3. Green via existing machinery: `acquire_episodes`,
   `construct_lineages`, `ConstructionLedger`, `select_candidate`,
   `exposure_manifest`, `freeze_selection` — zero production lines
   changed.

Net: zero production lines changed, zero new shims/branches/flags;
deletion-equivalent: no obsolete path existed to remove — the learn
lane already converged callers on this one design.

## Pre-existing failure (not fixed, not caused by this commit)

`tests/test_coord02_experiment.py::test_entry_write_evidence_round_trip:531`
fails at base `63090c8` (recorded in the M3 tasking). Out of M3 scope.
