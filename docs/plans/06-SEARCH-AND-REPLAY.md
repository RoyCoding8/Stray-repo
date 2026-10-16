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

P10 closed before this implementation started. At that checkpoint,
`agenda._select_and_run` built eligible opportunities and called fixed
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

- `Supported`: a recorded consequence and its operation/receipt and resource
  references. A continuation also needs its own recorded child frame.
- `Gap`: the requested action or continuation lacks matching evidence. It receives
  no task grade and cannot be counted as a policy success or failure.
- `Stopped`: the policy deliberately ends exploration under its declared rule.

Match support using the visible frame and action plus the actual task/start bytes,
worker/model, capability closure, P03 input packet, runtime, limits and evaluator
interpretation. Dispatch IDs locate evidence; they are not evidence that two
executions have equivalent inputs. An unchanged global memory revision is not a
substitute for checking the context actually consumed. Changed construction
inputs invalidate support even if the task name stays the same.

One-step screening compares policies on the same frozen frame. The current
implementation qualifies independent one-step decisions and reports a requested
second decision as missing child coverage. It does not yet follow supported
multi-step branches. Adaptive replay must follow recorded child frames only.
After divergence, missing matching context
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
Authored fixtures qualify this interface. Untrusted model policy execution must
first satisfy the repository's execution boundary; the current uncontained
candidate screening path does not qualify for live launch.

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

## Implementation contract

The caller first prepares a development menu, gathers real branch evidence,
screens an executable policy and then pins that policy in a new agenda:

```python
prepared = investigate.prepare_context(
    dsn, investigation_id, target_revision=0, artifacts_root=artifacts_root)
# Prepare every fresh alternative before executing any of their workers.
# Publish the visible menu and exact option-specific inputs as one frame.
branch = search.capture(
    dsn, frame_digest, opportunity_id, artifacts_root=artifacts_root,
    staging_root=staging_root)
screen = search.evaluate(
    dsn, checker, policy, frames, branches, allocation_id=screening_cpu_root,
    staging_root=staging_root, artifacts_root=artifacts_root)
# New charter only. Ordinary agenda.wake owns actual policy and worker effects.
```

### P01 preparation

`investigate.prepare_context` owns the exact continuation, deterministic
decision/attempt/operation IDs and P03 request used by `step`. It accepts only
a ready start at the declared revision with no pending worker decision. It
returns either ready plus the exact visible input, or the existing context/
capability refusal. It does not admit a P01 decision or dispatch work. `step`
uses this same implementation rather than rebuilding a second input shape.
Preparation may pin P03 journal entries and capability selection evidence.

The collector creates all fresh P01 starts, prepares their option-specific
packets, validates those packets and then publishes its frame before any branch
worker runs. Execute each selected collection branch through normal P01. A
prepared but unexecuted action has no supported consequence. Existing
continuations can be recorded as observed trajectories; this collector does not
claim to fork their earlier mutable state.

### Frame and branch objects

Use existing immutable artifacts and `rsi_decisions`, not a new database or
history owner. A frame separates its policy-visible request from provenance.
The visible request names the objective, bounded eligible menu, learner-visible
prefix, resource ceilings and option-specific input identities. Private source
cursors and future results are outside that request. Each option pins the actual
prepared P01 visible input, task/start bytes, genome/model or method closure,
runtime, limits and evaluator. IDs appearing in a real input remain part of its
digest; do not normalize them away to manufacture support.

For native methods, `capability.plan_invocation` derives the execution identity
from the prepared request, method closure, trusted runner and Python runtime
without staging or dispatch. `capability.invoke` executes that same plan. Pin
the evaluator's task identity and runtime prospectively. Its eventual operation
execution version includes the candidate solution and belongs in captured
result evidence, not in the prepared frame. Existing agent-run records with no
bound worker runtime remain unsupported for replay even when their observed
test result is known.

`search.capture` reconstructs a branch from its original P01 decision,
observation, worker/verifier operations, receipts and artifacts. It verifies the
prepared input against the actual consumed input. Known pristine results give a
supported consequence. Unfinished, conflicting or unmatched work remains a gap.
Record the actual child frame when one exists; never invent a next frame from
the original chronology. Worker, verifier and policy resource evidence stays
separate and attributable.

