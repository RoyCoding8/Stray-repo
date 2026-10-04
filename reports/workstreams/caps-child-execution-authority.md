# Caps lane: what a child execution draws on, and why the answer is a third ceiling

Lane owned `reports/cap-sheets/e0-e12-child-execution-caps.md` and this file.
Nothing else was edited. No Python was touched, no test was touched, and no
frozen cap sheet was rewritten.

## The question

Four CI failures are open because `0bc02d3` made `drive_improve_round` refuse
an owned store under a disposable authority. The fix is to supply real
authority, which means authorizing the round against a real allocation.

The triage lane stopped on a real problem, and it is worth stating precisely
before answering it, because the problem is different from how it was framed.

**`reports/cap-sheets/invl02-live-grant.md` declares E0 at `model_calls` and
`construction_calls` with no `sandbox_calls`. `_disposable_authority` is
bounded in `sandbox_calls`. So a round moved onto a real allocation would draw
on a ceiling that allocation does not carry.**

Every clause of that is true. The inference drawn from it is not.

## What `_disposable_authority` bounds, with what values

Read in full at `experiments/ad01/improve_channel.py:1787-1817`.

```python
handle = _authority.authorize_study(
    database.dsn, _isolation.study_root_for(token),
    authorized=1_000_000, allocation_id="%s-alloc" % token,
    ceilings={"sandbox_calls": 1_000})
```

It sets exactly **one** ceiling. Not a set.

| field | value |
|---|---:|
| `authorized` | 1,000,000 units |
| `ceilings` | `{"sandbox_calls": 1000}` — one key |
| `allocation_id` | `"<token>-alloc"` |
| `study_root` | `s09_run_isolation.study_root_for(token)` |
| `correction_budget` | default 2 (never passed) |

`no model_calls. no construction_calls. no execution_units. no operations.`
The other three are not refused. They are **undeclared**, and the distinction
is the whole answer.

## What an undeclared ceiling actually does

This is the fact the triage lane was one inference short of, and I verified it
by running the store module rather than by reading it.

`_check_study_ceilings` (`src/settlement/store.py:1419-1461`):

```python
ceilings = dict(row["ceilings"] or {})
if not ceilings:
    return
...
for name, raw_limit in ceilings.items():
    if _ceiling_counter(name) not in spent:
        continue
```

The loop iterates **only over names the study declared**. There is no default,
no fallback, no "resource not declared means zero". A study that declares two
ceilings is checked on two counters and no others.

So:

**A missing `sandbox_calls` does not refuse a child execution. It declines to bound it.**

The round runs. It is stopped, if it is ever stopped, by the unit allowance, not
by a ceiling. At 91 units per execution (derived below), E0's
`authorized=200000` is 2197 executions against a protocol that makes 19. The
grant is silent on the resource that would actually stop it.

That reframes the decision. There is no refusal to work around, and no risk of
"drawing on a ceiling that does not exist". There is a genuine hole in a grant,
which is a cap-sheet problem, which is what I own.

## `is_ceiling_name`, measured

`src/settlement/store.py:129-134`, called rather than read:

| name | admitted | enforced |
|---|---|---|
| `model_calls`, `construction_calls`, `sandbox_calls`, `operations`, `execution_units` | yes | yes |
| `calibration`, `development`, `repair`, `use` | yes | yes |
| `boundaries`, `witness_queries`, `dev_episodes`, `lineages`, `deadline_s`, `trajectories`, `diagnostic_queries` | yes | **no** |
| anything else | `authorize_study` raises | n/a |

`sandbox_calls` is in `CEILING_COUNTERS` and is enforced. `DECLARED_CEILINGS` is
the store's own record of names it accepts and never checks, and its comment
explains why refusing them was once the worse failure. I am not proposing to
use any of them.

## Every allocation the E0/E12 live path already creates

