# B14 retention freeze — a new freeze of the B live cap sheet

Status: FROZEN before any effect. Written 2026-10-01 at integration tip `794520f`.
This is a **new freeze**, not an amendment. `reports/cap-sheets/b-live-cap.md`
is unchanged on this branch and remains the record for B11, B12, B13 and B16.

The original sheet recorded B14 as **not allocated**, gated on B3: *"the
repertoire is closed and identical for every arm, so no difference in
`method_id` can be a retention effect."* It closed with: *"They need a new
freeze of this sheet, not a line added to this one."* This document is that
new freeze. B3 landed at `794520f` and opened the gate; opening the gate is
not the same as there being something to measure through it, and the rest of
this sheet says which it is.

## Authority

The same standing authority as its parent (`b-live-cap.md` Authority;
`WORKER-PROMPT.md:28-34`): fresh live experiments on verified free routes,
finite and prospective, token consumption not a concern. This sheet is that
authority made concrete for B14 alone.

**Allocation for B14: a dispatch ceiling of zero.**

Zero is a positive finite ceiling and it is stated as one. The reason is
measured, not assumed, and the measurement is in
`reports/evidence/invr1b14-retention/`. A ceiling is not a budget to be
spent; it is the number the lane is not permitted to exceed. Spending one
send against this sheet is a breach of it, exactly as spending a seventy-ninth
send would be against the parent's.

```text
total_dispatch_cap: 0
total_retry_allowance: 0
total_physical_send_ceiling: 0
campaign_wall_ceiling_ms: 0
per_request_units: 2492
requests: 0
unit_kind: estimated-budget
total_units: 0
carried_in_uncertain_units: 5563
carried_in_true_exposure: >= 5563
carried_in_netted_against_this_allocation: false
required_clusters: 6
alpha: 1/20
cluster_rule: (family, template)
panel: graph:dev+transfer
panel_ceiling: 0.285714
panel_minimum_p: 1/32
dispatches_used: 0
model_id_ends_free: true
```

## Why the ceiling is zero, and the number behind it

B14 needs a run that **acquires a member** and hands a later task a repertoire
holding it, with that member's own bytes giving **different verdicts across
tasks**. Two things must hold. Neither does.

### One: this route's acquired members carry a constant verdict

`invl02_liveacq_r4` is the only study in this tree that acquired members on
this same pinned free route and kept the bytes with their receipts. It
acquired **3 of 6** arms (`reports/evidence/invl02_liveacq_r4/summary.json`,
`acquired: 3`, and its own `live_acquisition: "true"` with all four
acquisition legs passing). Those three members were carried through B3's own
arrival path into a repertoire and measured on every frozen task in their
family by `w2_retention_campaign.retained_leg_verdict`, which executes the
member's own bytes out of process and grades with the frozen checker.

**All three return `preserved` on every task they are carried to.
`distinct_verdicts: ["preserved"]`. `retained_method_leg_measurable: false`,
three members out of three, at 9 tasks each — 27 measured executions.**

That is not three unlucky draws. It is a property of the bytes the route
produced, and the reason is in the bytes themselves:

```
def ENTRY(task, oracle, max_queries=16):
    result = reduce_graph(task, oracle, max_queries=max_queries, method="ddmin")
    return {"candidate": result["candidate"], "queries": result["queries"]}
```

All three name `"ddmin"`. Re-measured against the authored seed at a matched
budget of 16, the `ddmin` members match the authored `seed-*-ddmin` on the
scored observable **9 of 9 tasks, on both families** — the two artifacts are
the same policy under two names.

### Two: the menu is two values wide, and neither moves the verdict

The second and third members were the same call with a different
return shape, not a different strategy, so the strategy axis was swept
directly. `method_exec.child_contract()` offers exactly two direct reducers
differing only in the `method` a member passes, and that choice is the whole
of what a model can vary on this menu.

| family | strategy | distinct verdicts | measurable | reduction identical to seed |
|---|---|---|---|---|
| software | ddmin | `["preserved"]` | no | 9/9 |
| software | greedy | `["preserved"]` | no | 7/9 |
| graph | ddmin | `["preserved"]` | no | 9/9 |
| graph | greedy | `["preserved"]` | no | 0/9 |

**`greedy` does produce a different policy** — 0/9 identical to the seed on
graph, so the choice is real and does change the scored observable. **It does
not produce a different verdict.** A `verdict` that is `preserved` on every
task is a constant, and a constant is exactly the defect
`retained_leg_verdict` was built to refuse. Sweeping the only choice the menu
offers, in both directions, on both families, produces no member whose verdict
varies.

**So: 0 of 4 strategy arms measurable, and 0 of 3 live-acquired members
measurable.** The gate is open and the leg behind it is closed.

### Why this is not repaired by acquiring harder

B12 is the current acquisition run and its number is the honest one: **0 of 4
`python-step` lineages acquired**, three of five sends dying at the route and
the one response that arrived being 5783 characters of prose truncated at
`stop_reason: length` and refused as `unparseable-python`
(`reports/workstreams/b12-swe.md`). B14 cannot run on a route that currently
returns no acquired member, and it cannot run on one that returns only
`ddmin`-shaped members whose verdicts are constant.

