# Temporary teams and collective reasoning

Stage 8.6 design refinement; no adaptive-team implementation or benefit claim. This specifies the cognitive policy above existing bounded composition, delegation, evidence and commitment machinery. The current engineering worker's use of parallel implementation specialists is a development workflow; it is not evidence that the autonomous runtime has learned team formation.

## 1. Selected organizing principle

Form a team around **separable obligations or distinct information needs**, then dissolve it when those obligations are resolved or its allocation ends. A permanent set of expert personalities is not required. What persists is the work, artifacts, evidence, composition and knowledge of when that organization helped.

Select a bounded work graph with explicit joins as the first representation. Nodes name subquestions or artifacts, input conditions, ownership, allowed effects and caps. Edges specify information or completion dependencies. A join states what evidence satisfies the parent obligation. Use the existing composition and investigation mechanisms; this is not a second scheduler or a universal graph for all knowledge.

The policy may choose one worker, parallel alternatives, complementary work, a challenger or a sequential handoff. It can revise that plan inside its remaining authority. More participants require a task-relevant reason and a feasible join, not the claim that a swarm is inherently smarter.

## 2. When another worker might help

| Situation | Candidate organization | Question that could reject it |
|---|---|---|
| Distinct artifacts can be produced from stable shared inputs | Parallel decomposition with a declared compatibility check | Does integration consume the saved time or invalidate the parts? |
| Several plausible methods need independent exploration | Separate attempts followed by source-grounded selection | Are they producing the same errors at higher cost than serial alternatives? |
| A specific claim needs falsification | A challenger seeks a counterexample or missing assumption | Does the challenge produce inspectable evidence, or merely different prose? |
| Separate instruments or data access can resolve uncertainty | Complementary acquisition followed by an evidence join | Is there actual new information, and do permissions allow its combination? |
| Actions depend tightly on the latest shared state | One owner or a sequential handoff | Can parallel work do anything useful without stale-state errors? |
| No credible decomposition or information advantage is known | Strong single-worker reference; optionally a bounded team experiment | Does an exploratory comparison establish a reason to change the default? |

A seed team-selection policy uses observable constraints: dependency structure, artifact ownership, access requirements, previous measured coordination costs and unresolved evidence needs. Model judgments about decomposability remain hypotheses. Do not turn subjective diversity or confidence ratings into a calibrated expected-value score.

