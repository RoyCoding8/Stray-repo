# Whole-repository engineering review and repair

Continue in this worker chat. The human authorizes a comprehensive inspection and repair of the current repository, with aggressive parallel specialists in isolated worktrees. Tokens are not a constraint. Your job is to discover, investigate, fix, integrate and verify; do not wait for the design reviewer to enumerate bugs for you.

**Priorities determine order, not exclusions. Complete all priority levels.** Earlier instructions limiting the work to a small smoke, one episode, a short finding list or previously identified defects are superseded. A prototype classification explains the impact of a defect; it is not permission to leave a confirmed in-scope defect unfixed. This is an exhaustive engineering assignment over existing functionality, not authorization to implement every future research stage.

## 1. Start and authority

Fetch `origin`. Merge `origin/codex/development-02-live-evidence` into your coordinator branch, currently `codex/implementation-development-02`, preserving concurrent work. Record the exact source revisions. Read `AGENTS.md`, `IMPLEMENTATION-WORKFLOW.md`, `COLLABORATION.md`, the maintained [roadmap](docs/design/REFINEMENT-ROADMAP.md), and the current design/specification entry points. Read available skills; assign specialists the exact relevant skill and design sections. The assignment must remain understandable from committed files when local skills are unavailable.

Ordinary commits and pushes to the owned branch are authorized. Use the repository's private Git identity; ensure both author and committer remain private. Do not print credentials, account-specific remote URLs or old personal identities into reports. Do not rewrite history, force-push, overwrite another owner's branch or modify an unrelated checkout. No model restriction is imposed on your specialists: choose their capabilities and division of work yourself.

Read the earlier reviews, workstream reports and live evidence as leads and historical claims. Independently assess them. Neither a prior fix label nor a green probe makes a subsystem exempt. The [live evidence assessment](reviews/DEVELOPMENT-02-LIVE-EVIDENCE.md) and [earlier focused prompt](WORKER-LIVE-EVIDENCE-PROMPT.md) contribute concrete obligations to this larger assignment; their old scope/run-count caps do not apply.

Continue autonomously through ordinary fixes and engineering choices. Record material decisions with their rationale. Escalate only a genuinely missing external authority/resource or a core semantic contradiction that cannot be resolved from the human's goal and current design. Continue independent work while a question is pending. Cheap worker tokens do not authorize unlimited external inference, relaxed containment or broader privileges: live campaigns still need explicit finite grants and authorized profiles.

## 2. What completion covers

Inventory every tracked first-party implementation, entry point, script, migration, test, fixture, configuration example, packaging/installation path, UI component and active document. Include Git-ignored design inputs only if available and relevant; no new worker should need an unavailable local file. Check generated or third-party assets through their provenance, generation and integration rather than pretending to audit every dependency's internals. Inventory optional integrations, disabled features and deployment claims too. An unavailable runtime is a verification boundary to investigate and report, not a reason to skip its source and contract review.

Maintain a coverage matrix with: subsystem and files; supported behavior/invariants; incoming and outgoing boundaries; owner; techniques used; evidence; findings; verification limitations; final disposition. Include cross-module journeys as separate rows. A file being opened is not evidence that its behavior was understood. Every first-party file must belong to an assessed row; report omissions and justify genuinely inapplicable categories. Reconcile the matrix against the final tracked tree after integration, including newly introduced files.

Keep a findings ledger with stable IDs, trigger, expected and actual behavior, consequence, root cause, affected callers, priority, owner, reproduction, fix revision and final verification. Use dispositions such as confirmed/fixed, rebutted with evidence, intended behavior with rationale, or externally blocked with exact missing prerequisite. Do not convert an untested suspicion into a confirmed defect. Do not close a confirmed bug by relabeling it a prototype limitation. Group shared causes rather than manufacturing many IDs for one defect.

Inspect and fix current behavior all the way through its intended contract. If a needed fix crosses an architectural seam, repair the seam and record the change. Do not build speculative infrastructure or the pending autonomous-agenda, adaptive-team and learner-revision mechanisms merely because they appear in the roadmap. Explain a conflict with an existing design contract explicitly; do not silently weaken the contract to fit the implementation.

## 3. Ranked priorities — work through every row

