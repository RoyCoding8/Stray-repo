# Lane A6 — migrate the no-authority callers onto real authority

Branch `wt/a6-callers`, base `450a988`. Diff touches ten production files,
four inherited test files, and one new test file of my own. Nothing under
`reports/evidence/` was written.

A2 deleted the `dsn is None` branch in `method_exec.py` that executed
policy source through `launcher.dispatch` directly. That was right: no
source file becomes trusted merely because it is local. The consequence was
twelve failing tests, and each one named a real caller that had been
relying on that local trust.

There is no carve-out here. No `untrusted=` flag, no
`_run_diagnostic_untrusted`, no second entry point. Every caller below
either holds a real dsn, allocation and operation id, or no longer executes
policy source at all.

## Gate

    wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims;
    export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/a6.jsonl;
    cd /mnt/d/AI/Agent-Society-v2/.worktrees/a6-callers &&
    PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a6-callers/src
    timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest
    tests/test_inv_a6_caller_migration.py tests/test_s89a1_contract.py
    tests/test_invc1_method_envelope.py
    tests/test_construction_response_envelope.py
    tests/test_staging_fidelity_crlf.py -q -p no:cacheprovider'

    41 passed in 56.71s (0:00:56)

Base for comparison, same four inherited files with none of my changes
stashed in: `13 failed, 19 passed`.

## Per-caller disposition

Ten production files. Nine gained real authority, one already held it.

| Caller | Disposition | Authority it now holds |
|---|---|---|
| `records.py` `_execute_assessment` | authority-given | the proposal's own `allocation_id`, read off the stored proposal; operation id `attempt_id + task_id` |
| `assessment_profile.py` `_resolve_method` | authority-given | `dispatch`'s dsn and allocation, plus a minted operation id per profile/session/step/kind |
| `assessment_profile.py` `_shared_assessment_arm` | authority-given | same, with `session-step-k<N>` for the policy step, distinct from the member id |
| `policy_assess.py` `_candidate_from_action` | authority-given | the assessing arm's dsn and allocation; `attempt_id + task_id + role + k<N>` |
| `policy_assess.py` `_run_arm` | authority-given | same, threaded from `assess_policy`, which now takes `allocation_id` |
| `learner.py` `_action_of` | authority-given | an explicit `authority` argument; a side suffix per arm so the two comparisons are two operations |
| `experience_axis_run.py` `_step_policy` | authority-given | the run's own allocation, authorized in `main` against its disposable store |
| `s09_causal_proof.py` `_replay` | authority-given | `PolicyRun.dsn` / `allocation_id`, operation id derived from bytes and view digest |
| `s09_study_preflight.py` `qualification` | authority-given | a disposable database created and dropped around the check, so the study's store is still untouched |
| `s09_m2_reload_proof.py` | authority-given | a disposable store around the fresh subprocess; the dsn and allocation go in the spec file, not the environment |
| `scripts/s89_diagnose.py` `current_tree_execute` | authority-given | a disposable store around the reruns; `--no-rerun` classifies without executing |
| `trajectory.py` `dev_episode` | authority-given | `_dev_episode_authority`, per boundary, from the journal |
| `construct.py`, `s09_m3_pilot.py`, `agenda_policy.py`, `policy_step.py` | unchanged, already held authority | verified by reading, not migrated |

Nine migrated, four verified-already-holding, thirteen files total.

Two callers report a refusal rather than a decision when they have no
store: `records._execute_assessment` returns `outcome: reject` with the
reason, and `dev_episode` returns `disposition: rejected`. Both are tested.
A caller that swallowed the refusal and reported "no reduction" would be
claiming a method ran when none did.

### Three callers A2's list missed

A2 enumerated the callers from grep. My census parses each module with
`ast` and found three more that reach an executor and had no disposition:

- `experiments/ad01/agenda_policy.py` — already carried the campaign's dsn
  and allocation; passes `operation_id=None` without a dsn, which the
  executor refuses. Correct already.
- `experiments/ad01/construct.py` — already passed all three.
- `experiments/ad01/s09_m3_pilot.py` — already passed all three.
- `experiments/ad01/policy_step.py` — `run_policy_step` and
  `BoundedPolicy.run` forward what they are given; `BoundedPolicy.__call__`
  passes none and so refuses.

The census test fails on an unlisted caller, so the next lane's list is a
census rather than a grep.

## The malformed-envelope expectation, and why it is not a weakening

`tests/test_s89a1_contract.py::test_malformed_envelope_rejected` asserted
`'malformed' in str(exc)`. A2's warning was to update the expectation to
the new correct refusal and not to weaken the assertion into a tautology.

Under real authority the change in behaviour is not just a different
string. A member returning the bare task no longer fails at the host's
parse step. The child runs, records a typed error, and the operation
settles on that error. So the executor's own refusal is generic:

    refused: durable child operation has no successful receipt

