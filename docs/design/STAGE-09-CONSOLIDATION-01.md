# Stage 9: consolidate around persistent investigations

Direction for the next batch, based on implementation `f3d20ac` and live evidence `a26408f`. The worker first closes the bounded stage 8 interface failures, tests and reports them, then starts the stage 9 work below. The complete assignment is [the worker prompt](../../WORKER-STAGE-08-CLOSE-STAGE-09-START.md). Stage 9 starts now; useful learning and generality remain unproven.

## Evidence and the decision it supports

The reviewer fetched `a26408f089b3c9d601025cf911c4bab37e344d5b` and independently inspected the committed corpus and relevant source. Six repertoires have no members. All 24 use records select the incumbent, twelve in each domain. The ten construction receipts contain four completed responses, three output-limit responses and three timeout/unknown responses. All four recorded validation executions fail with `NameError: name 'reduce_graph' is not defined`.

`packet.public_operations` advertises bare `reduce_graph` and `reduce_software`. `method_exec._DRIVER` injects the `reducers` module into the acquired module, but does not supply those bare names. Existing functions in `experiments/representation/reducers.py` already implement the advertised signatures. Fix the contract where it is owned, rather than teaching the model to guess a different namespace or rewriting every recorded candidate. Check arguments, results, query accounting and both domains, not only name resolution.

The outcome is no acquisition under the executed configuration. It is not a clean estimate of model competence or of the benefit of investigation-selected work. Method execution was obstructed, and transport/truncation lost other opportunities. Archive this run unchanged. Post-fix executions of its candidates are intervention diagnostics and cannot become held-out evidence or retroactively change its outcome.

The reported suite is 849 passed, 592 skipped and two setup errors, with the affected file subsequently passing three tests under a URL-form DSN. This reviewer did not independently rerun that suite or live inference. Earlier study-readiness changes are delivered with worker evidence; this handoff does not certify every authority/recovery path or reopen the previous general audit.

## Purpose

Implement the [accepted direction after the Dream-RSI discussion](ARCHITECTURAL-DIRECTION-2026-09-17.md): persistent investigations, accumulated experience and executable revision of learning procedures. Preserve execution, evidence and authority guarantees while being willing to replace cognitive orchestration. The [Investigation 01 protocol](INVESTIGATION-01.md) remains an input, not an excuse to rename disconnected helpers.

The unit that persists is the investigation. Agents are temporary participants with bounded work. An investigation can continue after its participants and model contexts disappear. It can obtain evidence, construct a method, encounter a limitation in later use, and revise its procedure without a human supplying a new controller between steps.

Software and graph reduction are current instruments. The design must explain where a mathematical or scientific instrument fits without embedding those instruments' task IDs, judgments or fixed panel order in the shared runtime. Do not implement another domain solely to claim generality.

## Semantic contracts to settle

These are meanings and ownership obligations, not six mandatory services, tables or classes. Reuse existing data and interfaces when they satisfy them.

| Contract | Meaning and obligations |
|---|---|
| Investigation | Durable objective, hypotheses or open questions, permitted evidence, pending actions, policy identity, method repertoire and remaining authority. A question can be unresolved, supported, contradicted or retired without pretending that free text alone establishes its status. Hypotheses are optional for routine work. |
| Action and instrument | Versioned operation, actual callable interface, permitted inputs, expected result/failure meanings, dependencies and resource bounds. The same executable contract supplies the model-visible description and executor exposure. Domain code supplies semantics; admission owns authority. |
| Experience | Exact decision-visible input, proposal, admission, operation identities, observations, artifacts and known/unknown costs. State, evidence, claims and executable methods remain distinguishable. Summaries are derived views with provenance, not replacement truth. |
| Learning procedure | Identifiable executable behavior that selects or composes context, diagnostics, construction, revision, reuse and stopping. A procedure can call a model through existing mediated effects; it must still change actual execution. Prompt advice alone is not executable policy acquisition. Domain methods and policies that improve those methods are different retained objects. |
| Branch and replay | A branch pins its starting knowledge, policy and dependencies. Recorded replay returns supported outcomes only when its matching conditions hold. New code, changed context or an unseen action can return unsupported. Predictive simulation is labeled separately and cannot create observations or spend authority. |
| Assessment and retention | Scoped applicability, frozen independent checks, source/dependency identity, measured resources, uncertainty and fallback. Qualification, usefulness, transfer and release are separate decisions. Replacing a policy does not grant it authority to alter its judge, visibility rules or resource ceiling. |

