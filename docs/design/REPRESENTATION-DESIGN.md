# Settlement: selected representations

2026-09-08; companion status updated 2026-09-09. R5 of [the refinement roadmap](REFINEMENT-ROADMAP.md), based on [the conceptual architecture](REFINED-ARCHITECTURE.md). This document selects representation families and their semantic contracts. Concrete choices now follow in [TECHNOLOGY-DECISIONS.md](TECHNOLOGY-DECISIONS.md) and [PRACTICAL-SPECIFICATION.md](PRACTICAL-SPECIFICATION.md). It belongs only to this isolated design pass.

## 1. The decision

Use **typed durable state, immutable executable artifacts, and explicit dependency structures**, with human-readable views generated from them. Preserve open-ended domain content inside this disciplined boundary. The society can invent new concepts, programs, and representations without changing the meaning of authority, an experimental result, or a completed commitment.

These are logical representations, not a requirement for three databases or a new programming language. One storage engine may support several of them. Markdown remains a useful explanatory format; its file extension does not determine whether something is a learned capability. Behavioral contracts, invocation, provenance, and measured use determine that.

The selected split is:

| Concern | Authoritative representation | Reason |
|---|---|---|
| Ownership, commitments, reservations, operation status, release eligibility | Typed records with constrained state transitions | These need coherent updates and explicit legal transitions. |
| Observations, claim versions, warrants, comparison protocols and results | Versioned typed records referencing retained artifacts | Their scope and provenance must survive reinterpretation and default changes. |
| Programs, proofs, datasets, model configurations, translations, domain languages | Immutable artifact packages with manifests | Exact tested material must be identifiable, reusable, and interpretable. |
| Support, alternatives, work dependencies, composition and transfer hypotheses | Explicit typed relations, including grouped premises | Different relations imply different reasoning and invalidation behavior. |
| Search, summaries, dashboards, competence maps, working contexts | Derived views with provenance and freshness information | These may be rebuilt or replaced without silently rewriting their sources. |

The key rejection is an undifferentiated universal record whose payload and generic score determine every behavior. Shared identity and provenance are useful; uniform meaning is not. Also reject separate storage products for every row in this table without an operational need.

## 2. Identity, versions, and change

Distinguish four identities:

1. **Continuing identity:** this investigation, method family, or claim lineage across revisions.
2. **Immutable version:** one precise set of content and declared dependencies.
3. **Invocation identity:** this particular execution, including retries and uncertain effects.
4. **Release identity:** permission to select particular versions for particular uses under a decision policy.

Changing a default modifies release selection; it does not rewrite the version used by an old invocation. Two invocations of identical content remain different events. Two byte-distinct proofs of the same statement remain distinct artifacts even if their conclusions are logically equivalent.

Artifact manifests identify their format, interpretation version, retained content, dependencies, and required runtime assumptions. A content digest detects byte changes; it establishes neither semantic equivalence nor the trustworthiness of the content. Logical equivalence, where needed, is a separate scoped claim.

Capture model and environment identity as far as it is actually observable: requested configuration, returned provider metadata, relevant tool versions, sampling settings, and execution conditions. An opaque provider alias cannot become a reproducible model checkpoint merely by being written into a manifest. Unknown equivalence remains unknown; changed behavior can trigger renewed evaluation or narrower applicability claims.

A transition journal records consequential state changes together with the corresponding typed update. Its purpose is accountability and recovery. Do not require rebuilding all current state by replaying every historical event. Recorded external actions are facts to reconcile, not commands to execute again during reconstruction.

Retention applies to the journal as well as artifacts. Preserve the material required for active commitments, support, and recovery; retain checkpoints and lineage under an explicit policy. An archive reference counts as available evidence only while retrieval is actually possible under its declared conditions.

## 3. Capabilities as executable packages

A capability package contains an invocation contract, executable behavior, dependencies, interpretation requirements, and links to evidence. Separate its **claims about behavior** from **permissions granted to an invocation**.

The invocation contract describes:

- Input and output shapes, including domain interpretation versions.
- Applicability conditions and which are mechanically checkable, empirically supported, or unresolved.
- Possible outcomes: useful result, explicit failure, request for an observation, suspension, or another bounded operation proposal.
- Declared effects and resource bounds, subject to enforcement rather than trust in the declaration.
- Compatibility and evidence dependencies.

Use two complementary behavior forms:

