# M1 workstream: one runtime meaning across development and assessment

Lane: M1. Worktree: `.worktrees/m1-exec`, branch `wt/m1-exec`.
Base verified: `d10c471` Merge wt/m0-baseline. No merge by this lane.

## Decision

No new `src/settlement/executor_unified.py`. The existing dispatcher
(broker effect validation plus `method_exec` child execution plus the
`seeds` repertoire plus `policy_step` STEP execution) already owns every
effect. A new unified file would be a mirrored authority. The lane adds
one profile model instead: `experiments/ad01/assessment_profile.py`.

`policy_assess.py` is untouched. Its `_effect` refusal of model requests
and revision actions stays frozen under the labeled legacy profile
`assessment-restricted`. New qualification routes both development and
assessment through `assessment_profile.dispatch`.

## What dispatch guarantees

One `Profile` structure per lane role carries permissions, visibility,
budgets, destinations. Development and assessment share every owner:

- STEP bytes execute through `policy_step.run_policy_step` in both.
- `construct_method` and `use_method` run through `seeds.run_seed` or
  the `method_exec` child, with the packet-stripped task, so sealed
  keys never reach child execution through the task route either.
- `request_model` builds broker `MODEL_INFERENCE` operations through
  `broker.validate_effect` with byte-identical payloads. The restricted
  legacy profile refuses with a reason naming the declared difference.
- `propose_revision` stages locally only. `bind_revision` binds only
  with trusted qualification plus exact candidate digest plus exact
  scope. Audit never binds and never writes production destinations.
- Nested assessment requests are refused beyond depth one.
- Source digest and scope are verified before any owner is called.
  Target mismatch, unseen evidence references, over-budget requests,
  and production destinations under non-production profiles refuse.
- Every method effect reports the actual selected identity, including
  the family-default fallback when the program names no method.

## Verification sequence

Red first: the new suite was written before the module existed and
failed at collection with `ModuleNotFoundError:
experiments.ad01.assessment_profile`. The legacy divergence demo in
the same file passes throughout and pins the frozen behavior.

Green after: `tests/test_m1_shared_executor.py` 15 passed, including
same-program same-effects across profiles, real-owner call counts by
monkeypatch, no-second-interpreter source guard, identical broker
payloads, staged-only revision with trusted bind, depth bound, audit
production-write refusal, freeze-before-execution with zero owner
calls, fallback identity reporting, sealed-view exclusion, and the
stripped-task probe added for the Jev secrecy finding.

Nearby gates on the same revision: `tests/test_s09o_policy_assess.py`
8 passed, `tests/test_s09m2_policy.py` 2 passed. Combined run:
25 passed. Exact command:

- `uv run --with pytest python -m pytest
  tests/test_m1_shared_executor.py tests/test_s09o_policy_assess.py
  tests/test_s09m2_policy.py -q`

No live network. No new service. No lane database created. The nearby
DB-backed suites created and dropped their own fixtures.

## Jev checkpoints

Artifacts: `reports/jev/invl02-m1-shared-executor-request.json`,
`reports/jev/invl02-m1-shared-executor-response.json`,
`reports/jev/invl02-m1-secrecy-boundary-request.json`,
`reports/jev/invl02-m1-secrecy-boundary-response.json`. Sanitized to
model, answers, and token counts.

- Shared executor preserves meaning: boolean true, probability 0.89.
  Disposition: accepted, no change. The executing tests already prove
  same owners and matching effects.
- Weakest secrecy seam: choice `visibility_allowlist`, probability
  0.35 at confidence 0.19, with `view_projection` and `binding` at
  0.25 each. Disposition: partially accepted. The indirect task route
  into child execution was a real gap. Fixed by stripping the task
  with `packet.strip_task` before both method owners, plus an
  executing probe asserting sealed literals never reach the owner
  while witness and identity survive.

## Gaps

- Model dispatch through a live gateway is constructed but never
  sent here. Live qualification stays for M5 with valid authority.
- The legacy sealed assessor still cannot certify model or revision
  behavior. Frozen studies keep that label and that limit.
- Audit profile allows assessment-local method effects. A stricter
  read-only audit remains an open profile choice, not a defect.

## Files

- `experiments/ad01/assessment_profile.py` (new, about 300 lines).
- `tests/test_m1_shared_executor.py` (new, 15 tests).
- `reports/jev/invl02-m1-*.json` (4 sanitized artifacts).
- This report.
