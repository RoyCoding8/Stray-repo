# A57 prospective study grant and cap sheet — Stage 9 power, Stage 10 learner improvement

Status: FROZEN before any effect. Written 2026-10-03 at integration tip `8860d85`,
branch `wt/a57-grant`. This document **authorises nothing that has already
happened and runs nothing itself.** It is the freeze the assignment required
before effects, written after the matrix was measured and before any live leg
was attempted. Model calls made under this sheet: **0**. Dispatches: **0**.

It is a **new freeze**, not an amendment. `reports/cap-sheets/b-live-cap.md` and
`reports/cap-sheets/b14-retention-freeze.md` are unchanged and remain the record
for B11, B12, B13, B14 and B16. Nothing here reopens them, nets against them,
or makes anything they produced comparable to anything below.

## Authority

`WORKER-PROMPT.md:33-39` is the standing authority: fresh live experiments on
verified free routes, token consumption not a concern, finite and prospective,
with the grant and cap sheet written from the complete matrix before effects. A
missing grant file is setup work, not a reason to ask again. This sheet is that
record and it asks for nothing.

`WORKER-PROMPT.md:41-45` is the constraint on it: old exposure stays under its
original grants, unknowns are not settled, spent grants are not reused,
terminal historical rounds are not redispatched, frozen evidence is not edited to
unblock a study, and carried-in spend is accounted separately. Every section
below that could have broken one of those rules says so instead of doing it.

## What this freeze covers, and the one thing it does not

Three prospective legs, all of them live-route legs:

| leg | what it would measure | blocking condition |
|---|---|---|
| **A1** graph-panel experience contrast | whether relevant experience beats absent and equal-sized irrelevant experience on a powered panel | software measured at 2 units; graph independence unproven |
| **A2** `c4-live` live learner revision | whether one acquired revision of the acquisition procedure produces better descendants | no eligible revision, and no live route |
| **A3** `b5-sealed-state` per-task policy state | whether the policy's state survives into sealed assessment | no live route |

**A1 is allocated zero dispatches.** That is the finding of this sheet, not a
deferral. Section *The 60 percent* explains why, and the reason is a property of
both instruments, not a missing protocol and not a budget.

A2 and A3 are allocated a finite ceiling and are **not runnable today**. Both
preconditions fail for reasons this sheet records precisely rather than papers
over. Their ceilings are frozen anyway, so that a future run against a
restored route does not also have to re-derive its own authorisation.

## The instrument result that sets A1's ceiling at zero

**Measured, reproduced at this tip, not read from a report.**

`experiments/ad01/independent_units.py` measures how many *observationally
distinct* behaviours each family can present. The cluster rule
`(family, template)` in `experiments/ad01/s09_panel_inventory.py:26` counts
names. The question the sign-flip test asks is whether those names were
different draws.

For software, reproduced at `8860d85` by enumerating every legal op program over
the world's own alphabets:

```text
program_count            402233   (lengths 1-5, 13-symbol alphabet)
distinct signatures        2       of 8 in the observable space
  stale-clear  ->  (missing, str)
  stale-read   ->  (str, str)
templates named             4
template_count             4
signature_count            2
collapses               True
```

Four software templates collapse to two behaviours. `stale-read-2chain` and
`stale-read-3chain` are the same behaviour; so are `stale-clear-core` and
`stale-clear-del-core`. The collapse is forced by the fault branches at
`experiments/representation/software.py:100-143`, not by template shape:
`pending` is only populated from a non-empty stored value, so a `get` under
`stale-read` can only ever return `present`; and `clear` under `stale-clear`
retains the last written key, which is present where the reference is absent.
A third behaviour would need a branch reporting absence where the reference
reports a value. Neither branch can do that, and the enumeration over 402,233
programs found none.

**No software generator that reuses those branches can close the shortfall,
however many templates it adds.** This is the correct and final disposition of
the software side. It is not a defect in the generator to be repaired by
minting families; it is the instrument's observable space.

### The graph side: named six, measured two families, independence unproven

`independent_units.py:31-32` states that the graph panel's six templates "do
reach six distinct ceilings, so the graph side is not subject to this". **That
sentence has no code behind it.** The same module contains no graph measurement
at all; `graph` appears in the file only inside that docstring. And the panel
inventory records the gap explicitly for the graph family
(`experiments/ad01/s09_panel_inventory.py:154-162`): `signature_count: None`,
`collapses: None`, note *"no observable-behaviour measure is defined for this
family"*.

