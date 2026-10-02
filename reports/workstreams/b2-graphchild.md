# B2, a graph arm reaches a world turn

Offline lane. No live model call, no network, no fixture gateway. The
child under test is a real `LocalLauncher` dispatch on this host.

## Verdict first

Both defects were conflations, and that is the whole finding. Each
reported two different facts under one name. The harness called a child
that never started `no receipt`, which is what a reader takes away for a
program that ran and produced nothing. The graph executor called a value
it had read a literal, which is what a record that never read anything
looks like.

| Claim | Before | After |
|---|---|---|
| a graph arm reaches a world turn | no, on any world | yes, on the ordering world, asserted on the action |
| a child that died vs a child that was empty | both `no receipt` | `child-failed` vs `empty`, two refusal texts |
| an action can carry a read value | no, literal only | yes, on the ordering executor |

`tests/test_boolean_graph_policy.py`, named in my gate, **does not exist
in this tree and never has**. `git log --all --diff-filter=ADR` finds
nothing for it. I ran `tests/test_boolean_graph_arm.py`, which is the
Boolean graph executor's test.

## The import path, and why containment is not weakened

`scrub_env` published `PATH` and `LANG` and no import path at all, so a
child could not import the `settlement` package, which lives under
`src/`. It died with `ModuleNotFoundError` before loading a graph.

`package_search_path()` returns `src/`, the parent of the package, read
from `exec_profile.__file__` so a checkout anywhere resolves the same way
without configuration.

**The directory is `src/` and not the repository root, and that is the
containment decision.** The task-id key is `experiments/ad01/worlds.py`
(`TASK_ID_KEY`), and the study worlds publish opaque ids derived from it.
A child whose import path contained the repository root could import the
study package tree, hold the key, and invert a published id back to its
seed. That is exactly the exposure N-36 records, and the launcher
already refuses `read_deny` rather than run unbounded when the kernel
cannot provide it. Publishing the root would have made the protection
present and not applied.

`src/` grants exactly one package, and it is not that one. The test
asserts all three facts against the live value: the path contains
`settlement/__init__.py`, the path does **not** contain `experiments`,
and the path is not the repository root.

The receipt still says `containment=False`, unchanged. This is a bounded
subprocess, and the change does not make it a sandbox. What changed is
which package the launcher hands the child.

The gVisor argv builder drops `PYTHONPATH`. A host `src/` cannot resolve
inside a container, and a caller that mounts the package passes a
container-side mount and sets its own path there.

## A failed import is distinguished from an empty result

Two layers, and neither alone was sufficient.

**The receipt.** `_interpret` in `launcher_local.py` now emits
`parse: "child-failed"` for a nonzero exit. Before, that case fell
through to `parse: "rejected"`, and every caller in the tree reads
`data["worker"]`, found nothing, and reported `no receipt`. The
`returncode` that separated the two states was buried in `data`, so a
caller had to know to look for it, and none of them did.

`child-failed` is **not** narrowed to import errors. A nonzero exit is a
child that ran and did not finish, whatever the reason, and naming one
cause would make `assert` and `abort` read as an import failure. The
stderr carries the reason; the parse token carries the fact. The three
states are now three literals:

| literal | meaning |
|---|---|
| `child-failed` | exited nonzero, no stdout |
| `empty` | exited zero, printed nothing |
| `rejected` | exited zero, printed something that is not the contract |

**The harness.** `_refuse_failed_receipt` in `s09_graph_budget.py` maps
the first two to two different refusal texts:
`child-failed: <stderr>` and `child-ran-and-returned-nothing`. Neither
contains `no receipt`.

The refused receipt carries **no synthesized `worker` envelope**. A
receipt whose child never produced a typed payload must not claim one,
because that would be a claim no worker made.

## The view-read fix

`FIELD_BINDING = "$field"` binds an action input to a view field. The
executor resolves it at turn time in `_resolve_bindings`, before the
world validates the resolved action.

It cannot resolve at load. The load-time view is `World.static_view`, the
view in which nothing has been observed, so a field bound to an
observation has no value there and a value invented for the check would
be one the world never published. The cost is real and I did not hide it:
a bound action is **not** fully validated at load, and `_parse_action`
names the check it defers in a comment rather than skipping it quietly.
The claim about the *field* is still gated at load, by
`_parse_bound_fields`, against the same `World.field_type` table a guard
is gated by, so a record cannot bind `private.tables`.

An unreadable bound field is a refusal naming the field, not a `None`
that the world would then refuse with a message about a missing value.

An action that binds nothing takes the identical path it took before.

## The tests

All in `tests/test_inv_b2_graph_child.py`, 11 tests.

