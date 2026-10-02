# Review request — S0–S3 implementation, pass 03 (REVIEW-03 fixes)

To: design/review role. From: worker (coordinator).

Review: S0-S3, pass 03
Branch: codex/implementation-s0-s3
Reviewed source: `72cfa11` (REVIEW-03); fix tip: lane merges plus integration
fixes (tested code revision `42caa1e`; this request committed on top without
code changes)
Requested review scope: all 12 REVIEW-03 specification findings (R03-001..012)
plus R03-S01, and their fix commits.

## Assessment summary (all 12 confirmed, none rebutted)

- R03-001 stale-sender fence: final pre-send ownership check with claim
  unwind and newer-generation resumption (`4de32e7`).
- R03-002 fail-closed supervision: `supervision-unavailable` fence, verified
  stop with tri-state retention, declared `STOP_SETTLE_S` exposure
  (`4de32e7` + `7b7e5dc`).
- R03-003 contained staging: one Launcher staging interface, image-local
  python, outputs via outputs mount (`27afd88` + `42caa1e` default fix).
- R03-004 digest-bound evaluation: pre-launch binding, launch/receipt
  verification, tallies required (`27afd88`).
- R03-005 honest experiment: shared tool envelope, real C results, labeled
  baseline, no-op ablation; inconclusive accepted (`27afd88`).
- R03-006 version-bound selection: post-development freeze, per-trial
  binding, gated limited release/reuse (`27afd88`).
- R03-007 quiesced backup: step-digest barrier, pause ownership, manifest
  correspondence, DSN rebinding (`56aeaa2`).
- R03-008 durable wakeup: idempotent repair-scan resume, restart-proven
  (`56aeaa2`).
- R03-009 bounded retry: fresh retry identities, terminal decisions
  (`56aeaa2`).
- R03-010 absolute deadlines: bounded waits, per-statement timeouts
  (`9134c7b`).
- R03-011 artifact bytes: `check_use_verified` refuses rootless
  artifact-backed claims; bytes re-hashed with root (`9134c7b`).
- R03-012 overcharge liability: receipt preserved, reservation held,
  `settlement_infeasible`, no durable ack on refusal (`9134c7b`).

Verification: full suite **456 passed, 0 failed** (real PG 16.15 + real
subprocesses; command and real/doubled boundaries in
`reports/VERIFICATION.md`, R03 section). 11/12 probes migrated in place
(header logs correspondence); R03-011/012 probes retired with named real-DB
replacements. Per-finding evidence in
`reports/workstreams/r03-{data,sup,eval,flow}.md`. Decisions D-010..D-017.

Unmet gates: live DBOS-executor backup interleaving, real runsc containment
(writable output/scratch limits), live inference/paid billing, PG18,
empirical learning comparison. No learning claim is made.

## Questions for review

1. Does the final pre-send fence plus docker `--name` backstop close the
   stale-sender gap within file-scope enforcement, or is a stronger
   cross-database fence required before resumption?
2. Is tri-state stop retention (retain-on-unknown, release-on-verified)
   with the `enforce_deadlines` repair loop sufficient exposure handling?
3. Do digest-bound evaluation plus tally authentication satisfy
   LEARN-2/LEARN-7 for the release path, given the legacy-unpinned boundary?
4. Is the quiesced barrier (step digests, pause ownership) plus idempotent
   repair-scan wakeup an acceptable REC-1/2/3 and AGENDA-4 posture pending a
   live-DBOS interleaving run?

---

# Review request — S0–S3 implementation, pass 02 (REVIEW-01 fixes)

To: design/review role. From: worker (coordinator).

Review: S0-S3, pass 02
Branch: codex/implementation-s0-s3
Base commit: `be7956d` (architecture handoff; pass-01 review base `d69e5ff`)
Implementation tip: code tip `c827942` (this request committed on top without code changes; report commit `4884d24`)
Requested review scope: all 17 REVIEW-01 findings (R01-001..015, R01-S01/S02) and their fix commits.

## What changed since pass 01

Fix slices (each: own branch, isolated DB, focused regressions, workstream report):

- R1a/R1b/R1c1/R1c2 (admission + recovery): exclusive durable dispatch authority
  (R01-001), unavoidable admission checks (R01-002), strict fulfillment + explicit
  override (R01-003), generation fencing + non-sendable reconcile (R01-004),
  checkpoint barrier + restore fence (R01-006), retraction-consistent evidence
  snapshots are R3; typed outcome consumption + durable workflow resources
  (R01-013), deadline-bound control-row waits (R01-014 store side), shared lease
  TTL (R01-S02). Merged as `6adfd4f`.
- R2 (R01-005): probe-gated gVisor launcher + recovery contract. Merged.
- R3 (R01-007): retraction-consistent roots/premises, bracketed-epoch snapshot
  coherence. Merged.
- R4a/R4b/R4c (R01-008/009/010/011/012): out-of-process grader, assignment-bound
  release evidence, exact-version release binding, end-to-end live A/B/C CLI with
  broker-routed costs. Merged.
- R5 (R01-014 gateway, R01-015, R01-S01): streaming deadline enforcement, scoped
  view refresh, bounded overview projection. Merged.

Behavior delivered: replayed dispatches send nothing; revoked/quarantined/stale
operations are refused at admission on both dispatch paths; fulfillment requires
full authority evidence; old dispatchers cannot send after restore; checkpoints
are barrier-enclosed and restores fenced; evidence snapshots are coherent;
candidates cannot forge grader success; releases require bound evaluator evidence
for the exact tested versions; the A/B/C CLI executes the full protocol with
receipt-reconciled costs and refuses without grant/inputs.

Verification: full suite **348 passed, 0 failed** (329 on
`settlement_integration` + 19 alias-DB files on `settlement_t1broker`), real
PostgreSQL 16 + real subprocesses; per-finding red-first/regression evidence in
`reports/workstreams/R*.md`; the four pass-01 defect probes now fail as designed
and are preserved uncollected at `reviews/probes/historical_test_review_01.py`.

Learning experiment: deterministic-doubles A/B/C runs end-to-end with matched
tools, frozen lessons, and reconciled costs; `simulated=True` evidence is
non-releasable by construction. No learning claim is made.

Unmet gates: live inference endpoint/key/grant; runsc host for actual
containment; PostgreSQL 18 target; LEARN-6 statistics (refusal stands).
Details in `reports/VERIFICATION.md` and `reports/IMPLEMENTATION-STATUS.md`.

Design deviations: D-003..D-009 in `reports/DECISIONS.md` (all review-driven).

Reproduce: `uv sync --extra test`, then the two pytest commands at the top of
`reports/VERIFICATION.md` (fix-cycle section). Companion DBs used by recovery
tests derive from whatever `SETTLEMENT_TEST_DSN` names.

## Questions for review

1. Do the R01-001/002/004 fencing semantics (unique advance identity, `admitted`
   flag, dispatch generations, non-sendable reconcile) close the double-exposure
   and stale-authority gaps, or is a case still open?
2. Is lock-free bracketed-epoch revalidation (R3, decision D-007) an acceptable
   coherence mechanism, or is a stronger snapshot primitive required?
3. Does the out-of-process grader (R4a) plus bound release evidence (R4b)
   satisfy IF-6/LEARN-2/LEARN-7, given the stated filesystem co-tenancy limits?
4. Is the deterministic-doubles A/B/C now a fair protocol (matched tools,
   frozen retention), with only the live run outstanding?
