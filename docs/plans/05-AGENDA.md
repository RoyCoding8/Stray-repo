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

## Selected implementation shape (2026-10-15)

Two source-grounded Luna designs compared a journal-derived portfolio head with
one explicit portfolio row. An independent Luna judge and the coordinator choose
the row. P02 claim revisions use a separate memory clock, and the portfolio needs
a clear fence across different investigations. Keep both existing source clocks;
do not rewrite P02 to force event publication. Graft the alternative's exact
acknowledgement and shared-root allocation rules.

### Caller contract

`rsi.agenda.create(dsn, *, agenda_id, charter, artifacts_root)` pins a bounded
charter. `wake(dsn, agent, checker, agenda_id, *, staging_root, artifacts_root)`
selects or recovers at most one investigation action and returns its recorded
choice, result or deferral. `read` and `export` expose current state and decisions.
There is no background scheduler or additional worker runtime.

The charter names an existing immutable grant version, objective, token and CPU
root allocations, `seed/1` or `adaptive/1`, maximum turns and a UTC deadline. It
contains a finite catalogue of published development-task opportunities with
stable IDs, genome identities, objective/question, priority, resource ceilings,
expected observation and stopping condition. An optional exact P04 method request
makes an item an instrument opportunity. A scope-probe item also names its source
opportunity, relevant lesson and the changed condition/competing explanations it
can distinguish. This catalogue is an independently checked task-world adapter,
not a human-authored order of execution or a claim of arbitrary task generation.
No sealed task, pristine answer or verifier internals enter agenda policy input.

An item can refer to an existing P01 investigation inside the same roots or be
created by the agenda only when selected. Task and genome packages are loaded
and verified through their existing APIs. A scope probe must have a different
published task/input identity from its source; descriptions alone do not qualify.
When no valid probe exists, preserve a deferral instead of inventing an unchecked
experiment. Catalogue and charter are immutable for this component; P06/P07 can
later revise executable selection procedures with explicit lineage.

### State and authority

Add only `rsi_agendas` in migration `0031_agendas.sql`. One row owns immutable
charter, revision, turn count, event high-water, memory revision, and at most one
in-flight choice. Current portfolio state lives here. Ranked alternatives,
source references, policy attribution, eligibility/deferral reasons and exact
completion acknowledgements live in existing immutable `rsi_decisions`, written
atomically with the row. Do not revive retired `agenda_*` study tables.

The agenda never creates grants or root budgets. Require a grant that names the
agenda, permitted development tasks/genomes, permitted effects and separate token
and CPU limits. Root domains and ownership must match the charter; authorized
root amounts and maximum turns must fit the grant envelope. New admissions
require the pinned grant to remain current. Share these roots across selected
P01 work; do not create per-turn child budgets. Preserve token and CPU units and
unresolved exposure separately. Broker reservation remains the final capacity
check. Snapshot feasibility does not authorize a send.

Use `store.transact` and the portfolio row revision to serialize choices across
*different* wake request IDs. Snapshot source state first, then compare the agenda
revision, event high-water and memory revision inside the selection transaction.
Read the P02 clock under its existing lock order. A stale snapshot retries only
within a small fixed local bound and otherwise returns a stale deferral. No
network, model call, nested transaction or artifact staging occurs under that lock.
Advance only the high-waters actually examined. Filter source relevance and
learner visibility before policy input; unrelated events and agenda audit events
must not buy turns or inference. Preserve missing-source information explicitly.

### Exact action and recovery

A choice pins its selected P01 investigation and *pre-step revision*. Existing
P01 decision, attempt and operation IDs remain the deterministic hash of that
identity. Add an optional `target_revision` to the existing `investigate.step`
path, rather than another decision API. On that path:

- Admit only at the pinned ready revision, using the existing derived identities.
- Resume only that pending identity.
- If that decision already has a durable observation, return it without admitting
  the newly ready revision's action.
- Refuse a different pending identity or unexplained revision advance.

Persist the agenda choice before creation/admission/execution. Creation identities
are deterministic and replayable. Acknowledgement names the actual P01 decision,
attempt, operation and observed outcome, and clears the portfolio flight in one
transaction. A completed choice is never executed again. Uncertain effects retain
the flight and block new choices. Missing context, capability or source bytes
after selection also retain that choice until it can resume. Only an exact P01
definitive never-sent outcome may clear it as a deferral. Before selection,
ineligible options remain deferred without creating a flight. Concurrent wakes can recover
the same flight but cannot create a competing one. No network transaction is held
open during a child run.

### Policy and evidence

Use a pure `agenda_policy` reducer over bounded typed options and learner-visible
facts. Eligibility applies authority, resources, source availability, current
investigation status and exact capability applicability before ranking. Seed
ranking uses mission priority and stable fair order. The adaptive comparator
raises a discriminating probe after an applicable lesson fails on checked later
use and raises relevant observations newly enabled by checked retention. Retain
the trigger observation/claim/capability identities and all deferred alternatives.
Timeout, infrastructure loss or missing evidence is not a domain contradiction.
Scores are transparent priorities, never calibrated probabilities.

No eligible option means a resumable deferral if a later source or instrument can
change eligibility. A hard turn/deadline cap terminates new selection. Repeated
wakes without new relevant inputs consume no new turn and create no new admission.
At most one selected action runs per `wake`; reconciliation returns before another
selection. P10 will provide unattended campaign iteration.

Freeze a common initial catalogue/evidence state and equal disjoint root budgets
for seed/adaptive comparison. Each arm sees only its own subsequent experience.
Report valid completions, consequential probes, failed/wasted work, allocations
and uncertain effects separately. The integrated gate covers A-E, distinct-trigger
races, post-completion replay, source-clock changes, wrong-interface refusal,
authority/budget refusal and a disconnected feedback control. Native methods
execute through P04's bounded child path, never coordinator imports.

After integration and independent Sol High review, freeze a short free-route
sequence with at most three selected actions per arm, fixed per-operation limits
and a shared aggregate cap. One availability check suffices. Preserve unavailable,
unscored and negative results; do not extend the run to obtain a ranking change
or a gain. A fixture qualifies mechanics. A live ranking change qualifies only
experience-conditioned selection; usefulness and broader improvement remain
separate questions.

### Implementation ownership

- Runtime lane owns `rsi/agenda.py`, migration 0031, the narrow P01 replay fence,
  and runtime/state tests. It consumes the pure policy contract below.
- Policy lane owns `rsi/agenda_policy.py` and its focused tests. Its public
  `rank(options, policy)` accepts JSON-compatible option records with `id`,
  `eligible`, `priority`, `kind`, `triggered`, `last_selected` and `reason` fields;
  it returns every option in ranked order with a recorded rank reason. Seed sorts
  eligible first by priority descending, last-selected ascending, then ID.
  Adaptive first raises eligible triggered `scope-probe`/`instrument` options,
  then uses the same seed order. Invalid policy IDs fail at the boundary.
- Experiment lane follows runtime integration and owns the bounded comparison,
  offline recomputation and experiment gates. It must use public agenda commands,
  actual P01 operations and pristine verification rather than score stamped rows.

The coordinator integrates serially, checks complete public paths, then requests
Sol High review. All owned worktrees are removed after accepted merges. P05 closes
only after fixes, debloat, CI and backup synchronization.
