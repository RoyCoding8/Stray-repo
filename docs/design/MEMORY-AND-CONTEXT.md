# Memory and decision context

Status: selected architecture for stage 8.3, 2026-09-10. The first implementation slice is bounded to diagnosis, method construction and fresh-worker continuation. It extends the [learning model](LEARNING-MODEL.md), existing evidence/continuation contracts and E4. It does not select a new database or claim a demonstrated learning advantage.

## 1. The architectural decision

Treat memory access as an executable, budgeted computation serving a particular decision. Durable records preserve experience and competence. A versioned context policy resolves what the next decision requires into a packet of actual content, current state, evidence qualifications and explicitly missing information. The packet is bound to the invocation that receives it.

This separates three problems often hidden inside “memory”: retaining useful material, finding material for a decision, and expressing it so a worker can act correctly. Better storage alone does not solve the other two. The present implementation illustrates the distinction: `context.build_context` records references and transformations, while the new episode constructor receives unresolved task references. Persistence exists; the required experience does not reach that constructor.

The selected mechanism is **decision-directed context construction with explicit evidence dependencies**. A context policy can later be learned using the same candidate/trial/release system as other policies. Begin with a deterministic policy and a strong fixed retrieval baseline. Do not introduce adaptive search before the input/output contract is testable.

## 2. What persists

Use the existing coherent durable store and artifact system, with different meanings and access paths rather than independent copies of each “memory kind.”

| Durable material | Meaning | Rules for change |
|---|---|---|
| Experience | What was attempted, what input/version was used, observations, outcomes and cost | Preserve provenance and unresolved outcomes. Interpretations are separate from observations. |
| Claims and operational explanations | What evidence suggests, including scope, assumptions, competing explanations and counterexamples | New evidence can qualify or defeat support. Earlier observations are not overwritten. |
| Capabilities | Invocable methods, representations and policies with versions and applicability | Publication, trial eligibility, release and retirement remain distinct. |
| Working state | Commitments, next decisions, unfinished alternatives, dependencies and in-flight effects | Reconcile against current authoritative state on continuation; summaries do not replace operation records. |

Indices, summaries, tags and embeddings are derived access aids. They may be useful, but they cannot independently establish a claim, release a method or settle an operation. One record can participate in several views without becoming several drifting sources of truth.

## 3. Start with the decision, not a similarity query

Define a decision request abstractly as:

`D = (purpose, investigation, decision_kind, current_versions, required_inputs, allowed_actions, access, budget)`.

The purpose is a concrete question or action being considered. Required inputs are obligations of that decision type. Allowed actions and access come from the controller's admitted scope; a proposed context request cannot grant them. Current versions identify the intended continuation rather than silently selecting the newest available method.

| First decision kind | Required material before the model can perform it |
|---|---|
| Diagnose a bottleneck | Actual development inputs, attempted behaviors, observed outcomes/costs, relevant task specifications, unresolved observations, and the diagnostic output contract |
| Construct a method | Selected intervention, permitted concrete examples and counterexamples, development feedback, invocation/output contract, applicability boundary, effect/resource envelope, revision budget and current candidate lineage |
| Resume an investigation | Accepted objective and constraints, selected versions, last completed outcomes, pending external operations, unresolved obligations, next decision and remaining allocation |

Requirements are explicit for these seeded decision types. They are not a universal algorithm that infers all information needed for arbitrary reasoning. A later invented decision type proposes a new contract and tests it; a model cannot waive an existing required input simply because it would like to proceed.

A constructor needs a description of the actual executable interface: response shape, entry arguments, self-check behavior, input/output meaning and bounded failure/abstention behavior. That interface is legitimate instruction. Development examples and counterexamples are evidence. Preserve the distinction in the serialized request.

## 4. The context packet

The builder returns one of three outcomes:

- `ready`: declared input obligations are covered, with qualifications and a bounded rendered request.
- `needs_information`: identified material is missing, unavailable, unauthorized, or cannot fit; include a bounded retrieval/decomposition proposal.
- `stale`: a relevant source, dependency, selected version or working-state condition changed and must be refreshed.

“Ready” means compliance with the declared input contract. It does not prove the packet contains every fact a model could need or guarantee a correct answer.

An abstract packet is `P = (D, policy_version, source_snapshot, mandatory_content, evidence_bundles, optional_content, gaps, footprint, rendered_digest)`.

