# EC02 full completion assessment

Reviewed worker tip `fe41fb6f7e80f4afbfe67afdf89a20366761b42f`, including all changes since review `d2d8924`, on 2026-09-15. M4 lane `182d62c`, merge `3c032bd`, was the starting scope; the human expanded the review to the whole assignment. This assessment supersedes milestone completion labels, not preserved historical evidence. No production implementation was changed by this review.

## Verdict and task list

**The original assignment is not complete.** Useful helpers and fixture checks have been added, but their integration into the public campaign remains missing. This is an implementation/inference gap, not evidence that executable learning or general autonomy failed.

| Milestone | Assessment at reviewed tip |
|---|---|
| M0 recovery/contracts | Partial. Historical twenty-versus-twenty-four discrepancy is explicitly recorded; surviving live receipt preservation is worker-reported. Durable authority and destructive-test protection remain inadequate in the integrated path. |
| M1 complete execution | Not complete. Public entry creates a fake adapter; child factories return unchanged snapshots; interpreted A proposals do not govern the controller; accounting helpers are not wired into cell evidence. |
| M2 integrated qualification | Partial fixture coverage, not all EC-01–10 obligations. Tests inspect individual helpers or completed episodes where the assignment requires actual response-to-effect flow, interrupted execution and fresh-process use. |
| M3 acquisition/disposition | Live blocked in the reported worker environment. New `none` cases come from doubled/author-controlled tests, not a new live acquisition campaign. Missing credentials cannot validate the old lost-evidence campaign. |
| M4 frozen study | Not run as the commissioned live comparison. The 144 doubled fallback cells are apparatus checks. With no acquired candidate, the original design calls for no-acquisition/fallback disposition rather than a full learned comparison. |
| M5 delivery | Not complete: production reproduction, integrated evidence reconstruction and architecture conclusions remain open. |

- [x] Read M4 report, all eight tests, production delta and relevant callers.
- [x] Expand to all completion commits, reports and integration seams.
- [x] Execute independent non-DB probes and focused existing tests.
- [x] Separate new regressions, continuing integration gaps and overclaimed verification.
- [x] Design the next autonomy experiment without requiring a positive EC02 result.
- [ ] Worker closes the shared execution/evidence gaps and completes the applicable live/blocked disposition.
- [ ] Worker implements and qualifies the bounded autonomous-development continuation in the accompanying assignment.

## Standards assessment

No separate style finding blocks this batch. The important structural failure is duplicated or unused behavior: new canonical accounting and resume helpers coexist with an entry that still uses old shortcuts. Repair the shared caller path and delete superseded shortcuts. Do not prioritize formatting, comment removal or a net-negative line-count target over restoring the intended behavior. The worker's PLAN makes deletion counts sound like acceptance; behavioral correctness is the acceptance condition.

## Specification and behavior findings

### ECA-01 — P1: the public campaign cannot run the claimed live treatments

`experiments/coord02/entry.py:640–692` constructs `FakeGatewayAdapter` regardless of mode and discards it after discovery. `run_panel:544–576` has no gateway/model argument forwarded into its cells. `arm_child_factory:297–327` accepts only FIXTURE and returns unchanged source bytes; the identically behaving `live_child_factory` does not perform inference. Consequently an endpoint/key cannot make this CLI a live repair study.

A has a further causal break: `arm_decision:279–294` requests a model proposal, but `run_cell:484–509` selects a generated policy program without delivering that proposal into its state. A's prompt also uses current task source, not the acquired `package_text`. The independent probe intercepted only external endpoints: different A responses (`stop` and `unsupported`) produced identical controller program bytes and identical unchanged repair bytes. F's `coupled` observations are computed but unused; its partition condition is file count/nonempty dependency versions, not demonstrated public evidence of independence. These remain ECR2-01 integration obligations, despite the new helper-level tests.

Required closure: one production path with actual admitted model work, actual interpreted proposals, a meaningful frozen F and direct L execution. Test input/output substitution at the public entry, including successful and unsuccessful model-produced repairs. Removing reference solutions without installing the real constructor is not completion.

### ECA-02 — P1: measured/settled cost claims still use constants

`entry.py:364–390` returns 100 input tokens, 20 output tokens and one model call without reading operations, and substitutes a run ID if step receipts are absent. `write_evidence:619–622` assigns a whole cell's costs to each referenced operation. The new canonical records in `schemas_evidence.py` therefore do not make the panel accounting canonical. The probe confirms identical model usage at zero and fifty policy steps.

`tests/test_coord02_m4_frozen.py:521–533` checks that fields are numeric and receipts nonempty; that accepts the constants. The report's “real costs,” “settled” and “no unresolved” claims are not established by those assertions. Connect the production union and settlement/liability checks; test distinct usage, shared/replayed operations and missing usage. This is the original ECR2-02, not a new peripheral audit request.

### ECA-03 — P1: preserving scheduled L identity is incomplete because staging erases fallback attribution

