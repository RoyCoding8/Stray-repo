# Research inputs for component refinement

Primary-source reading, 2026-10-13. This is a focused design investigation, not a systematic review, replication or novelty certification. Reading scopes below are deliberately narrower than entire papers. Reported mechanisms and our proposals are separate. The [architecture synthesis](ARCHITECTURE-SYNTHESIS-2026-09-22.md) owns the selected design.

## Core RSI references

### Dream-RSI: Recursive Self-Improvement through Evolving Worlds

[Paper, v1](https://arxiv.org/html/2609.14858v1). Read main mechanism and experiments/analysis, sections 2–5, plus selected replay details in appendix B.

The changing object is executable exploration-policy code. A fixed discovery agent produces candidates; a fixed evaluator supplies outcomes. Recorded trees support replay of alternative exploration choices. The policy developer is also fixed. Replay reveals recorded branches without evaluating arbitrary untried interventions.

**Adopt:** one decision interface for replay and live exploration; visible history prefixes; reusable discovery branches. **Modify for our goal:** broaden the editable learning procedure and record missing replay coverage explicitly. A change to construction, context or capability bytes generally needs new outcomes. Replay improvement is a screening result, not evidence of better future discoveries. Do not copy a parallelism reward without measuring its costs.

### The Last AI Built by Humans: Toward Genuine Recursive Self-Improvement

[Paper, v1](https://arxiv.org/html/2609.11873v1). Read evidence scope in section 2.3, experience autonomy in 3.4, meta-improvement in 3.6, cross-level synthesis and selected challenges in section 6.

This is a survey/framework, including evidence of differing maturity, not one implemented RSI algorithm. It distinguishes autonomy over learning experience from autonomy over improvement strategies, and structural inheritance of an improver from effective improvement of that improver.

**Adopt:** explicitly state which learning decisions the system controls. Acquired experience must change later acquisition decisions. A revised improver must govern a later round before claiming structural recursion; better successors require additional evidence. Human mission, protected evaluation and resource authority can remain fixed. Do not treat a level diagram as a competence score.

### HyperAgents

[Paper, v1](https://arxiv.org/html/2603.19461v1). Reread sections 3 and 7; earlier project reading also covered experiments in sections 4–5.

Task execution and meta-level generation are combined in a modifiable program within an archive-based search. The main framework retains fixed outer selection/evaluation and a fixed task distribution.

**Adopt:** make the procedure generating improvements an executable, inherited object. **Limit:** editable meta instructions or stronger task solving alone do not demonstrate a better improver. Our comparison should follow descendant production under comparable starting conditions and budgets.

### Darwin Gödel Machine

[Paper, v1](https://arxiv.org/html/2505.22954v1). Read abstract and section 3.

Empirical agent revision replaces a theoretical proof-of-improvement requirement; an archive preserves alternative agents as possible starting points.

**Adopt:** preserve useful alternatives rather than always mutate one winner. Our current genome archive already supplies part of this substrate. Do not claim that an archive makes search open-ended in effectiveness, or that a coding-score gain proves a general improvement process.

## Memory, context and executable competence

| Source and inspected scope | Mechanism relevant here | Design consequence and limit |
|---|---|---|
| [Agentic Context Engineering, v1](https://arxiv.org/html/2510.04618v1), section 3 and discussion | Structured context entries, incremental updates and refinement rather than repeated monolithic rewriting. | Use localized lesson updates as a strong baseline. Model-reported helpfulness is feedback, not independent evidence. Structured text can help; executable learning does not require rejecting it. |
| [A-MEM, v1](https://arxiv.org/html/2502.12110v1), sections 3.1–3.4 and 6 | Structured notes, generated semantic links and evolving descriptions, with model-dependent organization. | Separate immutable observations from revisable interpretations. Retrieve through derived structure while preserving opposition and source identity. A semantic link is not an established causal relation. |
| [Recursive Language Models, v1](https://arxiv.org/html/2512.24601v1), section 2.2 and limitations in 5 | External context inspected through a REPL, with optional subordinate model calls. Evaluated recursion and execution choices have limits and overhead. | Treat context selection as bounded computation. Compare programmatic inspection with and without subcalls; do not promise unlimited context or costless recursion. |
| [LILO, v2](https://arxiv.org/html/2310.19791v2), sections 3 and 5 | Alternates program synthesis, symbolic abstraction/compression and documentation of the learned library. | Mine recurring computations for reusable methods. Compression proposes abstractions; fidelity and later use justify them. Its domain languages and search machinery are supplied structure, not a ready-made general Python skill learner. |
| [Voyager](https://arxiv.org/abs/2305.16291), abstract only in this pass | Automatic curriculum, executable skill library and iterative environment feedback using a fixed API model. | Supports studying persistent external skill growth without weight training. Minecraft supplies a rich environment and feedback; the abstract does not justify copying its architecture across arbitrary domains. |

## Search and coordination

| Source and inspected scope | Mechanism relevant here | Design consequence and limit |
|---|---|---|
| [GEPA, v2](https://arxiv.org/html/2507.19457v2), sections 3 and 3.1 | Reflects on traces to propose prompt revisions; selects complementary candidates using per-task performance rather than only the aggregate winner. | Use a strong prompt optimizer and complementary policy archive as comparators. Prompt adaptation can be substantive; our executable mechanisms must demonstrate an additional useful decision or affordance. |
| [Towards a Science of Scaling Agent Systems, v1](https://arxiv.org/html/2512.08296v1), section 4.4 and limitations in 5; earlier task-comparison reading | Coordination overhead and benefits depend on task, topology and model setting. Studied collectives and heterogeneity are limited. | Learn when decomposition is useful; retain a strong single worker and parallel portfolio baseline. Do not import numerical thresholds as universal routing rules or equate agent count with intelligence. |

Prior background remains relevant: [DreamCoder](https://arxiv.org/abs/2006.08381), [Stitch](https://arxiv.org/abs/2211.16605) and [FunSearch](https://www.nature.com/articles/s41586-023-06924-6). Their earlier reading record is preserved in this file's Git history. They were not newly replicated or fully reread in this pass.

## Our synthesis and unresolved questions

The architecture proposal connects evidence, executable capabilities and decision policies through a persistent investigation. Its central hypotheses are that acquired instruments should change the agenda; replay coverage should direct fresh exploration; contradicted claims should trigger development; and revised learners should be assessed by their descendants. These are proposed couplings, not results established by the sources above.

Before choosing representations or libraries, answer:

1. What must survive between worker invocations for a question to remain the same investigation?
2. Which evidence and counterevidence should a decision see, and what is deliberately unavailable?
3. What makes a procedure applicable, and how does a new instrument expand possible experiments?
4. Which policy changes can existing history evaluate, and which require fresh execution?
5. What later outcomes distinguish an improved learner from a stronger one-off solver?

No source establishes a globally best architecture, unrestricted recursive improvement, or superiority over another general assistant framework. The proposed program must earn those narrower claims it actually tests.
