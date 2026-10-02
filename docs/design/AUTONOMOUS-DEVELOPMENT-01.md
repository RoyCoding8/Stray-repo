# Autonomous Development 01: system-chosen investigations and executable reuse

Selected next prototype design, 2026-09-15. This follows the user's standing generality checkpoint in [the roadmap](REFINEMENT-ROADMAP.md). It does not reinterpret EC02's doubled records as learning or change its frozen experiment. Implementation is included, with dependency gates, in [the combined assignment](../../WORKER-EC02-CLOSURE-AND-AUTONOMOUS-DEVELOPMENT-01.md).

## 1. The architectural move

The next unit of progress is a **self-directed development trajectory**, not another externally specified repair. Give the system a broad operational objective, a repertoire, observed experience and finite authority. It must choose a capability gap, formulate an investigation, obtain evidence, develop a reusable executable change, check it and decide what to try next. We still supply primitive tools, evaluation standards and a bounded environment. The system supplies the intermediate research questions and interventions.

This tests initiative and learning across two different problem representations. It does not claim unrestricted discovery, general intelligence or an improved learner that rewrites itself. The initial learner policy remains fixed; changing that policy becomes a later experiment once trajectories expose a useful target. An EC02 benefit is not a prerequisite. A trustworthy execution/evidence path is.

## 2. Reuse the existing architecture

Reuse [agenda options](AUTONOMOUS-AGENDA.md), [development episodes](LEARNING-MODEL.md), [representation execution](REPRESENTATION-AND-TRANSFER.md), context packets, capabilities, artifacts, grants and the broker. Keep one authoritative state machine per existing responsibility. Do not add a heartbeat service, agent parliament, universal graph store or a second experiment ledger.

Three distinctions organize the implementation:

| Object | Operational meaning | Required evidence |
|---|---|---|
| Opportunity | A limitation or possibility the system proposes investigating | References to permitted observations; expected decision consequence; requested finite allocation |
| Investigation | Work intended to distinguish explanations or evaluate an intervention | Predeclared question, proposed test, actual operation outputs, negative/inconclusive outcomes |
| Executable improvement | Retained computation that changes later task execution | Response/package/input/operation lineage, independent checks, scoped subsequent use or explicit rejection |

Record opportunities as existing agenda/investigation records, investigation work as development episodes, and improvements as capability versions. A small experiment-specific record may link their IDs. No new storage engine is required.

## 3. Formal trajectory and decision interface

At a decision boundary the trusted runtime materializes

    X_t = (charter, visible_work, experience, repertoire,
           unresolved_questions, pending_effects, remaining_allocation).
    learner(X_t) -> proposed_option
    admit(proposed_option, authoritative_state) -> investigation or refusal
    execute(investigation) -> observed_evidence
    update(experience, repertoire, agenda) -> X_(t+1)

The learner cannot write observations, settlements or success into authoritative state. A proposed option includes its basis references, a testable question or capability gap, the next concrete action, requested resources, and how possible results change the next decision. Those explanations are hypotheses, not guarantees of value. Reject invented basis references; permit explicit exploratory options grounded in the charter and a stated unknown. Do not invent a numeric expected-value formula from model confidence.

Available substantive actions are: inspect a permitted task/experience; propose and execute a bounded diagnostic or counterexample search; start a development episode for an executable method/instrument; evaluate or reuse an eligible artifact; continue an investigation based on newly observed evidence; or stop. Use existing operation types and composition execution beneath these actions. A selector that only chooses among hand-authored complete solutions does not satisfy development.

Decision identity and packet contents are durable. Repeated callbacks resume accepted work; they do not give the learner a fresh budget. Pending effects are reconciled before dependent decisions. Use bounded event-driven advancement through the existing runner, not a busy periodic prompt loop. Human intervention stops or amends an investigation with a recorded reason; an unrecorded hint contaminates the autonomous trajectory.

## 4. Concrete first environment: investigate failures and mathematical counterexamples

Use the existing Representation 01 task semantics and independently written checkers as a starting point, with a **new AD01 freeze and development/use split**:

- **Software investigations:** reduce a stateful execution trace while preserving a designated interpreter discrepancy. The system can investigate order, overwrite/clear effects, dependencies and which observations distinguish causal from irrelevant events.
- **Finite mathematical investigations:** reduce a graph counterexample while preserving a designated graph property/witness. The system can investigate structural invariants, diagnostic witnesses and reusable search order rather than editing a software repository.

