# Agent-Society v2

A persistent autonomous society whose temporary workers develop, test and reuse executable methods and problem representations. The design uses external model inference; model-weight training is outside the initial scope.

This repository is the shared handoff between the implementation agent and the design/review agent. It begins with the complete specification, not with copied runtime code from the previous project.

## Start the implementation agent

Clone `the configured repository` and attach [WORKER-PROMPT.md](WORKER-PROMPT.md). The prompt contains the full assignment and points to all committed inputs. If a fresh clone has not selected a default branch, fetch and check out `codex/architecture-handoff` from origin first.

The initial assignment is **S0-S3**, ending with a reviewable first learning system and a matched-resource comparison of ordinary baseline behavior, retained textual lessons and retained executable methods. S4-S7 remain specified future slices rather than part of this first assignment.

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

The documents were developed in a separate design-only pass. Their references to the old repository, earlier constitution and `tmp/` location are provenance, not required input files or restrictions on this v2 implementation. The packet is now committed here. The current implementation assignment and [working agreement](AGENTS.md) define the authorized work.

## Collaboration and status

Read [COLLABORATION.md](COLLABORATION.md) for branch ownership, review reports and the pull/push cycle. This seed contains no implemented system or validated learning result. Each future implementation handoff must state its actual verification boundaries.

The existing Agent-Society repository and its concurrent work are independent and must not be modified as part of this assignment.
