# Representation invention and transfer

Stage 8.5 semantic design. At worker `324174f`, the first core/adapter/checker mechanics are implemented with authored-fixture evidence; model acquisition and the specified held-out comparison remain incomplete. See the [batch assessment](../../reviews/COGNITIVE-BATCH-01-ASSESSMENT.md) and [completion assignment](../../WORKER-REPRESENTATION-01-COMPLETION.md). This develops the operational-language contract in [Representation design](REPRESENTATION-DESIGN.md), the transfer example in [Conceptual architecture](REFINED-ARCHITECTURE.md), and E2/E6. [Research notes](COGNITIVE-RESEARCH-NOTES.md) separate external precedents from our decisions. [Representation 01](REPRESENTATION-01-IMPLEMENTATION.md) commissions one bounded slice; the broader invention space remains a design, not an implementation mandate.

## 1. The selected change in what the society can learn

The society should be able to invent a different set of objects and operations in which a family of problems becomes easier to solve. A representation is useful when it changes the work required: it can expose a missing distinction, eliminate irrelevant variation, introduce a reusable search move or make an independent checker available. Renaming concepts or producing a shorter description alone does not do this.

Select **task-scoped operational representations with explicit translation obligations**. Preserve multiple incompatible representations when they serve different tasks. A shared invocation/evidence contract connects them; the controller does not need to understand every future domain vocabulary.

| Alternative | Decision |
|---|---|
| One universal ontology or internal language fixed now | Reject as a prerequisite. It would make unknown future concepts depend on our present taxonomy and create a large implementation project before evidence. |
| Unrelated generated programs for each task | Keep as a strong baseline and for one-off work. It supplies little explicit basis for transferring their shared structure. |
| Per-family languages, executable interpretations and checked partial translations | Select. Supports reuse while making loss, applicability and interpretation failures observable. |
| Arbitrary edits to the trusted interpreter | Reject as an ordinary cognitive change. New domain interpreters run as versioned capabilities under the existing execution boundary. |

This is open-ended at the level of proposed vocabulary and computation, but bounded at each invocation. The system can invent new operations without inventing new authority for executing them.

## 2. What a representation promises

Write a representation proposal as:

    R = (scope, syntax, interpretation, encode, operations, decode,
         applicability, preserved_obligations, losses, bounds, dependencies)

These components may share one artifact package. They are not separate required services. `encode` is partial and returns an encoded task plus any explicitly retained auxiliary material, a refusal, or a request for information. `decode` interprets an encoded result against the original task and that declared auxiliary material. Translation, checking and decoding consume resources too.

For source task x, let S_x(y) state the original task's success obligation. Let E_x(z) state the encoded task's obligation. A claimed sound translation must justify, on its declared scope and assumptions:

    accepted_encode(x) and E_x(z) and accepted_decode(x, z, y)
        imply S_x(y)

This is an obligation, not a universal decision procedure or a proof supplied by this notation. Where only tests support the implication, label empirical fidelity on those cases. A formal argument depends on the actual interpreter, translations and assumptions being the versions that execute.

Keep four questions distinct:

- **Fidelity:** do accepted outputs satisfy the original obligation, with any approximation explicitly bounded?
- **Coverage:** which source tasks can be encoded and solved, including refusals and non-output cases?
- **Constructibility:** can the encoded object, operations, checks and decoded result actually be produced within bounds?
- **Use value:** does the resulting complete workflow help at declared acquisition and reuse horizons?

Soundness alone permits a vacuous implementation that never produces a result. Solvability preservation, if claimed, additionally requires that relevant solvable source tasks have constructible encoded solutions; it cannot follow from output checking. For optimization, carry the source objective and any distortion/approximation relation explicitly. A better score on a surrogate is not automatically a better source solution.

## 3. How to detect a bad abstraction cheaply

Before evaluating a large library, seek a pair of objects the encoding makes indistinguishable but the intended task must distinguish. If the downstream decision uses only that encoding, such a pair refutes the claim that the encoding suffices for that decision.

Example: the triangular-prism graph and K3,3 each have six vertices of degree three, but only K3,3 is bipartite. The prism consists of triangles on vertices 0,1,2 and 3,4,5 plus matching edges 0–3, 1–4 and 2–5; K3,3 has all edges between those two vertex groups. A degree-sequence-only representation cannot decide bipartiteness for both. A representation retaining an inspectable original graph could recover the distinction; then the recovery operation and its cost belong to the method, and the degree sequence alone is not the claimed sufficient representation.

Apply this test to practical cases: two failures sharing an exception name but having different causes; equal-sized contexts where one omits an opposing result; visually similar formulas whose variable domains differ; compressed experiment summaries with different unresolved effects. The source obligation decides which distinctions may be lost.

A lossy abstraction can still be useful as a search heuristic if final source checks remain effective and its failure/coverage limits are recorded. Do not require full invertibility when the task needs only a particular property. Conversely, a successful round trip on examples is not proof that all relevant operations preserve meaning.

## 4. The invention cycle

