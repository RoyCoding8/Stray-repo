# Agent-Society v2

A persistent autonomous society whose temporary workers develop, test and reuse executable methods and problem representations. The design uses external model inference; model-weight training is outside the initial scope.

This repository is the shared handoff between the implementation agent and the design/review agent. It contains the selected architecture and the S0-S3 foundation prototype. Useful autonomous learning remains an empirical objective.

## Current work

Start with the [maintained roadmap](docs/design/REFINEMENT-ROADMAP.md): philosophy through final implementation, with completed, ongoing and pending stages. We are refining the learning mechanism and preparing its first complete development episode.

Attach [WORKER-DEVELOPMENT-01-PROMPT.md](WORKER-DEVELOPMENT-01-PROMPT.md) to the worker. It contains branch integration instructions and all required reading, for either the existing conversation or a new one. [WORKER-PROMPT.md](WORKER-PROMPT.md) is the historical S0-S3 assignment.

The next slice is defined in the [learning model](docs/design/LEARNING-MODEL.md): construct a method from experience, evaluate its frozen version, and inspect fresh-worker use or fallback. It is bounded systems engineering and experimental design. Full autonomous agendas, representation transfer and learner revision remain later work. Parallel implementation specialists and isolated worktrees are authorized under [IMPLEMENTATION-WORKFLOW.md](IMPLEMENTATION-WORKFLOW.md).

## Complete design packet

| File | Role |
|---|---|
| [Design overview](docs/design/README.md) | Central mechanism, reading order, verification boundary. |
| [Glossary](docs/design/GLOSSARY.md) | Shared domain meanings. |
| [Conceptual architecture](docs/design/REFINED-ARCHITECTURE.md) | R0-R4: philosophy, mechanisms, formal obligations and scenarios. |
| [Representation design](docs/design/REPRESENTATION-DESIGN.md) | R5: executable packages, typed state, dependencies and context. |
| [Technology decisions](docs/design/TECHNOLOGY-DECISIONS.md) | R6: selected stack and primary-source research. |
| [Practical specification](docs/design/PRACTICAL-SPECIFICATION.md) | R7: 59 requirement IDs, concrete protocols, experiments and S0-S7 gates. |
| [Refinement roadmap](docs/design/REFINEMENT-ROADMAP.md) | Selected decisions and open empirical obligations. |
| [Learning model](docs/design/LEARNING-MODEL.md) | Acquired competence, development episodes, decisions DLM-01 through DLM-06 and requirements DEV-01 through DEV-12. |

The required design packet is committed here. The current assignment and [working agreement](AGENTS.md) define scope; historical prompts and provenance notes do not add hidden inputs or completed assignments to it.

## Collaboration and status

Read [COLLABORATION.md](COLLABORATION.md) for branch ownership and the pull/push cycle. The worker report at `be1730d` records 456 passing tests after R03. Live inference, real containment, operational qualification and empirical learning have separate outstanding gates; see [verification](reports/VERIFICATION.md). This design handoff does not independently reproduce the worker suite.

Keep concurrent work isolated. Handoffs state actual verification boundaries and distinguish implementation progress from learning evidence.
