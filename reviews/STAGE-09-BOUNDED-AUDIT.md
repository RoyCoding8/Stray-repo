# Stage 9 bounded audit and handoff

2026-09-21. Refetched remote implementation `1d90c2e` and review `0e142be`; both are unchanged. Reused the existing reviewer checkout. No production changes, provider calls or database effects.

The project is at stage 9. Foundations and the bounded stage 8 contract fix exist. Deterministic provider-boundary tests demonstrate acquisition/use machinery; the original live corpus still has zero retained members and incumbent fallback on all 24 uses. Generality and useful live policy learning have not been demonstrated.

## Additional audit, deliberately bounded

The [migration probe](probes/stage09_migration_guards.py) confirms two dependencies of the proposed consolidation:

1. A reference-free exploratory proposal targeting a protected transfer task can return admitted from `admit_investigation`. The real `_run_boundary` target fence then refuses it before the diagnostic runs, with zero query spend. The probe replaces only the forbidden diagnostic with a must-not-run sentinel. This is a split ownership issue to preserve/fix during migration, not evidence that the current public path leaks the protected task.
2. `_select_member` picks the first matching family. With old and revised members in one repertoire, appending the revision leaves the old one selected; reversing their order selects the revision. Current selection is not a promotion protocol. The new binding must select an independently qualified revision explicitly.

Source inspection also shows use operation identities depend on campaign and task rather than a revision. The migration must distinguish intentional execution of new bytes from a retry of the old action, without weakening retry identity. This audit did not exercise a real-store revision collision and does not label one as observed.

The prior review's three conclusions remain: exact-match replay support cannot rank changed policies, revision feedback needs separation from independent assessment, and learning-policy revision needs a concrete executable contract. These are addressed by the new [implementation contract](../docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md), rather than another round of generic bug finding.

## Decision and complete task

Proceed with one investigation driver over existing execution guarantees, a bounded executable policy step, separately governed feedback/assessment, explicit active bindings, and a prospective comparison of incumbent/direct/experience-informed policy construction. The worker owns sequential M0–M7 design concretization, implementation, qualification and delivery under [the full assignment](../docs/HISTORY.md#worker-stage-09-consolidation).

No full suite or Linux child rerun was needed for this documentation-only audit. The new probe is DB-free; the last review's nine focused checks and worker-reported integrated results keep their original scope. The handoff requires real integrated checks for the implementation. There is no new live grant in this note.

- [x] Refresh exact remote state and preserve the accepted closeout.
- [x] Trace and probe admission/selection migration dependencies.
- [x] Resolve the reviewed architecture gaps into a concrete implementation contract.
- [x] Assign one complete sequential worker batch with independent gates.
- [ ] Worker completes M0–M7 and reports implementation separately from learning evidence.
