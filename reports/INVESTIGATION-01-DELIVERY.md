# Investigation 01 delivery (lanes A–E)

Branch: `codex/implementation-investigation-01`. Handoff `123c211`, reviewed baseline `84d2094` contained.
Tip at delivery: see `git log`. Remote equality verified by push exit plus `git status`.

## A. Honest baseline (merged `b9f5480`)

C3 proves construction plus use with a callback learner, not outside-menu acquisition.
C4 is incomplete live qualification (11 pairs, 9 readable, no use phase), not a completed negative comparison.
C2 failure descriptions are lineage-specific. Raw model text and receipts are recorded missing and unrecoverable.
Gate `reviews/probes/inv_a_baseline_gaps.py` 17-0.

## B. Shared investigation path (merged `c317254`, `503e844`, `d59c809`, `92a16ea`, `e825e57`)

One typed packet shape per decision shared by both domains (`experiments/ad01/packet.py`, `experiments/coord02/packet.py`).
Renderer, parser, executor agree with mechanically tested transport examples.
One driver (`broker.sweep`) replaces heartbeat, recover, repair scan, scheduler rounds.
One `ResourceEnvelope` admits every effect from post-effect reads; IR-03 double promise killed at the caller.
Zero-budget probes refuse through a dedicated allowance without consuming a study lineage.
Gates: B1 11-0, B2 8-0, B4 4-0, B3 8-0. ag01 suite 37-0 after the CREATEDB prerequisite fix.

## C. Qualification (merged `dab3005`, gate 9-0)

Recording doubles drive the same public entry as live inference.
Settled receipt bytes equal script bytes at validation, retention, fresh-process use.
Acquired method reduces 14 ops to 3 in 5 queries, valid on all dev tasks.
Rejected-then-corrected, no-candidate incumbent use, two domains, kill/resume with zero added calls.
Replay boundaries refuse unsupported branches. All five lane gates 40-0 on the merged tip.

## D. Live qualification (blocked on grant, one request)

Old calls reconciled: 19 live construction settled, 27 live learner, 0 comparison, 0 use records.
Token floor 17383 AD01 per-op plus 11520 fallback declared, gateway-side unknown.
New-study ceiling: 360 model calls inside 1.475M tokens. Cap sheet in `reports/workstreams/inv-d.md`.
Request: provision `SETTLEMENT_GATEWAY_ENDPOINT`, the bearer key, a fresh disposable Postgres grant
for the new study root, and written confirmation of study root, model id, effort, frozen per-episode config.
No live work runs on assumed permission.

## E. Checks and replay

Full suite: 727 passed, 591 skipped (pre-existing DSN skips), 0 code failures.
16 provisioning errors (my dropped lane databases, unset DSN) all rerun green with provisioning present.
Independent replay: C4 11 pairs 9 readable, C3 72 records 45 retained-byte plus 27 incumbent (INV-E-02 corrected AD-06),
receipt arithmetic unreplayable from committed bytes (INV-E-03).
Reviews merged: semantic accept with 10 findings, state accept with 11 findings, one rework done.
System-chosen: packet shapes, envelope sequencing, sweep claims, acquired reducer, refusal dispositions.
Fixture-authored: C3 recording callbacks, authored reducers, bypass-era grants, probe budgets.
Acquired behavior changed execution: yes on doubles (14 to 3 ops); live transfer unmeasured (no grant).
Transfer: contract plus envelope plus loop are domain-shared; coord02 port proves the second domain.
Unmeasured: live acquisition, cross-domain method transfer, gateway-side token exposure.

## Next research bottlenecks (at most three)

1. Plan proposal plus lineage-specific repair before any grant (probes still need a fair first action).
2. Raw, receipt, and frozen-config export before spend claims (receipt arithmetic is currently unreplayable).
3. Fair paired design before benefit claims (I/R opportunity mismatch voids comparison readouts).

## Reproduction

Gate suite: `PYTHONPATH=. uv run --frozen --extra test pytest tests/test_inv_c_qualification.py
tests/test_inv_b1_contracts.py tests/test_inv_b2_loop.py tests/test_inv_b3_coord02_contracts.py
tests/test_inv_b4_trajectory.py` with lane databases provisioned per file header.
Baseline probe: `python3 reviews/probes/inv_a_baseline_gaps.py`.

## Bugfix passes 1-2 (merged)

- F1 seam refusal: unattested constructor artifacts refused with reason plus liability; canned-seam test migrated to the refusal contract.
- F2 receipt content: `operation_receipts` rows carry content; billed post-effect reads observe settled charges.
- F3 resume definition: one call definition (durable model-inference ops); resume row reads 5; INV-E-01 closed.
- G1 r03 prerequisite: explicit CREATEDB prerequisite test; two prior failures were environmental.
- G3 fresh observation: constructor receives the current boundary diagnostic (plus 2 minus 1).
