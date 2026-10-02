# B10 — the B cap sheet, written before any effect

Branch `wt/b10-capsheet`, forked from `75cab06`. Files added:
`reports/cap-sheets/b-live-cap.md`, `tests/test_inv_b10_cap_sheet.py`, this report.
Nothing under `reports/evidence/` was read-modified or moved, and no other cap sheet
or source file was touched. No model call, no network, no dispatch. `model_calls: 0`.

## Why this lane exists

Section (f) bullet B10 of `reports/workstreams/inv-b.md` says the two live campaigns
carry schema, namespace, freeze digest, matrix and per-request units, and that B's
matrix is larger and needs its own. It did not exist. Four files were in
`reports/cap-sheets/` and none was a B sheet. The assignment already grants standing
authority for the finite prospective studies (`WORKER-PROMPT.md:28-34`) and says a
missing grant file is setup work, not a reason to ask again. So this lane writes the
record. It asks for nothing.

## The matrix as recorded

From `reports/evidence/invr1b8-panel-census/census.json`, B8's census, itself
recomputable from the frozen world. Cluster rule `(family, template)`, alpha `1/20`,
`required_clusters: 6`, `model_calls: 0`.

**`graph:dev+transfer` is the supported panel.** 6 clusters, 6 required, shortfall 0,
`powered: true`, ceiling `0.285714` (exactly 2/7, the census rounds to six places),
`minimum_p: "1/32"`, 6 of 6 rows open. It is the smallest powered panel, chosen
because it buys the same power for fewer dispatches than the two larger graph
combinations. All three powered panels carry the same ceiling, so the choice costs
nothing in reachability.

**Software cannot carry it, and no split choice could have.** The frozen world holds
four software templates against the six required, so the software shortfall is at
least two everywhere: `software:dev`, `software:within`, `software:transfer` and
`software:dev+within` reach 2 clusters; `software:dev+transfer`,
`software:within+transfer` and `software:dev+within+transfer` reach 4. All seven are
`powered: false`. Both archived E2 contrasts ran that panel, which is why
`reports/evidence/invr1e2contrast/report.json` records
`sign_flip.minimum_p: "1/2"` against `required_clusters_at_alpha_1_20: 6`.

`verdict.powered_but_blind` is empty, recorded as a field rather than assumed. The
sheet says explicitly that this is a power repair and **not** the retention closure,
which no panel moves, and it claims no retention result.

## The route

Endpoint `http://127.0.0.1:4000/v1`, requested model
`nvidia/nemotron-3-ultra-550b-a55b:free`, provider `nvidia`, tier `free`. Confirmed
present unprefixed in a live 219-entry catalog read on 2026-10-01, 32 free-tier
(`reports/PLAN.md`, ROUTE row). The archived probe's 256-entry catalog and its
`frozen-model-absent-from-catalog` finding are named as superseded history, not
restated as a current precondition.

**The key is named by variable and never by value.** The sheet names
`SETTLEMENT_GATEWAY_KEY` and `SETTLEMENT_GATEWAY_ENDPOINT`, says the value lives in
an environment file outside Git at mode 600, and contains no `sk-` prefix, no
assignment to the key variable, and no opaque token that is not a path or a
snake_case identifier. Two tests hold that, one over the sheet and one over every
`.md` in `reports/cap-sheets/` so the sheet is not a special case.

## Finite ceilings, with the numbers

Per-request bounds carried from the archived contrast so B and the E2 contrast are
priced the same way: `max_output_tokens: 2048`, `deadline_ms: 300000`,
`reasoning_effort: low` with `reasoning_effort_on_the_wire: none-sent`, because the
chat surface refuses a request carrying an effort, so no request sends one and the
receipt records no effort rather than a control the wire never applied.

| study | dispatches | retries | sends | basis |
|---|---:|---:|---:|---|
| B11 served output budget | 6 | 0 | 6 | one rung each at 16, 64, 256, 1024, 2048, 4096 |
| B12 SWE construction and use | 24 | 1 | 25 | 4 lineages x (1 construction + 1 repair) = 8, plus 4 x 4 held-out = 16 |
| B13 E2 contrast, powered panel | 37 | 1 | 38 | 3 arms x 6 rows x 2 constructions = 36, plus 1 route probe |
| B16 acquired bytes, new process | 8 | 1 | 9 | 4 lineages x 2 held-out families, use only |
| **total** | **75** | **3** | **78** | |

