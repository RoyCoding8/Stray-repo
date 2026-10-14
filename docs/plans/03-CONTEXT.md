# P03. Context construction

Give each decision the evidence it needs under a finite budget. Depends on [P01](01-INVESTIGATIONS.md) and [P02](02-MEMORY.md). The [master plan](MASTER-PLAN.md) owns common rules.

## Decision contract

The system chooses which permitted evidence to inspect and present for a particular decision. This is a reusable investigation responsibility, not a SWE-specific prompt template. Initially it operates between Codex invocations; it does not control Codex's internal context manager.

Selected design, 2026-10-14: one immutable packet per P01 decision, with bounded inspection inside its builder. Two independent designs and a cross-review favored required/optional evidence selection with request identity tied to the investigation revision. Adopt the simpler packet design's complete evidence bundles and baseline-first delivery. Reject a separate context-session manager, request table and per-read reservation service.

| Responsibility | Owner |
|---|---|
| Objective, continuation and pending effect | P01 investigation |
| Evidence meaning, visibility, provenance and exact historical versions | P02 experience and memory |
| Evidence selection, inspection and packet construction | New `rsi.context` module |
| Dispatch, external effects and settled spending | Existing execution kernel |
| Exact packet consumption | Existing investigation/episode worker path |

Use two public operations: `context.build(dsn, request, artifacts_root=...)` and `context.validate(dsn, packet, artifacts_root=...)`. The builder owns request pinning and finalization; validation checks the packet's pinned dependencies. Keep policy selection and permitted text inspection inside this module. P01 remains the only lifecycle owner.

### Request and packet

A request identifies the investigation, objective and state revisions, decision/attempt/worker operation identities, question, decision purpose, permitted memory scope, required evidence references and finite allocation. It names a versioned context policy. Required references and information needs are explicit caller inputs; the policy cannot downgrade them to optional to obtain a ready result.

One deterministic request identity belongs to each investigation state revision. Pin its request and memory revision through the existing command journal, then cache the finalized packet under a distinct deterministic journal command. A conflicting request under the same identity is refused. Retry reuses the pin and any cached result; a new generation cannot refresh limits or silently move to newer memory. No schema migration is expected.

The packet records its schema and policy versions, request identity, selected memory revision, claim bundles, original evidence references, bounded excerpts, omissions, unresolved required needs and construction counts. A claim bundle contains its exact version, support, opposition, scope and provenance together. Optional bundles may be omitted whole. Optional discovery warnings remain visible; they do not alone make a packet insufficient.

Build returns `ready` or `needs_information`. Dependency validation can return `stale`; it does not mutate an admitted packet. Missing required evidence or a required bundle that cannot fit means `needs_information` and no worker dispatch. Source references identify verified bytes; an inaccessible external reference is not a substitute for required worker-visible evidence. P02 continues to determine eligibility and resolve original bytes.

### Allocation, visibility and retry

Preserve P01's six continuation fields: objective, objective revision, state revision, open questions, artifact references and previous observation. Add the packet to that continuation. Budget the complete canonical continuation, including JSON overhead and retained P01 fields, against the existing 65,536-byte cap. Measure the final rendered worker instruction separately, including task instructions and its input digest. Neither characters nor bytes are reported as measured tokens.

The baseline performs bounded trusted reads, without model subcalls or candidate execution. Limit selected records, scanned bytes, excerpt bytes and final packet bytes. Report completed-build counts and elapsed time separately from kernel-settled model/effect costs. Exclude volatile timing from the packet digest. An interrupted uncached build may repeat pure reads; do not claim cumulative crash-complete CPU accounting or report interrupted work as zero.

Active inspection uses only closed built-in exact search and excerpt operations over P02-permitted, resolved text. It cannot accept an arbitrary path, execute source content, read evaluator/hidden material or expand visibility. Give each inspection a stable request-local identity and cache completed results in the existing journal, with finite cumulative logical-action and returned-byte ceilings. Account repeated physical work separately where observable. Do not create another grant authority. Any later model or external subcall would require existing broker reservations and durable effect identities; none is needed in the initial P03 build.

