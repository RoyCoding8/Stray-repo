# Workstream: independent re-review of Investigation 01 completion

Reviewer: independent, not an implementer. Worktree `.worktrees/inv-rereview`,
branch `wt/inv-rereview`, reviewed tip `c519926` (implementation identical to
`a41d4b3`; the tip delta is reports only). The stale-tip review `9d74ea7` is a
sibling branch, not an ancestor, and was read from its commit without checkout.

## Method

Every deciding path ran on real Postgres with doubles only at the provider
seam (recording/scripted gateways plus the real local child-process launcher).
Disposable databases `inv_rr_v2_*` (16 total) were created for this review and
all 16 were dropped after. Pre-existing `inv_rr_*` stores from the interrupted
attempt were inspected read-only and left untouched. `.ad01-runs` was
snapshotted before and restored after (66 created dirs removed, diff clean).
Probe scripts live in `/tmp/opencode` and are not part of the commit.

Committed gates rerun by hand on my stores (never trusted as summaries):

- `tests/test_invc1_lifecycle.py`: 8 passed on `inv_rr_v2_c1`.
- `tests/test_invc2_authority.py`: 4 passed on `inv_rr_v2_c2` / `inv_rr_v2_c2b`.
- `tests/test_invd2_settle.py`: 3 passed on `inv_rr_v2_d2`.
- `tests/test_invd3_envelope.py`: 4 passed, 1 deselected (the B3 case needs its
  own fixed store name; I staged B3 separately on `inv_rr_v2_b3`).
- `tests/test_inv_c_qualification.py`: 9 passed on `inv_rr_v2_qual` /
  `inv_rr_v2_qual2`, including both renamed C7 gates.

## Own CLI runs (invented cases, not the implementers')

Smoke `inv_rr_v2_smoke`: one development boundary retained, 2 model calls,
export written. Independent method `inv_rr_v2_mine`: my own single-scan source
retained with byte-identical `method_source` and `authored false`.

B3 `inv_rr_v2_b3`: real CLI `run` with no grant exits 2, stderr names explicit
caller agenda authority, row counts 0 operations, 0 receipts, 0 allocations.

Correction `inv_rr_v2_corr`: invented-basis proposal then same-target
correction. Learner op `-c1` prompt (1998 chars) carries `PRIOR FAILURE` with
the invented-basis reason; episode retained with 3 model calls. Export from
this run drove all replay probes.

Exhaustion `inv_rr_v2_exh`: grant 1000 refuses the 2560 learner call with zero
writes. Same store at grant 2560 admits the learner (1 call) then rejects the
episode: construction needs 16384 parent authority with 2550 free, zero
construction operations.

N1 `inv_rr_v2_n1` (new refusal/exhaustion case): stubborn invalid basis
exhausts the budget, no-candidate with 3 learner ops. Fresh-process `resume`
returns the same reason with zero new operations, receipts and allocations.

N2 `inv_rr_v2_n2` (new interruption case): provider double sleeps through the
construction init call. Staged `dispatching` with zero receipts, SIGKILL the
process group, resume in a fresh process. Result: boundary `rejected`
(construction call left no settled response), zero resume gateway calls, the
killed op stays `dispatching`, its 3244-unit reservation stays `reserved`.
Filed as INV-N2.

C1 rerun `inv_rr_v2_kill3` (real staged kill, first-attempt hit): validation op
`dispatching`, 0 receipts, 0 new launcher files at SIGKILL. Resume identical
to control across disposition, model/construction calls, per-campaign op ids,
op states and receipt ids, with no repair ops. A first harness version compared
vacuously (normalization before filtering); fixed to filter before normalizing
and rerun clean.

C1B `inv_rr_v2_killb` (second M3 point): kill after the validation success
receipt with no settled boundary. Resume identical to control on the same
full comparison.

M5 probes against my own export: exact-prefix replay supported with the three
recorded result identities; hidden-future, new-code-bytes and version-mismatch
probes unsupported with empty results; malformed probe refused. `cli recompute`
matches the run. Post-hoc `cli export` reproduces the run-time packet digest
exactly when caps match (max_boundaries 1); with default caps (6) the
remaining-budgets field diverges. Filed as INV-N3 (P3 observation).

M6 `inv_rr_v2_study`: replicated the `run_study` flow call-for-call on my
store (the script entry refuses non `inv_c3_` names with rc 2, observed).
6 trajectories, 24 protected use records, 6 empty-use records all incumbent,
byte chains clean at every trajectory and use step, totals 39 model calls and
12 construction calls within caps, cap sheet mechanically clean. The script's
own `--recompute` exits 0 with matching 39/12/790/24 totals. External
requirements report presence only with no secret values.

## Cleanup

All 16 `inv_rr_v2_*` databases dropped; none remain. `.ad01-runs` restored to
the pre-review snapshot. Only the two owned files are added to the worktree.
