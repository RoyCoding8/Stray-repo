# P05. Autonomous agenda

Let the system choose what to learn or investigate next. Depends on [P01](01-INVESTIGATIONS.md), [P02](02-MEMORY.md) and [P04](04-CAPABILITIES.md). The [master plan](MASTER-PLAN.md) owns shared rules.

## Agenda contract

An agenda option identifies an objective or open question, proposed action, required capability, expected observation, resource request and reason to revisit or stop. Options can arise from a human objective, an unresolved investigation, a contradicted claim or a newly available capability.

The agenda owns allocation across investigations. P01 owns each investigation's continuation. A worker can propose an option but cannot grant it resources. Eligibility follows existing authority and resource constraints before policy ranking.

Use a transparent seed policy with mission priority, overdue obligations, learning opportunities and an exploration allocation. Preserve the alternatives considered and the reason for selection. An adaptive policy can revise allocation from outcomes, but an uncalibrated usefulness estimate is not a measured probability.

Generated practice tasks need validity checks independent of the generator. Choose future experience using the current capability state. One-time task generation or a fixed task rotation does not satisfy this component's autonomy goal.

## Delivery slices

1. **P05-1. Select among real options.** Derive options from active investigations and evidence. Admit selected actions through P01. Record deferrals and stopping reasons.
2. **P05-2. Close the learning feedback loop.** A capability acquisition, rejection or applicability failure updates the next selection. The system originates a useful follow-up rather than waiting for a human task.
3. **P05-3. Compare allocation policies.** Run the seed and one adaptive policy from common initial state. Track useful completions, learning opportunities explored, wasted work and resources.

## Acceptance scenarios

- **P05-A.** Two investigations compete under a finite allocation. The selected work executes, and the deferred work remains inspectable rather than disappearing.
- **P05-B.** A new executable instrument makes an observation possible. The agenda proposes and selects that observation when relevant to an open question.
- **P05-C.** A lesson fails on later use. The next agenda changes toward a discriminating probe or scope repair. Renaming the same task is insufficient.
- **P05-D.** No eligible action has enough authority or resources. Stop or defer with reasons rather than spinning a heartbeat loop.
- **P05-E.** Resume the campaign and reconsider only outcomes not already incorporated. Repeated wakeups do not create repeated admissions.

A bounded live sequence must show experience influencing later selection. Benefit over the transparent seed is an experimental question. P06 supplies additional search-policy evidence later.

## Working checkpoint

The human gives an objective and bounds rather than the next task after every episode. The agenda selects work through the existing investigation owner. A timer may wake execution, but is not another policy or state authority. See the older [agenda design](../design/AUTONOMOUS-AGENDA.md) for hypotheses requiring review.
