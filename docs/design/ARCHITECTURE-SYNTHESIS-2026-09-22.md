# Architecture synthesis: persistent investigations that improve their learning procedure

Status: selected next design, subject to explicit experimental reversal conditions. Design owner: Codex. Source baseline: `7e87d739344d30e3304bd6d96d38c955abcc4bce`. This packet completes the present design pass; it does not claim that the target architecture is implemented or empirically superior.

Read [research and its limits](RSI-RESEARCH-2026-09-22.md), then the [worker assignment](../../WORKER-INVESTIGATION-LEARNING-02.md). Historical experiments retain their original contracts and evidence.

## 1. Purpose and the architectural decision

Build infrastructure for a persistent system that pursues useful objectives, notices limits, chooses experiments, acquires executable competence and improves the procedure that performs those activities. SWE, mathematics and scientific investigation are domains through which to test this ability. None defines the whole product.

Select **persistent investigations with versioned executable operational and improvement behavior, over a small trusted execution runtime**. An agent invocation is temporary computation. The durable unit is the investigation and the behavior it can inherit. A swarm is an allocation option, not the owner of knowledge or the mandatory shape of thought.

The current implementation provides much of the execution machinery. The next architecture changes who owns the learning decisions and how their usefulness is evaluated. It must not merely add another coordinator around the existing study scripts.

Foundation-model weights remain fixed in this phase. Code, procedures, context selection, operational hypotheses, archive selection and research allocation can change. Learning means an experience-dependent persistent change that affects subsequent behavior. Recursive improvement is a narrower claim: an inherited change to the improvement procedure improves the successors that it subsequently produces. Neither follows from self-editability alone.

## 2. Evidence inventory and corrections to our interpretation

This pass traced source and the committed live bundle. The previous reviewer turn independently reran the offline verifier and reproduced its seven failures. The worker's full focused test gate was not rerun during this design pass. No new discovery-model calls or runtime changes were made; Jev calls are design review only.

The acquisition review changes one interpretation of the archived evidence. E0 proves that live model bytes reached retention only. It does not prove model acquisition, binding, inheritance, or utility. The final integrity implementation now requires a durable original dispatch record, linked finalization, exact package provenance, mandatory child receipt, and study-bound E3 evidence. The archived fixed-menu strategy is authored and control-derived, even though its package report uses `origin: "acquired"`. The output-shape preflight failed closed on exact route discovery before inference. Preserve the evidence and do not retry that study directory.

| Area | What exists at the baseline | What it does not establish | Disposition |
|---|---|---|---|
| Effects, authority and recovery | `src/settlement/broker.py`: operation preparation, dispatch, receipts, reconciliation; durable store and child execution | Universal containment, failure-free recovery or fully attributable live exports | Keep the guarantees and reuse the implementation; fix attributable-outcome gaps |
| Retained methods | `trajectory._use_retained_method`, frozen repertoire and subsequent-use path | Broadly useful live capability acquisition | Keep; expose through the common action executor |
| Executable policy | `policy_step`, `DecisionConsumer`, persistent STEP continuation | A good policy or a self-improving improvement procedure | Keep the ABI shape and byte identity; extend purpose and assessment |
| Revision lifecycle | `trajectory._construct_policy_revision` calls construction, freeze, assessment and binding; `_activate_bound_policy` installs a selected policy | Effective recursive improvement; shared semantics for all policy actions; a retained candidate is not bound merely because it was stored | Keep lifecycle and provenance, replace the narrow assessment boundary |
| Agenda | `run_campaign` enumerates supplied task IDs; `select_tasks` uses supplied or fixed defaults | System ownership of the task stream or learning agenda | Replace runtime dependence on the study schedule with durable admissible work |
| Policy assessment | `policy_assess._run_arm` executes STEP and measures method effects | Full learning behavior: its separate `_effect` refuses `request_model` and `propose_revision`, and initializes private state for each task | Retain as a restricted historical profile; do not use it to certify a general improver |
| Experience and context | Observations, evidence references and selected context exist in the current and earlier prototypes | One coherent memory lifecycle across every prototype, calibrated beliefs or useful learned retrieval | Consolidate only the path consumed by investigations; test utility |
| Live study | P0 has 8/8 preserved uses; P1/P2 unavailable; exact route preflight failed before model dispatch | A complete comparison, a learning null or an isolated diagnosis of model incapability; the output-shape study remains unrun | Preserve bytes and preflight failure; classify the study as incomplete |
| Generality | Software and graph panels | Broad domain transfer: both current panels primarily test reduction behavior | Keep as regression instruments; add a different experimental task structure |

