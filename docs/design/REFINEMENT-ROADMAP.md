# Settlement: philosophy to final implementation

Updated 2026-09-10. This is the maintained project map and design task list. The product is infrastructure for a persistent, general, autonomous society; the early work determines the behavior that infrastructure must support.

**We are at stage 8: refining and testing how the prototype acquires competence.** A conceptual architecture and provisional stack exist. S0-S3 machinery is built. Useful autonomous learning has not yet been demonstrated. The current assignment is [WORKER-DEVELOPMENT-01-PROMPT.md](../../WORKER-DEVELOPMENT-01-PROMPT.md).

## The mental model

Purpose -> intuitive behavior -> precise semantics -> architecture -> representation and technology -> buildable specification -> prototype -> behavioral experiments -> revised design -> complete system -> operational qualification -> final implementation.

This sequence has feedback. We revisit an earlier decision when evidence challenges it; we do not restart the whole project after each defect. Design levels R0-R7 describe precision. Build slices S0-S7 describe executable milestones. They are different axes, not competing roadmaps.

“Done” means the stated deliverable exists at its stated scope. A selected design is revisable. A built mechanism is not necessarily empirically useful. A simulated test is not a live experiment.

## Overall stages

| Stage | Purpose and existing mapping | Status | Evidence or next completion condition |
|---|---|---|---|
| 1. Philosophy | Purpose, generality, growth, human relationship; R0 | **Done: baseline selected** | [Conceptual architecture](REFINED-ARCHITECTURE.md), sections 1-2. Broad competence and useful discovery remain aims. |
| 2. Intuitive picture | The society working, exploring, remembering and changing; R1 | **Done: baseline selected** | Conceptual parts and end-to-end narratives in the architecture. |
| 3. Precise and formal description | Meanings, entities, transitions, obligations and limits; R2-R3 | **Done: baseline selected** | [Glossary](GLOSSARY.md) and architecture sections 3-4. Conditional arguments exist; no machine-checked proof or proof of intelligence is claimed. |
| 4. Abstract architecture | Connect execution, development and agenda; R4 | **Done: baseline selected** | Architecture section 5. Responsibilities do not prescribe permanent agents or services. |
| 5. Representation and technology | State, executable packages, interfaces and supporting tools; R5-R6 | **Done: provisional choices** | [Representation design](REPRESENTATION-DESIGN.md) and [technology decisions](TECHNOLOGY-DECISIONS.md). Experiment-driven revision remains possible. |
| 6. Practical specification | Builder protocols, requirements and acceptance conditions; R7 | **Done: baseline specified** | [Practical specification](PRACTICAL-SPECIFICATION.md). Later cognitive mechanisms still need policy-level refinement. |
| 7. Foundation prototype | S0-S3: bounded execution, persistence, evidence, continuity, candidate/trial/release machinery | **Built; validation partial** | Worker report at `be1730d`: R03 fixes merged, 456 tests passed; its verification section identifies tested code `42caa1e`. The design role has not independently rerun that suite. Live gates and empirical learning remain open. |
| 8. Learning and cognitive policy refinement | Specify and test acquired competence, memory, background development, agenda and teams | **Ongoing: current stage** | [Learning model](LEARNING-MODEL.md) selects the next episode. Its deterministic worker slice is implemented (`reports/DEVELOPMENT-01.md`); live learning evidence is pending. |
| 9. Evidence-driven architecture consolidation | Confirm, narrow, replace or remove mechanisms; revisit R2-R7 | **Not started as a synthesis milestone** | Record what experiments support and which representation/stack decisions consequently change. No automatic rewrite. |
| 10. Complete system prototype | S4-S6: representations/transfer, autonomous agenda/teams, learner revision/consolidation | **Not completed** | Each slice needs its own end-to-end demonstration. Scaffolding does not complete it. Stage 8 can deliver portions incrementally. |
| 11. Operational qualification | S7: real profiles, recovery, controls and supported deployment | **Partial groundwork; qualification not done** | Verify real components and the declared failure model for the chosen deployment. Explicit stack revisions can replace earlier targets. |
| 12. Final implementation and release | Consolidate the validated architecture into a supported infrastructure product | **Not started as a release milestone** | Complete chosen scope, migrations, installation, documentation, lifecycle UI and release evidence. Retain sound prototype code; “final” does not mean replacing everything or ending research. |

