# Stage 9 architecture (draft, proposed, not implemented)

Status: draft. Nothing here is built. Section 7 marks the migration as proposed.

Review status at `1d90c2e`: grounding and the in-place consolidation option are accepted as useful inputs; the package needs refinement before migration. The [architectural assessment](../../reviews/STAGE-08-09-1D90C2E-ASSESSMENT.md) identifies the replay-study limitation, feedback/promotion protocol and missing executable policy-revision contract. The proposals below remain recorded for review and are not a final implementation contract.

## Decision

Consolidate in the current consumer and driver (alternative 1 from
`reports/workstreams/s89-b1.md`). The merged Phase A findings confirm
the conditions that report named. The executor owns its callable
contract (`method_exec.child_contract`, version `ad01-child-v1`). All
four archived candidates execute past the old `NameError` through the
corrected child path, and the live study still retains nothing. A
substituted policy changes admitted behavior through the existing
consumer path (see `reports/STAGE-09-FEASIBILITY.md`). No trajectory
has needed cross-boundary branching, no crash has lost committed work,
and no third instrument exists. The registry in alternative 2 would add
a layer without a missing capability behind it.

## What persists and what does not

The investigation persists. Agents do not. An investigation keeps its
objective, open questions, accepted actions, observations, retained
methods, pending work, and remaining authority across the loss of model
contexts and processes. A participant that resumes reconciles recorded
state instead of inventing replacement work.

## Contracts

Each contract below names its states, its data identities, who writes,
and what failure produces. Existing representations satisfy them, so
no new tables or classes are proposed in this batch.

### Investigation

States: open, questioned, supported, contradicted, retired. Pending
actions move accepted, executed, observed, closed.

Identities: campaign id (`ad01-w<world>-<arm>-<seq>`), attempt id
(`att-<cid>-<seq>`), observation ids, basis references.

Ownership: `trajectory.record_decision` writes the accepted decision
before any effect runs. `trajectory._run_boundary` resumes a recorded
decision without re-deciding. `trajectory.resume_campaign` replays
settled boundaries without duplicate spend.

Failure: a decision without a boundary stays pending and reconciles on
resume. It never re-spends authority.

### Action and instrument

States: versioned, admitted, executed, with a typed result or a named
failure.

Identities: child contract version (`ad01-child-v1`), entry shape
(`ENTRY(task, oracle, max_queries=16)`), operation ids
(`ad01-<cid>-learner-<seq>`, `ad01-<cid>-use-<task>`, member validate
ids), origin labels (`authored-supplied-rpr01`, `host-oracle`).

Ownership: `method_exec.child_contract` owns signatures, return
shapes, and bindings. `packet.public_operations` renders the same
table for the model. `method_exec.verify_member` refuses malformed
members. Domain modules (`worlds`, `seeds`, `controls`, `reducers`,
`checkers`) supply semantics behind the `_family` dispatch. Admission
owns authority and never delegates it to domain code.

Failure: refusal names a reason (`refused: ...`, `malformed-result-
envelope`, `budget-exhausted`). Execution failure keeps its receipt.

### Experience

States: decision-visible input, proposal, admission, operation record,
observation, artifact. Summaries are derived views with provenance.
They never replace the rows they summarize.

Identities: packet digest, proposal derivation
(`records._proposal_from_decision`), retained bytes with recomputed
digests, measured and unknown costs, spend, run id (campaign,
database, freeze digest, model, packet version).

Ownership: `trajectory` appends observations and boundary rows.
`records.export_campaign` reconstructs packets with digests.
`records.verify_byte_chain` and `recompute_accounting` check exports
without new execution.

Failure: unknown costs stay unknown. The checker never scores unknown
as failure and never borrows an unrelated outcome.

### Learning procedure

A learning procedure is executable behavior that selects or composes
context, diagnostics, construction, revision, reuse, and stopping. It
runs through the same admission and execution path as any other
policy, so a substituted procedure changes what the system admits and
executes. Prompt advice alone is not a procedure. A hand-authored
substituted policy is an engineering control, not autonomous
improvement, and stays labeled as one.

Task methods and learning procedures are different retained objects.
A task method solves tasks. Its shape is `ENTRY(task, oracle,
max_queries)` and it is judged by preservation plus size. A learning
procedure decides how to learn. Its shape is proposer plus admission
plus stopping, and it is judged on subsequent independent outcomes
with full cost counted. A wrapper that delegates its whole strategy
to an authored reducer counts as valid execution, not as a novel
algorithm. Retention labels keep that distinction visible.

Ownership: `DecisionConsumer` takes proposer and admission as
constructor arguments. The model policy and the baseline already
share the pipeline. A richer procedure interface is a contract task
for the migration, not a new service.

Failure: a procedure that cannot change admitted behavior through the
real path is advice, not policy, and is rejected as a procedure.

### Branch and replay

