# L3 — action meaning: one gate, one effect

Lane A3. Branch `wt/a3-action`, commit `589cb9a`, forked from `f03db5b`.

## The decision: (b), keep six kinds and make the profiles agree

I chose (b). `CHECK` does not split, and the two profiles now refuse a
learner-revision proposal for the same reason.

**Why not (a).** The distinction that alters execution is not the kind, it
is the profile. Evidence, measured in this lane:

- `s09_swe_world.py:145,179,428,445` gives `CHECK` a real effect. It is
  `test.run_all`, it runs the public test suite, and it is charged against
  a `test` budget (`s09_swe_world.py:507`). A learner-revision proposal has
  no meaning in that world at all.
- `boolean_active.py:57-86` offers only `probe`, `construct`, `stop`. A
  seventh `CHECK` variant would be a kind with no operation in the Boolean
  world, so an arm written against it would fail there for a naming reason.

So a split would produce a kind that is a real task effect in one world, a
learner-revision proposal in another, and a no-op in a third. That is a
wider contract, not a sharper one.

**Why (b) is the subtraction, not a dodge.** The concrete defect was that
one act produced two effects under one profile name. `assessment_profile`
accepted a `propose_revision` under `ASSESSMENT` and returned a `staged`
payload. `bind_revision` (`assessment_profile.py:581-603`) refuses every
profile except `DEVELOPMENT`, so that stage had no reachable consumer. It
was an effect class nothing could honor, which is the "second effect with
no consumer" the project invariant forbids. Removing it deletes an
authority rather than adding a kind.

**Where staging survives.** Under `DEVELOPMENT`, which is the only profile
with `allow_revision_bind`. The nested-qualification depth bound is still
enforced, now reachable only under that profile, which is the honest place
for a bound that decides whether a revision gets qualified.

**Where the reason lives.** `policy_action.REVISION_NOT_A_TASK_EFFECT`
(`policy_action.py:34-42`). Both `policy_assess.REVISION_REFUSAL_REASON` and
`assessment_profile.REVISION_REFUSAL_REASON` are aliases of that one
constant, so a future edit that changes one spelling is a lint-visible
change to a single name.

## What the new test proves, and what it does not

`tests/test_inv_a_action_meaning.py`, 42 tests. It runs the same logical
action through both **real** executors (`boolean_policy.choose_action` for
STEP, `boolean_ast_policy.choose_action` for typed AST) inside the real
Boolean world, and compares what the world's own record says.

Requirements and the tests that carry them:

| Requirement | Test |
|---|---|
| 1. same admitted-effect class | `test_both_arms_admit_the_same_effect_class_for_every_kind` (6 params) |
| 1b. same observation | `test_both_arms_observe_the_same_thing_for_every_kind` (6 params) |
| 2. same refusal reason on the same malformed input | `test_both_arms_refuse_the_same_malformed_input_for_the_same_reason` (6 params) |
| 2b. that reason is the world's own literal | `test_the_refusal_reason_is_the_one_the_world_states` (6 params) |
| 3. same resource delta | `test_both_arms_spend_the_same_resource_delta_for_every_kind` (6 params) |
| 3b. a refusal spends nothing | `test_a_refused_action_spends_nothing_in_either_arm` (6 params) |
| 4. `propose_revision` refused in both, named | `test_a_propose_revision_under_sealed_assessment_is_refused_in_both_profiles` |
| 4b. the agreement cannot rot | `test_the_two_profiles_cannot_drift_apart_on_that_reason` |
| 4c. the refusal is subtraction, not loss | `test_a_refusal_stages_nothing_and_spends_nothing_in_both`, `test_a_revision_is_staged_only_where_a_bind_would_be_possible` |

**Honest scope limits, stated in the test module docstring.** The Boolean
world offers only `probe`, `construct`, `stop`. Those three are compared on
a real admitted effect and a real observation. `observe`, `use` and `check`
are refused at the world's availability boundary before any payload is read,
so for them the comparison is on the refusal itself: same kind, same input,
same reason from both arms. Where the SWE world gives those kinds real
effects is not claimed here. I did not extend this to the SWE world; that
would be its own lane.

The one measured difference between the arms is the stage label
(`policy-step` versus `ast-policy-step`), which names the bridge that
refused. `test_the_stage_label_names_the_arm_and_never_the_meaning` asserts
that difference explicitly so it is a recorded fact, not a silent gap.

