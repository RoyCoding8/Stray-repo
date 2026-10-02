# c3-fixture — the E4 verdict-shape fixture, repaired against the enforced freeze

Lane C3. Branch `wt/c3-fixture`, forked from `dd81e3e`. Gate: real
PostgreSQL under WSL as `ubuntu`, fixture gateway only, no network, no live
model call.

## The premise, verified rather than assumed

The coordinator's reading of `_probe_step` is **correct, and so is C2's**.
Measured:

```
classify_revision(_probe_step("view['experience'][0]['x']"), views=[view])
  -> {'eligibility': 'changes-an-unauthorised-decision',
      'reason': 'revision changed the step-skeleton, and the only change
                 it is authorised to make is the probe-input'}
```

`_probe_step` hand-writes a whole STEP program. It reads
`view['task_content']['task_id']`, branches on `state.get('done')` rather
than a step counter, and emits a single flat action, so it differs from the
incumbent at the allocation, the construction branch, the target and the
skeleton. `classify_revision` blanks the value bound to `x` and compares
the ASTs; with `x` blanked the two programs still differ everywhere, so the
freeze refuses. **That refusal is correct.** The test's claim is worth
keeping; its fixture was a different program.

## The repair

New helper `_admitted_step` in `tests/test_s09_e4_channel.py` returns
`channel._revision_source('view["experience"][0]["x"]')` — the incumbent
with its probed input replaced and nothing else. Measured:

```
unauthorised_change(IMPROVE_LOW_SOURCE, _admitted_step())  -> {}
classify_revision(_admitted_step(), views=[view])           -> eligible
```

`{}` is the freeze's own verdict that nothing outside the probed input
moved, so this is the authorised kind rather than a lookalike. It is built
through the module's builder rather than by string surgery here, so the
fixture cannot drift from the incumbent it claims to differ from.

Two other tests in that file used the same hand-written program for their
**admitted** half. They were red at base for the unrelated execution
reason, but pointed at `_probe_step` they now die on `KeyError`
`selected_evidence` *before* reaching the payload they are about. They use
`_admitted_step` and fail again at the original assertion `[[]] == [[2]]`.

`informs_decision is True` was removed from
`test_a_data_dependent_input_is_admitted_as_eligible`. It is derived from
`selected_evidence`, measured by executing the revision, and
`method_exec.run_step_out_of_process` refuses a policy source with no
execution authority (`MethodExecutionError: refused: execution needs
explicit authority and identity`). Measured: it is **False for every
revision** in this environment, admitted or not. Asserting True would
assert a measurement this gate cannot make. The claim belongs to the first
consumer that can execute.

**The freeze is untouched.** No production file is in the diff.

## The regression test that stops this happening again

New `tests/test_inv_c3_fixture_repair.py`, 12 tests, all passing.

1. The authorised change is admitted on its own account, asserted
   positively — a guard that refused everything would also pass a file of
   refusals and leave milestone C with no live experiment.
2. Both verdict shapes from one test, asserted as literals: admitted has
   `selected_evidence` and **no** `reason`; refused has `reason` and **no**
   `selected_evidence`. A verdict carrying both keys fails.
3. All six unauthorised variants still refused, each naming the decision it
   moved (`probe-allocation` ×2, `candidate-construction` ×2, `probe-target`,
   `step-skeleton`). Each is derived from this file's own `_admitted_step()`
   rather than imported from C2's baseline, and the anchor is asserted to be
   present, so a future repair that loosened the freeze fails here even if
   it left the first test green.

## Failure split, measured at both ends

The pre-C2 base `35ba5e9` was extracted to a scratch directory and run
against the same two files with the same gate.

| test | at `35ba5e9` | at `dd81e3e` | at HEAD |
|---|---|---|---|
| `test_s09_e4_channel.py::test_a_refusal_carries_a_reason_and_an_admission_does_not` | pass | **FAIL — C2's doing** | **pass** |
| `test_s09_e4_channel.py::test_a_data_dependent_input_is_admitted_as_eligible` | fail | fail | **pass** |
| `test_s09_e4_channel.py::test_an_admitted_revision_really_selects_evidence` | fail | fail | fail (unchanged) |
| `test_s09rev_boundary.py::test_the_probe_reaches_a_built_descendant` | fail | fail | fail (unchanged) |
| `test_s09rev_boundary.py::test_the_decision_actually_flips_on_a_real_task` | fail | fail | fail (unchanged) |
| `test_s09rev_boundary.py::test_delegation_to_the_unchanged_reducer_is_ineligible` | fail | fail | fail (unchanged) |

Base totals: **5 failed, 35 passed**. C2's totals: **6 failed, 34 passed**.
Mine: **4 failed, 48 passed** (12 of the passes are the new file).

**Exactly one failure was C2's doing** — the assigned one — and this lane
repaired it. The other four pre-exist at `35ba5e9` and are all the same
cause, measured rather than repeated from the brief: `method_exec` refuses
to execute a policy source with no execution authority, so every
step-executing test fails identically. Setting `SETTLEMENT_TEST_DSN` does
not help; the E4 driver never threads one.

`tests/test_inv_c2_freeze.py` still reports **20 passed**, which is the
attestation that the freeze was not weakened to get here.

## Verification

Gate (real PostgreSQL 16, WSL, `ubuntu`, one process, scoped):

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims;
export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/c3.jsonl;
cd /mnt/d/AI/Agent-Society-v2/.worktrees/c3-fixture &&
PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/c3-fixture/src timeout 1500
/home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_s09_e4_channel.py tests/test_s09rev_boundary.py \
  tests/test_inv_c3_fixture_repair.py -q -p no:cacheprovider -rf'
```

Result:

```
4 failed, 48 passed in 8.12s
S09ISO: dropped 13 database(s) for this run
```

`git diff --name-only dd81e3e HEAD -- reports/evidence/` is **empty**.
Files changed: `tests/test_s09_e4_channel.py`,
`tests/test_inv_c3_fixture_repair.py`. Working tree clean.

## Undetermined

- **Whether `informs_decision` is ever True.** It cannot be measured in
  this environment, so removing that assertion leaves the claim untested
  rather than established. It belongs to the first consumer that can
  execute a step with authority.
- **Whether the scope check is sound for a computed expression.** C2 named
  this; unchanged by this lane. The comparison is AST equality with `x`
  blanked, so a revision producing the incumbent's shape while differing
  semantically through a computed expression would pass. Not measured here.
- **Whether the four pre-existing failures should be fixed here.** They are
  the execution-authority guard doing its job, and fixing them is lane
  A2's territory, not a fixture repair's.