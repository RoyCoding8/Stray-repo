# Stage 8 closeout and stage 9 design review

Reviewed worker tip `1d90c2e6c553f6ad1b03cfd6145fe4cad86c7821`, based on assignment `4b25d0c`. Review date 2026-09-20.

**Accept the bounded stage 8 contract closeout. Accept the stage 9 grounding work, but revise the architecture package before treating it as implementation-ready.** Remain in stage 9. Do not reopen a general stage 8 audit or require a positive learning result.

## Accepted

The executor now owns the advertised helper table. Prompt exposure and child bindings derive from it; existing reducer implementations remain in use. The missing bare helper names are supplied in the candidate module before its code loads. Tests exercise both domains, direct oracle use, malformed output and query limits. A committed diagnostic script extracts the original candidate bytes and keeps the original live evidence separate from post-fix execution.

The worker reports that all four archived candidates execute and preserve the witness after the fix; two tie their starting measure and two improve it. This is useful development-task diagnosis. It remains distinct from retained live learning and transfer. `git diff a26408f..1d90c2e -- evidence_inv01_live` is empty.

The B1 call graph is useful. It identifies real ownership and admits that retained-member revision does not exist yet. Keeping the current consumer/driver is a viable implementation strategy. The absence of a third instrument today is not, by itself, sufficient evidence that the architecture supports the intended general investigation cycle. The following requirements apply whichever source organization is chosen; they do not require a new service, registry or wholesale rewrite.

## S9R-01: the selected replay experiment has its result encoded in the checker

`reports/STAGE-09-FEASIBILITY.md:97-124` proposes changing construct/stop actions and counting supported replay, with a 50 percent threshold for policy comparison. `experiments/doubles.py:387-394` rejects every changed target or instrument against the one selected transition before examining its result. It does not search the corpus for a different recorded continuation.

The independent [probe](probes/stage09_delivery.py) checks all 28 prefixes. Every unchanged action is supported; every changed instrument is unsupported. The corpus contains 23 diagnostic actions, five development actions and zero stop actions. Thus the proposed construct-where-stopped comparison has no observed stop cases. The changed-action rejection is a good conformance test, not evidence that distinguishes a replay-learning hypothesis from a prospective-learning hypothesis.

Neither 50 percent support nor action agreement alone establishes that policies can be ranked: unsupported decisions can determine the result, and the rule supplies no identified value estimate or bounds for them. Retain exact replay as an integrity/recovery tool. Complete a static coverage inventory now; do not commission a campaign to rediscover the exact-match guard. If proposing counterfactual evaluation, define the eligible policy class, matching state, supported continuations, selection bias and disposition of missing outcomes. Otherwise select a prospective question whose competing predictions are not predetermined by this checker.

## S9R-02: revision needs a feedback/evaluation separation and a promotion rule

The architecture's complete example, lines 170-186, starts revision from failures on protected tasks, then retains and supersedes the incumbent when the revision improves the failed task. It also mentions fresh use tasks, but does not make their outcome govern promotion or define how exposed tasks leave the protected set. The statement that steps 7-8 already run overstates what an ordinary acquisition gate proves about revision and supersession.

Distinguish operational feedback from sealed assessment. A visible failure may become development experience under a recorded visibility transition. Once exposed to construction it is development data; it cannot continue to count as independent assessment of that revision. Freeze revised bytes before evaluation on fresh, still-unseen tasks. Repeated revisions require an explicit protocol for assessment reuse or fresh allocation.

Promotion must depend on the declared independent assessment and resource rule, with regression checks relevant to the old scope. Fixing the single motivating example permits further assessment, not automatic replacement across the whole family. Preserve old bytes, scoped applicability, lineage and rollback. Spell out reject, retain-as-specialist, supersede and inconclusive outcomes as needed; avoid inventing mandatory machinery that the first concrete revision does not use.

## S9R-03: the core self-revision contract is still a paragraph, not a migration-ready design

