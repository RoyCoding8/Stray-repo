# Investigation 01: a usable, persistent development loop

Selected next architectural batch, 2026-09-19, based on [84d2094 assessment](../../reviews/EC02-AD01-84D2094-ASSESSMENT.md) and the [accepted direction](ARCHITECTURAL-DIRECTION-2026-09-17.md). This is a new implementation/qualification slice. It does not rename incomplete AD01 evidence into a pass or authorize further historical retries.

## Purpose and choice

Build one operational investigation loop in which a model can understand the available work, choose an experiment, consume the actual result, construct a usable method, retain or reject it, and continue after a restart. The same loop serves software and graph investigations through explicit domain interfaces. These remain proxy domains for the original general autonomy goal, not the product's permanent limits.

Three alternatives were considered. More bespoke prompt repairs preserve duplicated state and information transformations. A wholesale rewrite discards useful execution/evidence machinery without evidence that it is the obstacle. Select substantial consolidation of the cognitive path over existing execution guarantees. Replace experiment-specific orchestration where it duplicates this protocol; preserve historical executables/evidence when reproduction depends on them. No new database, agent hierarchy or generic workflow language is required.

The central hypothesis is that faithful, executable interfaces and feedback make autonomous development observable and useful. The current evidence does not justify ranking provider capability above those deficiencies. Replay-assisted policy development remains the next conditional extension, not a substitute for working live behavior.

## Objects and ownership

Use existing records and immutable artifacts. These are semantic contracts, not a mandate for five new classes or tables.

| Object | Required content and owner |
|---|---|
| Investigation state | Objective, visible opportunities, observations, unresolved questions, repertoire, accepted/pending actions, policy versions and remaining authority. Existing investigation/journal state is authoritative. |
| Instrument/method contract | Version, request and result shapes, semantic meaning, public task representation, legal effects, failure outcomes and bounds. The adapter owns execution and validation; prompt rendering derives from the same contract. |
| Decision packet | Concrete permitted state and contract content needed by this decision; source/configuration identities, missing information and reference handles. Reuse context materialization; no reference-only substitute for content. |
| Proposed action | Target, action/instrument, inputs and dependencies, requested resources, optional hypothesis and expected distinguishing observation. The model proposes; runtime admission controls effects. |
| Experience transition | Decision packet, exact proposal, admission/refusal, operations, results, visibility and measured/unknown costs. Existing operation/evidence records remain authoritative; replay indexes are derived. |

The shared loop performs: materialize -> propose -> admit -> execute/reconcile -> incorporate -> continue or stop. This is a control boundary, not a compulsory six-call reasoning script. A routine action need not invent an elaborate hypothesis. Diagnostic, construction and method-use results all return through the same observation path; a malformed action is an attributed result eligible for bounded correction, not silent advancement to another curriculum item.

Persist acceptance before effects. Resume the same logical action and reuse settled results. A deliberately new retry has a distinct attempt under the same study root and remaining allowance. Changing a database, task tag or policy version cannot renew authority.

## Make the model-facing environment usable

For software, supply the public operation representation, candidate shape, preservation objective and oracle result meaning. For graphs, supply nodes/edges and the relevant witness condition. Include actual permitted examples and diagnostics, not task identifiers alone. Give helper signatures and return shapes if helpers are offered. Keep protected evaluation outcomes inaccessible.

The contract renderer, parser and executor must agree on entry selection, arguments, output shape and profile restrictions. Use transport examples that demonstrate the interface without supplying the experiment's solution strategy. Mechanically test these examples against the validator. Do not force a model to infer undocumented constraints from repeated failures.

Feed the diagnostic just produced into the next construction/decision packet, including distinguishing content. Deliver per-candidate repair failures verbatim in structured form. Preserve transport errors, missing settlements, schema failures, execution failures and rejected scientific hypotheses as different outcomes. Retry policy and reasoning/output limits are explicit effective configuration. Do not classify all empty results as provider faults or all rejected programs as lack of model capability.

Permit substantive bounded programs beyond selecting an authored method. Programs can use model/tool operations through existing mediated interfaces when their profile allows them. Keep the outer action/effect vocabulary stable for this slice; new domain instruments can extend it by versioned contracts. Candidate code stays outside the trusted process. Process separation and hostile containment retain distinct qualification labels.

## One resource and experience path