Five `authorize_study` call sites exist in `scripts/` and the live ones are
these three, all routed through `trajectory.authorize_campaign`
(`experiments/ad01/trajectory.py:156-167`) and `invl02_live._authorize`
(`:1822-1827`):

| allocation | study root | authorized | ceilings |
|---|---|---:|---|
| `ad01-campaign-invl02-live-e0` | `invl02-live-e0` | 200000 | `model_calls` = `freeze.bounds.model_calls` (12), `construction_calls` = 4 |
| `ad01-campaign-invl02-live-e12` | `invl02-live-e12` | 400000 | `model_calls` = `freeze.bounds.model_calls` (80), `construction_calls` = 8 |
| output study (`_output_study_ceilings`, `:1803-1820`) | `invl02-live-output` | 200000 | `model_calls` = `max_dispatches` or 8, `construction_calls` = `max(max_construction_calls, 1)` |

**The live path holds a study allocation per `reports/workstreams/m1-lane-b11-findings.md`, and it does NOT carry `sandbox_calls`.** Established from the code above and corroborated by
`reports/evidence/invl02-live/store-reconciliation.json`, which reads back the
E0 row as `authorized_units: 200000` with no third ceiling. That is the gap.

The other `authorize_study` callers are not on the E0/E12 path: `s89_diagnose`,
`e2_contrast_gate`, `e2_replication`, `e3_ladder`, `experience_axis_run`,
`invr1b11/b12/b17`, `s09_bound_use_proof`, `s09_m2_reload_proof`,
`s09_run_isolation.RunIsolation.build` (which passes **no ceilings at all**,
`:318-322`), `s09_study_preflight`, and `trajectory.authorize_campaign` itself.
`invl02_live.py:2275` subdivides a *child* allocation for `restart_use`, which
is a reuse leg and not the round this lane is pricing.

## The derived numbers, and where each came from

**Units per child execution.** `broker._sandbox_exposure`
(`src/settlement/broker.py:154-159`) is
`timeout_ms // 1000 + STOP_SETTLE_S + 1`. Computed by importing both constants:

```
method_exec.STEP_TIMEOUT_MS = 10000   (experiments/ad01/method_exec.py:1264)
exec_profile.STOP_SETTLE_S = 80       (30 + 2*15 + 15 + 5; exec_profile.py:312-317)
10 + 80 + 1 = 91
```

**Steps per round.** `drive_improve_round` runs `for step in range(3)`
(`improve_channel.py:2307`). Three.

`EXECUTION_LIMITS["max_policy_steps"]` is 6 (`:190`) and is **not** counted. It
governs `classify_revision`, reached only through `admit_revision_under_freeze`,
reached only through `learner_revision`. `learner_revision` appears **zero**
times in both `scripts/invl02_live.py` and `experiments/ad01/live_construct.py`
(grep, count 0). Off this path.

**Executions per investigation.** AST over the live path, then read:

| step | site | execs |
|---|---|---:|
| `choose_next_work` × 2 | `live_construct.py:1186` | 2 |
| `run_live_improve_round(..., 1)` | `invl02_live.py:1975` | 3 |
| `run_live_improve_round(..., 2)` | `invl02_live.py:1999` | 3 |
| | | **8** |

Plus 3 when the arm retains an acquisition, via `bind_retained_acquisition`
(`:2209`) → `bind_live_revision` (`live_construct.py:1582`) → one round at
`:1525`.

**E0** = 2 investigations (`:2191` control, `:2200` live) + 1 binding round:
`16 + 3 = 19`. `19 × 91 = 1729` units against 200000.

**E12** = 3 investigations (`:2699` ×2 arms, `:2808` control) + 2 binding
rounds: `24 + 6 = 30`. `30 × 91 = 2730` units against 400000.

Not counted, and why: `boolean_live_round` (`:2444`) makes model calls only and
reaches no executor. `_run_p0_boolean` (`:2384`) is fully offline.

## The decision, and why the alternatives are worse

**Add `sandbox_calls` to the two existing study ceilings. Change the ceiling
set, not the study root, the allocation id, or the authorization.**

