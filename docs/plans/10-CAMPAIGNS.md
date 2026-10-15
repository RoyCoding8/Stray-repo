# P10. Continuing campaigns and assessment

Run useful bounded work without supervising every invocation in a chat. Depends on [P01](01-INVESTIGATIONS.md), [P02](02-MEMORY.md), [P04](04-CAPABILITIES.md) and [P05](05-AGENDA.md). The [master plan](MASTER-PLAN.md) recommends building this baseline before advanced replay and teams.

## Campaign contract

A campaign binds the human charter, allowed domains and effects, active policy versions, resource envelope, stop conditions and assessment protocol. It contains investigations and their learning lineage. The agenda selects work, P01 executes it, and the campaign records aggregate progress without duplicating their authoritative state.

Use the existing local runtime and operator facilities first. Support start, inspect, suspend, resume and stop through one public entry. A process may wake for due work, but no separate watcher decides the research agenda. Graceful stop preserves pending effects and liability.

Assess local correctness during work, reuse after retention and periodic performance on separately protected tasks. Separate development feedback from sealed assessment. For scientific work, distinguish a measurement, model prediction, supported hypothesis and unresolved explanation instead of forcing all results into a pass/fail task grade.

The report identifies useful completed work, acquisition attempts, retained capabilities, later use, transfer, learning-policy descendants, resources and human interventions. Infrastructure outages and unknown costs remain separate. Model-route variation is part of the conditions, not a learning gain.

Offline recomputation checks results derivable from the exported evidence. It
does not independently authenticate the provider, wall time or other runtime
measurements. Label those observations and their measurement source explicitly.

## Selected ownership and interface

Design selected after tracing the integrated P05 owner and comparing an assessment
flight against fixed assessment assignments. Implementation follows P05 closure.

Campaign identity equals agenda identity. `rsi_agendas` remains the only mutable
lifecycle owner. The existing P01 flight keeps its meaning. Publish an immutable,
content-addressed assessment protocol through the artifact store and pin only its
digest in the charter. Do not add a campaign table, budget, cursor or watcher.

The public consumer is `rsi.campaign` with `start`, `run`, `inspect`, `suspend`,
`resume`, `stop`, `export` and pure `recompute`. Provide the same operations through
`python -m rsi.campaign`. `start` accepts staging and artifact roots, validates the
protocol and existing authority, and creates the agenda idempotently. `run` accepts
a positive finite `max_wakes` and wall bound, plus the worker/verifier launchers.
It reloads the existing owner rather than accepting a new next-task sequence.
Inspection exposes status and protocol identity, not protected assessment content.

The protocol fixes a finite ordered set of assessment rounds before outcomes.
Each round pins its turn milestone, gate epoch, parent and candidate genomes,
model and sanitized route identity. Epochs fix task splits, evaluator versions and
execution bounds. Use the existing gate only for its actual genome comparison
contract. Its result does not establish native-method transfer or learner benefit.
Require disjoint fresh anchor content across rounds and no overlap with campaign
development work. Renaming a task does not make its ground truth fresh. Reuse the
existing content-based anchor reservation and conservative exposure accounting.

The existing immutable grant must name development and assessment tasks, all
comparison genomes, allowed effects and the shared allocation roots. Validate
these names before dispatch. Resource authority remains in the existing roots and
broker reservations. Neither protocol publication nor a stored task grants authority.

### Assessment admission and lifecycle

Store each admitted round as one immutable `p10.assessment.assignment` decision in
`rsi_decisions`. Its identity is deterministic from campaign and round; its
transaction request also includes the expected agenda revision. Under the agenda
row lock, require that revision, no P01 flight and no unresolved earlier assignment.
Status must be active, or complete with a predeclared final round now due. Suspended
and stopped owners admit no rounds. Insert the assignment and advance revision
without charging a P01 turn. Derive pending assessment from the assignment and existing gate,
operation, episode and verifier records. Do not store a second mutable cursor.

Campaign-owned agendas reject direct public `agenda.wake` calls before execution.
The campaign consumer uses the same internal agenda transition. This prevents a
second public driver from admitting development work while assessment is pending.
Ordinary P05 agendas retain their public wake behavior.

Both development-choice and assessment-assignment admission use that same row
lock. A pending assessment blocks a new development choice even if concurrent
campaign consumers passed their earlier reads. Resolve pending assignment from
immutable assignment and final gate decisions at this boundary; a preliminary
runner check alone is insufficient. A changed revision or controlled status also
refuses development admission before it can create a P01 flight.

Add `suspended` to the existing agenda status constraint. Lifecycle controls take
an expected revision. Suspend prevents new work and preserves the flight and
assessment assignment. Resume reactivates only suspended campaigns. Stop is
terminal for new admissions. Acknowledgement preserves a concurrently committed
suspended or stopped status.

Choice or assessment assignment commit is the admission boundary. If control wins
first, no assignment starts. If assignment wins first, only that already admitted
finite work may finish or remain uncertain. Stop does not promise to cancel a
running gate between its fixed cases. Restart while suspended drives no effects.
Neither stop nor restart refunds or discards unresolved exposure.

`run` resumes an existing assignment first, then admits the next due round, then
advances one P01 choice. It returns on pending or unscored work, lifecycle control,
unchanged or deferred eligibility, deadline, wall bound or call bound. A completed
agenda may still owe its final predeclared assessment; do not drop a due round when
the last P01 acknowledgement reaches the turn cap.