**Executable modules** implement computation, tools, generators, translators, and specialized methods. Their internals may use a general-purpose language. They execute within the controlled environment and return observations or permitted operation proposals through the invocation boundary. Source code is inspectable material; it is not permission to run inside the trusted controller.

**Compositions** express how invocations cooperate. Select a small structured algebra: sequence, conditional choice, bounded repetition, parallel alternatives, dependency joins, and suspension pending an observation. Model inference is an invocable operation in this algebra. A composition can delegate complicated internal logic to a module, so the algebra need not grow into a universal programming language.

Every loop has an enclosing attempt bound. A dynamically generated next step becomes a new validated continuation before its effects occur. Parallel cancellation means an attempt has lost permission for subsequent work; already dispatched external effects still need reconciliation. A join names which outputs satisfy which obligations, rather than waiting for a count of successful workers.

This gives the system small editable compositions and unrestricted intellectual room inside bounded modules. It can replace a prompt, invent an algorithm, combine a symbolic method with inference, or change its team strategy. A whole composition may be the unit of variation when its components interact. The representation imposes no requirement that every learned behavior be decomposable into independently beneficial parts.

Do not promote a custom domain interpreter into the enforcing controller. A new interpreter is itself a versioned capability. Its outputs still cross the same authority and accounting boundary. Changing that boundary is a different revision scope.

## 4. Invented representations as operational languages

A learned representation must have enough structure for a future worker to do something with it. Represent it as a package with:

| Element | Required meaning |
|---|---|
| Domain and version | Which objects and tasks this interpretation addresses. |
| Vocabulary and object constructors | How valid expressions or objects are formed; unfamiliar vocabulary is allowed. |
| Interpretation | What those objects mean in the target domain, with explicit assumptions. |
| Task translation | How source tasks become tasks in the new representation, including failure to translate. |
| Solution interpretation | How results become candidate source-domain results. |
| Available operations | Methods, transformations, observations, or search moves defined over these objects. |
| Fidelity and coverage evidence | What is preserved, what is lost, and where the translation applies. |
| Use evidence | Whether the resulting workflow improves the relevant performance profile after all translation costs. |

Some packages will have formal syntax and checked semantics. Others will combine structured objects with partially natural-language interpretation and empirical validation. The latter can be useful, but do not inherit a formal guarantee from having typed fields.

Use **versioned domain vocabularies with explicit translations**, rather than one ontology that must anticipate all future discoveries. Two investigations can develop incompatible descriptions. Shared identity, provenance, invocation, and evidence contracts make the descriptions inspectable without forcing premature unification.

A translation between vocabularies is itself a capability with fidelity obligations. Multiple translations can coexist. There is no automatic equivalence merely because two fields have the same name. When a concept changes, retain its old version and invalidate dependent claims where their assumptions no longer apply.

For example, a learned reduction interface can describe a reducible object, a measure, candidate transformations, and a witness predicate. Software failures and finite mathematical counterexamples can instantiate it differently. The shared search structure becomes transferable only after each interpretation satisfies its own witness and termination obligations. A reduction that reaches a locally irreducible witness does not automatically find a globally smallest one.

The same principle allows new graph abstractions, symbolic languages, experiment descriptions, or compressed state representations later. The selected architecture does not require those formats now. A future trained model could also be a package dependency with its own identity and evaluation; weight training is not part of the current work.

## 5. Evidence as grouped derivations

Represent a warrant as a conclusion with **alternative derivations, each containing its jointly required premises**, procedure, assumptions, and scope. This is a directed dependency structure with grouped edges, often called a hypergraph. A separate graph database is not implied.

The grouping matters. Suppose claim C is supported either by a checked proof using premises A and B, or by an independent derivation using D. Retracting B invalidates the first derivation. It need not invalidate C when the D derivation still discharges the same obligation. A flat list of links cannot distinguish this from a derivation requiring A, B, and D together.

Use distinct relation meanings:

- Required support: a premise in an identified derivation.
- Opposition or defeat: evidence that challenges a claim, assumption, or applicability scope.
- Background: relevant context that does not discharge an obligation.
- Attribution: what source or invocation produced the material.
- Equivalence or translation: an independently justified relationship between versions or representations.