The draft describes a learning procedure as proposer plus admission plus stopping. The concrete walkthrough revises a task method. It does not specify the retained executable policy's representation, invocation, state, effect requests, revision identity or independent comparison. Naming `DecisionConsumer` callback arguments demonstrates an extension point, not an implemented or fully specified self-improving procedure. Trusted admission must remain outside generated policy authority.

Before the migration, supply an end-to-end policy revision example in addition to method revision. Define permitted policy inputs, executable bytes and dependency identity, output action/stop contract, bounded model/tool requests, checkpoint state, failure/fallback behavior and evaluation/promotion. State which existing records carry each field and which meanings change. Generated policy code cannot execute as an unrestricted host callback. An authored substituted policy is a valid engineering control and must remain labeled as such.

The draft also names open questions and hypothesis states without mapping their persistence, and gives campaign identities tied to world/arm/schedule. Explain how the selected in-place design represents investigation identity, branching or a declared initial branch limitation, and successive revisions independently of benchmark identities. Reuse existing rows if they suffice; show the encoding and update owner. This is the original generality requirement, not a request for a third benchmark or speculative multi-agent layer.

Replace the loose migration bullets with ordered slices: state/identity semantics, shared reconcile ownership, policy contract and execution, feedback/revision, assessment/promotion, then removal of obsolete callers. For each slice name owned files, dependencies, treatment of pending work and one public-path acceptance check. Source moves alone are not architectural progress.

## Feasibility evidence to carry forward accurately

The report's first probe calls `DecisionConsumer.decide` and admission; it observes different admitted targets. It does not record downstream execution. The second records a pending row and reads it in another process; it does not resume/reconcile that action or verify its spend. Keep those narrow successes, and remove the stronger conclusions unless existing integrated tests or committed probes demonstrate them.

Three probe scripts were not committed. That limitation was disclosed and is not, on its own, a reason to reject the architecture. Close it when checking the revised design: reuse committed recovery tests where they prove the precise claim, and commit the smallest missing public-path checks. Do not demand a fresh full-suite campaign merely for prose changes.

## Verification and boundaries

The reviewer ran nine focused checks successfully in 3.90 seconds: all of `test_s89a2_extract.py`, the two injected-path runner checks, and `test_prompt_exposure_derives_from_executor_contract`. These check extraction, classification, byte forwarding, recorded failures and contract rendering. They do not independently rerun the Linux child or PostgreSQL acquisition/recovery paths. This local Windows environment has no configured test DSN; the available WSL Python lacks project dependencies. No new provider calls or study database changes occurred.

The worker's `reports/PLAN.md` records 869 passed, 592 skipped and two setup errors at `257ac3c`, followed by three passing tests in the affected file with a URL-form DSN. Preserve those results separately. The handback's 872 is a sum across runs, not a single fully provisioned suite result on the final tip. This qualification does not reopen the accepted contract fix.

The committed reviewer probe and [observed replay counts](evidence/stage09-review/observed.json) make S9R-01 reproducible without a provider or database. It is a checker conformance result, not an empirical policy comparison.

Jev assessed the supplied review, worker architecture and replay counts. It favored accepting the stage 8 scope while refining stage 9, and classified S9R-02 as a proposed-design gap rather than demonstrated executed leakage. Its [input](evidence/stage09-review/jev-input.json) and [typed response](evidence/stage09-review/jev-output.json) are recorded. Jev did not independently inspect the repository, run the study or establish calibrated confidence in correctness.

## Next work and stopping condition

The next useful work is stage 9 design refinement, with the accepted stage 8 fix left closed. Retain the source-grounded ownership map. Correct the feedback/promotion protocol, make executable learning-policy revision concrete, and replace the predetermined replay experiment with an informative question. Reverify only the feasibility claims needed for those decisions. A sound in-place consolidation remains an option; its suitability must follow from the required learning cycle rather than the absence of that cycle in today's benchmark.

This is an architectural review, not authorization for new live spending or a wholesale migration. The next implementation should begin from the revised, reviewable contract and its explicit evidence limits.