### Consumer binding and migration

Before admission, validate packet dependencies and the complete continuation size. Store the exact packet in P01's decision. The episode renderer then embeds that continuation in the broker's actual instruction; a digest stamp without the corresponding content is insufficient.

On resume, use the saved decision, packet and operation payload. Revalidate selected bytes without replacing the packet or inventing another operation. Changed dependencies follow P01's established never-sent or unresolved-effect handling; stale context cannot erase an uncertain dispatch.

Move the existing memory builder and revalidator out of `investigate.py` into the context owner. New decisions use only the packet path. A validate-only adapter may drain pre-P03 pending decisions using their exact saved `visible_input.memory`; it must not rebuild them or become a fallback for new decisions. Preserve frozen evidence. Migrate P02 consumer assertions to the new envelope while retaining their opposition, provenance and resume behavior checks.

## Delivery slices

1. **P03-1. Build and consume the baseline.** Implement the pinned request, deterministic selection, complete claim bundles, required/optional omissions and full-continuation admission. Connect a real P01 decision and fixture child. Remove the replaced builder. Qualify exact retry, legacy pending resume and actual instruction binding before adding inspection.
2. **P03-2. Add active inspection.** Implement bounded exact searches and excerpts, allowing one inspection result to determine the next query or selected excerpt. Demonstrate a case where this changes worker-visible evidence under the same allocation; otherwise the loop is merely decorative. No subordinate model framework is required.
3. **P03-3. Compare policies.** Independently version structured baseline, raw bounded history and adaptive inspection. Run the integrated acceptance gate before independent GPT-6.1 Sol High review. After repairs, run a bounded free-route comparison. Finish with consolidation, CI repair, cleanup and backup sync as the master plan requires.

Pin interfaces before delegating. A context owner can implement the builder and inspection code; a consumer owner can migrate P01 and the episode path against that contract. Keep test ownership disjoint. Integrate the baseline first, then inspection and comparisons; do not fragment one evolving packet shape across many writers.

## Acceptance scenarios

- **P03-A.** Relevant evidence is dispersed among irrelevant records. The invoked worker uses the selected source to make the correct distinction.
- **P03-B.** A highly similar lesson is contradicted in the current scope. The view includes opposition, and the worker does not treat similarity as authority.
- **P03-C.** Required evidence exceeds the allocation. Return an information need or request a bounded inspection. Do not silently omit it and label the packet complete.
- **P03-D.** Change a dependency after packet construction. The consumer detects the invalid view before making the affected decision.
- **P03-E.** Disconnect the packet from the invocation. An independent check detects that the decision did not consume the declared context.

P03-E needs an unchanged passing baseline and a deliberately disconnected instruction, checked through stored decision, broker payload and actual fixture-child input. A verifier that rejects the baseline cannot establish sensitivity. Add UTF-8/JSON-overhead boundary checks, optional-warning versus required-source cases, atomic opposition retention, cached retry and fresh-process resume. Changing an irrelevant unselected source should not invalidate a packet.

Use source-removal and misleading-memory controls. For active inspection, vary an eligible source so that the next inspection or selected evidence changes; also demonstrate refusal when the required source is unavailable. A transcript listing searches without affecting the consumed packet does not qualify.

For the live comparison, freeze permitted corpus, memory revision, tasks, solver, model/route, budgets and grading before effects. Separate arm state so earlier arm results cannot enter later context. Interleave or randomize arm order and record route variation. Report completed decisions, task quality, omitted/insufficient cases, local construction work, actual instruction size, measured model usage and latency. Include source-removal and misleading-memory controls. A passing task or a citation alone does not establish a context advantage; an honest tie or unavailable arm is informative. Stop at the prospectively bounded comparison, not repeated route qualification or win-seeking retries.

## Working checkpoint

P01 decisions consume identified context selected by a replaceable policy. P04 can request capability-development context through the same path. The first policies are authored; autonomous acquisition of a context policy and improvement of the learner are later claims. A recursive model framework or embedding service is not part of this checkpoint. Research motivation is in the [context and memory source review](../design/COGNITIVE-RESEARCH-NOTES.md).
