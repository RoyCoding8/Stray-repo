# Agenda 01: durable investigation choice and a rejecting experiment

Status: selected implementation contract, based on `913bda791bd0fb3cf87c568fb57daea17fe4a240`. No Agenda 01 implementation or scored result exists yet. The [worker assignment](../HISTORY.md#worker-agenda-01) commissions this slice. Read the [policy](AUTONOMOUS-AGENDA.md) and [experiment protocol](AGENDA-EXPERIMENT-01.md) for the underlying semantics. This document resolves their implementation boundary; it does not replace their controls or interpretation limits.

## 1. What this slice should establish

Build a persistent agenda that can propose a finite investigation, admit an exact revision, observe its result, justify or decline another attempt, become dormant, and resume after a relevant event in a fresh process. Then measure whether the specified continuation qualification helps under a fixed exploration budget.

The experimental intervention is the continuation rule. It is not a new model, memory database, execution engine, multi-agent organization or unrestricted autonomous service. A correct negative result completes this assignment. No live gateway, generated code, acquired-method release, real containment or GPU is required for this deterministic study.

Use the existing Python/PostgreSQL runtime and broker. This is demanding bounded engineering with an experimental design component: the worker chooses concrete tables, signatures and fixtures within these contracts. It must freeze those choices before scoring, and may challenge a contradiction with evidence rather than silently alter a requirement.

## 2. Reconcile with the actual runtime

| Existing mechanism at the base | Use in Agenda 01 | Missing semantics to supply |
|---|---|---|
| `agenda.propose_frontier` and `renew_proposal` return dictionaries; renewal currently accepts changed prose | Preserve compatibility where useful | Durable immutable option revisions and evidence-qualified continuation. A nonempty `changed` string is not qualification. |
| `investigations` and `investigation_revisions`; `steward.admit_commitment` | Existing admitted objective, obligations and revision anchor | An unadmitted option must not become a commitment simply by being proposed. Link to an existing investigation or a proposed objective identity, then bind admission explicitly. |
| `store.transact`, command journal, event/outbox machinery | Idempotent commands, bounded transactions, durable transitions | Expected option/disposition versions, immutable input identity and selection cursor. Never nest public transaction-opening calls under the locked control row. |
| `steward.admit_task` / `store.acquire_work` | Attempt ownership, investigation revision and occupancy | Acquisition currently does not reserve an operation's spending exposure. Do not report an attempt as fully funded merely because acquisition succeeded. |
| `store.prepare_operation`, reservations and broker dispatch | Prepare/reserve actual effects and retain existing final dispatch checks | Exact option-to-attempt-to-operation binding and an admission fence for the selected revision. |
| Allocation hierarchy and protected supervision scope | Finite exploration authority and separately recorded recovery capacity | Durable lineage attribution; retries, branches and wakeups must not seed fresh grants. |
| Evidence/artifacts, receipt reconciliation and epoch validation | Byte-bound result references, support/opposition, stale evidence refusal | Link outcomes to their actual attempts, scopes and dependencies. A simulated observation is labeled simulated evidence. |
| `agenda.seed_order` | Common class rotation where compatible | Explicit opposite tie permutations and a persisted cursor; document the experimental adapter if production ordering differs. |
| `agenda.collect_wakeups`, repair scan | Existing event cursor and mechanical recovery | Typed option wake matching and duplicate/out-of-order delivery handling. Scanning does not buy inference or mint authority. |
| Context packets currently constrain decision kinds to diagnose/construct/resume | Continue using them for their existing purpose | The deterministic agenda needs a persisted, digested structured decision input. Do not mislabel it a model invocation or add a new model packet kind solely for this study. |
| Operator overview and existing read API | Inspect agenda state and actual execution together | Visible eligibility reasons, continuation basis, wake condition, costs and outstanding liability. |

Select a small PostgreSQL extension for option revisions, current disposition/version, attempt links and decision records. Versioned JSONB bodies with explicit indexed identities are permissible; one table per conceptual noun is not required. Do not encode `open/dormant/answered/retired` in the existing investigation disposition column: these are different state machines. SQL constraints, immutable records and the journal should enforce identities without introducing a second event store.

Record the exact table and transaction mapping before delegation. For atomic preparation, extract shared transaction-local logic if necessary; keep public entry points compatible. A staged implementation is also acceptable only if every intermediate state is durable, cannot dispatch prematurely, and has a proven resume/refusal path. A crash between acquisition and preparation must neither strand occupancy indefinitely nor permit an unbound operation to dispatch.

## 3. Required behavior

| ID | Contract | Observable acceptance |
|---|---|---|
| AG01-01 | An option has immutable revisions, stable request identity, scope, lineage, objective/investigation link, evidence/opposition, alternatives, probe/outcome contract, decision consequences, dependencies, cap, expiry and exposure. | Same command replays one logical result; changed payload under the same request conflicts. A stale expected version refuses without admitting work. |
| AG01-02 | Disposition is independent of execution. Eligibility is derived from current authority, dependencies, evidence, pending effects and capacity. | An open option can be blocked. Dormancy/retirement does not complete a pending operation, refund exposure or erase ownership. Answering an agenda question does not fulfill an investigation without its existing witnesses. |
| AG01-03 | Selection records the policy version, exact input digest, option revision, ordering/cursor and reasons; admission rechecks current state and binds funded work. | Concurrent selectors cannot create two effects for the same intended probe slot. Revocation or revision change between selection and admission refuses. Existing pre-send fencing remains effective. |
| AG01-04 | Outcomes cite actual durable receipts/evidence and preserve uncertainty, opposition and dependency scope. | Wrong-attempt, missing, tampered, invalidated or future-epoch support cannot justify continuation. An unresolved result remains unknown. |
| AG01-05 | R and Q share candidate generation, observation access, parser, rotation and all mechanical safety rules. Only Q applies the additional continuation qualification. | Same structured input yields an inspectable decision; policy code has no access to latent world state, future events, grader answers or policy-specific privileged fields. |
| AG01-06 | Continuations link a parent attempt, its observations, residual decision, next probe, finite request, stop condition and any frozen replication obligation. | Paraphrasing, a new ID or attaching an irrelevant true observation does not qualify Q. A meaningful small observation, applicable counterexample or remaining finite replication can qualify. False-negative stopping is measured. |
| AG01-07 | Options share finite allocation roots and preserve lineage/exposure. Exact duplicate identity is structured; semantic equivalence is not guessed from prose. | Branches and repeated wakeups cannot reset the cap. Distinct scopes remain distinct. Legitimate repetition has a named replication slot; it does not masquerade as a duplicate retry. Totals union operation identities across shared ancestry. |
| AG01-08 | Dormancy records a typed prerequisite/evidence/version/authorized-scan wake condition. Wake processing rechecks state. | Duplicate, stale and out-of-order events do not revive retired work or create duplicate effects. A relevant later event can reopen a dormant question with a recorded reason and current eligibility. |
| AG01-09 | Decision cursor, disposition, observations, outstanding work and resource records survive process exit. | Terminate and resume in a separate process after selection/preparation, pending outcome and dormant event delivery. Preserve the same logical effects and accounting as uninterrupted execution. |
| AG01-10 | The frozen authored study implements the existing 32 worlds, two tie orders, R/Q pair, 24 ticks, 64 exploration units and eight end-use tasks per trajectory. | All 128 trajectories run through the implemented agenda commands and durable records. The scored path cannot be a disconnected in-memory policy demonstration. |
| AG01-11 | Reports derive from preserved traces, actual operation/reservation records and independent grader outputs. | A separate checker reconstructs pair/family totals, cost unions and liabilities; it rejects altered/missing/duplicate records. Scored failures remain visible. |
| AG01-12 | A visible CLI path and existing operator interface explain the agenda without reading SQL. | Demonstrate propose → admit → observe → continue/decline → dormant → wake → fresh-process resume, with both a useful continuation and a justified refusal. |

Stable request replay and intended-effect deduplication are separate. The latter includes portfolio/lineage scope, question identity, evidence/dependency versions, probe, intended decision and optional replication slot. Cosmetic option IDs are not a way around it. Freeze the exact canonicalization, including what remains deliberately distinct.

## 4. Make Q testable without giving it an oracle

Implement a small explicit observation vocabulary and a deterministic qualification function over the same public input R receives. Scope propositions and alternatives by dependency versions. Preserve conflicting and unknown observations. Do not infer truth from the presence of a reference alone.

Q may justify continuation through one of these supported routes:

1. A cited observation changes the applicable alternatives or decision conditions and the next probe addresses the residual question.
2. The proposed probe has at least two still-possible observable outcomes with different declared decision consequences, and the current evidence does not already settle that distinction.
3. A finite replication protocol, declared before its first sample, has a remaining sample obligation and has not reached its frozen stopping condition.

These are fallible rules for a limited language, not a general theorem of scientific value. Mere passage of time, unrelated novelty and renamed alternatives are insufficient. A changed dependency can invalidate an old negative result, but does not itself guarantee the new probe is worthwhile. Prerequisite acquisition can be a probe; charge it and evaluate its stated consequence as such.

The implementer must publish the actual rules and examples before scoring. The world may expose measurement specifications as shared domain knowledge; it may not expose fields such as `informative`, `good_action`, `expected_score_gain` or the true hidden hypothesis to either policy. Proposed consequences are predictions, not trusted world labels. Both policies apply the same interpretation of observations; qualification is the only treatment difference. Apply Q to continuations, not selectively to initial options, unless a separately versioned study explicitly changes that intervention.

Use development fixtures to test an irrelevant observation, settled distinction, consequential weak signal, negative observation in scope, stale negative observation, remaining replication and exhausted replication. The reviewer independently checks data flow and the possibility of Q losing. Authored worlds can embody author assumptions even when code separation is correct; report that limitation.

## 5. Experiment execution and accounting details

The [existing protocol](AGENDA-EXPERIMENT-01.md) controls the scenario families and merit criterion. Complete its executable manifest before scored runs. Include full source revision, fixture/generator/checker digests, world parameters, public versus privileged fields, proposal generation, event ordering, tie permutations, policy versions, observation grammar, grading rules, budgets and analysis. Hash the resolved manifest and reference it from every trace. Validation may inspect fixtures; scoring must not precede the committed freeze.

Freeze a deterministic order within each tick: due external events and available receipts, wake/eligibility processing, then at most one paid policy decision and its possible discretionary admission. Specify zero-delay receipt handling and tie ordering explicitly. One unit is charged once per decision, including idle; retrying the same committed decision is not another tick or free new work. Read-only explanation and UI refresh do not advance the cursor. End at 24 ticks or inability to fund another decision. An affordable decision with no affordable probe may idle. Reserve the entire chosen 2/4/8-unit probe exposure before launch.

The study's probe prices are declared simulation costs, not estimates of measured compute. Use the existing allocation/reservation/settlement machinery to record them and decision costs, with distinct operation identities or a justified existing accounting command. Do not invent provider bills or label an accounting-only decision record as model inference. Report actual runtime overhead separately; charging each policy one abstract decision unit does not prove equal real computational cost.

Each trajectory starts with independently initialized authority and state. Both arms have the same exogenous world and proposal-generation rule, but later proposals depending on discoveries may differ because their observations differ. No cross-arm discovery sharing. Namespace all mutable state, artifacts, operations and DBOS execution. A shared database is permissible only with proven complete isolation; separate databases are the simpler default for this bounded run.

Keep the evaluation and protected recovery budgets finite, separate, frozen and unavailable to exploration. Specify their numerical caps and cost models in the manifest. After the exploration horizon, reconcile pre-existing effects under the declared recovery budget; never launch another exploratory probe. Freeze the end-use evidence cut at the horizon: information first received during the drain is reported but cannot improve the eight scored tasks. If recovery cannot resolve liability within its declared bound, retain and report it; this is not a refund or a silently successful trajectory.

End-use answers must be constructed from that trajectory's available observations and permitted simulated products; latent world answers are accessible only to the grader. Use domain facts and applicability checks, not a score bonus for choosing Q-like actions. Simulated reusable products are world-state effects, explicitly labeled; they do not create production capability releases. Publish equal end-use solver rules and costs for both arms. Include a deliberately wrong-answer control and positive controls for both policies.

Record all scored trajectories, errors, incomplete runs and exclusions. An apparatus defect that invalidates interpretation requires a new manifest/version and a complete rerun, preserving the earlier result. Do not selectively retry losing pairs, tune Q after looking at scored outcomes, or treat a negative benefit result as an implementation bug. Fault-injection acceptance runs are separate from benefit scoring.

## 6. Acceptance and stopping

First pass the mechanical gates with real PostgreSQL and real fresh processes at the durable seams. Use deterministic adapter doubles for world observations; document them precisely. Test adverse interleavings and emitted effects, not only helper return values. If a shorter pure policy runner helps debugging, prove agreement with the durable path; use the durable path for the reported 128 trajectories.

Then freeze and execute the comparison. Publish every paired difference, family totals, both tie orders, costs, waiting/idle time and unresolved liabilities. Distinguish mechanically feasible waiting from Q-qualified waiting so rejected work cannot disappear from a starvation measure. Apply the original merit criterion unchanged: aggregate primary improvement with no family-total regression, or every pair's primary result tied with lower total measured resources, with all mechanical gates passed. Report the resource vector and avoid offsetting unlike resources into an invented score.

Assignment completion means the mechanism is built, its invariants have appropriate evidence, and the frozen experiment has an interpretable result. It does not require Q to win. A regression can support retaining R and revising qualification before a live study. A blocked mechanical gate means the experiment cannot yet be interpreted. Live agenda semantics, general discovery, representation invention, adaptive teams and learner revision remain later work.

Deliver the exact integrated revision, affected checks and full-suite result, requirement-to-evidence map, manifest, bounded traces, independent summary checker, operator/CLI demonstration and limitations. Keep evidence necessary to reproduce the conclusion before deleting scratch databases. No further audit cycle is required for stale historical prose: reconcile the existing report index while integrating this slice, preserving historical evidence.