Dispatching more lineages would be a search for a positive past a stated
stopping condition. This sheet therefore authorises zero and stops.

## The panel, measured not assumed

The panel is chosen for B14 on the cap sheet's own criteria, and it is the
same panel its parent froze: **`graph:dev+transfer`**. Recomputed here from
source with no model and no dispatch.

| panel | clusters | required | shortfall | powered | ceiling | min p | open rows |
|---|---:|---:|---:|---|---:|---|---|
| `graph:dev+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6/6 |
| `graph:within+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6/6 |
| `graph:dev+within+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 9/9 |

Cluster rule `(family, template)`, alpha `1/20`, so
`minimum_clusters_for_alpha(1/20)` first satisfies `2^(1-n) <= 1/20` at n = 6.
`0.285714` is the census's six-decimal rounding of the exact `2/7`. All three
graph combinations reach six clusters with a positive ceiling, and the
smallest was chosen because it spends the fewest dispatches on the same
power — which at a ceiling of zero dispatches is zero either way. The panel is
recorded because a reader comparing this sheet to its parent must be able to
see that B14 did not quietly move the panel to get its answer.

**A second, independent blocker stands on the same panel.** The frozen
retention panel is `software`/`transfer`, and the qualification gate reads
only `software`, so the campaign's own `qualification_census()` reports
`readable: 0` on it (`w2_retention_campaign.qualification_census`). The three
powered panels are `graph`, and `w2_retention_campaign`'s header states the
gate's five authored policies hardcode a `seed-sw-` method, so a graph target
is refused before any reading is taken. B13b repaired the seed hardcoding on
`wt/b13b-replseed`, not merged here. **B14 would be gated on a live contrast
even with a varying member in hand.** Recorded rather than worked around.

## What was measured, and what was not

**Measured, zero dispatches, on this branch:**

- The three members `invl02_liveacq_r4` acquired live on the pinned free
  route, admitted through `assessment_profile.Repertoire` and executed
  through `method_exec.run_member_out_of_process` on every frozen task in
  their family. 27 executions. **0 of 3 measurable.**
- The strategy axis swept to its full width on both families. 36 executions.
  **0 of 4 measurable.**
- The panel census, re-derived from source.

**Not measured, and not claimed:**

- Whether this route *could* return a varying member at a budget or framing
  nobody has tried. Nothing here bounds that, and nothing here should be read
  as bounding it. Four observations on a menu two values wide is a small
  sample of the route's behaviour.
- Whether an acquired member with a genuinely different walk would have a
  varying verdict. The `reason` field separates `ok-preserved` from
  `ok-incumbent`, and B3's fixture member does vary (`not_preserved` on one
  task, `preserved` on two), so the mechanism works. **B3 proved it with
  bytes written in a test**, and those bytes are not this route's.

**The offline leg was demonstrated and is NOT a live acquisition.** B3's own
fixture member, admitted through the same arrival path and measured the same
way, gives `distinct_verdicts: ["not_preserved", "preserved"]` and
`retained_method_leg_measurable: true` over 9 tasks. That is the instrument
working. Its `origin` is `fixture-stand-in` and it is labelled as such
everywhere it appears, including in the gate, which reads the label out of the
artifact rather than asserting it.

## Per-request unit accounting

Re-derived for this study's own prompt shape, not carried from the parent,
because a unit figure is a property of the request and B14's requests are not
the archived contrast's.

The broker prices one model request at
`exposure_schedule(MODEL_INFERENCE, request, 0)`, which is
`(sum(len(message.content) for message in messages) // 4 + 1 +
max_output_tokens) * (retries + 1)` and is `estimated-budget` units, not a
price and not a dispatch count (`src/settlement/broker.py:149-151`). At the
served budget of **2048** (`max_output_tokens: 2048`, established by B11's
ladder: served at 16/64/256/1024/2048, lost at 4096), and at the parent
sheet's B-shape prompt of `message_characters: 1774`:

```
per_request_units: 2492
requests: 0
unit_kind: estimated-budget
total_units: 0
```

`2492` is `1774 // 4 + 1 + 2048` = `443 + 1 + 2048`, and it is checked
against the archived contrast's own recorded `per_request_units` rather than
asserted. `requests: 0` because this sheet authorises none. The figure is
stated so a later sheet that does dispatch on this route prices at the same
arithmetic; **nothing here is pooled with a run under any other budget.**

`billed` and `charge_units` are **null on every receipt from this route**,
because the adapter reads those two keys and the route reports its price as
`usage.cost` (`reports/evidence/invr1e2contrast/report.json`, `accounting.
discrepancy`). This sheet asserts no provider price in either direction.
Unknown is recorded as unknown and is never written as zero.

## Carried-in historical exposure, accounted separately

