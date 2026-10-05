# Child-execution cap sheet for the E0 and E12 study allocations

Status: FROZEN before any effect under it. Written 2026-10-04 at
`7a00676`, branch `wt/caps`. Model calls made under this sheet: **0**.
Sandbox executions: **0**. This sheet authorizes nothing retroactively and
reopens nothing below.

It is a **new freeze**, not an amendment. `reports/cap-sheets/a57-prospective-freeze.md`
and `reports/cap-sheets/invl02-live-grant.md` are unchanged and remain the
records they were. Where this sheet's numbers disagree with either, this sheet
is the later record and the disagreement is named in *Corrections to the frozen
sheets* rather than papered over by editing them.

## Why this sheet exists

`0bc02d3` made `drive_improve_round` refuse to execute against an owned store
under a disposable authority (`experiments/ad01/improve_channel.py:2260-2264`).
The production live path supplied none, so restoring it means supplying a real
one. That raised a question no committed sheet answers:

**What is a `sandbox-exec` operation authorized to draw on, under the E0 and E12 study allocations?**

`invl02-live-grant.md` declares E0 at `model_calls` and `construction_calls`
and says nothing about child executions. `invl02_live.py` authorizes E0 at
`:2177-2180` and E12 at `:2640-2643` with the same two names and no third. The
rounds that would now run against those allocations execute out of process, and
an out-of-process execution is a `sandbox-exec` operation, which spends
`sandbox_calls` and reserves units on the allocation. The grant was written
before any round executed against a durable store, so it priced the model and
not the child.

## What the store actually enforces

Measured by running the code at `7a00676`, not read from it.

`settlement.store.is_ceiling_name` accepts a name if it is in
`CEILING_COUNTERS` or `DECLARED_CEILINGS`, tolerating a `max_` prefix on both
(`src/settlement/store.py:102-134`). Verified by import and call:

| name | admitted | enforced |
|---|---|---|
| `model_calls`, `construction_calls`, `sandbox_calls`, `operations`, `execution_units`, `use`, `development`, `repair` | yes | yes |
| `boundaries`, `trajectories`, `diagnostic_queries`, `deadline_s` | yes | **no** |
| anything else | **no**, `authorize_study` raises | n/a |

`sandbox_calls` is an **enforced** name, and `broker._sandbox_exposure`
(`src/settlement/broker.py:154-159`) sizes its reservation. So is
`execution_units`, which the same operation also moves.

**An undeclared ceiling is not a zero ceiling.** `_check_study_ceilings`
(`src/settlement/store.py:1439-1441`) returns immediately when the study's
`ceilings` is empty, and the loop at `:1443-1445` iterates only the names the
study declared. A study that declares `model_calls` and `construction_calls`
and no `sandbox_calls` therefore **admits every child execution** and is bounded
only by its unit allowance. Omitting the name is not a refusal; it is an
unbounded resource wearing a grant's clothes.

That is the finding. The defect is not that the E0/E12 grant forbids child
executions. It is that it does not price them, and a lane now needs to know what
a round costs before it authorizes one.

## What one child execution costs

`broker._sandbox_exposure` returns `timeout_ms // 1000 + STOP_SETTLE_S + 1`.

- `method_exec.STEP_TIMEOUT_MS = 10_000` (`experiments/ad01/method_exec.py:1264`).
- `exec_profile.STOP_SETTLE_S = 30 + 2*15 + 15 + 5 = 80` (`src/settlement/exec_profile.py:312-317`).

Computed by running both:

```
10 + 80 + 1 = 91 units per child execution
```

## How many child executions one investigation makes

Counted by AST over the live path at `7a00676`, then reconciled against the
evidence of the last real run. `improve_channel.py:2307` bounds a round at
`for step in range(3)`. `EXECUTION_LIMITS["max_policy_steps"]` is 6
(`:190`) but that governs `classify_revision`, which this path never reaches:
`learner_revision` appears **zero** times in `scripts/invl02_live.py` and
`experiments/ad01/live_construct.py`, so `admit_revision_under_freeze` and its
`classify_revision` call are off the E0/E12 path. It is not counted.

One `_run_frontier_investigation` call, verified by reading `:1934-2083`:

| step | call site | execs |
|---|---|---:|
| `choose_next_work` for `choice_preserved` | `live_construct.py:1186` | 1 |
| `choose_next_work` for `choice_mismatch` | same | 1 |
| `run_live_improve_round(store, task, active, 1)` | `:1975` | 3 |
| `run_live_improve_round(restarted, task, active2, 2)` | `:1999` | 3 |
| **per investigation, before acquisition** | | **8** |

When the live arm retains an acquisition, `run_e0` calls
`bind_retained_acquisition` (`:2209`), which reaches `bind_live_revision`
(`live_construct.py:1582`) and one further round at `:1525`. **+3.**

The E0 evidence corroborates the count from the other side.
`reports/evidence/invl02-live/e0-run.json` records `live.model_calls: 1` and
`live.boundaries: 1` against `guard.ceiling: 12`, so the run stopped at the
transport before its rounds completed. The count is derived from the code, and
the evidence says the last run never reached the point where it would be
tested.

## The derived ceilings

`WORKER-PROMPT.md:145-146` requires caps derived from the frozen matrix to
include "child executions". They did not, which is what this sheet repairs.

**E0.** Two investigations: the control at `:2191` and the live arm at
`:2200`. The control never acquires, so it never pays the binding round.

```
2 investigations x 8 execs          = 16
+ 1 retained-acquisition binding    =  3
                                    -----
max sandbox_calls                   = 19
19 x 91 units                       = 1729
```

**E12.** Three investigations: P1 at `:2699`, P2 at `:2699`, and the control at
`:2808`. Each of the two arms may retain.

