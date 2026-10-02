# c2-freeze — the declared freeze, enforced, and reviewer-written controls

Lane C2. Branch `wt/c2-freeze`. Base as forked: `35ba5e9` (the assignment
named `e7d0e3f`; see "The fork was not where the assignment said" below).
Gate: real PostgreSQL 16 under WSL as `ubuntu`, fixture gateway only, no
network, no live model call.

## Job 1 — COMPLETE

`classify_revision` now tests "nothing else changed". The premise verified:
`FROZEN_FIELDS` at `improve_channel.py:177` was used at exactly one place
(line 849, in `_attempts_frozen_write`) and `classify_revision` never
referenced it. Five conditions were checked and "and nothing else changed"
was not among them.

### The check

`unauthorised_change(incumbent, revision)` parses both sources, blanks the
value bound to every `x` key on both sides, and compares the resulting ASTs.
There is no threshold and no similarity score: the question is whether the
two programs are the same program once the authorised change is taken away.
Blanking rather than scoring is what makes this an interface check.

`_first_difference` walks both ASTs in source order and attributes the
first divergence to a decision via `_SITES`. New refusal reason
`INELIGIBLE_OUT_OF_SCOPE = "changes-an-unauthorised-decision"`, added to
`INELIGIBILITY_REASONS`. `mutates-frozen-field` is untouched and still means
exactly one thing: a write to a declared frozen field. A revision that
rewrites the construction branch writes no frozen field at all, so
overloading that reason would have told a reader it touched the grant or the
evaluator when it did not.

The check runs after the two gates that need no scope question (emits-probe,
x-is-data-dependent) and before the delegation gate, which executes the
revision. `admit_revision_under_freeze` reads the incumbent off the store's
bound package via the new `bound_improve_source`, so a revision is judged
against the program it would actually replace rather than a constant.

### The six variants from w4-e4-interface.md §4

Measured before the change, all five that reach a verdict were `eligible`.
Now:

| variant | reason |
|---|---|
| asks 8 queries/8 steps | `changes-an-unauthorised-decision` / `probe-allocation` |
| asks 0 queries/0 steps | `changes-an-unauthorised-decision` / `probe-allocation` |
| candidate ctor forced high | `changes-an-unauthorised-decision` / `candidate-construction` |
| construction decision rewritten | `changes-an-unauthorised-decision` / `candidate-construction` |
| probe target rewritten | `changes-an-unauthorised-decision` / `probe-target` |
| never probes; jumps to construct | `no-boundary-action` |

The sixth is refused for a stronger reason than the freeze. Replacing the
probe removes the boundary entirely, so `no-boundary-action` — "revision
never selects diagnostic evidence" — is the accurate report and naming a
scope breach would overstate what the freeze contributed. The ordering is
pinned in its own test so it is not accidental. All six are ineligible;
the reasons differ.

### The authorised kind is still eligible

Asserted positively, not implied:
`_revision_source('3 if not view["experience"] else 8')` returns `eligible`
with a non-empty `selected_evidence`. All four authored controls also
classify as `eligible`, checked against the module rather than a fixture.
The freeze is not satisfied by refusing everything; milestone C keeps its
live experiment.

### An incidental finding

`_revision_source("8")` on its own names a fixed input, so it is refused as
`task-solver-not-decision` before any scope question is reached. The audit's
base ran the same view read every authored control uses. Without that, the
six fixtures would have been testing the wrong gate. The test file builds
its baseline through `channel_controls._selector` and says why.

## Job 2 — COMPLETE

### Independently written controls

New `experiments/ad01/channel_controls.py` (383 lines) owns all four
builders, moved out of `learner_revision.py` (195 lines deleted). It imports
the channel for the incumbent's bytes, the instrument's range and the
descendant metric, and writes every control itself. It adds no second
eligibility rule, no second evaluator and no second metric: a control is
graded by `improve_channel.evaluate_descendants` and
`descendant_delta`, so it cannot flatter the mechanism it qualifies.