1. **Select a bottleneck from experience.** Name the repeated computation, unavailable observation or costly distinction, and an alternative explanation. Frequent expensive successes are eligible too.
2. **Propose an intervention.** Specify what changes if a new operation or distinction becomes available. A proposal may factor common code, invent a new predicate, introduce a domain language or construct an instrument. Keep its hypothesized benefit separate from its implementation.
3. **Construct a bounded package.** Define invocation and failure behavior. Mechanically recognizable repeated structure can suggest a shared procedure; model inference can propose structure not obvious syntactically. No custom synthesis engine is required for the first trial.
4. **Attack fidelity before seeking advantage.** Use source/encoded positive controls, indistinguishable-pair counterexamples, invalid-domain inputs and cases the package should refuse. Check external effects and failure identities where relevant.
5. **Freeze and compare use.** Evaluate source outcomes, not only internal encoded success. Include complete acquisition, translation, search, checking, routing and fallback cost. Release only the supported composition and scope.
6. **Attempt transfer as another hypothesis.** Freeze a new domain interpretation while keeping the purported shared core fixed. If the core changes, record a derived version and qualify the result as adaptation rather than unchanged-core reuse.
7. **Update the frontier.** Retain a useful method, a narrower applicability claim, an instrument gap, a refutation or a new question. A failed abstraction can teach which distinction must be restored without producing a release.

Candidate descriptions are part of the context through which future workers choose and use the package. Test important descriptions against execution examples; do not let a persuasive name override an operational precondition. Preserve the original task/result references through representation changes so later workers can inspect what the abstraction omitted.

## 5. First transfer candidate: reduction with a preserved witness

Use the existing proposed reduction example as a candidate, not a mandated discovery. Its shared procedure accepts an object, candidate reductions, a nonnegative integer measure and a predicate for the designated witness. Accept a reduction only when the measure strictly decreases and the witness remains valid. The initial measure bounds the number of accepted reductions; a separate total cap bounds rejected checks and search. Report local irreducibility only if all reductions required by the declared neighborhood were checked. No global-minimum claim follows.

For a software failure, the witness must identify the relevant failure condition. Replacing one bug with a different smaller crash is not preservation merely because the process still fails. For a finite mathematical counterexample, a domain-specific checker establishes the counterexample property and validity of the object. The shared search loop does not establish either checker.

To make this a representation test, the package must supply a usable object/operation interpretation and translation, not just a renamed generic function. Distinguish three outcomes: reuse of search code; valid interpretation in another domain; improved complete task solving. Only the last supports a scoped transfer benefit, and it still does not establish broad cross-domain discovery.

## 6. Comparison specification before an implementation contract

For the first scoped study, compare:

| Arm | Retained material |
|---|---|
| A | The same available base solver/tools and a strong textual account of development observations and lessons. |
| B | A plus original task-specific procedures from the same development material, without the proposed abstraction. |
| C | B plus the frozen shared representation/procedure and its domain interpretation, through a frozen selector. |

The arms may use the same model; the treatment is retained operational structure. Track actual use and selector overhead. If C never invokes the representation, its score does not measure a benefit from representation use. Compare acquisition-inclusive totals as well as later-use costs; do not conceal the cost of creating C because B was already available.

Before final tasks are exposed, freeze family grouping, translation/checker versions, supported and unsupported cases, adaptation allowance, reuse horizons, resource limits, primary outcome, regression limits and how every refusal/timeout/format error is counted. Use positive, negative and insufficient-representation controls. Separately freeze transfer-domain examples and evaluation groups; changed names or random constants are not automatically a new family.

If the representation earns a limited release, test actual selected use in a fresh process and a mixed task panel where the incumbent should still be used. A deterministic hand-authored representation can validate mechanics first, but only an actual admitted construction episode supplies evidence of acquisition. Neither study has run yet. Representation 01 now selects finite panel sizes, bounded construction and execution allowances for a pilot; those are experiment choices, not estimates of optimal budgets. Its executable-retention comparison includes established reducers and explicitly excludes per-task model inference. A promising result selects a broader trial rather than immediately authorizing a general release.

## 7. Retention, composition and rejection

A representation's identity includes its interpretation and dependencies. Reinterpreting a token or operation creates a new version. Existing artifacts remain interpretable under their historical version; an unsupported migration cannot silently relabel them.

Composing translations requires compatible domains, assumptions, auxiliary material, effects and bounds. Fidelity of each edge does not settle unrecorded interaction effects or availability of required information. Evaluate the composed route where contracts do not discharge those obligations. Use a bounded set of explicit candidate routes initially; do not build an automatic universal translation graph search.

Reject or narrow the proposal when it loses task-relevant distinctions, preserves the wrong witness, works only on invention examples, evades coverage by refusing difficult cases, or costs more than useful reuse can repay. Preserve a bounded experimental alternative only with a concrete future probe and allocation. High compression, attractive vocabulary and a long library are not release criteria.

## Decisions and dependency boundary

- DRT-01: choose local operational languages with explicit partial translations; keep generality in proposed computations rather than a universal seeded ontology.
- DRT-02: test fidelity, coverage, constructibility and use value separately, including cheap indistinguishable-pair counterexamples.
- DRT-03: distinguish unchanged-core reuse, adapted reuse and a newly solved task; evaluate actual source-domain outcomes.
- DRT-04: preserve textual lessons and original procedures as strong comparators; acquire the abstraction only when it earns its cost or a bounded further trial.

Ready now: semantic contracts, alternatives, rejection cases, and the concrete Representation 01 task families, invocation boundary and study protocol. The existing repair-specific ABI does not implement the proposed interpretation boundary; the worker will add one named profile using existing runtime primitives. Actual input/output preservation, source-checker reliability, acquisition quality, costs and selected-use behavior remain empirical obligations. The first corpus is deliberately constructed and labeled; we do not infer that an organically accumulated useful corpus already exists. No new stack choice is justified yet.
