# EC02 Lane L — learning (experience packet, construction, selection, frozen use)

Branch: `ec02-lane-L`. Tip at write time: `a584aa8` (merge of integration
tip; prior task tip `d02e69a`). Base for this lane's diff: `a584aa8`.

Owned paths only: `experiments/coord02/experience.py` (new),
`tests/test_coord02_learning.py` (new), this report. `src/settlement/*`
read-only; R seam (`experiments/coord02/controller.py`) and W interfaces
(`oracle.py`, `checker.py`, `freeze.py`) used, not modified.

## No-live-grant posture

No `TEAM01_LIVE_API_KEY` in the environment, so no live model call is
possible. All construction runs route through the broker
(`ensure_operation` + `dispatch_operation`, effect `MODEL_INFERENCE`)
against the `FakeGatewayAdapter`. Every such run is labeled `DOUBLED` in
code (`CONSTRUCTION_LABEL`, `DOUBLED_NOTE`) and in each ledger record
(`label`, `doubled=True`, `live=False`).

Construction-call accounting: **0 live used / 4 authorized.**
`construction_budget()` returns `max_calls=4, live_calls_used=0,
live_calls_authorized=4`. The 4 live construction calls + G2 acquisition
await the grant. No hand-written coordination strategy is presented as
model-built: test stand-ins are named `DOUBLED_*_TEST` and described as
"DOUBLED construction-path test stand-in".

## What was built

`experiments/coord02/experience.py` (public surface):

- REAL-episode acquisition: `acquire_episodes` runs dev-task episodes
  (c02-t01…c02-t26 subsets) through the R seam; `build_experience_packet`
  assembles `coord02-experience/1` packets with versioned inputs,
  decisions, probe observations (first interface always `observe-broken`,
  no protected-case content), executed operations, cost with explicit
  `unknown` fields, development observations, and selection ground truth.
- Construction: `construction_budget`, `construction_request`,
  `ConstructionLedger` (`request_call` broker-routed, `repair_call` with
  protected-feedback refusal, 4-call ceiling raising
  `ConstructionBudgetExhausted`, `accounting` with live/authorized split).
  `keep_response` records every reply including empty/non-JSON ones.
- Strict gate: `parse_candidate` (compile + nonempty), `stage_candidate`
  (labeled staging), `check_candidate` (publish + frozen reload +
  digest match), `stage_gate` returning parse/stage/check/select verdicts.
- Validation/selection: `validate_on_development`,
  `ORDERING = (valid-execution, solved-tasks, model-tokens, sandbox-ops,
  canonical-bytes)`, `select_candidate` (winner or explicit `none`),
  `freeze_selection` (selected or none-kind freeze via W helpers).
- Frozen use: `publish_retained` (publish + byte verification + retention
  hooks: applicability, evidence refs, scope, dependencies, budget),
  `revoke_binding_eligibility` (quarantine on control),
  `scoped_loss_evidence` (binding-scoped, never global).

Fixes found by probing (all verified on real PG + subprocesses):

- Dev binding digest mismatch: `_requires_for`/`_dev_bindings` now match
  oracle worker paths by stem instead of positional pairing.
- `check_candidate` compared entry-bytes SHA against the package digest
  (whole-archive SHA); now compares staged vs loaded entry bytes.
- `publish_retained` attaches retention hooks on both `APPLIED` and
  `ALREADY_APPLIED`.
- `ConstructionLedger.request_call` checks the 4-call budget before the
  per-lineage guard so overspend raises `ConstructionBudgetExhausted`.

## Freeze contents for E

`freeze_selection` output for the E lane: freeze id, source SHA, selection
(winner lineage or `none` kind), per-lineage dev results, exposure
manifests, construction accounting (calls used, 0 live). Tested for both
the selected path (via `stage_gate`) and the `none` path (unparsable
entry → `verify_freeze` clean).

## Limits

- No live calls; doubled construction only.
- Dev-task evidence is acquisition (REAL episodes), not G2.
- Retention hook fields ride on `CommandResult.data["hooks"]` because the
  capability store has no dedicated retention columns.

## Gate

`tests/test_coord02_learning.py`: **9 passed** on real PG
(`dbname=ec02test_l`) with real subprocess launches, ~18s.

## Request to R / W

None. No controller or oracle/checker/freeze changes needed.