The M4 `scheduled_arm` change correctly avoids S/L identity collisions. However, `stage_record:416–442` replaces `trial.failures` with grader failures whenever a tree can be staged. Its line 433 copies the original list only when there is no tree and the trial failed. The M4 report's unconditional preservation claim is incorrect.

The probe supplies an explicitly marked L/S-fallback trial and intercepts the protected grader with a labeled success double. The actual staging function emits `arm=L, outcome=success, failures=[]`. The none package remains a clue, but the explicit executed treatment has disappeared. Keep requested arm, executed treatment and fallback reason as persistent provenance independent of grading failures; cover successful and failed staged trees as well as no-tree failure. Do not repair this by weakening the grader.

### ECA-04 — P1: the resume/transfer battery does not close continuity

`schemas_evidence.resume_plan:536–550` compares both procedure and `frozen_digest` to `freeze.package.digest`. Production selection instead writes `package_digest`/`entry_digest` (or no digest for none); `stage_record` uses `frozen_digest` for a successful candidate tree, or empty for failure. These are different identities. The actual staged failed record is classified to run again; a fabricated record containing only matching invented digests and an outcome is skipped.

The M4 test line 311 asserts zero skips for its real evidence, then lines 354–371 manufacture matching records to prove skipping. Its reconciliation operation is newly created and unrelated to the pending cell; its reruns use fresh random episode IDs. The transfer test loads and hashes S bytes in a child process, but executes no task there; all 48 panel cells were run in the parent process. These are useful helper tests, not interrupted same-campaign resumption or fresh-process retained execution. Verify the actual public resume/use entry against its own unmodified saved records and operation identities.

### ECA-05 — P1: authority and evidence protection are still caller-dependent

`experience.acquire:1152–1156` creates a new UUID, seeds a new construction allocation and defaults to a new prefix each call. `ConstructionLedger` counts operations by that prefix; it does not enforce a durable campaign identity across normal re-entry. `request_call:579–595` separates its count check from admission, and ignores the unresolved list returned by `_reconcile_pending`. Hydrating one explicitly reused prefix is a partial improvement, not the requested durable campaign contract. Bind campaign authority before either development or construction and verify concurrent admission/re-entry against the same root.

The M4 fixture first applies migrations and calls `designate_db(...disposable)` before `prepare_disposable_db`. `designate_db:683–695` unconditionally appends the new designation; `_designation` selects the latest. Thus the test can relabel a prior evidence DB disposable before checking protection. Its DSN substring check does not satisfy the explicit requirement to protect by resource purpose. Use exclusively created disposable resources, and refuse existing evidence designation before test mutation. Reproduce against an isolated sentinel, never surviving live evidence.

### ECA-06 — P1: executable validity and task success are conflated during selection

`experience.validate_on_development:1046` sets `valid_execution = bool(solved or fallbacks)`. A valid policy that executes and admits work but whose repair worker fails every task is consequently described as “neither candidate executable” by `select_candidate:1071–1074`. The design explicitly allows weak/constant executable candidates and ranks quality separately. Preserve parse/profile/execution validity, intervention outcome, task quality and fallback as distinct observations. Do not manufacture failure-to-acquire by using failing fixtures, or manufacture a valid candidate by counting fallback success alone.

## What M4 did improve

The checker loop-variable rename fixes actual panel-filter shadowing. Keeping the scheduled arm in trial identity is also correct, subject to ECA-03. Coverage of schedule membership, labeled none handling and record shapes is useful. Preserve it as fixture evidence; the presence of 144 records is not 144 live or learned trials. Do not rerun those 144 fixture failures merely to increase confidence in learning.

## Verification boundary

The [independent probe](probes/ec02_completion_review.py) runs real entry/staging/resume/accounting functions while explicitly intercepting database/model/join endpoints. It executes no acquired code, provider calls or database mutations. Its [observations](probes/ec02-completion-observed.json) reproduce ECA-01–04 at `fe41fb6`. ECA-05/06 are source-traced obligations, not independently reproduced real-DB concurrency results.

Five selected existing checks passed across focused runs: trial record round trip, checker bridge, cost-union deduplication, unknown cost and joint promising rule. Initially four passed and checker bridge failed twice because this Windows checkout translated the pinned manifest's LF bytes; writing that file from the exact `fe41fb6` Git blob made the bridge pass (1 passed, 4.47s). The blob hash matches its committed pin. No freeze was regenerated or evidence amended; checkout handling is a local verification qualification, not a new study finding. The file was restored afterward.

The eight M4 real-PG tests and the full runtime suite were not rerun here; their pass counts remain worker-reported. The review did not access the worker's live DB or provider. No claim of completed live acquisition follows from this review.

## Architectural consequence

Do not redesign the learner because a fake gateway returned empty or unchanged sources failed grading. Close the shared execution/evidence path once, close EC02 under its actual candidate/grant outcome, and reuse that path for [Autonomous Development 01](../docs/design/AUTONOMOUS-DEVELOPMENT-01.md). A positive SWE-team result is not a prerequisite for testing system-chosen investigations. The next batch is specified in [the consolidated worker assignment](../docs/HISTORY.md#worker-ec02-closure-and-autonomous-development-01).
