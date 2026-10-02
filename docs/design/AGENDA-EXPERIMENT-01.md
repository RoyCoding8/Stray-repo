# Agenda experiment 01: representation and falsifiable protocol

Status: protocol selected for the [Agenda 01 implementation assignment](../../WORKER-AGENDA-01.md), not implemented or executed. This refines stage 8.4 of the [roadmap](REFINEMENT-ROADMAP.md) and the policy in [Autonomous agenda](AUTONOMOUS-AGENDA.md). Its executable fixtures and manifest must be frozen before any scored comparison. The [implementation contract](AGENDA-01-IMPLEMENTATION.md) maps these records onto the audited runtime and supplies execution/accounting details.

The question is narrow: **does requiring an evidence-based reason to continue an investigation improve use of a finite exploration budget, compared with transparent rotation over feasible proposals?** We are testing a decision policy, not whether more records or a busier swarm look intelligent.

## 1. Separate three decisions

1. **Permitted:** existing authority, capacity, evidence-access and effect-reconciliation rules allow this operation. Both policies must satisfy these rules.
2. **Worth attempting now:** the agenda chooses among permitted opportunities, using only available observations and its declared policy.
3. **Worth retaining:** the existing evaluation/release machinery decides whether a proposed change earns future use. Scheduling an experiment does not release its output.

An option is a proposal, an attempt is admitted execution, and a retained method is a separately evaluated product. Keep these identities separate. In particular, an attractive proposal must not allocate itself resources, and an apparently useful observation must not become a method merely by being stored.

## 2. Minimum durable representation

Reuse existing investigations, allocations, evidence/artifacts, packets and operation/episode records. The following is a semantic record shape, not a demand for a new table for every noun or a new scheduling service. The implementation design must map each field to an existing store or justify the small missing extension.

| Record | Required information | Why it exists |
|---|---|---|
| Option revision | Option/investigation identity; immutable revision; lineage and allocation-root references; question and scope; evidence and opposition references; alternative explanations; proposed probe and observable outcomes; proposed decision consequences; prerequisites; requested finite cap; expiry; exposure references | Describes exactly which experiment is proposed and what could make it useful. |
| Disposition event | Option revision; prior disposition/version; new disposition; evidence references; reason; optional typed wake condition; deciding policy/input identity | Preserves why work was selected, blocked, put dormant, answered or retired. |
| Attempt link | Option revision; admission/operation/episode references; input packet and policy versions; resource allocation; execution status and outcome references | Connects proposal to actual authorized work without copying the broker's execution state machine. |
| Continuation record | Parent attempt and actual result references; previous decision; observed change or predeclared replication obligation; residual question; next probe; requested cap; stop condition | Supplies inspectable grounds for a new admission. It is a proposal to continue, not an authority token. |
| Experiment manifest | Source/configuration identities; policy versions; world/task identities and exposure rules; tie order; budgets; metrics; stopping/analysis rules | Makes the comparison replayable and fixes what its result can mean. |

Avoid a single status enum mixing cognition and execution. An option may be `open`, `dormant`, `answered` or `retired`; a linked attempt has the existing execution statuses, including unresolved effects. An open option can be temporarily blocked by missing authority or prerequisites. Eligibility is a derived, explainable result evaluated against current versions and capacity, not a permanent Boolean column.

A wake condition is initially one of a few typed predicates: a named prerequisite version becomes available, a relevant evidence dependency changes, or a pre-authorized scan is due. Do not execute arbitrary model-written predicates in the trusted scheduler. Timers schedule bounded inspection; they do not replenish spending authority.

Use exact structured identity to suppress duplicate requests: investigation/scope, referenced evidence versions, probe identity and intended decision. Similar prose is insufficient to merge hypotheses. Uncertain equivalence remains explicit. Branches inherit relevant exposure and allocation roots; renaming a question or creating another option never creates a new root grant. For multiple-parent work, account shared ancestors once in portfolio totals and retain attribution rather than summing the same charge along every ancestry path.

## 3. Semantic command boundary

The first interface needs only these operations; names here describe behavior, not final function signatures:

