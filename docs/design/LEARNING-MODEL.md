# Acquired competence and development episodes

Status: selected design for the first bounded development experiment, 2026-09-10. Inspected base: `be1730d`. This refines R2-R4 and LEARN-1 through LEARN-9; it preserves the existing execution, evidence, authority and release contracts. See [the roadmap](REFINEMENT-ROADMAP.md) and [worker assignment](../HISTORY.md#worker-development-01-prompt).

## 1. Selected mechanism

The Settlement develops by changing computations available to future investigations and the policies that select them. Experience can produce an invocable method, an operational representation, an improved policy, an applicability explanation or a newly investigable question. These products have separate evidence obligations.

Select explanation-guided candidate construction followed by bounded comparison and scoped reuse. An explanation guides an intervention; it cannot certify it. Preserve a reference and permit rejection or inconclusiveness. Prefer a simpler construction policy if explanation guidance does not earn its acquisition cost.

The next slice acquires a method through actual model inference in a live run. A prewritten implementation-worker solution or scripted response is a fixture, not autonomous acquisition. Full agenda formation, learned memory policies, representation invention and learner revision remain separate milestones.

## 2. Carriers of acquired competence

| Kind | Meaning | Distinct obligations |
|---|---|---|
| Method | Procedure transforming admissible inputs into outcomes or informative failure | Input/output meaning, applicability, bounded execution, failure behavior and outcome checks |
| Representation | Language or structure making useful operations available on a problem | Interpretation, partial translations, preserved properties and coverage limits |
| Policy | Procedure choosing an action, method, context or allocation from allowed alternatives | Admissible inputs/actions, fallback, downstream outcomes and selection cost |

These are semantic distinctions inside capabilities and compositions, not three required registries. A package may combine them. Compare the whole bundle when its parts cannot be separated meaningfully; presence during a success does not establish individual causal contribution.

An abstract capability contract is `C = (behavior, applicability, interpretation, effects, bounds, dependencies)`. Behavior and operational dependencies are versioned. Evidence and competence profiles refer to exact versions and conditions; new evidence can change eligibility without rewriting bytes. This notation does not prescribe a new database schema.

Applicability can be supported, contradicted or unknown for a proposed use. Unknown can justify an allocated trial; it cannot silently become supported default use. Check observable preconditions. Keep uncheckable assumptions explicit rather than accepting a model assertion as validation.

Text can describe a useful procedure, and a textual procedure can itself be operational when invocation and execution are defined. The architectural distinction concerns future behavior, not file extension. The experiment tests what retention enables a fresh worker to do.

## 3. Learning and its evidence

For a declared panel `T`, starting conditions `I`, model/environment `M`, and resource policy `B`, compare outcomes `O(C; T, I, M, B)` for candidate and reference compositions. Keep per-case outcomes and costs. Freeze useful-gain thresholds, permitted regressions and comparison rules before evaluation feedback is exposed.

Fresh-worker invocation establishes continuity of a behavioral change. A learning claim additionally requires comparative evidence of improvement at its stated scope. A completed development episode may have rejected its candidate and established no learning gain.

For comparable resource units, report `total(h) = acquisition + sum(use_cost[j], j=1..h)` at declared reuse horizons. Keep money, tokens, tool time, elapsed time and unresolved liabilities separate. Failed candidates, verification and selection also consume acquisition resources. Do not invent a universal utility score to combine unlike quantities.

The first episode permits finite-panel conclusions. Inferential promotion remains subject to LEARN-6, including validation of the actual adaptive selection/stopping procedure. Fresh worker identities do not make related tasks statistically independent.

## 4. Episode semantics

A development episode is a bounded investigation into a change in future behavior. Durable state identifies its triggering experience, explanations, reference, allocation, access policy, candidate lineage, evaluation bindings, pending operations and disposition. Reuse investigations, artifacts, journal records and trials where their semantics suffice.

Separate episode lifecycle, candidate eligibility and evidence verdict. A blocked provider is not evidence against a method. A suspended or finished episode can still have unresolved external liabilities.

| Transition | Preconditions and input | Durable output |
|---|---|---|
| Observe -> propose | Identified failure, expensive success, inconsistency or opportunity | Trigger references, proposed bottleneck, predicted intervention effect, competing explanation or explicit uncertainty |
| Propose -> admit | Reference, allowed changes/access, finite allocation, stopping rule | Admitted episode or precise refusal |
| Admit -> diagnose | Allowed observations and instruments | Allocated probe results, distinct from predictions |
| Diagnose -> construct | Selected intervention and remaining budget | Candidate bytes, contract, lineage and construction receipts; no candidate or malformed output is valid |
| Construct -> development check | Isolated trial eligibility and visible development/regression material | Check outcomes, bounded revision, rejection or evaluation selection |
| Select -> bind | Selection uses development feedback only; evaluation policy already fixed | Exact artifact, lesson, reference, task-group and evaluator bindings |
| Bind -> compare | Frozen versions and matched information/resource policies | All assigned outcomes and costs; gain, regression, inconclusive or unusable comparison |
| Compare -> dispose | Evidence sufficient for requested disposition | Scoped experimental release, rejection, suspension or retained research artifact; incumbent fallback preserved |
| Dispose -> use | New task, fresh worker, current eligibility and allocation | Actual invoked version/output, outcome/cost, profile update or regression challenge |

State names and grouping are engineering choices. Preserve this causal order and reconstructable trace; no row requires a separate model call, agent or service.

## 5. Seed policy for the first episode

1. A caller selects a completed development batch or identified experience. Global opportunity selection is later work.
2. Broker-routed inference proposes at most two explanations and one actionable intervention. Uncertainty or “no worthwhile change” is admissible. Explanations are public hypotheses, not requested private reasoning transcripts.
3. Permit at most one diagnostic probe and two constructed candidate versions in total. A revision uses one of those slots. These count bounds supplement finite money/time/tool ceilings; they do not replace them.
4. Select at most one candidate using visible development/regression evidence. Stop construction before protected comparison feedback becomes available.
5. Compare once on the frozen panel. A later revision requires a new episode and an access policy accounting for prior feedback. A new episode ID does not make an exposed panel unseen.
6. If release is supported, test it on a separate subsequent-use panel through fresh workers. Otherwise use the incumbent and keep the candidate in experimental scope. Never manufacture a positive release to complete the trace.

The caller supplies or admits finite resource ceilings before work. The worker may reduce these count defaults for its environment, recording the configuration before evaluation. They are a simple seed policy, not claimed optimal settings.

All inference and candidate execution use the existing gateway/broker/launcher path. Generated code stays outside the trusted host process. Host code can validate descriptions and package bytes; it must not execute a generated synthesizer as a callback. Trusted scripted responses remain labeled fixtures.

## 6. Comparison and attribution

Preserve A/B/C: A has declared ordinary history and a fixed starting procedure without a newly retained method library; B retains textual lessons; C retains an executable method. All arms may construct tools within a task under the same usable tool and inference policy. Matching tool descriptions in prompts is insufficient if actual invocation differs. Match ceilings and access, not necessarily expenditure or action sequence.

Use a declared common development batch and identical initial exposure for this first controlled experiment. Charge common acquisition cost to each standalone arm in per-arm comparisons, but once in the actual experiment cash ledger. Add each arm's own retention construction/verification costs. This isolates retention after common experience; it does not compare autonomous curricula.

Keep the existing no-op executable ablation. It tests whether the method's behavior matters beyond invocation scaffolding. If a retained method adds model computation, a stronger causal attribution needs a declared matched-compute control. A first report may compare whole retained compositions without claiming which internal part caused a difference.

Two freezes preserve adaptive development and protected evaluation:

- Before development, fix task selection/grouping, access, budgets, scoring, stopping, exclusion and release rules.
- After development-only selection, bind the resulting immutable candidate, lesson and reference versions before evaluation launches. Do not select new favorable tasks at this point.

Development, evaluation and subsequent-use groups must be disjoint by underlying problem source/structure, not just task ID or source hash. Record the grouping rule and known shared structure; no finite grouping procedure proves absence of all leakage. Constructor and candidate cannot access protected answers. Evaluation feedback cannot drive an unrecorded retry.

Freeze a primary outcome, such as correctness under fixed caps, a useful-gain threshold, tie treatment and regression bounds. Report C-A and C-B separately. Finite-panel evidence can support a visibly limited experimental release under existing rules. Small panels need no invented statistical certainty; stronger inference is outside this assignment unless separately justified.

A narrower scope discovered after inspecting evaluation failures is a new specialization proposal, not a retroactive change to the release rule. Confirm it under an appropriately declared new comparison before making the stronger scoped claim. Infrastructure failures follow the frozen outcome policy and remain distinguishable from evidence of method failure.

## 7. Retention and negative experience

Retain an incumbent, supported specialists and bounded experimental alternatives. Publication makes bytes available; release admits specified use. An applicability explanation cannot widen release scope by itself.

Before use, check authority, bytes, dependencies, quarantine and eligibility. Route unknown scope to the incumbent or an allocated trial. A method failure consumes resources and follows the declared fallback within remaining task budget. Do not erase it from the comparison.

After interruption, reconstruct the next decision from durable state and existing operation identities. A replacement worker must not regenerate a published candidate through an unaccounted model call. Preserve uncertainty and liabilities using existing broker recovery, rather than a second retry scheduler.

A failed episode can retain a scoped negative result and conditions for reopening: changed evidence, environment/model, scope, instrument or budget. It is not a universal ban on related ideas. Make that record discoverable without admitting its candidate. Full automated forgetting and consolidation policy is later work.

Consolidation must eventually compare abstractions with their original methods, test composition interactions, preserve active dependencies and retire unnecessary active complexity without rewriting historical evidence. Description compression alone is not competence.

## 8. Representation and transfer boundary

The later representation mechanism is an operational language with an interpreter and partial translations. If `encode(x)` succeeds, representation operations must have a stated meaning for `x`; a decoded result must satisfy the original task obligation under stated assumptions. Refusal to encode may preserve soundness while giving poor coverage. Test these separately.

A generic reducer can take an object, admissible reductions, a decreasing measure and a witness predicate. It can preserve a witnessed property and terminate accepted reductions without finding a globally minimal witness. Mathematical reuse requires an independently justified predicate and interpretation. Shared API shape does not establish transfer.

This is later S4 work. Do not build a universal representation language for the first episode. Record a supported transfer opportunity as a proposal if one emerges; none is a valid outcome.

## 9. Worked trace and failure cases

Extend the current bounded software-repair family unless inspection shows its groups/outcome checks cannot answer the question. The worker chooses and freezes exact panel contents and deterministic grading, including structural variation and cases where the proposed method should abstain.

Illustrative trace, not a promised discovery:

1. Development attempts repeatedly mishandle a boundary condition. Public outcomes and receipts supply trigger evidence.
2. One explanation is failure to recognize the condition; another is ambiguity in the available task specification. A visible probe can distinguish them, or uncertainty remains explicit.
3. The model constructs a bounded detection/repair procedure from development material. It may instead produce an exact-answer lookup; identify that honestly and do not infer generalization.
4. Development checks include relevant bugs and cases that should remain unchanged. An overbroad rewrite fails; a second candidate may narrow applicability within the allocation.
5. Freeze the selected version. Fresh workers compare A/B/C on independent groups with the no-op control.
6. If the release condition holds, a subsequent worker obtains that release and consumes its actual output. Otherwise the incumbent remains selected and the episode records its result.
7. Later contradiction narrows eligibility or triggers quarantine under existing rules; it never rewrites the historical score.

Also exercise no candidate, invalid output, unavailable provider, exhausted budget, interruption after publication, unknown applicability, and method failure. Reuse meaningful existing regressions and integration seams; each path need not create a new framework or test file.

## 10. Decisions and alternatives

| Decision | Selection | Alternative and reconsideration condition |
|---|---|---|
| DLM-01 Carrier | Operational capabilities with method/representation/policy obligations | Textual lessons remain a serious baseline; prefer them where executable retention adds no value. |
| DLM-02 Constructor | Bounded explanation-guided intervention | Direct generation/mutation; compare later at equal cost. This episode does not establish explanation guidance's superiority. |
| DLM-03 State | Development investigation over durable primitives | Process-local script suffices for fixtures, not fresh-process continuity claims. Avoid a second workflow engine. |
| DLM-04 Selection | Scoped portfolio and fallback | One global winner only if mixed-family outcomes and routing overhead justify it. |
| DLM-05 Scope | One caller-admitted method-acquisition episode | Full autonomous discovery entangles agenda, acquisition, representations and teams before any is measured. |
| DLM-06 Qualification | Bounded prototype evidence with explicit limits | Production qualification first only where actual experiment conditions require it. |

These are selected choices with empirical limits. Data layouts, module extraction, exact prompts and panel contents are engineering decisions inside the obligations. No globally best architecture or scientific novelty claim follows.

## 11. Development 01 requirements

These IDs add a bounded slice. They do not rename S4-S6 or reopen every prior review.

| ID | Observable requirement | Acceptance evidence |
|---|---|---|
| DEV-01 | Admit an episode with identified experience, reference, access policy, finite allocation and seed limits | Real entry-point trace; missing essentials refuse before dependent effects |
| DEV-02 | Broker-routed inference proposes an intervention and constructs candidate bytes from allowed experience | Request/response provenance and receipts; scripted responses distinguished from live output |
| DEV-03 | Stage, check and invoke generated behavior through artifact/capability/execution contracts | Exact digest and receipt; no generated host callback |
| DEV-04 | Selection/revision/evaluation obey the two freezes and branching bounds | Version/exposure trace; no silent construction retry after comparison feedback |
| DEV-05 | Fresh process resumes after publication using durable state | Clear constructor process state and scratch, retain required artifact bytes; no repeated settled construction |
| DEV-06 | A/B/C have declared common experience and usable within-task affordances; costs are visible | Per-arm accounting and actual ledger; preserve labeled lookup and no-op controls |
| DEV-07 | Frozen source-group splits and exact bindings govern evaluation and subsequent use | All assigned outcomes, isolation checks and version-linked receipts; appropriately scoped conclusions |
| DEV-08 | Release, routing and fresh-worker use agree; unsupported gain preserves incumbent | Verify release and non-release branches; simulated gain remains fixture evidence |
| DEV-09 | No candidate, invalid output, exhaustion and interruption produce truthful states/accounting | Focused integrated checks, including method failure/fallback within remaining budget |
| DEV-10 | Scoped negative evidence and reopening conditions remain discoverable | Inspect rejected episode without activating its candidate or erasing evidence |
| DEV-11 | Operator can inspect phase, next decision, hypotheses, lineage, comparison and costs | Extend existing investigation/learning view or link a bounded report there; no separate management app |
| DEV-12 | One documented entry point runs the episode with revision/environment/result reporting | Deterministic run required; live run needs supplied access/allocation and suitable explicit profile; update reports and roadmap |

Reuse `experiment.py`, `capabilities.py`, `trials.py`, `evaluation.py`, `context.py`, investigation state and broker/launcher interfaces as appropriate. The inspected `_synthesize_method` is a labeled exact-lookup baseline. Its custom callback is not by itself a model-backed durable constructor. Preserve the baseline rather than relabeling it. The worker must verify these observations before selecting an implementation seam.

## 12. Completion and next decision

Finish when missing DEV behavior is implemented, meaningful integrated checks pass, the worker has assessed the assembled result, and the runnable experiment/evidence are committed. Without live inputs, mark live evidence blocked and supply the exact command; implementation may still be complete within tested bounds. Positive learning is not required.

The next review checks this episode and its experimental interpretation. It then chooses acquisition improvement, memory/context refinement or experiment redesign from the evidence. Full representation transfer, autonomous curricula, adaptive teams, learner revision, fine-tuning and operational qualification remain separate milestones.