| option | child executions | 3269-unit uncertain reservation | counters for one leg |
|---|---|---|---|
| existing allocation, unchanged | unbounded until 2197 execs | stays put | one |
| **existing allocation, `sandbox_calls` added** | **19 / 30, refusable** | stays put | **one** |
| new allocation, same root | not available | stays put | one |
| new allocation, new root | bounded | **orphaned** | **two** |

**Same root, new allocation is not on the table at all.** `authorize_study`
treats the authority fields as immutable per study root
(`src/settlement/authority.py:105-115`): re-authorizing with a different
`ceilings` dict raises `ConflictPayload`. I confirmed the guard by reading it,
not by running it, because running it needs a store and this host has none.

**A new root is the one that could have been tempting and is the worst.** It
gives one leg two allocations and two counters. `_study_operation_counts`
(`store.py:1550-1596`) walks the subtree beneath
`study_authority.allocation_id`, so a second root is a second count, and E0's
ceiling would be checked against a counter that excludes the executions the
protocol just priced. `WORKER-PROMPT.md:158` says "Keep one campaign
authority."

**The existing allocation is also the one holding the history.**
`store-reconciliation.json` records a 3269-unit reservation still `uncertain`
and its operation `unresolved`, under `ad01-campaign-invl02-live-e0`. That
exposure belongs to this allocation. A new allocation would not carry it, and
moving it would edit frozen evidence, which `WORKER-PROMPT.md:41-45` forbids.

**On WORKER-PROMPT.** "A missing grant file is setup work, not a reason to
request the same authorization again" (`:139`) means I write the sheet rather
than escalate, and I have. `:145-146` names "child executions" among the caps
that must be derived from the frozen matrix. They were not derived before, which
is what this sheet supplies. So this decision is what WORKER-PROMPT asks for,
not an exception to it.

## The frozen sheets

Neither was edited. `a57-prospective-freeze.md` and `invl02-live-grant.md` are
unchanged and byte-identical to `7a00676`.

Two corrections are recorded **in the new sheet** instead:

1. `invl02-live-grant.md` prices E0 without a child-execution ceiling. Not a
   live defect when written, because every round then ran against a disposable
   store whose own `sandbox_calls: 1000` was discarded with it. It is one now.

2. **`construction_calls` is never charged on the E0/E12 path, so the E0 value
   of 4 and the E12 value of 8 bound nothing there.**
   `_counters_spent_by` (`store.py:1401-1406`) charges the counter only when the
   operation carries `resource == "construction_calls"`. The live path's model
   admission at `invl02_live.py:934-940` passes **no `resource` argument**. The
   only `resource="construction_calls"` in the live tree is
   `live_construct.py:1745`, on `LiveOutput.infer`, a different path.

   So E0's `construction_calls: 4` is stored, admitted, and never checked on
   this path. That is `DECLARED_CEILINGS`' exact concern in different clothes, and
   it is a **finding for the lane that owns `invl02_live.py`**, not something I
   repair from a cap sheet. It does not affect the decision above.

## Code spec for the lane that owns `scripts/invl02_live.py`

Their file. Not mine. Precise enough to apply without re-deriving anything.

**Spec 1, the cap sheet.** `run_e0` at `:2177-2180` becomes:

```python
authority = _authorize(
    dsn, STUDY_ROOT_E0, 200000,
    {"model_calls": freeze["bounds"]["model_calls"],
     "construction_calls": 4,
     "sandbox_calls": E0_CHILD_EXECUTION_CEILING})
```

`run_e12` at `:2640-2643` becomes:

```python
authority = _authorize(
    dsn, STUDY_ROOT_E12, 400000,
    {"model_calls": freeze["bounds"]["model_calls"],
     "construction_calls": 8,
     "sandbox_calls": E12_CHILD_EXECUTION_CEILING})
```