Two earlier interpretations need correction. First, the live failure cannot yet be attributed solely to the free model. Transport, decoding, construction and accounting are confounded. Second, every dispatch must be attributable, but a timeout cannot truthfully produce a settled provider receipt. The proper requirement is durable attempt identity, available response/failure evidence and explicit unresolved liability. Reconciliation must not invent a result or mark unknown cost as zero.

The independently reproduced guard defect is separate: `StudyGatewayGuard.infer` returns `GatewayError` before inspecting captured cost. A post-response check can stop later calls but cannot prevent a charge already incurred. Future reports must distinguish a configured free route, measured per-response cost and unresolved billing.

## 3. Alternatives considered

| Alternative | Strength | Limitation for this goal | Decision |
|---|---|---|---|
| A. Fixed host learning loop with separately learned component policies | Small migration, easy local ablations, predictable execution | The host still chooses the research sequence; useful interactions can be constrained by fixed component boundaries | Keep as the strong baseline and fallback |
| B. Persistent investigations and an executable program that can revise its own improvement behavior | Makes agenda, experiment choice and future construction decisions inheritable; permits whole-program changes without rewriting trusted effects | Harder assessment and state compatibility; usefulness is an empirical question | **Selected** |
| C. Whole-repository agent populations with independent runtimes and evolving judges | Broadest editable implementation space | Multiplies runtime/evaluator confounds and maintenance before we have evidence those restrictions are the bottleneck | Defer; preserve the ability to propose broader changes later |

B does not require separate services for each cognitive concept. Start with one package and one driver. Operational and improvement modes describe what a program is being asked to accomplish; they can share code and state. The external acceptance mechanism remains separate.

Reverse B toward A if matched prospective studies show no useful changes to improvement behavior, if most gains come from a fixed context/method library, or if the additional search consumes more resources than it saves. Consider C only after a useful policy repeatedly encounters an expressive restriction that cannot be removed within the shared action interface. Large changes are allowed; each needs a causal reason.

## 4. Precise model

Let the system state at a decision boundary be:

`S = (G, I, E, C, A, V, P, B)`.

- `G`: externally supplied mission, constraints and success criteria.
- `I`: investigations with objectives, open questions, candidate explanations, next options and dependencies.
- `E`: attributable observations and attempted effects, including missing and disputed outcomes.
- `C`: revisable claims with support, opposition, scope and invalidation conditions.
- `A`: artifact archive, including active defaults, scoped specialists and experimental alternatives.
- `V`: active program versions and program-private state by investigation.
- `P`: accepted but unfinished actions, pinned to the program and input that proposed them.
- `B`: resource authority, actual usage and unresolved exposure.

This is a semantic decomposition, not eight new database tables or services. Most can be projections of existing records. `S` is not claimed to be a sufficient Markov state of the external world.

A versioned context builder produces a permitted view `v = Ctx(S, purpose, allowance)`. A frozen executable program computes `(a, z_next) = STEP(v, z)` in a bounded child. The runtime validates the request, reserves authority, persists its identity and proposed private-state transition, performs the effect, and incorporates the resulting event exactly once into the investigation projection. “Exactly once” refers to local incorporation; arbitrary external effects still need idempotency or explicit unknown outcomes.

On rejection, the policy receives a typed refusal. On an uncertain external result, the policy receives an unresolved outcome. Neither silently becomes a successful action or free budget. State from an accepted STEP and the corresponding pending action must survive a restart together.

An improvement program receives a target artifact or program, permitted experience and an improvement budget. Its output is a candidate plus evidence of the process that produced it. The same executable package can determine how to acquire experience, invoke constructors, test alternatives and stop. A revision can change this improvement behavior as well as operational behavior. A fixed host call to an unchanging constructor prompt is a useful baseline, not sufficient evidence of that recursion.

Concretely, retain one STEP calling convention. Its permitted view names a purpose, `operate` or `improve`, the target artifact digest, accessible experience, remaining authority and available instruments. Improvement mode can read its own frozen source through the artifact reader, choose evidence and parents, choose constructor inputs, request checks, and submit candidate bytes. A model constructor is a leaf effect, not a host-owned sequence of research choices. Candidate manifests identify the source digest that implements both purposes. The host selects the externally requested purpose and enforces bounds; the program selects the improvement procedure. Version changes cannot alter that purpose or expand authority. An authored control remains authored even when the host selects it. An acquired treatment requires independent model-response provenance, checks, and the durable binding path.

