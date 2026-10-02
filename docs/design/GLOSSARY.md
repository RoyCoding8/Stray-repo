# Settlement conceptual redesign

Vocabulary for [the selected architecture](REFINED-ARCHITECTURE.md) and [learning model](LEARNING-MODEL.md). These are domain meanings; implementation and empirical status are tracked separately in [the roadmap](REFINEMENT-ROADMAP.md).

## Language

**Settlement**: The continuing collective system, identified by its authorized purpose, commitments, accumulated competence, and accountable history across revisions.

**Settler**: A temporary worker that performs bounded work using a selected composition of capabilities. Its disappearance does not terminate the work's identity or erase its committed state.

**Role**: A reusable description of a worker's responsibilities and preferred capability composition. A role is neither a grant of authority nor an indivisible unit of learning.

**Charter**: The authorized account of the Settlement's purposes, commitments, and permitted scope of autonomous agenda formation.

**Capability**: A versioned, invocable behavior with applicability conditions, declared effects, resource limits, and evidence about its performance.
_Avoid_: Permission, authority, or a document merely describing expertise.

**Authority**: The externally grounded permission to perform specified effects within specified resource and scope limits.
_Avoid_: Capability tier when referring to demonstrated competence.

**Competence profile**: The evidence about a system or capability's performance across identified task families, conditions, and resource budgets.

**Learning**: An evidence-supported, durable change that improves subsequent competence or resource efficiency within a stated scope.

**Development**: A change in the repertoire or organization through which the Settlement solves problems and learns. A developmental change is not necessarily beneficial.

**Development episode**: A bounded investigation into a proposed change in future behavior, connecting triggering experience, candidate construction, comparison and disposition. Completing an episode does not imply a learning gain.

**Method**: A procedure transforming admissible inputs into outcomes or informative failure. Its operational form can be deterministic, model-assisted or a composition.

**Representation**: A language or structure with a stated interpretation that makes operations available on a problem. Its validity and the range of problems it can express are separate questions.

**Translation fidelity**: The extent to which a representation and its operations preserve specified source-task obligations under stated assumptions. It is distinct from coverage and usefulness.

**Transfer**: Use of acquired structure in a different declared task family or interpretation, with explicit adaptation and exposure. Reusing an interface alone does not establish a performance benefit.

**Representation core**: The reusable computation over encoded objects whose identity is held fixed in an unchanged-core transfer claim. Its execution alone does not establish useful transfer.

**Domain interpretation**: The declared meaning and partial translations connecting encoded objects and operations to source tasks. Its version and retained auxiliary information are part of the composition being evaluated.

**Designated witness**: The precise source property a transformation must preserve, including its identity and validity conditions. An unrelated failure or an easier surrogate property cannot substitute for it.

**Cognitive policy**: A procedure choosing actions, methods, context or allocations from permitted alternatives. Its effectiveness is judged by the downstream consequences of those choices.

**Applicability**: The conditions under which a capability is suitable for a proposed use. Support, contradiction and uncertainty about those conditions are distinct.

**Acquisition cost**: Resources consumed to develop, check, select and retain a change, including failed candidates. It is distinct from the resources consumed by subsequent use.

**Subsequent use**: A later attempt using retained behavior, with its own task, conditions and outcome. Fresh-worker invocation establishes continuity; comparative outcomes are needed to establish benefit.

**Investigation**: A persistent pursuit of an objective or question, including its alternatives, observations, obligations, and stopping conditions.

**Attempt**: One bounded execution against an investigation, with a particular worker composition and versioned starting conditions.

**Team plan**: A bounded organization of responsibilities, information dependencies and result-combination rules for an investigation. A team may contain one worker.

**Evidence join**: The justified combination of partial results into support for a parent obligation, respecting assumptions, dependencies and the declared composition rule.

**Commitment**: An accepted obligation with an owner, conditions of fulfillment, resource allocation, and rules for amendment or withdrawal.

**Observation**: A recorded result from an identified interaction or measurement, together with its provenance and conditions. It does not automatically establish the truth of an interpretation.

**Claim**: A proposition with explicit scope and assumptions. A claim may have supporting evidence, opposing evidence, or both.
_Avoid_: Claim as the verb for acquiring work; use acquire or lease.

**Warrant**: A versioned justification that identified evidence supports a particular claim under a stated evaluation procedure and scope.

**Evidence obligation**: A specific requirement that must be discharged before an associated conclusion, completion, or release is accepted.

**Working context**: The temporary information supplied for a particular decision, selected from durable work state, evidence, and admitted capabilities.

**Decision request**: A concrete question or action under consideration, with its decision kind, current work/version state, required inputs, permitted actions, access and resource envelope.

**Context policy**: A versioned procedure that resolves and presents material for a decision request. Its efficacy depends on downstream behavior and resource use, not the amount retrieved.

**Context packet**: Materialized input for a decision, together with its source/transform versions, qualifications, gaps and delivered-content identity. Readiness means compliance with the declared input contract, not complete knowledge or guaranteed correctness.

**Evidence bundle**: A claim or observation with its scope, assumptions, selected support route, relevant registered opposition and unresolved obligations. Association with another record does not itself establish evidential support.

**Context footprint**: The recorded source versions, bytes, derivation routes, operation states and transformations on which a packet depends. Inclusion in a footprint does not establish that a model attended to or causally used the material.

**Frontier**: The current, evidence-qualified account of capability limits, difficult cases, and opportunities for useful investigation or transfer.

**Opportunity**: A scoped possibility to improve competence, resolve consequential uncertainty, or advance the charter. It does not itself authorize work.

**Investigation option**: A proposed finite next experiment with an evidence basis, observable outcomes, a decision consequence and a resource cap. Options form the actionable part of the frontier; blocked and dormant options retain their history.

**Decision consequence**: What an observation would change about the next action, accepted explanation, applicability, instrument choice or disposition.

**Continuation certificate**: A record linking an attempt's actual evidence to a residual question, next discriminating probe and requested additional allocation. It justifies a new admission decision; it does not guarantee progress.

**Developmental trajectory**: The ordered changes, experiments, dispositions, resource use and subsequent outcomes produced by a development procedure from declared starting conditions.

**Evaluation epoch**: A versioned account of what an evaluation measures and how its results are interpreted. Comparability between epochs requires an explicit justification.

**Retirement**: Removal from eligibility for new use, without implying deletion of historical material or cancellation of previously admitted work.

**Learning trial**: A bounded comparison of a candidate change with a defined reference under a declared evaluation protocol.

**Release**: The admission of a particular version or composition for a specified scope of use. Release does not assert universal superiority.

**Substrate**: The machinery that sustains execution, persistence, and enforcement. Its cognitive policies are distinguished from the externally controlled rules that protect authority and accountability.

**Anchor**: The authority outside unilateral self-change that establishes ultimate permissions, protected evaluation access, and recovery control.
