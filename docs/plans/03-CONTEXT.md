# P03. Context construction

Give each decision the evidence it needs under a finite budget. Depends on [P01](01-INVESTIGATIONS.md) and [P02](02-MEMORY.md). The [master plan](MASTER-PLAN.md) owns common rules.

## Decision contract

A request names the question, decision purpose, visible investigation revision, permitted memory scope, required artifacts and context allocation. A context policy selects evidence and inspection actions. Its output identifies source bytes, selected claims, opposition, omissions and unresolved information needs.

Distinguish a usable view, insufficient information and a view invalidated by changed dependencies. A small packet with omitted required evidence is not a usable view. A policy may choose a targeted inspection or bounded subcall when it expects that action to resolve a specific information need.

The policy owns selection. P02 owns evidence meaning and visibility. The kernel owns execution of any inspection or model effect. The worker consumer binds the produced view to its invocation. A document written to disk but never consumed does not qualify.

Initially control context between Codex invocations. Do not claim control over Codex's internal context management. The first representation is a structured packet and immutable content references. Keep large artifacts external and provide scoped access through permitted tools.

## Delivery slices

1. **P03-1. Build the baseline view.** Select required evidence and relevant scoped entries using a deterministic policy. Include opposition and explicit omissions. Bind the view to a real P01 decision.
2. **P03-2. Add active inspection.** Allow exact searches and bounded programmatic excerpts. Add optional subordinate model calls only where simpler inspection cannot answer the request. Charge all work.
3. **P03-3. Compare policies.** Version selection policies independently of the solver. Compare the baseline, raw bounded history and one adaptive policy on the same questions.

## Acceptance scenarios

- **P03-A.** Relevant evidence is dispersed among irrelevant records. The invoked worker uses the selected source to make the correct distinction.
- **P03-B.** A highly similar lesson is contradicted in the current scope. The view includes opposition, and the worker does not treat similarity as authority.
- **P03-C.** Required evidence exceeds the allocation. Return an information need or request a bounded inspection. Do not silently omit it and label the packet complete.
- **P03-D.** Change a dependency after packet construction. The consumer detects the invalid view before making the affected decision.
- **P03-E.** Disconnect the packet from the invocation. An independent check detects that the decision did not consume the declared context.

Use source-removal and misleading-memory controls. A live comparison checks model-conditioned behavior, not just whether packet text contains a citation. Report decision quality alongside construction cost and latency.

## Working checkpoint

P01 decisions consume identified context selected by a replaceable policy. P04 can request capability-development context through the same path. A new recursive model framework or embedding service is not part of this checkpoint. Research motivation is in the [context and memory source review](../design/COGNITIVE-RESEARCH-NOTES.md).
