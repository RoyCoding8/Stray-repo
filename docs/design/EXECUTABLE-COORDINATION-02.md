# Executable coordination: learned procedures for organizing and checking work

Selected design and experiment, 2026-09-12, based on worker `5864740` and assessment `81d0d44`. This is COORDINATION-02, a new study with new freezes. It does not change the treatment or verdict of Team 01. Implementation is assigned by [the combined worker prompt](../../WORKER-EXECUTABLE-COORDINATION-02.md).

## 1. The architectural decision

Retain a **coordination procedure**: executable behavior that turns the current task, observations and unresolved obligations into a bounded proposal for what should happen next. A procedure can inspect structure, generate a diagnostic, partition ownership, choose independent alternatives, request selective rework or decline to act. The existing runtime admits the proposal and executes it. No model must reinterpret the retained procedure for its decisions to take effect.

The learned object is neither a fixed team roster nor necessarily a fixed graph. It is a generator of concrete plans and revisions, conditioned on evidence. The graph for one task is an execution product. The procedure that generates useful graphs across tasks is the reusable capability.

This joins three existing design ideas: executable capabilities, evidence-qualified applicability, and bounded compositions. Use one capability registry, one operation ledger and the existing continuation machinery. Do not build a new scheduler, memory database, graph language or agent framework.

The meaningful target is **experience changing future computation**. A useful memory might learn that a certain observable dependency requires a diagnostic before parallel edits, how to generate that diagnostic from new interfaces, and which work must be repeated after its result. Merely converting an instruction into JSON does not achieve this.

## 2. Concepts and their precise roles

| Concept | Meaning | What it does not establish |
|---|---|---|
| Experience | Versioned inputs, proposals, executed operations, actual artifacts, observations, failures and cost | A fluent account of what supposedly happened |
| Residual obligation | The part of the parent task that remains unsatisfied, with the evidence exposing it | Automatic blame of a worker or a calibrated confidence score |
| Coordination procedure | A program mapping materialized observations and durable state to an admissible next proposal | Authority to perform its own external effects |
| Binding | A map from the procedure's required roles/interfaces to the current source and observation references | Proof that similarly named interfaces have equivalent semantics |
| Applicability | Mechanical input eligibility plus a separately qualified hypothesis that this procedure helps here | A universal theorem inferred from passing a schema check |
| Diagnostic | A bounded attempt to distinguish plausible conditions before committing more work | A self-authored replacement for the independent task checker |
| Plan | Actual children, ownership, input references, checks and resource subdivisions for this task | A shape label attached after the work was already done |
| Join | The runtime's check that submitted artifacts satisfy the integrated parent obligation | A vote, a success count, or a program's own `passed=true` |
| Retention | Persisting exact procedure bytes, interface, dependencies and scoped experience for later invocation | Automatically promoting the procedure to the default |
| Consolidation | A development episode proposing a reusable procedure from a corpus, then testing it | An unbounded periodic reflection prompt |

The key distinction is between a statement, an instrument and a policy. “These edits may conflict” is a statement. A function that generates and runs an interface observation is an instrument. A procedure that uses that observation to allocate work is a policy. All can be retained, with different evidence obligations.

## 3. Formal interface and guarantees

Represent a retained procedure abstractly as `K = (P, I, D, H, E)`: executable bytes P; invocation/input contract I; pinned dependencies D; applicability hypotheses and limits H; supporting and opposing evidence references E. Reuse capability/artifact records for this representation.

At decision t, the controller materializes:

    X_t = (task_snapshot, public_contract, interface_bindings,
           accepted_plan, observations, residual_obligations,
           remaining_allocation, dependency_versions)
    P(X_t, m_t) -> (proposal_t, m_next)

`m_t` is bounded, untrusted procedure state. It contains no authoritative operation status or permission. Accepted runtime state remains authoritative. A restart reloads both the accepted execution state and the pinned procedure; it does not ask a model to remember its intentions.

The controller validates proposal structure, current versions, ownership, permitted inputs/effects, phase and resource capacity. It records the accepted transition before dispatching its effects. The next observation comes from identified operations and artifacts, not a field supplied by the procedure claiming those operations succeeded.

