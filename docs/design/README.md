# Autonomous society architecture refinement

Updated 2026-09-10. These are committed design documents for the implemented foundation and its next development stage. Start with the [maintained roadmap](REFINEMENT-ROADMAP.md) for the whole progression from philosophy to final implementation. The current handoff changes documentation only and is isolated from implementation work.

## Read in this order

1. [Roadmap and task list](REFINEMENT-ROADMAP.md): overall stages, current status and next assignments.
2. [Learning model](LEARNING-MODEL.md): the current refinement of acquired competence and bounded development, with DEV-01 through DEV-12 for the worker.
3. [Selected conceptual architecture](REFINED-ARCHITECTURE.md): R0-R4, philosophy through abstract operation. Sections 3.10 and 5.7 describe development and transfer; sections 4 and 6 contain formal obligations and failure scenarios.
4. [Selected representations](REPRESENTATION-DESIGN.md): R5, typed state, executable packages, dependencies and derived views.
5. [Technology decisions](TECHNOLOGY-DECISIONS.md): R6, the provisional runtime, persistence, execution, retrieval and operator stack.
6. [Practical specification](PRACTICAL-SPECIFICATION.md): R7, protocols, interfaces, experiments and S0-S7 acceptance gates.
7. [Glossary](GLOSSARY.md): shared domain meanings.

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

The next assignment is [Development 01](../../WORKER-DEVELOPMENT-01-PROMPT.md), a bounded method-acquisition episode that extends the current prototype. It preserves the A/B/C comparison and accepts negative or inconclusive results. S4-S7 remain later slices; the roadmap tracks their refinement and implementation separately.
