# Cognitive design checkpoint: compatibility and evidence mapping

2026-09-11. Design commit `cf888de` (docs-only, no production-code changes)
merged into the implementation coordinator line at `b070458`. This note
records the compatibility check against implementation contracts and maps the
checkpoint's requested implementation evidence to audit findings. The drafts
add no implementation of agenda, representation invention, adaptive teams or
learner revision to this assignment; no API was reshaped to match them.

## Compatibility with implementation contracts

All draft cross-references resolve to existing material:

- LEARN-6/8/9 and the learning model: `docs/design/LEARNING-MODEL.md`,
  `docs/design/PRACTICAL-SPECIFICATION.md`.
- Study/experiment identifiers E1-E8, S0-S7: `PRACTICAL-SPECIFICATION.md`,
  `docs/design/REFINED-ARCHITECTURE.md`.
- Reduction-with-witness candidate: `docs/design/REFINED-ARCHITECTURE.md`.
- Ownership, quarantine, outbox machinery assumed by the team draft:
  present by name in `src/settlement/broker.py`, `capabilities.py`,
  `store.py`, `context.py`, `experiment.py`, `run.py`, `steward.py`.

Posture is compatible: the checkpoint prescribes no new services, universal
ontology, vector store, permanent hierarchy or workflow engine, and defers
exact database/API mapping to audited interfaces. No contradictions found.
Three watch-items for the audit (dependencies, not contradictions):

- W1: the team draft assumes working ownership/restart/outbox/resource-root
  semantics. Names exist; correctness is exactly what ENG-INV-A is auditing.
- W2: the representation draft's witness pattern assumes a per-domain
  checker; no such checker exists in the repo, as expected for an
  uncommissioned study.
- W3: evaluator-epoch bridges assume retained raw evidence; raw-evidence
  completeness is the known EVID-01 gap, partly addressed by ENG-SOLV
  follow-ups (`e6a8848`, `3439e8b`).

## Evidence-request mapping (refreshed 2026-09-11 against final tree)

Checkpoint section "What now needs implementation results", per row. All
code revisions below are on `codex/implementation-development-02`;
components are real PostgreSQL 16 + real subprocesses with model doubles
unless "live" is stated.

1. Interpretable live solver-to-grader path, preserved raw outcomes,
   failure classification: ESTABLISHED. Verbatim-source contract +
   reserved-settled reporting (ENG-SOLV lineage, EVID-01 closed by direct
   probe, CLOSE-1). One bounded live baseline smoke on the repaired tree
   (`reports/evidence/eng-close2/`, run revision `35c3fef` clean):
   panel-triangular, inference → validation → staging → grading →
   settlement, success, 3/3 grade cases, unique-operation reconciliation
   holds (consumed delta 8455 == settled sum). Remaining uncertainty: this
   is a live baseline solver run, not autonomous candidate construction or
   acquired-method use; selected-method transfer still unexercised.
2. Effective configuration, operation union, cost/usage, held-liability
   reconciliation: ESTABLISHED for internal settlement. Operation-union
   accounting + held liability (ENG-ACCT lineage, EVID-02 closed by direct
   probe); entry records pin source fingerprint + effective config
   (EVID-PROV closed); the smoke's reconciliation.json shows reserved ==
   settled per unique operation with ledger agreement. No live monetary
   oracle exists, so provider charges stay unknown; internal settlement is
   conservative (unbilled settles full reservation, fail-visible). Live
   selected-method accounting and the historical 8344/111/111/8455 lane
   state (annotated, preserved) remain outside the confirmation.
3. Actual packet delivery, dependencies, current-state checks:
   ESTABLISHED for the deterministic path. Build/bind/ready-gate behavior
   verified (ENG-INV-C lineage: fail-closed MODEL_INFERENCE bind,
   byte-recorded invocation); run_tests.py assessed end to end (CLOSE-1).
   Freshness/completeness claims stay explicitly labeled, not asserted.
   Remaining uncertainty: live-constructed packets at scale; CTX-level
   delivery assurance under adversarial load.
4. Audited composition, ownership, stop/recovery, reservation interfaces:
   ESTABLISHED. Receipt-operation binding + reconcile guard (INVA-01/02),
   cross-identity contradiction flag (CLOSE-1-04), max_depth enforcement
   routed through attempt_workflow (CLOSE-1-05), bounded read waits
   (coord INVA-06), gateway cancel + group-kill supervision (INVB-01–05),
   all green in restart/cancellation/stale-state suites. Semantic
   guarantees hold under tested restart, cancellation, stale-generation
   and accounting paths; untested: multi-host fencing, daemon-present
   runsc behavior.
5. Release selection, fresh-process use, preserved interpretation
   versions: DETERMINISTIC BEHAVIOR ESTABLISHED, LIVE EARNING OPEN.
   Fresh-process `run_use.py` path, release-gate refusal of synthetic
   origins, evaluator version pinning and interpretation-version
   preservation all verified deterministically. Zero releases; no live
   method has earned release, so transfer/consolidation/migration behavior
   has no live subject. Do not read router correctness as learning gain.
6. Usable corpus and observed development bottlenecks: ASSESSED FROM
   ACTUAL MATERIAL. The usable corpus today is the failure/fix record:
   60 failed arm-task outputs (C-episodes), the solver-format confound
   cases, repeated construction/grading failure classes in the ledger, and
   the cost profile (model 8344 vs grade 111 per smoke). No abstraction or
   learner-policy intervention is selected, and none is blocked on a
   positive release: the corpus already supports studying failure
   classification and construction reliability before any candidate wins.
   Whether it supports representation invention is untested, not assumed.

PG18 and real runsc containment remain externally blocked with exact
prerequisites (deployment host / daemon host). A large passing test
count alone does not answer rows 5–6; the behavior-level evidence above
is what does.
