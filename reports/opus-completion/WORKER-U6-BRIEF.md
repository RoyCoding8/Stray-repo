# Worker brief U6: export and offline verification of policy assessment and binding

Repository `D:\AI\Agent-Society-v2-investigation-review`, branch `codex/stage-09-opus-completion`
at `c3e8566`. Clean tree. Work in place.

You own exactly these files:

- `experiments/ad01/records.py`
- `scripts/s09_verify.py`
- `tests/test_s09o_export.py` (new)

Do not edit `trajectory.py`, `policy_assess.py`, `policy_step.py`, `selection.py`,
`agenda_policy.py`, `cli.py`, or any existing test. If one of them must change, STOP and
report exactly what and why instead of editing it.

## The defect

`records.export_campaign` (`records.py:258-423`) and `records.verify_campaign`
(`records.py:626-766`) predate the policy revision cycle. Neither exports nor verifies the
policy source bytes, the policy artifact fields, the frozen candidate, the sealed panel,
the frozen comparison rule, the executed STEP decisions, the per-arm quality and resources,
the assessment outcome, or the `capability_releases` binding row. `verify_byte_chain`
(`records.py:447-548`) verifies retained TASK-METHOD bytes only, through
`method_exec.verify_member`.

Policy fields reach the export today only by accident, because `export_campaign` copies the
episode dict, which happens to contain `proposal_id`, `policy_candidate` and `freeze`.

Consequence: a reviewer cannot independently confirm that the policy was assessed on its
executed behaviour or that only the exact assessed bytes were activated. That is C6's
offline recomputation requirement, and it is currently unmet.

## Read first, in full

`experiments/ad01/policy_assess.py` for the assessment record shape.
`experiments/ad01/trajectory.py` lines 734-943 for what the revision episode now carries and
how a bound policy is resolved. `experiments/ad01/selection.py` for the release row and
`binding_provenance`. `tests/test_s09o_cycle.py` and `tests/test_s09o_causal.py` for the
fixture style and the durable fields they already read.

## Part 1: export

Add a dedicated policy section to `export_campaign`. Do not rely on the incidental episode
copy. The export must carry, explicitly:

- the policy source bytes, its SHA-256, and the policy artifact fields: kind, entry, ABI,
  origin, parent_digest, applicability
- the freeze record: proposal id, candidate digest, entry, byte count
- the proposal: id, parent digest, scope, protocol id
- the sealed panel: panel id, ordered task ids, panel digest
- the frozen comparison rule: rule id and every threshold it contains
- the assessment: attempt id, outcome, reason, protocol id, evaluator version, scope
- per arm, for the incumbent AND the candidate: the ordered executed action-kind sequence,
  the per-step returned state digest, the effects with their accepted flag, the quality
  counts, the resource counts, and the produced task output per panel task
- the release binding row: release id, versions, scope, disposition, protocol id,
  evaluator version, evidence refs, and the invalidation provenance
- for a rejected or unavailable revision, the durable refusal record, so absence of a
  release is itself evidenced rather than merely observed

Never export a sealed or protected value. Digests, counts, ids and task outputs only. A
task output is the policy's produced artifact, not the task's hidden answer.

## Part 2: offline verification

Extend `scripts/s09_verify.py` and `records.verify_campaign` so the checks below run with
NO provider and NO live database. The committed frozen task corpus may be read; it is
deterministic offline data, not runtime output. Each failed check must name the check id
and the specific field that failed.

V1. Recompute SHA-256 of the exported policy source; require equality with the exported
candidate digest, the freeze candidate digest, and the binding provenance digest.

V2. Re-verify the exported artifact offline: kind `learning-policy`, entry `STEP`, declared
ABI, parent digest, applicability equal to the proposal scope.

V3. Re-run the static STEP source validation offline, without executing the source.

V4. Require the panel and rule freeze to be recorded at an earlier journal position than
every executed assessment step, so freeze-before-exposure is checkable from the export.

V5a. Do NOT simply re-apply the rule to runtime-supplied counts; that is circular.
Recompute the quality counts from the frozen corpus by re-running the deterministic checker
and size measure on the exported per-task outputs. Require the recomputed preserved and
reduced counts to equal the exported per-arm quality. Then re-apply the exported frozen
rule to the RECOMPUTED counts and require the resulting outcome to equal the recorded
outcome.

V6. Require both arms to carry non-zero `step_calls` and a decisions list whose length
equals `step_calls`.

V7. Require the binding row to cite the assessment attempt id in its evidence refs, with
protocol, evaluator version and scope equal to the assessment's.

