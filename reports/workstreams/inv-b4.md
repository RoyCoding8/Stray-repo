# INV-B4: IR-03 kill at the trajectory caller

Scope: `experiments/ad01/trajectory.py`, `tests/test_inv_b4_trajectory.py`
(new), one justified assertion migration in
`tests/test_inv_b1_contracts.py`. `src/**` untouched. Branch
`wt/inv-b4-trajectory`, worktree `.worktrees/inv-b4`.

## Root cause

`_run_boundary` promised the same queries twice from one number. The
development pre-cap and the diagnostic grant both computed
`remaining - 1` from pre-diagnostic remaining, and construction then
received the pre-diagnostic figure after the diagnostic had spent:
remaining 6 granted diagnostic 5, the graph diagnostic spent 4, and
construction was still granted 5, so boundary spend reached 10 against
6. Nothing in the path sequenced sub-budgets. The zero-budget probe
was worse: `dev_episode(max_queries=0)` returned a study lineage entry
while `_run_boundary` still ran `construct_method` first, burning one
of the 2/trajectory construction lineages plus model calls before
discarding the member. Measured on base: C3 I-arm seq 2
(`ad01-w0-dev-sw-00`) rejected with `construction failed: lineage cap
reached (2/trajectory)`, starved by the seq 1 zero-budget probe.

## Invariant restored

Sub-budgets sequence from remaining minus actual diagnostic spend
through `ResourceEnvelope.sequence_construction_allowance`, and a
zero-budget probe is refused through the loop `admit_probe` path with
both lineages intact: no `construct_method` call, episode lineage
`[]`, boundary spend bounded by remaining.

## Change

`experiments/ad01/trajectory.py` only, signatures unchanged:

- New `_sequenced_construction_allowance` helper routing through the
  envelope. Both hand-rolled `max(0, remaining - 1)` grants
  (development pre-cap, diagnostic budget) now call it with zero
  prior spend, which is arithmetically identical and deletes the
  second authority for the math.
- After `run_diagnostic`, development re-sequences: `action_max =
  min(requested, envelope(remaining, actual_diagnostic_spend))`. The
  granted construction budget and the journaled decision visibly carry
  the reduced figure. Remaining 6, diagnostic spent 4 now grants
  construction 1.
- Zero sequenced allowance skips `construct_method` entirely and falls
  into `dev_episode(max_queries=0)`, which now routes through
  `ResourceEnvelope.admit_probe` (dedicated `ad01-trajectory-probes`
  allowance identity, loop `zero-budget-probe` refusal) and returns
  lineage `[]` with the refusal reason. Nonzero paths are untouched.

## Existing-test migration (one, justified)

`tests/test_inv_b1_contracts.py::test_c3_trajectory_admits_every_model_call`:
`"rejected" in dispositions` became `"no-candidate" in dispositions`.
The old assertion encoded the bug above: the rejected episode was
sw-00 starved by the lineage the zero-budget gr-00 probe burned
before its member was discarded. Post-fix the probe takes the refusal
path, sw-00 retains, and every model call is still broker-admitted
(the rest of the test, learner/construction counts and receipts,
passes unchanged). Rejection coverage still lives in
`test_rejected_episode_is_visible_not_silent`, green.

## Gate evidence (disposable databases)

- `tests/test_inv_b4_trajectory.py`: 4 passed, DB-free. Failing-before
  run on base: 3 failed (construction granted 5, probe lineage of 1,
  construct called on zero budget); the software zero-spend guard
  passed before and after.
- `tests/test_ad01_traj.py`: 31 passed on `ec02test_adtr`.
- `tests/test_ad01_env.py`: 32 passed, DB-free.
- `tests/test_inv_b1_contracts.py`: 11 passed on disposable `inv_b4_b1`
  (via `INV_B1_DSN`), after the one justified assertion migration.
- Nearby, no regressions: `test_alec_episode` + `test_p2c_ad01_resweep`
  11 passed, `test_alea_experience` 6 passed, `test_aled_campaign` 18
  passed, `test_inv_b2_loop` 8 passed on `inv_b2_loop`. `src/**`
  unmodified, so loop/broker suites are unaffected by this branch.
- `inv_b4_b1` dropped after the gate. `inv_b2_loop` was created for
  the envelope nearby check and left in place. No test changes beyond
  the one justified assertion. No monkeypatched controller, no canned
  solution, no silent fallback, no secrets in Git.

## Verification boundary

Fake `construct_method` doubles sit behind the budget-capture seam in
the new tests; every grant number comes from the real `_run_boundary`
plus the real graph diagnostic and seed episode. Live inference and
containment are not validated here.