The footprint identifies exactly which source versions, artifact bytes, derivation routes, opposition records, operation states and transformations justify this view. The rendered digest identifies the actual model-visible payload. A manifest of references with no corresponding content or usable admitted retrieval action is not materialized context.

Record three distinct events: material found, material delivered, and task outcome. A model's later citation or self-report does not prove causal use or attention. Compare policies to establish benefit; do not reward memory records merely for appearing in a prompt.

## 5. Constructing a packet

Use the following deterministic seed procedure. It is one policy version, not a permanent cognitive center.

1. **Resolve the request.** Obtain current investigation state, admitted authority, pending operations and pinned versions. Choose the decision contract. Identify required inputs and available budget before retrieval.
2. **Resolve direct references.** Fetch the named experience, content, artifacts and applicable capability contracts through the existing access and byte-verification paths. A family tag is not a substitute for its observations. Classify a missing or withheld reference explicitly.
3. **Assemble evidence bundles.** For a claim used as supported, find an admissible support route and its qualifications. Bring relevant registered opposition or defeaters with it. Preserve uncertainty where the interpretation remains disputed.
4. **Retrieve optional context.** Use bounded lexical, structural/dependency and, if already available, semantic access. Rank by declared decision relevance, applicability and unmet information needs. Similar wording is only a candidate-generation signal.
5. **Pack within the envelope.** Place required state/contracts first, then selected evidence bundles and optional material. Measure the complete serialized payload, including schemas and wrapper text, while reserving output/tool capacity. Record omissions and transforms.
6. **Validate and bind.** Check required input coverage, access, relevant versions, current eligibility and byte availability. Persist packet identity and bind it to the model request that will actually use it.
7. **Observe the result.** Record outcome and resource consumption. Missing information can originate another bounded read or investigation. Unsupported inference remains a claim, not a new authoritative memory.

The prototype may use a conservative payload bound when exact provider tokenization is unavailable, labeled as such. It must not claim an exact token count from a character estimate. If a required input cannot fit, narrow the decision or stage a bounded sequence of decisions. Do not silently drop the input and leave the packet “ready.”

Keep state and content within a coherent declared snapshot where possible. Before consequential use, recheck dependencies that can change after the snapshot. A global evidence epoch is a sufficient conservative first implementation; finer invalidation is an optimization. The execution controller still independently enforces authority and pending-effect rules.

## 6. Evidence bundles and the role of counterevidence

A retrieved claim should travel with the qualifications that determine how it can be used. Define an evidence bundle as a claim or observation, its task scope and assumptions, a selected support route if asserted as supported, relevant registered opposition, source content or admissible drill-down, and the next unresolved obligation.

Suppose C is supported by jointly required premises A and B, or independently by D. Retracting B invalidates the first route, not necessarily the route through D. A packet may select the cheaper valid route through D, but must not pretend that B still supports C. If registered counterevidence challenges C in the proposed scope, a positive summary alone is insufficient.

This mechanism covers known relationships. It does not guarantee discovery of every contradiction in natural-language material. Unknown conflicts, omitted dependencies and mistaken instruments remain failure modes. A packet that cannot fit enough evidence may present C as an unverified lead, omit it from optional material, or request a narrower decision; it cannot upgrade it to a fact to save space.

This also gives negative experience operational value. A failed method can be retrieved because it prevents repeating a failed intervention under matching conditions. Include the conditions under which retry could be justified. A failure on one task family does not become a global prohibition.

## 7. Compression and active access

Lossless omission and lossy interpretation have different obligations. Removing duplicate immutable references is mechanically checkable. Summarizing a scientific claim while preserving its quantifiers, exceptions and causal meaning is partly interpretive. A source hash proves identity, not semantic preservation.

Keep required executable contracts, current action states, hard constraints and critical structured qualifications exact. Optional narrative can be shortened with source references, transform version and acknowledged loss. A transformed claim cannot have stronger scope or certainty than the underlying evidence warrants. Verify consequential details at the source where that interpretation matters.

If an optional summary hides a detail needed later, the worker can request an admitted read. Reads have their own budgets and current access checks, and the result produces a new packet revision or attached observation. A list of “you may retrieve this” suggestions is not an implemented retrieval affordance. The first slice can avoid a general interactive retrieval loop by materializing the required bounded development examples directly.