For a task distribution `D`, let `Q_D(x)` be externally measured task utility of configuration `x`. For an improver `m`, a starting configuration `x`, permitted history `E` and total budget `b`, define:

`Y_D(m | x, E, b) = Q_D(Select(Improve_m(x, E, b))) - Q_D(x)`.

`Select` uses the declared development/qualification protocol; a separate untouched audit estimates the displayed utility. Include the unchanged starting configuration when there is no eligible successor. A meta-improvement claim compares `Y_D(m_new | x, E, b)` with `Y_D(m_old | x, E, b)` using matched starting conditions, then reports the distribution of differences. Better task code alone does not identify a better improver.

Represent resources as a vector: model dispatches, input/output tokens, tool queries, child computation/time, billed units, unresolved exposure and human interventions. Do not collapse unknown values to zero. Do not divide by a baseline's zero token count. A frozen rule may compare quality under common resource ceilings or cost at an agreed quality floor. Cross-domain utility aggregation needs declared normalization and per-domain reporting.

### What the formal model can and cannot establish

Conditional invariants are reviewable: no admitted effect exceeds its authority; every incorporated result points to its actual operation; a bound program matches assessed bytes and scope; future decisions inherit the bound version; assessment secrets do not enter development views. These require correct implementations and explicit failure assumptions.

The model gives no guarantee of monotone competence, discovery, calibrated uncertainty, optimal allocation or limitless improvement. A confidence estimate from a model is not such a guarantee. Those properties require evidence and may fail even when every invariant holds.

## 5. One execution meaning in development, assessment and use

All profiles invoke the same action dispatcher and domain instruments. Profiles change permissions, data visibility, quotas and persistence destinations. They must not quietly change what an action means.

| Request | Runtime meaning | Assessment treatment |
|---|---|---|
| Read evidence or request context | Materialize authorized records and byte-bound artifacts under an input budget | Same reader, restricted to the assessment session's permitted history |
| Probe an environment | Invoke a declared instrument with bounded inputs and observation access | Same instrument, independent environment instance and query accounting |
| Request a model | Broker-routed inference with operation identity, bounded output and failure accounting | Available when the assessed program requires it; otherwise the profile is explicitly restricted and cannot qualify that behavior |
| Construct or repair an artifact | Run the program-selected construction attempt; validate resulting source and ABI | Same constructor and validator, on assessment-local candidate artifacts |
| Use a retained method | Resolve actual eligible bytes, invoke the child and record the selected identity | Same resolver and child; only the frozen allowed repertoire is visible |
| Propose an investigation | Add a mission-related, executable option to the investigation frontier | Assessment-local frontier; no change to the protected challenge set |
| Propose a program revision | Create an immutable candidate version with lineage and purpose | May stage a revision locally; cannot promote into production or recursively launch unbudgeted qualification |
| Request assessment or adoption | Submit a frozen candidate to the trusted qualification procedure | Candidate cannot read protected labels or change the gate; final audit never launches nested promotion |
| Wait, stop or allocate work | Yield to an event, end the investigation, or request finite child work | Same semantics; all descendant resources count toward the parent allocation |

Map these meanings onto the existing action vocabulary first. Add an action only when an existing action cannot represent the effect honestly. Do not create a second interpreter in the evaluator. The integration test supplies the same program and permitted observations to both profiles and verifies matching admitted effects up to the explicitly declared differences.

The learning session and its private audit are distinct. A policy may receive operational feedback from its own legal probes and constructions while a separate scorer holds final answers. “Sealed” does not mean disabling the model or all useful environment interaction. It means the learning program cannot inspect the private answers, selection bookkeeping or future challenge outcomes.

## 6. Agenda and memory

### Agenda

An opportunity contains a mission link, a question, supporting observation references or an explicit initial unknown, a proposed intervention, alternatives it could distinguish, an expected useful consequence, and a finite resource request. Syntax establishes admissibility, not usefulness.

The seed selector first handles accepted work and required recovery, then urgent user commitments, then eligible learning opportunities. Start with a simple recorded ordering over expected task benefit, information relevant to a pending choice, cost and uncertainty. Do not pretend those estimates are calibrated. Keep an authorized exploration slice so an unsupported idea can be tested rather than permanently excluded. Policy revisions may change this ordering within mission and resource constraints.

