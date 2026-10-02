# INV-R2: S2 interrupted-decision state (lane R2)

- Base: `8d2b2a5`, branch `wt/inv-r2-resume`, worktree `.worktrees/inv-r2`.
- Scope: `experiments/ad01/agenda_policy.py`, `experiments/ad01/trajectory.py`
  (boundary diagnostic checkpoint only), `tests/test_invr2_*.py`, this report.
- Assignment: `WORKER-INVESTIGATION-01-STUDY-READINESS.md` S2 plus rejecting
  checks; reviewer input ICR-02 in
  `reviews/INVESTIGATION-01-7941AB4-ASSESSMENT.md`.

## Delivered

- Resumed `DecisionConsumer` restores the full last correction from the
  durable journal: rejected target, failure reason, correction index, and the
  pre-boundary remaining allowance. Target release only through the declared
  `_releases_pin` semantics.
- Allowance restoration counts current-boundary model calls so the resumed
  provider request is byte-identical to the victim's (`remaining 60`, one
  `60`/`59` byte located by diff during development). The broker then
  returns `ALREADY_APPLIED` instead of an identity conflict.
- A crash orphaned mid-dispatch is never silently resent (broker at-most-once
  guard). The consumer retries once with a fresh identity while preserving
  the restored prior instead of journaling the transport artifact.
- `_run_boundary` persists diagnostic completion, observation, remaining
  allowance, and state counters through `authority.note_phase` before
  construction, and reuses the saved result on resume with zero diagnostic
  redo. Persist degrades gracefully when the deciding operation is not study
  work (custom funding) or no learner operation exists (scaffolding path).

## Rejecting checks (real processes, real Postgres, `inv_r2_*` only)

- Kill after first invalid proposal, before correction; resume fresh: next
  real provider request carries `PRIOR FAILURE` with refused target `SW0`
  pinned and the invented-basis reason. Settled identities stable (base
  learner op exactly one success receipt, one correction row). Orphaned `c1`
  keeps zero receipts; retry settles `c2` once. One resumed provider call.
- Kill after diagnostic completion, before construction; resume fresh: zero
  diagnostic calls, zero learner calls, unchanged observation, equal queries,
  model calls, construction calls, spend, and disposition `retained` versus
  an uninterrupted control on a separate database. Phase reread returns the
  same operation id.
- No replacement campaign, no pre-completed boundary; resume replays the
  pending decision of the same campaign.

## Gates

- `tests/test_invr2_correction.py`: 3 passed (2 unit, 1 kill-resume).
- `tests/test_invr2_diagnostic.py`: 1 passed (control plus kill-resume).
- Nearby: `test_ad01_traj.py`, `test_alee_learner.py`, `test_inva_recovery.py`
  (38 passed, 4 skipped), `test_invc2_recovery.py`, `test_aled_campaign.py`
  (with invr2: 25 passed), `test_p2c_ad01_resweep.py` (6 passed).
- One pre-existing learner test funds calls from a custom allocation; the
  checkpoint skips persisting there rather than failing the boundary.
- Scratch `.ad01-runs/` removed; disposable `inv_r2_*` databases dropped.

## Remaining gaps

- Mid-dispatch orphans of model construction calls have no broker-supported
  resume; the diagnostic proof crashes before construction entry, which is
  what the check specifies.
- Fake doubles sit at the provider seam only; no live inference validated.
