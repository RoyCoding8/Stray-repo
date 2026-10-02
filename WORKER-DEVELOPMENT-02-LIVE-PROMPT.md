# Development 02: finish the live episode

Continue in the existing chat or start a new one with this file. Work from the existing repository and configured `origin`; do not copy remote addresses or private local endpoint configuration into documentation. Fetch and inspect status first. The reviewed implementation is `a1d2525a37571abf45a54de45c3dfcdad4aaaf9f` on `codex/implementation-development-02`.

Merge `origin/codex/development-02-assessment` into your coordinator branch after checking lineage. Ordinary additive commits and push to your implementation branch are authorized. Preserve concurrent work, private repository identity, and prior history. No force push, reset or unrelated cleanup.

## Read first

1. `AGENTS.md`, `IMPLEMENTATION-WORKFLOW.md`, `COLLABORATION.md`.
2. `reviews/DEVELOPMENT-02-ASSESSMENT.md`: disposition, five narrowly scoped findings and answers to your four review questions.
3. `reviews/probes/test_development_02_acceptance.py` and `reports/evidence/development-02-prompt-pilot/{protocol,results}.json`.
4. `docs/design/MEMORY-AND-CONTEXT.md`, `docs/design/LEARNING-MODEL.md`, and the maintained roadmap.

The separate `docs/design/AUTONOMOUS-AGENDA.md` advances stage 8.4 design. **Do not implement it in this assignment.** Your task is a real, bounded Development-02 episode, not another architecture expansion or S0-S3 audit.

## Independent assessment and changes

Verify or rebut each D2A finding against the actual source and your real-DB environment before changing it. Reviewer probes use explicit persistence/effect doubles and assert the reported limitations; they are not a replacement for your maintained integration tests. Record correspondence when converting them to the intended contracts. Do not invert them just to make a number green.

Required episode corrections:

- **D2A-001:** supply a complete canonical diagnosis/constructor response contract and file-to-file procedure ABI. The independent live responses both failed strict JSON parsing; construction returned a repaired function instead of a reusable procedure. Decide and verify a bounded response-format policy. Ensure the normal invocation contract, selftest, output file and allowed effects agree with the consumer. The model authors the candidate; do not substitute worker-written candidate code for live acquisition. Genuine model abstention or invalid output must remain honest outcomes.
- **D2A-002:** resolve the collected episode claims into diagnosis, not just the database. Assert original inputs, permitted cases/feedback, attempted behavior and outcomes in the actual outgoing request. The normal CLI's task-ID refs currently do not select the newly collected diagnosis claims.
- **D2A-003:** fresh-process ordinary use resolves the post-comparison release/router disposition and applicability. A bound but unreleased candidate is not the incumbent. An out-of-scope task must follow the declared fallback. Distinguish an explicitly admitted candidate trial from ordinary use.

For **D2A-004** actual-input binding and **D2A-005** counterevidence loss, either close the contracts with focused regressions or run under the assessment's explicit restricted conditions: fresh isolated experiment, no packet reuse, ample context, no mandatory/counterevidence omission, and independently compare the complete admitted/emitted input against stored packet evidence. If using the restriction, record CTX-04/05/06 as incomplete at their broader scope. Do not represent operation-existence linkage as verified delivery. These restrictions authorize a narrow pilot, not silently weakened memory semantics.

Your split cost ownership and pre-candidate declaration decisions are accepted in principle. Export whole-episode costs as a unique-operation union covering collection, diagnosis, construction/checks, comparison and subsequent use; distinguish shared cost and arm-specific cost. Preserve unsettled exposure. Harness-only totals must stay labeled as such. Previously exposed use tasks are fine for restart smoke, not proof of unseen-task competence.

## Execute, with finite bounds

Use your configured gateway. Verify discovery, authentication and one actual inference separately. The human selected **`claude-opus-4-6-thinking`** for the comparison; use that exact identifier when available. If it is unavailable, report the actual blocker rather than silently using a different model or claiming fixture output is live. Credentials stay outside Git. Do not assume this machine's endpoint works in your environment.

First perform a small real-provider contract smoke using the exact runtime-emitted requests and responses. Record this as development feedback. Freeze the final task splits, exposure, policy, model settings, response handling, finite total grant and request/time ceilings **before** the subsequent comparison. Any prompt/contract tuning based on the smoke must precede that freeze and be reported. Respect existing allocation/settlement and launcher authority; use an appropriate probed execution profile for model-generated code. Do not execute generated code in the trusted host or silently fall back to uncontained execution.

Run one bounded live episode end to end if the gateway, allocation and execution profile are available. Preserve original live prompts, response envelopes, returned/requested model, exact candidate artifacts, grade/use receipts, pre/post-disposition selection and all-in cost/exposure. No positive result is required. A rejected or ineffective method can finish the experiment through real incumbent use. Parser or execution-interface failure is an integration result, not evidence that learning is ineffective. No retry-until-success loop; material protocol amendments require a new labeled experiment.

If your runtime profile or access genuinely prevents this, save exact successful/failed preflights and the remaining command/input requirement. Do not repeat an environment-variable-only blocker without checking the gateway available in your environment. Do not purchase access or invent missing monetary authority.

## Coordination and finish

Use your own implementation models. Parallel specialists with isolated worktrees/databases are authorized; choose non-overlapping seams. The coordinator owns shared interfaces, integration and the experiment. Detect silent lane failure, reclaim explicitly and retain honest task history. Use the available skill instructions where relevant; no requirement depends on a skill that exists only in the reviewer's environment.

Run focused real-DB/effect tests for changed paths, then the full suite on the final source. Update `reports/PLAN.md`, `reports/DEVELOPMENT-02.md`, `reports/VERIFICATION.md`, `reports/DECISIONS.md`, `reviews/REQUEST.md` and the roadmap. Report exact commands/revisions and distinguish worker tests, reviewer characterization probes, live inference, generated-code execution, and learning evidence.

Commit and push the finished coordinator branch, verify its remote tip, and clean only your owned temporary worktrees/databases. Return the disposition of D2A-001..005, the live episode result or exact blocker, and evidence paths. Stop after this bounded assignment. The next architectural work is the autonomous agenda experiment and its representation, not another open-ended correctness sweep.