Read remaining resources after every effect, including diagnostics and failed validations. Construction and use consume their admitted shares of the same study authority. Derive reporting from operation identities and measured counters; caller-supplied totals are not proof. Do not substitute output-token caps or a character estimate for known input usage. Unknown exposure remains visible and reserved/refused according to existing rules.

A study export has a unique run identity across databases, source and effective configuration, model/protocol/profile identities, packet/artifact digests, phase boundaries, attempted operations, receipts and unresolved liabilities. Export sufficient permitted raw content to diagnose model-interface failures, excluding credentials and protected material. Historical records lacking these fields remain qualified; do not fabricate them retrospectively.

Use existing broker/store, context, capabilities and artifact machinery. `experiments/ad01/trajectory.py`, `construct.py`, `learner.py` and `method_exec.py` supply migration inputs, not a second permanent runtime. Experiment modules should select worlds, treatment policies and judges and export results. They should not independently implement grants, learner loops or accounting. Reuse coordination's child execution where applicable; do not force all tasks into a team plan.

## Decision policies and replay boundary

Expose the next-decision policy as a versioned replaceable behavior over the same packet/action contract. Provide a fixed baseline and the model policy. I/R qualification differs only in who selects the curriculum opportunity; both use the same remaining pipeline and comparable initial resources. Qualify replacement and restart structurally without claiming that a better learner was acquired.

Record transitions so they can support later policy evaluation. For this batch, provide offline replay of recorded transitions and explicit unsupported decisions. Replay must enforce the information available at the recorded prefix. A matching task ID is insufficient: dependencies, artifact/model/environment versions, action arguments and relevant prior observations must match the declared replay conditions. Reordering dependent actions, introducing new code, or changing available context may invalidate replay. Stop that simulated branch as unsupported; do not borrow an unrelated outcome, charge it as live, or score unknown as failure/zero.

Do not yet build predictive worlds or a large replay-optimization campaign. This first trace format and checker should answer whether the corpus has enough supported, behaviorally different choices to justify that next study. Dream-RSI motivates that later use, while the current constructor failures show why replay alone cannot repair missing interface semantics.

## Qualification and informative stopping

1. Exercise the public entry with doubles only at provider seams. The learner must be called and its costs included; no direct proposal callback substitutes for integrated qualification. Include substantive acquired methods, no-candidate/incumbent use, stop, correction, cross-split refusal and domain differences.
2. Alter a diagnostic result while holding the preceding state fixed; follow it into the next request and actual selected work. Alter only irrelevant labels as a control. Test runtime behavior, not merely packet inequality.
3. Kill after diagnostic completion and after candidate validation. A fresh process resumes the same observations, versions, resource envelope and pending actions without duplicate calls. Freeze and use exact retained bytes in another process. An empty repertoire still executes the declared incumbent-use phase.
4. Independently test resource exhaustion between diagnostic and construction, failed validation after queries, shared costs and multiple retry attempts. Capture remaining authority before and after each effect. No host candidate execution or unreported profile fallback.
5. Check trace replay, hidden-future refusal, artifact/version mismatch and unsupported alternative decisions. This proves replay boundaries, not policy improvement.
6. Under separately valid authority, run one complete live calibration investigation per domain and fresh-process use. Then use two fresh worlds, each with three visible development tasks per domain and six protected use tasks: two within-scope and one structural-transfer task per domain. Run I and R in each world, producing four development trajectories and 24 final use records. Use separate calibration tasks. Freeze manifests and policies after calibration, before protected exposure; do not select new seeds based on their results. Baseline-only use and no improvement are acceptable. If transport or missing semantics block the intended comparison, report that narrower outcome instead of a learning verdict.

For this engineering pilot, each of the two calibration and four comparison trajectories has at most six decision boundaries, three development episodes, two candidate lineages with one initial and at most one repair call each, and 60 total model calls including diagnosis/context/use calls. Thus at most 24 construction calls and 360 total model calls across the six trajectories, not an instruction or authorization to spend them. Set concrete aggregate input/output-token, witness-query, execution-time and wall-time ceilings from the implemented request/profile bounds before requesting the new grant. Do not inherit AD01's spent allocation, reset counts on retries, or expand a limit after observing protected results. These limits are experimental controls, not permanent architectural restrictions.

The live pilot is an engineering qualification, not a statistically established benefit claim. Do not require a positive learning result to finish. Finish when the connected behavior is qualified at its actual scope and the report identifies the next discriminating bottleneck. Only then choose between replay-assisted policy improvement, candidate construction, better context, domain instruments or another intervention. No endless unbudgeted retries for a success story.