Conditional engineering obligations:

1. Every dispatched procedure-requested effect has an accepted proposal, current authority and recorded operation identity.
2. Every accepted plan binds the procedure invocation and input snapshot that selected it; submitted work binds the actual admitted child and revision.
3. A learned decision cannot remove the authoritative task checks, change protected answers, create authority, or mark its own output verified.
4. A change to relevant inputs, selected bytes or support eligibility requires revalidation before affected work; stale durable state is not permission to continue.
5. Restart consumes already recorded decisions and receipts. Uncertain external effects remain uncertain until reconciled; no blanket exactly-once claim.
6. A semantic claim about applicability remains empirical unless independently justified. Well-typed execution does not imply useful or correct reasoning.

These obligations are a design contract, not a completed formal proof or a claim of optimal intelligence.

## 4. Selected representation and execution profile

Use ordinary generated Python in an artifact package, invoked as `python <entry> <request.json> <response.json>` through the existing launcher/broker. Profile identifier: `coordination-procedure/1`. No generated module is imported into the trusted host. A package may contain bounded helper files; its entry and every dependency are digest-bound. A description may explain its behavior but is not required to execute it.

Select one semantic operation, `step`, rather than separate public methods for every phase. The request identifies the procedure, request/observation snapshot, phase, bounded state and available actions. The response echoes the binding identities and contains one proposal plus new bounded state. Concrete field names and module layout are worker engineering decisions, frozen before lanes implement against them.

The request is versioned and includes a unique decision identity, selected package digest, source/observation digest, expected plan revision and the controller's allowed-action set. The response must echo those identities exactly. Limit retained state to 16 KiB within the overall message limit. Parse the result strictly; unknown actions, extra effect-bearing fields and malformed state are errors, not hints to a model. The procedure may propose an observation-derived feature, but cannot place it in the controller's accepted-receipt fields.

| Proposal | Executed meaning | Required checks |
|---|---|---|
| `probe` | Request up to four bounded JSON invocations of declared public source interfaces; receive raw outputs/errors as attributed observations | Only currently bound interfaces and allowed snapshots; no hidden checker, arbitrary host command or network destination |
| `plan` | Supply a concrete `single`, `alternatives` or `decompose` team with actual ownership and input bindings | Existing team validators plus complete coverage of requested edits, valid source references, integrated public checks and finite allocation |
| `rework` | After a failed public join, name children to reattempt and the observation references motivating it | Same shape, at most one revision; fresh attempts for reworked or dependency-invalidated work; unaffected valid work may be carried |
| `stop` | End this policy's intervention, preserving its reason and any residual obligation | Cannot declare task success or discard unresolved effects |
| `unsupported` | Decline because required binding, supported scope or available action is missing | Record the gap; use the predeclared fallback if the remaining allocation permits |

For this profile, there is at most one probe batch, one initial plan and one rework round. A probe may precede the initial plan or follow a failed join; it cannot run concurrently with mutable child work on the same snapshot. Probe feedback feeds another `step` invocation. `rework` does not silently change team shape; existing `revise_team_plan` preserves that constraint. Arbitrary reorganization during execution is a later extension, not a claimed feature of this study.

Before any plan, allowed actions are probe, plan, unsupported or stop. After a pre-plan probe they are plan, unsupported or stop. A successful join ends policy intervention and proceeds through the independent freeze/grade path; a failed join permits the unused probe, rework or stop. After rework, the next join is terminal for this intervention. The controller derives the phase from accepted state, not the program's memory. Before a plan, unsupported/stop/invalid execution records the distinct reason and may enter the frozen S fallback using the same remaining allocation. After a plan, no automatic fresh S episode is started: preserve work, join failure and liability, and finish with the best artifact the existing checks actually accept. Budget exhaustion never grants a free fallback.

The program has meaningful freedom inside this interface. It can derive structural features, generate novel probe inputs, compute relations among observations, map many files into two ownership groups, select alternatives or stay single, and select rework from failure evidence. It is not limited to selecting an authored menu of complete procedures. Primitive actions are seeded; the decision computation is acquired.

