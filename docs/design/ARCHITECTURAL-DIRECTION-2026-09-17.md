# Architectural direction after the Dream-RSI discussion

Accepted by the user on 2026-09-17 as the direction that will guide next steps. This records a design commitment to investigate, not a completed architecture or a claim of demonstrated learning. The worker is still implementing the current EC02/AD01 assignment; the user will notify the reviewer when it finishes. This note does not change that assignment, its evaluation conditions or its live authority.

## Decision

Optimize for the eventual general autonomous system, not for preserving the current implementation or minimizing the diff. The user explicitly accepts large modifications when they improve the product. Cheap worker implementation makes substantial alternatives feasible; it does not remove the need for informative comparisons.

Make persistent investigations, accumulated experience and executable self-revision the operational center. Agents are temporary participants. An investigation preserves its objective, competing explanations, actual observations, alternatives, dependencies, retained methods, pending actions and unresolved questions across the loss of model contexts.

Existing conceptual documents already allow much of this. The next design must make those choices operational rather than rename existing concepts or add disconnected frameworks. Preserve trustworthy guarantees, not code or experiment-specific structure for its own sake.

## Keep, change and remove

| Area | Direction |
|---|---|
| Execution and evidence | Keep durable operation identity, resource accounting, recovery, artifact identity, independent assessment and authority boundaries. Simplify or replace implementations where necessary without weakening those guarantees. |
| Cognitive orchestration | Be willing to replace substantial code. Use a shared investigation protocol for observation, proposed action, admission, execution, result incorporation, branching, revision, reuse and stopping. Domain instruments and judges specialize it; reasoning policies need not follow one fixed sequence. |
| Memory and context | Keep experience, claims, capabilities and working state distinct. Record decision-visible inputs and consequential dependencies so experience supports retrieval, continuation, policy comparisons and supported replay. |
| Dreaming | Distinguish replay of recorded outcomes, predictive simulation and new execution. Missing outcomes remain unknown. Neither a prediction nor an old result from a different intervention establishes a new observation. |
| Learning procedure | Make context selection, diagnostics, construction, allocation, coordination and stopping identifiable, replaceable policies. Allow code, model calls and tools in a procedure. Compare explanation-guided proposals with simpler mutation, recombination and direct construction. |
| Agenda | Make system-selected questions and interventions central. Use competing predictions to identify informative experiments, while allowing direct routine execution. Learned allocation must improve subsequent outcomes, not merely produce persuasive novelty scores. |
| Retention | Keep a bounded portfolio of scoped specialists and experimental alternatives. Allow whole compositions to evolve when interactions matter; do not force a global winner or artificial component attribution. |
| Swarm | Let the work determine when independent searches, parallel construction or adversarial checks help. One worker remains valid. Messages should contribute observations, artifacts, objections or decisions to persistent work. |
| Removal candidates | Duplicated experiment orchestration, disconnected helpers, restrictions that belong only to completed experimental controls, and manual assertions of facts that runtime records should establish. |

Do not adopt a universal world model before narrower predictions earn their value. Do not rewrite the whole runtime for tidiness. More agents, records or generated programs do not establish greater competence. Preserve historical experiments under their original conditions; changing future architecture must not rewrite old evidence.

## Research input and limits

[Dream-RSI](https://arxiv.org/html/2609.14858v1) motivates using recorded discovery history to evaluate executable exploration policies cheaply. Its replay covers recorded continuations, not arbitrary unseen consequences. Our proposed extension is to let uncertainty and disagreement between plausible policies help select bounded live investigations. This is a hypothesis for our design, not an attributed result or established advantage.

## Next-step checklist

- [x] Record the user's willingness to make substantial changes and the preferred architectural direction.
- [ ] Receive the current worker handback and assess the complete assignment, preserving accepted progress and separating material gaps from minor issues.
- [ ] Map the actual implementation onto the investigation protocol; identify which guarantees and components to reuse and which orchestration to replace.
- [ ] Compare a substantial consolidation with continued incremental extension before selecting the next build. Do not assume that either the smallest diff or a wholesale rewrite is best.
- [ ] Specify a coherent development trajectory: encounter a limitation, choose an investigation, acquire a procedure, use it in a different setting, detect a boundary or failure, and revise the procedure or learning policy. Require restart continuity without a new controller written by us between steps.
- [ ] Give the worker a substantial integrated assignment with explicit acceptance conditions, internal reviews and continuation rules. Keep experimental comparisons interpretable even when the architecture is broad.

The next design decision should use the worker's actual evidence. A positive result from every existing experiment is not a prerequisite for advancing. No new implementation or live campaign is authorized by this direction note alone.