The system may derive a new investigation from a contradiction, a failure of a retained method, an expensive repeated behavior, disagreement between procedures, or a user objective. It may also perform routine work without inventing a scientific hypothesis. New goals must be executable through admitted instruments; arbitrary goal text is not an effect.

Operational scheduling is event-driven: new request, completed effect, changed support, explicit deadline or authorized idle allocation. A periodic wake checks readiness and recovery. It does not unconditionally inject the entire memory into a model. With no admissible useful work or no authority, the system waits.

### Memory and context

Reuse the earlier separation of experience, claims, capabilities and working state in [Memory and context](MEMORY-AND-CONTEXT.md). Preserve observations; revise interpretations. A claim may be contested or unsupported without erasing the observation that motivated it.

The dependency relation records what a decision relied on. It enables invalidation and targeted rereading; it is not automatically a learned causal model. When a source changes, dependent claims or releases become stale according to their declared contract. The context builder delivers the required contract, current commitments, relevant evidence and counterevidence, then optional history within a token allowance. Missing required information becomes a request or an explicit uncertainty.

Compression and summaries are derived artifacts with source references. An executable method is retained by its bytes, invocation contract, applicability and evidence of actual use, rather than by a narrative saying that it was learned. Ordinary prose remains useful as content and explanation; the architecture does not depend on a special file extension.

### Retention and forgetting

Keep active defaults, qualified scoped specialists, experimental alternatives and failed attempts distinct. The experimental archive permits bounded use in an isolated study, not unrestricted deployment. Preserve the baseline and the dependencies of active artifacts. Archive other variants by demonstrated utility, complementary applicability or an explicit experimental reason, subject to a quota. Delete redundant derived material before unique evidence needed for a claim. More retained variants are not inherently better.

## 7. Dreaming, support and the next useful experiment

Use three explicit evidence classes:

1. **Recorded replay:** reveal an outcome for a matching prior action with compatible input, state, instrument, environment and relevant versions. A mismatch returns unsupported.
2. **Prediction:** a heuristic or learned model proposes what might happen. Record its model/version and uncertainty; it is not an observation.
3. **New execution:** perform the admitted intervention and acquire new evidence.

A replay support report states which decisions had compatible recorded outcomes, which exhausted a recorded branch and which requested unseen interventions. Candidate scores with different support cannot be compared as if they covered the same world. On a shared supported prefix, policies may be screened cheaply. Their disagreement beyond that prefix can supply a proposed live experiment.

The first learned allocation hypothesis is specific: **choose new experiments where plausible procedures recommend different consequential actions and existing observations do not decide between them**. Disagreement is a search signal; expected usefulness and resource constraints still matter. Compare it with fixed round-robin allocation and ordinary uncertainty-based selection. Do not add a general simulator until prediction quality and downstream value justify it.

Dreaming itself costs model calls or computation. Its value is prospective: did it reduce the real work needed to obtain useful capabilities? A favorable replay score alone does not answer that question.

## 8. Inheritance, adaptation and teams

Bind a program version at an investigation decision boundary. Accepted pending effects remain pinned to their old version and complete or reconcile there. Never reinterpret an accepted action using newly installed code.

For the first implementation, activation requires a quiescent boundary and resets program-private state. Durable observations, claims, mission, capabilities and unfinished obligations remain intact and become the new program's explicit view. Arbitrary private-state migration is deferred. A later migration function would require a versioned source/target schema and its own qualification; it cannot rewrite observation history or authority.

The program manifest names the operational and improvement entry behavior. When a revision to improvement behavior is adopted, a subsequent investigation must invoke those exact bytes to generate or select another candidate. Trace this inheritance after process replacement. A marker or a parent digest without an invoked descendant-producing path is insufficient.

Parallelism is bounded work allocation. Independent branches receive their own work identity, snapshot, state and resource share. They return observations and artifacts for the durable investigation to incorporate. They do not share a mutable prompt or writable checkout. Parallel sampling, specialist methods and adversarial checks remain available, but serial execution is a valid baseline. No team benefit is assumed from agent count.

## 9. Representation and technology decisions

Retain Python executable artifacts with a bounded STEP-style request boundary, existing PostgreSQL records, content digests, durable operation identity and the current gateway/execution adapters. Domain-specific executable methods remain ordinary artifacts. Do not introduce a new DSL, vector database, graph database, message platform, distributed service architecture or training pipeline for this batch.

Investigations and their dependency edges need ordinary indexed records. A graph is a logical view; graph storage is not a requirement. Store large immutable source/evidence objects using the existing artifact path. Use current version and epoch invalidation facilities wherever they implement the selected contracts.

