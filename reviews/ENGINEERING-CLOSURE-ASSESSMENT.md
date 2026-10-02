# Engineering closure: accepted experimental baseline

Assessed source: `913bda791bd0fb3cf87c568fb57daea17fe4a240` on `codex/implementation-development-02`. Assessment scope is the closure evidence and readiness for the next bounded experiment, not another whole-codebase audit.

The worker reports **590 passed, 0 failed, 0 errors** in 838.45 seconds on real PostgreSQL and real subprocesses. The design role has not rerun that suite. Its preserved source/configuration and verification boundaries remain in [VERIFICATION](../reports/VERIFICATION.md), [close1](../reports/workstreams/eng-close1.md) and [close2](../reports/workstreams/eng-close2.md).

## Independently checked from the preserved evidence

- The closure revision was fetched and resolved exactly. The production, experiment and test source diff from the recorded clean smoke revision `35c3fef26333927d48e0f7d3a5c5d2c544642a64` to the closure tip is empty.
- The [new smoke](../reports/evidence/eng-close2/smoke_close2.json) contains two unique operations. Model settlement is 8,344 units and grading is 111, totaling **8,455**. Independent arithmetic agrees with allocation debit and the expenditure ledger in the [reconciliation bundle](../reports/evidence/eng-close2/reconciliation.json); both operations have zero unresolved liability and one matching settled reservation.
- Accepted solver source equals the recorded decoded model receipt text. Independently computed SHA-256 is `d777e666f69ad5ea3c257ebb8e1c3606ddfe2192bea97001415e11f44c35c962`, matching the preserved source digest. The grader record reports three of three checks passing. The design role did not execute that generated source.

This resolves the previously observed mismatch in the historical smoke's cost reporting. The new run is one live baseline solve on a visible regression task, using an explicit local uncontained profile. It is not held-out transfer, a released learned method or evidence of learning gain. Provider monetary billing remains unknown; internal settlement is the verified quantity. Decoded output is preserved, not full raw provider transport bytes.

## Decision

Accept this revision as the foundation for the deterministic Agenda 01 experiment. The [six dependency rows](COGNITIVE-DESIGN-COMPATIBILITY.md) now distinguish established mechanics, scoped live evidence, corpus availability and unproven learned competence. A positive capability release is unnecessary to test deterministic investigation scheduling.

Residual report hygiene is carried into the next integration task: duplicate/superseded ledger rows, a stale 579-test summary and the pending active-docs coverage disposition. Those records should have one authoritative current mapping. They do not by themselves demonstrate a broken runtime or justify restarting the broad audit.

The next deliverable is the [Agenda 01 contract](../docs/design/AGENDA-01-IMPLEMENTATION.md), followed by its implementation and frozen trajectory comparison. Live learned-method selection/transfer, real runsc containment, verified provider charges, PostgreSQL 18 and the remaining deployment qualifications stay open. No claim of general autonomous improvement follows from this acceptance.
