# Worker: complete the stage 9 consolidation cycle

This is a complete assignment for a fresh chat. Fetch `origin/codex/stage-09-complete-handoff`; it contains implementation `1d90c2e`, review `0e142be` and this contract. Inspect status and ownership, then create `codex/implementation-stage-09-consolidation` from the fetched handoff. Preserve unrelated work. Use an isolated owned worktree, not another coordinator's checkout. Commit additively with author and committer `Nightjar <nightjar@authors.invalid>`, push through `origin`, and verify remote equality. No force-push or private remote URLs in reports.

Read in order: `AGENTS.md`; `docs/design/REFINEMENT-ROADMAP.md`; `reviews/STAGE-08-09-1D90C2E-ASSESSMENT.md`; `reviews/STAGE-09-BOUNDED-AUDIT.md`; `docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md`; `IMPLEMENTATION-WORKFLOW.md`; `COLLABORATION.md`. The implementation contract supersedes conflicting proposals in the earlier architecture draft. `docs/design/ARCHITECTURAL-DIRECTION-2026-09-17.md` preserves the product direction.

The human asks for the full work, completed systematically. This assignment includes design concretization, implementation, integration, verification and delivery. Do not stop at a design document, one repaired helper, a lane report or a model's unusable output. Keep stage 8's accepted contract fix closed. The goal is a persistent investigation that can acquire, independently evaluate and reuse an executable revision to how it learns. A positive learning outcome is not required.

## Execute these milestones in order

### M0. Establish the plan and concrete contracts

Verify your baseline and the accepted stage 8 checks. Inspect actual callers before moving code. Record M0–M7 in `reports/PLAN.md` with owned files, dependencies, commands and current status. Translate N1–N6 of the new implementation contract into concrete signatures, records, versioning, state transitions and acceptance checks. Reuse existing machinery where it truly supplies the behavior.

Update `docs/design/STAGE-09-ARCHITECTURE.md` to the selected contract. Map every claimed state field to storage and every effect to its trusted owner. Pin the evaluation/feedback boundary and policy ABI before downstream work. Do not leave competing architecture documents both claiming authority. A capable independent reviewer should challenge this plan against the contract before implementation; resolve ordinary design choices locally without asking the human to manage milestones.

### M1. Consolidate persistent investigation ownership

Implement N1 and the migration foundation of N6. One driver owns accepted actions, checkpoints, effect reconciliation and observations. Investigation identity is distinct from experiment labels. Preserve parent study authority, consumed/pending exposure and exact artifact versions. The currently delivered admission helper can report admitted for a reference-free protected-target proposal while a later execution fence refuses it. Carry that entire protection into the consolidated trusted path; do not delete the later guard just because the earlier function has an authoritative name.

Test real public run/resume, including interruption after acceptance and after an effect but before result incorporation. A new process must reconcile the same operation without duplicate effects or renewed limits. A database read of a pending row is not this proof. Complete the checkpoint/migration manifest changes required by any schema addition. Preserve other owners' databases and the historical evidence anchors.

### M2. Execute versioned policy artifacts

Implement N2: bounded child execution of `STEP(view,state)`, durable state transitions, actions through trusted admission, and model/tool requests as accounted broker effects. Do not run generated policy source in the host via `DecisionConsumer(proposer=...)`. Do not delegate admission, evaluation or grant mutation to that source.

Prove two independently authored policy controls produce different actual operations through the public entry under the same initial conditions. Also prove one unchanged policy behaves consistently after restart. Then connect a model constructor that returns policy source bytes under the same ABI, with source lineage, actual response digest, validation and bounded repair. Reuse the existing construction/execution infrastructure without disguising a fixture policy as acquired output. No hardcoded strategy menu is an acceptable substitute for executable returned source.

### M3. Separate feedback from assessment

Implement N3. Operational feedback can motivate investigation and revision. Sealed assessment content and judgments cannot enter policy or method constructors. An exposed assessment batch is no longer independent for descendants. Keep the historical AD01 protected-task guard intact under its original protocol; do not permit a global bypass to make the new revision demo run.

Use a real operational-use failure to open a persisted revision proposal. Test context construction with a hidden-answer perturbation and inspect the actual provider-bound request. The request must remain unchanged before any authorized reveal. Test exposure/descendant tracking, rejection of protected references and state isolation between matched assessment arms. Do not prove visibility solely by omitting a field from a fake packet.

### M4. Assess and bind a revision

Implement N4 for task methods and executable learning policies, reusing the same evidence/authority guarantees while keeping their artifacts and judges distinct. Freeze candidate bytes before assessment. Fixing the motivating task permits assessment; promotion follows the independent protocol, regression checks and resource rule.

Make active scoped bindings explicit. The current selector returns the first family match: appending a revision can leave the old method selected, while reordering the list changes it. Prove a successful bind selects and executes the revised bytes in a fresh process, a failed comparison preserves the old binding, and a stale concurrent bind cannot replace a newer version. Re-executing the same target with an intentionally different revision must not reuse the prior revision's settled use operation. Retry of one logical action must still reuse its own identity.