A constant single-worker procedure is legal and may be efficient. If that is what acquisition produces, report policy compilation or simplification; do not pretend that diagnostic discovery, conditional coordination or a new algorithm was demonstrated.

The trusted source-invocation adapter exposes declared JSON-callable interfaces and actual outputs. Any relation the learned program infers from those outputs is its hypothesis. Public specifications remain available to every arm. Correctness is decided by independent checks after artifact freeze. The program cannot hide extra tool calls inside an unaccounted subprocess: each requested source invocation is a broker operation.

## 5. Binding, work allocation and context

Inputs contain source bytes, public requirements and interface declarations for the current snapshot. Mechanical binding checks path membership, ABI/version, allowed edits and reference freshness. When necessary semantics are absent or ambiguous, the procedure can probe or decline. The controller does not invent a field such as `safe_to_parallelize=true` from benchmark family membership.

Do not supply task-family labels, protected cases, reference patches or an authored optimal organization. Opaque bookkeeping identities may be echoed but cannot select behavior. Diagnostic variants include consistent renaming to expose identity lookup. Structural transfer also changes interfaces and dependencies; renaming alone is not a transfer claim.

All repair workers receive the same public root specification, bound source information and admitted observation contents allowed by their treatment. Different ownership and peer-answer exposure are explicit parts of organization. In the executable arm, the controller renders child instructions from the accepted plan; it does not append the learned source, lesson or arbitrary rationale to child prompts. A learned obligation refers to public contract items and source/evidence bindings, not a hidden solution payload.

Represent obligation text as a bounded explanation attached to structured references. In A/F/L, free-form policy explanations are stored for operator inspection, not forwarded to repair workers. The trusted renderer constructs child obligations from public contract IDs, permitted paths and admitted observation references. This prevents the explanation field becoming an unmeasured second solver channel: source patches, expected held-out answers and free-form retained lesson blocks are not accepted plan content. Domain-specific calculations belong in observed diagnostics or actual child work, with their provenance recorded.

Decomposition may group several modules per child; the host must not replace the program's partition with the current `_live_children` first-two-modules rule. Whole-task alternatives own complete independently checked candidates. All permitted edits must be owned or explicitly preserved. A file omitted from both ownership and preservation is not silently forgotten.

## 6. Concrete learning and use example

An experience corpus contains repairs to producers and consumers that each look plausible locally but disagree on interval boundaries. A development episode proposes a procedure that reads the new public interface declaration, binds the producer and consumer roles, generates endpoint inputs, observes the assembled behavior, and uses the observed mismatch to choose one owner for the coupled edits. When interfaces are already compatible and repairs are disjoint, the same procedure may allocate separate ownership groups.

On a new task, the endpoint values and interface bindings come from that task. The old answer is unavailable. If the interfaces instead operate on unordered sets and do not support the declared interval relation, binding/probing should expose the mismatch or the procedure should decline. A structurally plausible false applicability claim is allowed to fail in the experiment; it does not become trusted because the program emitted it.

After a failed join, the program may request rework of the consumer while preserving an unaffected producer. That is admissible only if the producer's relevant input/contract bindings remain valid. If the shared convention changes, preserving its old submission is unsafe; the controller invalidates dependent work. Runtime validation preserves identity and declared dependencies, while the experiment tests whether the learner declared useful dependencies at all.

This example specifies an opportunity and a rejecting control, not the answer the model must discover. The worker must not hand-code the interval strategy into the acquired package or label it model-generated.

## 7. Acquisition and evidence-qualified retention

Use the existing development lifecycle: observe actual experience, diagnose a coordination bottleneck, construct executable candidate bytes, check, compare on development tasks, freeze and retain an experimental selection or `none`. Construction requests include the complete file ABI, action semantics, examples of valid transport messages, actual development observations and the finite budget. A transport example must not contain a working coordination strategy for the task families.

Allow at most two candidate lineages, each with one initial construction and one repair attempt: four broker-routed construction calls total. Keep unusable and empty responses with their usage. A repair receives the concrete parse/execution failure, not protected feedback. A local developer must not fill an empty response with an authored method. Both lineages receive the same development access policy; the second may inspect the first's development results, with that exposure recorded.