`learner_revision` re-exports `CONTROL_BUILDERS`, `AUTHORED`,
`REVIEWER_X`, `DISCONNECT_X` and `build_control` at the header, so the run's
own arm loop and the tests naming `lr.build_control` keep one source of
truth rather than two that can drift.

The reviewer module also builds its own package for a control rather than
borrowing `learner_revision.revision_package`, so a control cannot fail
where the mechanism fails.

### The bookkeeping mismatch

`improve_channel.CONTROL_ROLES` still names the three mandatory roles and is
still what `qualify_apparatus` iterates for the verdict. The declaration of
everything written is now `WRITTEN_CONTROL_ROLES`, which names four. The
registry and the declaration are checked against each other in the tests
rather than as counts, because a count passes when one control is renamed
and another is added.

`qualify_apparatus` gained `additional_checks`. A fourth control that was
driven and reports the wrong effect unqualifies the apparatus; a fourth that
was never driven does not. That asymmetry is deliberate and tested: the
immutable E4 artifact at `reports/evidence/inv_r1_e4/result.json` records
exactly three controls, and requiring four would misread that history as an
incomplete run.

### The load-bearing property is preserved

`disconnect-bytes` still differs from the incumbent in source digest, is
still admitted, and still changes no decision — its only difference from the
incumbent is the expression bound to the probed input, which is the change
the interface names. That is why it survives the new scope check, and the
survival is now a stated fact rather than a lucky escape. Its docstring is
corrected: it previously claimed it passed because "the bytes are not the
incumbent verbatim", which was a weaker and different claim.

Two tests drive it: one asserts it still separates different bytes from the
same behaviour, one asserts an arm reporting a change unqualifies.

## Tests

`tests/test_inv_c2_freeze.py`, 20 tests, all passing. Coverage required by
the assignment:

1. each of the six variants is ineligible with a literal reason naming the
   change — six parametrised cases plus the boundary case;
2. the authorised kind is eligible — asserted positively, twice (the named
   revision and all four controls);
3. the effectful control changes an acquisition decision — driven from
   identical starting conditions against the incumbent;
4. the no-op changes nothing — names 3, is not refused, delta exactly 0.0;
5. the disconnect is refused — `refused_by_instrument`, `x_probed == -1`, and
   the refusal names the range `0..15`;
6. every written control is reachable from `WRITTEN_CONTROL_ROLES`, registry
   equals declaration, and the three mandatory roles are a strict subset.

Controls that execute a step need execution authority:
`method_exec.run_step_out_of_process` refuses a policy source with no dsn,
allocation or operation id (closed in `1e0dd44`). `drive_record` therefore
requires `dsn` and `allocation_id` and raises rather than reporting a
measurement it did not make. Tests use the `migrated_db` fixture and seed
one allocation row.

## Known pre-existing conditions, reproduced and not fixed

**26 failures at base, before any edit of mine.** All trace to one cause:
`method_exec.run_step_out_of_process` refuses without a dsn, so every test
that executes a step fails with "execution needs explicit authority and
identity". Setting `SETTLEMENT_TEST_DSN` does not help; the E4 driver never
threads one. Files and counts: `test_s09_e4_qualification.py` 14,
`test_s09rev_boundary.py` 3, `test_s09_learner_revision.py` 5,
`test_s09_e4_remediation.py` 1, `test_s09_e4_channel.py` 2.

The failure ids are listed in the final message. None is in a file I own
except `test_s09rev_boundary.py`, where the 3 failures are the same
execution refusal and are unchanged by this lane.

The named A2-origin and B3-origin failures in the assignment
(`test_inv_r1_authored_control.py`, `test_invd3_envelope.py`,
`test_frontier_atomicity.py`, `test_s09c2b_bind.py`, `test_s09m34_bind.py`)
are outside the scoped gate run here and are untouched by this lane.

