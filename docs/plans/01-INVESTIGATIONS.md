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

## Implementation contract (2026-10-13)

Reuse the kernel investigation as the objective authority. Its commitment revision
continues to fence attempts. A one-to-one SQL extension owns a separate continuation
revision, domain configuration, questions, artifact references and pending decision.
Do not advance the commitment revision merely because a worker returned a result.
The extension references the objective; it does not copy or redefine it.

An expected continuation revision reserves exactly one decision and attempt before
dispatch. Record decisions in the existing immutable RSI decision history and
observations under the existing attempt history. The pending decision fixes its
operation identity, visible continuation and input artifact references. Kernel
operation state remains authoritative for whether an effect was sent or settled.
No external execution or nested store command occurs inside the state transaction.

Suspension blocks new decisions. It does not cancel or erase an admitted effect.
Resumption finishes that effect under its existing identity before another decision.
Uncertain effects retain the pending reference and cannot complete the objective.
Invalid actions end with an explicit unresolved result and no fabricated success.

Keep each domain task and evaluator immutable. Bind the worker's continuation and
previous solution snapshot to its admitted instruction, including the input content
digest. A new worker gets a separate workspace materialized from those bytes. Task
projection was rejected because it would rename one task on every continuation.
Event-only state reconstruction was rejected because the existing journal does not
derive the current questions and pending decision without a second interpreter.

The initial task instrument checks solutions with the existing pristine verifier.
Its bounded seed policy either attempts the task, continues from a failed checked
solution, or stops with an unresolved result. It supplies no hidden tests or reference
solution to worker context. Migrate development-task execution in the existing loop
through this owner, keeping archive selection and sealed comparisons in their
existing owners. The migrated default remains one worker attempt so existing frozen
loop budgets retain their meaning; the public investigation entry allows a larger
prospectively bounded attempt count.