| Order | Review priority | Typical consequences to investigate |
|---|---|---|
| P0 | Authority, irreversible effects, data integrity and evidence integrity | Unauthorized execution/access, escaped generated code, unbounded spending, lost durable state, duplicate external effects, forged or misattributed evidence. |
| P1 | End-to-end functional and experimental correctness | Intended paths fail, wrong candidate is used, inputs are recorded but not delivered, stale state changes decisions, grading or billing is misinterpreted, a comparison cannot support its conclusion. |
| P2 | Recovery, concurrency, integration and operational reliability | Restart/retry/cancellation races, stranded liabilities, checkpoint inconsistency, incompatible interfaces, lifecycle controls that do not take effect, unsupported deployment behavior. |
| P3 | Test quality, reproducibility, observability, performance and operator usability | Weak oracles, flaky checks, missing effective configuration, unreplayable evidence, resource growth, confusing or inaccessible controls, broken installation/examples. |
| P4 | Maintainability, simplicity and documentation consistency | Duplicated rules, misleading names, dead paths, unnecessary layers/configuration, brittle fixtures, stale guidance and examples. |

Use consequence to classify; a test or documentation defect can be P0/P1 when it hides a dangerous or scientifically invalid result. Advance lower-priority work in parallel where ownership and dependencies allow it. Neither this table nor the techniques below limits what you may discover.

## 4. Review mindset

1. **Trace effects, not reassuring names.** Follow a user request or autonomous action from entry to durable state, actual dispatch, external effect, receipt, reconciliation and later consumption. Find alternate callers, direct lower-level access and fallback routes. A function called `verify` or a row called `bound` proves nothing by itself.
2. **Separate claims from observations.** At each boundary compare what was requested, configured, admitted, sent, returned, checked, consumed, settled and reported. Carry identity, version, unit, scope and provenance across the entire chain. Look for a true local fact being used to justify a stronger global claim.
3. **Attempt to falsify the contract.** Ask what smallest realistic input, failure or interleaving would make the promised behavior false. First understand the intended positive path, then attack it. Fail-closed behavior is incomplete if authorized valid work can never finish.
4. **Question both implementation and test oracle.** Tests may duplicate the same misconception as production code. Derive expected behavior from the contract and an independent example. Treat a fix that requires changing many assertions as a signal to understand their semantics, not as automatic evidence for or against the fix.
5. **Follow a root cause through every caller.** Search analogous paths, sibling implementations, old adapters and error branches. Repair the shared rule at its proper boundary; update all callers and examples. Avoid a named-test patch that leaves equivalent behavior broken elsewhere.
6. **Be adversarial about your own fixes.** After a patch works, try a valid case it might wrongly reject and an invalid case it might still accept. Independently review the merged result. Test quantity, confident reports and a clean merge are not correctness evidence.
7. **Keep distinctions that affect decisions.** Unknown is not zero; dispatched is not observed; recorded is not delivered; successful execution is not task success; task success is not transferable improvement; a fake sandbox is not containment; an inconclusive experiment is not a broken experiment.
8. **Simplify after understanding.** Prefer existing mechanisms, native constraints and small coherent functions. Delete accidental complexity without deleting authority, recovery or evidentiary obligations. Keep justified complexity where the failure model requires it.

## 5. Techniques and coverage checklist

This is a coverage checklist, not a prewritten bug list. Apply every category to the relevant code, add categories as the architecture demands, and record why a technique is inapplicable instead of silently omitting it.

### A. Build a behavioral map

- Enumerate CLI/API/UI/background entry points and the production call graph between them. Trace both a fresh install and an existing resumed system.
- Extract invariants and state transitions from the committed contracts. Map each to its enforcing location, persistence rule and observable evidence. Locate rules duplicated across modules or enforced only by callers.
- Trace complete journeys: initialize/authenticate; discover/infer; admit/reserve/dispatch; supervise/cancel/reconcile; ingest/verify/invalidate evidence; diagnose/construct/check/freeze/evaluate/release or reject; restart and use a retained method or incumbent; repair; checkpoint/restore; operator inspection and control.
- Trace positive, negative and empty paths. Exercise no candidates, no evidence, exhausted allocation, unavailable prerequisite, old versions, duplicate requests, partially completed work and concurrent operators.
- Read actual library integration points and supported dependency contracts when uncertain. Verify against the versions in the lock/environment and authoritative documentation, not recalled behavior. Record version-dependent assumptions.