| Test | Proves |
|---|---|
| `test_a_graph_arm_reaches_a_world_turn_through_the_bounded_child` | the real bounded child returns the probe action, inputs and cursor spelled |
| `test_the_launcher_publishes_the_package_directory_and_not_the_root` | `src/` grants one package, not the study tree, not the root |
| `test_the_scrub_still_drops_a_secret_the_import_path_change_carries` | the import path did not widen the environment |
| `test_a_child_that_died_to_import_is_not_reported_as_a_child_that_ran_nothing` | `child-failed` vs `empty`, two real children, no synthesized worker |
| `test_a_child_that_ran_and_printed_a_non_envelope_is_a_third_fact` | `rejected` is the third state, not a synonym for the first |
| `test_the_graph_harness_names_which_of_the_two_it_saw` | the harness maps the two receipts to two different refusal texts |
| `test_two_views_differing_only_in_an_observed_value_now_produce_different_actions` | the anti-disagreement test, literals on both values |
| `test_a_bound_field_the_world_does_not_publish_is_refused_rather_than_guessed` | `observed.9.earlier` is a refusal naming the field |
| `test_a_binding_names_a_field_a_guard_could_not_have_named` | `private.tables` is refused at load |
| `test_a_literal_action_still_loads_and_still_carries_its_literal` | the repair adds a capability, it does not rewrite the old records |
| `test_the_boolean_field_b1s_witness_names_is_not_this_executors_vocabulary` | why the proof sits on the ordering world |

Watched failing first. Seven of the eleven failed before the fix. The
four that passed first were the characterizations, and they were kept
because each is falsifiable: the turn test would fail against the pre-fix
child, and the two literal tests would fail if a binding leaked into a
record that spells a literal.

Two of my own first-draft tests were wrong and the gate caught them. One
drove the harness with a malformed record, but the shipped driver catches
its own load errors and reports a typed envelope, so that never reaches
the state under test. One printed only environment key names and then
asserted on `KEEP_ME=visible`. The second is recorded because a test that
passes for the wrong reason is the failure this project is about.

## Verification

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/b2.jsonl; \
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/b2-graphchild && \
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b2-graphchild/src timeout 1200 \
  /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b2_graph_child.py \
  tests/test_s09_swe_executor_capability.py tests/test_ordering_graph_policy.py \
  tests/test_boolean_graph_arm.py -q -p no:cacheprovider'
```

```
3 failed, 62 passed in 70.68s (0:01:10)
```

The three are the pre-existing capability failures named in my brief. I
verified them on the clean base by stashing my work: identical three, and
**the same `assert 'observe' == 'stop'` symptom**, not the `construct`
my brief recorded. My fix turned none of them green.

A second baseline, measured because I changed `scrub_env` and the receipt
vocabulary: `tests/test_s09step_arm.py` has six failures reading `refused:
execution needs explicit authority and identity`. Verified identical on
the clean base, so pre-existing and not mine. The other five files in
that run passed or skipped.

`git diff --name-only f03db5b HEAD -- reports/evidence/` names one file,
`reports/evidence/invr1b8-panel-census/census.json`. It is **B8's**,
from commit `005a4f7`, which predates my base. My commit touches nothing
under `reports/evidence/`. Flagging it so the coordinator does not read it
as mine.

## The two remaining comparability blockers

**1. The graph driver has no `swe` branch.** `_GRAPH_DRIVER` dispatches
`ordering` to the ordering executor and sends **everything else** to the
Boolean one. `s09_swe_binding.SWE_WORLD` is a real `World` value, so
`choose_action` takes it as a parameter, but nothing hands it to the
child. A SWE graph therefore loads under Boolean rules and is refused
with `stop target must be boolean.task`.

Not mine and not fixable in my paths. `s09_graph_budget.py` is a third
lane's, and adding a `swe` branch means the driver imports
`s09_swe_binding`, which reaches the SWE world and its task fixtures.

**2. The typed-AST arm is refused at turn time** by the frozen Boolean
interpreter's stop-target contract, which wants `boolean.task` where the
SWE arm needs `swe.task`. B1's, unchanged by this lane.

With both repaired, the graph and AST cells become comparable on the SWE
world. Neither is a DSL change and neither touches the notation.

## Records that went stale, recorded not edited

Three files assert the view-read defect is still open. All are outside my
paths, so I did not edit them and am recording them instead.

- `tests/test_inv_b1_swe_view.py:174`,
  `test_a_graph_arm_cannot_act_on_a_value_the_evaluator_read`, asserts
  the two actions are byte-identical. **Now red**, and correctly so: the
  repair inverted the property it was written to guard. It needs to
  become the anti-disagreement test my
  `test_two_views_differing_only_in_an_observed_value_now_produce_different_actions`
  already is.
- `experiments/ad01/s09_swe_ast.py:336`, the `action-graph` witness, says
  `_parse_action` discards the read value. That is now false for the
  ordering executor. Its second half, the `code.localize` load-time
  refusal, is **still true** and is a separate limit.
- `experiments/ad01/s09_swe_experiment.py:39` and `:1069` repeat the
  claim in prose.

## Final process count

Zero for this worktree. `ps` shows one pytest tree, PID 438590 and its
two children, and every path in it is `/mnt/d/AI/Agent-Society-v2/.worktrees/a7-probe`,
which is lane A7's. I did not start it and did not touch it.