Longer-term, the context policy may choose between reading a source, requesting a discriminating experiment and acting with stated uncertainty. Its objective is better downstream decisions per resource envelope. Surprise, retrieval count and compression ratio are search hints, not measures of competence.

## 8. Changes, retention and background development

Existing version/invalidation semantics govern packets. If a pinned method is quarantined or a support route is defeated, an older packet cannot restore eligibility. A newly valid alternative route can support a rebuilt packet without erasing the previous result. A worker restart reconstructs required state from durable records, not a copy of another worker's private reasoning.

Keep material needed by active obligations, admitted releases, pending trials and recovery. Cold material can retain inexpensive discovery metadata and explicit archival status. Deleting bytes and retiring eligibility are different operations; a summary cannot silently replace protected evidence bytes. The first slice adds no automatic destructive forgetting or new garbage collector.

Later consolidation searches for repeatable computations and explanations across experiences. It may propose a method, representation, context policy or retirement. Such proposals enter the development loop and consume a separate bounded allocation. The mechanical wakeup supervisor does not perform model inference merely to demonstrate activity. Episode completion, new counterevidence, repeatedly missing context or a due decision can be concrete wake conditions; selection among them is stage 8.4 work.

## 9. Formal obligations and limits

Let `Req(D)` be the declared required inputs, `Allowed(D)` the authorized material, `Visible(P)` the content actually delivered, and `Support(P)` its current evidence footprint. For an admissible packet:

1. **Coverage:** every required input has actual content, an explicit current state such as an unresolved outcome, or a refused/staged decision. A bare inaccessible ID does not discharge coverage.
2. **Access:** every delivered source is admitted for this caller, purpose and exposure history. Access labels come from authoritative metadata, not model-written text.
3. **Qualification:** delivered claims retain relevant scope, assumptions, support disposition and registered counterevidence. “Conflicting” does not silently become “supported.”
4. **Budget:** the rendered input plus declared output/tool reserve fits the admitted envelope or returns `needs_information`.
5. **Binding:** the invocation identifies the packet and actual rendered bytes. Rebuilding content after binding requires a new revision.
6. **Freshness:** relevant invalidation or pending-operation changes cause revalidation before affected use. Pinning a version does not pin authority forever.
7. **Continuity:** required state survives the originating process and does not replay completed external effects.

These are conditional engineering obligations for known contracts and recorded dependencies. Natural-language sufficiency, relevance, correct causal explanation and improved intelligence are empirical questions. The formalism deliberately does not claim an optimal or infallible memory policy.

## 10. Alternatives and primary-source grounding

