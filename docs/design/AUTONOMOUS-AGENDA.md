# Autonomous agenda: selecting the next useful investigation

Status: stage 8.4 conceptual policy selected for refinement; not implemented or empirically validated. Builds on AGENDA-1..5, [learning episodes](LEARNING-MODEL.md), [decision context](MEMORY-AND-CONTEXT.md), and existing `agenda.seed_order`, frontier proposals, wakeups and protected supervision. This document advances design while Development 02 completes its bounded live episode. It is not an instruction to expand that worker assignment.

## 1. The central decision

The society chooses **which observation or capability change is worth acquiring next**. A task queue records accepted work; an agenda also forms questions and decides whether acquiring their answers deserves resources. The model proposes interpretations and experiments. Durable state, declared policy and resource admission determine which proposals become commitments.

Select a portfolio of bounded investigation options. Each option connects a current limitation or charter-compatible possibility to a discriminating observation and a next decision. Do not use a permanent executive persona, a global novelty score, or a model's self-assigned confidence as the governing mechanism. Intelligence belongs in proposing useful distinctions and methods; persistence belongs in retaining their evidence, consequences and obligations.

The system can originate investigations with no current user task. The charter and a finite exploration allocation authorize that activity. Successful task performance can itself motivate development: repeated one-off solutions may justify a reusable procedure, even when there are no failing tests. Conversely, solving one task does not prove that a reusable competence has been acquired. The Development-02 prompt check illustrates why these meanings must be separated.

## 2. The objects and their meanings

| Object | Meaning |
|---|---|
| Opportunity | A scoped possibility to improve competence, resolve consequential uncertainty, or advance the charter. It is not yet work authority. |
| Investigation option | A proposed finite next experiment with evidence basis, an observable result and a disposition rule. |
| Frontier | The current set of options, including dormant, blocked and rejected options whose history matters. |
| Decision consequence | What a possible result would change: routing, applicability, explanation, instrument choice, another experiment, or retirement. |
| Continuation certificate | A record connecting a completed attempt's evidence to the specific next question and requested additional allocation. It is a checkable justification, not a proof that further work will succeed. |

An option is

`O = (lineage, question, scope, basis, alternatives, probe, outcomes, consequences, prerequisites, cap, expiry, exposure)`.

`basis` resolves to actual sources and gaps, not a paragraph claiming importance. `alternatives` need only be distinctions sufficient for the next decision; an entire theory of the problem is unnecessary. `probe` names an available procedure or the bounded work needed to construct one. `outcomes` includes failure and inconclusive results. `consequences` maps those results to next actions or constraints. `cap` includes the relevant money, inference, execution, wall-time and concurrency limits; do not collapse unlike resources into an invented common unit.

For example: two recent routines solved inclusive-range errors using different local edits. An option proposes constructing one source transformation, checking it against both successes and a known negative-input failure, and determining whether it deserves a narrow application scope. A win can justify a larger transfer trial. A counterexample can narrow scope or reject the method. An invalid evaluator can instead create an instrument option. All are informative outcomes without forcing success.

## 3. Origination and context

Origins include repeated failures or expensive successes, contradictions and invalidated warrants, context gaps, transfer opportunities, missing instruments, and speculative charter questions. A completion or material evidence change updates affected opportunities. A bounded charter scan can originate new ones under an explicitly granted exploration budget. Avoid deriving every opportunity only from current failures: that would prevent genuinely new directions.

An agenda decision needs its own context contract: charter boundaries, current commitments and protected capacity, scoped competence/uncertainty evidence, recent attempts and their costs, candidate options, available instruments, known negative results, and the next permissible actions. The packet must identify whether an apparent gap is missing knowledge, missing retrieval, missing authority, or an unavailable instrument. Each leads to different work.

Source reuse is desirable; answer leakage is not. Exposure to prior attempts, peer outputs and evaluation material follows the option and its descendants. An observation learned while exploring cannot later be relabeled as held-out confirmation merely because another worker receives it.

## 4. Selection policy: transparent seed before learned ranking

Start with the existing fair rotation among bottleneck, transfer, instrument and speculative opportunities. Add feasibility and relevance checks, without inventing a calibrated expected-value model.

1. Reconcile due operations and protect supervision capacity. Accepted obligations retain their admitted bounds and declared scheduling policy.
2. Resolve current option basis, prerequisites, scope and exposure. Reject duplicates; park infeasible options with a concrete wake condition. A blocked option does not occupy a runnable worker.
3. Admit only options that can reach a declared next decision within a finite allocation. When that is unknown, the first option is a bounded feasibility probe, not a promise to finish the research.
4. Within development capacity, rotate eligible classes and use stable fair order within each class. Apply deadline handling where explicitly admitted. Record why an option was eligible and selected.
5. Start one attempt, or a specifically justified team, through existing admission and execution mechanisms. Re-evaluate on a relevant event, completion or due decision time.

Maintain typed evidence about potential benefit—frequency of a limitation, observed cost, unlocked task scope, instrument reuse—and explicit unknowns. These inform later comparisons of scheduling policies. Do not multiply uncalibrated model estimates of novelty, importance, success probability and impact into a spurious precise score. Fair rotation is intentionally a measurable baseline, not a claim of optimality.

