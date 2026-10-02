# DEVELOPMENT-02 — memory/context slice (deterministic)

Current status update, 2026-09-11: the historical deterministic report below is followed by the [live campaign](workstreams/d02live-live.md) at available tip `3857ec4`. Live access and fallback execution have now been exercised. The [review assessment](../reviews/DEVELOPMENT-02-LIVE-EVIDENCE.md) qualifies the all-zero interpretation, missing raw evidence and billing/accounting claims; current work is the [bounded evidence smoke](../docs/HISTORY.md#worker-live-evidence-prompt). Statements below about absent live access describe the earlier delivery.

Coordinator branch: `codex/implementation-development-02` from `e1b95a6`;
design packet `origin/codex/development-design-02` merged (tip `0816ebf`).
Lane merges: M-CTX `b46c559` (conflict-free); M-EP lane branch produced no
output (specialist terminated after reading) and was reclaimed — the slice
was implemented directly on the coordinator branch (`8648d8e`, lane branch
left at the contract base `b7d7c85`). No parallel-edit conflict was
possible.

Live model access is absent (no `SETTLEMENT_GATEWAY_ENDPOINT` / KEY /
`SETTLEMENT_GRANT_UNITS` in the environment), so no live run is claimed.
The deterministic slice is complete and proven:
`experiments/run_dev_episode.py --gateway fixture` runs the full episode —
observe → propose → admit (finite-panel policy frozen) → experience batch
→ diagnose → construct → check → freeze → select → bind → comparison
(batch reuse) → release → fresh-process subsequent use — against real
PostgreSQL and real subprocesses.

## What was built

- Bounded decision-context packets (`src/settlement/context.py`, migration
  `0008_context_packets.sql`): decision requests with per-kind required
  inputs; authorized experience + exact artifact/source version resolution
  (protected evaluation material never delivered); output/invocation
  contracts and working state incl. unresolved effects; budget qualification
  with staging/narrowing instead of silent drops; byte-bound invocation
  (`packet_invocations`); revalidation (evidence routes, quarantine,
  pending ops, byte availability); scope labels from authoritative records
  only. Outcomes ready/needs-information/stale; kill-process resume keeps
  packet continuity. Operator overview shows packet state (data region +
  rendered table, inert autoescaped template).
- Pre-diagnosis experience batch (`development.collect_experience`): DEV
  inference + grading through the real broker/launcher paths before any
  constructor-visible feedback; authenticated observations,
  candidate-scope experience claims carrying actual task content, and live
  observation-premise warrants. Diagnosis/construction consume ready-gated
  packets (refusal before spend otherwise); prompts carry packet id +
  rendered bytes + explicit response/invocation contract; invocations are
  digest-bound. The trigger-refs-only experience shape is deleted.
- Admission-frozen finite-panel policy (`panel_policy_for`,
  `{episode}-panel`): groups with tasks, access, outcomes, thresholds,
  stopping, release rules. Verify-then-amend lineage
  panel → `{panel}-eval` → `{eval}-bound`; harness arm protocols amend
  superseding the eval protocol and refuse group drift.
- Binding-only synthesis: the selected immutable binding is the sole
  source; reject/no-candidate yields no C candidate (harness abstention is
  the declared control behavior) and no fallback stem. With the bound
  version as stem, `_freeze_method` dedupes to the bound row itself.
- Harness transcript reuse (`run_abcs(..., dev_transcripts=...)`): the dev
  batch runs once; lessons/synthesis still run; costs settle without
  double-counting.
- Subsequent use (`experiment.run_subsequent_use`,
  `experiments/run_use.py`): fresh-process selection → invocation →
  grading → recording with use protocol, domain event, prior-exposure and
  pending-operation snapshot. Rejected episodes follow the visible
  incumbent path. Report phases derive from use receipts.
- Challenge panel (`experiments/dev02_challenge.py`): six frozen scenarios
  executed in `tests/test_dev02_episode.py` (missing-content refusal,
  counterexample preservation, retraction failover to a live route,
  oversize staging, resume-with-unresolved-operation visibility,
  reject-to-incumbent use).
- Probes retired: `reviews/probes/historical_test_development_01_readiness.py`
  with per-probe correspondence to the real-DB regressions.

## Verification (deterministic)

- `tests/test_dev02_episode.py` (14 tests) + `tests/test_dev02_context.py`
  (12 tests) + migrated `test_dev01_episode.py`/`test_dev01_ops.py`
  (incl. full fixture CLI e2e asserting the use phase from receipts).
- Full suite gate at integration (see `reports/VERIFICATION.md`).
- Still unverified: live finite-panel comparison with held-out groups,
  live model conditioning, real `runsc` containment, PostgreSQL 18.

## Runnable gates left for review

- Deterministic: `experiments/run_dev_episode.py --gateway fixture`
  (needs PostgreSQL + prepared DB).
- Live finite-panel: same entry `--gateway live` with endpoint/key/grant
  and `claude-opus-4-6` model access (refuses without them); live use via
  `experiments/run_use.py --gateway live`.