A support cache records which versions, assumptions, and evaluation epoch produced its conclusion. Registered changes invalidate the relevant cache dependencies. Before consequential use, confirm current admissibility. Eager propagation and lazy recomputation can be combined; their correctness obligation is the same. Concurrency must prevent a stale cached admission from bypassing a relevant already-committed invalidation.

Represent evaluation outcomes according to their meaning. A checked proof needs a proposition, assumptions, checker identity, proof artifact, and receipt. An experiment needs its protocol, sample population, observations, exclusions, outcome definition, uncertainty treatment, and result. Human acceptance identifies the person and accepted scope. None becomes a universal scalar confidence merely to fit a common interface.

Some propositions remain natural language and their relationship to experiments remains partly interpretive. Mark that boundary. Contradiction detection is not guaranteed by string comparison or a universal reasoner. Missing dependencies, misunderstood specifications, and incorrect instruments remain empirical failure modes.

The system may record both a result and a challenge to its interpretation. Selecting which evidence is sufficient for a particular use is a versioned decision under an evidence policy; it does not erase the disagreement.

## 6. Investigations as persistent state with conditional dependencies

An investigation is a versioned objective and obligation structure with owned attempts. It is not restricted to a task tree. One result can support several investigations, alternative branches can compete, and an observation can determine a branch that was not known in advance.

Represent dependencies with explicit conditions: all listed obligations, any sufficient alternative, or a conditionally activated branch. A failed attempt is evidence about an approach, not the logical negation of its investigation's objective. A branch can be replanned without rewriting completed observations or silently changing the original commitment.

The current working state holds the next decision, unresolved questions, selected versions, required evidence, pending operations, and explicit reasons for consequential choices. It does not need to serialize private model internals or pretend that a textual summary is a complete copy of a mind.

Represent three dimensions separately:

| Dimension | Examples |
|---|---|
| Attempt lifecycle | Prepared, running, suspended, completed, failed, cancelled. |
| Commitment disposition | Proposed, accepted, fulfilled, amended, withdrawn. |
| External operation outcome | Not dispatched, in flight, observed result, unresolved outcome, reconciled. |

These are not interchangeable statuses. A cancelled attempt may still have a charge to reconcile. A completed attempt may leave its parent objective unsolved. Withdrawal needs the commitment's authorized procedure; workers cannot make obligations disappear by renaming them.

Ownership generations gate writes that require ownership. A separate collaboration relation allows workers to submit evidence without acquiring exclusive completion authority. Current authority and release eligibility are checked at use, so version pinning cannot revive revoked permission.

## 7. Memory and context as views over durable material

Use one coherent body of durable material with multiple access paths: direct identity lookup, text or semantic retrieval, dependency traversal, and investigation continuity. The exact retrieval algorithms are later technology and evaluation choices. There is no need for a separate autonomous agent or separate database for every kind of memory.

Classify material by its use:

- Episodic records preserve what happened in an invocation or investigation.
- Claims and operational models preserve what is inferred, predicted, and disputed.
- Capabilities preserve invocable behavior.
- Working state preserves unfinished commitments and pending decisions.

The classifications can refer to the same artifact. Avoid copying it into several stores that independently drift.

A context builder returns a **context view** with the decision it supports, selected source versions, inclusion and compression transformations, current governing references, and unresolved retrieval limitations. Optional summaries are derived artifacts linked to their sources. A compacted claim retains its scope and uncertainty; a persuasive summary cannot upgrade its warrant.

The enforcing controller checks authority and resource conditions independently of whether a model understood the context. The model still needs the relevant constraints to plan useful actions. If mandatory decision information cannot fit, the workflow narrows or stages the decision. It cannot certify a context complete simply because a token limit was reached.

Context construction may use learned query expansion, selection, and compression. Evaluate the composed process on downstream continuation, retrieval of counterexamples, constraint preservation, and total cost. Do not select it solely by compression ratio or source recall: recalling every source can still make an unusable context.

Access and disclosure restrictions apply to the context view as well as to stored material. In particular, an evaluation task's hidden answer cannot become ordinary retrieval context merely because the society generated or stored it. Provenance is useful for detecting exposure; enforcement is needed to prevent it.

## 8. Learning trials, profiles, and releases

Keep the **proposal**, **execution record**, **evaluation result**, and **release decision** distinct. They have different authorship and authority. A model-written result cannot masquerade as an evaluator receipt because it contains a matching field name.