**Measured result.** For all six kinds, both arms produce the same effect
class, the same observation, the same reason and the same resource delta.
The reasons are held as literals, so two arms agreeing on a wrong answer
still fails the suite. Two defects in my own fixture were found and fixed
by running it: reading a later turn as the outcome of the first, and
serializing the STEP source with `json.dumps`, which spells a null pair
`None` in Python and gave the child a `NameError`.

## Tests I changed, and why

`tests/test_m1_shared_executor.py`, two tests, in this commit.

`test_revision_staged_locally_only_trusted_bind` and
`test_nested_qualification_bounded_and_audit_never_promotes` both staged
under `ASSESSMENT` and both encoded the divergent behavior directly. They
now assert the sealed refusal and stage under `DEVELOPMENT`, the profile
the stage was for. Every other assertion in both tests is unchanged,
including all four `bind_revision` outcomes (untrusted, tampered, wrong
scope, bound) and the audit-never-promotes check. No assertion was
weakened; the sealed-refusal assertion is new.

## Gate

Exact command, run in WSL as `ubuntu`:

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/a3-action && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a3-action/src timeout 1800 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_a_action_meaning.py tests/test_s09_vocab_unify.py tests/test_policy_action_contract.py tests/test_s09_arm_parity.py tests/test_s09step_arm.py tests/test_s09_policy_governance.py -q'
```

Result: **`151 passed, 1 warning in 122.26s (0:02:02)`** — zero failures,
zero errors. The warning is a pytest cache-path permission notice on the
Windows-mounted worktree, unrelated to the tests.

TDD was honored. The file was written first and watched fail (6 failures,
including `AttributeError: module 'experiments.ad01.policy_assess' has no
attribute 'REVISION_REFUSAL_REASON'`), then the production change made it
green.

Wider checks, all green: `tests/test_m1_shared_executor.py` (21 passed),
`tests/test_s09o_policy_assess.py`, `tests/test_s09_receipt_readback.py`,
`tests/test_s09c2a_actions.py`, `tests/test_s09_e2_scored.py`,
`tests/test_s09_e4_channel.py`.

## Written down, not done: work outside my owned paths

1. **`/tmp/settlement-claims` is root-owned.** Every bounded child launch
   went through `claim-not-durable` and returned zero results, which made
   19 of my gate's tests fail on a clean tree. The ledger path is
   `launcher_local.py:445-451`, keyed off `tempfile.gettempdir()`. This is
   an environment defect, not a code one, and it is outside my paths. I
   confirmed the launcher is correct once the directory is writable, and
   the failure resolved externally at 01:47 during this lane (the
   directory changed owner to `ubuntu`). A host that runs these gates as
   `ubuntu` with a root-owned `/tmp/settlement-claims` will get 19
   spurious failures.

2. **`scrub_env` strips `TMPDIR`** (`exec_profile.py:105-112`), so a nested
   child reverts to the unwritable default. If a lane needs a writable
   ledger for a nested launch, it must pass `SETTLEMENT_CLAIM_LEDGER`
   through the payload rather than relying on the environment. I did not
   change this, since it is a containment decision and not mine.

3. **`tests/test_m0_plan_claims.py` fails 7 on the clean base.** The
   citation table's verified line `a1f514c` is not an ancestor of `f03db5b`
   (`git merge-base --is-ancestor a1f514c HEAD` exits nonzero), and three
   citations already point at wrong lines on base. My edit shifts two more
   (`policy_action.py:68`→80 for `parse_action`, `policy_assess.py:412`→420
   for `assess_policy`) but the count is 7 before and 7 after, so I add no
   failure. I did **not** re-pin the table: those citations are a
   chain-claim record, and re-pinning them to my own numbers without the
   evidence the record asks for would falsify it. It needs its owner.

4. **`policy_step.py` is shared with lane A2 (a2-nodsn).** I made **no
   changes** to it. The gate and the new test pass without touching it, so
   there is no merge conflict from my side.

## Not done

- The three kinds with no Boolean-world effect (`observe`, `use`, `check`)
  are compared on their refusal only. Proving their admitted effects agree
  needs a world that offers them, which is the SWE world. Out of scope here.
- I did not extend the comparison to the action-graph arm. The assignment
  asked for STEP against typed AST, and R2 exists to answer the
  three-representation question independently.
- No live model calls, no network, no pip. The gate used the fixture
  gateway only.
