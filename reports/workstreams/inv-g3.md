# inv-g3: AD01 open-findings sweep

Tip at start: `8a14a46`. Branch: `wt/inv-g3-ad01`.

## Findings handled

1. IR-01(b) (EC02-AD01-84D2094 assessment): `_run_boundary` ran the
   diagnostic but forwarded the earlier `seen` packet to
   `construct_method`, so the just-produced diagnostic observation never
   reached the construction prompt. OPEN on this tip, reproduced red,
   FIXED here: the construction experience now appends the fresh
   observation to the accumulated `seen` observations. Invariant
   restored: the constructor observes every diagnostic result produced
   on its boundary, including the current one.
2. IR-01(a) (prompt content gap): already fixed. `packet.py` carries
   full task content, candidate shape, reducer signatures, verdicts
   plus reason codes, observation detail and entry rules from one
   `method_exec` contract. No code written. Evidence: B1 gate 11/11
   green on `inv_g3_ad01`.
3. IR-03 (allowance re-grant): already fixed by `d59c809`
   (`_sequenced_construction_allowance` after diagnostic spend). No
   code written. Evidence: B4 gate 4/4 green, including
   `sequence_construction_allowance(6, 4) == 1`.
4. BDR-01 (host execution): already fixed. Unknown members route
   through `method_exec.run_member_out_of_process`; no `exec` of
   candidate bytes in the host. No code written. Evidence:
   `test_bdr01_host_boundary.py` green.
5. BDR-03 (protected-target admission): already fixed
   (`_target_refusal` at the dispatch boundary). No code written.
   Evidence: `test_bdr03_target_admission.py` green.

Out of scope met but untouched: BDR-02 (EC02 child identity, outside
`experiments/ad01`), INV-R-T11 (reports arithmetic, already corrected
at `9f273ec`).

## Diff

- `experiments/ad01/trajectory.py`: construction call passes
  `{**seen, "observations": [*(seen observations), observation]}`
  instead of bare `seen`.
- `tests/test_inv_g3_obs.py`: DB-free regression test doubling
  `construct_method` at the seam; asserts seed plus fresh diagnostic
  observation ids reach the constructor with detail attached.

## Evidence

- Red: `test_construction_receives_fresh_diagnostic_observation`
  failed before the fix (`'obs-c3-novel-unproductive-...'` not in
  `['obs-ad01-w0-dev-gr-00-seed']`).
- Green after: 1 passed; nearby `test_inv_b4_trajectory` 4 passed,
  `test_inv_b1_contracts` 11 passed (on disposable `inv_g3_ad01`),
  `test_ad01_traj` + `test_ad01_env` + bdr01 + bdr03 76 passed,
  `test_inv_c_qualification` 9 passed (on disposable `inv_g3_ad01`
  plus `inv_g3_ad01b`). Databases dropped afterwards.
- Boundary: doubled gates prove doubled behavior only; no live
  inference or containment claim.