Measured here, against the 27 frozen graph task files and the world's own
scorer:

| template | \|V\| | \|E\| | girth | cyclomatic | flip distance | tasks |
|---|---:|---:|---:|---:|---:|---:|
| `C5+tree` | 6 | 6 | 5 | 1 | 1 | 6 |
| `C7+tree` | 8 | 8 | 7 | 1 | 1 | 6 |
| `C5+shared-edge` | 8 | 9 | 5 | 2 | 1 | 3 |
| `C5+shared-vertex` | 9 | 10 | 5 | 2 | 1 | 6 |
| `C9+tree` | 10 | 10 | 9 | 1 | 1 | 3 |
| `C5+joined-by-path` | 10 | 11 | 5 | 2 | **2** | 3 |

Every graph is connected and every one carries a cycle, so the three `+tree`
names do not describe trees. Zero self-loops and zero malformed edges, so this
is not degenerate input. The six names collapse to **two structural families
of three**: three single odd cycles at girth 5, 7 and 9, and three gluings of
two 5-cycles by a shared vertex, a shared edge or a bridge.

**The templates are not behaviourally identical.** The outcome vocabulary is
two-valued — `checkers.check_graph`
(`experiments/representation/checkers.py:99`) returns `preserved` or
`not_preserved`, and no third verdict is reachable — but *how hard each
template is to move* varies by structure. The verifier is triangle-free and
non-bipartite, so an odd cycle survives a vertex deletion unless the deletion
hits the cycle. Five templates lose the witness to a single edit;
`C5+joined-by-path`, which carries two disjoint 5-cycles joined by a bridge,
**cannot**. Measured exhaustively: one edit never reaches bipartite, two do.

So the reading is narrower than "six independent units" and wider than "one
unit". It is **two families of three, differing within family by a length
parameter**, plus one template that is genuinely distinct from its own family.

**What is still unproven is independence.** The difficulty spread is measured.
Whether six clusters give six independent draws is not, and the only code that
could say so does not exist. The `C5+tree` / `C7+tree` / `C9+tree` trio
differs by cycle length alone, and a monotone length gradient is the shape of
difference most likely to produce a consistent sign across clusters — which is
exactly the correlation a sign-flip test is designed to absorb. Pooling a
length gradient into a sign flip risks measuring "bigger graphs are harder" and
reporting it as cluster independence.

**A1 is therefore still allocated zero**, but on the software result plus this
uncertainty rather than on a settled graph negative:

- **software: measured and final.** 2 observable behaviours behind 4 template
  names, exhaustive over 402,233 programs. No generator reusing those two
  branches can add a third.
- **graph: not final either way.** Either the two families are one unit of size
  variation, or the trio is a length gradient that a sign flip would absorb. The
  distinction needs a per-cluster independence measure that does not exist and is
  not written here, because writing it is a study and this sheet does not run
  studies.

The census is not retracted. It is bounded: `census.json` answers *how many
templates does this panel name*, and it is correct to that question. It is not a
measurement that those names are independent draws, and for software it would
have overstated by a factor of two.

## The matrix, cell by cell

Two matrices are in play and they are not the same object. The complete matrix
is `reports/PROJECT-INVENTORY.md` plus
`reports/evidence/invr1b8-panel-census/census.json`. §B's expressivity matrix is
3 representations × 3 worlds = 9 cells. The census's power matrix is
family × split = 14 panels. Both are dispositioned below, because both bear on
whether a live leg can produce a comparison.

### Panel census — all 14 panels, read from the committed census

Cluster rule `(family, template)`, `alpha: 1/20`, `required_clusters: 6`.

