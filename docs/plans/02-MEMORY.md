# P02. Evidence and memory

Make prior experience usable without turning interpretations into facts. Depends on [P01](01-INVESTIGATIONS.md). The [master plan](MASTER-PLAN.md) owns shared rules. P03 owns context selection rather than storage semantics.

## Objects and ownership

Keep immutable observation references to decisions, operations and artifact bytes. A claim is a versioned interpretation with scope, supporting observations, opposing observations and status. A lesson is a proposed reusable interpretation of experience. A continuation belongs to its investigation and is not another free-form memory summary.

Claims can be untested, supported within a scope, challenged, superseded or withdrawn. These statuses do not assert universal truth or calibrated confidence. Links distinguish support, opposition, derivation and supersession. A model-proposed link remains derived information.

Store claim metadata and relationships in the current database, with large content in the artifact store. Begin with exact and lexical lookup plus scope filters. Embeddings can later assist candidate retrieval; no graph database is required to represent these relations.

A query names its purpose, investigation, scope and visibility. Return evidence references, interpretations, opposition and missing information. Enforce visibility before retrieval results reach the caller. Do not index sealed answers into a learner-visible search corpus.

## Delivery slices

1. **P02-1. Preserve experience.** Make P01 observations discoverable by identity and scope. Check referenced bytes and distinguish missing evidence from an empty result.
2. **P02-2. Introduce revisable claims.** Add claims and their support or opposition. Apply a correction as a new version without changing the original observation.
3. **P02-3. Reuse and consolidate.** Query relevant experience during a later investigation. Merge redundant derived entries with explicit provenance. Retire a lesson from active retrieval while preserving its history.

## Acceptance scenarios

- **P02-A.** A successful procedure fails on a changed input. Record both observations, narrow or challenge its applicability claim, and preserve the original success.
- **P02-B.** A later investigation retrieves the useful lesson and its contrary evidence. A copied summary cannot count as an independent corroborating observation.
- **P02-C.** Withdraw a misleading lesson. Default retrieval stops recommending it, while historical reconstruction still explains its earlier use.
- **P02-D.** A query resembling a sealed assessment task returns no protected content or derived answer leakage.
- **P02-E.** Restart and query the same memory revision. Source references and claim history remain stable.

Compare a raw-history view and structured lessons on examples requiring prior experience. A bounded live run checks that the worker actually responds to the remembered contradiction. Storage correctness alone does not prove useful memory.

## Working checkpoint

Investigations read earlier evidence and correct an interpretation through one memory API. P03 can select from those objects without inventing their meaning. Leave learned ranking and elaborate probabilistic belief propagation out of P02. See the older [memory design](../design/MEMORY-AND-CONTEXT.md) for additional hypotheses, not current implementation status.