Specify ownership of each write and effect. The investigation records an accepted action before execution; a resumed participant reconciles that action rather than inventing a replacement. Deliberate retries have distinct attempts under the same remaining authority. A policy proposal may alter plans and methods, never mint budgets or silently redefine recorded facts.

## Alternatives to compare

Compare two concrete designs against the current call graph, with their smallest credible public usage examples and state transitions:

1. Consolidate the existing `DecisionConsumer` and trajectory implementation in place. One existing driver owns investigation state; domain modules become instruments and experiments supply conditions and judges. Identify where whole-episode assumptions remain and whether they prevent branching or policy replacement.
2. Extract a durable action-level investigation core over the existing broker, context and artifact facilities. Experiments become clients. Specify which source moves or disappears, how pending work migrates, and why the new ownership reduces coupling enough to justify the change.

Select one and explain why the other loses on the actual workloads. A thin wrapper over unchanged duplicate loops is not consolidation. A new workflow engine, distributed grant service, event store or universal world model is not a default. Large changes are acceptable when required by the chosen semantics; short diffs are not the objective at the expense of the general system.

For each alternative, walk the same trajectory: observe a limitation -> choose an investigation -> construct/check a method -> retain or reject -> fresh-process use -> observe a scope failure -> revise a method or learning procedure -> compare independently -> keep or reject the revision. Show exactly which choices the system makes. Keep human-authored controls and policies explicitly labeled.

## Dreaming and policy improvement

Use the corpus to measure what replay can actually answer before choosing a replay optimization experiment. Count useful decision prefixes, actual delivered context coverage, supported continuations and unsupported alternatives. Distinguish matching a recorded action from estimating the result of a changed policy. One trajectory per prefix does not support arbitrary policy comparison. Inspect the existing replay implementation before proposing another.

The next learner revision should have a falsifiable target. For example, a policy may decide whether to seek another observation, construct immediately or stop. It must be judged on subsequent independent outcomes and full cost, not on the persuasiveness of its explanation. The design must allow richer executable procedures than choosing among an authored menu, while keeping authority and evaluation fixed.

Do not select a full replay-assisted improvement campaign just because Dream-RSI motivated the direction. If this corpus has insufficient behavioral coverage, identify the smallest prospective investigation that would distinguish the leading explanations. Timeouts, truncation, interface mismatch and scientifically unhelpful methods require different interventions. An unsupported replay result is informative and honest.

## Stage 9 outputs and stopping condition

The worker delivers a source-grounded architecture package after the stage 8 fixes, not a speculative platform implementation. It must include:

- Actual public call graph and ownership map for both domains, from study entry through decision, construction, execution, retention and use. Include feedback, restart and export; connect every claimed mechanism to a caller.
- Semantic state/action signatures, one end-to-end usage example, alternatives comparison and selected ownership boundaries. Pseudocode belongs in the design document, not as unused production scaffolding.
- A keep/change/remove/migrate table with concrete files and dependencies. Preserve historical study reproduction explicitly; do not keep two permanent current drivers by default.
- Runnable feasibility checks against the fixed code: both domain contracts; a behaviorally changed policy through the real admission/execution path; pending-action continuity; and supported/unsupported replay. Existing checks can satisfy these with recorded commands and results. Authored policy substitution proves replaceability, not learned improvement.
- A corpus analysis and ranked next empirical question. Explain what existing evidence answers and what requires new observations. Give one proposed next experiment with controls, resource envelope, positive/negative/unsupported dispositions and an informative stopping condition.
- A sequenced next implementation plan with owned paths, data migration/recovery effects, integrated gates and deletion points. No new dependency or deployment stack without a concrete missing capability.

Finish stage 9's first consolidation package when these choices are concrete and the feasibility limits are exposed. Do not require a positive learning result or complete every future stage. The architectural reviewer can then assess a meaningful design and implementation plan rather than receive another list of local repairs.

## Task list

- [x] Inspect the delivered corpus and identify the construction interface mismatch.
- [x] Preserve the no-retention outcome and separate interface, transport and output-limit causes.
- [x] Define the stage 8 closeout and stage 9 consolidation scope.
- [ ] Worker: fix and qualify stage 8 contracts, then report corrected diagnostic outcomes.
- [ ] Worker: compare ownership alternatives and deliver the stage 9 architecture package with feasibility checks.
- [ ] Reviewer: evaluate the package and select the next implementation and empirical study.
