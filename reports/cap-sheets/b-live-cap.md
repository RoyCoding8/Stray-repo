# B live cap sheet — milestone-B prospective studies

Status: FROZEN before any effect. Written 2026-10-01 at integration tip `75cab06`.
This is a NEW study root with explicit allocation. It reuses no grant, settles no
unknown, replays no historical round and does not discharge any prior
authorization. `reports/cap-sheets/invl02-live-grant.md` and
`reports/cap-sheets/w1-e1-cap.md` remain the records for the work they describe and
are unchanged by this sheet.

## Authority

The human authorized fresh live experiments on verified free routes and stated that
token consumption is not a concern. That is standing authority for the finite
prospective studies in this assignment (`WORKER-PROMPT.md:28-34`). This sheet is
that authority made concrete, and it is written before the first dispatch because
establishing the served output budget is itself a dispatch. A missing grant file is
setup work, not a reason to ask again.

## The matrix, and why this panel

B8 enumerated every non-empty combination of the three splits the frozen world
offers, per family, fourteen panels in total
(`reports/evidence/invr1b8-panel-census/census.json`, `model_calls: 0`). The cluster
rule is `(family, template)` and alpha is `1/20`, so
`minimum_clusters_for_alpha(1/20)` first satisfies `2^(1-n) <= 1/20` at n = 6.

The supported panel is **`graph:dev+transfer`**. It is the smallest combination that
reaches six clusters, its cluster count is 6, its shortfall is 0, its ceiling is
`0.285714`, its minimum attainable p is `1/32`, and all 6 of its 6 rows are open. It
is the only family that can carry the experience contrast at all. Two larger graph
combinations also reach six clusters with the same ceiling, `graph:within+transfer`
and `graph:dev+within+transfer`, and the smallest was chosen because it spends the
fewest dispatches on the same power.

| panel | clusters | required | shortfall | powered | ceiling | minimum p | open rows |
|---|---:|---:|---:|---|---:|---|---|
| `graph:dev+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6/6 |
| `graph:within+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6/6 |
| `graph:dev+within+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 9/9 |
| `software:dev` | 2 | 6 | 4 | no | 0.312500 | 1/2 | 1/3 |
| `software:within` | 2 | 6 | 4 | no | 0.000000 | 1/2 | 0/3 |
| `software:transfer` | 2 | 6 | 4 | no | 0.285714 | 1/2 | 2/3 |
| `software:dev+within` | 2 | 6 | 4 | no | 0.312500 | 1/2 | 1/6 |
| `software:dev+transfer` | 4 | 6 | 2 | no | 0.312500 | 1/8 | 3/6 |
| `software:within+transfer` | 4 | 6 | 2 | no | 0.285714 | 1/8 | 2/6 |
| `software:dev+within+transfer` | 4 | 6 | 2 | no | 0.312500 | 1/8 | 3/9 |

The three `graph` rows are the only powered panels; the ten `software` rows are the
unpowered remainder, and the four unpowered graph panels are omitted from this table
because this sheet allocates nothing to them. `powered_but_blind` is empty, because
every panel that reaches six clusters also has a non-zero ceiling. A powered-but-blind
panel would be a different world. The census rounds its ceiling to six decimal places;
`0.285714` is the rounded value and `2/7` is the exact one.

The software family cannot carry the contrast on any combination.
`software_templates_in_frozen_world: 4` against `required_clusters: 6`, so the
shortfall is at least two everywhere and no split choice could have saved the archived
runs. Both ran the software panel, which is why
`reports/evidence/invr1e2contrast/report.json` records `sign_flip.minimum_p: "1/2"`
against `required_clusters_at_alpha_1_20: 6`. This is a power defect and a panel
choice repairs it. It is not the retention closure, which no panel moves, and this
sheet claims no retention result.

## The route

| Item | Pinned value |
|---|---|
| Endpoint | `http://127.0.0.1:4000/v1` |
| Requested model | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Provider | `nvidia` |
| Tier | `free` |
| Catalog | 219 entries, 32 free-tier, the pinned id present unprefixed, live read 2026-10-01 |
| Key variable | `SETTLEMENT_GATEWAY_KEY` |
| Endpoint variable | `SETTLEMENT_GATEWAY_ENDPOINT` |

The 256-entry catalog that the archived probe recorded is superseded. Today's live
catalog has 219 entries and the pinned id is present, so the archived
`frozen-model-absent-from-catalog` finding no longer describes this route
(`reports/PLAN.md`, ROUTE row, live catalog read 2026-10-01). The absence finding is
history and is not restated as a current precondition.

**No key value appears in this sheet, in this repository, or in any evidence file it
references.** The key lives in an environment file outside Git, mode 600, and the
sheet names the variable and nothing else. No paid fallback is permitted. Jev is not
called. Rate limits, quota and concurrency on this route are **UNVERIFIED**; two
probe calls cannot characterise them, so reserve headroom is treated as unknown
rather than as available.

