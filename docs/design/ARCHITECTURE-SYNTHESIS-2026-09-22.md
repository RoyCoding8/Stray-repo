# Architecture synthesis: a persistent investigator that develops its capabilities

Research decision, 2026-10-13. This replaces the historical consolidation plan at this path; Git preserves that plan. The [ledger](../../reports/PROJECT-LEDGER.md) owns implementation status. The [research notes](COGNITIVE-RESEARCH-NOTES.md) record sources and reading scope. This is a proposed architecture, not a claim of empirical superiority or a new implementation assignment.

## 1. Destination and foundation

Build a system that pursues objectives over time, chooses what to investigate, develops reusable capabilities, and improves how it learns. Software, mathematics and computational science provide environments for that goal. A finite coding bank is an instrument, not the product boundary.

Accept the current bounded revision loop as the foundation prototype at its scope. It has durable execution, artifact identity, development evidence, genome proposals, independent task verification and incumbent comparison. Live instruction acquisition and fresh-process smoke use have been observed. Useful executable-skill acquisition, transfer, sustained autonomous investigation and improved learning remain open.

The next program develops those missing mechanisms. It does not wait for statistically convincing improvement before allowing another architectural iteration. Behavioral completion, exploratory utility and robust improvement are separate milestones.

## 2. Architecture and alternatives

Select **one persistent investigation owner, with versioned operational and learning policies, over the existing execution kernel**. Temporary model invocations and teams supply computation. They do not each own a separate memory, agenda or lifecycle.

Many investigations can run concurrently. Each has one authoritative continuation;
the shared agenda allocates workers and resources across them. Compatible claims
and capabilities can be reused across investigations without sharing hidden
assessment data. This ownership rule does not restrict the system to one agent.

| Alternative | Attraction | Limitation |
|---|---|---|
| Expand instruction genomes and run the existing task loop longer | Cheap; a strong baseline | The fixed loop still chooses the work; context and development decisions remain mostly implicit inside prompts. |
| Rebuild a society of permanent specialists | Apparent autonomy and specialization | Multiplies owners before establishing which decisions need separation; adds communication and recovery obligations. |
| Persistent investigator with executable decision policies | Makes experience selection, reuse and learning choices explicit and revisable | Requires a decision interface and migration of the current loop; selected for the stated goal. |

Keep useful broker, budget, artifact, verifier and genome machinery. Migrate the fixed loop's decision ownership, then delete the replaced path. Do not leave two controllers deciding the same work. A subsystem rewrite is appropriate where its ownership prevents this design; a new database, universal agent DSL or service mesh is not justified merely by this plan.

## 3. Research inputs

