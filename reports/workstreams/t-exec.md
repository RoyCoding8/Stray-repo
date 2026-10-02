# T-EXEC workstream report: EC02 execution lane (reclaimed by coordinator)

Base `fa777d5`, branch `wt/ec02-exec`. Lane agent stalled 3x (analysis
only, zero implementation); coordinator reclaimed per stated rule and
implemented the entry side directly. Doubled gateway only at the model
seam via labeled RECORDING double; DB `ec02test_exec` only; never
touches `ec02test_live`.

## Owned scope

`experiments/coord02/entry.py` (sole owner) + `tests/test_coord02_exec.py`
(new, 8 tests) + this report. No edits to `schemas_evidence.py`,
`experience.py`, controller, checker, or other lanes' paths.

## Production delta (entry.py)

1. `run_cell` requires explicit `gateway` + `model` (no silent Fake
   default; explicit doubled default keeps preserved batteries honest);
   `run_panel` forwards both; `main` builds the real adapter via
   `gateway_factory(doubled=...)` (`HttpGatewayAdapter.from_env`,
   `responses` API on live; `FakeGatewayAdapter` on doubled) and passes
   it into panels — ECA-01 adapter propagation closed.
2. `arm_decision` A-branch returns distinct `stop` / `unsupported` kinds;
   `run_cell` routes both to the explicitly-marked S-fallback path (no
   child dispatch on a model stop) — a model stop actually stops.
3. Interpreted A proposals ride the recorded decision chain: the A policy
   program's response `state` carries `model_proposal` (`_SEED_STATE`
   merge in the shared epilogue), so the post-probe plan carries
   model-produced children/obligations into `_admit_plan`.
4. `arm_child_factory` A-arm returns `admitted_child_factory`: submits
   owned-path bytes with the admitted obligation deterministically
   stamped (repairs map honored when present; harmless comment stamp
   otherwise). Changed model responses change submitted bytes and the
   graded result. `live_child_factory` (unchanged-input stand-in under a
   live name) deleted — zero references anywhere; `solved_child_factory`
   stays behind the explicit FIXTURE label only.
5. F partitions on demonstrated probe evidence: `coupled` (successful
   `interface`-bearing observations) required alongside multi-file and
   fresh deps; probe-error observations never authorize decomposition.
6. L with a retained package executes its bytes (`arm_policy_entry`
   returns them verbatim); absent package stays the recorded none →
   explicit S-fallback with scheduled arm preserved.

## Per-claim table

| Behavior | Production path | Observed run + revision | Live / doubled deps | Countercheck |
|---|---|---|---|---|
| Model output reaches submitted bytes | `run_cell` → `arm_decision` (interpreted) → `_SEED_STATE` → post-probe plan → `_admit_plan` → `admitted_child_factory` | 8/8 green @ working tree (`test_coord02_exec.py`) | recording double at model seam; real PG + subprocesses | red failed pre-fix (`differed == []`); poisoned overlays change nothing |
| stop/unsupported diverge from plan | `run_cell` kind routing + S-fallback | same run | same | distinct failure markers asserted |
| Fixture route locked | `arm_child_factory` label gate | same run | pure | `LIVE` label raises |
| L executes retained bytes | `arm_policy_entry` L branch | same run | same | arm + package_digest asserted; none → attributed fallback |
| Over-budget dispatches nothing | `check_ceilings` pre-admit + broker admission | same run | real PG admission | ceiling breach list non-empty; allocation stays within authorized |

## Regressions (same worktree code)

- `test_coord02_m2_qualification.py`: 12 passed.
- `test_coord02_exec.py`: 8 passed.
- `test_coord02_learning.py` + `test_coord02_experiment.py`: 50 passed.
- `test_coord02_m4_frozen.py`: under investigation (fixture-scope
  errors; single-test probe running — see below).

## Contract-change note for T-STATE (not implemented here)

`run_cell` computes `executed` (S/A/F/L-acquired/S-fallback) and
`fallback_note` but `SE.build_trial_record` accepts neither kwarg yet —
threading waits on T-STATE's schema side per the pinned contract. No
unilateral schema edit made.

## Open: M4 fixture errors

M4's module fixture (full 144-cell `run_panel`) errors under the new
entry. Single-test probe in flight (`/tmp/m4-one-test.log`). Suspects:
obligation-stamp interaction with M4's digest/panel assertions, or the
F-condition change on M4's schedule. Fix stays in entry.py; M4 battery
itself is preserved evidence and will not be weakened.
