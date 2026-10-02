# Autonomous society architecture refinement

Updated 2026-09-11. These are committed design documents for the implemented foundation and its next development stage. Start with the [maintained roadmap](REFINEMENT-ROADMAP.md) for the whole progression from philosophy to final implementation. The current handoff changes design/navigation and reviewer apparatus/evidence; production code is unchanged and the checkout is isolated from implementation work.

## Read in this order

1. [Roadmap and task list](REFINEMENT-ROADMAP.md): overall stages, current status and next assignments.
2. [Memory and decision context](MEMORY-AND-CONTEXT.md): current stage 8.3 design, context materialization and CTX-01 through CTX-10; read alongside the [learning model](LEARNING-MODEL.md), which defines acquired competence and DEV-01 through DEV-12.
3. [Selected conceptual architecture](REFINED-ARCHITECTURE.md): R0-R4, philosophy through abstract operation. Sections 3.10 and 5.7 describe development and transfer; sections 4 and 6 contain formal obligations and failure scenarios.
4. [Selected representations](REPRESENTATION-DESIGN.md): R5, typed state, executable packages, dependencies and derived views.
5. [Technology decisions](TECHNOLOGY-DECISIONS.md): R6, the provisional runtime, persistence, execution, retrieval and operator stack.
6. [Practical specification](PRACTICAL-SPECIFICATION.md): R7, protocols, interfaces, experiments and S0-S7 acceptance gates.
7. [Glossary](GLOSSARY.md): shared domain meanings.

For the next conceptual refinement, read [Autonomous agenda](AUTONOMOUS-AGENDA.md): stage 8.4 policy, investigation options, continuation, bounded background work and the next experiment. The [agenda experiment and representation draft](AGENDA-EXPERIMENT-01.md) refines its semantic records, comparison, counterexamples and stopping rules. Continue through [representation and transfer](REPRESENTATION-AND-TRANSFER.md), [temporary teams](TEMPORARY-TEAMS.md) and [learner revision](LEARNER-REVISION.md). The [design checkpoint](COGNITIVE-DESIGN-CHECKPOINT.md) summarizes their connections and the implementation evidence now required. [Research notes](COGNITIVE-RESEARCH-NOTES.md) separate primary-source precedents from our own hypotheses. These are design drafts, not new implementation mandates in the current engineering audit.

## The architectural decision

Build a persistent collective that searches over its own problem-solving methods and representations. Temporary workers pursue durable investigations. Experience can produce an invocable abstraction, an explanation of where it applies, and new questions made tractable by it. These products are evaluated separately.

The principal loop is:

    limitation or opportunity -> competing explanation -> operational change
    -> bounded comparison -> scoped retention -> transfer -> revised frontier

The system can alter context construction, tools, procedures, representations, teams, curricula, and learning policies. Its authority and protected evaluation access remain externally grounded. No single role, model, fixed organization chart, or universal performance score is its permanent center.

The central empirical question is whether this arrangement acquires useful, transferable competence more efficiently than strong simpler alternatives under comparable total resources. The documents select a design and state rejecting experiments. They do not claim that formal notation proves autonomous intelligence or inevitable improvement.

## Verification boundary

The original design pass selected R0-R7 and recorded conditional arguments, failure scenarios and empirical rejection criteria. The worker subsequently implemented S0-S3 and addressed three review rounds. Its report at `be1730d` records 456 passing tests with real PostgreSQL 16.15 and subprocesses, with model/runtime doubles where stated. This design pass has not independently rerun that suite. [Worker verification](../../reports/VERIFICATION.md) records exact tested revisions and remaining live gates. E1-E8 remain empirical obligations; no learning advantage is claimed.

The provisional implementation stack is Python/PostgreSQL/DBOS with immutable artifacts, a composition interpreter, a probe-gated gVisor profile, a mediated gateway and a browser management surface. Real containment and operational qualification remain distinct from shim-based tests.

The live-capable Development-02 worker tip available at review is `3857ec4`, with 530 reported deterministic tests and four live rejection/fallback summaries. The [campaign assessment](../../reviews/DEVELOPMENT-02-LIVE-EVIDENCE.md) accepts integration, identifies a solver-format confound and distinguishes billing from internal settlement. The [current worker assignment](../../WORKER-ENGINEERING-REVIEW.md) is a whole-repository engineering review and repair, including those evidence obligations and all ranked priorities. The earlier [live context pilot](../../reports/CONTEXT-PILOT-01.md) remains limited feasibility evidence. No acquired-competence advantage is established; S4-S7 remain later slices, tracked in the roadmap.