| panel | family | clusters | required | shortfall | powered | ceiling | min p | open | rows |
|---|---|---:|---:|---:|---|---:|---|---:|---:|
| `software:dev` | software | 2 | 6 | 4 | **no** | 0.3125 | 1/2 | 1 | 3 |
| `software:within` | software | 2 | 6 | 4 | **no** | 0.0 | 1/2 | 0 | 3 |
| `software:transfer` | software | 2 | 6 | 4 | **no** | 0.285714 | 1/2 | 2 | 3 |
| `software:dev+within` | software | 2 | 6 | 4 | **no** | 0.3125 | 1/2 | 1 | 6 |
| `software:dev+transfer` | software | 4 | 6 | 2 | **no** | 0.3125 | 1/8 | 3 | 6 |
| `software:within+transfer` | software | 4 | 6 | 2 | **no** | 0.285714 | 1/8 | 2 | 6 |
| `software:dev+within+transfer` | software | 4 | 6 | 2 | **no** | 0.3125 | 1/8 | 3 | 9 |
| `graph:dev` | graph | 3 | 6 | 3 | **no** | 0.263158 | 1/4 | 3 | 3 |
| `graph:within` | graph | 3 | 6 | 3 | **no** | 0.263158 | 1/4 | 3 | 3 |
| `graph:transfer` | graph | 3 | 6 | 3 | **no** | 0.285714 | 1/4 | 3 | 3 |
| `graph:dev+within` | graph | 3 | 6 | 3 | **no** | 0.263158 | 1/4 | 6 | 6 |
| `graph:dev+transfer` | graph | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6 | 6 |
| `graph:within+transfer` | graph | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6 | 6 |
| `graph:dev+within+transfer` | graph | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 9 | 9 |

Three of 14 are `powered: true` by the census's own rule, all three graph.
**That verdict survives only as a count of names**, and the sections below bound
it: all six graph templates resolve to two structural families of three, and
whether those are independent draws is unmeasured. Every software panel is
unpowered on any combination, measured and final: the whole frozen software
world holds 4 templates behind 2 observable behaviours. Read the table as *what
the panel names*, not as *what the panel can measure*.

### §B expressivity matrix — 9 cells

| cell | what exists | what it can support | honest disposition |
|---|---|---|---|
| boolean × step | shipped live acquisition entry; r2/r3 returned 0 usable programs; r4 acquired 3 wrappers delegating to authored `ddmin` | that acquisition can happen and be told apart from authoring | **comparable**, and its past results are negative |
| boolean × typed-AST | `compare_arms`-comparable on 5 tasks; node set expressible | representation parity on Boolean, authored records only | **no acquisition protocol shipped** |
| boolean × graph | `compare_arms`-comparable; guard fragility measured on 5 points | parity, and a guard-mismatch observation | **no acquisition protocol shipped** |
| ordering × step | runs; every arm scores 0.0 | that the world is drivable and all three agree on nothing | **ceiling 0**; agreement on zero is not parity |
| ordering × typed-AST | runs; no symbolic `lt` in the frozen node set | a measured expressivity limit | **ceiling 0** |
| ordering × graph | runs; commits a written order | same | **ceiling 0** |
| software × step | 4 lineages, 4 distinct record digests; 12 lineages total, 8 refused and reported as refusals | acquisition reaches and reports failure honestly | **supported cell**, but on an instrument with 2 units |
| software × typed-AST | `missing_cells()` witness: the loader accepts the edit; the cell cannot **read** the program, so it cannot localise a line | that the limit is reading, not writing | **missing cell, demonstrated** |
| software × graph | `missing_cells()` witness: no `FIELD_BINDING`, so a guard value read from the view is discarded; repair rate 0 for record-shape reasons | that a graph arm can inspect and stop | **missing cell, demonstrated** |

**One cell of nine has a shipped acquisition protocol.** Eight do not. That is
the §B matrix's honest state, and it is a plan-versus-measurement gap, not
twelve new generator families.

## The 60 percent, stated accurately

A prior lane recorded that *no cap sheet is writable: 60% of the ceiling has no
protocol.* **That figure is not reproducible from any denominator in the
committed census.** Measured against `census.json`:

| reading | value |
|---|---:|
| unpowered panels, by count | 11/14 = 0.7857 |
| unpowered panels, by ceiling sum | 2.896616 / 3.753758 = 0.7717 |
| software panels, by count | 7/14 = 0.5000 |
| software panels, by ceiling sum | 1.821428 / 3.753758 = 0.4852 |
| §B cells with no acquisition protocol | 8/9 = 0.8889 |

The sentence does not appear in any committed document on any branch, so its
denominator is unrecoverable. This sheet does not restate it.

**The finding it was reaching for is real, and it is now stated exactly.**
There are two distinct shortfalls, and conflating them is what made the figure
unreproducible.

1. **A protocol shortfall, which is an instrumentation gap.** Eight of nine §B
   cells have no shipped acquisition entry. That gap is closable by building
   prompts and executors, and §B says explicitly that an unsupported cell needs
   a witness and an architectural disposition, *"not a new DSL built merely to
   fill the table."*