`search.evaluate` executes the supplied genome's exploration method through
`capability.invoke`, with `interface="exploration-policy/1"`, the visible frame
as `value`, and empty `files` and `context`. The result has empty files and one
closed action: `{"action":"choose","opportunity_id":"..."}` or
`{"action":"stop","reason":"..."}`. An ineligible ID or malformed output is a
policy refusal, distinct from a valid action lacking historical coverage.
One-step and recorded-child evaluation use this same ABI. The pure offline
recomputation checks inputs, support, quality, resource references and coverage;
it does not execute candidate Python on the coordinator.

### P05 integration

Fixed `seed/1` and `adaptive/1` remain baselines. An executable charter policy
names a published genome, method name, the exact interface and finite native
timeout/output limits. Its genome must be included in the existing agenda grant.
The policy budget permits at most `max_turns` native policy admissions, counted
from durable decisions under the agenda lock. An invalid result cannot create an
unbounded sequence of free retries or silently call a fixed policy.

The existing flight holds either a pinned policy invocation or its selected P01
work. A policy flight names its immutable frame and operation before dispatch.
Restart recovers that same invocation. A known choice advances the flight
atomically to work; a deliberate stop or definitive refusal is recorded and
closed by the same owner. Uncertain effects keep the flight. No second driver,
watcher or selection authority is introduced.

Prepare option inputs before taking the source snapshot. After policy execution,
rebuild the relevant menu and revalidate prepared dependencies. Account explicitly
for that invocation's own charged CPU when comparing its source resource view.
If external decision inputs changed, do not execute the obsolete choice. If they
remain equal, take a fresh source frontier and retain the existing transactional
epoch, memory, grant, revision and deadline fence at final admission. The
policy's own events must neither cause perpetual self-invalidation nor exempt
another actor's changes. Exhausted policy admissions stop rather than repeatedly
spending against stale inputs.

Campaign exports include these native policy operations even though they have no
P01 attempt. Durable policy admissions locate their receipts, reservations and
execution identities; offline accounting must not omit their screening cost.

### Integration and qualification

First land and verify the shared P01 preparation seam. Then use disjoint lanes
for search artifacts/replay, P05 executable policy ownership, and the prospective
collector/experiment. Pin their exact public signatures before fan-out. The
coordinator runs the connected path and neighboring component gates before
independent Sol High review, then runs the bounded free-route slice.

Owned lanes are P01 preparation, search artifacts/replay, and P05 policy
ownership. The coordinator owns the shared native invocation plan and serial
integration. Their disposable test namespaces are `ad1061xx`, `ad1062xx`,
`ad1063xx` and `ad1060xx` respectively. A runtime-planning test must establish
that the prospective identity equals the actual child operation's identity.

The collector uses three small development worlds with two prepared alternatives
per world. Execute recorded branches through P01 native methods and pristine
verification. Run both authored screening policies against the identical frame
and branch corpus. An extra unexecuted option and an absent continuation expose
coverage gaps. These authored worlds qualify machinery, not learned competence.

For the free-route slice, construct one exploration method from development
history through the existing P04 constructor. Permit at most one repair after a
completed unusable response. A transport timeout or unresolved effect stops the
slice. Each model admission has a 90-second timeout and a 400,000-unit token
reservation, with at most two admissions in total. Native execution keeps the
method's declared limits. Record every construction and screening charge.

Screen the model's unchanged method bytes on the development corpus. Eligibility
for a fresh one-turn P05 charter requires supported coverage on every screening
frame, no worse checked quality than the declared incumbent, valid closed
actions, and known costs within the frozen allocation. A rejected or unavailable
candidate ends with its named reason. An eligible candidate controls the fresh
charter through the same public agenda path. Report its actual selection and
checked result separately from replay. Neither eligibility nor one fresh use
establishes sustained learning or general transfer.

Use at least three small development worlds. Include agreeing policies,
different supported first choices, an unexecuted option, a missing child,
changed consumed input and changed worker/runtime identity. Start every mutation
from a clean accepted baseline. Check public P05 effect identity, a restart
between policy admission and result consumption, relevant source changes during
policy execution and literal future-value exclusion. Report supported decisions,
gaps, deliberate stops, quality and costs without imputing missing outcomes.

## Working checkpoint

The agenda uses versioned exploration code informed by discovery history. Background replay is bounded work under the same allocations, not a second independent scheduler. The [research notes](../design/COGNITIVE-RESEARCH-NOTES.md) explain the Dream-RSI connection and its limits.
