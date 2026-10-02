# Settlement architecture refinement

Status: refinement map, updated 2026-09-09. The selected R0-R4 baseline is [REFINED-ARCHITECTURE.md](REFINED-ARCHITECTURE.md); R5 is in [REPRESENTATION-DESIGN.md](REPRESENTATION-DESIGN.md), R6 in [TECHNOLOGY-DECISIONS.md](TECHNOLOGY-DECISIONS.md), and R7 in [PRACTICAL-SPECIFICATION.md](PRACTICAL-SPECIFICATION.md). The user explicitly authorized treating the earlier constitution and D1-D82 as reasoning aids rather than constraints; section 8 of the selected baseline records replacements. The historical documents remain unchanged. No implementation work is included.

## Task list

- [x] Recover the user's intended system and the original design process.
- [x] Propose levels of refinement and a conceptual parts map.
- [x] Draft the first level's purpose, distinctions, and outstanding questions.
- [x] Refine R0: philosophy, purpose, and desired character.
- [x] Refine R1: intuitive behavior, conceptual parts, and their interactions.
- [x] Refine R2: precise meanings and competing mechanisms.
- [x] Specify R3: abstract entities, relations, transitions, and obligations.
- [x] Compose R4: a coherent abstract architecture and scenario traces.
- [x] Perform a conceptual adversarial review and record conditional invariant arguments.
- [x] State empirical rejection criteria and separate selected design from demonstrated learning.
- [ ] Discharge empirical learning obligations E1-E8 through later experiments.
- [x] Isolate this pass from concurrent work, including its glossary and task list.
- [x] Choose R5: representations against the abstract requirements.
- [x] Check cross-document vocabulary, local links, version/revocation behavior, and representation soundness versus coverage.
- [x] Choose R6: technology against workload and operational constraints.
- [x] Verify consequential technology guarantees against primary documentation.
- [x] Produce R7: a practical specification and experimental build sequence.
- [x] Specify command idempotency, transaction order, effect reconciliation, artifact publication, and checkpoint behavior.
- [x] Define a matched-budget experiment for textual versus executable retained competence.
- [ ] Execute the S0-S7 build and acceptance gates in a separately authorized implementation pass.
- [ ] Calibrate inferential evaluation protocols before making broader competence claims.

## Working intent

The intended system is a persistent, general, autonomous society using externally supplied model inference. It should perform requested work, originate investigations within its charter, accumulate reusable competence, and improve how it learns and operates. Software engineering and mathematics are possible proving grounds, not an exhaustive domain definition. Updating model weights is outside the present design scope, but must not be treated as permanently impossible.

The selected baseline now commits to composable capabilities, a developmental frontier, representation invention, and adaptive worker composition with explicit alternatives and rejection criteria. These are design decisions; their empirical advantages remain hypotheses to compare.

The existing user intent includes disposable workers, durable accumulation, a society rather than permanent reliance on one privileged reasoning agent, and a human relationship that can progress toward gardener. Specific selection algorithms, storage shapes, and coordination arrangements remain subject to explicit reconsideration.

## Two dimensions of the work

The user clarified that the desired progression is philosophy -> intuitive conceptual picture -> precise abstract description -> formal description -> architecture -> representation -> technology -> implementation. Each stage translates the same underlying idea into a more precise language. The intuitive stage must not be skipped in favor of premature architectural categories.

Levels specify how precisely we describe the system. Parts specify which questions we must answer. We revisit the same parts at successive levels; their names do not prescribe software modules, tables, agents, or processes. The parts map below is a provisional coverage aid, not a demand to design eight subsystems now.

## Refinement levels