## Stage 8 design task list

| Order | Design part | Current state | Required result |
|---|---|---|---|
| 8.1 | Acquired competence and development episodes | **Selected for the first experiment** | [Learning model](LEARNING-MODEL.md): method/representation/policy distinctions, transitions, evidence and failure cases. |
| 8.2 | First complete development episode | **Deterministic slice implemented; live run pending** | DEV-01 through DEV-12: construct a method from experience, freeze it, compare, and inspect fresh-worker use. Separate simulation from live outcomes. Worker evidence in `reports/DEVELOPMENT-01.md`. |
| 8.3 | Memory and decision context | **Baseline only; detailed refinement pending** | Retention, retrieval, compression, contradiction and forgetting policies; test continuation and downstream outcomes. |
| 8.4 | Background development and autonomous agenda | **Baseline only; detailed refinement pending** | Triggers, allocation, wake conditions and stopping. No inference merely to keep a heartbeat busy. |
| 8.5 | Representation invention and transfer | **Abstract contract selected; working mechanism pending** | Runnable interpretations/translations; separate soundness, coverage, cost and negative transfer. S4 and E2. |
| 8.6 | Temporary teams and collective reasoning | **Baseline only; adaptive policy pending** | When teams help, how work/disagreement combine, and when a single worker wins. S5 and E5. |
| 8.7 | Learner revision and consolidation | **Baseline only; working mechanism pending** | Complete learning-trajectory comparisons, retirement, specialization and migration. S6 and E7. |

The order expresses dependencies, not a demand to finish each part globally. Complete one development episode, then use its evidence to refine memory and agenda. Mathematical transfer is a later experiment, not a prerequisite for this episode.

## Current packet checklist

- [x] Inspect the selected design and worker implementation at `be1730d`.
- [x] Restore a current roadmap from philosophy through final implementation.
- [x] Specify acquired competence and the first bounded development episode.
- [x] State alternatives, failure cases and limits on learning claims.
- [x] Write the bounded worker prompt and update the design entry points.
- [x] Worker maps DEV requirements onto code and records implementation choices.
- [x] Worker implements missing behavior and verifies the integrated slice.
- [ ] Execute a live episode with supplied model access, allocation and suitable execution profile.
- [ ] Assess the finite-panel result without requiring a positive outcome.
- [ ] Use the result to choose the next memory/context or development-policy refinement.

## Acceptance from here

1. **Blocks the intended experiment:** the path cannot run, evidence is untrustworthy, or a confound defeats the comparison. Address before drawing its conclusion.
2. **Prototype limitation:** controlled conditions or an explicit workaround permit an honest bounded experiment. Record the condition and proceed within it.
3. **Production hardening:** robustness or scale work outside the experiment's conditions. Schedule for qualification rather than repeatedly reopening prototype acceptance.

Classification depends on use. Absent containment can permit trusted scripted fixtures in an explicitly disposable test environment; it does not qualify arbitrary generated code on an exposed host. Missing paid access blocks a live claim, not implementation or deterministic verification.

R03 does not trigger another unrestricted review cycle. The next review asks whether this episode works and what its evidence means. A negative or inconclusive result can complete an experiment while leaving the architectural hypothesis unsupported.

## Evidence and maintenance

Current worker evidence: [implementation status](../../reports/IMPLEMENTATION-STATUS.md), [verification](../../reports/VERIFICATION.md), and their linked R03 workstream reports. Unverified areas include live inference/paid billing, real runsc containment and writable limits, live DBOS backup interleaving, PostgreSQL 18, and empirical learning. These are separate obligations, not a requirement to finish all of them before any controlled experiment.

E1-E8 in the conceptual architecture track empirical claims. The first A/B/C comparison does not discharge all eight or establish scientific novelty or knowledge absent from model training.

After every handoff, update the current-stage sentence, affected rows, checkboxes and evidence links. Record the source revision and distinguish reported results from independently reproduced results. Preserve attributable historical reports. A passing harness never completes a pending empirical obligation.
