# P01. Persistent investigations

The investigator owns an objective across worker calls. The [master plan](MASTER-PLAN.md) owns build order and shared acceptance rules. This plan defines the first component to build.

## Scope and dependencies

Use the existing execution kernel, artifact store, genome and worker invocation. Give an investigation one authoritative continuation. Support multiple investigations without sharing their mutable workspaces. Advanced retrieval, learned agenda selection and teams are later components.

Reuse `src/rsi/episode.py`, `genome.py` and the broker where appropriate. Inspect `src/rsi/loop.py` for decision ownership to migrate. Preserve useful task-loop behavior until its caller moves, then delete the replaced route.

## State and decision contract

An investigation holds identity, objective and authority references, domain, state revision, open questions, current artifact references, policy versions, allocation and pending operation references. Completion means a domain-specific obligation was met or the investigation ended with an explicit unresolved result.

A decision observes an identified state revision and returns an explanation, a proposed action, its required artifacts and its intended observation. The explanation is a proposal, not evidence. The kernel owns dispatch identity and permission checks. A stale decision cannot advance a newer investigation revision.

Record the selected action and its visible input before dispatch. Link resulting observations to that decision. Resume a pending operation by its durable identity rather than creating a new invocation. An uncertain effect leaves the investigation unresolved at that boundary.

Begin with SQL investigation state plus immutable decision and observation references, using existing durable history where it fits. An event-only reconstruction is the alternative. Prefer explicit current state unless replaying existing records already derives it simply. Do not mirror authoritative state in JSON files.

A domain instrument supplies public task input, workspace materialization and the interpretation of checked outcomes. Keep the core independent of Exercism task names. Only domain instruments decide what counts as a task result.

## Delivery slices

1. **P01-1. Pin the contract.** Map the state and transitions onto current records. Specify expected-revision advancement, pending effects, completion and refusal. Show how one current episode fits without another broker.
2. **P01-2. Execute a continuing investigation.** A public entry creates an objective, requests a bounded worker action, incorporates the observation and chooses another action. Use a simple seed policy through the eventual policy interface.
3. **P01-3. Resume and migrate.** Continue the same investigation in a fresh process. Route one existing task workflow through it, then remove that workflow's duplicate decision owner.

## Acceptance scenarios

- **P01-A.** A worker's first result leaves a named question open. The next invocation receives that continuation and produces a result linked to it. This is more than two independent task launches.
- **P01-B.** Interrupt with an admitted operation pending. A fresh process resumes the same investigation without another send or loss of uncertainty.
- **P01-C.** Submit a decision against an obsolete revision. It cannot replace the newer continuation or launch another action.
- **P01-D.** Run two investigations concurrently. Their objectives, mutable artifacts and pending effects remain distinct.
- **P01-E.** An impossible or invalid action yields an inspectable unresolved result. It cannot become a successful task result through fallback text.

Use deterministic workers to qualify transitions, then a bounded live multi-decision run to inspect actual continuation. No gain over the current worker is required to close P01.

## Working checkpoint

The operator can create, inspect, suspend and resume one objective through the public consumer. Export its decisions, observations and unresolved effects. P02 can attach memory to these same identities. Do not add an autonomous scheduler, general claim graph or new UI application in this part.
