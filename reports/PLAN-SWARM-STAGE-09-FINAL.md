# Final swarm: three independent slices

The handoff asks for the expanded work completed without restarting lanes.
Three items were outstanding and they are independent, so they fan out
rather than serialise. `/swarm` frames, fans out, aggregates, reports.

## Done predicate

Each slice returns `PASS`, `ISSUES`, or `BLOCKED` with evidence, and each
lands a tested module on a file no other worker owns. Integration — wiring
any slice into the shared harness — is mine alone, so two workers never
touch `s09_arm_parity.py`.

## Shape: partition, not a race

Three slices, disjoint files, no shared writes. Not a race: none of these
is a question with one right answer, and racing them would produce three
different modules for the same job.

| slice | owns | question |
|---|---|---|
| E2 scored observable | `s09_e2_scored.py` + its test | can a dependent variable that responds to policy *content* replace the `diagnostic` field that was shown dead? |
| ordering AST | `ordering_ast_policy.py` + its test | can the typed AST express the ordering world's decision, or which cell is missing? |
| ordering graph | `ordering_graph_policy.py` + its test | can the graph executor load and run an ordering graph, and what must the integration owner wire? |

Worktrees: one per worker, from this branch, per `git-worktree-discipline`.

## Why these three together

They are the handoff's open items and nothing else is. E1's parity result
is bounded but one world; the second-world comparison needs executors for
the two typed representations on the ordering world. E2's five contrasts
are void because their observable does not discriminate, which is a
scoring problem, not a sampling one. M4 is not on the list because it is
not a build — it is a decision about what the study claims to measure, and
Jev put that at 0.83 for the researcher.

## Pre-verified premise, so a worker's PASS is checkable

Before dispatch I confirmed the E2 premise holds: two STEP policies
differing only in whether they read the observation verdict produce
*different executed actions* (x: 3→7 versus 3→3) through
`method_exec.run_step_out_of_process`. The dead `diagnostic` field could
not do this. So a scored observable is achievable with existing tools and
no new executor.

## Aggregation rule

Take every slice's report. A slice that reports `BLOCKED` counts as a
result, not a failure — this campaign's most useful outputs have been
refusals, and the handoff requires an inexpressive representation be
demonstrated with a concrete attempted behaviour rather than worked around.
