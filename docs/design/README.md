# Autonomous society architecture refinement

Updated 2026-09-09. This folder contains one isolated design pass. It is separate from the concurrent implementation and the historical material in `tmp/design/`. No source code, runtime settings, historical constitution, or existing design decisions have been modified by this pass. These documents are inside the repository's gitignored `tmp/` tree.

## Read in this order

1. [Selected conceptual architecture](REFINED-ARCHITECTURE.md): R0-R4, from philosophy through the abstract operating model. Sections 3.10 and 5.7 explain the developmental mechanism and give a concrete trajectory of abstraction and transfer. Sections 4 and 6 contain the formal obligations and failure review.
2. [Selected representations](REPRESENTATION-DESIGN.md): R5, expressing those semantics as typed state, executable packages, dependency structures, and derived views.
3. [Technology decisions](TECHNOLOGY-DECISIONS.md): R6, the selected runtime, persistence, execution, retrieval and operator stack, with primary sources and explicit limits.
4. [Practical specification](PRACTICAL-SPECIFICATION.md): R7, transition protocols, recovery, interfaces, learning experiments, and sequenced build acceptance gates.
5. [Refinement roadmap and task list](REFINEMENT-ROADMAP.md): design completion status and remaining empirical/build obligations.
6. [Glossary](GLOSSARY.md): vocabulary scoped to this redesign.

## The architectural decision

Build a persistent collective that searches over its own problem-solving methods and representations. Temporary workers pursue durable investigations. Experience can produce an invocable abstraction, an explanation of where it applies, and new questions made tractable by it. These products are evaluated separately.

The principal loop is:

    limitation or opportunity -> competing explanation -> operational change
    -> bounded comparison -> scoped retention -> transfer -> revised frontier

The system can alter context construction, tools, procedures, representations, teams, curricula, and learning policies. Its authority and protected evaluation access remain externally grounded. No single role, model, fixed organization chart, or universal performance score is its permanent center.

The central empirical question is whether this arrangement acquires useful, transferable competence more efficiently than strong simpler alternatives under comparable total resources. The documents select a design and state rejecting experiments. They do not claim that formal notation proves autonomous intelligence or inevitable improvement.

## Verification boundary

Completed: selected design documents through R0-R7, six conditional invariant arguments, 24 conceptual adversarial scenarios, representation consistency scenarios, concrete transition and recovery requirements, primary-source technology checks, and document/link checks. The adversarial work was a self-review, not an independent review or executed software test suite. No machine-checked proof, agent benchmark, live inference experiment, implementation, or weight training was performed for these documents. E1-E8 remain research obligations.

The implementation target is Python/PostgreSQL/DBOS with immutable artifacts, a stable composition interpreter, gVisor-isolated generated execution, a mediated gateway, and a browser management surface. This selection does not alter the concurrent repository's stack or install anything.

The next executable work is the S0-S7 sequence in the practical specification. Its first learning comparison tests retained textual lessons against retained executable methods under matched resources and independent task exposure. Begin a separate implementation pass only when requested; the current pass is a research and design handoff.
