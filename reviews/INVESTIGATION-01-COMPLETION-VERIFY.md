# Investigation 01 completion verification

Independent review of `89c2eff659ef011ebb43b2c401738eb0b51b2412` on
`codex/implementation-investigation-01-completion`. The reviewer invented
all four cases below. Every case ran against the real `ad01-traj` CLI on
real Postgres with doubles only at the provider seam. Disposition: the
connected public path is not finished. C2 is merged but its authority and
recovery machinery does not drive the public campaign. C1 and C3 are
unmerged branches.

## Verdicts

M1, integrated lifecycle: unmet. Both domains flow through
`trajectory._run_boundary`, but no shared decision consumer exists to
replace or disconnect. `propose` is a per-call closure and the default
path bypasses `settlement.loop` entirely; the trajectory imports only
allowance arithmetic from it. The rejecting check cannot be staged.

M2, one authority: unmet on the public path. `settlement.authority`
refuses correctly and its tests pass, but the public campaign never calls
it. Construction funds every episode from a fresh parentless allocation,
and a fresh database renews authority for the same campaign. Evidence:
cases D, INV-C2, INV-C3.

M3, feedback and recovery: unmet on the public path. Refusals advance to
the next task with no correction of the same decision. Mid-validation
kill adds spend instead of recovering. Post-validation kill recovers, but
no suite test stages it. Evidence: cases B1, C1, C2, INV-C1, INV-C6.

M4, executable interfaces: unmet. The method return envelope is enforced
by the child driver and absent from the prompt. The renderer, parser and
executor agree only if the author already knows the envelope. C1, which
claims the contract work, is unmerged. Evidence: case A, INV-C4.

M5, trace, export, replay: unmet. No public run export exists on the tip
and no replay consumes one. The replay test drives `settlement.loop`
with hand-built packets. C3, which claims this work, is unmerged.

M6, runnable study: unmet. No study entry exists on the tip. No enforced
cap sheet, no study aggregate, no study deadline. The C3 branch holds
`scripts/inv01_study.py`; it is not merged.

## Findings

INV-C1: resume after a mid-validation kill spends repair plus a fresh
lineage. The killed validation operation rests in `dispatching` with no
receipt. `dispatch_operation` returns early for non-`prepared` rows, so
the resume never relaunches it, scores a validation failure, and retains
lineage 2 with 3 construction calls against a control of lineage 1 with
1 call. Observed on `inv_rev_c`, campaign `ad01-w0-I-10`, control
`ad01-w0-I-11`.

INV-C2: construction ignores remaining parent authority. With the parent
at exactly 0 after the learner call, init, repair and second-lineage
calls were all admitted under a fresh parentless 16384-unit episode
allocation (`_construction_allocation` seeds per episode from
`PROMPT_BUDGET_CHARS // 4` plus output tokens). Observed on `inv_rev_d`:
parent remaining 0, episode allocation consumed 12810.

INV-C3: the same campaign reruns on a fresh database under a new
allocation. Campaign `ad01-w0-I-32` ran `retained` on `inv_rev_d2` with
2 fresh model operations after running on `inv_rev_d`. Reopening storage
renews authority.

INV-C4: the ENTRY return envelope is undocumented. A method returning the
candidate, the prompt's literal reading, passes `verify_member` and dies
in the child with `KeyError: 'candidate'`. Only the `{'candidate': ...}`
form runs. The prompt documents helper return shapes but not the
method's own.

INV-C5: unbilled model calls settle at the full character estimate.
Learner prompt 1746 chars consumed 2485 units while the settled receipt
reports 5 input and 5 output tokens unbilled. `actual_cost` is set only
for billed usage, otherwise settle books the reservation. Internal
charges equal the estimate for every unbilled call even though exact
prompt bytes sit in the same row.

INV-C6: no correction reaches the next request. After an invented-basis
refusal, the following boundary's recorded learner prompt does not
contain the refusal reason. The public path has no bounded correction of
the same decision; the loop-layer correction queue is not connected to
the trajectory.

INV-C7: two suite tests assert the opposite of their names.
`test_cross_database_no_renewal` repeats all gateway calls under a fresh
allocation and passes on equal authorization: reproducibility, not
conservation. `test_kill_resume_reuses_settled_results` starts its
resume subprocess after normal completion: fresh-process reuse, not crash
recovery. Neither would fail for the defects in INV-C1 and INV-C3.

## Qualifying behavior observed

Valid output is admitted and used end to end: independently written
bytes retained and executed byte-identical in fresh-process use.
Protected-use targets refuse pre-effect with zero queries and one
learner receipt. Missing caller authority refuses with exit 2 and zero
durable writes. Post-validation kill resumes with fixed operations,
fixed receipts and unchanged run bytes. Repertoire digest mismatch
refuses at load. These hold, and the milestone verdicts above stand
beside them.
