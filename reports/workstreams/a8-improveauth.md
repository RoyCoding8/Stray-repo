# Lane A8 — real authority for the invl02 improve channel

Base: `a4929f2`. Branch: `wt/a8-improveauth`. Offline lane: fixture gateway
only, no live model call, no network.

## The repair

`experiments/ad01/improve_channel.py:_run_source` forwarded `**evidence`
straight into `method_exec.run_step_out_of_process`. A2 deleted the
`dsn is None` branch, so the forward refused with

    refused: execution needs explicit authority and identity

and the refusal propagated out of `drive_improve_round` into the inherited
suite. A6 knew and listed this file in `OTHER_LANES`, which made the
obligation unowned rather than missed.

No source file is trusted because it is local, so there is no exemption to
write. The obligation is met by supplying real authority.

## Where the authority comes from

`frontier.py` holds no `dsn` and no allocation anywhere, and `FrontierStore`
wraps a JSON document. So there is no ledger the invl02 world could consult,
and no caller with an identity to pass down. The honest source is the one
that actually attributes the work: **a disposable store, created before the
execution and dropped after it, with a study allocation bound to it.**

That is A6's construction for the diagnostic paths it migrated, and it makes
the claim stronger rather than weaker. The executions are durable and
attributed while they run, they are separate from any live store by
construction because they never existed before and do not exist after, and
they were obtained by executing the bytes rather than by declining to run
them. Measured cost of the create/migrate/drop cycle is 0.59s, and one
execution takes about 0.48s.

The allocation is bounded in `sandbox_calls`, the resource a `sandbox-exec`
operation actually draws on, rather than in a number chosen to be large
enough. The frontier document remains the authority for how many queries and
steps a round may spend; the disposable store bounds what the executions
behind those decisions cost in the ledger. Those are two different resources
and neither was asked to do the other's job.

`drive_improve_round` holds one store for all its steps, entered lazily at
the first execution. A round resumed from its durable command records
executes nothing, so it mints no authority, spends no allocation and creates
no database. The store's existence stays a claim about work done.

## What changed, smallest first

- `_run_source` now names `authority` and `operation_id` as required
  keyword-only parameters and names every other executor keyword explicitly.
  No `**evidence`, so nothing can arrive untyped and slip past the check at
  this boundary. The check lives here, at the call, rather than only in the
  executor.
- `run_improve_step` and `run_operate_step` take `authority=None` and
  resolve it through one place, `_execution_ledger`. That is the only branch
  in the module: a caller that holds a study store joins it, a caller that
  holds none gets a disposable one. No flag, no context object threaded
  everywhere, no bypass.
- `_execution_ledger` refuses a half-supplied authority rather than silently
  substituting a disposable store, because falling back would let a caller
  that meant to join a study ledger quietly get a different one.
- `_derived_operation_id` derives the identity from what the execution is
  (arm, package digest, view digest), so a re-entry reads a settled receipt
  back instead of re-running, and two executions of different work never
  collide.

## Two defects found while repairing this one

The structural test parses the module rather than grepping it, and it found
a third `_run_source` call site A2's grep had missed.

`revision_evidence_choices` executed revision bytes with a bare
`except Exception: break`. That converted "the executor refused to run these
bytes" into "these bytes chose nothing" — the opposite claim, and it is what
`classify_revision` scores eligibility from. It is now narrowed to the one
exception that genuinely means the child ran and its step was unusable
(`step-failed`); a refusal to execute propagates. A revision nobody executed
has not chosen nothing, it has not been looked at.

The same function then needed a per-step identity. Its loop advances
`state` on each of up to six steps, so one fixed operation id offered the
broker one identity with a different payload per step, and the broker
refused it as a request-identity conflict. The broker was right: those are
different executions. The identity now carries the step index and the view.

## Gate

```
3 failed, 365 passed in 287.49s (0:04:47)
S09ISO: dropped 13 database(s) for this run
```

The three failures are environmental and pre-exist at `a4929f2`. Verified by
running the same three in a throwaway worktree at base, which produced the
identical three with the identical literals:

```
3 failed in 0.76s
```