Select using a fixed development validation set and a preregistered ordering: valid end-to-end execution first; then solved tasks; then lower total model tokens, then lower total sandbox operations, then shorter canonical package bytes. Any unsupported case still contributes its complete fallback outcome and overhead. Select `none` if neither candidate is executable under the required contract. This is selection for an experimental trial, not a release or proof of learning.

Freeze exact selected bytes, required dependencies, input contract, development exposure manifest, model/configuration, selector and baseline implementations before held-out use. The fixed program baseline is also frozen before inspecting the acquired package. No held-out feedback updates any of these during this study.

Memory retains both positive and negative observations. Demonstrated input incompatibility removes eligibility for that affected binding; an observed performance loss informs scoped evidence and the next development proposal. Do not globally quarantine a procedure merely for losing one task, and do not treat a natural-language objection as a mechanically proved violation. Existing quarantine/retirement commands remain the authority for blocking new uses.

## 8. Four-arm comparison

| Arm | Treatment | Question answered |
|---|---|---|
| S: strong single | One continuing repair worker with iterative edits, diagnostics and self-review; no acquired coordination package | Does the entire acquired coordination approach beat a competent simple default? |
| A: interpreted memory | A model receives the same selected package source and description as text, the same observation interface, and emits the same proposal contract | Is direct execution better than a capable model interpreting the same retained information? |
| F: fixed executable | A competent developer-authored conditional policy using public structure, probes and the same proposal interface | Is the learned computation better than a sensible seeded executable policy? |
| L: learned executable | The acquired package executes directly at each decision; repairs still use live model-generated bytes | Does learned executable coordination provide useful behavior and transfer? |

A is deliberately stronger than a vague lesson-only baseline. It can inspect the full retained algorithm, reason about applicability and request the same probes. Its model calls and repeated input cost are charged. L has no hidden planner-model call: its package requests bounded source observations and emits decisions. All repair model configuration, tool affordances, independent checks and total episode ceilings are shared. F must be a real conditional baseline, not a no-op designed to lose.

For F, begin with source dependency structure and explicit public interface declarations: keep localized/tightly coupled edits under one owner; partition genuinely disjoint declared ownership groups; use a bounded public diagnostic when its outcome can distinguish those cases; on a failed join rework the implicated group and declared dependents. The worker must implement and validate a concrete version on development controls, without using hidden defect counts, family IDs or learned-package contents. Where those facts cannot be established, stay single. It need not mimic the candidate's internals or consume its runtime budget doing useless work to make costs equal.

S may use diagnostics and iterative repair within its single-owner organization. It is not reduced to one prompt. Allocation saved by any policy is available within its remaining root allowance. Treatment-specific overhead is counted, not compensated with extra authority. The experiment measures complete policies; removing planner calls is a legitimate efficiency result, but it does not by itself establish a more intelligent coordination algorithm.

## 9. Workload, discrimination and freeze

Create six public workload families. For each, prepare two development tasks, two held-out evaluation tasks and one held-out transfer task: 12 development, 12 evaluation, six transfer. Use executable multi-file JSON transformations with independently checked outcomes. Preserve Team 01's bytes; new tasks and manifests live under a new study directory.

| Family | Pressure to expose | Required apparatus control |
|---|---|---|
| Separable multi-module work | Useful partitions may group four or more files into two obligations | A first-two-files shortcut misses required edits |
| Coupled semantics | Units, boundary conventions or producer/consumer contracts must agree | Locally plausible outputs fail the combined checker |
| Diagnostic information | A public observation distinguishes two plausible repair/organization choices | Changing the observed behavior changes the justified next choice; no hidden label supplies it |
| Single-owner advantage | A localized or tightly coupled change makes extra workers wasteful | A strong single solution fits the shared envelope |
| Rework dependencies | A failed join affects some work but can invalidate an apparently completed neighbor | Both genuinely reusable and actually stale submissions occur |
| Scope and misleading similarity | Familiar filenames conceal changed ABI/semantics; unfamiliar names preserve relevant structure | Explicit incompatibility/refusal and legitimate renamed use both exist |