2. **A power shortfall, which is not closable by building protocols.** The
   software world has two observable behaviours behind four template names. No
   protocol reaches a third. The graph world resolves to two structural families
   of three, and whether those are independent draws is unmeasured. A
   comparison on software can be run and its result will be n=2 regardless of
   dispatches spent; a comparison on graph could be run and would risk measuring
   a length gradient.

Cells that are unpowered **are not benefit results** and must not be scheduled
as though they were. That is why A1 gets zero dispatches. The correct next move
for the experience contrast is not a study on either frozen world; it is an
instrument change that makes distinct behaviours reachable — a software fault
branch capable of a third observable, and graph templates differing in
observable behaviour rather than in vertex count — or a decision that these
worlds cannot answer the question and it moves elsewhere.

## The route, and the external dependency

**There is no usable route on this host, and this is a specific external
dependency rather than model failure.** Measured at `8860d85` on 2026-10-03,
Windows-first, no WSL use and no inference attempted:

| fact | how measured | result |
|---|---|---|
| `SETTLEMENT_GATEWAY_KEY` | env read at Process/User/Machine, all three scopes | **unset**, length 0 |
| `SETTLEMENT_GATEWAY_ENDPOINT` | same | **unset**, length 0 |
| `INVL02_LIVE_GRANT` | same | **unset**, length 0 |
| `S09_STUDY_CALLS_ALREADY_SPENT` | same | **unset**, length 0 |
| `/home/ubuntu/.config/agent-society-live.env` | filesystem probe, WSL down | **absent** |
| Windows-side live env file | filesystem probe | **absent** |
| port 4000 listener | `Get-NetTCPConnection -LocalPort 4000 -State Listen` | listening, PID 30360 |
| what that PID is | `Win32_Process` command line | `python.exe -m modules.router` |
| `GET http://127.0.0.1:4000/v1/models` | read-only, no auth header, no inference | **HTTP 401** `{"error":{"message":"invalid api key"}}` |
| `GET http://127.0.0.1:4000/` | read-only | HTTP 200 |

The process on 4000 is an unrelated router, not this project's gateway. It
answers an OpenAI-shaped 401, so a contract match is not evidence of identity.
**No key value appears anywhere in this sheet.** The variable is named, never
assigned, and its value must never enter Git, a prompt, a report or evidence.

### What would have to be true for a live leg to run

A live leg needs **all five**, and none is currently met:

1. `SETTLEMENT_GATEWAY_KEY` set at the scope the broker reads, with the
   credential held in a mode-600 environment file outside Git, as
   `b-live-cap.md` already specifies.
2. `SETTLEMENT_GATEWAY_ENDPOINT` set to the gateway, and the gateway verified to
   be that process rather than a port squatter.
3. A live catalog read confirming the pinned free model
   `nvidia/nemotron-3-ultra-550b-a55b:free` is present, replacing the
   2026-10-01 reading rather than assuming it. The 219-entry catalog is
   **stale** and must not be inherited.
4. A disposable database reachable, since the live leg is broker-routed and the
   broker imports `dbos`.
5. `INVL02_LIVE_GRANT` set to this sheet's id, so exposure is attributed here
   rather than to a spent historical grant.

### What may be concluded without any of them

Every disposition below is reachable with zero dispatches, and most of them are
already measured. Specifically:

- The software power shortfall is settled and needs no route. It is a property
  of `software.py`'s fault branches.
- The graph structure is measured and needs no route: two families of three,
  and one template (`C5+joined-by-path`) whose flip distance is 2 where the
  other five are 1. Whether that yields six independent clusters is unmeasured
  and is not claimed here.
- The §B expressivity matrix is settled as a plan-versus-measurement gap and
  needs no route.
- The §A chain result is a fixture-gateway doubles result and bears on nothing
  live. It is not evidence of acquisition and this sheet does not cite it as
  such.

**What may not be concluded without a route:** any acquisition rate, any
utility or transfer benefit, any learner improvement, and any negative that
depends on the route answering. Route absence bounds what can be *run*. It is
not a negative result and must never be recorded as one.

## Dispatch caps

Frozen per-request bounds, carried from the parent sheets so a future run is
priced the same way:

| bound | value |
|---|---|
| `max_output_tokens` | 2048 |
| `deadline_ms` | 300000 |
| `reasoning_effort` | `low` |
| `reasoning_effort_on_the_wire` | `none-sent` |
| `endpoint` | `http://127.0.0.1:4000/v1` (**unverified today**, see above) |
| `requested model id` | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `provider` / `tier` | `nvidia` / `free` |
| `key variable` | `SETTLEMENT_GATEWAY_KEY` (name only, never a value) |