## The output budget is UNRESOLVED

**Status: UNRESOLVED. This sheet does not establish it and must not be read as
having established it.**

The recorded 502 tracks the requested output budget, not the prompt. Against the same
campaign prompt this route returns HTTP 200 at 16 and at 256 output tokens, returns
502 at the protocol's own 2048, and a short prompt returns 200 at 2048
(`reports/evidence/w1-e1-boolean-r3/route-probe.json`, finding
`output-budget-causes-the-502`; `probes.campaign-prompt-budget-16.status: 200`,
`probes.campaign-prompt-budget-256.status: 200`,
`probes.campaign-prompt-budget-2048.error: "TimeoutError: timed out"` at 182.06
seconds, and `probes.short-prompt-budget-2048.status: 502` with
`error_type: "empty"`). Every campaign currently caps `max_output_tokens: 2048`.

Which budget this route actually serves is therefore unknown. Establishing it costs
dispatches, so it is the first bounded item in this sheet and the first thing any
operator does, not an assumption this sheet is allowed to make. `B11` below is that
measurement, with its own cap and its own exclusions. **Its outcome is a new freeze.**
A changed output budget creates a new freeze and does not make older and newer runs
comparable, so nothing produced under one budget may be pooled with anything produced
under another. The unit figures in this sheet are derived at 2048 and are re-derived
by the formula the moment B11 returns.

## The dispatch caps

Per-request bounds, carried from the archived contrast cap sheet
(`reports/evidence/invr1e2contrast/report.json`, `cap_sheet.bounds`) so that B and the
archived E2 contrast are priced the same way: `max_output_tokens: 2048`,
`deadline_ms: 300000`, `reasoning_effort: low`, and
`reasoning_effort_on_the_wire: none-sent` because the chat surface refuses a request
carrying an effort, so no request in these campaigns sends one and the receipt records
no effort rather than a control the wire never applied.

| study | dispatches | retries | physical sends | basis |
|---|---:|---:|---:|---|
| `B11` served output budget | 6 | 0 | 6 | one ladder rung each at 16, 64, 256, 1024, 2048 and 4096 output tokens on the campaign prompt |
| `B12` SWE construction and use | 24 | 1 | 25 | 4 lineages x (1 initial construction + at most 1 repair) = 8, plus 4 lineages x 4 held-out instances = 16 |
| `B13` E2 contrast, powered panel | 37 | 1 | 38 | 3 arms x 6 rows x 2 constructions = 36, plus 1 route probe |
| `B16` acquired bytes, new process | 8 | 1 | 9 | 4 lineages x 2 held-out families, use only, no construction and no repair |
| **total** | **75** | **3** | **78** | |

`total_dispatch_cap: 75`, `total_physical_send_ceiling: 78`,
`campaign_wall_ceiling_ms: 22800000`, which is 78 sends x 300000 ms, the sum of every
request's own deadline under a serial broker. `B11` carries no retry allowance
because a retry at a fixed budget re-measures the same rung and answers nothing.

```text
total_dispatch_cap: 75
total_retry_allowance: 3
total_physical_send_ceiling: 78
campaign_wall_ceiling_ms: 22800000
per_request_units: 2492
requests: 78
unit_kind: estimated-budget
total_units: 194376
carried_in_uncertain_units: 5563
carried_in_true_exposure: >= 5563
carried_in_netted_against_this_allocation: false
required_clusters: 6
software_templates_in_frozen_world: 4
alpha: 1/20
cluster_rule: (family, template)
```

`B14` and `B15` are **not allocated and not in this total.** `B14` (retention and
adaptation) is gated on B3, because the repertoire is closed and identical for every
arm, so no difference in `method_id` can be a retention effect. `B15` (the selection
comparison) is gated on B7, because the construct, reuse and continue decisions do not
exist yet. Both are listed at zero so a reader can see they were considered and
declined rather than forgotten. They need a new freeze of this sheet, not a line
added to this one.

## Per-request unit accounting

The broker prices one model request at
`exposure_schedule(MODEL_INFERENCE, request, 0)`, which is
`(sum(len(message.content) for message in messages) // 4 + 1 + max_output_tokens) * (retries + 1)`
and is `estimated-budget` units, not a price and not a dispatch count
(`src/settlement/broker.py:149-151`).

At the frozen B request shape of `message_characters: 1774` and
`max_output_tokens: 2048` that is `1774 // 4 + 1 + 2048` = `443 + 1 + 2048` = **2492
units per request**, which is the archived contrast's own `per_request_units`, so the
derivation is checked against a recorded number rather than asserted.

`per_request_units: 2492`, `requests: 78`, `unit_kind: estimated-budget`,
`total_units: 194376` = 2492 x 78. A retry is charged as its own request, exactly as
the archived sheet charges its nineteenth send.

