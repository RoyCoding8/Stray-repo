# INV-B2 phase 1: sole ownership and shared-loop design

Scope: lane B2, base `32e2ea2`, branch `wt/inv-b2-state`.
Requirements: INVESTIGATION-01 ranked 1 (admit before effects, resume
identity, no renewal by relabeling), ranked 4 (one resource path,
post-effect reads, measured counters), ranked 5 (prefix-enforced replay,
two-domain calibration before frozen comparison); Qualification 1-6.
Structural brief: three drivers converge the same work with no single
owner. IR-03: allowance reallocation after diagnostic spend.
Principles applied: model-the-domain (data shapes first, §3),
foundational-thinking (one envelope and one driver are scaffold, §4).

## 1. Traced public path (measured, base 32e2ea2)

Prepare path (single, sound): `broker.ensure_operation` (broker.py:244)
is the only writer of `prepared` ops. Callers `team.py:886`,
`experiment.py:100,443`, `development.py` (via its probe/stage submits),
`scripts/agenda01.py` all funnel through it. Keep it.

Dispatch primitives (sound, keep): `broker.dispatch_operation`
(broker.py:374) with advance-then-send, generation fence
(`_revalidate`, `_finish_send`), and `admit_launcher_receipt`
(broker.py:347). `team.dispatch_child` (team.py:1228) is a thin route
into `dispatch_operation`. Keep both.

Three converging drivers (the disease):

- D1 `broker.heartbeat` (broker.py:904) plus `broker.recover`
  (broker.py:935). Heartbeat runs restore-everything, then
  `dispatch_pending`, then its own `restart_reconciliation` reconcile
  loop when `repair_due=True`, then `wake_waiting_workflows`.
  Recover runs a second reconcile loop over the same
  `restart_reconciliation` source with different claim semantics
  (lists even `still-running` ops as `repaired` entries).
- D2 `agenda.repair_scan` (agenda.py:128), a one-line alias for
  `heartbeat(..., gateway=None, repair_due=True)`, paired with
  `agenda.collect_wakeups` (agenda.py:112) as a read that only the
  scheduler couples to driving.
- D3 `scripts/scheduler.run_once` (scheduler.py:25): wakeups, then a
  rounds loop of `repair_scan` plus an extra `broker.dispatch_pending`
  after every round with nonempty `repaired`.

`dispatch_pending` (broker.py:759) is itself a fourth scan (prepared
table plus outbox) called from inside heartbeat and from the scheduler
loop. The sends are safe (atomic `advance_dispatch` dedupes), but
ownership is scattered: four scans, three claim reports, divergent
deferral rules, and no one place that decides an op is parked.

Allowance path (IR-03, measured): `trajectory._run_boundary`
lines 284-287 promise construction `min(requested, remaining-1)`;
line 295 grants the diagnostic the same `remaining-1`; line 332 and
line 363 hand construction the pre-diagnostic number. Diagnostic spend
never reduces the construction allowance. Same-unit-double-promise,
not a one-line slip: nothing in the path sequences sub-budgets.

## 2. Sole owners

- State (operations, attempts, receipts, continuations, wake log):
  the store owns durability through `transact`; the broker owns every
  lifecycle decision through one driver. Agenda keeps typed reads
  (`collect_wakeups` content, eligibility) and typed agenda commands
  (`propose_option`, `select_and_admit`, `record_outcome`,
  `process_wake`); it never scans or advances operations.
- Resource admission: one envelope object in the new loop module
  admits every effect (model, sandbox, diagnostic, construction,
  repair, use) against a single study root. `store.reserve/settle`
  stay the durable mechanism; `team.py:184-186` ad-hoc exposure
  checks move to envelope admission. Trajectory-level `remaining`
  dicts are not a second authority.
- Continuation (wakeups, resume, kill/resume): the loop owns the
  continue step. `wake_waiting_workflows` becomes a private helper of
  the single driver. `agenda.process_wake` stays as the agenda-domain
  typed command and routes continuation through the same step.
- Contracts and rendering: lane B1. This loop consumes B1 packet
  shapes read-only and never redefines them.

## 3. Data shapes first