### B. Challenge boundaries and representations

- Follow identifiers, hashes, generation/epoch counters, scopes, timestamps, monetary units, token counts and enum meanings through serialization, storage, subprocesses and adapters. Probe absent/null/empty/zero/negative/extreme values and inconsistent combinations.
- Check canonicalization and byte binding. Verify that the exact accepted data is the data dispatched and later consumed. A digest of one object does not authenticate a different object with the same descriptive label.
- Probe malformed/truncated/oversized payloads, unexpected fields or statuses, mixed response shapes and partial provider output. Distinguish transport completion from semantic validity.
- Inspect environment/config precedence, startup validation and runtime overrides. Verify that effective settings, including limits, protocol, model identity and profile, reach both execution and the evidence manifest.
- Compare adjacent modules' definitions of success, failure, pending, stopped, released, compatible and settled. Find fallbacks that silently change the meaning of a request.

### C. Exercise state, concurrency and recovery

- Draw the relevant finite state transitions; generate or hand-enumerate invalid transitions and interrupted prefixes. Check durable invariants after each transition, not just the final return value.
- Inject failure immediately before and after every significant durable/external boundary: reservation, commit, claim, launch, send, receipt, acknowledgement, settlement, release, invalidation and checkpoint.
- Use controlled barriers to force races instead of relying on sleep timing: duplicate delivery, simultaneous admission, stale sender versus new generation, stop versus launch, revoke versus consume, restore versus active worker, retry versus late receipt.
- Kill a real process and resume in a fresh process with only persisted state. Test whether recovery repeats an effect, loses ownership, skips verification or strands capacity. Distinguish safe retention of uncertainty from permanently inaccessible recovery.
- Examine transaction scope, lock order, isolation assumptions, nested operations, deadlocks, leases and fencing. Check races across processes and database connections, not only tasks sharing a Python object.
- Reconcile journal, outbox, reservations, liabilities and receipts under retry/duplicate/out-of-order delivery. State precisely which effects are idempotent and how ambiguous external outcomes are reconciled.
- Check all waits and retries for total bounds, cancellation, backoff and error classification. Study wall-clock changes where elapsed-time assumptions matter. Ensure cleanup and error paths do not mask the primary failure or incorrectly acknowledge completion.

### D. Inspect authority and isolation

- Follow authentication, operator grants, capability scope, resource limits and revocation to the final point of effect. Probe alternate entry points, replayed credentials/receipts, stale generations and confused-deputy behavior.
- Inspect generated code execution, imports, subprocess arguments, working directories, mounts, filesystem traversal/symlinks, environment inheritance, network access and output collection. Keep candidate code outside the trusted host process.
- Verify actual process-tree ownership and termination, writable space/output limits and sandbox launch configuration with real supported runtimes when available. Distinguish configuration intent, shim behavior and observed containment.
- Check that fallback paths cannot widen authority, pick a different model/profile silently, bypass evaluation or turn an unavailable containment profile into unrestricted execution.
- Inspect UI/server trust boundaries, inert rendering of untrusted text, secret exposure in errors/logs/artifacts and isolation between trials. Treat private Git access as separate from permission to commit credentials or personal machine state.

### E. Validate experimental meaning and model integration