Memory tiers and model-directed data movement already have precedent: [MemGPT](https://arxiv.org/abs/2310.08560) uses virtual context management and interrupts across memory tiers. That is a useful reference for active access; it does not by itself answer this project's evidence and release obligations.

[A-MEM](https://arxiv.org/abs/2502.12110) describes structured notes, dynamic links and updates to contextual attributes of memories. We can use such associations as retrieval proposals while retaining a distinction between derived organization and warranted evidence.

[Lost in the Middle](https://arxiv.org/abs/2307.03172) reports position-sensitive performance on document QA and key-value retrieval for its tested models. It motivates testing placement and distraction rather than assuming more context is always effective. It does not establish the same failure magnitude for the currently selected model.

These primary-source abstracts were checked on 2026-09-10. They provide adjacent mechanisms and test ideas, not an exhaustive novelty review or empirical support for our particular design.

| Decision | Selected mechanism | Strong alternative and test that could change the choice |
|---|---|---|
| DMC-01 Access unit | A packet for a particular decision with explicit input obligations | Generic top-k retrieval. Prefer it when a strong fixed baseline matches outcomes at lower total cost. |
| DMC-02 Evidence organization | Derived associations plus explicit support/opposition dependencies | One evolving narrative. Compare continuation under corrections, contradictions and source loss. |
| DMC-03 Context policy | Versioned deterministic seed, later evaluated like other capabilities | Model-managed context from the start. Compare downstream correctness and acquisition/use cost without giving one arm privileged data. |
| DMC-04 Continuity | Durable working state plus source materialization | Transcript/summary alone. Test process replacement with pending effects and superseded conclusions. |
| DMC-05 Retention | Protected dependencies and explicit archival/retirement | Recency-only decay. Test useful old exceptions and bounded storage pressure before choosing a forgetting policy. |
| DMC-06 First implementation | Materialize context for three existing decision types | A universal memory service or additional graph/vector platform. Defer until measured workload requires it. |

The architectural bet is that decision obligations, evidence qualifications and executable policy evaluation form a useful combination. Do not call that a new scientific result without a proper literature study and comparative evidence.

## 11. The next bounded implementation: Development 02

First address D02-001 through D02-004 in [the readiness assessment](../../reviews/DEVELOPMENT-01-READINESS.md). They are prerequisites for interpreting the episode, not an open-ended audit assignment. Use the materialization work below to solve the experience-input gap rather than building a parallel solution.

| ID | Required behavior | Observable acceptance |
|---|---|---|
| CTX-01 | Versioned decision requests for diagnose, construct and resume | Required input contracts differ appropriately; empty references alone cannot yield `ready` |
| CTX-02 | Resolve authorized experience and exact artifact/source versions | Actual examples, attempts, observations and costs reach construction after they exist; protected evaluation material does not |
| CTX-03 | Materialize output/invocation contracts and current working state | A model-facing payload explicitly states required response/entry behavior; continuation includes unresolved effects and obligations |
| CTX-04 | Budget and qualify the packet | Oversized/missing mandatory content stages or refuses; optional omissions and cost/count estimation are reported |
| CTX-05 | Bind actual delivered content to its sources and invocation | Packet identity and rendered digest appear in the execution record; metadata-only context cannot pass |
| CTX-06 | Revalidate relevant support, opposition, eligibility and byte availability | Stale or defeated support is not silently reused; a valid alternative route can still be used |
| CTX-07 | Resume through a fresh process using durable packet/state reconstruction | Kill originating process, preserve required store/artifacts, complete the next bounded decision without repeat construction |
| CTX-08 | Ground post-disposition use and fallback in execution | Separate unseen use assignment after release/rejection, actual selected behavior/output, outcome and cost; no completion from pinning alone |
| CTX-09 | Inspect packet contents, gaps and provenance in the existing operator view | Show decision, source/transform versions, known qualifications, delivered-content identity and next action; inert rendering |
| CTX-10 | Run a focused structural challenge panel and prepare the live comparison | Complete outcomes and exposure/cost policy; fixture compliance is distinct from model benefit and full-system qualification |

Use existing `context.py`, `evidence.py`, artifacts, continuations, episode state and broker records. Add only the representation needed to connect them. No new vector database, memory framework, universal ontology, permanent specialist hierarchy, automatic deletion policy or global agenda engine is part of this slice. The worker chooses schema and module seams with a requirement-to-path map.

## 12. Challenge panel and empirical decision

Freeze a small panel before policy feedback. Include: a bare reference with missing content; a known counterexample to an attractive method; a superseded conclusion with an intact alternative support route; distracting recent material around an older relevant observation; mandatory content exceeding the envelope; and a restart with an unresolved operation. These scenarios have inspectable expected behavior independently of model agreement.

Structural tests establish packet and lifecycle semantics. A model comparison asks a different question: does the selected policy improve continuation/task outcomes or use cost? Compare it against a strong fixed context/retrieval policy with the same corpus, required inputs, tool access, model, task order policy and total resource ceilings. Do not handicap the baseline by omitting its required task contract or pending operations.

Report complete paired outcomes, context/retrieval cost, inference usage, missing-information decisions, incorrect actions and actual follow-through. Charge policy construction and diagnostic calls separately. Treat the first result as a finite-panel pilot; use held-out groups and the protected evaluation procedure for stronger learning claims. A direct model-only pilot does not validate the repository's broker, containment or billing.

If both policies succeed equally, keep the simpler one unless measured efficiency justifies the extra machinery. If both fail because the task contract is incomplete, repair the experiment. If additional optional context helps only at much larger total cost, report the trade-off. If scope/contradiction handling improves while task performance does not, report that narrower structural result.

A first [live read-only pilot](../../reports/CONTEXT-PILOT-01.md) has now run: both arms answered four synthetic cases correctly; following explicit dependencies used 77.35% fewer gateway-reported input tokens than full context. This is feasibility evidence for the simple resolver, not learned retrieval or a runtime qualification result. It does not justify a more elaborate memory engine.

After this slice, refine stage 8.4: which observed gaps and opportunities should autonomously trigger the next investigation, and how their expected information/use value competes with committed work. Memory and context then supply the evidence that agenda selection needs.