| Level | Question | Required output | Completion condition |
|---|---|---|---|
| R0 Philosophy | What kind of thing do we want, why should it exist, and what should growth mean? | A short philosophy, guiding tensions, and the human relationship. | We can describe the intended character and direction without invoking mechanisms or technology. |
| R1 Intuitive conceptual picture | What would this system be like in motion, across hours, months, successes, and failures? | Narratives of working, exploring, learning, disagreeing, and changing; a provisional conceptual parts map. | We share a coherent picture of its behavior and what persists, while mechanisms remain open. |
| R2 Precise abstract description | What do the intuitive words mean, and what mechanisms could realize them? | Precise definitions, responsibilities, relationships, and serious alternatives for consequential mechanisms. | Terms such as capability, learning, autonomy, and progress have distinguishable meanings; leading mechanisms have reasons and recorded uncertainties. |
| R3 Abstract semantics | What exactly exists, changes, and follows? | Entities, relations, operations, preconditions, outcomes, invariants, and progress conditions. | Independent readers can trace the same scenario consistently without assuming a database, language, or framework. |
| R4 Abstract architecture | How do the mechanisms form one working whole? | Module responsibilities, interfaces, authority, persistence, feedback loops, and complete scenario traces. | Ordinary work, learning, disagreement, interruption, resource exhaustion, and self-change have coherent end-to-end behavior. |
| R5 Representation | How should these semantics be expressed? | A justified representation for each kind of state and behavior, including versioning and interpretation. | The representations preserve distinctions and operations required at R3-R4, with acceptable complexity and migration costs. |
| R6 Technology | Which concrete tools support those representations and operations? | Stack choices and rejected alternatives tied to expected workloads and constraints. | Each dependency has a demonstrated job and a defensible operational cost. |
| R7 Practical specification | What can a builder implement and verify? | Execution protocols, interfaces, lifecycle rules, acceptance experiments, build slices, and operator behavior. | A builder can act without inventing the learning theory or resolving hidden conceptual contradictions. |

This is an ordered process with feedback. A contradiction at R4 can reopen R2. A representation that erases an essential distinction must be changed, or the upstream decision explicitly reconsidered. We do not force a straight descent through discovered problems.

## Proposed conceptual parts

### A. Direction

How purposes become agendas: requested work, autonomous exploration, commitments, priorities, and stopping. Distinguish choosing a goal inside an authorized purpose from changing that purpose. Explain how exploration remains worthwhile when immediate task reward is unavailable.

### B. Experience and belief

How observations become claims, explanations, predictions, and revised beliefs. Distinguish what occurred from its interpretation, and evidence from permission. Preserve scope, uncertainty, disagreement, and the conditions under which previous conclusions cease to apply.

### C. Continuity and attention

What survives a worker, what must remain accessible, and what a current decision needs to see. Cover memory, retrieval, working state, forgetting, compaction, context construction, and resumption. Storage and access are distinct questions; an artifact's existence does not ensure that it will be useful later.

### D. Competence and composition

What a learned capability is, when it applies, how it is invoked, and how capabilities combine. Explore procedures, tools, strategies, representations, role bundles, and any later learned models as candidate carriers. Do not decide their representation at this level.

### E. Deliberation and action

How a problem becomes an attempt: planning, experimentation, execution, observation, revision, completion, and abandonment. Explain why the next action is appropriate given current evidence and resources. Cover both changing the world and gathering information about it.

### F. Collective organization

How temporary workers collaborate, divide effort, preserve independent attempts, reconcile disagreements, and allocate shared resources. Separate the user's preference for a society from any particular scheduling algorithm or fixed organization chart.

### G. Learning and development

How experience changes future competence: candidate generation, comparison, credit, retention, transfer, consolidation, and retirement. Include development of new task families and representations. Distinguish changes to task-solving behavior from changes to the procedures that produce those changes.

### H. Self-governance

What may change autonomously, what requires stronger evidence, and what remains externally anchored. Cover configuration, authority, budgets, identity, recovery, and continuity across revisions. Explain how the system changes its operating methods without invalidating the basis on which improvement is measured.

## Concerns spanning every part

- Evidence: what would support or refute a claim that this mechanism works?
- Resources: whose inference, time, computation, storage, or attention does it consume?
- Change: what is versioned, what depends on it, and what happens when it is revised?

These are questions to apply throughout the architecture, not three additional services.

## Historical starting material for R0 and later refinement

The material below records the earlier starting point. Its proposed statuses and open questions describe that stage; the selected baseline now resolves the philosophical choices and refines these definitions. [GLOSSARY.md](GLOSSARY.md) records the redesign's current vocabulary without claiming that the runtime already implements it. This entire pass is isolated in `tmp/architecture-refinement/` at the user's request.

### Philosophy draft

The Settlement is a persistent society whose temporary members contribute to a shared ability to understand, construct, and investigate. Its development is visible in what later members can accomplish and how they approach unfamiliar problems. It can initiate work within its purpose, preserve useful disagreement, and change its methods and organization through experience. The human provides direction and remains the ultimate authority while the society takes increasing responsibility for its own work and development.