- Establish trusted positive and negative controls for solver input/output, grading, procedure application, selftest and candidate selection. Include an independently known correct specimen through the real public path. Ensure controls can detect a broken grader as well as a bad candidate.
- Classify failures at the earliest responsible stage: provider/auth/transport; timeout/truncation; output ABI or parser; compilation/import; execution; grading; binding/evidence; actual wrong answer. Preserve raw evidence sufficient to review that attribution.
- Trace actual model-visible bytes. Stored references, packet hashes and metadata do not prove that relevant observations, opposing evidence or the required procedure interface entered the request. Check budget overflow behavior and unsupported claims of freshness or completeness.
- Verify development/selection/test splits, frozen policies, candidate identity, grading assignment, contamination/exposure records and post-freeze mutation refusal. The same rule must hold through repair, retry and subsequent use.
- Assess baselines and ablations for what they actually do. Hold the intended controls equal and report deliberate differences. Do not describe a lookup baseline as a learning baseline or a no-op control as removal of an active method when none exists.
- Include every consumed resource and failed attempt in the declared comparison scope: proposal/diagnosis, construction, checks, grading, retries, rejected candidates and later use. Report measured provider usage, external billing knowledge, internal reservation/debit and attribution separately; reconcile their union without double counting.
- Freeze runnable configuration and campaign limits before drawing comparisons. If discovery changes the protocol, record the change, separate exploratory observations and use a newly frozen comparison. Do not keep tuning the benchmark or rerunning until a preferred result appears.
- Preserve sanitized raw requests/responses, grader inputs/errors, binding and settlement evidence, effective configuration and source state sufficiently to reproduce the conclusion. Use manifests/hashes and explicit redactions. Include failed/partial episodes. Do not delete the sole explanatory artifacts during cleanup.
- Verify a released method's actual later routing in a fresh process if live release occurs. If no live release occurs, test that machinery with clearly labeled deterministic controls and leave the live claim open. Negative or inconclusive learning is an acceptable empirical outcome.

### F. Make tests capable of finding different mistakes

- Prefer public-path integration tests for semantic contracts, focused unit tests for boundary cases, and real database/process tests for their actual guarantees. Keep cheap doubles, but document what they cannot establish.
- Use property-based or state-machine checks where state/sequence spaces matter; metamorphic checks where transformations should preserve or change outcomes predictably; differential checks against a trusted reference where one exists. Choose methods for the contract, not a tool quota.
- Check that tests fail under a plausible violation, using an isolated local mutation or controlled faulty double where useful. Do not commit intentionally broken production behavior. Test independent oracles rather than copying the implementation's decision table verbatim.
- Exercise repeated runs, fresh processes, schema upgrades, empty and nonempty databases, version changes and concurrent executions. Ensure fixtures do not supply privileged internal state that ordinary callers cannot obtain.
- Audit existing probes and test retirements. Preserve an explicit old-obligation to new-test correspondence. Demonstrate the replacement still detects the defect class; do not retire a test solely because a changed signature made it inconvenient.
- Investigate flakes instead of naming them away. Separate an invalid observation window from an actual termination/recovery defect using controlled synchronization and production evidence. Fix confirmed causes. A rerun passing is evidence about intermittency, not proof of correctness.
- Inspect skips, expected failures, fixture teardown, order dependence, test pollution, hidden network calls and environment requirements. Make missing required infrastructure visible; distinguish unavailable optional qualification from a successful test.

### G. Review operations, performance and the human interface

- Verify clean install, locked dependency resolution, supported Python/database/runtime versions, migration from existing populated state, backup/restore and runnable documented commands. Check packaged artifacts and included resources if packaging is part of the supported surface.
- Examine configuration examples, launch/cleanup scripts, ports, path handling, permissions and platform claims. Exercise the actual documented deployment profile where the environment permits; never infer another profile from it.
- Look for unbounded rows/files/processes/queues, leaked connections, growing prompts/evidence, N+1 queries, excessive polling and work that scales with all historical state. Measure representative workloads before choosing an optimization and preserve semantics under limits/backpressure.
- Check operator visibility of active steps, blocked prerequisites, costs, unresolved operations, failures and lifecycle controls. Verify controls cause server-side effects and survive refresh/restart; ensure labels, empty/error/loading states, keyboard access and validation are usable and truthful.
- Check diagnostics can locate a failure without exposing secrets: correlate operation/episode/candidate identities, show effective limits and stop reasons, preserve causal errors and make recovery options actionable.
- Review logs, metrics and report queries against source-of-truth records. Test their treatment of partial, duplicated, stale and missing data. A polished status page must not turn unknown or refused work into a green success.

### H. Simplify and reconcile the repository