Transfer variants change dependency topology, role-to-file mapping or interface semantics in addition to values/names. At least two transfer tasks combine pressures previously seen separately. Include public requirements sufficient to solve them. Protected concrete tests and reference implementations never enter learner/solver execution.

The protected evaluator reads a submitted immutable candidate after freeze and emits its score to the experiment record. It does not return protected feedback to the coordinator policy or repair workers. Store/mount boundaries and invocation payload tests must demonstrate this separation. An implementation coordinator knowing the fixture design is not itself empirical independence; report how the actual learner and solver processes are restricted to their permitted inputs.

The corpus reviewer must establish each stated pressure through authored controls before live acquisition. This is exposure validation, not proof that L will exploit it. Calibrate baseline feasibility and source/response limits on development only. If every policy solves everything, efficiency may still be tested, but quality discrimination is saturated. If the intended mechanism never activates, report it rather than retrospectively changing the panel.

Evaluation: 12 tasks x four arms x two repeats = 96 episodes. Transfer: six tasks x four arms x two repeats = 48 episodes, each starting with a fresh process and no development transcript. Counterbalance order by a frozen schedule, isolate mutable state, and report provider randomness limits. Pairs use `(freeze, panel, task, repeat, arm)` identities; a task ID alone is insufficient.

## 10. Mechanism probes and targeted interventions

The structural battery must exercise the following at the public integrated entry. Authored packages and doubles are appropriate for rejecting controls, explicitly labeled; they never count as model acquisition or live repair evidence.

| Gate | Required observation |
|---|---|
| EC-01 executable causation | Alter a policy branch or partition and observe different accepted child work/probe behavior; changing only ignored description text leaves direct execution unchanged |
| EC-02 actual bytes | Model response -> acquired package -> staged invocation -> accepted proposal -> real child operation -> submitted bytes -> checked result; disconnect and substitution controls fail visibly |
| EC-03 admission ordering | Refused plan dispatches no child inference or repair; accepted ownership/allocation precede those effects |
| EC-04 binding and eligibility | Renamed compatible input binds; incompatible/missing input declines; version change or quarantine blocks affected new use |
| EC-05 diagnostic sensitivity | With an identical pre-probe decision state, two real controlled source behaviors produce different observation bytes; replay each into the policy and record actual subsequent decisions |
| EC-06 integration and rework | Local-green/integrated-red cannot complete; selective rework mints fresh attempts; valid unaffected work survives; changed dependencies invalidate carried work |
| EC-07 continuity | Kill the coordinator after a recorded probe and separately after one accepted child; another process resumes the same DB, preserving a sentinel and settled operations |
| EC-08 bounded failure | Infinite/oversize/invalid policy, empty model reply, exhausted budget and cancelled work produce explicit outcomes and attributable liabilities, not authored fallback success |
| EC-09 evidence reconstruction | Offline checker detects deleted cells/pairs, cross-panel collisions, wrong procedure/input digests, altered receipts and unattributed cost; live reconciliation is a separate command |
| EC-10 genuine retention | Unseen use loads the pinned package in a fresh process without reconstruction, source substitution or a planner interpreting its text |

For EC-05, a program may legitimately take the same action for both observations. That is a measured inactive mechanism, not an apparatus failure if an authored positive control proves the path can carry a difference. Different live model outcomes alone do not prove causation. Deterministic recorded-input interventions locate sensitivity; live matched comparisons measure practical outcomes.

Freeze a diagnostic subpanel of six evaluation tasks before scoring. Run two interventions once per task, at most 12 additional live episodes: L with its optional probe request replaced by an explicit `probe_unavailable` observation, and L with selective rework replaced by reworking every child on join failure. All extra work remains capped; do not bypass joins or feed protected answers. Skip and label an intervention inactive if the selected program never exercises its target. These variants are diagnostics, excluded from candidate selection and the primary benefit rule.

## 11. Finite campaign and result rules