[Dream-RSI](https://arxiv.org/html/2609.14858v1) evolves executable exploration-policy code using recorded discovery trees. Its discovery agent, policy developer and evaluator stay fixed. Replay reveals recorded outcomes rather than generating new ones. We borrow live discovery plus policy screening; unrecorded experiments still require execution.

[The Last AI Built by Humans](https://arxiv.org/html/2609.11873v1) is a survey and autonomy framework. Useful distinctions include control over future learning experience and structural versus effective improvement of the improver. We use these to specify responsibilities, not to assign ourselves a capability level.

[HyperAgents](https://arxiv.org/html/2603.19461v1) makes task and meta-level behavior editable while retaining fixed outer components. This motivates executable learner revision alongside operational revision. Protected authority and independent assessment remain outside our learner's control.

Executable libraries, context adaptation and prompt optimization contribute complementary mechanisms. Sources and limitations are in the research notes. None establishes that combining them will work or that our combination is novel.

## 4. Abstract model and ownership

Let durable research state be:

`S = (charter, investigations, experience, claims, capabilities, policies, allocations, pending effects)`.

An investigation contains an objective, unresolved questions, proposed explanations, candidate interventions, observations, dependencies and continuation state. It can span many worker invocations and learning rounds.

The human supplies objectives and authority limits. The system chooses investigations, experiments, context, methods, delegation, performance settings and stopping within those limits. It may propose charter changes; it cannot authorize them itself.

For each decision:

1. Construct `V = view(S, purpose, visibility, context budget)`.
2. A versioned operational policy proposes `D = operate(V)`.
3. The kernel admits permitted effects under the allocation, or records a refusal.
4. Workers execute admitted effects. Observations and unresolved outcomes enter the durable record.
5. Apply the accepted decision and observations to the investigation state.

A learning policy proposes persistent changes:

`changes = learn(development experience, capabilities, policies, allocation)`.

Changes can affect executable skills, context construction, experiment selection, coordination or the learner itself. Assessment determines their permitted use. Editing an artifact and inheriting an effective behavior remain different events.

These expressions specify responsibilities, not a Markov model of the world or proof of convergence. Visibility, admissible effects, interruption semantics and domain-specific success obligations need formal contracts before implementation.

| Owner | Authority |
|---|---|
| Kernel | Identify and admit effects; enforce limits; preserve outcomes and uncertainty; protect assessment and publication. |
| Investigation owner | Maintain one continuation; invoke policies; apply accepted state transitions. |
| Operational policies | Choose observations, methods, context, effort, decomposition and stopping. |
| Learning policies | Diagnose limitations; propose, test and consolidate changes; select future learning experience. |
| Domain instruments | Supply observations and checks with explicit validity limits. |
| Human | Set mission and privileged authority; inspect, redirect, suspend or retire work. |

The current Codex CLI invocation is a coarse worker. Initially the investigator owns decisions **between** invocations. It cannot claim to control retrieval or reasoning inside Codex. If finer control becomes necessary, migrate that worker interface explicitly.

## 5. Components and mechanisms

### 5.1 Investigation and autonomous agenda

Use a durable agenda of objectives, open questions, opportunities and blocked work. Completed effects, new evidence, due commitments or authorized idle intervals make work eligible. A timer wakes execution; the agenda decides whether useful work exists.

The policy chooses among solving, gathering information, practicing, developing a capability, revisiting a claim, consolidating and stopping. It names the question or capability an action could change. Begin with a transparent portfolio baseline, then adapt allocation from observed consequences.

Expected usefulness and uncertainty are estimates, not certified probabilities. Preserve exploration allocation so immediate task score cannot consume all research effort. Generated learning tasks need separate checks of validity, difficulty and usefulness.

**Behavioral obligation:** a persistent capability change alters which experience is selected next without a human supplying the next task. Cycling through a fixed list is insufficient.

### 5.2 Experience and epistemic memory

Use one experience store with distinct views:

- Observations: what was requested, executed and measured, including failures and uncertainty.
- Claims: interpretations with scope, support, opposition and status.
- Procedures: executable methods and applicability evidence.
- Continuations: unfinished questions, next discriminating actions and pending dependencies.

Raw evidence remains unchanged. A new interpretation supersedes a claim without rewriting the observation. Semantic links and summaries are derived claims; agreement among summaries is not independent evidence.

Consolidation proposes merges, scope restrictions, abstractions and retirement. Frequent retrieval must not make a mistake more authoritative. Preserve contradictions and failed applicability examples; remove redundant views without losing reconstructable evidence.

**Behavioral obligation:** later decisions use relevant experience, recover from contradicted lessons and resume the same question after restart. Compare with raw history and structured text lessons.

### 5.3 Context as controlled computation

Keep large experience and artifacts outside the prompt. A context policy chooses queries, programmatic inspection, evidence excerpts and bounded subordinate model calls. It produces a decision-specific view containing support, opposition, uncertainty and missing information.

Use cheap filtering and exact inspection before semantic synthesis where appropriate. Incremental lesson updates avoid rewriting all memory. Summaries retain source references and do not replace source bytes where execution depends on them.

Context construction can be revised independently of the solver. Model calls, intermediate text, elapsed time and context size count. Recursive inspection is an option, not a requirement for every task.

**Behavioral obligation:** selected evidence changes decisions on dispersed-information tasks, while irrelevant or misleading memories do not gain authority. More prompt text alone is not success.

### 5.4 Executable capabilities and representations

A capability is a versioned executable artifact with an invocation interface, preconditions, observable postconditions, effects, dependencies, limits and applicability evidence. Documentation helps choose and invoke it; execution carries the procedure.

Support reusable methods and instruments that create new observations. An acquired parser, simulator, proof checker or experiment generator can change what the system can learn next. Representation learning includes useful encodings and adapters, not only final task solvers.

Begin with ordinary code packages and existing artifact machinery. Find abstractions in recurring successful computations and failures; check replacements on original uses and changed inputs. Do not invent a universal symbolic language before the corpus warrants it.

Distinguish task-local candidates, experimental reusable capabilities and trusted defaults. Bounded exploratory use need not wait for a broad improvement claim. Selection records which capability was requested and executed, and why it applied. Candidate code runs through bounded child execution, never on the coordinator host.

**Behavioral obligation:** generated bytes execute, survive fresh-process reuse and affect behavior on a changed task. Distinguish no-op, disconnected and inapplicable methods from useful reuse.

### 5.5 Search history and dreaming

Record alternatives and evidence visible when choices were made. Each branch preserves its starting artifact state, action, outcome, resources and continuation. Replay must not reveal future results.

Background development has two activities:

1. **Replay:** compare policies selecting, ordering, extending or stopping within recorded support.
2. **New investigation:** construct hypotheses, tasks, abstractions or policies requiring fresh checks or live outcomes.

They share artifacts and decision interfaces, not an invented outcome oracle. If replay lacks an action's consequence, report missing coverage. Neither punish the action as a failure nor award an imagined result. Select informative live branches to expand coverage.

Retain complementary policies by task profile and resource tradeoff rather than aggregate score alone. Charge acquisition and replay compute alongside deployment compute. Measure concurrency costs instead of assuming a universal parallelism bonus.

Separate permanent evidence from the active search archive. A bounded working set
keeps alternatives with distinct demonstrated behavior or a concrete reassessment
reason; old versions remain recoverable without all being loaded or reconsidered
on every round. Diversity labels alone do not establish useful diversity.

**Behavioral obligation:** a replay-selected policy changes live branch allocation through the same decision interface. Report replay ranking separately from subsequent live results.

### 5.6 Learner and learner revision

The learning policy is an executable procedure for selecting evidence, diagnosing a bottleneck, proposing interventions, allocating checks and deciding retention. Text instructions remain useful inputs but are not the only editable surface.

Distinguish unavailable tools or bad context from missing procedures, weak search, invalid evaluation and model limitations. Prefer discriminating interventions over changing every surface together. The learner can revise its diagnosis or construction procedure and pass that version into a later learning round.

Measure separately whether the revision controls successor generation and whether its successors improve. Compare learners from common starting capabilities and experience, on later tasks, including construction costs. Better performance of the learner's own solution is insufficient.

**Behavioral obligation:** an inherited learning-policy change causes a different subsequent development decision and attributable successors. Effective improvement needs longitudinal evidence beyond this mechanism test.

### 5.7 Temporary teams

A team is an executable work graph selected for an investigation. Roles have input artifacts, output obligations, access limits and explicit joins. Independent exploration, complementary measurements and adversarial checking are candidate structures; permanent personas are not required.

Retained team policies control decomposition, sequencing, dispatch, joins and rework. Advice inserted into a coordinator prompt is a textual baseline, not executable coordination learning.

**Behavioral obligation:** changing the coordination program changes decisions and the composed artifact. Compare against a strong single worker with equivalent tools and a simple parallel portfolio. Count duplication, communications and integration. Free tokens do not remove those costs.

### 5.8 Assessment and long-horizon stewardship

Use local checks during work, development comparisons during learning, later-use monitoring after retention and periodic independent assessment. Keep sealed answers out of learning views. Passing a software test, checking a proof and supporting a scientific hypothesis are different achievements.

Track useful work, reuse, transfer, learning yield, resources, recovery and human intervention over a continuing campaign. Short probes qualify mechanisms; they cannot establish sustained improvement. Infrastructure failures remain separate from task and learning outcomes.

The runtime must persist and resume campaigns without ChatGPT supervision. The human sets charter and bounds, then receives inspectable results and actionable exceptions. Unbounded dispatch and automatic privileged actions are not prerequisites for autonomy.

## 6. Cross-component research hypotheses

These are our proposals, not established paper results:

1. **Acquisition changes the agenda.** A new instrument enables previously unavailable observations; the agenda exploits and evaluates that opening.
2. **Missing replay coverage guides exploration.** A promising unevaluable action becomes a candidate live experiment rather than being silently discouraged.
3. **Contradictions trigger development.** Failed applicability can cause a scope repair, discriminating probe or new method, rather than only a longer summary.
4. **Consolidation improves executable reuse.** Compression is useful when later retrieval, invocation or development benefits justify it.
5. **Learners are judged by descendants.** Preserve complementary development strategies and evaluate what their successors later do.

These couplings are the research center. An inventory of eight sophisticated modules would not demonstrate them.

## 7. Component plans and build order

The original philosophy-to-release stages remain. This program refines architecture across stages 8–10; it neither restarts the project nor declares release readiness.

The [master build plan](../plans/MASTER-PLAN.md) divides this architecture into
ten component plans with dependencies, delivery slices and acceptance scenarios.
It owns the build order. The broad research themes remain investigation and
capability use, experience-directed development, and learner revision with
coordination and transfer. They are not indivisible implementation batches.

Build one part to a working checkpoint before advancing. Basic investigation,
memory, context and capability use lead to an autonomous agenda and continuing
campaign. Advanced replay, learner revision, transfer and teams can follow.
Finalize technology where the component mechanism requires it.

Existing detailed mechanism drafts are inputs, not automatically current API contracts. Review them against this synthesis and the simplified runtime. Do not revive an archived implementation because its old document has a matching name.

## 8. Experimental program

Use a connected campaign rather than one demo per module. Begin with meaningful software work and computational mathematics with independently checkable results. Extend to scientific hypothesis testing when domain instruments can represent observations and uncertainty honestly. A shared reduction wrapper does not itself establish general transfer.

Follow investigators through acquisition, retention, changed-task use, contradiction, consolidation, interruption and resumption. Include tasks requiring different information and procedures, not renamed variants. Distinguish learned methods from stored answers and supplied scaffolding.

Keep strong comparators: the current genome loop, a well-equipped single worker, structured text lessons, a simple executable library, a fixed exploration portfolio and an unchanged-copy control. After the connected path works, isolate important mechanisms. Avoid a huge factorial campaign before identifying the bottleneck.

Measure later use across learning rounds, including acquisition costs. If a free router changes its model, do not attribute backbone variation to learning. Continuing campaigns can accumulate evidence without using the human's interactive research budget for supervision.

Build completion means intended decisions and effects occur and can be inspected. Improvement requires an appropriate comparison; improved learning requires better successor production. Broad superiority requires far broader evidence than we currently have.

## 9. Next implementation unit

The next implementation unit is [P01, persistent investigations](../plans/01-INVESTIGATIONS.md).
Pin its state and transition contract, then implement its public continuing and
resuming consumer. Later plans constrain shared interfaces without requiring
their implementation now. This planning pass starts no runtime work.

Leave detailed engineering audits to implementation. Reopen architecture when
findings contradict decision ownership, evidence semantics or intended behavior.