| leg | dispatches | retries | physical sends | basis |
|---|---:|---:|---:|---|
| A1 graph-panel experience contrast | 0 | 0 | 0 | software measured at 2 units, graph independence unproven; allocated zero, stated as a positive finite ceiling |
| A2 `c4-live` learner revision | 12 | 2 | 14 | 6 revised-vs-parent acquisition pairs x 2 constructions, plus 2 spare repairs |
| A3 `b5-sealed-state` policy state | 0 | 0 | 0 | instrument-gated: the sealed-state comparison has no shipped entry; the leg's question is answerable offline |

```text
total_dispatch_cap: 12
total_retry_allowance: 2
total_physical_send_ceiling: 14
campaign_wall_ceiling_ms: 4200000
per_request_units: 2492
requests: 14
unit_kind: estimated-budget
total_units: 34888
carried_in_uncertain_units: 5563
carried_in_true_exposure: >= 5563
carried_in_netted_against_this_allocation: false
required_clusters: 6
alpha: 1/20
cluster_rule: (family, template)
panel: graph:dev+transfer
panel_named_clusters: 6
panel_ceiling: 0.285714
panel_minimum_p: 1/32
panel_independence_measured_here: partial
panel_independence_measured_in_repo: false
panel_independence_verdict: graph-two-families-of-three-independence-unproven
graph_structural_families: 2
graph_templates_named: 6
graph_flip_distances: "1,1,2,1,1,1"
software_distinct_observable_outcomes: 2
software_templates_named: 4
powered_panels_by_naming: 3
powered_panels_by_software_measurement: 0
dispatches_used: 0
model_calls: 0
model_id_ends_free: true
route_verified_live: false
credential_present: false
source_tip: 8860d85
written: 2026-10-03
```

A2 is not runnable today and its ceiling is frozen anyway, so that restoring a
route does not also require re-deriving an authorisation. **Spending a
thirteenth dispatch against this sheet is a breach of it**, exactly as a
seventy-ninth send would be against the parent sheet.

### Per-request unit accounting

Derived from `settlement.broker._model_exposure`
(`src/settlement/broker.py:149-151`), which is
`(sum(len(content)) // 4 + 1 + max_output_tokens) * (retries + 1)`. At the
frozen 1774-character message and 2048 output tokens: `443 + 1 + 2048 = 2492`
units per request, `unit_kind: estimated-budget`.

`2492` is checked against a recorded value rather than asserted: the archived
contrast at `reports/evidence/invr1e2contrast/report.json` records
`per_request_units: 2492`, which this formula reproduces exactly.

These are estimated reservation units. They are **not** a price, not a dispatch
count, and not proven provider billing. `billed` and `charge_units` are null on
every receipt from this route because the adapter reads those keys and the route
reports `usage.cost` instead. This sheet asserts no provider price in either
direction. Unknown is recorded as unknown and never written as zero.

### Carried-in historical exposure, accounted separately

The ledger records a verified uncertain subtotal of **5563** internal estimated
reservation units, with true exposure **`>= 5563`** because one further
uncertain reservation is excluded from every reconciliation artifact and
identified nowhere.

**The 34888-unit allocation is independent of the 5563.** 34888 is not 34888
minus 5563. No historical grant is reused, no unknown is settled, no terminal
round is redispatched, and no frozen evidence is edited. The gap is recorded as
a blocker on a different grant, not a debt this sheet pays.

## Protocol and selectors, frozen

- **Protocol.** Three arms per supported cell — relevant, absent, and
  equal-sized irrelevant — with matched interfaces and matched opportunity. Each
  arm gets at least 4 independent construction opportunities, deduplicated
  against hidden targets and separated by template before evaluation. Selection
  and repair use development information only; scoring is sealed. A failed
  acquisition is never promoted to an authored learned arm.
- **Selectors.** The development-only selector is the existing per-world
  declared policy view contract, unchanged. Sealed scoring is unchanged. No new
  selector is introduced by this freeze.
- **Scored observables.** Operational quality, intermediate behaviour and
  complete resources. Constant preservation is **not** a benefit metric, which
  is why the 26-row retention leg reading `{"preserved"}` uniformly is a
  no-acquisition result rather than a benefit.
