# P06. Search history and dreaming

Use accumulated attempts to improve exploration decisions. Depends on [P01](01-INVESTIGATIONS.md), [P02](02-MEMORY.md) and [P05](05-AGENDA.md). The [master plan](MASTER-PLAN.md) owns shared rules.

## History and replay contract

A discovery branch identifies its starting artifact state, visible evidence, operational policy, selected action, outcome, resources and continuation. Preserve primary derivation separately from other evidence dependencies. Replay reconstructs what was visible at the decision, not everything known at the end.

An exploration policy chooses among available starts or continuations, allocates effort and may stop. Pin the worker, construction context, environment and outcome interpretation associated with replayed transitions. A change that invalidates those conditions cannot reuse an old outcome as its counterfactual result.

Support is explicit. A replay query returns a recorded consequence or reports missing coverage. Stopping deliberately is different from lacking a recorded continuation. Unsupported actions receive neither an invented reward nor an automatic failure score.

Screen policies against several historical investigations with the same decision interface used live. Rank quality and resource tradeoffs without assuming parallelism is inherently beneficial. New live outcomes expand the usable history. Consolidation can propose abstractions or corrected claims, but those proposals need their own checks.

## Delivery slices

1. **P06-1. Record discovery branches.** Preserve decision prefixes and artifact starting points while actual P05 work runs. Reconstruct a known trajectory from its public history.
2. **P06-2. Execute policy replay.** Compare fixed exploration policies on supported choices. Report coverage separately from performance and record all screening costs.
3. **P06-3. Revise and use a policy.** Construct one executable policy revision from development history. Screen it, then deploy it prospectively on fresh work through P05. Use missing coverage to propose informative live branches.

## Acceptance scenarios

- **P06-A.** Two policies order known alternatives differently and produce different supported exploration decisions.
- **P06-B.** Request an unrecorded continuation. The result is missing coverage, not a fabricated task failure or success.
- **P06-C.** A replayed policy tries to inspect a future outcome. The interface does not reveal it.
- **P06-D.** Change the worker or capability bytes whose behavior a transition records. Replay refuses to treat that transition as equivalent without appropriate evidence.
- **P06-E.** A selected policy changes actual live allocation. Quoting its source or inserting its advice into a prompt cannot satisfy this scenario.

Compare replay ranking with subsequent live results and report disagreement. A replay winner need not win live to complete the experiment. Check sensitivity to incomplete histories and resource objectives before treating replay as the primary selector.

## Grounding and design sketch

This sketch is prospective. P10 must close before P06 implementation starts.
`agenda._select_and_run` currently builds eligible opportunities and calls fixed
`seed/1` or `adaptive/1` ranking code. Its choice pins one P01 flight before
execution. P01 records the actual P03 packet, worker input, operations and
observations. P02 capture advances shared memory, so changing an earlier choice
can change later worker inputs. Chronological history alone cannot supply those
changed inputs or their consequences.

Two independent design readings compared frozen decision frames with strict
historical-prefix replay. Select immutable decision frames backed by existing
artifact references, with strict support matching. Prefix replay alone usually
has only the action already taken. Copying whole mutable investigations into a
replay database would duplicate ownership. Neither approach licenses invented
outcomes. New alternative evidence must come from real bounded work.

### Policy and replay interface

One executable `exploration-policy/1` accepts a learner-visible decision frame
and returns one existing eligible opportunity ID or an explicit stop. Opportunity
ceilings define the units of effort it can allocate. The policy cannot mint a
grant, raise limits, dispatch a worker or write a task result. The same interface
must control P05 work and replay. Fixed policies remain comparison baselines.

A frame pins eligible opportunities, visible prefix and evidence references,
remaining authorized resources and the current P01 starts. Store outcomes outside
the policy input. After the policy chooses, the trusted replay reader returns one
of these distinct results:

- `Supported`: a recorded consequence, its operation/receipt references, measured
  resource fields and the actual recorded child frame.
- `Gap`: the requested action or continuation lacks matching evidence. It receives
  no task grade and cannot be counted as a policy success or failure.
- `Stopped`: the policy deliberately ends exploration under its declared rule.

Match support using the visible frame and action plus the actual task/start bytes,
worker/model, capability closure, P03 input packet, runtime, limits and evaluator
interpretation. Dispatch IDs locate evidence; they are not evidence that two
executions have equivalent inputs. An unchanged global memory revision is not a
substitute for checking the context actually consumed. Changed construction
inputs invalidate support even if the task name stays the same.

One-step screening compares policies on the same frozen frame. Adaptive replay
follows recorded child frames only. After divergence, missing matching context
or a child is a gap; do not silently continue through the original chronology.
Report supported queries, gaps and deliberate stops separately, alongside outcome
quality and resource vectors. Screening compute is an additional cost, not free
historical discovery. A policy with less coverage cannot win by hiding unknown
results in an average over its surviving cases.

### Ownership and evidence acquisition

Reuse `rsi_agendas.flight` as a tagged pending policy or work invocation. Pin the
policy digest, frame artifact, operation identity and source frontier before
bounded child execution. Recover that same receipt before atomically advancing
the flight to a P01 action. Keep one mutable owner and existing broker allocation
roots. A policy's own charged execution must not invalidate its source merely by
advancing the global event epoch; revalidate external decision inputs and retain
the final admission fence. Do not exempt unrelated external changes.

Construct a policy as bounded P01 development work from development-only history.
Pin source and lineage, screen the artifact, then name its exact digest in a new
prospective P05 charter. Do not mutate an active charter or reuse task-specific
P04 retention as policy assessment. An absent, invalid or unresolved policy result
does not authorize a silent fixed-policy substitution.

Collect known alternatives prospectively from fresh starts with their visible
frame and option-specific construction contexts fixed before effects. Separate
P01 investigations execute the alternatives under declared allocations. If their
inputs do not match the claimed support conditions, retain the traces as different
branches and report a gap. Arbitrary continuation forks are outside this slice
until an exact starting prefix can be reconstructed. Fixture branches qualify
this mechanism; they do not establish model-conditioned exploration benefit.

The current native child is bounded and uncontained. P06-C qualifies the serialized
interface with literal future-value probes; it cannot prove hostile policy code
cannot read coordinator files or databases. Keep that limitation explicit rather
than claiming containment from a filtered JSON request.

### Informative qualification

Use several small worlds with supported alternatives, incomplete histories and
different resource objectives. First establish clean replay and prospective-use
baselines. Then remove a continuation, change worker or context bytes, and inject
a protected future value. Check actual P05 choice/effect identities, not only a
policy ranking or source hash. Include a decision where two executable policies
produce different supported allocations and a control where they agree.

The bounded live slice constructs at most one revision plus one repair, screens
it without provider calls, and compares the selected policy with the incumbent on
fresh opportunities. Freeze the exact call/resource/wall caps before effects.
Stop on construction failure, insufficient support, unresolved effects or the
declared limits. Preserve replay/live disagreement. No sustained learning win is
required to close the component mechanism.

Dream-RSI motivates reusing recorded branches to revise executable exploration
policies while keeping the discovery worker and evaluator fixed. Its replay
reveals recorded children rather than generating unseen outcomes. Our shared
memory makes construction-context support an additional explicit condition.
This is design input, not evidence of our utility or recursive improvement.
[Primary source, section 3](https://arxiv.org/html/2609.14858v1).

## Working checkpoint

The agenda uses versioned exploration code informed by discovery history. Background replay is bounded work under the same allocations, not a second independent scheduler. The [research notes](../design/COGNITIVE-RESEARCH-NOTES.md) explain the Dream-RSI connection and its limits.
