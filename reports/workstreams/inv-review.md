# Workstream: independent review of Investigation 01 completion

Reviewer: independent, not an implementer. Worktree `.worktrees/inv-review`,
branch `wt/inv-review`, from `origin/codex/implementation-investigation-01-completion`.
Reviewed commit `89c2eff659ef011ebb43b2c401738eb0b51b2412`.
Only two files are owned here: this log and
`reviews/INVESTIGATION-01-COMPLETION-VERIFY.md`. No merges performed.

## Baseline

Postgres 16 online. Disposable databases created for this review:
`inv_rev_a`, `inv_rev_b`, `inv_rev_c`, `inv_rev_d`, `inv_rev_d2`.
All review runs used the real `ad01-traj` CLI on real Postgres.
Doubles sat at the provider seam only (`--recordings` scripts through
`RecordingGatewayAdapter`); validation and use ran in the real local child
process launcher. Probe scripts live in `/tmp/opencode/inv-review` and are
not part of the commit.

Existing suites rerun on the reviewed tip before inventing cases:
`tests/test_invc2_authority.py` plus `tests/test_invc2_recovery.py`,
7 passed. `tests/test_inv_c_qualification.py`, 9 passed.

## Case A: valid model output, admitted and used

I wrote my own method from only the delivered construction prompt and
`entry_contract`. The prompt documents entry params, candidate shape,
helper returns and budgets. It never states the ENTRY return envelope.
The natural reading (return the candidate) passes `verify_member` and
fails in the real child with `KeyError: 'candidate'`. The envelope form
(return `{'candidate': ...}`) runs: 16 queries, 14 ops down to 3.

Full path via the real CLI on `inv_rev_a`: development proposal for
`ad01-w0-dev-sw-00` admitted, diagnostic ran, construction retained my
bytes (`method_source` identical, `authored` false), repertoire frozen,
fresh-process `use` on `ad01-w0-within-sw-00` executed my bytes
(`executed_source` identical, verdict preserved, 14 witness queries).
Graph diagnostic via CLI also checked: `ad01-w0-dev-gr-00` inspected.

Suite coverage: `test_entry_drives_learner_and_construction_through_broker`
qualifies this shape in-process with authored fixture bytes plus CLI `use`
with byte identity. My run adds the real CLI `run` binary and
independently written bytes. Verdict: qualified, with the two deltas named.

## Case B: refusals

B1, invalid proposal: invented basis reference on `ad01-w0-dev-sw-00`.
Episode `no-candidate`, reason `invented basis references:
obs-invented-999`, zero construction operations for that boundary. The
next boundary's recorded learner prompt in the operations table does not
contain the refusal reason. There is no same-decision correction on the
public path. Suite coverage: `test_rejected_then_corrected_proposal`
rejects the bad input but its second boundary targets a different task,
so it does not qualify correction feedback either.

B2, unsupported choice: development proposal for protected-use task
`ad01-w0-within-sw-00` on the I arm. Episode `no-candidate`, reason
`protected-use target ... is never a development target`, queries 0,
exactly 1 operation and 1 receipt (the learner call). Refused pre-effect.

B3, missing authority: fresh database, CLI `run` without
`--agenda-authorized`. Exit code 2, stderr `ad01-traj refused: campaign
requires explicit caller agenda authority`, zero operations, zero
receipts, zero allocations. No suite test pins this behavior.

## Case C: interruption

C1, kill during validation: slow method (verified identical logic plus a
bounded spin) on `ad01-w0-I-10`. SIGKILL with the validation operation
present, no receipt, no settled boundary, decision checkpoint present.
Resume in a new process finished `retained`, but construction calls went
1 (uninterrupted control on seq 11) to 3, lineage 1 to 2, model receipts
2 to 4. Root cause: the killed validation operation rests in
`dispatching` with no receipt; `dispatch_operation` returns early for any
non-`prepared` row, so the resume never relaunches it; `read_result`
finds nothing; the interruption is scored as a validation failure and
the run spends repair plus a fresh lineage. The suite never stages this:
`test_kill_resume_reuses_settled_results` resumes after normal completion
and `test_crash_recovery_reuses_diagnostic_and_validation` drives the
`settlement.loop` layer directly, never the public trajectory validation
seam.

C2, kill after validation: SIGSTOP the moment the validation receipt
landed, boundary confirmed absent, then SIGKILL. Resume finished
`retained` with calls 1, operations 3 to 3, receipts 3 to 3, and no byte
change under `.ad01-runs`. The settled-validation path recovers cleanly.
The suite does not test this point either.

## Case D: resource exhaustion

Pilot measured exact exposures: learner 2485 units (1746 prompt chars,
2485 == 1746//4+1+2048), validation sandbox 111, construction init 3177.
D-run with agenda authority exactly 2485: learner admitted, parent
remaining 0 before construction. Construction still spent 4 model calls
(init, repair, second lineage init, and its follow-on) consuming 12810
units of a fresh parentless 16384-unit episode allocation. Repair draws
from the same fresh money, never from the parent. `use` with a repertoire
member under the exhausted parent fell back to incumbent with reason
`refused: allocation ... cannot cover 111`; use never refuses, it
degrades. Same campaign id on a second fresh database with new authority
ran `retained` with 2 fresh model operations: renewal, not refusal.

Suite coverage: `test_exhausted_parent_refuses_init_repair_use` and
`test_same_study_on_fresh_db_refuses_without_renewal` exercise
`settlement.authority`, which the public campaign does not call.
`test_cross_database_no_renewal` reruns the public campaign in a second
database, repeats the gateway calls under a fresh allocation, and passes:
that asserts reproducibility, not conservation.

## Caps, bounds, accounting

No `scripts/inv01_study.py` on the reviewed tip. The CLI accepts only
`max_boundaries`, `agenda_authorized`, tasks, model and recordings: no
token ceilings, no query aggregate, no study deadline. Per-trajectory
caps exist (6 boundaries, 3 dev episodes, 2 lineages, 1 init plus 1
repair each, 60 model calls) but no study aggregate (24 construction,
360 total) is enforced anywhere on the public path. The C3 branch holds
the study entry; it is not merged.

Allocation `consumed` for unbilled model calls equals the full
characters/4 estimate. Measured: learner prompt 1746 chars consumed
2485 units while the settled receipt reports input 5, output 5, unbilled.
Mechanism: `actual_cost` is set only when usage is billed, otherwise
settle books the whole reservation. Estimates, measured usage, internal
charges and billing exist as separate fields, but internal charges
collapse to the estimate for every unbilled call.

## Cleanup

`.ad01-runs` cache removed from the worktree. `inv_rev_a`, `inv_rev_b`,
`inv_rev_c`, `inv_rev_d`, `inv_rev_d2` dropped. The `inv_c2_*` and
`inv_c_qual*` databases used by the existing suites were left in place.