Separate trusted runtime, reusable investigation logic and experiment definitions in code ownership. Move or extract current functions only as needed to remove duplicate behavior and fixed-panel dependencies. Old frozen experiments may retain a clearly labeled legacy profile. They must not become runtime defaults for the new design.

Technology choices remain provisional. Change a tool when a measured limitation blocks the selected behavior, not because a more ambitious architecture sounds as though it needs a larger stack.

## 10. Experiments that can change the decision

### E0: interpret the current live failure and correct its disposition

Trace the seven empty exported receipt sets through source operations, attempted dispatch, raw or hashed provider response, decoder disposition, receipt admission and outstanding reservation. Classify each as never sent, observed failure, lost/unknown response, receipt-admission failure, or export omission. Preserve old evidence. Add a reconciliation supplement rather than rewriting it. Resolve cost-guard error paths and restart accounting before further inference.

The archived E0 run is a retention observation. It proves that live model bytes reached retention only. It does not prove model acquisition, binding, inheritance, or utility. The run's `revision.disposition: "bound"` is a worker projection of `retained`, not evidence of a durable active package. The reported bound digest differs from the durable active digest, and the resumed round used the existing active package. Correct that projection in the source before treating any later E0 result as a binding or inheritance result.

Then perform one bounded construction preflight with the actual chosen provider: response bytes must reach parsing, ABI validation, executable behavior and the log. A basic known-good independently authored policy is the apparatus control; it never enters an acquired treatment arm. Do not infer model inability from an unobserved response. This preflight is not E3 eligibility.

### E1: autonomous investigation and actual learning behavior

Use two different task structures: existing software reduction and **finite Boolean-rule discovery**. In the latter, a hidden four-input/four-output deterministic rule is exposed only through bounded input experiments. The system chooses inputs, observes outputs and constructs an executable predictor. A private scorer evaluates all sixteen input states and reports queried/unqueried subsets separately. An eight-query ceiling prevents full table enumeration. Independently authored generators create development, qualification and audit rule instances; identical truth tables cannot straddle splits.

This is a small scientific-inference environment with exact assessment, not a claim of general science or an unlimited world model. Its purpose is to require experiment selection and prediction rather than another reduction algorithm. The old graph panel remains a regression control.

For the first instrument, each output bit belongs to a public hypothesis class: an affine Boolean expression over the four inputs, optionally XORed with one pairwise input product. Deduplicate the resulting functions by their sixteen-bit truth tables. The hidden target selects four such functions. The competent authored control maintains the surviving hypotheses after each query, chooses an input that reduces disagreement and predicts from that version space. Publish the hypothesis class and query interface equally to all arms; keep target identity and unqueried outputs private. This makes useful inference possible without claiming arbitrary truth tables are learnable from eight observations. Freeze task seeds and preflight baseline difficulty on development instances before touching qualification or audit instances.

Give the system a mission and a bounded choice of instruments and problem instances, not the next task ID sequence. It chooses an investigation, collects evidence, constructs or reuses behavior, encounters a controlled mismatch, then chooses whether to revise, switch method, investigate further or stop. The mission, environment grammar, grants and judge remain human-supplied. This demonstrates agenda control inside a declared environment, not unrestricted goal discovery.

Require at least one independently authored behavior-control trajectory that proves every essential transition. Live generated behavior is reported separately. If live construction fails, report unavailability and its stage; do not use the control to claim live acquisition.

### E2: does experience improve the learned procedure?

P0 is a competent fixed learner with ordinary retrieval and the same tools. P1 constructs an executable program from interface/mission information without the development history. P2 receives the same information plus the permitted history. P1/P2 have equal reserved candidate/repair allocations, model configuration and construction interfaces. Their history difference is the declared treatment. Task and arm order cannot consume another arm's reserved allocation.

Freeze candidate bytes, model/configuration, instruments, task splits, resource ceilings, use environment and comparison rule before qualification. Compare through the shared executor. Charge development and construction separately and report total/amortized cost at a declared number of future uses. Include failed attempts. Missing candidates produce unavailable arms; complete comparable outcomes may produce a null. A mechanism check and a statistical effectiveness claim have separate verdicts.

Use paired task instances and repeated model seeds when affordable. A tiny pilot reports individual outcomes and uncertainty; it does not manufacture statistical significance. For a larger benefit claim, specify sample size and practical effect threshold before the audit. Reused qualification results are adaptive feedback and cannot also be advertised as an untouched audit.

