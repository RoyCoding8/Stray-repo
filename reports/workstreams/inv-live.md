# inv-live — live qualification on the verified free model

Grant (human, this session): study-root `inv01-live`, model
`nvidia/nemotron-3-ultra-550b-a55b:free`, reasoning effort high,
`--agenda-authorized 600000`, deadline 3600s, full 6-trajectory study
after a bounded pilot goes green. No fallback model was needed. Keys
stay in memory and never enter Git or any report.

## Bounded pilot (same grant, small shape)

`--max-trajectories 1 --max-boundaries 1` on disposable `inv_r1_live`:
study rc 0, provider live, ultra model, 7 operations, 3 success
receipts with real nonzero token usage and zero charge. Green.

A same-root resume to full shape was correctly refused by settlement
semantics (`ConflictPayload`: campaign scheduled with 1 task cannot be
re-planned with 6), so the full run used a fresh disposable database.

## Full study (disposable `inv_r1_livefull2`)

Study rc 0. Provider live, model ultra, grant 600000, 6 trajectories,
6 exports, 24 use records, 47 operations, 36 success receipts.
`--recompute` rc 0 with 43 model calls, 10 construction calls,
24 use records and 548 witness queries against the 360/24/960/5328
ceilings. Receipt sums: 0 charge units, 40801 input tokens,
40002 output tokens. Zero spend.

## Live-found defect and fix

The first full-shape attempt failed the merged `verify_study` gate:
`ad01-w1-I-00` reported 3 construction calls against 4 ledger ops.
Root cause in `experiments/ad01/construct.py`: the repair-transport
handler recorded the failure and broke to the next lineage without
counting the ledger row it had created, so reported totals drifted
from recomputation. Fixed at the source (count the repair row when it
exists) with regression `tests/test_invfix_construction_count.py`
(red first: 2 vs 3; green after with nearby `test_aleb_construct`
plus `test_ad01_traj`: 36 passed). Committed as `a9cd159`. The rerun
above is the post-fix evidence. Committed evidence lives in
`evidence_inv01_live/` (endpoint string redacted, all other bytes
identical): 6 exports, 6 repertoires, study, accounting, cap sheet,
freeze, manifest and 24 use records.

## What was learned and retained

Nothing retainable, stated plainly. All 6 repertoires hold zero
members and all 24 use records fell back to the incumbent. Per
trajectory model/construction calls: w0-I 10/4, w0-R 5/1, w1-I 13/4,
w1-R 5/1, w2-I 6/0, w2-R 4/0. Observation verdicts over 28
transitions: seed preserved with novel not preserved in 10, mutual
not-preserved in 6, exact ties in 12. The system proved diagnosis
without acquisition on this panel at high effort.