These are genuinely different input/validity semantics, although both admit reduction. That shared algorithmic structure makes this an informative first transfer question. It is not broad scientific discovery or proof of generalization across arbitrary domains. Graph witness checks support their stated finite propositions only.

The objective is: **improve the ability to produce smaller valid explanatory examples across the visible workload, within the allocation, and preserve correctness and supported prior scope**. Reveal normal public task descriptions, interfaces and baseline experience. Do not supply ranked gaps, a task-family-to-best-method map, predetermined explanations, an authored acquired core, future costs or protected use outcomes.

Reuse the supplied `ddmin` and domain-aware greedy reducers as seed capabilities. They must be labeled authored. The learner may construct different executable search/diagnostic behavior and compose or adapt previously checked computation. It may discover that a baseline is already best and stop. Counting a library entry or writing advice is not a capability gain.

Use the existing `representation-01/1` file execution profile for generated core/adapters/instruments wherever its semantics fit. Preserve exact entry/dependency bytes, bounded state and broker-mediated witness queries. The host interprets requests and independent checkers decide preservation; code never certifies itself. Do not force the generated search algorithm to copy the reference core's halving strategy. If a current validator accidentally encodes that strategy rather than the profile contract, record the mismatch and make the smallest explicit profile revision before freezing consumers. Do not use an authored reference core as a hidden fallback labeled acquired.

## 5. What autonomy must visibly do

The human sets the objective, environment, initial capabilities, limits and experiment rules. The system chooses which visible failure/cost pattern matters next, which competing explanation to investigate, what diagnostic to construct or invoke, what executable improvement to attempt, when to abandon it, and whether checked prior computation applies later.

The experiment must allow several sensible choices. Include development opportunities where a cheap existing method suffices; a dependency invalidates a naive deletion; a seemingly novel direction is unproductive; a diagnostic can resolve a useful uncertainty; and prior negative evidence should prevent repeating identical work. Validate these opportunities with authored controls. Do not reward the learner for matching our preferred choice: evaluate the resulting trajectory and report the chosen question/action.

At least one deterministic control changes observed evidence while keeping the charter and initial identities fixed. The next decision must be capable of changing through that evidence path. Test renamed/reordered bookkeeping identities separately. If the live learner chooses identically, report measured inactivity; do not rewrite its output. Distinguish autonomy of selection, investigation, construction and retention rather than collapsing them into a single autonomy score.

## 6. One comparison, whole trajectories

Compare two arms with the same seed repertoire, task descriptions, diagnostic tools, constructor model/configuration, context limits and resource ceilings:

- **I: initiative.** The learner chooses the next opportunity and its allocation from current permitted experience.
- **R: reference curriculum.** A frozen fair rotation chooses the next visible workload item, alternating domains and advancing a fixed order. The same learner then formulates the investigation and constructs/checks methods under the same action semantics.

This isolates the practical effect of system-chosen agenda within a fixed development architecture. It is not a separate test of every cognitive subsystem. R is permitted to learn and reuse methods; otherwise any advantage could just be learning versus no learning. Both arms can stop when no admissible work remains. Preserve differences in subsequent observations as part of their trajectories; never copy useful findings between them.

Freeze three initial worlds, each with three visible development tasks per domain. Run one I/R pair per world: six trajectories. Initial seed experience must be obtained by recorded baseline execution or explicitly labeled authored fixture evidence, symmetrically supplied. If live baseline experience is shared, charge it once to the experiment with explicit shared attribution, and report its amortization separately.

Per trajectory, allow six agenda decision boundaries, at most three development episodes, at most two candidate lineages and four construction calls total including repair, at most sixteen additional diagnostic queries, and at most sixty model calls across the full trajectory including final use. Set aggregate input/output-token, wall-time, source-execution and sandbox caps in the committed cap sheet after development-only calibration and before freezing. Existing smaller grant/profile ceilings still bind. These are proposed maximums for this study, not newly available spending authority.

Freeze twelve protected use tasks per world: six within-scope new instances (three per domain) and six structural-transfer instances (three per domain). The latter must change causal/dependency structure or graph topology, not only identifiers. Reuse known RPR overlap constraints, but audit the new split rather than assuming a new seed guarantees independence. No use feedback reaches either trajectory until acquisition and repertoire selection are finished. This yields 72 final use records across six trajectories. Each arm's complete use phase starts in a fresh process using its frozen experimental repertoire; it cannot reconstruct missing packages with new model calls.

For each use task, choose the eligible repertoire member from development-qualified scope using a selector frozen before protected use. Use the declared baseline when none is eligible. Record requested/selected/executed artifact and fallback independently of task outcome. No automatic global release is involved.

