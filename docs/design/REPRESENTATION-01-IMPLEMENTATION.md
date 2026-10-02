# Representation 01: acquire an abstraction and test its transfer

2026-09-11. Stage 8.5, first buildable contract. Design selected; implementation and results pending. This refines [Representation and transfer](REPRESENTATION-AND-TRANSFER.md), uses the existing substrate, and is commissioned by [Cognitive batch 01](../HISTORY.md#worker-cognitive-batch-01). It does not depend on a favorable Agenda 01 result.

## 1. Architectural decision and precise scope

Make a retained representation an **executable interpretation with a separate reusable core**, an applicability claim and evidence about source outcomes. A later invocation supplies a source object through the interpretation, uses the core's operations, and checks the interpreted result against the original obligation. The runtime understands this boundary; it need not understand every invented internal vocabulary.

This permits a growing collection of incompatible, locally useful languages. Descriptions help select and understand them. Executable behavior, translation dependencies and evidence determine what can actually be reused. Existing artifacts, capabilities, context packets and releases carry these parts; no ontology service, universal DSL, graph database, new scheduler or new workflow engine is commissioned.

The first study asks: **can bounded construction from software reduction experience acquire an operational abstraction whose unchanged core is usable and useful with a new finite-mathematics interpretation?** We supply the task of witness-preserving reduction. Discovering that task or the connection between the domains is outside this study. Delta debugging is established prior work, not a new algorithm we claim to invent; see the [research addendum](COGNITIVE-RESEARCH-NOTES.md#representation-01-reference-check).

Keep the following verdicts separate:

| Verdict | Necessary evidence |
|---|---|
| Mechanics work | Authored fixture packages traverse real invocation, checking, persistence and later-use paths. |
| Acquired package | An admitted model construction consumes recorded development experience and produces the executed bytes. |
| Operational abstraction | Its encoding, operations and interpretation have a stated meaning, and observed behavior uses them. A renamed function alone is code reuse. |
| Unchanged-core transfer | The exact frozen core executes through a different domain interpretation; adaptation is confined to disclosed components. |
| Scoped use benefit | Complete source outcomes and costs improve against the specified strong comparators. |

Any earlier verdict can hold while a later one fails. Seeded synthesis cannot establish that the underlying idea was absent from model training. This small study cannot establish general mathematical discovery or autonomous curriculum formation.

## 2. Concrete source tasks and supplied structure

Select two finite source families, with independent trusted checkers. Inputs are data, never host-executed task programs.

**Software development family:** shrink sequences of operations on a tiny deterministic key/value state machine while preserving one designated disagreement between a reference interpreter and an explicitly faulty interpreter. Use at least two faulty behaviors: stale reads following an overwrite, and stale state surviving a clear. Include distracting operations and multiple keys. The original designated observation has a stable identity retained through deletion; preserve its typed value-disagreement condition. A parse error, invalid sequence, unrelated exception or disagreement at a different observation is not the designated witness. Do not claim preservation of an unknowable root cause: the preserved property is the specified observable disagreement.

**Mathematical transfer family:** shrink finite simple undirected graphs that are triangle-free and non-bipartite. Legal outputs are subgraphs of the original, preserving vertex identities. The witness is the conjunction of validity, absence of triangles and non-bipartiteness. Use different odd-cycle lengths, attached trees, disconnected distractors and multiple odd cycles. Keep this family invisible to source acquisition until its core and source development choices are frozen. Reducing a supplied counterexample is not discovering a new conjecture or proving a general theorem.

The source measure is sequence length for software and number of vertices plus edges for graphs. All accepted changes strictly decrease it. Inputs have at most 24 sequence operations or 10 vertices and 18 edges. Runtime checks validity, legal deletion/subgraph relation, measure and designated witness independently of the candidate. Initial valid inputs are incumbents; a failed proposal cannot destroy them.

Public instruments include source syntax, legal deletion rules, the witness specification, source-check query access and the baseline reducers. All arms receive the same instruments. Do not provide a minimal answer, a privileged structural decomposition or hidden expected output to C alone. Record an inventory of everything supplied versus constructed. The worker chooses exact interpreter bugs and generators within these semantics, documents them, and verifies them on small exhaustive instances before freezing evaluation. They are experiment fixtures, not production plugins.

## 3. One package boundary; no generated callbacks in the host

Use the existing immutable artifact envelope with an explicit named entry, package version, component digests, dependencies and invocation profile `representation-01`. The package contains a core and a domain adapter, plus their interpretation description. Source and transfer adapters have separate identities. An archive with the same core digest and a different adapter is a different composition.

The ABI is bounded JSON files: `python <entry> <request.json> <response.json>`. The following are semantic actions, not required services or tables:

| Action | Receives | Returns |
|---|---|---|
| Adapter `encode` | Source task and public domain specification | Encoded initial object, declared auxiliary material and applicability decision, or refusal. |
| Core `start` / `advance` | Encoded object, explicit prior core state, remaining limits and previous query feedback | One proposed encoded object and next state, a final encoded object, or refusal. |
| Adapter `decode` | Encoded proposal, original task and declared auxiliary material | Candidate source object, or refusal. |

The adapter is a translation, not a second search loop: each invocation starts afresh, has no oracle access, receives no search transcript or mutable private state, and cannot invoke the core. The core receives the encoded material and oracle feedback, not undeclared raw source files. Retaining the original inside the encoding is allowed if declared and charged; it weakens any claim that a smaller abstraction alone suffices. The adapter may perform substantial deterministic computation, whose costs count; unchanged-core identity by itself does not prove that the core supplies the intelligence.

Every generated entry executes through the existing Launcher/broker boundary. The host controller routes bytes and invokes a separately maintained source checker; it never imports, evaluates or calls generated Python as a callback. A core proposal is decoded and checked before the controller updates its best valid incumbent. Feedback has `preserved`, `not_preserved`, `invalid`, or `unknown`, a checked measure when available, and a bounded reason code. Timeout and checker failure are `unknown`, never evidence that the witness is absent. The final result is independently source-checked as well. Final checking is charged even if a cache can safely reuse identical verified bytes and dependencies.

Declared state and auxiliary bytes are bounded and persisted with their identities. Start and advance can be implemented by the same executable. Separate invocations make interpretation changes and restart behavior observable; do not build a generic RPC framework. The worker can select the concrete JSON schema and packaging layout once, before lanes branch. It must reject unknown versions, malformed responses, stale task/component identities and oversized material consistently.

## 4. What the existing implementation can and cannot supply

Reuse capability publication and version/dependency records, artifact storage, allocations, broker dispatch, evaluation binding, evidence and scoped routing. Existing `development.METHOD_ABI` and `experiment._invoke_method` specifically translate `broken.py` to `fixed.py`; they are not already this protocol. Add a named invocation profile/runner and preserve the existing repair profile. Never infer the entry from whichever Python file happens to appear first.

Use a study-specific admitted construction path that borrows existing lifecycle/context/model-dispatch primitives without pretending a repaired-source candidate is a representation. A small shared helper extracted at a demonstrated seam is acceptable; converting every development episode into a new general framework is not required. Persist parent experience references, candidate lineage, component identities and trial disposition through existing records where their meanings fit. Document any genuinely missing durable fields before adding a migration. No duplicate event log or second capability registry.

The study entry point is explicit admitted work under a finite allocation. Autonomous agenda selection is unnecessary for this experiment. It therefore can be developed while AGR2 is corrected. Generated executions and oracle checks still require actual operations and receipts; simulated success messages cannot substitute for them.

## 5. Construction, exposure and freeze sequence

1. **Apparatus development:** create authored package fixtures and source instruments. Prove that controls discriminate valid reduction, wrong witness and translation failure. Generate real execution experience with source-specific procedures. Authored candidates are labeled throughout and never reported as model inventions.
2. **Source acquisition:** A develops textual lessons; B can additionally construct source-specific procedures; C can additionally propose a shared core/representation and its software adapter. Provide the same source experience and instrument inventory, with arm-specific retention rules below. Preserve all attempts, refusals and costs. At most two candidate versions per arm may be considered; no unrecorded manual repair of generated code.
3. **Source freeze:** choose each arm's retained material using development/check data only. Freeze core, source adapter, procedures, text, selector and prompts. No transfer-domain data has entered source acquisition.
4. **Transfer development:** reveal the graph specification and its development examples equally to all arms. A may revise text; B may construct a graph-specific procedure; C may construct a graph adapter. C's shared core cannot change. At most two transfer versions per arm, selected on transfer check data. A changed core is a separate adaptation result and does not enter the unchanged-core comparison.
5. **Final freeze:** bind every arm composition and resource policy before held-out inputs are delivered. Generation seeds, source/checker code, split identities and candidate identities are in a content-verified manifest. Candidate contexts cannot inspect held-out data or aggregate results during selection. A future doc-only commit must not change the identity of the frozen executable experiment.
6. **Evaluation and disposition:** evaluate all assigned cases, including failures, then conduct fresh-process use according to the resulting disposition. Do not revise candidates or the panel after observing scores. A corrected apparatus creates a new preserved epoch if the correction affects interpretation.

The worker implements the split barrier and records actual delivered bytes, not merely filenames labeled held-out. Hold out generator templates/structural patterns as well as seeds within these small families, document overlap, and call the result finite-family transfer rather than broad out-of-distribution generalization.

## 6. Strong comparators and treatment attribution

| Arm | Available retention and selector |
|---|---|
| A | Base tools, a tested ddmin-style deletion reducer and a simple domain-aware greedy reducer, plus strong textual development lessons. Select its reducer on development data. |
| B | A plus acquired task-specific procedures. Freeze a selector using development data. Source procedures remain available during transfer; a graph-specific procedure has the same transfer-development allowance as C's adapter. |
| C | B plus acquired representation/core and the relevant adapter. On declared supported cases, attempt that composition; on refusal use the same frozen A fallback. Both attempts and fallback count. Outside its scope, use the incumbent directly. |

All reducers use the same legal source operations, oracle feedback and per-task allowances. Baselines get ordinary native implementations; do not force them through artificial translation work to equalize C's overhead. That overhead is part of C's real cost. A/B text is preserved and accessible, but the scored first pilot uses executable reducers without per-task model calls. Therefore this isolates executable retention and transfer; it does not establish superiority over an unrestricted prompting agent. A matched live per-task solver comparison is a later study if this slice earns it.

For C, report actual core/adapter invocations, every retained source improvement and fallback fraction. On development/check cases run a **core substitution control**: use the same adapter with a simple bounded proposal strategy where the declared encoding supports one. If no meaningful compatible strategy exists, report attribution unresolved rather than substituting an invalid program. Also run the direct source reducer bypassing the encoding. If the adapter alone effectively computes the answer, classify that contribution explicitly; packaging it behind an unchanged core is not evidence that the core learned a transferable search principle.

Do not add a contrived weak baseline to manufacture a release. Reduction is a well-understood task; A may win. The useful architectural outcome can be discovering that executable representation acquisition offers no advantage at this scope.

## 7. Finite pilot panel, budgets and decision rule

The first panel is deliberately small. It selects a next experiment, not a statistical claim about general intelligence.

| Split | Software | Graph transfer |
|---|---|---|
| Development | 6 tasks, both fault behaviors represented | 6 tasks spanning the graph constructions |
| Candidate check | 4 disjoint tasks | 4 disjoint tasks |
| Frozen evaluation | 8 supported tasks | 8 supported tasks |

Add four frozen scope/validity controls outside the 16 benefit cases: wrong designated observation, invalid sequence, graph with a triangle, and a bipartite graph. All 20 inputs are assigned to A/B/C: 60 complete arm-task records. Put paired insufficient-encoding and core-substitution controls in the development apparatus, not hidden benefit totals. Maintain a separate mixed subsequent-use panel with one supported source case, one supported transfer case and two outside-scope cases, generated from distinct fixed seeds.

Each benefit task permits at most 16 candidate witness queries, 64 generated-component invocations, 120 seconds elapsed time, 2 seconds per component/check invocation and 64 KiB per request, response or persisted core state. Initial/final source checks are additionally permitted and counted; they cannot be used as unbounded search. All proposal attempts count, including invalid or duplicate proposals; exact delivery retries reuse the same durable step identity. Fallback shares the remaining task budget. Remaining global allocation can terminate work earlier. Do not claim local irreducibility if the declared neighborhood was not exhausted; report `budget_exhausted` with the best verified incumbent instead.

Before live construction, freeze model/provider settings and a concrete grant-backed maximum exposure using the existing accounting units. Upper bounds: 12 model calls for the entire acquisition/transfer campaign, at most 16,384 input tokens and 8,192 output tokens per call, no automatic retries beyond those calls. Allocate equal call/token opportunities per arm (up to two source and two transfer calls); unused capacity is not transferred to C. If no model supports the selected limits, record a preflight amendment before any campaign response, within the available grant. Discovery/connection probes count against their separately recorded finite preflight allocation. Missing credentials, funds, or a suitable execution environment block the live phase only.

This is a cap, not a requirement to spend. A source candidate failure may terminate that arm and retain its incumbent; do not invent a candidate to fill the panel. Decode or constructor protocol failures consume their actual budget. Generated scripts require the selected execution profile; retain explicit labeling and the established restrictions for any disposable uncontained environment. Do not broaden execution authority as a side effect of this packet.

Measure each valid-input task by `u = (initial_measure - best_verified_measure) / initial_measure`; the unchanged input has zero improvement. Score invalid source outputs as zero improvement and record the validity violation separately. A crash/refusal/timeout with only the original valid incumbent scores zero; if a previously checked smaller incumbent survived, it retains its measured improvement with the failure status recorded. Scope controls are judged separately by correct refusal/routing. Report every case, not just means or successful candidates.

The preregistered **promising-pilot** rule is: no invalid delivered result or incorrect control handling; C's transfer mean improvement exceeds both A and B by at least 0.10; C's software mean trails neither by more than 0.05; and its measured execution CPU, elapsed time, oracle queries, model tokens and accounted exposure are each at most 1.25 times each comparator's total over the same 16 benefit tasks (a zero denominator requires C also zero). A secondary efficiency outcome requires identical per-task improvements and no greater resource component, with at least one strict reduction, against both comparators. Report uncertainty of wall-time comparisons rather than treating small timing differences as dependable savings. These thresholds are conservative pilot choices, not optimal constants or significance tests.

Always report acquisition costs separately and acquisition-inclusive totals at reuse horizons 1, 10 and 100 repeats of this exact finite panel, as explicitly hypothetical projections. Shared source experience counts once per standalone arm deployment; B includes A's inherited costs and C includes B's plus its own. Also report the experiment's physical operation union once, without double-counting shared operations. Cheap invocation alone cannot establish that acquisition pays back. A promising pilot warrants a broader frozen trial; it does not itself authorize a general learned capability release.

## 8. Fidelity and continuity acceptance

The worker owns meaningful checks at these seams, not an exhaustive audit of unrelated modules:

- A smaller source object with the wrong software witness, an invalid graph, or a nondecreasing measure is rejected by the independent source checker.
- Two inputs conflated by an insufficient encoding but requiring different witness decisions expose that limitation. Declared auxiliary data may resolve it; undeclared access may not.
- Changing adapter/core/checker bytes invalidates the relevant composition or evidence binding. Core equality in transfer is derived from actual staged bytes, not a label.
- The source/checker task relation is checked independently; a candidate cannot replace the task, initial measure, witness identity or oracle implementation.
- A fresh process resumes after a prepared query and after a receipt but before the next core state is committed, without rerunning settled effects or losing an accepted incumbent. Preserve a database sentinel; replaying from a newly created database is not resume.
- A strict result checker rejects missing/duplicate arm-task records, incomplete outcomes, modified manifests, unbound invocation records and omitted cost/liability records. CLI replays from committed inputs and manifests, not a scratch-only driver.
- Future use loads exact retained artifacts, verifies dependencies/scope and shows selected composition or incumbent with a reason. An unreleased trial candidate stays trial-only. If no representation earns release, prove persistent rejection/fallback; mark real released-representation use unexercised. Authored positive fixtures may exercise that route, with fixture provenance explicit and no fabricated evaluator scores.

The small-domain checker needs an independently written reference for exhaustive cross-checking: graph BFS coloring against exhaustive two-color assignments on graphs up to five vertices; triangle detection against explicit triples; finite interpreter cases against a separately written transition table. Do not test a checker by calling the same implementation twice. Enumerate bounded small cases, not all graphs in the evaluation size range.

## 9. Deliverables, ownership and stop rule

Requirements: RPR-01 source instruments and bounded corpus; RPR-02 package/profile and interpretation boundary; RPR-03 admitted acquisition, context and lineage; RPR-04 freeze/splits/comparators; RPR-05 real execution, independent checking and costs; RPR-06 unchanged-core transfer; RPR-07 restart and subsequent use; RPR-08 complete evidence and disposition. Map each to implementation paths and behavioral evidence in `reports/REPRESENTATION-01.md`.

Deliver one reproducible entry command, a committed manifest/checker, deterministic authored-fixture evidence, the bounded live campaign when its actual prerequisites are available, and a concise operator view of the composition, source witness, next action, budget, result and disposition using the existing UI. A separate management application is unnecessary. Preserve transcripts/artifacts as repository-safe evidence with credentials excluded. Store large raw artifacts through the existing artifact mechanism and commit enough identity/manifests and retained inputs to reproduce or inspect the claimed result.

Do not expand the batch into autonomous domain discovery, representation composition search, learned wake/sleep policy, temporary teams, learner self-revision, production deployment or a new stack. Stop after an interpretable positive, negative, inconclusive or externally blocked live result. Where results expose a deeper architectural problem, preserve a small discriminating example and report the decision needed; do not begin an unlimited redesign.