Once histories support it, candidate agenda policies can allocate among option classes differently. Compare entire bounded trajectories, including time spent proposing, failed probes and downstream task outcomes. A ranking policy that generates convincing descriptions but no better decisions has not improved the society.

## 5. Continuation, branching and stopping

An attempt ends with evidence and one of: answer obtained, capability candidate produced, scoped counterexample, instrument failure, inconclusive within the cap, or unresolved effect requiring reconciliation. The next step is a new admission decision. Completion does not automatically refill a budget.

A continuation certificate contains the prior attempt and result references; the decision before and after that observation; the residual question; the next discriminating probe; its cap; and the stopping or abandonment condition. A replication with no new conclusion can still be justified if a predeclared protocol requires additional observations and the remaining allocation covers them. “Try harder,” a renamed hypothesis, or prose claiming something changed is insufficient.

Branching generates sibling options with shared lineage and exposure. Shared parent expenditure remains charged once to the overall exploration portfolio, with explicit attribution for comparisons. New IDs do not reset cumulative caps. Do not automatically merge hypotheses merely because their text is similar: deduplicate concrete evidence/probe/decision identity first, and retain disagreements when equivalence is uncertain.

Dormancy retains a wake predicate such as an instrument becoming available, a relevant new source, or a materially changed task distribution. Periodic mechanical scans repair missed wakeups. A due timer alone is not a reason to buy more inference; an admitted bounded scan or changed predicate is. Idle is a valid state.

## 6. Dreaming as a family of experiments

Background consolidation is work selected by this same agenda, using existing experience. Possible options include testing whether two procedures share an executable abstraction, finding a counterexample to an apparent regularity, distilling a context policy, or replaying a prior failure with a changed instrument.

Their outputs remain proposals until checked. Generated examples can help development but do not independently confirm the generating model's own hypothesis. A synthetic counterexample becomes evidence only when its claimed effect is independently checked by the relevant procedure. A summary does not replace unresolved operations or silently upgrade uncertainty to fact.

Thus there is no privileged dreaming loop with unrestricted self-editing rights. There are bounded synthesis and testing operations whose costs and outcomes remain visible. The architecture can later learn which such operations deserve more capacity.

## 7. Connections and representation boundary

Use existing investigations for continuing identity, frontier proposals for candidates, allocations for authority, packets for decision inputs, and episodes for operational change. A small durable option record plus lineage and disposition events is enough for the first representation candidate. No additional scheduler service, universal world-model graph or vector database is implied.

The public semantic seam is: update frontier from relevant evidence; explain eligibility; select under capacity; admit an option; observe an attempt result; decide continuation or dormancy. Exact tables, function signatures, indexes and deployment choices belong to the next representation/engineering pass after those behaviors are approved by their first probe. Existing policy functions are seed mechanisms, not a reason to duplicate an agenda subsystem.

## 8. First experiment and rejection conditions

Before implementation, freeze a small replayable environment with optional investigations and delayed consequences. Include an expensive repeated success that rewards abstraction, a misleading high-novelty question, a missing instrument, two duplicate proposals, a real counterexample, an unresolved operation, an eligible speculative question and a valid reason to stop. The scheduler sees only evidence released at each decision time, not future outcomes.

Compare the existing fair rotation and the proposed eligibility/continuation policy under equal total allocations. Count valid consequential decisions, end-task outcomes, total cost, unresolved liability and time starved among continuously eligible options. Do not reward proposal count, activity, apparent novelty or hypothesis agreement. In a stochastic live follow-up, share the initial environment and budget, then preserve each policy's own exposure trajectory; importing the other policy's discoveries would invalidate the comparison.

Structural acceptance precedes a benefit claim: no budget reset through descendants, no duplicate launch from repeated wakeups, no known pending effect replay, dormant work releases runnable capacity, and continuation cites actual evidence. Then test whether the richer policy improves outcomes or reduces waste. If it does not, retain the simpler rotation and useful durable records. A handcrafted trace validates mechanics only; it cannot establish general scientific discovery.

## Decisions and next refinement

- DAG-01: choose evidence-backed investigation options as the scheduling unit; a bare task list omits origination and continuation semantics.
- DAG-02: retain transparent fair rotation as the seed; postpone learned utility ranking until comparable trajectories exist.
- DAG-03: model renewal as a new bounded admission tied to evidence and shared lineage; a non-empty explanation string is too weak.
- DAG-04: run consolidation through the same authority and evidence machinery; no privileged background self-modification path.
- DAG-05: evaluate agenda policies on trajectories with total costs and exposure histories; local proposal quality is insufficient.

The [first representation and experiment protocol](AGENDA-EXPERIMENT-01.md) now specifies minimal semantic records and an adverse-case trajectory comparison. Next, reconcile these records with audited interfaces and commission executable fixtures for freezing before scored runs. The worker's comprehensive engineering review proceeds in parallel as a separate assignment. Full autonomous agenda implementation, adaptive teams and learner revision are not silently bundled into that work.