## 7. Outcomes and stopping rules

Freeze the primary benefit rule before execution: I must have no increase in validity failures in either domain; no loss in solved/valid task count in either domain; strictly greater total normalized reduction on valid outputs; and total model tokens, witness queries and sandbox operations each no more than 1.25 times R. Invalid/unknown outputs score no reduction, and unknown mandatory measurements make the benefit verdict unevaluable. Report each world and domain as well as aggregate values; three paired worlds are a descriptive pilot, not statistical proof.

Use the existing quality definition where applicable: reduction relative to the input's size, only if the independent witness-preservation check accepts. Freeze exact treatment of empty inputs and minimum valid size. Report acquisition and use costs separately and as cumulative union totals; no quality/cost weighted reward hides a validity loss. When both arms reach a size floor, quality discrimination is saturated; report any efficiency difference descriptively without changing the primary rule.

Always report mechanism outcomes separately: opportunities proposed; evidence-grounded changed choices; diagnostics executed; constructed/checked/retained artifacts; negative results subsequently respected; actual later invocation; correct abstention; domain coverage; and reuse across changed structure. A negative comparison can still demonstrate a working autonomous development cycle. Missing model output is a construction boundary, not evidence that initiative is useless.

No candidate is a valid trajectory outcome: preserve its failed investigations and run the use phase with the explicit incumbent. Unlike EC02, this study compares development trajectories, so no-acquisition is part of its treatment outcome rather than a nonexistent learned-policy arm. This distinction is deliberate. If the provider/grant is unavailable, finish the apparatus and publish exact blocked phases instead of substituting fixtures for live trajectories.

## 8. Acceptance and implementation boundaries

| Gate | Required production-path observation |
|---|---|
| AD-01 initiative | Public campaign invocation makes a model-proposed investigation from actual experience; no precomputed answer mapping |
| AD-02 investigation | Proposed diagnostic produces attributed real observation, which is delivered at the next decision |
| AD-03 executable change | Acquired source -> staged profile -> checked artifact -> later invocation; substitution/disconnect controls refuse |
| AD-04 negative knowledge | Rejected/incompatible work stays inspectable, and its actual relevance is available to later selection; text alone does not quarantine |
| AD-05 continuity | Kill at a recorded decision and separately after publication; fresh process resumes same campaign without duplicate spend or reconstruction |
| AD-06 retained use | Fresh-process mixed-domain use loads exact eligible bytes; incapable or missing methods fall back explicitly |
| AD-07 fair comparison | Independent checker reproduces world membership, freezes, quality, full operation unions and the declared benefit rule |
| AD-08 agency boundary | Human-set versus system-chosen decisions and all external interventions are visible; protected use feedback cannot drive development |

Mechanism controls may use authored programs and recording doubles, but must enter through the same campaign interface. Helpers alone do not close these gates. The independent reviewer supplies at least one unexpected-but-valid model output and follows it to an actual operation/result. Full implementation requires both successful and rejecting paths, not a large panel of always-failing fixtures.

Run diagnostic controls first, then a single live development/use trace and internal review, then the bounded paired trajectories when separately granted. Do not stop for a new handoff after each internal milestone. Do not expand the number of worlds, generations, domains or evaluator powers during the study. Future learner self-revision, richer scientific environments and open-ended deployment remain later choices.

## 9. Research references and what is ours