`total_dispatch_cap: 75`, `total_physical_send_ceiling: 78`,
`campaign_wall_ceiling_ms: 22800000` (78 x 300000 under a serial broker). B14 and B15
are recorded as **not allocated**: B14 is gated on B3 because the repertoire is
closed, B15 on B7 because the reuse and continue decisions do not exist. Both need a
new freeze of this sheet, and a test fails if either acquires a cap row without one.

Repair reserve is at most 1 repair per construction opportunity, carried as the retry
allowance, so each study's sends equal its dispatches plus its retries. B11 carries
no retry allowance because a retry at a fixed budget re-measures the same rung and
answers nothing.

**Per-request unit accounting.** `broker.exposure_schedule(MODEL_INFERENCE, request, 0)`
is `(sum(len(content)) // 4 + 1 + max_output_tokens) * (retries + 1)`, so at the frozen
1774-character message and 2048 output tokens it is `443 + 1 + 2048` = **2492 units per
request**, `requests: 78`, `unit_kind: estimated-budget`, `total_units: 194376`. The
test recomputes 2492 through the real broker and compares it to the archived contrast's
own `per_request_units`, so the number is checked against a recorded value rather than
asserted. These are estimated reservation units, not a price and not a dispatch count.

`billed` and `charge_units` are null on every receipt from this route because the
adapter reads those keys and the route reports `usage.cost` instead. The sheet asserts
no provider price in either direction, and says so.

## The unresolved item, stated as unresolved

**Status: UNRESOLVED. The sheet does not establish it.**

The recorded 502 tracks the requested output budget, not the prompt. The same campaign
prompt returns 200 at 16 and at 256 output tokens, 502 at the protocol's own 2048, and
a short prompt returns 200 at 2048
(`reports/evidence/w1-e1-boolean-r3/route-probe.json`, finding
`output-budget-causes-the-502`). Every campaign currently caps 2048.

Which budget this route serves is unknown, and establishing it costs dispatches. So it
is **B11, the first bounded item in the sheet and the first thing an operator does**,
capped at 6 sends with no retries, and it is listed first in the dispatch table. The
sheet's own unit figures are derived at 2048 and are re-derived by the formula the
moment B11 returns. **Its outcome is a new freeze.** A changed budget creates a new
freeze and does not make older and newer runs comparable, so nothing produced under one
budget may be pooled with anything produced under another. The test asserts the three
recorded statuses and that the item is still marked unresolved, so a later editor
cannot quietly resolve it in prose.

## How carried-in spend stays separate

The ledger records a verified uncertain subtotal of **5563** internal estimated
reservation units, and true exposure is **`>= 5563`** because one further uncertain
reservation is excluded from every reconciliation artifact and identified nowhere. The
two verified terms are 2294 and 3269 (`reports/PROJECT-LEDGER.md:103-117`).

**The 75-dispatch and 194376-unit allocation is independent of the 5563.** The sheet
says 194376 is not 194376 minus 5563, names the historical gap as a read-only query
against the `invl02_live` store that this host cannot reach, and records it as a
blocker on a different grant rather than a debt this sheet pays. Nothing historical is
reused, settled or netted, and no terminal round is redispatched. The test asserts the
5563 is present, that `carried_in_netted_against_this_allocation` is `false`, and that
the netted figure `188813` appears nowhere in the sheet.

## The five assertion groups the test names

1. `test_the_route_is_the_loopback_gateway_and_the_model_id_is_free_tier`, plus
   `test_the_catalog_count_recorded_is_the_live_one_and_not_the_superseded_one`.
2. `test_no_credential_value_appears_anywhere_in_the_sheet`, plus
   `test_the_repository_records_the_key_variable_by_name_only` which sweeps every
   `.md` cap sheet.
3. `test_every_study_dispatch_cap_is_a_positive_integer_and_matches_its_ladder`,
   `test_the_dispatch_caps_sum_to_the_stated_total_and_no_more`,
   `test_the_unit_allowance_is_recomputed_through_the_broker_not_restated`, and
   `test_the_studies_that_are_gated_record_zero_rather_than_disappearing`.
