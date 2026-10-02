# Workstream inv-f2: loop-layer review findings

Scope. `src/settlement/loop.py`, `src/settlement/broker.py`,
`src/settlement/store.py`, `tests/test_inv_f2_loop.py`, this note.
Tip under test. `804940d`. Databases `inv_f2_verify`, `inv_f2_loop`,
`inv_f2_b2`, `inv_f2_broker`. All dropped after the runs quoted below
except `inv_f2_loop`, `inv_f2_b2`, `inv_f2_broker`, which hold no live
state and are dropped next.

## Finding 1. Zero-budget probes and the single envelope hold

Source. Semantic review failure reproduction and state finding T05.
They name `loop.py` `admit_probe`, `sequence_construction_allowance`
and `store.allocation_free`. Both reviews accept the behavior.

Verdict. Not a defect on this tip. No code written.

Evidence. Throwaway probe `/tmp/opencode/inv_f2_verify.py` on
`inv_f2_verify`. Amount 0 probe refused with `zero-budget-probe` and
study consumed plus reserved unchanged. Later amount 5 grant succeeds.
Remaining nets the subdivided probe child. Allowance sequencing reads
1, 5 and 0 for the three literal cases. Sandbox admission consumes
exactly the admitted exposure and remaining reflects the spend. The
committed B2 gate passes 8 of 8 on `inv_f2_b2`.

## Finding 2. Post-effect cost reads ignored receipt content

Source. State finding T06. It names `loop.py` `read_measured_costs`
and `run_boundary` journaling over `store` receipts. The review accepts
the behavior, so this finding was taken as a re-verification and it
failed.

Root cause. `store.operation_receipts` selected only
`receipt_identity` and `outcome`. `loop.read_measured_costs` reads
`content.usage.billed` from those rows, so the billed branch was dead
and measured cost returned 0 for every operation, including billed
model calls. The same gap left `run_boundary` observations and
journaled transitions carrying empty content. Every other content
reader in the tree (`experiment.py`, `capabilities.py`,
`evaluation.py`, `development.py`, `representation.py`, `team.py`)
selects `content` explicitly. Only the loop path relied on the
narrow row shape.

Failing before. New `tests/test_inv_f2_loop.py` on `inv_f2_loop`.
`test_measured_costs_read_billed_receipt_content` failed with
`assert 0 == 3` for a billed gateway receipt with charge units 3.
`test_run_boundary_observation_carries_receipt_content` failed with
`assert {} ==` the inline note receipt content. The unknown-receipt
guard test passed throughout, as its path uses outcome only.

Fix. One line in `src/settlement/store.py`. `operation_receipts`
now selects `receipt_identity, outcome, content`. No caller depends
on the narrow shape. Broker uses outcome and row counts only. All
test usages read identity, outcome, length or empty equality.

Passing after. `tests/test_inv_f2_loop.py` passes 3 of 3.
B2 plus F2 passes 11 of 11. Broker and store suites pass 54 of 54
across `test_broker_prepare`, `test_broker_dispatch`,
`test_adv_broker`, `test_settle_actual` and `test_acct_store_costs`.
The full throwaway probe passes 21 of 21, including billed measured
7 through the production dispatch path and unchanged unknown listing.

Invariant restored. Post-effect reads observe settled receipt bytes.
Billed usage measures, unknown exposure stays listed and is never
zeroed into measured, and journaled transitions carry the receipt
content they claim to record.

## Finding 3. Malformed actions take visible effect

Source. Semantic finding S02. Its loop-layer half is the
`run_boundary` refused path in `loop.py`.

Verdict. Not a defect on this tip. No code written.

Evidence. The throwaway probe refuses a teleport instrument with
`refused:malformed-action`, journals no operation, then admits the
note correction with one receipt. The journal holds both transitions
in order. The B2 rejection-then-correction test passes unchanged.

## Out of scope notes

State finding T11 names lane D report totals, not loop files. The
correction already sits at `9f273ec` on this branch.

`test_r03_flow` restore tests and `test_broker_dbos` error before
reaching behavior with `psycopg.ProgrammingError` on their DSN
string. The same 2 failures plus 2 errors reproduce on the clean
tree with this fix stashed, so they are pre-existing and outside
this scope. Restore and DBOS paths are untouched.

## Verification boundary

Doubles prove the integrated path, not live inference or
containment. No committed test uses a monkeypatched controller or a
direct proposal callback. All databases named above are disposable.
