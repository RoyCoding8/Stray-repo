# Team 01 live2: scoped experiment accepted; delivery and representation limits

Assessed worker `58647406e87d3375a1c08c1e5406ebcd045edb88`. This pass inspected source and committed evidence and independently recomputed the finite-panel arithmetic. It did not rerun provider calls, the 895-test PostgreSQL suite or live-DB reconciliation. Those executions remain worker-reported. The published reconciliation file is evidence of the worker's receipt comparison, not a fresh receipt lookup by this reviewer.

## Decision

Accept the real-repair prototype and the observed non-promising results for the actual treatments. Do not repeat the 48 evaluation or 24 transfer episodes merely to correct reporting or an accounting projection. The corrected refusal accounting cannot turn this campaign into a promising result.

The narrower treatment matters: warm-T receives a model-written advisory lesson in its prompts. It does not load the executable, parameterized coordination template required by Team 01. Thus this is useful live evidence about retained advice, while executable coordination acquisition remains an unmet design obligation. Preserve that distinction instead of either rejecting all progress or marking the original requirement complete.

Two reported campaign modules are absent from the pushed tree. Publish those and a corrected derived evidence view before declaring reproducible delivery complete. This is a bounded delivery task, not another live campaign or broad audit.

## Independently recomputed result

The stored evaluation has exactly 48 unique `(panel, arm, task, repeat)` cells; transfer has 24. Feeding these records and the published control outcomes into the current `finite_panel_rule` reproduces:

| Comparison | Solves | Model tokens | Visible tool executions | Decision |
|---|---|---|---|---|
| Eval T / S | 16 / 15 | 72,392 / 93,942 as recorded | 28 / 19 | T's tool ratio exceeds 1.25 |
| Eval T / P | 16 / 16 | 72,392 / 73,653 | 28 / 32 | T meets the level comparison |
| Transfer warm-T / cold-T | 8 / 8 | 36,463 / 34,728 | 12 / 14 | Warm uses more tokens |
| Transfer warm-T / S | 8 / 8 | 36,463 / 39,856 | 12 / 9 | Warm uses more tools |

Neither complete rule recommends a broader trial. These are finite, scoped results, not evidence of global equality or inferiority of teams. Near-ceiling scores on this small panel leave little room for a quality gain.

The current checker also makes `complete-records=false` because `_solved` returns unknown for a recorded refusal. The specification counts a complete refusal as zero success; a known unsuccessful outcome and missing evidence are different states. This discrepancy is an analysis/measurement repair, not a reason to re-execute the task.

For `live2-S-team01-t06-r2`, the published reconciliation gives 890 input and 563 output tokens while its original record has zero. A sensitivity calculation, performed in memory without altering the committed record, adds those 1,453 tokens and treats the refusal as zero success. S's evaluation total becomes 95,395 tokens; completeness ceases to block the rule, but `beats-S` remains false because 28 tools still exceed 1.25 × 19. Transfer is unchanged.

Preserving original records is correct. It does not prohibit publishing a clearly linked derived correction using the available receipt evidence. Do not describe a usage-record discrepancy as an unconfirmed external effect: the report says the receipts exist. Keep effect settlement, accounting agreement and empirical outcomes separate.

## What was retained and used

`template-frozen-live2.json` stores a 1,386-character directive. It recommends organizations for named development task patterns, includes concrete example outputs and has an `applies_when` sentence. The build record contains actual model response text, rather than the previous authored menu.

In `solver.py:1067–1156`, `plan_prompt` appends the directive, and `solve_T` also places it in child-constructor context. The model then proposes a fresh shape. The stored directive does not contain an executable composition with parameter bindings, and this path does not enforce the prose applicability condition. This is a learned advisory artifact used for model conditioning. It is legitimate to study it; it is not the requested executable-template mechanism.

The stored paired transfer shapes differ in two of eight cells, both on `team01-t08`: cold-T chooses decomposition and warm-T chooses single. Both arms solve all eight cells. This is observed decision divergence, not proof that the directive caused the difference independently of model sampling. Also, the directive reaches constructors as well as the planner, so the treatment combines coordination advice with task-solving hints. It cannot isolate improvement in organization alone.