- Search duplicated invariants, repeated data shapes, dead branches, obsolete adapters, unused configuration, one-caller wrappers and speculative abstraction layers. Remove or consolidate where the supported behavior becomes clearer and verification can preserve it.
- Keep code compact and explicit at important boundaries. Use functions and data-driven structure for genuine repetition; avoid dense tricks that obscure state or effects. Follow repository style, including no new inline comments. Record non-obvious decisions in the appropriate design/workstream document.
- Review naming, public contracts, module ownership and dependency direction. Make interfaces carry the information actually required to enforce their obligations; do not hide crucial authority or provenance in ambient state.
- Reconcile production code, tests, fixtures, migrations, manifests, examples and active documentation together. Preserve historical evidence with correction notes instead of retroactively rewriting what a previous experiment observed.
- Check repository hygiene, accidental credentials/identity details, temporary artifacts and reproducibility. Keep intended evidence; remove only owned temporary resources after preservation and verification.

## 6. Parallel execution and integration

Create a task graph and coverage matrix first. Split by coherent ownership and assign separate cross-cutting reviewers for end-to-end contracts. Use as many useful independent specialists/waves as the machine supports. Do not make several agents blindly repeat the same full repository read. Each specialist receives exact paths, contracts, techniques, verification responsibilities and handoff outputs, plus instructions to report cross-boundary findings to the responsible owner.

Use isolated Git worktrees/branches and separate mutable test resources: databases/schemas, artifact roots, workflow identities, ports and processes. The coordinator owns shared contracts, migration numbering, integration, active status documents and the final report. Negotiate interface changes before parallel callers drift. Isolated worktrees do not provide runtime containment.

Monitor progress and inspect actual work when an agent stops or reports nothing. Reclaim abandoned work honestly. Review every patch and its tests, including the caller consequences. Give critical fixes an independent reviewer; do not use the author's own assurance as the only check.

After each integration wave, rerun the affected combined paths and reconcile shared interfaces, migrations, fixtures and report claims. Branch-local evidence can become stale after another lane changes a contract. Inspect semantic integration even when Git merges cleanly. Reconcile test counts by actual collection and results, not arithmetic that merely looks plausible.

Finish with independent passes over the merged tree: one organized by user/agent journeys and one by failure modes/trust boundaries, with attention to the interactions introduced by fixes. These passes may discover new work; fix it and recheck the affected contracts. The worker owns this loop without requiring an external review after each patch. Do not claim mathematical exhaustiveness: completion means the declared coverage is complete and discovered obligations have been resolved, not that no undiscovered bug can exist.

## 7. Deliverables and completion gate

Keep `reports/PLAN.md` current and create `reports/ENGINEERING-REVIEW.md` as the concise index to the coverage matrix, findings ledger and specialist evidence. They may live in existing workstream files; do not duplicate a large narrative across many reports. Update implementation status, verification, decisions and the review request with accurate scope and pointers.

Completion requires:

- Every first-party inventory row and cross-module journey assessed, every applicable checklist category covered, and newly discovered surfaces included.
- Every confirmed in-scope defect at P0 through P4 fixed and verified. External blockers carry exact missing prerequisites, attempted checks and remaining claims; they remain open and prevent an unqualified statement that the entire assignment is complete. Intended behavior and rebuttals have evidence.
- Targeted regressions plus the appropriate full suite on the final integrated source state. If later code changes invalidate that evidence, rerun affected checks and the final gate as appropriate. Investigate failures; do not repeatedly run an unchanged suite merely to obtain a green screenshot.
- Real-runtime/live checks wherever the available environment and explicit grants support them, with separate labels for doubles, real components, live providers and unresolved qualifications. No arbitrary success requirement for learning experiments.
- Reproducible, sanitized evidence preserved before cleanup, including effective configuration and exact source revision or source-tree fingerprint for runs performed before a reporting commit.
- An independent final integrated review and a clean ownership-aware cleanup. Never remove another worker's worktrees, databases or active resources. Verify the pushed remote commit equals the local result.

Return: branch/commit; coverage summary; finding counts and dispositions by priority; the important changed behaviors and architectural decisions; exact verification outcomes; links to evidence; remaining externally blocked claims; cleanup status. Keep the human-facing message short; put the exhaustive record in the repository.

The design role can continue formalizing the agenda experiment while you work. Your report supplies trustworthy engineering and experimental evidence for that next stage; it need not deliver a positive learning result or implement the future agenda policy to satisfy this assignment.