Research reports task-dependent coordination benefits and losses; that motivates these comparisons rather than a universal worker-count threshold. See [the primary study](https://arxiv.org/html/2512.08296v1) and its limitations summarized in [research notes](COGNITIVE-RESEARCH-NOTES.md). Settlement's own workload must determine which organizations earn retention.

## 3. Work and message semantics

A proposed team plan contains:

    (parent_investigation, plan_revision, obligations, node_dependencies,
     participant_compositions, input_contracts, access_partitions,
     artifact_ownership, joins, resource_partition, stop_conditions)

The plan proposes authority subdivisions; it cannot increase the parent grant. Reserve against the same enclosing resource roots. Failed branches, synthesis, messages, repeated context and cancelled work count. Parallel elapsed time and total work are different metrics.

Start each participant with a materialized decision packet suited to its obligation. Record shared premises and deliberately withheld peer answers. A worker may discover a better decomposition and propose a plan revision, but it must not create unbudgeted descendants or silently change another participant's task.

Distinguish message effects:

- A **proposal** suggests work or an interpretation; it does not create an obligation.
- An **observation reference** points to an attributable result; it does not transfer the sender's authority or make its interpretation true.
- A **challenge** names the target claim/version, disputed premise and a possible discriminating check.
- A **handoff** transfers a bounded responsibility through the existing ownership protocol; it includes unresolved effects and required state.
- A **completion submission** supplies an artifact and evidence for a named obligation; the join checks it before parent completion.

Free-form discussion can exist inside these messages, but does not bypass their meaning. Prefer sharing a stable artifact and the exact disputed point over broadcasting entire transcripts. Count context construction and reading cost; references are useful only if the receiving worker can actually obtain the required content.

## 4. A join is an evidential operation

Let parent obligation O be decomposed into obligations O1 through Ok under assumptions H and composition rule J. Parent completion needs accepted evidence for the required sub-obligations, compatibility of their assumptions/versions, and justification that J connects them to O. Matching artifact types or receiving k success messages is insufficient.

For a conjunctive join, every required part must be established. For alternatives, one independently checked result may discharge O, while other operations still require cancellation/reconciliation. A synthesis may create a new claim whose evidence must be checked; it does not inherit the strongest confidence expressed by a contributor. When decomposition is only empirically justified, label the whole-composition evidence accordingly.

Example: two workers produce locally passing code changes that rely on incompatible data formats. The join requires an integrated behavior check, not two green reports. In mathematics, proofs of separate lemmas may use conflicting assumptions; the synthesis must expose the shared assumption set before claiming the theorem.

A temporary coordination owner can choose among permitted actions and submit the final artifact. Ownership does not grant authority to decide disputed facts by fiat. The owner is replaceable from durable state; the society does not need a permanent privileged model to remain coherent.

## 5. Independence, disagreement and shared error

Separate information independence from statistical independence. Two workers with different names or fresh contexts may share the same model biases, source error or generated premise. Record common evidence and derivation ancestry. Agreement based on the same source is not repeated independent confirmation.

For a comparison needing independent proposals, keep initial proposal phases isolated and freeze submissions before exchange. Subsequent critique can inspect them, with that exposure recorded. A critic influenced by the original answer can still be useful, but is a different treatment from independent derivation.

Convert disagreement into a small question: different interpretations, missing premise, checker disagreement, stale version, arithmetic error or genuine empirical uncertainty. Seek an observation or counterexample when possible. If the cap cannot resolve the issue, preserve alternatives and an explicit unresolved condition. Voting or fluent compromise cannot discharge a proof or execution obligation.

Neither majority vote nor confidence aggregation is the seed truth rule. Majority voting can be evaluated as a task-specific decision policy where outputs and error conditions justify it; it is not the universal evidence mechanism. When an external checker is itself uncertain or flawed, record that instrument uncertainty rather than treating it as an infallible oracle.

## 6. Revision, cancellation and persistence

Revisions bind expected plan and dependency versions. A submitted result remains attributable to the plan and inputs under which it was produced. A newer plan may reuse it only after checking the still-relevant obligations; a matching filename or task title is not sufficient. Conversely, do not discard unaffected valid work solely because an unrelated branch changed.

Ownership transfer fences further commits from the old owner without assuming the process has died. Cancellation stops new permission to act; already dispatched work may still produce effects, evidence and cost. The parent cannot declare itself cleanly finished by forgetting those branches.

Bound discussion rounds, fan-out, repeated revisions and total work through the enclosing attempt allocation. Use existing restart and outbox mechanisms. A restart reconstructs pending obligations, submissions, ownership and unresolved effects; it need not reconstruct a persona's private transcript to invent the plan again.

At completion, retain the versioned composition, relevant artifacts, justified outcomes and cost/exposure profile. Do not turn each participant into a permanent agent or award a global reputation from one success. A useful learned product may be the decomposition rule or a previously unknown integration precondition.

## 7. First comparison and failure controls

Use the following treatments within a frozen study:

| Treatment | What it tests |
|---|---|
| Strong single worker with the same tools, evidence access, total budget and permission for repeated attempts/self-checking | Whether delegation beats additional work by a capable reference. |
| Fixed parallel alternatives with a declared checker/selection rule | Whether simple parallel search suffices without adaptive collaboration. |
| Proposed team-selection policy, including its choice to stay single | Whether choosing and revising organization adds useful value. |

The adaptive selector must use only information available before the relevant choice. Evaluate the complete selector on the full panel, including bad selections and single-worker decisions. Reporting only the tasks where teams happened to win would not evaluate the policy. Separately examine conditional outcomes to understand where it helps.

Include decomposable work, tightly sequential work, misleading decomposition, shared-source error, incompatible assumptions, a decisive minority counterexample, delayed participant failure and an already adequate single-worker task. Use independent expected outcomes or checkers where the domain permits. Freeze development and evaluation groups, count coordination overhead, and report end-task correctness, wall time, total resources, unresolved effects and abandoned work. Fix the primary outcome and permitted tradeoffs before scoring.

Structural probes: a missing sub-obligation blocks a conjunctive join; duplicated evidence does not create independent support; a peer message cannot expand authority; a stale owner cannot commit; a cancelled branch's liability survives; an unsupported synthesis remains unsupported. These validate mechanisms, not intelligent collaboration.

Exact live panels and budgets await an interpretable solver and resource profile. A paper's relative gains or a successful human-coordinated worker campaign cannot fill that gap. If adaptive teams add no value beyond the fixed alternatives, keep the simpler organization and useful evidence/ownership semantics.

## Decisions and dependency boundary

- DTT-01: select teams around obligations and information needs, with one-worker execution as a full member of the policy space.
- DTT-02: use existing bounded work graphs and explicit joins; do not add a permanent hierarchy or shared transcript as the society's center.
- DTT-03: preserve evidence ancestry and distinguish isolated proposal from informed critique; agreement alone does not establish truth.
- DTT-04: compare complete selection policies at matched total resources, including harmful delegation and integration cost.

The first concrete slice is now selected in [Team 01](TEAM-01-IMPLEMENTATION.md), against `cb8a62a`. It reuses the existing composition algebra and work substrate, with a bounded three-shape policy and independent task checks. Exact executable budget mapping and development calibration belong to the worker. Broad adaptive organization remains a research question.

## 8. From temporary organization to persistent competence

The architectural object worth retaining is the relationship between a problem structure, an organization of work and the conditions under which the resulting pieces fit. Keeping a roster preserves identities. Keeping only the final patch preserves one answer. A parameterized coordination template can preserve a way to produce and check new answers.

Let the durable state relevant here be `X = (Gamma, E, F)`: the repertoire of executable methods and compositions, attributable evidence, and the current frontier of unresolved obligations. A temporary plan `P` maps a parent obligation and visible state to bounded work. Executing it produces artifacts `A`, observations `O` and cost/liability `C`. Checking the combined result produces either scoped support for the parent or a residual obligation `R`.

`R` must identify what remains unresolved: missing contribution, incompatible assumption, failed combined behavior or insufficient evidence. It is not a scalar confidence score or necessarily a blame assignment. For example, two correct local implementations may use different meanings of an empty interval; the integration counterexample identifies the mismatch without establishing that either agent was uniquely at fault.

There are then two different developmental moves:

- **Repair this work:** change the present artifact or organization under its remaining allocation, then recheck the affected parent result.
- **Improve future work:** propose a parameterized plan or diagnostic that would prevent or expose the same class of mismatch on new inputs. Compare its subsequent behavior through a separate bounded development episode.

The second move is the architectural bridge from a swarm to a learning system. A coordination template is a versioned composition with parameters, applicability conditions, check dependencies and scoped evidence. It can instantiate a single worker, two independent attempts or complementary workers. Its worth does not depend on how many agents it creates.

An example is a producer/consumer repair. One episode discovers that two locally passing patches disagree about interval endpoints. A proposed template makes both workers bind the interval contract first, then executes a generated boundary probe through the assembled pipeline. On a later repository it must bind that repository's actual interfaces and generate/check new work. Retaining the old expected answer is not transfer. If the new problem uses unordered sets rather than intervals, an unmet applicability condition should cause refusal or a new investigation.

This yields an important separation of responsibilities:

| Responsibility | Concrete role in the continuing society |
|---|---|
| Context | Deliver the particular source, interfaces, assumptions and opposing evidence needed by the next node |
| Team policy | Choose who works on which unresolved obligation and how outputs combine |
| Evidence/memory | Preserve artifacts, checked results, failures and exact conditions of use |
| Development/consolidation | Construct, specialize or retire candidate methods and coordination templates |
| Agenda | Decide whether an unresolved pattern warrants more investigation under the current purpose and budget |

Background consolidation can inspect repeated integration counterexamples and propose a reusable diagnostic. That is a bounded development job with an input corpus and a rejecting evaluation, not a free-running reflection prompt. It should wake because new evidence or an admitted opportunity exists; elapsed time may trigger a scan, but it does not supply a reason for unlimited inference. Existing agenda and development machinery already provide the relevant boundaries.

### What we deliberately do not infer

One successful plan does not establish that its decomposition caused success. An integration failure does not establish a general precondition. Reusing a template can improve organization, worsen model conditioning, or merely save planning tokens. These effects need separate observations, including a cold policy with the same resources and task information.

We also cannot certify an arbitrary decomposition merely by attaching contracts to nodes. In Team 01, local checks guide work and an independent whole-task evaluator measures the result. In open scientific discovery the parent may remain an explicitly unresolved hypothesis even when every planned experiment completed. Completion of planned work must never imply truth of the original hypothesis.

### Decisions added by this refinement

- DTT-05: retain parameterized compositions and integration counterexamples; do not make agent identities or transcripts the unit of cumulative competence.
- DTT-06: distinguish fixing the current plan from learning a better future plan. A later checked use is the first behavioral evidence for the latter.
- DTT-07: choose bounded multi-module repair as the first team measurement environment. Generality is a property to demonstrate on subsequent domains, not a property conferred by an abstract interface.
- DTT-08: keep the first template experimental and immutable during held-out use. Delay learned global team selection and learner revision until an observed bottleneck gives them a target.