4. `test_the_output_budget_is_present_and_marked_unresolved`.
5. `test_carried_in_historical_exposure_is_recorded_and_not_netted`.

Plus the matrix tests that read the census rather than restating it, and the freeze,
stopping-condition and honest-unknown tests. Sixteen in total.

The test PARSES the sheet. It reads the dispatch table rows with a regex, reads the
figures from a `text` block inside the sheet, and compares them to literals pinned in
the test. It reads the panel numbers out of `census.json` and the unit figure out of
the broker and the archived contrast, so a hand-edited sheet fails rather than being
inherited.

## The gate

    wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/b10.jsonl; cd /mnt/d/AI/Agent-Society-v2/.worktrees/b10-capsheet && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b10-capsheet/src timeout 900 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b10_cap_sheet.py -q -p no:cacheprovider'

    16 passed in 2.33s (0:00:02)

TDD was followed in the useful direction. The first run was **9 failed, 7 passed**,
and every failure was real: three of my test's literals were wrong (the census rounds
its ceiling to `0.285714`, not `0.2857142857`; `powered_with_positive_ceiling` is a
list of strings, not panel objects; `carried_in_true_exposure` is `>= 5563`, not `>`),
one was a hard-wrapped phrase, one over-matched on long snake_case identifiers, and
four were the sheet's figures living in prose where a regex could not read them. The
last four I fixed in the sheet, not by relaxing the test. **I did not weaken one
assertion to go green.**

## The tampers, measured

A cap sheet nobody checks is a promise, so I broke the sheet on purpose and confirmed
the test bites, restoring the bytes after each.

| tamper | result |
|---|---|
| B13 raised 37 to 99 dispatches | 2 failed, 14 passed |
| `carried_in_netted_against_this_allocation` flipped to `true` | 1 failed, 15 passed |

Both were caught by the specific assertion that names the thing, not by a generic
"something changed" failure. The file was restored byte-for-byte from a copy taken
before each tamper and the final green run is on the restored bytes.

## The stopping condition

The campaign stops at 78 physical sends, or 6 B11 ladder rungs, or 30 days from the
sheet's date, whichever is first. It also stops immediately, without spending the
remainder, if the route 502s or times out at the lowest B11 rung, if a study's
dispatches are exhausted with its matrix unfilled (missing cells are recorded with
their concrete limitation, not retried or filled by an authored arm), if a quality or
freeze gate fails, or if a credential, a paid tier or a Jev call is requested. A stop
or an unknown does not authorize a replacement episode. A rerun after an apparatus
failure is not replication. The free tier is not a reason to widen any number.

## What is frozen, and what a change costs

Source tip, endpoint, requested model id, provider, tier, reasoning effort and the
fact that none is sent on the wire, the panel and its split set, the three experience
arms and their size matching, the construction and repair loop, the decision grid, the
held-out instance set, the selectors, the per-request bounds and every ceiling.
**A change to any frozen item creates a NEW freeze.** It does not retroactively
validate work already run and does not make old and new runs comparable. There is no
repair that makes older and newer runs comparable, only a new freeze and an honest
report of what each is.

## Preconditions still NOT MET, recorded not removed

- Panel readable by the qualification gate. B13b repaired the five authored graph
  policies that hardcoded a `seed-sw-` method, on `wt/b13b-replseed`, not merged here.
- Out-of-process execution carries authority. `s09_e2_scored._execute` passes no dsn,
  allocation or operation id, so every policy reading is `unscored`. Owned by A2.
- Served output budget. UNRESOLVED, and B11 measures it.
- Uncertain historical reservation identified. Needs the `invl02_live` store.
- Confined read denial. WSL2 rejects Landlock, needs bare metal.
- Rate limits, quota, concurrency. UNVERIFIED, treated as unknown headroom.

The sheet says no dispatch is authorized while a NOT MET row sits on that study's
dispatch path, and that recording the gap is not removing it.

## What I did not measure

Only `tests/test_inv_b10_cap_sheet.py` was run. The resource policy caps this lane at
one pytest process on a named file list, so no other test file was touched and I claim
no wider result. The panel numbers were read from B8's committed census rather than
re-derived here, and the test reads the same committed file, so a wrong census would
pass both; B8's own test is what proves the census against the frozen world.