Maximum development episodes: 48, including baseline calibration, candidate validation, live mechanism probes and retries. A feasible allocation is 24 S/F calibration episodes, 12 candidate validations (six declared development tasks per candidate), six A validations, and six live controls/continuity probes. Unused slots are not an instruction to spend. Construction has the separate four-call ceiling from section 7. Main evaluation 96, transfer 48, optional interventions 12: at most 204 live episodes plus four construction calls. All require an available configured gateway and finite durable grant; the worker must preflight actual inference, not discovery alone.

Starting per-episode ceilings: 12 model calls, 128,000 aggregate input tokens, 48,000 aggregate output tokens, 20 visible source/public-tool invocations, 64 total sandbox operations, eight policy `step` invocations, two children, one probe batch of at most four source invocations, one rework round and 900 seconds elapsed. Reserve final checks and cleanup inside the root before admitting work. A policy invocation uses a finite launcher bound (initial target two seconds and 64 KiB request/response); declared source limits may require larger packets, resolved on development before freeze. Never silently truncate required context or responses.

Construction calls may use larger output limits needed to emit source, but each has a finite declaration under the campaign grant. The coordinator records an executable cap sheet before spending: per-call input/output, model/context compatibility, timeout, policy/source/check execution reservations and total grant. The numbers above are ceilings, not exact price quotes or permission to overdraw an existing grant. If the environment cannot support the study, commit the exact blocked command and remaining cells; do not replace it with a doubled “live” run.

Report these separately: primary correctness; model input/output tokens and calls; source/public-tool invocations; all sandbox operations including policy execution and protected checks; observed sandbox CPU/wall where available; elapsed episode/campaign time; abandoned work; unresolved liabilities; internal accounting; external billing knowledge. Unknown measurement is unknown, not zero. No composite reward hides a quality loss.

For a complete settled refusal/timeout, task success is zero and all cost remains included. Missing evidence or uncertain external state is a different status and prevents an unqualified complete-panel conclusion. Reconciliation is by operation-identity unions, including builds, validation, failed and cancelled attempts. Never infer whole-campaign totals from episode counters alone.

The frozen finite-panel promising rule compares L independently against S, A and F. Against each, L must either solve strictly more with model tokens, visible source/tool invocations and total sandbox operations each <=1.25x the comparator; or tie solved count with no increase in any of those resources and strictly fewer model tokens. No evaluation family may lose more than one solved episode; no transfer family may lose a solved episode. A zero denominator permits only zero numerator for that bound. Unknown mandatory totals make the comparison unevaluable. Report each comparator result and the complete raw vector even when the joint rule fails.

A **promising retained policy** satisfies the rule against all three on evaluation and transfer. This is a descriptive pilot invitation to a broader trial, never automatic release or LEARN-6 promotion. Acquisition costs are additional: report both marginal-use and cumulative observed results. Calculate break-even reuse only for actual positive per-use savings, component by component; do not invent a monetary value for correctness or forecast demand.

Do not launch all held-out panels if neither candidate is executable: freeze `none`, demonstrate explicit fallback and report no acquisition. A legal but weak or constant candidate may proceed; learning failure is informative. Stop and invalidate affected measurements for a real apparatus error, preserve the old freeze and rerun the smallest complete affected comparison under a new freeze. Do not keep altering candidates or panels until a gain appears.

## 12. Engineering seams and deliberate scope

| Existing code | Reuse and required adjustment |
|---|---|
| `src/settlement/run.py` | Existing invoke/choice/sequence/parallel/join/continuation semantics; no second generic graph interpreter |
| `src/settlement/team.py` | Actual plan validation, owned children, revisions, submissions and joins; accept the selected partition, not an experiment-side replacement |
| `src/settlement/broker.py`, `store.py` | Admission, durable operations, reservations, receipts and recovery; authoritative operation state lives here |
| `capabilities.py`, `artifacts.py`, `development.py` | Publish/check/pin the acquired bytes, dependencies, experiment selection and disposition; reuse rather than duplicate the registry |
| `context.py`, `evidence.py` | Materialized decision inputs, opposition and current eligibility; distinguish semantic hypotheses from machine-checkable prerequisites |
| `representation.py` | Reuse file-invocation and durable-step patterns where genuinely shared; do not force coordination into the reduction-specific encode/decode profile |
| `experiments/team01/solver.py` | Reuse actual repair, tool and join behavior; separate policy selection from child execution so admission happens first; preserve historical evidence semantics |