The trusted study coordinator owns split assignment and exposure records. Development results may influence programs. Qualification results may select among frozen candidates and are therefore adaptive evidence. The final audit runs only after that selection and cannot change the reported winner. Reusing its results for a later revision retires that audit from future untouched claims. Environment probe outputs available during an audit task are legal operational observations; private target identities, unqueried outputs and final scoring results are not available to the program before its prediction is committed.

### E3: did the improver improve?

E3 is unavailable unless a genuinely eligible model revision exists. Eligibility is conjunctive. The revision must have all of the following evidence:

1. **Model-response provenance.** The executable bytes trace to the exact model response through the response digest, construction record, validation, and package manifest. An authored fixed-menu source or a system-selected authored strategy is not model provenance.
2. **Exact-digest binding.** The candidate package digest and executable digest are bound to the same revision, and the durable active package digest equals that candidate digest. A retained package, a label such as `origin: "acquired"`, or a digest mismatch is insufficient.
3. **Durable post-restart child citation.** After process replacement, an independently checked child invocation cites the same bound executable digest in durable evidence. A parent digest, an active marker, or a resume that only loads the package is insufficient.
4. **Usable result.** The candidate produces a valid, executable result under the declared parsing, ABI, behavior, and assessment protocol. Retention without a usable result does not qualify.

Retained-only, digest-mismatched, and authored or control-derived bytes are ineligible. A no-op candidate can be rejected honestly. Do not force a bind to satisfy the study. E3 remains unavailable until the four conditions are all evidenced.

From an accepted eligible development revision, extract the inherited improvement program. Compare old and revised improvers from the same starting solver, archive, permitted history, model and total resources on new problem instances. Freeze the improvers during this comparison. Score the successors they generate on private tasks. Separately demonstrate a second revision round under the inherited program to establish structural recursion.

If there is no eligible revised improver, do not run empty panels. Report the missing condition and end the bounded study with a causal diagnosis. If both work but successor gains tie, report a meta-improvement null. A positive result establishes only the tested horizon and distributions.

Before a live claim, use two independent authored controls with identical operational behavior and different improvement behavior. From the same target and observations they must produce a known difference in a probe, constructor request or candidate choice, attributable to the improvement entry. Adopt one, restart, and observe that difference in the next descendant-producing round. This identifies the channel without claiming either control was learned or is generally better. The live comparison then follows acquired bytes through that same channel.

### Targeted ablations, not an enormous factorial study

After the core comparison runs, choose an ablation from the dominant observed mechanism: same history with simple retrieval for context, fixed task ordering for agenda, or no replay screening for dreaming. Preserve all other inputs and resource conditions. Expand to an archive ablation only after retained alternatives are actually used. This sequence gets informative evidence without simultaneously changing every cognitive component.

## 11. Completion, non-goals and ownership

The design role owns this conceptual model, alternatives, formal contracts, mechanism choices, evidence limits and study logic. The worker owns detailed module edits, storage mapping, executable checks, migration, bounded runs and delivery. It may challenge this design with a concrete counterexample; it may not quietly resolve a semantic ambiguity by weakening the experiment.

The final implementation gate at `9e6c922` completed the evidence boundary. The authorized output-shape preflight performed `GET /models` only and failed closed before any model dispatch. The P1/P2 study remains unrun. A route-specific preflight failure is an unavailable result, not evidence of model inability or a learning null. The same study directory cannot be retried. No positive learning result is required to claim implementation completion. No negative or unavailable result is permission to claim effective RSI.

Stage 9A-9D design is complete in this packet. Stage 9E execution and Stage 10 general integration remain open. Operational deployment qualification and release are later milestones. There is no requirement to rewrite functioning prototype code as a ritual final implementation.

Three ranked uncertainties remain: whether the model can propose useful executable improvement behavior under the interface and budget; whether the new behavior transfers beyond the experience used to create it; whether autonomous experiment selection improves usefulness per resource relative to the competent fixed learner. These are the reasons to run the next batch.

## 12. Review trail

The initial [Jev request](../../reports/jev/s09-synthesis-plan-request.json) and [response](../../reports/jev/s09-synthesis-plan-response.json) supported alternative B and identified common action semantics as the largest missing contract, with private-state activation next. Sections 5 and 8 resolve those contracts explicitly. Jev is a typed second opinion, not independent proof or authority to spend. The final challenge and disposition are recorded in the synthesis worklist.