[Voyager](https://voyager.minedojo.org/) combines an automatic curriculum with executable skills and feedback-driven program improvement. This supports using a complete curriculum-to-reuse trajectory as a useful unit of investigation; its Minecraft results do not establish our cross-domain claim.

[Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) evaluates code-based agent modifications and explores an archive of alternatives. It motivates preserving unsuccessful and intermediate development history rather than assuming a single monotonic improvement chain. Its coding results do not justify calling our proposed mathematical/software proxy generally intelligent.

Our selected integration is a bounded, evidence-grounded agenda over existing development and executable-retention machinery, with human/system decision boundaries and whole-trajectory accounting. The design choices and pilot thresholds above are ours; they are not guarantees derived from those papers or a claim that executable skill learning is novel. The next design decision should come from the observed bottleneck: opportunity formation, investigation quality, construction reliability, scope selection, or reuse economics.

## 10. Operational refinement after review of `23a3e68`

This section makes the existing design's execution semantics explicit; it does not add a new experiment or expand its grants. The inspected implementation supplies useful worlds and seed reducers but does not yet implement the learner described above. See the [full assessment](../../reviews/EC02-AD01-COMPLETION-ASSESSMENT.md). Keep this experiment directed toward general autonomous development, not optimization of another authored reducer menu.

### The system owns actions; the runtime owns facts

At each boundary, materialize `X_t` from durable state: actual charter, all currently permitted opportunities, prior diagnostic outcomes including failures, available capability versions, pending work, unresolved questions and remaining resources. Use the existing context packet mechanism for the model request. A seed observation is either an attributed execution result or an explicitly authored fixture; do not generate an `unmeasured` observation and present it as accumulated experience.

The learner returns one action from the section 3 language with target, evidence references, question, proposed effect and finite request. Admission validates the action and commits its identity before dependent work. The dispatcher executes that accepted target, not the next item in a surrounding task loop. Refusal returns an observation within the same bounded progression. `stop` terminates further development dispatch; it cannot silently invoke an incumbent development episode. A later frozen use phase can still use the incumbent, with separate attribution.

An action boundary is not automatically a development episode. Inspection/diagnostic work can consume a boundary without consuming construction capacity. Conversely, a construction episode consumes its own episode and lineage/call allowance in addition to the trajectory resources. Track those counters independently; six boundaries never authorize six development episodes.

For I, the learner selects the next opportunity from the visible set. For R, the frozen rotation supplies the curriculum item before the same learner runs. R still chooses its question, diagnostic, method construction and continuation under the same semantics. Keep the two-arm difference at opportunity selection, not different task lists, different constructors or different access to evidence. Honest model inactivity may produce identical trajectories, but a distinguishing recording-adapter control must establish that I can choose differently through the real dispatcher.

### An acquired method is computation, not an entry in a seed menu

Use the existing representation execution profile and capability/artifact lifecycle. A candidate contains model-produced source or a composition with the profile's actual executable semantics, immutable byte identity, dependencies and permitted scope. It must be able to change the search/diagnostic procedure beyond returning the string `greedy` or `ddmin`. Reusing an authored primitive is allowed; attributing that primitive itself as newly acquired is not.

For example, the learned program could derive a deletion order from observed dependency constraints, query a permitted witness instrument, and revise its next proposal after that result. In the other domain, the instrument supplies graph structure and witness validity through its domain adapter. This illustrates a permissible mechanism, not a required solution or hidden answer supplied to the live learner. We provide representation/measurement primitives and the execution contract; the learner supplies the procedure. Never import learner-written source into the trusted host.

Separate three outputs: the reusable program, its task-specific candidate, and the independent assessment. Persist their distinct digests and operation lineage. A smaller valid task instance does not by itself mean a new program was acquired. Retention refers to the program and its checked scope; final use loads that exact version in a new process. Loss of the executable cannot be repaired by looking up an authored seed with the same display name.

### Experience must alter future work and survive a restart

A diagnostic produces evidence, not an authoritative recommendation. Store its input, output, operation identity, dependencies and allowed visibility. The next learner packet includes that result and the unresolved question it addresses. Negative results remain accessible with their scope: repeating a failed idea without new support should be visible, while a changed dependency or genuinely new observation may justify reopening it. Do not hardcode the right answer in a task-ID or family-to-policy table.

Persist the accepted decision and pending effect before dispatch; attach real observations and capability references after settlement. Resume reconstructs the same `X_t`, including repertoire and unfinished work. A receipt-name string is not a settled operation. Cleanup and reconciliation must retain unknown liabilities rather than inventing zero-cost completion. The cost view is derived from the broker's unique operations; it is not another experiment ledger.

### Acceptance must distinguish behavior from serialization

Use the public campaign with a recording adapter whose outputs are chosen independently of implementation. One control chooses a different visible task; one stops; one uses a diagnostic result to choose a different next action. Assert the dispatched targets and absence of prohibited calls. Separately change bookkeeping identifiers while preserving their reference relationships; that change must not be the cause of an apparent mechanism effect.

A successful construction control supplies a valid program outside the seed menu and follows response bytes to staging, checking, retention and fresh-process use. Alter a behavior-bearing branch: observe a changed invocation sequence, candidate, grade or measured resource path on a task designed to expose it. Alter only comments: byte identity changes, but that is not a behavioral success. Disconnect the artifact: refuse or use an explicitly recorded incumbent. Do not require arbitrary programs to change every task's score.

For continuity, compare uninterrupted and interrupted trajectories by settled operations, pending effects, remaining caps, permitted experience, retained version digests and subsequent decisions/use—not only by a spend integer. The environment checker and durable receipt reconstruction remain independent of the learner's self-report. Implement these controls before running more live cells; complete the already specified live pilot automatically when its finite authority is available.