The current solver constructs child repairs before calling `propose_team_plan`. COORDINATION-02 must reverse that causal order on the new path: evaluate policy -> validate/admit concrete plan -> construct under admitted child ownership -> submit -> join. A post-hoc graph with model-call IDs attached is insufficient. Establish one shared execution path for the new A/F/L policies; do not clone the entire solver for each arm. Historical entry points may remain compatibility wrappers without changing old as-run evidence.

Concrete schemas, helpers, migration needs and concurrency implementation are open engineering choices. The nonnegotiable parts are the semantics above and the observable evidence. Use the current technology stack; real containment, deployment and PG18 qualification remain separate unless this environment already supplies them. An explicitly authorized uncontained disposable execution profile is not evidence of containment.

## 13. Architecture beyond this study

The same conceptual cycle can later acquire a scientific measurement procedure, mathematical counterexample search or context-selection policy: experience identifies an unresolved distinction; development proposes computation; admitted execution produces evidence; later use tests scope and value. This study implements only coordination, not one universal profile for all cognition.

Background development should consume concrete evidence batches, such as recurring integration failures or repeated expensive planning. The agenda admits a finite consolidation episode; it does not call a model forever on a timer. A successful procedure can later be used as a dependency in another capability, with composition compatibility and use evidence. Multi-generation library growth and revision of the learner itself are subsequent experiments, not inferred from one retained package.

| Outcome | What the next design turn should do |
|---|---|
| L beats A but not F | Treat execution/compilation as useful; improve acquisition or retain the simpler authored policy; do not claim novel coordination |
| L beats S/A/F and transfers | Investigate scoped routing, multi-generation reuse and acquisition break-even before broader promotion |
| L changes decisions but loses quality | Study applicability, diagnostic validity and error propagation from the observed traces |
| L is correct but costs more | Identify whether probing, partitioning, repeated policy execution or rework is the expense; simplify the measured bottleneck |
| No nontrivial mechanism activates | The acquired object is simple or the distribution uninformative; retain that result and redesign exposure before scaling |
| In-scope succeeds but scope-shift fails | Improve bindings, explicit assumptions and refusal/routing; more workers do not fix applicability |
| Construction fails or freezes none | The next learner intervention is executable-construction reliability, not a claim that executable memory failed to help |
| All arms saturate correctness | Restrict conclusions to cost/mechanism; test a more discriminating workload in a later independent freeze |

Return evidence against every row that applies. The purpose is an informative architectural decision, not another undifferentiated PASS.

## 14. Alternatives and research grounding

The source checks below were made on 2026-09-12 at abstract level. They establish adjacent ideas; this is not an exhaustive novelty study, a replication, or evidence that our combination works.

- [Voyager](https://arxiv.org/abs/2305.16291) explicitly retains executable skills and uses black-box model calls without parameter fine-tuning. Executable memory itself is therefore not a novelty claim. Our question here concerns checked coordination decisions, scope and durable operation semantics.
- [DreamCoder](https://arxiv.org/abs/2006.08381) grows symbolic abstractions and a program-search language, coupled with neural training. It motivates asking whether experience yields reusable computation rather than only another solution. We are not implementing its learning algorithm or claiming its results without training.
- [Automated Design of Agentic Systems](https://arxiv.org/abs/2408.08435) describes a meta-agent programming new agents using an archive of earlier discoveries. Broad agent-code search is a serious alternative. We select a smaller effect interface to make the causal connection to existing authority, evidence and recovery explicit, while allowing arbitrary bounded decision computation inside the package.

We considered three representations. A fixed parameterized graph is easy to inspect but puts complex binding/diagnostic logic elsewhere. An unconstrained self-editing agent process offers freedom but makes authority, evaluation and causal attribution harder to separate. A generated decision program with validated proposals reuses the existing runtime and keeps computation open-ended within an explicit effect contract. This is the selected engineering tradeoff, not a claim to the best possible architecture in all environments.
