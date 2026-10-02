# Implementation workflow

This is the shared workflow. The current assignment lives in WORKER-PROMPT.md; status lives in reports/PROJECT-LEDGER.md.

## Start and ownership

Inspect Git status, current branch, worktrees and active processes before changing anything. Preserve unrelated changes and receipt anchors. Use the repository's private author identity. Fetch without checking out over someone's work.

Keep the task graph and ownership in reports/PLAN.md. Keep per-lane evidence in reports/workstreams/. Update the project ledger at meaningful checkpoints; do not copy the whole plan into it.

For parallel implementation, use the installed git-worktree-discipline skill. Reference and apply relevant skills such as TDD, root-cause repair and prove-it-works; do not mechanically invoke every skill. Jev is unavailable and must not be called.

Give each delegate a base revision, exclusive worktree, owned paths, behavioral contract, acceptance checks and disposable database namespace. The worker may use its available models; the researcher's earlier Luna restriction is not a restriction on this implementation harness.

Use 12–16 useful parallel agents when the harness supports them, with further queued review and experiment lanes. Concurrency must respect actual CPU, database and gateway capacity. Do not create agents just to reach a number. Keep one integration writer and one live-campaign authority; lanes must not share mutable files, databases, evidence roots or grant counters.

A stream timeout is not proof that an agent died. Check its process, checkout and output before reassignment. Transfer ownership explicitly before a takeover.

## Build and integrate

1. Trace the real call path and reproduce a material defect before fixing it. Prefer one repair at the owning boundary and delete branches it supersedes.
2. Use cheap red/green behavioral regressions for defects. Never weaken assertions to make a lane pass; explain contract corrections against the governing behavior.
3. Review each lane's full diff and evidence before merging. Merge serially with --no-ff and rerun affected checks on the integrated tip.
4. Resolve shared-contract changes before dependent lanes start. If a late change affects another lane, revalidate that dependency after integration.
5. Pin tested source before a campaign. Keep unrelated maintenance off that campaign's source and freeze.

Do not add a second evaluator, broker, grant authority, generic plugin framework or alternative execution path to avoid repairing the existing one.

## Independent checks

Use separate contract, integrated-behavior and evidence-recomputation passes. Reviewers should write their own candidate bytes and counterexamples rather than only run the author's fixtures.

Recurring checks that matter here:
- Trace response bytes through retained artifact, executed program, admitted effects and graded result. STEP and ENTRY each match their own bytes; their digests need not equal each other.
- Separate real calls, fixtures, wrappers around authored solvers and independent construction opportunities. Different record IDs are not replication.
- Keep transport failure, empty response, invalid program, poor task result and unknown accounting distinct. Unknown is not zero.
- Use development-only selection, sealed evaluation and comparable controls. Freeze before effects, not after looking at results.
- Ensure the new regression actually ran. A skipped regression cannot validate its fix.
- First obtain a clean baseline, then measure each tamper test's added failure. A broken baseline does not prove that tampering was caught.
- Export the receipts and inputs needed for offline recomputation before deleting their database.

## Verification and cleanup

Run final affected gates on the merged source. Broaden testing for changed dependencies and unresolved concerns, not to chase test counts. Report exact commands, revision, environment, duration, failures, skips and interruptions. Never sum separate runs into a fictitious full-suite pass.

Long runs need progress and a sensible diagnosis when they stall. Use isolated disposable databases and explicit DSN configuration. Do not silently skip integration checks or disable child limits to make Windows pass a Linux execution contract.

Clean up only owned, inactive scratch worktrees, branches, processes and databases. Enumerate and verify targets first; preserve unique commits and unresolved evidence. Prefer managed worktree tools when available. A database's age is not proof that its owner finished. Do not drop live receipt anchors until their required exports verify.

## Delivery

Keep one current completion report with requirement-to-evidence mapping, separate verdicts, remaining work and the next architectural decision. Put bulk raw output in evidence files. Update PLAN and the project ledger without repeating the report.

Commit fixes additively with finding IDs. Push normally and verify remote equality. If a reviewer publishes a separate branch, merge it deliberately rather than resetting over active work. State the tested source tip separately if later commits contain only documentation or exports.