Unchanged from its parent and not netted against this allocation. The ledger
records a verified uncertain subtotal of **5563** internal estimated
reservation units, and true exposure is **`>= 5563`** because one further
uncertain reservation is excluded from every reconciliation artifact and
identified nowhere (`reports/PROJECT-LEDGER.md:103-117`;
`other_uncertain_reservations_excluded: 1` in
`reports/evidence/invl02_live/store-reconciliation.json:44`).

**The zero allocation above is independent of the 5563.** Zero is not zero
minus 5563. No historical reservation is reused, settled or netted here, and
no terminal historical round is redispatched.

## The route

Carried from the parent, and unchanged by this sheet:

| Item | Pinned value |
|---|---|
| Endpoint | `http://127.0.0.1:4000/v1` |
| Requested model | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Provider | `nvidia` |
| Tier | `free` |

The requested model id ends in `:free` and no paid fallback is permitted.
The catalog count is **not** pinned: B11 recorded 255, 256, 219 and 203
entries for the same query on the same day, so the precondition is *pinned id
present in the live catalog, re-read at dispatch*, never a count. A read-only
preflight reached the router today and it answered `401` without a credential,
which is a live listener refusing an unauthenticated `GET /models` and is the
cheap preflight `scripts/b11_route_preflight.py` exists for.

**No key value appears in this sheet, in this repository, or in any evidence
file it references.** The gateway reads its key from the environment variable
named by `gateway.api_key_env`, which is `SETTLEMENT_GATEWAY_KEY`; this sheet
names the variable and nothing else. The shipped `LIVE_ENV_PATH` does not
exist on this host, so the value resolves from the router config in
`~/.claude.json`, and this lane's gate reads it to scan its own written bytes
rather than taking this claim on trust. Jev is not called; it is unavailable.

Rate limits, quota and concurrency remain **UNVERIFIED**. Zero sends bound
nothing.

## What is frozen, and what a change costs

Frozen before the first effect: the panel and its split set, the ceiling of
zero, the per-request bounds above (`max_output_tokens: 2048`,
`deadline_ms: 300000`, `reasoning_effort: low`, and
`reasoning_effort_on_the_wire: none-sent` because the chat surface refuses a
request carrying an effort), the stopping condition, and the finding that
zero of this route's members carry a varying verdict.

**A change to any frozen item creates a NEW freeze.** A changed freeze does
not retroactively validate work already run, and **it does not make older and
newer runs comparable.** In particular:

- A different served output budget is a different instrument. A run at 1024
  and a run at 2048 are two instruments and mixing them produces a number
  belonging to neither. B11 established 2048; a lane needing more has a new
  problem, not a bigger number to try.
- **A change to the child menu is a change to what a member can even be.**
  The finding above is bounded by `CHILD_CONTRACT_VERSION = "ad01-child-v1"`
  and its two-strategy menu. If the menu grows a primitive that changes the
  walk, this sheet's negative result does not carry over to it, and a new
  freeze must re-measure the axis rather than inherit this verdict.
- A change to the checker or to the world invalidates the 27 and 36
  executions recorded here.

There is no repair that makes older and newer runs comparable. There is only
a new freeze and an honest report of what each is.

## The stopping condition, stated in advance

The campaign stops at **0 physical sends**, and that is the whole of it. It
also stops immediately, without spending anything, on any of the following.

- A route, catalog, credential or quality precheck fails. Those are
  refusals, not obstacles to route around.
- A credential, a paid tier or a Jev call is requested.
- A dispatch is proposed against this sheet. Its ceiling is zero.

**A stop, an unknown, or a no-member outcome does not authorize a replacement
episode.** A rerun after an apparatus failure is not replication; only a
second independent campaign namespace is. There is no search for a positive
result past this ceiling.

## Preconditions

| Precondition | State |
|---|---|
| Free route present in the live catalog | MET — listener live, preflight answered 401 unauthenticated, pinned id present per B12's re-read at dispatch |
| Standing authority for finite prospective studies | MET — `WORKER-PROMPT.md:28-34` |
| Panel reaches required clusters with a positive ceiling | MET — `graph:dev+transfer`, 6 clusters, ceiling `0.285714`, 6 of 6 rows open |
| Repertoire admits a method acquired on a prior task | MET — `assessment_profile.Repertoire`, landed by B3 at `794520f` |
| **A member whose verdict varies across tasks exists** | **NOT MET** — 0 of 3 live-acquired and 0 of 4 strategy arms measurable |
| **Acquisition returns a member at the current rate** | **NOT MET** — B12 returned 0 of 4 lineages; the last live acquisition before it returned 3 of 6, all constant-verdict |
| Panel readable by the qualification gate | **NOT MET** — `qualification_census` reads 0 rows; the seed hardcoding is repaired on `wt/b13b-replseed`, unmerged here |
| Confined read denial | NOT MET — WSL2 kernel rejects Landlock; needs bare metal |
| Rate limits, quota, concurrency | UNVERIFIED — treated as unknown headroom |

**No dispatch is authorized while any row reading NOT MET above sits on the
dispatch path of the study.** Two of them do, which is why the ceiling is
zero. Recording the gap is not removing it.