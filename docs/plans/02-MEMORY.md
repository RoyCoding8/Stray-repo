# P02. Evidence and memory

Make prior experience usable without turning interpretations into facts. Depends on [P01](01-INVESTIGATIONS.md). The [master plan](MASTER-PLAN.md) owns shared rules. P03 owns context selection rather than storage semantics.

## Pinned implementation contract (2026-10-13)

P02 extends the current P01 consumer. It does not restore the retired study
drivers or implement P03. The coordinator compared direct projection from P01
history with a revisioned inventory of immutable source references. Select the
reference inventory. A live projection with a sequence high-water mark can admit
late commits into an old snapshot. An explicitly captured source and a serialized
memory revision give later decisions a stable view without copying observations
into another authority.

Use three small tables in migration `0030_memory.sql`: a singleton revision clock,
captured experience references keyed by original observation ID, and append-only
claim versions keyed by claim ID and version. Captures and claim revisions lock
the same clock row within their write transaction. Duplicate capture is a no-op.
No synchronizer, embedding service, graph store or background worker is needed.
The older generic claim tables have no current source consumer and do not own P02.

`rsi.experience` owns source capture and resolution. Its public calls are:

```python
capture(dsn, observation_id, *, artifacts_root) -> dict
capture_investigation(dsn, investigation_id, *, artifacts_root) -> list[dict]
resolve(dsn, observation_ids, *, artifacts_root, revision=None,
        visibility="learner") -> dict
```

Captured metadata identifies the original investigation, decision, attempt,
worker operation, task, evaluator and artifact digests. A source content digest
detects changed canonical records. Scope and visibility come from provenance,
not caller labels. Only development-task observations enter learner memory.
Protected task splits or artifact ancestry cannot be relabeled as development.
Rendered experience contains public task instruction, compact checked outcome
and provenance. It never contains pristine tests, reference solutions, raw
verifier details or unrestricted trajectory text. Registered source packages are
byte-verified at capture and resolution. Missing or changed bytes produce explicit
missing-information entries. They do not become an empty search result or support.

`rsi.memory` is the consumer's one query and claim API:

```python
revise(dsn, *, claim_id, expected_version, text, scope, status,
       support=(), opposition=(), derived_from=(), supersedes=(),
       kind="lesson", artifacts_root) -> dict
query(dsn, *, purpose, investigation_id, scope, artifacts_root,
      visibility="learner", revision=None, view="structured",
      claim_ids=(), observation_ids=(), limit=10) -> dict
history(dsn, claim_id, *, artifacts_root, visibility="learner") -> list[dict]
```

Scope is a dictionary of explicit applicability filters; `domain="task"` permits
reuse across task identities. Relationships reference exact observation IDs or
exact `(claim_id, version)` pairs. Existing versions and observations never
change. Expected version prevents lost updates. Text and relationship collections
have finite bounds. An untested interpretation may lack support; a supported
interpretation needs available original evidence. Derived text remains labeled
interpretation. Flatten provenance to distinct original observation identities;
copies or merged lessons add no independent corroboration. Preserve inherited
opposition and withdrawal/supersession history rather than laundering it through
consolidation. New versions may narrow scope, challenge or withdraw a lesson.

Queries require a real investigation, purpose, scope and recognized visibility.
Apply source visibility before matching, returning content or counting results.
Default structured retrieval omits withdrawn and superseded heads. Exact history
can reconstruct prior versions. Exact and lexical matching are deterministic.
Each selected lesson brings its support, opposition, derivation roots and missing
information, even if an opposing source has different lexical text. A raw-history
view returns original experience without treating interpretations as observations.
The returned revision is a committed memory high-water mark; querying an earlier
revision selects the same captured references and claim versions after restart.
Byte availability remains a current qualification and may change independently.

The investigation consumer captures its observed history idempotently and queries
memory only before admitting a new decision. Pin the result in that decision's
`visible_input`; pending replay reuses the admitted bytes and identities. An
optional frozen `memory` configuration declares scope, view and result limit.
Default later-use retrieval uses the task domain and objective as purpose. Before
dispatch, revalidate any referenced bytes; missing evidence must refuse rather
than silently omit a required remembered contradiction. Preserve the existing
64-KiB continuation bound. Do not add another context lifecycle or truncation.

Acceptance uses real PostgreSQL and actual fixture child execution. The later
worker must change its observable behavior when the contradicted lesson is
disconnected or replaced by wrong evidence. A separate prospectively bounded
free-route probe checks actual model conditioning. Failure or unavailable transport
is an honest live result, not a reason to weaken the deterministic contract.

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