Deliver one complete deterministic cycle with doubles only at the provider boundary: permitted observation -> system policy chooses investigation -> method construction/check/retention or rejection -> later use -> operational failure -> constructed policy revision -> independent assessment -> bind/reject -> fresh-process continuation. Include the rejection/no-candidate cycle. Human-authored test policies prove machinery, not autonomous learning.

### M5. Replace the replay pseudo-experiment and build the prospective pilot

Keep the 28-prefix exact replay result as a conformance check. Do not run the previously proposed construct/stop support count as a learning experiment; its answer is encoded in the checker. Implement the prospective P0/P1/P2 study in N5. P1 is direct policy construction without experience; P2 receives permitted experience; P0 is the frozen incumbent. Same interfaces and construction allowance for P1/P2. Both candidates must come from returned model bytes when labeled live.

Prepare the bounded development/feedback episodes, candidate construction, twelve matched assessment episodes and sealed use tasks. Freeze identities, order, metric/resource rules, effective configuration, query/time/token ceilings and one study root before exposing assessment results. Derive worst-case counts from code and prove exhaustion/refusal before effects. The 100-model-call ceiling is not an instruction to spend 100 calls and not a fresh grant. Do not generate replacement episodes when an arm fails. Missing candidates are unavailable arms with a narrower result, not baselines rebranded as candidates.

Run the complete pilot deterministically through the public entry and an offline verifier first. If valid live authority and gateway configuration are already available for this new study, run it once within those limits, preserving honest negatives and unknown costs. Otherwise finish all code, controlled-provider qualification and evidence exports; return one exact command/cap-sheet request naming model, effort, study identity, protocol and required remaining allowance. Do not reuse the spent historical grant or infer authorization from free billing. Lack of live authority is not a reason to leave M6/M7 unfinished.

### M6. Independent integrated verification

Have a reviewer read the original requirements and the actual public entry before your verdict. It must supply its own valid policy/candidate and challenge effect execution, protected feedback, revision identity, selection, resume and evidence completeness. Give it an isolated database/worktree. Ask it to classify material findings, not produce a broad unrelated style audit. Rebut only with source or runnable evidence. Fix and rerun integrated findings before declaring completion.

All required probe scripts must be committed and runnable from a fresh checkout. Verify the final path after lane merges, including actual child execution and real PostgreSQL. Compare executed digests with submitted/model-returned bytes. Disconnect the constructor to prove no authored fallback fills a live arm. Omit a use record or correction receipt and require the offline verifier to name the missing evidence. Include every construction, rejected action, policy execution, model request, use and repair in resource accounting; unknown costs remain unknown.

Run the applicable full suite with correctly configured DSNs after final production changes. Report the actual pass/fail/skip/error counts and exact tested source. Do not add results from separate reruns and call the sum one clean full suite. Long runs need progress updates. A later prose-only edit can be recorded as such; a production fix requires affected integrated checks again. Avoid redundant full-suite reruns absent a new change or unresolved concern.

### M7. Deliver and clean up

Deliver `reports/STAGE-09-CONSOLIDATION.md`, the updated architecture/roadmap, the runnable public command, committed bounded evidence and independent verification. The report must distinguish implemented contracts, fixture qualification, any live results and externally unverified limits. Answer what the system itself chose, whether revised bytes changed decisions and effects, whether independently measured quality/resources improved, and what happened after a restart. State at most three evidence-supported next bottlenecks.

Update stage 9 to completed only for the delivered consolidation scope when its gates pass; do not claim generality, learning advantage or final deployment from that. Stage 10 and operational qualification remain separate. Preserve `evidence_inv01_live/` byte-for-byte. Remove only your owned disposable worktrees/branches/databases after evidence verification. Keep any necessary receipt anchor with its owner and reason. Push the complete integration branch and verify the remote SHA. Return one full handback, not a list of unmerged lane reports.

## Mature workflow and continuation rules

Use capable implementation/review models of your choice. The external reviewer's Luna preference does not constrain you. Parallelize only independent work after M0 fixes shared contracts; give each specialist exact skills/design sections, owned paths, baseline, worktree, database and executable gates. One writer per worktree, coordinator-only integration writes, serial merges with affected reruns. Inspect processes and branches before replacing a quiet worker. Never run broad cleanup against resources found merely by prefix.

Useful independent lanes are persistence/driver, policy ABI/construction, evidence visibility/promotion, and pilot/verifier, with dependencies recorded explicitly. Do not allow lanes to invent incompatible lifecycle or identity contracts. The coordinator owns complete execution through all milestones. Review beyond each diff for affected callers, checkpoints, exports and CLI entry points.

Use Jev when available to challenge typed decisions and evidence claims; direct execution and source remain authoritative. If a skill is unavailable, follow these written requirements rather than pretending to have run it. Use regression checks for material defects; ledger minor unrelated items. Do not shrink the product to the current benchmark, and do not grow a speculative framework to compensate for missing behavior. Keep working through the whole assignment unless a concrete external prerequisite blocks a dependent step; continue independent work and report the exact boundary.