Gate recovery uses its existing operation identities. Repair its current final
`blocked` write for infrastructure exceptions and unknown verifier outcomes.
Those return incomplete with no final score and preserve the same assignment.
A failed pristine test with a known boolean remains a task result. A terminal
infrastructure receipt cannot be retried under a new identity to obtain a result.
Deterministic configuration refusals remain distinct from incomplete effects.

### Applicability and evidence boundaries

P10-D requires a veto at `capability.select`, not just a diagnostic opportunity.
Bind new selections to the requested task and input condition. A verified failed
later native use suppresses future default selections of that exact method,
genome and scope. Reuse checked use and selection evidence; add no mutable
blacklist. Validate the failed use, solution, pristine verifier and settled effects
before applying the veto. Unknown infrastructure outcomes cannot veto applicability.
Preserve already admitted selections on resume. Do not generalize a single failure
to unrelated inputs, tasks or methods. A changed-input P05 probe remains eligible
when supported by its own trigger.

Assessment runs outside P01 feedback capture. Protected task contents, answers,
verifier details and verdicts never enter agenda ranking, P01 context or P02 memory.
Verify that boundary with actual inputs and literal protected-value checks, not
only an artifact access label.

Export protocol and artifact bytes, P05 and P10 decisions, investigations, gate
epochs/runs, exposure reservations, episodes, verdicts, operations and receipts.
Include historical parent checks used by the regression phase. Deduplicate the
resource union by operation identity and keep token and CPU units separate.
Recompute identities and known results from that bundle without database or route
access. Missing or contradictory evidence cannot produce a gain verdict.
Runtime/provider/compute attestations remain labeled; offline consistency checks
cannot authenticate a coordinated rewrite of trusted exports.

Three disjoint implementation lanes own lifecycle, campaign assessment, and
applicability. The coordinator integrates and exercises the public CLI before
Sol High review. Tests first establish a valid export, then challenge mutations.
Use a short prospectively bounded free-route campaign with interruptions after
review. Stop at the declared limits even when the result is incomplete or null.
Extended learning observation is a later use of the campaign, not a condition
for declaring its mechanisms implemented.

### Shared implementation shape

The charter's optional `assessment_protocol` is the published protocol digest.
Protocol JSON uses `schema: "p10-assessment/1"` and a bounded ordered `rounds`
array. Each round names `id`, `after_turn`, `epoch`, `parent`, `candidate`, `model`
and `route_identity`. Turn milestones are nonnegative integers within the charter
turn cap. Round identities are unique and milestones nondecreasing. Route identity
is the SHA-256 of the launcher's base URL with trailing slashes removed, excluding credentials; model
identity is separate. Epoch budget and execution declarations remain authoritative.

The lifecycle lane owns `agenda.control(dsn, agenda_id, expected_revision, action)`
for `suspend`, `resume` and `stop`, plus the common internal `agenda._wake` consumer.
Public `agenda.wake` rejects campaign-owned charters. The same lane owns
`agenda._pending_assessment(cur, agenda_id)`, which returns an immutable assignment
without a matching final gate decision, or `None`. Both admission paths reuse it;
neither infers completion from an empty operation set or a missing score.

The campaign lane owns the protocol parser, artifact publication, assessment
assignment, existing gate integration, public functions and CLI. `start` takes
`campaign_id`, `charter`, `protocol`, `staging_root` and `artifacts_root`. `run`
takes the campaign identity, both launchers, both roots, `max_wakes` and
`wall_seconds`. Lifecycle wrappers use the existing agenda revision. Export and
pure recomputation share one versioned bundle shape rather than separate live and
fixture reports.

The applicability lane binds `capability.select` and `validate_selection` to
required `task_id` and `value` arguments, in addition to the existing genome,
name and interface. Canonical task identity plus value defines the exact requested
condition. Update P01 and all direct callers in the same wave. Admitted historical
choices retain their identity; new selection decisions include the condition and
the checked contrary evidence that caused any veto.

## Delivery slices

1. **P10-1. Run and resume a bounded campaign.** Wire the existing components through one public consumer. Export enough state to inspect why each investigation continued, stopped or remained unresolved.
2. **P10-2. Add longitudinal assessment.** Freeze the applicable comparisons before outcomes, record later-use results and recompute verdicts from exports without a gateway.
3. **P10-3. Observe extended operation.** Run an authorized continuing campaign with planned interruptions and later tasks. Introduce P06–P09 as they become qualified, pinning changed versions for attribution.

## Acceptance scenarios

- **P10-A.** Run multiple learning rounds without the human supplying each next task. Report useful outcomes and intervention count.
- **P10-B.** Stop and restart the process with unfinished work. The same campaign resumes without duplicate effects or erased uncertainty.
- **P10-C.** A route becomes unavailable. Report an infrastructure interruption, preserve pending state and avoid inventing a model or learning failure.
- **P10-D.** A previously retained method becomes inapplicable. Preserve the evidence, stop default use in that scope and make a diagnostic option available to the agenda.
- **P10-E.** Recompute the campaign's claims from exported observations and artifacts. Tamper checks first require a clean unchanged export to pass.
- **P10-F.** Reach a resource or human-defined stop condition. Exit with pending effects identified and a usable continuation, rather than silently resetting the envelope.

Use bounded live operation to qualify the campaign. Extended observation can continue after mechanism delivery. Reports distinguish implemented behavior, observed utility, transfer and improved learning. An incomplete comparison issues no benefit verdict.

## Working checkpoint

The operator can leave the system running within its charter and later understand what it did, learned, rejected and still needs. This closes a connected prototype checkpoint, not production release. Hostile containment, unattended privileged external actions, installation and supported deployment remain separate qualification work under stages 11–12.
