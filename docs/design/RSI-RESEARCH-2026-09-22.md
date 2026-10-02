# RSI research for the next architecture decision

Read on 2026-09-22. This is a focused mechanism review, not a comprehensive survey or reproduction of published experiments. Paper claims below are attributed; project choices are our inferences. Institutional affiliation is not a substitute for inspecting a method, its controls and its limits.

## 1. The paper the user remembered

[Duan et al., The Last AI Built by Humans: Toward Genuine Recursive Self-Improvement, v2](https://arxiv.org/html/2609.11873v2), especially sections 2.2, 3.4-3.7 and Table 8. Some news translations use “Towards True RSI.”

This is a survey and roadmap. It separates autonomy over executing improvements, choosing strategies, acquiring experience, adapting persistent deployed state and revising the improvement mechanism. It distinguishes structural inheritance from evidence that the inherited mechanism produces better successors. Its evaluation discussion calls for comparable starting conditions, resources and independent assessment. It does not establish that greater autonomy guarantees greater competence.

**Our decision:** record who owns each learning decision and test the inherited improver separately from the resulting solver. Do not assign the whole project an L1-L5 badge from an interface or test count. An implementation can expose a high-level decision while failing to make it useful. The original mission and resource authority remain externally specified.

## 2. Dream-RSI

[Zheng et al., Dream-RSI: Recursive Self-Improvement through Evolving Worlds, v1](https://arxiv.org/html/2609.14858v1), section 3 and the experimental setup in section 4.

The method changes executable exploration policy while keeping the discovery agent and evaluator fixed. Historical discovery trees provide recorded continuations for inexpensive policy evaluation. Replay traverses the observed search space; it does not generate the outcomes of arbitrary new actions. Policy selection improves its measured replay objective over the fixed history by retaining the incumbent as an option. That does not imply improvement on future online problems.

**Our decision:** adopt explicit supported replay and use it to screen proposals. A policy's unsupported choices become candidate live experiments. We must measure whether replay rankings predict prospective utility before allowing replay alone to justify deployment. Our observation graphs may contain shared dependencies and merged work; they need not become trees to imitate this paper.

## 3. Generalized Agent Iteration

[Tang et al., Generalized Agent Iteration, v1](https://arxiv.org/html/2609.13406v1), sections 3, 5 and 6.

The framework separates whether the modifier is editable from whether evaluation remains externally grounded. Its definitions expose why ordinary policy-improvement guarantees cannot simply be carried over to arbitrary program self-modification. The paper explicitly leaves reachability, computational cost and several formal results unresolved. We use its coordinates, rather than importing its classifications of other systems as settled facts.

**Our decision:** distinguish task state, improvement-program state and externally owned evaluation contracts. Formalization here specifies transitions and assumptions; it does not establish convergence, optimal intelligence or a monotone improvement curve.

## 4. HyperAgents

[Zhang et al., HyperAgents, v1](https://arxiv.org/html/2603.19461v1), method, sections 5.1-5.3 and the improvement-capacity definition in the appendix.

The editable program includes both a task agent and the agent that generates changes. The study tests transfer of improvement procedures to another domain, separating that question from task-agent performance. Some initial agents fail basic task formatting, which matters when interpreting gains; the source also reports comparisons with stronger customized baselines. Its results are bounded experiments, not evidence of indefinite acceleration.

**Our decision:** compare an old and revised improver from the same competent starting solver and archive. During that comparison, freeze the improvers. Otherwise better initial task code, extra experience or further online revisions confound the inference. Format-repair success is useful engineering, but report it separately from better investigation strategy.

## 5. Darwin Godel Machine

[Zhang et al., Darwin Godel Machine, v2](https://arxiv.org/html/2505.22954v2), sections 1 and 3 and the archive ablation.

The system explores an archive of executable agent variants rather than retaining only the latest winner. Earlier or currently weaker variants can lead to useful descendants. Archive maintenance and parent selection remain fixed in the described method, so not every part of the search improves itself.

**Our decision:** distinguish an experimental archive from active deployment. Keep a bounded set of useful alternatives with their evidence and applicability. Do not activate everything in the archive or build an unlimited population. Test whether retaining alternatives helps before adding an elaborate diversity optimizer.

## 6. STOP

[Zelikman et al., Self-Taught Optimizer: Recursively Self-Improving Code Generation](https://arxiv.org/abs/2310.02304). The abstract was read directly; detailed mechanism discussion was cross-checked against the RSI survey. The attempted arXiv HTML page was unavailable, so this review does not claim a full-text audit of STOP.

An executable improver queries a fixed language model and selects programs under a utility function. Applying the improver to itself produces revised improvers, evaluated through downstream program quality. The model weights are unchanged, and the reported setting is small.

**Our decision:** measure the output of an improvement procedure under a budget, not whether its own source looks more sophisticated. This is directly applicable without GPU training. Do not borrow the paper's reported gains as a prediction for this system.

## 7. Voyager

[Wang et al., Voyager: An Open-Ended Embodied Agent with Large Language Models, v2](https://arxiv.org/html/2305.16291v2). Abstract and method overview reviewed.

Voyager combines automatic curriculum, an executable skill library and feedback-driven code refinement, using a black-box model without parameter training. Its environment is Minecraft. It establishes that executable skill retention and autonomous experience collection predate this project; neither feature alone is novel or a general RSI demonstration.

**Our decision:** the distinction worth testing is the connected relationship between goal choice, retained executable behavior and changes to the future improvement procedure. We should compare against a competent fixed learning loop with memory, not only a stateless prompt.

## What these sources change

The resulting project design is our synthesis, specified in [Architecture synthesis](ARCHITECTURE-SYNTHESIS-2026-09-22.md). The central question is whether a persistent system can improve the decisions that generate its next useful capabilities while serving an externally specified mission. “The model wrote code,” “a new version was retained,” and “a benchmark score increased” answer different, weaker questions.

Three promising project hypotheses follow. These are not attributed findings or novelty claims:

1. Missing support for a consequential policy choice can identify a useful experiment. Test the resulting agenda against fixed allocation and ordinary uncertainty sampling.
2. A scoped portfolio of methods and improvement programs may retain useful alternatives better than a single global winner. Test use and forgetting under a fixed archive budget.
3. Decision-specific context may make accumulated experience useful at fixed token budgets. Test it against straightforward retrieval over exactly the same admissible history.

This review does not justify a universal predictive world model, weight training, an autonomous evaluator replacement program, or a whole-repository rewrite. Those remain possible future mechanisms if measured limitations justify them.