No extra experiment is required now to repair that interpretation. Label these records as the advisory treatment and keep executable coordination acquisition explicitly open. Do not retroactively relabel this text as an executable policy, and do not generate a new policy after evaluation to insert into the old freeze.

## Reproducible delivery still needs two modules

The report and review request name `experiments/team01/acquire2.py` and `experiments/team01/reconcile2.py`. Neither file exists in the checked-out `5864740` tree or its tracked file inventory. The new Python changes since the preceding design checkpoint are confined to solver/checker/tests. Consequently the reported acquisition and reconciliation path cannot be inspected or reproduced from this delivery, even though its output JSON files are committed.

Recover the exact executed modules and any essential campaign driver/configuration from the retained worker environment, commit them, and state their source provenance. If exact source cannot be recovered, say so; a reconstruction must not be presented as the historical executed implementation. A fresh clone that recomputes aggregate scores is useful, but it does not replace delivery of the module that acquired the artifact.

The evidence also calls for small derived-report corrections. The 86 published records comprise 47 evaluation successes, one evaluation refusal, 24 transfer successes, and 14 development-tagged records: 11 successes and 3 failures. The latter include the validation/continuity records. Separate calibration from probes before restating totals. Include the standalone template-construction call and all earlier calibration costs when describing whole-campaign cost. Reconcile from explicit operation identity unions instead of assuming the episode total contains every build or prior attempt.

## Architecture consolidation: decisions supported now

This starts a scoped stage 9 synthesis while the unmet stage 8.6 executable-template obligation remains visible. It does not mark all cognitive development complete.

| Architectural choice | Decision and reason |
|---|---|
| Persistent work | Keep investigations, owned attempts, artifacts, checked joins and durable continuation. The vertical path and live panels exercise useful end-to-end behavior. |
| Default organization | Keep the strong single worker as the conservative starting policy. Retain bounded team execution as an available option, not a universal default justified by this pilot. The observed tradeoffs do not establish a global winner. |
| Advisory memory | Keep evidence-backed textual advice as a distinct candidate artifact. Useful prose can affect decisions, but its scope and cost still need checking. This campaign found no qualifying efficiency gain. |
| Executable memory | Preserve the original goal: a reusable computation/plan with checked inputs, applicability and dependencies. It remains unimplemented/unverified by the current directive treatment. |
| Learner revision | Do not build a general self-rewriter or select retry learning from near-ceiling scores. First identify an observed, repeated bottleneck on the actual development path. |
| Next design question | Specify how one supported lesson becomes a bounded invocable computation or check, with explicit refusal outside scope, and distinguish that from simply prompting the model again. Answer the representation/interface question before commissioning another large comparison. |
| Stack and deployment | No new infrastructure framework or stack rewrite follows from this result. Operational qualification remains separate. |

One prospective example, not a demonstrated learned result: instead of retaining “check units before splitting work,” retain a parameterized interface probe that consumes a supplied conversion contract and actual producer/consumer entry points, executes a round-trip/boundary check, and emits a concrete counterexample or scoped result. Its parameters and check can be validated without requiring a new model to reinterpret the advice. Whether acquiring such a probe helps remains an experimental question; no implementation is assigned in this delivery cleanup.

## Completion list

- [x] Inspect `5864740` in the separate assessment checkout.
- [x] Recompute both published panel rules and refusal-accounting sensitivity.
- [x] Classify actual retained behavior and identify the missing executed modules.
- [x] Accept the scoped non-promising experiment without requesting another full campaign.
- [x] Begin architecture consolidation with explicit supported and unsupported parts.
- [ ] Worker publishes the executed acquisition/reconciliation source and derived accounting/interpretation corrections.
- [ ] Design role refines executable retained computation separately; no broad learner or runtime rewrite is commissioned.

The bounded handoff is [delivery closure](../docs/HISTORY.md#worker-cognitive-batch-02-delivery-closure). Historical records and prior assessments remain intact.