```python
class Allowance:  # one sequenced grant inside an envelope
    allowance_id: str; kind: str  # diagnostic|construction|repair|use|...
    amount: int; spent_measured: int; spent_unknown: int
    # spent advances only from post-effect reads (receipts, measured
    # counters). Caller-supplied totals never advance it.

class ResourceEnvelope:  # the single study authority
    study_root: str  # grant/allocation root; relabeling never renews
    authorized: int; allowances: list[Allowance]
    ceilings: dict  # frozen pilot ceilings per INVESTIGATION-01 Qual 6
    def remaining(self, kind) -> int: ...  # authorized minus measured
    def admit(self, kind, amount) -> Allowance | Refusal: ...

class ProposedAction:  # model proposes, runtime admits
    target: str; instrument: str; inputs: dict; dependencies: list
    requested: dict  # resource name -> amount, validated nonneg ints
    hypothesis: str | None  # optional; routine acts carry none

class ExperienceTransition:  # persisted per boundary, replayable
    packet_id: str; packet_digest: str; proposal: ProposedAction
    admission: str  # admitted|refused + reason
    operations: list[str]  # operation identities, never bare totals
    results: list[str]  # receipt identities + outcomes incl. unknown
    costs_measured: dict; costs_unknown: list[str]
    continuation: LoopState  # pending action identities for resume

class LoopState:
    objective: str; opportunities: list; observations: list
    questions: list; repertoire: list; actions: list
    policy_versions: dict; envelope: ResourceEnvelope
```

The shared loop is one function over these shapes, both domains:

```
run_boundary(packet, propose, adapters) -> (ExperienceTransition, LoopState)
  materialize: B1 packet (ready or narrow, never silent drop) + wakeup read
  propose:     learner over LoopState, malformed acts are attributed results
  admit:       envelope.admit + ensure_operation (acceptance before effects,
               idempotent sticking request ids, same-action resume identity)
  execute:     broker dispatch + single-driver reconcile; diagnostics,
               construction, repair, use all return through one observation path
  incorporate: receipts into observations, measured spend into allowances
  continue:    LoopState with pending identities, or stop with reason
```

Domain differences enter only through `adapters` (task semantics,
candidate validation, grading), shaped by B1 contracts. Required B1
seam: packet identity plus rendered digest, mandatory content,
evidence bundles, gaps, footprint, and token estimate; outcome
`ready|needs_information|stale`. B1 is unmerged (still at base
`32e2ea2`); phase 2 starts from its merged packet shape and adapts
only the materialize step if field names move.

Envelope rules: post-effect reads after every effect including
diagnostics and failed validations; reporting derived from operation
and receipt identities with measured counters; unknown exposure stays
visible and reserved or refused; sub-budgets sequenced (the IR-03
class fix: construction allowance derives from remaining minus actual
diagnostic spend, never from pre-diagnostic remaining); one root
across stages, repair, use, and databases, so moving work across a
database, task tag, or policy version cannot renew authority.

## 4. Phase 2 deletion and preservation lists

Delete (all inside owned paths, net smaller, no compatibility shims):

- `broker.heartbeat`, `broker.recover`, `broker.dispatch_pending` as
  public drivers, replaced by one `broker.sweep` with an explicit
  mode. `wake_waiting_workflows` folds in as a private helper.
- `agenda.repair_scan` and the `agenda.collect_wakeups` wrapper; its
  two underlying reads (`store.read_events`,
  `steward.due_attempts`) move into loop materialize.
- `scripts/scheduler.run_once` rounds loop; the scheduler becomes a
  thin timer calling `sweep` once per tick and printing one report.
- Hand-rolled allowance math wherever it sits inside owned paths;
  every admission goes through `ResourceEnvelope.admit`.
- Out-of-scope note: `experiments/ad01/trajectory.py` keeps its
  `remaining` dict until the coordinator migrates that caller onto
  the envelope API. Phase 2 exposes the API; it does not edit
  `experiments/**`.

Preserve (historical reproduction entry points, signatures frozen):

- `broker.ensure_operation`, `dispatch_operation`,
  `admit_launcher_receipt`, `reconcile` (primitive),
  `redispatch_after_reset` plus `scheduler.redispatch_reset`,
  `request_cancel`/`note_worker_stopped`/`confirm_cancel`.
- All `store.*` command shapes, migration history, `store.transact`,
  `restart_reconciliation` as the single unfinished-op source.
- Agenda command set and request-id vocabularies; `run_abcs`,
  `run_subsequent_use`, `collect_experience` signatures;
  `reviews/probes/*` frozen files; `evidence*/**` bytes.

## 5. Failing repros (both red on base 32e2ea2)

Drivers (`/tmp/opencode/inv-b2-repro-drivers.py`, disposable Postgres
`inv_b2_repro`, since dropped): one sandbox op advanced to
`dispatching` with no send and a dead launcher. `heartbeat`
repaired it, `scheduler.run_once` (rounds=2) repaired it twice more,
`recover` claimed it a fourth time:

```
reconcile invocations for op-hung: 3 ['op-hung', 'op-hung', 'op-hung']
heartbeat claims: repaired= ['op-hung'] next= work-done
scheduler.run_once claims: repaired= ['op-hung'] rounds= 2 next= repair-done
recover claims: repaired= ['op-hung:unresolved-liability'] next= recovered-1-ops-1-attempts
final state: unresolved
allocation: {'authorized': 100000, 'consumed': 0, 'reserved': 86}
RED: 3 reconciles by 3 drivers claim op-hung with no state change
```

Three counted reconciles (heartbeat one, run_once one per round)
plus recover's own pass make four reconcile passes across three
claimant reports; the op moved `dispatching` to `unresolved` once
and froze with 86 units reserved. One driver would reconcile once
and park it.

Allowance (`/tmp/opencode/inv-b2-repro-allowance.py`, no database;
real `_run_boundary`, real graph diagnostic, real seed episode,
spies record granted budgets only):

```
task: ad01-w0-dev-gr-00
remaining queries before boundary: 6
diagnostic budget granted: 5
diagnostic spend: 4
construction max_queries granted: 5
construction spend: 5
boundary spend returned: 10
sequenced construction allowance (R-1-diagnostic): 1
RED: construction granted 5 after diagnostic spent 4 of 6; boundary spend 10 exceeds remaining 6
```

Software diagnostics spend zero, which is why this needs the graph
task to show: the same six queries were promised to both stages.
Phase 2 envelopes sequence them, so this boundary would grant
construction at most one.

## 6. Phase 2 entry

Blocked only on lane B1 merge for packet field names. On release:
new shared loop module plus envelope, single `broker.sweep`,
scheduler thinning, agenda driver deletions, new tests
`tests/test_inv_b2_*.py` covering the envelope invariant above, one
driver claiming one stuck op exactly once, and kill/resume reusing
settled results. No new database, no second workflow engine, no
silent fallback, no infrastructure-flake labels.

## 7. Phase 2 record (built on merged B1, base `5f75ef6`)

Both phase 1 repros confirmed red on the merged code before any edit:
3 reconciles by 3 drivers with no state change; construction granted 5
after diagnostic spent 4 of 6.

New module `src/settlement/loop.py` owns the shared boundary:
`ResourceEnvelope` (one study root, post-effect reads, sequenced
sub-budgets, honest learner headroom at measured 2600 exposure,
probe allowance separate from study lineage), `ProposedAction`,
`ExperienceTransition` (journaled to the domain event log under a
stable action identity, replayed by `resume_state`), `LoopState`,
`run_boundary` (materialize B1 packets read-only, propose, admit,
execute, incorporate, continue), `admit_effect` (single admission
choke point), `collect_wakeup_events` (single wakeup read).

One driver: `broker.sweep` (claim set, claim-on-transition,
parked short-circuit in `reconcile` with identical decisions).
`dispatch_pending`, `heartbeat`, `recover`, `agenda.repair_scan`,
`agenda.collect_wakeups` and `scheduler.run_once` delegate to it;
the scheduler runs one sweep per tick. `wake_waiting_workflows`
survives as a wrapper over the private continuation step.

Deletions as built: heartbeat/recover/dispatch_pending bodies,
scheduler rounds loop plus per-round dispatch, agenda repair-scan
and wakeup bodies, team hand-rolled reserve math and both free
computations (now `store.free_of` / `_take_reservation`), experiment
direct ensure calls (now `admit_effect`). Net: drivers 3 to 1,
allowance arithmetics to one function. Preserved: all entry
signatures, `recover` report shape, journal/event vocabulary.

Known boundary, not edited (out of scope): the IR-03 double promise
still lives in `experiments/ad01/trajectory.py:284-363`. The class
fix ships here as `sequence_construction_allowance` plus envelope
admission; the coordinator migrates that caller. Same for the
zero-budget probe lineage in `trajectory.dev_episode`: the loop
refuses zero-budget probes without touching lineage and funds probes
from a dedicated allowance; the trajectory caller still needs the
migration.

Gate: `tests/test_inv_b2_loop.py`, 8 passed on disposable
`inv_b2_loop`. Affected suites green with no test touched: broker,
agenda, scheduler, team, experiment, coord02, ad01, B1 gate,
recovery/resume/store sets, 876 passed total. `test_ag01_experiment`
passes 36 here; the reported 24 pre-existing failures did not
reproduce on this base.