- **Replication.** A second independent namespace where the first run supports
  the comparison. An apparatus-repair rerun is not replication.

## The stopping condition, stated in advance

The study stops at 14 physical sends, or when the frozen scope and analysis are
complete, or 30 days from this sheet's date, whichever comes first. It also
stops immediately, without spending the remainder:

- if the route is not restored on all five conditions above, since a leg that
  cannot authenticate is not a negative result;
- if a study's dispatches are exhausted with its matrix unfilled — missing
  cells are recorded with their concrete limitation, never retried and never
  filled by an authored arm;
- if any quality or freeze gate fails;
- if a credential, a paid tier or a Jev call is requested;
- if the answer arrives, **including a negative one**. A valid negative study
  is useful and this assignment does not search indefinitely for a positive
  result. **There is no search for a positive result**, and the free tier is not
  a reason to widen any of these numbers.

A stop, an unknown or a no-candidate outcome does not authorize a replacement
episode. **A rerun after an apparatus failure is not replication.**

Three results would end this study, and all three are legitimate endings:

1. **Already reached for the software half of A1.** The software instrument
   cannot present six independent units, measured exhaustively. The graph half
   is unresolved and is recorded as unresolved. Either way A1 has no protocol
   and no dispatches, and no dispatch changes that.
2. **The route is never restored.** Then A2 and A3 stay unrun and are reported
   as unrun, never as negatives.
3. **A2 runs and yields no eligible revision.** That is a completed bounded
   attempt, which §C asks for, and it is reported as a completed attempt rather
   than as a learner-benefit comparison.

## What is frozen, and what a change costs

Source tip, endpoint, requested model id, provider, tier, reasoning effort and
the fact that none is sent on the wire, the panel and its split set, the three
experience arms and their size matching, the construction and repair loop, the
decision grid, the held-out instance set, the selectors, the per-request bounds
and every ceiling.

**A change to any frozen item creates a NEW freeze.** It does not
retroactively validate work already run and it does not make old and new runs
comparable. There is no repair that makes older and newer runs comparable, only
a new freeze and an honest report of what each is.

## Preconditions

No dispatch is authorized while a NOT MET row sits on that leg's dispatch
path. **Recording the gap is not removing it.**

| precondition | A1 | A2 | A3 | state |
|---|---|---|---|---|
| Credential present on host | n/a (zero ceiling) | required | required | **NOT MET** |
| Gateway identified, not a port squatter | n/a | required | required | **NOT MET** |
| Free model confirmed in a live catalog | n/a | required | required | **NOT MET** (last read 2026-10-01, stale) |
| Disposable database reachable | n/a | required | required | **NOT MET** |
| Grant id in environment | n/a | required | required | **NOT MET** |
| Six independent clusters exist | **NOT MET** | n/a | n/a | **NOT MET**; software measured at 2 units, graph unproven |
| Graph observable measure defined | **NOT MET** | n/a | n/a | **NOT MET**; structure measured here, independence not |
| Eligible revision exists | n/a | **NOT MET** | n/a | **NOT MET**, no live attempt has run |
| Sealed-state entry exists | n/a | n/a | **NOT MET** | **NOT MET** |
| Out-of-process execution carries authority | n/a | required | required | **NOT MET** |
| Uncertain historical reservation identified | n/a | required | required | **NOT MET**, needs the `invl02_live` store |
| Rate limits, quota, concurrency | n/a | required | required | **UNVERIFIED**, headroom unknown |

Two rows in the earlier sheet are recorded rather than removed, because they are
still true: **Confined read denial** — WSL2 rejects Landlock, so it needs bare
metal — and **Served output budget**, which B11 established at 2048 for one
route at one time and which is **not** re-verified here. A route that has
changed since is a different route.

## What this sheet does not establish

- It runs nothing and measures no model. Dispatches used: 0.
- It does not qualify a live route. The route is absent and the credential is
  absent, and that is an external dependency.
- It does not claim any acquisition, utility, transfer or learner-improvement
  result. Every disposition above acquisition that exists in the ledger remains
  exactly as the ledger records it.
- It does not repair either instrument, and it does not propose a new DSL to
  fill a matrix. §B forbids the latter and the first is an architectural
  decision that is not this lane's to make.
- The instrument measurements here are **model-free**. They enumerate the
  frozen worlds and their scorers, so they cost no dispatch and they carry over
  unchanged to any future run. They say nothing about what a model can do, only
  about how many independent comparisons the instrument can present.