## One cross-lane regression, in a file I do not own

`tests/test_s09_e4_channel.py::test_a_refusal_carries_a_reason_and_an_admission_does_not`
was passing at base and now fails.

Cause, measured: that file's `_probe_step` fixture is a hand-written STEP
program that rewrites the whole step skeleton — it reads
`view['task_content']['task_id']`, uses `state.get('done')` instead of a
step counter, and emits a single flat action. Compared to either menu member
with `x` blanked it differs everywhere, so it is now
`changes-an-unauthorised-decision` / `step-skeleton` rather than `eligible`.

The test's own claim is not wrong; its fixture is a different program from
the incumbent. The other two fixtures in that file
(`test_a_data_dependent_input_is_admitted_as_eligible`,
`test_an_admitted_revision_really_selects_evidence`) fail at base for the
unrelated execution reason, so this lane did not break them.

The correct fixture is the real incumbent with a view-dependent `x`, which
classifies `eligible` (measured). I did not edit that file: it is outside my
declared path ownership, and editing another lane's test to accommodate my
change is the thing the standing rule forbids. The coordinator's call.

This is a genuine contract consequence, not a mistake in the freeze: the
freeze says a revision may change the probed input and nothing else, and
that fixture changes the skeleton. The same claim stated on the real
incumbent's bytes passes.

## The fork was not where the assignment said

The worktree forked at `35ba5e9`, not the named `e7d0e3f`. `e7d0e3f` is 2
commits ahead (`bb62fe5`, `e7d0e3f`, lane B11 route probe). Those 5 commits
touch only `experiments/ad01/invr1b11_budget_probe.py`,
`scripts/b11_route_preflight.py`, `tests/test_inv_b11_budget_probe.py`,
`reports/workstreams/b11-probe.md` and two B11 evidence files. None is a
path this lane owns, and none is read by any code here. All work was done
against `35ba5e9`.

`git diff --name-only e7d0e3f HEAD -- reports/evidence/` is therefore NOT
empty, and lists exactly those two B11 files inherited from the base. This
lane's own diff against its fork point is empty for `reports/evidence/`,
and the working tree is clean for that directory.

## Verification

Gate command (seven files, scoped, one process):

```
27 failed, 79 passed
```

26 of the 27 are the pre-existing execution-authority failures listed above.
The 27th is the cross-lane regression named above. `tests/test_inv_c2_freeze.py`
alone: `20 passed`.

Reproduce from the worktree:

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims;
export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/c2.jsonl;
cd /mnt/d/AI/Agent-Society-v2/.worktrees/c2-freeze &&
PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/c2-freeze/src timeout 2400
/home/ubuntu/.venvs/as9/bin/python -m pytest \
tests/test_s09rev_boundary.py tests/test_s09_e4_channel.py \
tests/test_s09_e4_qualification.py tests/test_s09_learner_revision.py \
tests/test_s09_e4_evidence.py tests/test_s09_e4_remediation.py \
tests/test_inv_c2_freeze.py -q -p no:cacheprovider -rf'
```

## Undetermined

- **Whether the frozen interface is now sufficient.** It catches every
  variant measured and every one an auditor would write by hand, but it is a
  structural equality on the AST with the probed input blanked. A revision
  that produced the incumbent's shape while differing semantically through a
  computed expression would pass. Whether such a revision exists is not
  measured.
- **Whether milestone C's live experiment is worth running.** The scope
  check does not widen the reachable evidence, which is still a two-element
  menu (`_STRATEGY_SOURCE`). That is lane L7's work and is untouched here.
  The six-dispatch negative's cause is unchanged.
- **Whether the four controls pass on a host that can execute steps.** The
  26 pre-existing failures mean no control has been driven end to end
  through `drive_improve_round` since the dsn guard landed. The controls are
  driven through `run_improve_step` with real authority here, which reads the
  decision off an executed action but does not build a descendant.