- Propose a revision with its expected current version and stable request identity.
- Explain eligibility using current authority, dependencies, unresolved attempts and capacity.
- Select and admit one exact revision under a named policy and input snapshot.
- Record an attempt outcome by linking validated durable evidence.
- Submit continuation, dormancy, answer or retirement against the expected disposition version.
- Reconsider dormant options when a matching wake event or admitted scan occurs.

Duplicate commands return the same logical result. Concurrent disposition changes use existing transactional version/fencing mechanisms. Selection is advisory until admission atomically rechecks the relevant versions and reserves resources through existing authority machinery. A stale selection must not bypass this recheck. No transaction should span a model inference call.

An observed result may change the decision to abandon an idea; that counts as useful information when the observation supports the decision. Conversely, the presence of a result reference and changed prose does not establish an informative continuation. The seed policy checks typed obligations and cited observations, then records its judgment and uncertainty. For open-ended scientific work, semantic usefulness will remain fallible; the scheduler cannot derive it from hashes or database constraints.

Unresolved effects retain their liabilities and recovery ownership. They do not become a completed experiment through a new disposition event. An option becoming dormant releases eligibility for further work, while already admitted work and held liability remain governed by the execution substrate. There is no automatic cancellation, refund or replay implied by dormancy.

## 4. Compared policies and common ground

**R: rotation reference.** Rotate fairly among mechanically feasible options under fixed class ordering and recorded tie order. Use the current seed rotation where it matches this definition; document adapter changes and call it an experimental reference if it differs from production. Consider each finite well-formed continuation without an additional test of whether its cited observation materially changes the next decision.

**Q: evidence-qualified rotation.** Use the same rotation, class order, authority rules and proposal stream. Before spending on a continuation, require a supported decision change, a discriminating next probe, or remaining work in a predeclared replication protocol. Otherwise make the option dormant or retire it with a reason. Previously recorded negative results affect this judgment within their valid scope. Novel words, a new ID or a nonempty rationale are not sufficient evidence.

Both policies receive the same record fields and observation interfaces. Both refuse unauthorized actions, prevent duplicate effects, honor cumulative caps, protect mandatory work and distinguish unknown from success. Do not give R unsafe behavior and count Q's safety mechanisms as a scheduling advantage. Exact duplicate suppression belongs to both. The treatment difference is whether observed evidence warrants another discretionary attempt, including when negative history is applicable.

Neither policy sees the world's latent answers or future events. Proposed consequences are hypotheses, not trusted labels of which action is best. In the fixture study, both interpret an explicit observation vocabulary with the same deterministic parser. Any richer semantic judgment later supplied by a model must be counted and evaluated in a separate live study.

## 5. Executable study to freeze before scoring

Use eight scenario families, with four parameterized variants each: 32 paired worlds. Fix all generators, constants, identities, event schedules, scoring functions and tie permutations in a committed manifest before running scored trajectories. Create diagnostic development fixtures separately; changes made after viewing scored worlds require a new experiment version. Authors knowing the simulator is not an independent held-out benchmark; label that limitation.

| Family | Decision pressure | Adverse case that must also appear in its variants |
|---|---|---|
| Repeated expensive success | A reusable abstraction could save later task cost even when current tasks already pass | Construction costs exceed reuse benefit within the horizon. |
| Appealing but uninformative continuation | Fluent new hypotheses propose probes that repeat what is already known | A small-looking observation actually opens a consequential next probe. |
| Missing instrument | A useful investigation must await or acquire a prerequisite | The instrument never arrives, or costs more than the blocked question warrants. |
| Duplicate and branched proposals | Several options consume the same finite resource root | Similar descriptions concern different scopes and must remain separate. |
| Counterexample and negative history | An observation narrows applicability and should change future choices | A changed dependency makes an old negative result inapplicable. |
| Replication and noisy observations | Additional observations are justified by a frozen finite replication plan | Premature stopping loses a real finding; extra replication can also waste the remaining budget. |
| Unresolved effect and wakeup | Delayed acknowledgement/recovery competes with other work | Duplicate wakeups and out-of-order receipts must not create new effects or authority. |
| Sparse opportunity and stopping | Inactivity can be correct when no justified experiment is available | A later independent event creates a useful opportunity after dormancy. |

