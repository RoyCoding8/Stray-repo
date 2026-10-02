# Investigation Learning 02 final handback

**Source and scope.** Exact source tip is `f73127fa02a50ba456be92e0f68a5d9aaf1f26d6` on local branch `wt/invl02-final-reports-2`, based on `f73127f`. This is a report-only refresh. No source or evidence was modified. No live, network, provider, or database call was made.

## Current verification

**Correction, observed 2026-09-24.** This handback recorded **616 passed, 32 skipped** as the final complete affected gate. Re-running the exact file list below at tip `2d12d56` gives **135 passed, 16 skipped**, and that list collects only 149 tests. The 616/32 figure is a stale or mis-scoped worker aggregate and is not reproducible from the cited list. Treat this section as historical worker prose, not a verified gate. The exact affected test list from the final repair wave was:

```text
tests/test_ag01_demo.py
tests/test_ag01_experiment.py
tests/test_broker_dbos.py
tests/test_final_provenance.py
tests/test_frontier_atomicity.py
tests/test_inv_b1_contracts.py
tests/test_m2_frontier_inherit.py
tests/test_provenance_authority.py
```

Destructive fixtures were not authorized in that run. Current test database safety requires explicit `SETTLEMENT_TEST_DSN`, a matching `SETTLEMENT_TEST_TRUNCATE_DSN` for destructive fixtures, and explicit `INV_B1_DSN` for the INV-B1 contract gate.

The final frontier evidence worktree gate for the selected frontier gate passed **430** tests with **0 skipped**. This is separate from the corrected affected gate above. A separate 15-minute full-suite attempt at `f73127f` used disposable DSNs and timed out before pytest printed a summary. It is not a pass, a failure, or a green full-suite result.

## Current live boundary

Fresh route discovery at `f73127f` accepted the 550B route. The record is `reports/evidence/invl02-route-discovery-550b-r3/route-discovery.json`, SHA-256 `b41189edd87a28b782cdd723f61f716b0b526f22cbc862e49243bf2897e0904a`.

Fresh output freeze is `reports/evidence/invl02-output-shape-550b-r3/freeze.json` with SHA-256 `5ebc5cfad4a10b8ab912bed36c33c140c6416b4613ac57dfe78f57217a2ef4e1`. Fresh preflight is `reports/evidence/invl02-output-shape-550b-r3/preflight.json` with SHA-256 `0ed8adde9160e909384487ab8b1b2f215509744bac774037cf27b9de0f9a4fc1`.

`run-output` at `f73127f` was refused before dispatch with exit 3 because a fresh human grant is required. No model inference occurred. The current route is accepted, but the live study is grant-blocked. Do not retry the historical output-shape directory.

Historical E0 limitations remain unchanged and retention-only. Historical E12 limitations remain unchanged and incomplete. E3 remains unavailable and unrun. The current evidence does not support utility, transfer, or recursive improvement.

## Next decision

Obtain a fresh human grant before any new live `run-output` dispatch. The current route is accepted, but the live study remains grant-blocked. The remaining handback blocker is a fresh human grant plus the 15-minute full-suite timeout. If a new study proceeds, keep its protocol, source identity, route evidence, resource bounds, and result classes separate from historical E0 and E12 evidence. Run E3 only if a genuinely eligible model revision has model-response provenance, exact-digest binding, a durable post-restart child citation of the same executable digest, and a usable result. Retained-only, digest-mismatched, and authored or control-derived bytes are ineligible. Keep Stage 9 open. Stage 10 is not completed by this batch.

The systematic-repair workflow artifact is `/home/ubuntu/.agents/skills/parallel-bugfix/SKILL.md`. It is a workflow record, not a product capability.