`billed` and `charge_units` are **null on every receipt from this route**, because the
adapter reads those two keys and the route reports its price as `usage.cost` instead
(`reports/evidence/invr1e2contrast/report.json`, `accounting.discrepancy`). This sheet
therefore asserts no provider price in either direction. It is not a statement that
the route is free and not a statement that it is not. Unknown is recorded as unknown
and is never written as zero. A free tier does not make usage, compute or
experimental opportunity unmeasured.

Every call, success, failure, refusal, empty response, lost response and unknown is
counted. The five failure modes stay distinct fields in durable receipts; they are
never collapsed into a zero.

## Carried-in historical exposure, accounted separately

This is **not** settled, **not** identified in full, and **not** subtracted from the
allocation above. The ledger records a verified uncertain subtotal of **5563** internal
estimated reservation units, and true exposure is **`>= 5563`** because one further
uncertain reservation is excluded from every reconciliation artifact and identified
nowhere (`reports/PROJECT-LEDGER.md:103-117`;
`other_uncertain_reservations_excluded: 1` in
`reports/evidence/invl02-live/store-reconciliation.json:44`). The two verified terms
are `res-invl02-output-872608eb94c3-P1-audit-0023-a1` at 2294 and
`res-ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-construct-l1-init` at 3269.

**The 75-dispatch and 194376-unit allocation above is independent of the 5563.** It is
a fresh root against the broker's exposure schedule, and 194376 is not 194376 minus
5563. Closing the historical gap needs one read-only query against the `invl02_live`
store, which this host cannot reach; that is a named blocker on a different grant, not
a debt this sheet pays. No historical reservation is reused, settled or netted here,
and no terminal historical round is redispatched.

## What is frozen, and what a change costs

Frozen before the first effect: source tip, endpoint, requested model id, provider,
tier, reasoning effort and the fact that none is sent on the wire, the panel and its
split set, the three experience arms and their size matching, the construction and
repair loop, the decision grid, the held-out instance set, the selectors, the
per-request bounds above, and every ceiling in this sheet. A study pins its exact
protocol before its own first effect and never changes limits midway.

**A change to any frozen item creates a NEW freeze.** It does not retroactively
validate work already run, and it does not make old and new runs comparable. The
served output budget is the item most likely to change, and the one whose change
costs the most comparability: the 502 in the archived probe is a budget fact, not a
prompt fact, so a run at 1024 and a run at 2048 are two instruments. Mixing them
would produce a number that belongs to neither. There is no repair that makes older
and newer runs comparable. There is only a new freeze and an honest report of what
each is.

## The stopping condition, stated in advance

The campaign stops when **78 physical sends** have been made or refused, when
**6 B11 ladder rungs** have been measured, or when the **30-day** wall ceiling from
this sheet's date expires, whichever comes first. It also stops immediately, without
spending the remainder, on any of the following.

- The route answers 502 or times out on the B11 ladder at the lowest rung, because
  that is a route fact no later study can spend its way out of.
- A study's dispatches are exhausted with its matrix unfilled. The unfilled cells are
  recorded as missing with their concrete limitation. A missing cell is not an
  authorization to try again, to substitute an authored arm, or to redispatch a
  terminal round.
- A quality gate, selection gate or freeze check fails. A skipped regression is not a
  pass.
- A credential, a paid tier or a Jev call is requested. Those are refusals, not
  obstacles to route around.

A stop, an unknown, or a no-candidate outcome does not authorize a replacement
episode. A rerun after an apparatus failure is not replication; only a second
independent campaign namespace is. Sampling and selection rules are fixed here,
before assessment. There is no search for a positive result past the stopping
condition, and the free tier is not a reason to widen any of these numbers.

## Preconditions

| Precondition | State |
|---|---|
| Free route present in the live catalog | MET — 219 entries read 2026-10-01, pinned id present unprefixed |
| Standing authority for finite prospective studies | MET — `WORKER-PROMPT.md:28-34` |
| Panel reaches required clusters with a positive ceiling | MET — `graph:dev+transfer`, 6 clusters, ceiling `0.285714`, 6 of 6 rows open |
| Panel readable by the qualification gate | **NOT MET** — the five authored graph policies hardcoded a `seed-sw-` method; repaired on `wt/b13b-replseed`, not yet merged here |
| Out-of-process execution carries authority | **NOT MET** — `s09_e2_scored._execute` passes no dsn, allocation or operation id, so every policy reading is `unscored`; owned by A2 |
| Served output budget | **UNRESOLVED** — see above; `B11` measures it |
| Uncertain historical reservation identified | **NOT MET** — needs the `invl02_live` store, a different grant |
| Confined read denial | **NOT MET** — WSL2 kernel rejects Landlock; needs bare metal |
| Rate limits, quota, concurrency | **UNVERIFIED** — treated as unknown headroom |

No dispatch is authorized while any row reading NOT MET above sits on the dispatch
path of the study in question. Recording the gap is not removing it.