A trial protocol names candidate and reference versions, initial information access, sampling, task validity, budgets, metrics, stopping rules, permitted exclusions, and uncertainty treatment. A trial result references actual invocations and actual conditions. Deviations produce an explicit qualification or a new protocol; they do not silently repair the original experiment.

A competence profile is a set of scoped measured claims indexed by relevant task and environment conditions. Avoid both a global fitness scalar and an exhaustively preallocated grid of every possible condition. Store observations and declared aggregates, then build views at justified resolutions. Sparse evidence stays sparse; a sophisticated table does not fill the gaps.

A release is a decision object naming eligible versions, applicability, limitations, fallback, evidence, policy version, and review or invalidation conditions. Candidate, experimental, limited, default, quarantined, and retired are dispositions with explicit admission rules. They do not constitute one universal quality ranking. A specialist can remain a permanent limited release without being defective.

The selector or router is itself a versioned capability. Its evidence includes cases where it should choose an incumbent or abstain. A portfolio of individually useful methods is not sufficient evidence that their combined selection policy is useful.

Evaluator packages may be revised, but protected reference tasks and admission procedures remain outside the evaluated candidate's unilateral control. Query access to a nominal holdout is tracked because repeated results can leak information. Equivalent evaluation protocols and cross-epoch comparisons are claims requiring evidence, not assumptions inferred from matching metric names.

## 9. Representation-level consistency checks

These are required inspection scenarios for a later implementation, not tests already run against software.

| Scenario | What this representation must make distinguishable |
|---|---|
| Same capability is run twice; first response is lost | One immutable version, two invocation identities, and the first invocation's unresolved exposure. |
| A new default is selected | New release selection; old invocations and evidence retain their subjects. |
| One of two independent support routes is invalidated | One failed derivation; the surviving route is checked against the same obligation. |
| A method migrates from software failures to mathematical objects | Shared behavior plus a different interpretation, witness predicate, and transfer claim. |
| A summary omits a critical counterexample | A defective derived view; the original evidence remains discoverable and its support effects remain active. |
| An unfinished investigation is resumed | Durable obligations and pending effects, not only a conversation summary. |
| A role bundle succeeds but component attribution is unclear | Evidence for the bundle; unresolved contribution claims for its members. |
| A candidate mutates an evaluator | A distinct evaluator candidate and protocol; no forged receipt or automatic transfer of old results. |
| A domain vocabulary changes meaning | A new interpretation version and explicit compatibility or migration obligations. |
| A withdrawn permission remains in a saved context | Historical context remains attributable; current dispatch is still refused under the new authority. |

## 10. Choices deliberately rejected

| Alternative | Why it is not the selected default | Where it remains useful |
|---|---|---|
| Everything is a document with embeddings | Does not itself distinguish current authority, evidence scope, pending effects, or invocable behavior. | Narrative, source retrieval, explanation, and small validated procedures. |
| Everything is one generic node and edge type | Moves all semantic constraints into conventions and makes invalidation ambiguous. | Shared identifiers, provenance envelopes, and derived graph views. |
| Everything is a custom DSL | Requires inventing a general programming environment before earning its cost. | Small composition algebra and domain languages with demonstrated benefit. |
| Everything is generated host code | Blurs cognitive behavior with enforcing control and makes safe introspection difficult. | Controlled executable modules behind the stable invocation boundary. |
| Every record is an immutable event and state is only replay | Couples ordinary access and recovery to complete historical interpretation. | A journal of consequential transitions with materialized current state. |
| One fixed ontology for the whole society | Prematurely constrains representational invention and hides incompatible interpretations. | A small stable vocabulary for shared authority, identity, evidence, and invocation. |
| Only a black-box archive of complete agents | Makes narrow reuse, interpretation transfer, and conditional composition harder to inspect. | Whole-system candidates when interaction effects dominate. |

## 11. What the next level must decide

R5 selects the carriers and contracts above. R6 must choose the smallest technology set that implements them under a declared host and failure model. The consequential questions are transactional state updates, artifact retention, controlled module execution, recovery, retrieval, and evaluation isolation. A graph-shaped semantic relation does not by itself justify a graph database; a composition algebra does not by itself justify a workflow product.

R7 must instantiate transition atomicity, operation protocols, schema constraints, interpreter boundaries, failure handling, and acceptance experiments. Those are substantive remaining decisions. This document is precise enough to constrain them, but is not a substitute for their specification or evidence that the resulting society improves autonomously.