A branch pins starting knowledge, policy, and dependencies as one
record. Recorded replay returns a supported outcome only when packet
digest, target and instrument, version fields, code bytes by digest,
dependency order, requested resources, and prefix-only observations
all match. Anything else returns unsupported with a named reason
(`artifact-mismatch`, `unsupported-decision`, `version-mismatch`,
`new-code-bytes`, `dependency-mismatch`, `reordered-dependents`,
`changed-context`, `hidden-future`). Malformed probes return refused.
`doubles.check_replay_prefix` already enforces this boundary.

Predictive simulation is labeled separately. It creates no
observations and spends no authority. A shared task id is never
sufficient for a supported replay.

### Assessment and retention

States: scoped, checked, qualified, useful, transferred, released.
Each is a separate decision with its own evidence.

Identities: scope family, frozen checks, source digest, dependency
identity, measured resources, freeze identity, benefit records.

Ownership: `trajectory.dev_episode` retains only on a `preserved`
verdict with a strictly smaller candidate. `trajectory.run_use`
falls back to the incumbent with a recorded reason. `checker` plus
the frozen benefit rule judge use records. Experiments supply
conditions and judges. They do not implement their own grants,
loops, or accounting.

Failure: rejection records stage and reason. The old member stays.

A policy may never revise its own evaluation authority. It cannot
alter its judge, its visibility rules, or its resource ceiling, and
it cannot claim unseen outcomes as facts.

## Complete example

One walkthrough, showing what the system does at each step without a
new human-written controller between steps.

1. Limitation. On a software task the model policy proposes a
   diagnostic whose seed verdicts disagree. `admit_investigation`
   admits it on recorded basis references. The diagnostic runs and
   its observation joins experience.
2. Construction. The policy proposes development. `construct_method`
   spends init and repair attempts through broker operations, gates
   and executes out of process, and checks preservation.
3. Acquisition. A preserved, smaller candidate retains with bytes,
   digest, scope, and lineage. Anything else rejects with stage and
   reason. The boundary publishes and the loop continues.
4. Retained use. A fresh process loads the frozen repertoire and runs
   a protected task. `_select_member` picks by scope family. Member
   failure falls back to the incumbent with a recorded reason.
5. Scope failure. A method that passes dev tasks but fails protected
   tasks with the same family records failed use records. Today the
   trace stops here. The migration adds the next step.
6. Revision proposal. Failed use opens a pending `revise` action
   pinned to the old member digest. Construction fills it with the
   failure as prior, linked by lineage. The intent is recorded
   before the work, not reconstructed after it.
7. Independent assessment. The revised bytes execute out of process,
   check against the frozen oracle, and run fresh use tasks under
   the unchanged benefit rule and resource ceiling.
8. Retention decision. A preserved improvement on the failed task
   retains and supersedes the old member for its scope. Otherwise
   the old member stays and the attempt records as rejected
   lineage. The pending `revise` action closes either way.

Steps 1 through 4 and 7 through 8 run on current code. Steps 5
through 6 need the revise trigger in section 7. No step mints
budgets, redefines recorded facts, or revises the judge.

## Replay support boundaries

Replay answers what happened on a recorded prefix. It does not
estimate a changed policy. One trajectory per prefix cannot compare
arbitrary policies. A changed action, changed context, or unseen
observation returns unsupported, and that answer is informative and
honest. A changed policy becomes evaluable only with new execution
under pinned versions, or with a corpus that already contains the
matching continuation.

## Keep, change, remove, migrate

| File or area | Verdict | Note |
|---|---|---|
| `experiments/ad01/trajectory.py`, `agenda_policy.py` | Keep, consolidate | Move whole-episode bookkeeping from `_run_boundary` into named consumer methods behind one `reconcile` function |
| `experiments/ad01/method_exec.py` child contract | Keep | A1 put ownership here; prompt and runtime derive from it |
| `experiments/ad01/packet.py` | Keep | Sole packet builder for AD01 |
| `settlement/context.py` packet builders | Remove from AD01 claims | Only `team.py` and `development.py` call them; no silent second packet truth |
| `trajectory.next_decision` | Delete or wire | No production caller; either the real stop rule or gone |
| `run_c3_qualification.py` own loop | Migrate | Becomes a client of the driver instead of a parallel driver |
| Revise trigger plus lineage | Add | Only addition in this plan; failed use opens a pending `revise` action |
| Settlement `context.py`, `artifacts.py` reuse claims | Remove | Asserted, not implemented for AD01 |

## Public usage sketch

```
ad01-traj run --world 0 --arm I        # campaign runs, decisions persist
ad01-traj use                          # frozen repertoire on protected tasks
ad01-traj export                       # transitions with digests and costs
ad01-traj replay                       # supported or unsupported, never borrowed
```

A future mathematics instrument registers a task loader, an oracle,
and a checker behind the versioned instrument contract. It brings no
task ids, judgments, or panel order into the shared runtime.

## Next experiment

See `reports/STAGE-09-FEASIBILITY.md` section 4. Replay
policy-comparison coverage on the committed corpus decides whether
replay can rank policies or the next learner question must be
prospective.
