# Workstream inv-d2: settle unbilled model calls at measured tokens

Owner: Nightjar. Worktree `.worktrees/inv-d2`, branch `wt/inv-d2-settle`,
base `b67ecbf`. Owned paths only: `src/settlement/store.py`
(`_settle_amount` path), `src/settlement/broker.py` (receipt `actual_cost`
line), `tests/test_invd2_settle.py` (new), this note.

## Defect INV-C5

Unbilled model calls settled at the full characters/4 reservation estimate
while the settled receipt reported small measured tokens unbilled.
Reproduced on this tip with a 1746 character learner prompt and 2048 max
output tokens. Reservation exposure was 2485 units. The gateway receipt
reported input 5, output 5, billed false. Allocation consumed was 2485.

## Root cause

`broker._send_model` set `actual_cost` only when usage was billed.
Unbilled responses sent `None`. `store.admit_receipt` passed that `None`
into `_settle_amount`, which books the whole reservation when actual is
missing. Internal charges therefore collapsed to the estimate for every
unbilled call even though measured bytes sat in the same receipt row.

## Fix

Two lines carry one decision. Measured usage is input plus output tokens.

- `src/settlement/broker.py`. Unbilled gateway receipts now construct
  `actual_cost` as input plus output tokens. Billed receipts still use
  provider charge units. Unknown outcomes still send no cost.
- `src/settlement/store.py`. `admit_receipt` falls back to receipt usage
  tokens when `actual_cost` is missing, the outcome is decided, usage
  reports billed false, and both token counts are present integers.
  Sandbox and inline receipts carry no usage, so they keep the existing
  full reservation settlement. Unknown outcomes keep the existing
  uncertain exposure path. Over measured reservations still refuse
  settlement and retain exposure through the existing infeasible path.

The reservation remains the pre effect bound. Admission still requires
free cover for the full estimate. Settlement only releases the unused
remainder after the measured effect.

## Gates

New gate `tests/test_invd2_settle.py`. Three tests on disposable
`inv_d2_settle`. Failing before, passing after.

- Unbilled 1746 char prompt with 2048 max output exposes 2485, settles
  at 10, receipt carries input 5, output 5, billed false, charge 0.
  Before the fix consumed was 2485. After the fix consumed is 10.
- Billed same prompt settles at provider charge 42. Unchanged.
- Unknown gateway outcome retains 2485 reserved with zero consumed.
  Unchanged.

Nearby results with disposable `inv_d2_*` databases.

- `tests/test_invc2_authority.py`. 4 passed. Ledger sums use billed,
  unknown, and sandbox paths. No unbilled model success is present,
  so corrected semantics change nothing here.
- `tests/test_aled_campaign.py`. 18 passed. Union assertions read
  billed receipt content. Billed paths are unchanged.
- `tests/test_inv_c_qualification.py`. 8 passed, 1 failed.
  `test_envelope_sequences_diagnostic_construction_repair` expects
  diagnostic remaining of start minus exposure 19. Corrected settlement
  consumes measured 18 for the unbilled double with input 11 output 7.
  Remaining is start minus 18. This failure is the fix working. The
  owning lane should migrate that one assertion from exposure to
  measured with this justification. This lane leaves the file untouched
  per disjoint ownership.
- `tests/test_settle_actual.py`. 7 passed. Generic no usage receipts
  still settle at full reservation. Billed partial settlement unchanged.
- `tests/test_inv_f2_loop.py`. 3 passed. Billed measured reads unchanged.

Out of scope failures that encode the old estimate behavior. Left
untouched per disjoint ownership. Each needs its owning lane to migrate
to measured with the same justification.

- `tests/test_r02_exec.py`
  `test_unbilled_settlement_reports_conservative_debit` expects 1000.
  Corrected settlement consumes 30 for input 10 output 20 unbilled.
- `tests/test_r02_authority.py`
  `test_unbilled_usage_settles_full_reservation` expects full exposure
  51. Corrected settlement consumes 0 for the fake gateway with zero
  measured tokens.

## Verification boundary

Fake gateways and fake sandboxes prove settlement arithmetic only.
They do not validate live inference or containment.
