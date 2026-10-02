# B9, the bounded child names an executor per world

Offline lane. No live model call, no network, no fixture gateway. The
child under test is a real `LocalLauncher` dispatch on this host.

## Ruling

**The driver may import and dispatch the SWE world, and does.** The
containment question B1c deferred turned out not to be the live one. The
child already reached the study package before any branch existed, so the
branch grants no new reach. What the branch changes is which executor a
driver-authored dispatch names, and a silent fall-through is a worse
answer to that than an explicit refusal.

## The premise held, and it moved the question

The brief's claim is measurable rather than arguable, and I measured it on
the **unmodified** driver. `_GRAPH_DRIVER` does `sys.path.insert(0,
sys.argv[1])` with the repository root as that argument. A child holding
only that preamble, no branch, imports the panel and enumerates it:

```
{"experiments.ad01.s09_swe_tasks": "reachable",
 "experiments.ad01.worlds": "reachable",
 "experiments.ad01.s09_swe_binding": "reachable"}
```

and the instance it hands back carries the answers:

```
entry, mechanism, patch, protected_test, public_tests,
reference_source, reference_text, source, source_text,
split, structure, task_id, template
```

`mechanism` is the injected fault and `patch` is the repair. B2's
containment decision was about the *launcher's* `PYTHONPATH`, which is
still `src/` and still does not carry `experiments`. The driver's own
argument is a separate grant, and it is not mine to close. So the branch
adds an import, not a directory, and a test asserts the reach exists so
the ruling's premise cannot be lost silently.

**What changes.** The child gains one import, inside the `swe` branch, and
one dispatch entry. **What does not.** The import path is still
`sys.argv[1]` and nothing else; `src/` is untouched; no new
`PYTHONPATH`; the compute bounds, the staged-record discipline and the
refusal vocabulary are all as they were. The branch is also lazy on
purpose. `s09_swe_binding` builds its observation vocabulary by
enumerating the panel at import, which costs about 1.4s of a 10s CPU
budget, so a Boolean or ordering child should not pay it or hold the
fixtures. The import is inside the branch for that reason alone.

## The dispatch, and the defect it replaces

`else` sent every world without a branch to the Boolean executor, so a
SWE graph was loaded by an executor validating against the Boolean world
and refused as `stop target must be boolean.task`. Reproduced first:

```
REFUSED GraphBudgetRefused graph step failed in child:
  GraphPolicyRefused: node done arm 0 action: stop target must be boolean.task
```

That is the driver's own comment about `ordering` recurring one level up,
and a typo in a world string was reported as a graph the Boolean world
would have refused. Now one entry per world, the name the key, and an
unrecognised name is a refusal naming itself. `GRAPH_WORLDS` is the closed
set, checked in the parent before a child is spawned, so an unbound world
never costs a process.

## A graph arm now reaches an SWE world turn

Through the real bounded child, asserted on the action with its inputs as
literals:

```
{"kind": "construct", "target": "code.inspect", "inputs": {"line": 1}}
```

The record's first guard is `observed.0.kind ne ""`, so reaching the
construct arm is the world having published an observation the guard read.
`test_the_swe_world_admits_the_turn_the_swe_branch_returned` asks
`swe.admits` directly rather than trusting a second copy of what the
executor emits, and the cross-world pair is driven the other way too: a
SWE record on the Boolean child is still refused with `boolean.task`,
which is the evidence that the Boolean executor is the one that ran.

Under `compare_arms` the graph arm now returns a real `ArmRecord` and no
incompatibility at all, where it previously produced
`episode-failed / stop target must be boolean.task`. That is what the two
inherited assertions in `test_inv_b1_swe_view.py` now assert, which is
stronger than what they asserted before: an arm that runs produces a
record, and an arm that is mis-loaded produces neither.

## What the branch did not fix, and the finding

`compare_arms` is still `incomparable`, and the graph cell is still held
back, by something one layer above the executor and neither prior report
named.

`compare_arms` hands every arm a `contract_view`. On this world that
projection carries no `symptom` key, so `project_swe_view` has nothing to
re-publish, the guard is decided against an empty observation table, and
the arm takes its always arm. Measured, same record, same world:

| view handed to the executor | action |
|---|---|
| raw `policy_view()` | `construct` / `code.inspect` |
| `contract_view()` | `stop` / `swe.task` |

So the honest answer to "is comparability one patch away" is no, and it is
worth being precise about why: the graph notation is not what is missing.
A guard over an observed field already reads, already resolves, and
already produces a world-admitted action here. What is missing is a
projection the common harness publishes for a world whose observations
live under `symptom`, and that is a view-contract change in
`s09_arm_parity`, not a notation change and not a new DSL. I did not
build it, because a matrix cell is not a reason to invent machinery, and
the failure is a harness projection with a one-line witness rather than an
expressivity limit of the graph.

The support record now names the surviving blocker and no longer names the
closed one, and both directions are asserted.

## Watched failing, and watched failing for the right reason

| Mutation to production | Result |
|---|---|
| restore the `else` mis-load, drop the `swe` branch | 3 failed |
| keep the branch, gut the `else` refusal message | 1 failed |

The second one is the interesting one. It first passed, which told me the
child's `else` is unreachable through `run_graph_step`, because the
parent's `GRAPH_WORLDS` guard refuses before a child is spawned. Rather
than leave that as a second unexercised authority, the test now asserts
the two hold the same closed set and that the child's refusal still
names itself. Two owners of one fact is a second authority; two owners
whose agreement is checked is a boundary.

## Verification

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; \
  export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/b9.jsonl; \
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/b9-driver && \
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b9-driver/src timeout 1500 \
  /home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_inv_b9_graph_driver.py tests/test_inv_b1_swe_view.py \
  tests/test_inv_b2_graph_child.py tests/test_s09_swe_executor_capability.py \
  tests/test_s09_swe_binding.py tests/test_ordering_graph_policy.py \
  tests/test_boolean_graph_arm.py tests/test_s09_arm_parity.py \
  -q -p no:cacheprovider'
```

```
112 passed in 42.21s
S09ISO: dropped 13 database(s) for this run
```

Blast radius on the dispatch and projection neighbours, run as its own
gate: `tests/test_s09_representation_matrix.py`,
`tests/test_view_contract_swe.py`, `tests/test_s09step_arm.py` gives
`6 failed, 27 passed`, and the six are all of
`test_s09step_arm.py` reading `refused: execution needs explicit
authority and identity`. Reproduced identically on a clean extract of the
base commit `5d3f4be`, so they are pre-existing and none is mine.

The two bind suites named in the brief are unchanged at `9 failed, 42
passed` alongside `tests/test_frontier_atomicity.py`, and the same nine
ids fail on the clean base extract. `test_frontier_atomicity.py` is green,
as A8 left it. Reproduced and recorded, not fixed.

`git diff --name-only 5d3f4be HEAD -- reports/evidence/` is empty.

## What I did not do

I did not build the contract-view projection, so `compare_arms` is still
`incomparable` on this world. I did not add a notation, a DSL or a cell
mechanism to fill the matrix, because the measured failure is a harness
projection and not a graph expressivity limit. I did not touch
`experiments/ad01/ordering_graph_policy.py`, `s09_swe_binding.py` or
`worlds.py`. I did not run a whole-suite sweep, per the resource policy.

## Final process count

Zero. `ps -eo pid,args | grep -c '[p]ytest'` returns 0, and the base
extract I used for the clean-baseline comparison is deleted.

Co-Authored-By: Claude Code <noreply@anthropic.com>