Every trajectory has 24 decision ticks and an exploration cap of 64 abstract units. One policy decision costs one unit, including a decision to idle. Executed probe costs are drawn from the manifest's fixed set of 2, 4 and 8 units and reserved before launch. These are simulator resource units, not token or dollar estimates. Stop discretionary execution when its full reservation plus decision cost would exceed the remaining cap, or when the horizon ends. Required reconciliation continues under separately declared protected capacity and is reported; it cannot be hidden by ending the scored run.

Variants must include simultaneous feasible options and delayed effects so ordering has consequences. Run every paired world with two fixed opposite tie permutations, giving 64 pairs/128 trajectories. Reset each world for each policy. Exogenous events follow the same schedule; endogenous observations and discoveries belong only to the trajectory that acquired them. Do not replay one policy's discoveries into the other. Keep the option-generation rule the same and charge any proposal/instrument construction through the declared probe costs; no free extra planner for Q.

At the horizon, assess each trajectory on the same eight end-use tasks fixed by that world's manifest. These assessments use a separate equal evaluation allowance, unavailable for exploration, and supply no further policy feedback. The tasks must depend on world facts or checked capability applicability, not on whether the policy chose an author-favored action. Publish the grader/control definitions and their costs. Where a simulator supplies a known correct answer, identify that privileged instrumentation explicitly.

Before comparison, check that both policies can solve at least one positive-control world and that a deliberately wrong answer fails its grader. Validate fixture costs and observation release independently from policy code. Keep mechanical fault probes separate from scored benefit trials when their injected failures intentionally invalidate normal execution assumptions.

## 6. Measurements and interpretation

For every trajectory preserve action/observation order, selected/blocked/dormant reasons, record versions, lineage, cumulative expenditure, reservations, unresolved liability, wake events and end-use results. Count idle ticks and continuously feasible waiting time. Track valid decision revisions as a diagnostic, but do not use self-reported insight or proposal count as reward.

Primary outcome: paired difference in the number of correct end-use tasks, out of eight, under the equal exploration cap. Report every pair, family totals and both tie orders, including regressions. Secondary outcomes: exploration cost, end-use execution cost, justified unanswered questions, wasted/redundant attempts, waiting time, pending liabilities and policy overhead. Report evaluation and protected reconciliation costs separately as well as in total-resource reporting. Do not combine heterogeneous resources into an invented universal score.

Mechanical gates require no cap reset through branching, no duplicate effect through wakeup, no replay of known pending work, correct stale-state refusal and observable continuation evidence. Passing these gates validates mechanics only. A decision certificate containing valid references is not evidence that its scientific judgment was correct.

This deterministic authored panel yields descriptive results, not a statistical claim about general scientific discovery. Q merits a broader trial if it improves aggregate primary outcome with no family-total regression, or ties every primary outcome while reducing total measured resource use, with all mechanical gates passing. Report tradeoffs rather than declaring success when that criterion is not met. A richer policy losing here is grounds to revise it or retain R, not to change the fixtures until it wins.

The subsequent live study needs its own frozen workload, model/input contracts, finite resource grants, independent evaluation and analysis appropriate to stochastic outputs. It must include model reasoning/proposal costs and potential semantic errors in continuation judgment. Current live-solver/evidence corrections are prerequisites for interpreting that study, not prerequisites for writing this protocol.

## 7. Decisions and next handoff

- DAGE-01: reuse existing durable identity, authority and execution records; add only the option/continuation information their semantics lack.
- DAGE-02: separate proposal disposition from execution state and recompute eligibility at admission.
- DAGE-03: compare cognitive continuation rules under shared safety rules and equal observation access.
- DAGE-04: include false-negative stopping and stale negative knowledge alongside repetitive-work cases; more selective behavior is not automatically better.
- DAGE-05: retain transparent rotation unless the added judgment earns its cost in a declared comparison.

Next: implement the selected [durable seams and simulator contract](AGENDA-01-IMPLEMENTATION.md), freeze executable fixtures, then run the declared comparison. The audited-interface mapping is complete at the semantic boundary; the worker chooses and records exact schemas/APIs. This document does not complete the executable freeze, agenda prototype, empirical benefit test, final schema or final technology choice.
