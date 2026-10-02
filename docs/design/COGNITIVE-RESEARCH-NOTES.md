# Research references for the next cognitive mechanisms

Read 2026-09-11. This is a focused primary-source pass for brainstorming and design criticism, not a systematic review, replication, or novelty certification. Paper results belong to their environments and budgets. Our design implications below are proposals for Settlement, not conclusions established by those papers. No implementation dependency is selected by citation.

## Sources and what they change in our reasoning

| Source and reading scope | Relevant reported mechanism or limitation | Our design implication |
|---|---|---|
| [DreamCoder](https://arxiv.org/abs/2006.08381), abstract | Learns symbolic program abstractions alongside neural guidance, using imagined and replayed tasks. | Treat executable abstraction as a carrier of accumulated competence. Its trained search component is outside our initial compute assumption; copying the wake/sleep name would not reproduce the mechanism. |
| [Stitch: Top-Down Synthesis for Library Learning](https://arxiv.org/abs/2211.16605), abstract; [official implementation](https://github.com/mlb2251/stitch), repository description | Finds shared program structure through corpus-guided abstraction search; the reported library-quality measure concerns compression. | A bounded corpus of successful procedures can seed abstraction candidates. Compression supplies candidates, while task fidelity and later use decide retention. Do not adopt a universal DSL or this dependency before our corpus and interpreter justify it. |
| [LILO](https://arxiv.org/html/2310.19791v2), mechanism, examples and discussion | Combines synthesis, symbolic compression and generated documentation. The paper reports both useful naming/documentation effects and incorrect descriptions; its LLM-only baseline also improves over time. | Compare executable retention against a strong textual/library baseline. Keep an invocation's observable behavior separate from the model's interpretation of it; check the description where downstream decisions depend on it. |
| [FunSearch](https://www.nature.com/articles/s41586-023-06924-6), specification, pretrained-model and implementation sections | Searches programs using an evaluator, a seed program and often a supplied skeleton. It requires no problem-specific model fine-tuning; the reported campaign uses extensive sampling. | Inference-only discovery is a substantive research direction. The evaluator and search representation remain important supplied structure; neither general discovery from minimal teaching nor cheap operation follows automatically. |
| [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954), abstract | Modifies coding agents and evaluates them on coding benchmarks, preserving an archive for further exploration. | Retain bounded experimental alternatives as possible parents rather than replacing the entire system after every apparent gain. Benchmark improvement and a generally better improvement process remain distinct claims. |
| [HyperAgents](https://arxiv.org/html/2603.19461v1), sections 3–5 and limitations | Makes task and modification behavior editable. Main experiments retain fixed outer selection/evaluation components and a fixed task distribution. Section 5.2 includes an initial math-grading format failure. | Compare improvement policies on common initial capabilities and full resource costs. Preserve format-versus-semantic failure attribution. State exactly which revision scopes remain externally controlled; do not label a bounded evolving component unrestricted self-improvement. |
| [Towards a Science of Scaling Agent Systems](https://arxiv.org/html/2512.08296v1), task comparisons and limitations | Reports task-dependent benefits and losses from coordination. Limitations include a small benchmark set, within-family model heterogeneity, and non-optimized architecture-specific prompts. | Treat decomposition, sequential dependence and communication cost as hypotheses for selecting teams. Do not import its numerical thresholds or explanations of model internals as universal laws or runtime configuration. |

## Representation-01 reference check

Read 2026-09-11: Zeller and Hildebrandt's author-hosted [Simplifying and Isolating Failure-Inducing Input](https://www.st.cs.uni-saarland.de/papers/tse2002/) abstract and paper contents, and Zeller's [Reducing Failure-Inducing Inputs](https://www.debuggingbook.org/html/DeltaDebugger.html) introduction/interface examples. Delta debugging already searches for smaller inputs preserving a failure; reduction is established prior art. The book illustrates reduction across collections and a reusable programmatic interface. Our proposed witness-preserving core must be compared against that class of existing tool, not presented as an original discovery because a model writes it.

This changes the first experiment: include tested generic deletion and domain-aware greedy reducers; state exactly which witness is preserved; distinguish an acquired operational interpretation, reused code and complete task benefit. The proposed core/adapter/source-checker split and pilot rules are our design choices, not results established by these sources. Software-to-graph reduction deliberately supplies a common problem form; it cannot establish discovery of that bridge. If the generated package merely reconstructs a standard reducer, record scaffolded acquisition or code reuse and evaluate whether its costs justify retention.

## Synthesis: ideas to keep, challenge and avoid

**Keep a search space larger than stored answers.** A retained change can introduce an operation, an instrument, an input distinction, a translation or a decision policy. Those changes alter which future computations are affordable or possible. Our current design already permits this; the next documents supply stricter obligations for making it usable.

**Challenge the selection pressure.** Short code, more candidates, higher benchmark scores and more agreeing agents can each reward behavior that fails the intended task. Each proposed mechanism therefore needs its own rejecting example and an outcome measure outside its own description of success. There is no single score that usefully replaces these distinctions across all domains.

**Keep semantic and experimental grounding separate.** A checked translation can be too costly to help. A useful heuristic can lack a universal proof. A new program can improve the solver without improving the procedure that develops programs. These are different outcomes, all worth recording accurately.

**Allow useful intermediates without an unlimited archive.** Preserve exact historical evidence and a bounded set of experimental alternatives with a reason to revisit them. A proposed stepping stone has a finite allocation and reassessment condition; its imagined future value is not evidence of achieved competence.

**Use disagreements to propose measurements.** Teams should create independently inspectable artifacts, distinctions or counterexamples. Additional prose agreement alone need not reduce uncertainty. A measurement plan may be a better result than a synthesized confident answer.

**Keep the simplest strong alternatives.** Textual lessons, a fixed rotation, a well-equipped single worker and a fixed development policy remain meaningful comparators. Their success would tell us to remove unnecessary machinery, not that the overall project failed.

## Questions this research does not answer

- Which representation family our actual experience corpus can support without an expensive custom synthesizer.
- Whether current construction, grading, billing and context paths preserve enough information to measure acquisition and transfer.
- What reuse horizons justify consolidation or which team decompositions our workload contains.
- Whether a candidate learning policy produces reliable benefits under the available models and real costs.
- Whether the combined design is novel, globally best, or capable of unbounded scientific progress.

The first two require the worker's engineering evidence. The following design drafts can proceed without it: [representation and transfer](REPRESENTATION-AND-TRANSFER.md), [temporary teams](TEMPORARY-TEAMS.md), and [learner revision and consolidation](LEARNER-REVISION.md). Their choices are reasoned hypotheses with rejection conditions; they are not replications of these papers or current implementation assignments.
