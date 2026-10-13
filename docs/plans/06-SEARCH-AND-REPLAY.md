# P06. Search history and dreaming

Use accumulated attempts to improve exploration decisions. Depends on [P01](01-INVESTIGATIONS.md), [P02](02-MEMORY.md) and [P05](05-AGENDA.md). The [master plan](MASTER-PLAN.md) owns shared rules.

## History and replay contract

A discovery branch identifies its starting artifact state, visible evidence, operational policy, selected action, outcome, resources and continuation. Preserve primary derivation separately from other evidence dependencies. Replay reconstructs what was visible at the decision, not everything known at the end.

An exploration policy chooses among available starts or continuations, allocates effort and may stop. Pin the worker, construction context, environment and outcome interpretation associated with replayed transitions. A change that invalidates those conditions cannot reuse an old outcome as its counterfactual result.

Support is explicit. A replay query returns a recorded consequence or reports missing coverage. Stopping deliberately is different from lacking a recorded continuation. Unsupported actions receive neither an invented reward nor an automatic failure score.

Screen policies against several historical investigations with the same decision interface used live. Rank quality and resource tradeoffs without assuming parallelism is inherently beneficial. New live outcomes expand the usable history. Consolidation can propose abstractions or corrected claims, but those proposals need their own checks.

## Delivery slices

1. **P06-1. Record discovery branches.** Preserve decision prefixes and artifact starting points while actual P05 work runs. Reconstruct a known trajectory from its public history.
2. **P06-2. Execute policy replay.** Compare fixed exploration policies on supported choices. Report coverage separately from performance and record all screening costs.
3. **P06-3. Revise and use a policy.** Construct one executable policy revision from development history. Screen it, then deploy it prospectively on fresh work through P05. Use missing coverage to propose informative live branches.

## Acceptance scenarios

- **P06-A.** Two policies order known alternatives differently and produce different supported exploration decisions.
- **P06-B.** Request an unrecorded continuation. The result is missing coverage, not a fabricated task failure or success.
- **P06-C.** A replayed policy tries to inspect a future outcome. The interface does not reveal it.
- **P06-D.** Change the worker or capability bytes whose behavior a transition records. Replay refuses to treat that transition as equivalent without appropriate evidence.
- **P06-E.** A selected policy changes actual live allocation. Quoting its source or inserting its advice into a prompt cannot satisfy this scenario.

Compare replay ranking with subsequent live results and report disagreement. A replay winner need not win live to complete the experiment. Check sensitivity to incomplete histories and resource objectives before treating replay as the primary selector.

## Working checkpoint

The agenda uses versioned exploration code informed by discovery history. Background replay is bounded work under the same allocations, not a second independent scheduler. The [research notes](../design/COGNITIVE-RESEARCH-NOTES.md) explain the Dream-RSI connection and its limits.