One is `PermissionError: [Errno 1] Operation not permitted:
'/tmp/identity.json.tmp' -> '/tmp/identity.json'` at `frontier.py:1730`,
and two are `CalledProcessError: git rev-parse HEAD returned 128`. The cause
is that this worktree's `.git` file holds the Windows path
`D:/AI/Agent-Society-v2/.git/worktrees/a8-improveauth`, which git under WSL
cannot resolve. Not chased.

`test_s09c2b_bind.py` / `test_s09m34_bind.py` carry the same 9 failures as at
base (`refused: assessment execution needs the proposal's allocation`), on a
different root cause in `records.py`. Recorded, not fixed.

`test_frontier_atomicity.py` is **fully green**. Its 8 failures at base were
this lane's defect, not pre-existing; they were listed in the assignment as
pre-existing and they were not.

## The seventeen reds

The assignment named seven. At base the same root cause produced **18** across
five files. All 18 are green.

| File | Count |
|---|---|
| `test_binding_provenance.py` | 5 |
| `test_live_integration.py` | 1 |
| `test_provenance_authority.py` | 5 |
| `test_r123_gates.py` | 6 |
| `test_s09_receipt_readback.py` | 2 |

Plus `test_m2_frontier_inherit.py` (7), `test_s09_learner_revision.py` (4),
`test_invl02_causality.py` (2), `test_invl02_route_discovery.py` (2),
`test_s09rev_acquisition.py` (1), `test_s09rev_boundary.py` (3).

They are green because the authority is real, which
`test_the_inherited_reds_are_green_and_their_receipts_are_settled` asserts
rather than assumes: a round resumed from its durable commands would return
the same candidate without executing anything, so the test reads the receipt
the frontier store now holds and requires it to name an operation identity a
real ledger settled. That receipt cannot be produced by a round that executed
nothing.

No assertion was weakened. No test was marked `xfail` or `skip`.

## What the new test proves

`tests/test_inv_a8_improve_authority.py`, 10 tests, all against a real
PostgreSQL database this run created and dropped.

1. `_run_source` cannot execute policy source without authority. Asserted
   structurally three ways: the signature names `authority` and
   `operation_id` with no defaults and no `**kwargs`; every
   executor-reaching call site in the parsed module supplies both, with a
   floor on how many sites were checked so the test fails if it stops
   covering the module; and no `try` around an execution still catches a bare
   `Exception`.
2. With authority, one execution produces an operation row `observed` and
   `settled`, a reservation carrying exposure 91 in state `settled`, and one
   receipt with `outcome = success`. The receipt handed back to the frontier
   store is asserted equal to the receipt identity the ledger decided, so the
   effect cannot settle against an identity nothing settled.
3. Both wrappers are covered, so the operate path is not left unattributed
   while the improve path is fixed.

## Conflict risk with lane C2

`improve_channel.py` is co-owned with C2 and I touched it. My diff is
confined to the authority plumbing: `_run_source`, the two `run_*_step`
wrappers, `revision_evidence_choices`, and the three new helpers
(`_disposable_authority`, `_derived_operation_id`, `_execution_ledger`). C2
should not touch those. The large line count in the diff is mostly the two
loop bodies re-indented by four spaces to sit inside the new `with`, which is
mechanical and will conflict textually if C2 edits the same loops. Worth a
serial merge rather than a concurrent one.

No file outside `improve_channel.py` and my own test was modified. In
particular `frontier.py`, `live_construct.py` and `learner_revision.py` were
read but not touched: their callers needed no change, because the authority
resolves inside the channel at the boundary that already owned the decision.

## What I could NOT prove

1. That the durable rows survive the round. The store is dropped when the
   round ends, by design, so the operation row and its reservation are gone
   by the time any test can read them. The row-level assertions are made
   against a store the caller supplied and still holds. For the disposable
   path I assert the receipt identity, which is the durable fact the frontier
   store keeps, rather than the row it settled against.
2. That a production caller supplies its own study store rather than letting
   the channel mint a disposable one. Every caller I found inherits the
   disposable path. That is the honest default for a world with no ledger,
   but if invl02 is ever driven from a study, that caller must pass
   `authority=` and nothing here verifies it does.