V8. Require every exported use record carrying a release id to either name an executed
source digest equal to the bound candidate digest, or carry a non-empty `fallback_reason`.
A present-but-empty reason string must FAIL. This is what makes a fallback execution
impossible to hide.

V9a. Load the panel tasks' sealed and protected values from the frozen corpus, then require
that none of those literal values appears anywhere in the serialized export, at any depth,
under any key. Keep a key-name check as a cheap extra guard, but the value check is the
binding one. A key-name check alone is not adequate, because a leaked answer can appear as
a plain value under an innocuous key.

V10. Require the exported panel task ids to be disjoint from the exported development task
ids and from the campaign's own task list.

V11. Require the incumbent arm and the candidate arm to carry the identical ordered panel
task id list, equal to the frozen panel task ids, and to name the same rule id and
evaluator version. Require the incumbent arm to carry its own non-zero `step_calls` and its
own outputs recomputable under V5a. A verdict whose incumbent arm has an empty or differing
panel, or zero executed steps, MUST fail. This is what makes a comparison against nothing
detectable.

V12. Require the per-arm action-kind sequence length to equal `step_calls` and the exported
effects to be consistent with that sequence. Export both arms' sequences whenever the
outcome is bind. Do NOT require the two sequences to differ; a policy may legitimately bind
on resource cost with the same action sequence.

State explicitly, in a docstring or in the verifier's own output, that resource
measurements (step calls, model calls, queries, child wall time) are attested by the
runtime and cannot be recomputed offline, whereas byte identity, artifact conformance,
quality and leakage are independently recomputable. Do not overstate what the verifier
proves.

## Part 3: tests

`tests/test_s09o_export.py`. Own only database names beginning `s09o_export`. Never touch
`ec02test_*`, `inv_*`, or an `s09_*` database you did not create. Note
`tests/test_ad01_traj.py` has 5 pre-existing errors from a missing `ec02test_adtr`
database owned by another task; ignore it.

Drive the export from the PUBLIC path, through `trajectory.run_campaign`. Do not hand-build
an export dict for the happy path.

Required cases, each asserting literal expected values:

1. A successful bound cycle exports every field listed in Part 1, and offline verification
   passes with no provider and no live database. Prove the no-database part by running the
   verifier in a SEPARATE OS process with the database stopped or simply unreachable, or by
   passing it only the exported file path and asserting it opens no connection.
2. Verification FAILS, naming the check, for each of these mutations applied to a valid
   exported file. Write these as a data-driven table, one case per mutation:
   - a single byte changed in the exported policy source (V1)
   - the artifact entry changed from `STEP` (V2)
   - the incumbent arm's panel task list truncated (V11)
   - the incumbent arm's `step_calls` set to 0 (V11)
   - a per-arm quality count altered away from what the outputs recompute to (V5a)
   - the recorded outcome flipped from reject to bind while counts stay the same (V5a)
   - a use record's executed digest changed with `fallback_reason` left empty (V8)
   - a panel task's sealed answer inserted into an innocuously named export field (V9a)
   - the decisions list length made unequal to `step_calls` (V12)
   - the binding evidence refs no longer citing the assessment attempt id (V7)
3. A rejected cycle exports the durable refusal and no release, and verification passes.
4. An unavailable cycle likewise, and its export is distinguishable from a rejected one.

Each mutation test must assert that verification fails AND that the reported reason names
the right check. A test that only asserts "it failed" is too weak.

## Verification you must run and report

```
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh u6-export tests/test_s09o_export.py
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh u6-regress tests/test_s09c1_continuity.py tests/test_s09c1_failure.py tests/test_s09c2a_actions.py tests/test_s09c2b_bind.py tests/test_s09c3_policy_pilot.py tests/test_s09m1_driver.py tests/test_s09m1_state.py tests/test_s09m2_construct.py tests/test_s09m2_policy.py tests/test_s09m34_bind.py tests/test_s09m34_cycle.py tests/test_s09m34_exposure.py tests/test_s09m34_visibility.py tests/test_s09m5_pilot.py tests/test_s09m6fix_bind.py tests/test_s09o_boundary.py tests/test_s09o_policy_assess.py tests/test_s09o_cycle.py tests/test_s09o_causal.py
```

The regression run currently stands at 109 passed and must stay at 109 passed plus your new
tests. It takes roughly 6 minutes. Let it finish; a stream timeout is not a failure. Report
exact pass, fail, skip and error counts for both commands, plus a red result from before
your change for at least cases 1 and 2.

Do not invert an assertion, weaken a runtime check, or delete a test to reach green.

## Style

No inline comments. Compact functions, data-driven repeated structure for the mutation
table, no abstraction layer with a single caller. Match surrounding formatting.
