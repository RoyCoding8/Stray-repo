# Workstream inv-learning02-m2: durable investigations and inherited improvement

Owner: m2-frontier lane. Worktree `.worktrees/m2-frontier`, branch
`wt/m2-frontier`, base `f1cbe01`. Owned paths only: this report,
`experiments/ad01/frontier.py`, `experiments/ad01/improve_channel.py`,
`tests/test_m2_frontier_inherit.py`. No other lane files touched.

## What was built

`frontier.py` owns the durable frontier of admissible work. The study
freezes mission plus environments. It never names the next
investigation. The program chooses through its own STEP bytes under
explicit query/step authority. One JSON store holds opportunities,
observations, outcomes, obligations, pending effects, the active
package, lineage, retained evidence and acquired arms. Every mutation
saves atomically, so the investigation survives a restart. Replay
returns a recorded outcome only on exact identity match and
`unsupported` otherwise. Prediction is a separate class and never a
replay result. Readiness is event-driven. No loops, timers or
schedulers were added.

`improve_channel.py` owns the shared executable package: one
operational STEP source plus one improvement STEP source under a
package digest that binds both bytes and the parent/version/identity
lineage. The improvement entry returns probe, construct and select
actions that the driver executes through the real boolean-rule
instrument and the leaf constructor. Two authored controls share
operational bytes and differ in improvement bytes. Leaf construction
maps the requested strategy to the next package. Adoption binds at a
quiescent boundary, pins settled effects to their original digest,
resets private state and retains evidence plus obligations explicitly.

Reuse without edits: `method_exec` verification plus out-of-process
STEP execution, `policy_step` STEP envelope plus action contract plus
versions, `packet` sealed projection plus packet version,
`boolean_rule` as the real probe instrument. New probe-family action
kinds were added because the software/graph vocabulary cannot honestly
represent a boolean-rule probe. Operate STEP output travels inside the
shared `diagnose` envelope with the frontier intent in its inputs.

## Verification

Failing repro first: the new test file was run before the modules
existed and failed at collection on the missing imports. The fixed
panel characterization test documents the defect the frontier
replaces. After implementation the lane suite passes 12/12.

Gates run, all with
`PYTHONPATH=$PWD:$PWD/src:$PWD/experiments
/home/ubuntu/AI/Agent-Society-v2/.venv/bin/python -m pytest`:

- `tests/test_m2_frontier_inherit.py`: 12 passed.
- Adjacent deterministic suites `test_m3_rule_instrument.py`,
  `test_m1_shared_executor.py`, `test_m4_offline_recompute.py`:
  43 passed alongside, 55 total, no regressions.
- Fresh-process proof runs inside the suite: a new OS process loads
  the retained package bytes from the store file and generates the
  round-2 candidate through them.

Covered behavior: observation-dependent choice of next work, restart
survival with continued choice, known probe divergence x=3 versus
x=11 under matched inputs with identical operational output,
quiescent adoption with pinned history plus state reset plus
authority refusal, second improvement round under inherited bytes
after a disk reload, replay compatibility plus prediction separation,
control labeling with treatment-arm separation, event readiness,
purpose-bearing views with frozen source visible only to improve.

## Gaps and boundaries

- Operate-level construct, reuse and revise actions are validated,
  authority-checked and recorded, but not executed. No live
  constructor or model exists in this deterministic lane. Live
  construction stays with M5.
- Jev checkpoints were not called. The lane setup forbids live
  network and the key value must never be printed, so typed review
  stays with the coordinator.
- The boolean-rule instrument is reused from the M3 lane by import
  only. Development seeds 4 and 5 are used. Qualification and audit
  splits are never touched.
- Hygiene: no database was used, no `/tmp/opencode/m2-frontier`
  scratch was created, no secrets are in the diff, and `git status`
  shows only the four owned paths.
