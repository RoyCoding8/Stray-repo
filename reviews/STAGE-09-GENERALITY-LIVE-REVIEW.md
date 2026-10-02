# Stage 9 generality campaign: independent live-evidence review

Clarification, 2026-09-26: STEP policy and ENTRY method are different artifacts; different digests are legitimate. S09R-02 concerns the missing policy invocation and false attribution of the authored method to the model, not an equality requirement between the artifacts. The corresponding overbroad ledger instruction has been corrected. Verify each artifact's own identity and the causal join between decisions and effects. The [connected-study assignment](../docs/HISTORY.md#worker-stage-09-connected-study) supersedes this review's next-action instructions after the worker's repairs through `b0c010c`; the historical contaminated bundle stays unchanged.

Reviewed `codex/implementation-investigation-learning-02` at `9b9e421` on 2026-09-25. This is a review of the committed M3 bundle, not a new model run. Preserve `evidence_s09_m3_live/` byte-for-byte. The source and bundle establish a useful representation mechanism, but **do not establish live model acquisition or acquired-policy benefit**.

## Blocking findings

**S09R-01 — The purported live P1 construction carries a double identity.** `evidence_s09_m3_live/freeze.json` declares a live free model, while `construction.json` records `requests[0].model == "recorded-double"` for P1 and the later requests. The P1 policy source equals the `P1_POLICY_SOURCE` fixture in `scripts/s09_pilot.py` byte-for-byte. Its model-inference operation has the fixture-like 5-input/5-output-token receipt. A model could coincidentally emit fixture bytes, but a persisted request for `recorded-double` is not evidence that the frozen live model produced them. The pilot ran doubles immediately before live; deterministic campaign/operation identities may have replayed settled double operations from the same store. That mechanism is a hypothesis until the durable DB history is inspected. The independent claim that one live call acquired P1 is **withheld**.

**S09R-02 — The claimed bound-to-use byte identity conflates two artifacts.** P1's bound `STEP` digest is `b71a7f8f39ad1655555f0ac47ab2ab81321a78d98ac90f1079944fc626194706`. The four P1 software use records have `executed_source_digest == 3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de66ea04c58685`. That source is the authored `METHOD_SOURCE` constant in `scripts/s09_pilot.py`, the branching `ENTRY` quoted in the report as model-written. `run_study` takes the use repertoire from the frozen shared development repertoire and calls `trajectory.run_use`; it subsequently copies a policy digest into each saved use record. It does not execute the bound P1 policy in that use phase. Each method digest is internally correct, but it is **not equal** to the policy digest. The statements “the model wrote the branching program” and “model bytes, bound policy and executed bytes are the same object at every step” are false for this bundle.

**S09R-03 — The offline verifier accepts both gaps.** `scripts.s09_verify.verify_bundle_dir('evidence_s09_m3_live')` returned `pass`, zero problems, 13 model calls, three construction calls and 24 use records at this tip. It checks that a use-method digest belongs to a frozen repertoire and that a policy digest is present, but does not require the persisted model request identity to match the live freeze or prove the bound policy caused the subsequent use. The green result validates the narrower internal accounting/shape checks, not the headline acquisition claim. Add a rejecting check at the real authority/provenance boundary and a behavioral counterexample, rather than changing the report alone.

## Correct disposition now

| Question | Supported result |
|---|---|
| Three representation mechanisms | Implemented and tested at their reported scope; this review did not rerun the 195-test gate. |
| M3 live policy acquisition | **Unproven/contaminated evidence.** The committed P1 constructor request names a double. |
| Task benefit | No live-acquired treatment comparison. The numerical tie belongs to the committed, fixture-contaminated study. |
| Cross-domain transfer | Unproven; P1 is software-scoped and graph use is labeled fallback/uncovered. |
| Recursive improvement | Unproven and not eligible. |

The earlier gateway-refusal problem remains a worthwhile diagnosability defect, but this new provenance breach is the first gate. Do not infer that the model lacks capability; equally, do not infer that it acquired P1 from this evidence.

## Required correction and requalification

1. Read the original study DB and compare every P1/P2 construction operation's persisted request model, response digest, adapter identity, receipt and dispatch timestamp with the freeze. Identify whether deterministic operation IDs replayed the doubles run. Reconcile all prior live and doubled effects; do not issue another send merely to inspect them.
2. Separate doubles and live by disposable DB plus unique study/campaign/operation namespace, not only by output directory or a `mode` label. Refuse a live freeze if any joined construction request or receipt names a different model, adapter, study root or prior run. Keep the old bundle unchanged and mark its acquisition verdict withdrawn in the maintained ledger/report.
3. Establish the exact artifact chain in two columns: **operational policy** (`STEP`, construction response, release, accepted decisions) and **task method** (`ENTRY`, repertoire provenance, child invocation). If the hypothesis is that policy decisions improve later use, execute the bound policy after restart through the same action dispatcher. Merely copying its digest onto a `run_use` record is insufficient. Test a substituted policy that changes an admitted action while the method repertoire is held fixed, and a disconnect that refuses rather than falls back silently.
4. Freeze a new prospective live study against the same confirmed free model, with prior uncertain exposure carried conservatively. Run it only after the provenance gate passes on a fresh store. Report live acquisition, benefit and transfer separately; a negative or unavailable arm is valid. Recompute from raw bytes and receipts, then have an independent reviewer repeat the two comparisons above before restoring a positive claim.

The immediate decision is to **keep the representation work, withdraw the M3 acquisition headline, and repair the experimental join before another live comparison**. This is a causal-evidence issue, not a reason to resume broad unrelated bug cleanup.