`authorized` is unchanged at 200000 and 400000. Define the two constants beside
`STUDY_ROOT_E0` and `STUDY_ROOT_E12` (`:34-35`) as `19` and `30`, with
`reports/cap-sheets/e0-e12-child-execution-caps.md` named in the comment.

**Spec 2, and this is the one that will bite.** `_already_spent`
(`:245-284`) is

```sql
SELECT COUNT(*) AS spent FROM operations WHERE allocation_id = %s
```

It counts **every** operation under the allocation. Its own docstring names the
currency as "a send that reached the store", and that was true when the only
rows under this allocation were model dispatches. It is no longer.

Once the rounds execute here, each child execution writes an operation row, so
`_already_spent` starts counting sandbox executions as model calls. It feeds
`ceiling=freeze["bounds"]["model_calls"] + already_spent`
(`:2199`) and E12's per-arm guard (`:2683`). The guard would then refuse the
live arm's **first** model call, because 8 sandbox rows already exceed the
model ceiling of 12 by the time the acquisition dispatch is reached.

The fix is one predicate, matching what `_output_already_spent` (`:1386-1400`)
already does with its explicit id set: filter by effect.

```sql
SELECT COUNT(*) AS spent FROM operations
 WHERE allocation_id = %s
   AND payload->>'effect' = 'model-inference'
```

This is required by Spec 1 and is not optional. Applying Spec 1 without it turns
a silent hole into a hard refusal of the study's own first dispatch.

**Spec 3, verify, do not assume.** `authorize_study` is immutable per root, so
re-running E0 against the **existing** `invl02_live` store will raise
`ConflictPayload` on the changed `ceilings`. The lane needs a fresh store, or a
new store name, for the first run under the new ceiling set. Note this in the
run record. Do not edit `study_authority` in place.

**Spec 4, the tests.** `tests/test_inv_a8_improve_authority.py:170-197` counts
executor-reaching calls and asserts `checked >= 4`. Spec 1 and 2 add none.
`tests/test_inv_a8_improve_authority.py:231-247` requires
`_disposable_authority` to remain in `drive_improve_round`'s body. Neither is
touched by this change. Both lanes own that file, not this one.

## What I could not do

- **I did not run the test suite.** PostgreSQL is unreachable on this host
  (`SETTLEMENT_TEST_DSN` unset, `postgresql://localhost` times out, no `pg_ctl`,
  no Docker), and WSL is out of scope for this lane. So the immutability guard
  at `authority.py:105-115`, the empty-ceilings early return at
  `store.py:1439`, and the four CI failures are established **by reading and by
  importing pure functions**, not by running them. The import-derived facts
  (`is_ceiling_name`, `STOP_SETTLE_S`, `STEP_TIMEOUT_MS`, the 91) were computed
  by running them.
- **I did not measure a real round's execution count.** 19 and 30 are derived
  from the loop bounds in the code, not from a completed run. The last E0 run
  stopped at the transport (`e0-run.json`: `live.model_calls: 1`,
  `guard.ceiling: 12`, and `store-reconciliation.json` shows the operation
  `unresolved` on a gateway timeout), so no run has ever completed a round here
  to confirm the count.
- **I did not verify a live route.** `a57` records it absent on 2026-10-03. I
  did not re-measure it, and nothing in this lane depends on it.

## Principles applied

*Attack the premise.* The triage lane's inference was that a round "would draw
on a ceiling that allocation does not carry", implying refusal. Establishing the
predicate in `_check_study_ceilings` turned it into a boundlessness problem, and
that reframing is what made the decision answerable rather than blocking.

*Prove it works.* Every ceiling-name fact was obtained by calling
`is_ceiling_name`, and both unit constants by importing them. The 36 line
citations in the cap sheet were checked mechanically against the files; six were
wrong and were corrected before the sheet was considered finished.

*Minimize reader load.* One new sheet carrying the arithmetic, and this file
carrying the reasoning and the spec. Neither frozen sheet was touched, and the
two corrections live in the new record rather than as edits to history.