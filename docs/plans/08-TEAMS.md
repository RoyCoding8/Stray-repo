# P08. Temporary teams

Use multiple workers when their information or artifacts can contribute to a composed result. Depends on [P01](01-INVESTIGATIONS.md), [P03](03-CONTEXT.md), [P04](04-CAPABILITIES.md) and [P05](05-AGENDA.md). The [master plan](MASTER-PLAN.md) owns common rules.

## Coordination contract

A team policy produces an executable work graph. Each work item names inputs, output obligations, authority, allocation, dependencies and its completion check. A join consumes actual submitted artifacts and determines which obligations are met or require rework.

P01 retains the parent investigation's continuation. Workers own isolated workspaces and their assigned outputs. The team does not create another mission owner or shared mutable scratch directory. The agenda allocates the team's total resources before workers consume them.

The initial alternatives are a well-equipped single worker, an independent parallel portfolio and a work graph with explicit joins. Use a real workload with separable information or artifacts. Agents taking different role names while reading the same answer is not independent evidence.

Retained coordination must control dispatch, sequencing, joins or rework through executable decisions. Prompt advice is a comparator. P07 may later revise the coordination-development procedure, but is not required to execute teams.

## Delivery slices

1. **P08-1. Execute an independent work graph.** Qualify isolated work, dependency release, artifact submission and joins using independently authored graphs.
2. **P08-2. Construct coordination.** Ask the model to produce a graph under the explicit contract. Execute its accepted decisions and preserve rejected graphs as rejected.
3. **P08-3. Retain and compare.** Reuse eligible coordination on changed work. Compare against the single worker and simple portfolio, including communication and integration costs.

## Acceptance scenarios

- **P08-A.** Two workers produce complementary artifacts. The join checks the composed result against the parent obligation.
- **P08-B.** Every worker reports success but the artifacts are incompatible. The parent result fails or requests attributable rework.
- **P08-C.** Change a retained graph dependency. The actual dispatch order changes. Cosmetic edits do not count as behavior change.
- **P08-D.** Interrupt with one worker complete and another pending. Resume the graph without resending completed work or treating a missing output as success.
- **P08-E.** Introduce a shared erroneous assumption. An independent check can reject the result despite unanimous worker agreement.

Run a bounded live comparison on tasks with a genuine decomposition opportunity. More workers or more text is not itself benefit. A null or losing team result can justify retaining the single-worker policy.

## Working checkpoint

One investigation can select and execute a bounded temporary team, retain eligible coordination and inspect joins. Permanent specialist agents, all-to-all messaging and a new distributed orchestrator are outside this part. The older [team design](../design/TEMPORARY-TEAMS.md) supplies hypotheses, not proof of useful coordination.
