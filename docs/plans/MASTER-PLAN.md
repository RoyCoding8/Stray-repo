# Master plan for component development

Selected plan, 2026-10-13. Build one working part at a time. Keep the system usable at each checkpoint.

The [architecture synthesis](../design/ARCHITECTURE-SYNTHESIS-2026-09-22.md) explains the design and research. This master plan owns component dependencies and build order. Each component plan owns its scope and acceptance conditions. The [project ledger](../../reports/PROJECT-LEDGER.md) alone records what is implemented and verified. The [refinement roadmap](../design/REFINEMENT-ROADMAP.md) retains the original philosophy-to-release stages.

## Destination and starting point

Build general autonomous investigation, acquired executable competence and transfer, followed by improvement of the learning procedure. Many investigations may run concurrently, with one authoritative continuation per investigation. Teams are temporary allocations of computation.

The existing bounded genome loop is the accepted foundation prototype. Reuse its kernel and useful worker, artifact and verification paths. A retained instruction change is not yet an acquired executable method. No component below is complete merely because an older experiment had a similar name.

## Parts and dependencies

Dependencies mean usable contracts, not proven learning advantages. The parts are modules and responsibilities, not ten new services or permanent agents. Identifiers name plans, not new runtime API symbols.

| ID | Component plan | Required parts | Working result |
|---|---|---|---|
| P01 | [Persistent investigations](01-INVESTIGATIONS.md) | Existing kernel and worker | An objective survives several decisions, effects and restart under one owner. |
| P02 | [Evidence and memory](02-MEMORY.md) | P01 | Relevant experience and contrary evidence inform later decisions without rewriting observations. |
| P03 | [Context construction](03-CONTEXT.md) | P01, P02 | A bounded, versioned policy selects and inspects evidence for a particular decision. |
| P04 | [Executable capabilities](04-CAPABILITIES.md) | P01, P02, P03 | A constructed method is checked, retained, selected and actually executed on later work. |
| P05 | [Autonomous agenda](05-AGENDA.md) | P01, P02, P04 | The system chooses its next learning experience using capability and outcome history. |
| P06 | [Search history and dreaming](06-SEARCH-AND-REPLAY.md) | P01, P02, P05 | Recorded branches screen executable exploration policies and identify needed live experiments. |
| P07 | [Learner revision](07-LEARNER-REVISION.md) | P02, P03, P04, P05 | An inherited executable learning policy governs a later development round. P06 adds replay evidence when available. |
| P08 | [Temporary teams](08-TEAMS.md) | P01, P03, P04, P05 | A retained work graph controls real delegation, joins and rework. |
| P09 | [Representations and transfer](09-TRANSFER.md) | P02, P03, P04 | A retained abstraction or method executes on meaningfully changed work with explicit applicability. |
| P10 | [Continuing campaigns and assessment](10-CAMPAIGNS.md) | P01, P02, P04, P05 | An unattended bounded campaign resumes, exports results and accumulates later-use evidence. P06–P09 can join later. |

Assessment is present from P01. P10 adds longitudinal assessment and operation; it does not introduce correctness checking for the first time. Likewise, P01 includes basic bounded context and explicit next actions. P03 and P05 improve those decisions rather than making P01 depend on unfinished components.

## Recommended build sequence

| Checkpoint | Work in order | What the operator can do afterward |
|---|---|---|
| 1. Durable investigator | P01 | Give one objective, inspect its decisions, interrupt it and continue it. |
| 2. Useful remembered context | P02, then P03 | Continue work using relevant earlier evidence, including a contradicted lesson. |
| 3. Acquired executable competence | P04 | Acquire or reject a method and try an eligible retained method on changed work. |
| 4. Autonomous continuing work | P05, then P10 | Give a bounded charter and let the system select, execute and resume useful work without a supervisor chat. |
| 5. Better development decisions | P06, then P07 | Screen search policies and inherit a changed procedure for producing successors. |
| 6. Broader reuse and coordination | P09, then P08 when work warrants teams | Reuse representations across changed tasks and execute useful team decompositions. |

This is a recommended sequence, not a demand to finish every later plan before using the system. P09 may start after P04 when there is a suitable corpus. P08 may start after P05 when a workload exposes a concrete decomposition opportunity. Avoid speculative parallel implementation across unknown shared contracts.

The earlier architecture packages map onto these parts. A contains P01–P04. B contains P05–P06 and relevant consolidation. C contains P07–P09. P10 connects operation and assessment across them. These are subdivisions of stages 8–10, not ten new project stages.

## How to build one part

1. Read the component plan and the ledger. Inspect only its relevant implementation and callers. Record what can be reused and what must be replaced.
2. Resolve the component's stated design decision. Pin its input, output, authority and persistence contracts before parallel code changes. Compare mechanisms only where the choice remains consequential.
3. Implement its delivery slices in order. End each slice at a working public consumer and focused check. The owner integrates changes serially.
4. Run the component's acceptance scenarios against the integrated path. Include an unchanged baseline and a deliberate disconnection or wrong artifact where specified. A broken baseline cannot validate a tamper test.
5. Run a bounded live path when the component requires model-conditioned behavior. Use an authorized verified free route. A fixture proves mechanics, not model acquisition or learning.
6. Consolidate before the next component. Remove obsolete callers, duplicate rules and temporary scaffolding. Inspect CI on the integrated checkpoint, reproduce failures, and repair either the implementation or a demonstrably stale test contract. Do not weaken correct assertions to obtain green CI.
7. Record the consolidation diff and exact verification boundaries in the ledger. Remove owned temporary worktrees and branches, sync the checkpoint backups, and confirm CI is green before starting the next assigned component. Carry unrelated externally blocked checks explicitly instead of calling them passing.

Engineering regressions are the builder's responsibility. Use isolated worktrees for authorized parallel work, with disjoint ownership and serial integration. The master plan does not authorize spawning agents where session instructions require asking first. Paid models and Jev are outside the current scope.

## Shared rules and evidence

- Keep kernel authority, durable dispatch identity, unresolved effects, artifact provenance and sealed assessment. Evolving policies propose decisions within those boundaries.
- Every part has one owner for its state. Use existing SQL and artifact mechanisms where they fit. Do not add another lifecycle manager or shadow ledger.
- Treat operations, model observations, claims, derived summaries and executable packages as distinct objects. Do not substitute a self-report for an observed result.
- Candidate code runs through permitted bounded child execution. The coordinator never imports or executes candidate code. Current native limits do not establish hostile filesystem or network containment; trusted promotion remains subject to its existing requirements.
- Keep a small working archive. Preserve historical evidence without loading every past artifact into each decision.
- Preserve frozen study bytes. Use fresh identities for new experiments. Unknown usage or uncertain effects remain explicit.

For each component, report implementation, behavioral qualification, live acquisition, useful later use and wider learning benefit separately. Applicable dimensions can remain unknown or negative. A truthful negative can finish a bounded experiment and still guide the next part.

## Completion and stopping

A part is working when its public consumer performs the declared behavior, its acceptance scenarios pass, and its state can be used by the next part. A schema, standalone helper, test count or report alone does not complete it.

Do not spend each batch demanding a sustained learning win. Close the mechanism build with attributable behavior and an informative outcome. P10 accumulates longer-term evidence. Formal promotion, deployment qualification and release remain separate milestones.

P01 and P02 reached their qualified component checkpoints. P03 implementation,
independent review, bounded live comparison and consolidation are complete;
final checkpoint CI is pending. P04–P10 remain paused. The ledger owns
exact verification boundaries and outstanding work.