The structured reason now lives in the settled receipt, not in the raised
message. The test asserts both, and neither half is trivially true:

    assert refusal == "refused: durable child operation has no successful receipt"
    recorded = _child_error(authority["dsn"], operation_id)
    assert recorded.startswith("malformed-result-envelope")

The second line reads the receipt back through
`store.operation_receipts` and requires the child's own recorded reason to
be the envelope refusal. Without it the test would pass if the bytes were
refused for any unrelated reason. With it, the test fails if the executor
stops surfacing the envelope contract, and fails if the bytes never reach a
child.

`tests/test_invc1_method_envelope.py::test_malformed_envelope_reports_structured_reason`
was asserting `match="malformed-result-envelope"` against the raise. It had
to change, because the raise no longer carries that string. It asserts the
same refusal literal and then reads the same receipt field, so it lost no
specificity: it now checks a string that is exact rather than a substring
that would also match the old one.

## What else moved, and why

**The four gate test files now hold real authority.** Each takes a module
fixture that creates a disposable database, authorizes a campaign against
it, and mints a fresh operation id per execution. Fresh ids matter: a shared
one would make the second test replay the first test's settled receipt and
report a result no test executed.

`tests/test_staging_fidelity_crlf.py` needed the same treatment for a
subtler reason. It captured staged bytes at `_stage_text` and asserted
`"driver.py" in child.staged`. Without authority the executor refuses
before staging anything, so the assertion was failing on the refusal and
measuring nothing. It now holds authority, still replaces the child with
`_NoChild`, and therefore still executes no candidate code.

**One inherited failure was environmental, and I repaired the invocation
rather than the assertion.**
`test_gitattributes_pins_every_content_hashed_tree_to_lf` failed because a
linked worktree's `.git` is a file holding `D:/AI/...`, which git under WSL
on `/mnt/d` cannot resolve. The command died with exit 128 before reading
an attribute. The assertion is sound; I translated the drive letter to its
mount point and passed `--git-dir` / `--work-tree` explicitly. The
attributes asserted are identical either way.

**`s09_m2_reload_proof.py` and `s09_causal_proof.py` both claimed "no
store" in their own docstrings**, justifying it with the branch A2 deleted.
Both now name a real disposable store. In both cases that is a stronger
claim than the one it replaced: a disposable store created and dropped
around the proof is separate from live by construction, and it is obtained
by actually executing rather than by declining to run the bytes at all.

## Not fixed, and not mine

Six failures in `tests/test_inv_r1_authored_control.py` and
`tests/test_invd3_envelope.py` are A2's damage at my base. Same six ids
fail with all my changes stashed. Both files are outside my ownership.

`tests/test_s09cs02_causal_proof.py::test_a_digest_copied_onto_a_record_never_qualifies_launch_either`
fails because its `PolicyRun` carries no store, and the qualification now
needs one. I probed the fix: the same run with a dsn and allocation returns
`proven` with both links intact. The test file is outside my ownership, so
I did not edit it.

`tests/test_s09c2b_bind.py` and `tests/test_s09m34_bind.py` report nine
failures. Identical nine at base with my changes stashed, so my
`records.py` change caused none of them.

## What the new test proves

`tests/test_inv_a6_caller_migration.py`, nine tests. The load-bearing one is
the census, which walks `experiments/` and `scripts/` with `ast` and finds
every call to the four public entry points, so it fails on a new call site
and not only on a change to a known one. It found three callers A2's grep
missed.

- `test_the_census_reaches_every_executor_call_site` — the census is not
  silently empty, and names each module this lane migrated.
- `test_every_migrated_caller_is_named_with_a_disposition` — every caller
  reaching an executor is authority-given, pass-through, or owned by
  another lane. No caller is unlisted.
- `test_no_production_caller_hands_the_executor_an_empty_authority` — all
  five incomplete authority combinations are refused with the exact literal.
- `test_the_substitution_gate_refuses_without_authority` and
  `test_the_substitution_gate_reads_its_evidence_under_authority` — the
  refusal, and the positive control that a policy reading its evidence
  moves while a blind one does not. The refusal alone would be satisfiable
  by refusing everything.
- `test_a_caller_with_authority_leaves_a_settled_receipt` — the same bytes
  through the same public entry, asserting a settled operation row joined
  to its receipt in the real database. Every refusal assertion in the file
  is satisfiable by a broken executor; this one is not.
- `test_the_assessment_records_a_refusal_rather_than_a_decision` and
  `test_the_diagnostic_diagnostic_refuses_rather_than_reporting_a_verdict`
  — the two no-store callers report the refusal as their own outcome.
- `test_the_reload_proof_runs_under_its_own_authority` — the reload
  subprocess is given the proof's store and allocation.

## TDD

The census tests were red before the migration and named their caller:
`agenda_policy.py`, `construct.py`, `s09_m3_pilot.py` and `policy_step.py`
each failed with "reaches an executor and has no disposition named in this
gate". The four gate files were red at `13 failed, 19 passed`. Both were
watched fail before the fix.