This is a starting interpretation of the user's intent, not a newly binding declaration. Open philosophical choices include how strongly curiosity should compete with usefulness, what continuity across deep self-change requires, and which qualities make a society preferable to another form of collective system.

### Purpose statement

Develop a persistent system that expands the range of useful problems it can solve, improves the reliability and efficiency of its existing competence, and originates productive investigations within its charter, while using external models for inference and retaining human control over purpose and ultimate authority.

This statement is proposed, not committed. In particular, the relative importance of breadth, depth, discovery, and cost has not been reduced to one objective.

### Distinctions required before mechanisms

1. Performance: the outcome of a particular attempt under particular conditions.
2. Competence: an evidenced ability across a stated family of conditions and resource limits.
3. Learning: a durable change that improves subsequent competence or efficiency, supported by comparisons appropriate to the claim.
4. Development: a change in the system's repertoire or organization, including new representations and ways to acquire competence; beneficial development still needs evidence.
5. Autonomy: discretion over specified decisions, including methods, action, agenda, and self-change. It is not a single unrestricted permission.

These are tentative working definitions. They are not additions to the binding glossary yet.

### Improvement has several coordinates

- Breadth: previously unsupported problem families become tractable.
- Depth: more difficult instances become tractable within a family.
- Reliability: success becomes more consistent under relevant variation.
- Efficiency: comparable outcomes require fewer resources, including human intervention.
- Transfer: retained learning helps on independently selected tasks beyond the originating examples.
- Learning efficiency: new competence can be acquired with fewer learning resources.

Do not combine these into an arbitrary scalar now. Retain explicit trade-offs. Both acquisition cost and subsequent use cost matter; a capability may be valuable only after sufficient reuse.

### Distinguishing scenarios

| Observation | What we may conclude |
|---|---|
| More notes, roles, tools, or messages appear; subsequent behavior is unchanged. | Accumulation occurred; increased competence is not established. |
| A previously seen task is solved from a saved answer. | Useful recall may have improved; generalization is not established. |
| A task succeeds after ten times as much inference. | Performance improved under a larger budget; efficiency and learning are unresolved. |
| A learned method helps independently selected new cases under comparable budgets. | Evidence of competence gain within the tested scope. |
| An investigation fails but rules out a live approach and prevents repeated wasted effort. | The investigation may be valuable despite task failure; downstream benefit still needs assessment. |
| A revision raises its own score by changing the evaluator. | The score change alone does not establish improvement. |
| A specialized improvement degrades another family. | A trade-off exists; retain conditional claims rather than declaring global progress. |

### Important unresolved tensions

- Breadth versus depth: how much specialization may autonomous exploration buy?
- Immediate utility versus stepping stones: how is exploration protected without rewarding endless novelty?
- Adaptation versus continuity: what makes successive revisions one accountable system?
- Flexible evaluation versus a stable comparison: how can evaluators improve without making progress self-certified?
- Collective autonomy versus coherence: what coordinates finite resources and commitments without prescribing one permanent reasoning controller?

## Record for each consequential choice

1. Question and level.
2. User intent, applicable constraints, and earlier decisions used as reasoning aids.
3. Leading proposal and causal explanation.
4. Strongest alternative and the trade-off.
5. Concrete scenario, failure case, and cheapest distinguishing probe.
6. What would cause reconsideration.
7. Status: proposed, supported, selected, or superseded; reversal cost separately recorded.

A selected design can still be empirically unsupported. A successful implementation test can still leave the architectural hypothesis unresolved. Keep those distinctions explicit.

## How we proceed

Refine in dependency order, revisiting earlier levels when contradictions appear. A substantive pass can traverse several levels, as the user requested; it need not stop for approval at every boundary. Begin with philosophy and the intuitive picture before demanding precision. Compare choices with the largest impact on learning and generality, rather than interchangeable implementation details.

Record selected commitments, unresolved obligations, and the reason the next level is answerable. The selected baseline's replacement map makes revisions to the earlier decisions explicit. R0-R7 now have selected design documents. The next work is implementation and empirical qualification against those documents; new constraints or failed experiments can reopen a decision.

No implementation, representation selection, stack selection, subagent work, or fine-tuning is authorized by this document itself.