```
3 investigations x 8 execs          = 24
+ 2 retained-acquisition bindings   =  6
                                    -----
max sandbox_calls                   = 30
30 x 91 units                       = 2730
```

`boolean_live_round` (`:2444`) makes model calls only. It reaches no executor,
so it draws on `model_calls` and not on `sandbox_calls`, and it is not counted
here. `_run_p0_boolean` (`:2384`) is fully offline and is not counted at all.

| allocation | authorized units | `sandbox_calls` | `sandbox_calls` cost | headroom |
|---|---:|---:|---:|---:|
| `invl02-live-e0` | 200000 | **19** | 1729 | 198271 |
| `invl02-live-e12` | 400000 | **30** | 2730 | 397270 |

The `authorized` figures are the live values at `invl02_live.py:2178` and
`:2641`, unchanged by this sheet. The headroom is deliberately large. These
are **hard** ceilings on a local process execution, and their purpose is to
make the resource bounded and attributable, not to ration a resource that
competes with anything.

## The decision

**Add `sandbox_calls` to the two existing study ceilings. Do not create a new
allocation.**

This is a change to the **ceiling set**, not to the study root, the allocation
id, or the authorization amount. Concretely, `scripts/invl02_live.py:2177-2180`
and `:2640-2643` gain one key each. The `model_calls` and `construction_calls`
values stay as they are.

### Why not the existing allocation unchanged

An undeclared `sandbox_calls` leaves child executions bounded only by
`authorized` units, as shown above. At 91 units an execution, 200000 units is
2197 executions against a protocol that makes 19. The round would run, and the
grant would be silent about the resource that actually stops it. `a57` lists
"Out-of-process execution carries authority" as a NOT MET precondition; this
sheet is what makes that row answerable.

### Why not a new allocation under the same study root

`authorize_study` is **immutable per study root**
(`src/settlement/authority.py:105-115`). Re-authorizing `invl02-live-e0` with a
different `ceilings` dict raises `ConflictPayload`, not a silent overwrite. So a
new allocation under the same root is not available without either a new root
or editing the existing binding.

A **new root** would be worse. It would give one study two allocations and two
counters for one question. `_study_operation_counts` (`store.py:1550-1559`)
walks the subtree under `study_authority.allocation_id`, so a second root means a
second count, and the E0 protocol's ceiling would be checked against a
counter that does not include the child executions the protocol just priced.
`WORKER-PROMPT.md:158` says "Keep one campaign authority". A second root for the
same leg is two authorities for one leg.

The existing allocation is also the one already carrying the study's history.
`reports/evidence/invl02-live/store-reconciliation.json` shows
`allocation_id: ad01-campaign-invl02-live-e0` with a 3269-unit reservation still
`uncertain` and its operation `unresolved`. That exposure belongs to this
allocation. A new allocation would not carry it, and moving it would edit frozen
evidence.

### What each option does to what an E0 grant authorizes

| option | child executions | the 3269-unit uncertain reservation | counters |
|---|---|---|---|
| existing allocation, unchanged | unbounded until 2197 execs | stays on the allocation | one |
| **existing allocation, `sandbox_calls` added** | **19, refusable** | stays on the allocation | **one** |
| new root | bounded | orphaned, and counted elsewhere | two for one leg |

### The cost that needs recording

Adding a ceiling is a change to a frozen item. `a57` says so itself: *"A change
to any frozen item creates a NEW freeze."* This sheet is that new freeze. It
does not validate the 2026-09-23 E0 run under it, and it does not make that run
comparable to a future one. What it does is bound a resource that was never
priced.

## Corrections to the frozen sheets

Recorded here rather than by editing either file.

1. **`invl02-live-grant.md` declared E0 at `model_calls` and
   `construction_calls` with no child-execution ceiling.** At the time it was
   written that was not a live defect, because every round ran against a
   disposable store whose own `sandbox_calls: 1000` applied
   (`improve_channel.py:1812-1813`) and was discarded with it. It is a defect
   now, because `0bc02d3` routes the round onto the durable allocation.

2. **`construction_calls` is never charged on the E0/E12 path.**
   `_counters_spent_by` (`store.py:1401-1406`) charges the counter only when
   the operation carries `resource == "construction_calls"`, and the live
   path's model admission at `invl02_live.py:934-940` passes no `resource`
   argument. Only `live_construct.py:1745` sets it, on a different code path
   (`LiveOutput.infer`). So the E0 and E12 `construction_calls` ceilings of 4
   and 8 are **admitted and stored but never enforced on these paths**. They
   are not a bound on anything here. That is `a57`'s own `DECLARED_CEILINGS`
   concern in a different costume, and this sheet does not claim to repair it;
   it names it so the lane that owns `invl02_live.py` can decide.

3. **`sandbox_calls` appears nowhere in `a57-prospective-freeze.md`**, verified
   by grep, count 0. Its NOT MET precondition "Out-of-process execution carries
   authority" is the gap this sheet closes for E0 and E12. It says nothing about
   A1, A2 or A3.

## What this sheet does not establish

- It runs nothing. It measures no model and executes no child process.
- It does not qualify a route. `a57` records the route absent on 2026-10-03 and
  this sheet changes nothing about that. I could not re-measure it: the host has
  no `SETTLEMENT_GATEWAY_KEY` and no reachable PostgreSQL, so no live leg can
  run from this lane regardless.
- It does not claim that 19 and 30 are the numbers the study needs. They are
  the numbers the code can make, at the loop bounds it actually has. A deeper
  protocol changes them, and a change is a new freeze.
- It does not verify that a round now succeeds under real authority. That
  requires the four red tests to run in CI, which carries PostgreSQL. Not
  runnable here.