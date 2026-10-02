# B11 — the served output budget, measured

Lane B11. Branch `wt/b11-probe`, forked from `933f487`. The first live lane in
milestone B, and the first item on `reports/cap-sheets/b-live-cap.md`.

## The answer

**This route serves `max_output_tokens: 2048`.** The campaign's own frozen
budget returned HTTP 200 with a decided `success` receipt, 2048 output tokens,
`stop_reason: length`, and 64 characters of text. **4096 does not serve**: the
send was lost to a read timeout and settled as a `lost-response` with an
`unknown` outcome.

The archived 502 at 2048 did not reproduce. The variable the archived record
blamed is not the one that decides this route, and the difference is the
finding.

## The ladder

One variable moved. The prompt is held fixed at the archived campaign prompt —
982 characters, sha256 `defd0009…` — which reproduces byte-for-byte from
`live.render_output_prompt(session.output_model_input(), [], 1)` over
`w1_e1_campaign_r3._build_session("qual", 11)`, the same string the archived
probe measured. `max_output_tokens` varied across the cap sheet's own ladder.

| budget | outcome | receipt | output tokens | `stop_reason` | units |
|---:|---|---|---:|---|---:|
| 16 | served | `success` | 16 | length | 262 |
| 64 | served | `success` | 64 | length | 310 |
| 256 | served | `success` | 256 | length | 502 |
| 1024 | served | `success` | 1024 | length | 1270 |
| **2048** | **served** | `success` | 2048 | length | 2294 |
| **4096** | **lost** | `unknown` | unknown | — | 4342 |

`stop_reason: length` at every served rung is the load-bearing detail: the route
honoured the requested budget exactly and stopped there, so 2048 is a budget the
route serves rather than a ceiling the model happened to stay under.

**6 of 6 sends used. Zero retries.** That is the full authorisation.

## The archived record, re-read

`reports/evidence/w1-e1-boolean-r3/route-probe.json` recorded
`output-budget-causes-the-502`, stating "returns 200 at 16 and 256 tokens and
502s at the protocol's own 2048; a short prompt returns 200 at 2048." **The
data in that same file does not support its own statement**, which is why the
cap sheet's UNRESOLVED is the honest reading of it and not timidity:

- `probes["campaign-prompt-budget-2048"]` is `{"status": null, "error":
  "TimeoutError: timed out", "seconds": 182.06}` — a **client-side timeout**,
  not a 502. No HTTP status was ever received.
- `probes["short-prompt-budget-2048"]` is the **only** 502 in the file, with
  `error_type: "empty"`. The finding's evidence line credits the 2048 failure to
  the campaign prompt and treats the short prompt as the control, but the 2048
  arm recorded no status at all and the short-prompt arm is where the 502 is.

So the archived 502 was on the *short* prompt, and the archived "502 at 2048" on
the campaign prompt was a 182-second timeout. What that supports is "this route
intermittently fails at large budgets", not "the budget alone decides it". This
ladder ran the same prompt at the same budgets today and got a decided success
through 2048, so the route's behaviour has changed, or the archived failures were
transient. **I did not spend a seventh send to tell those apart**, and the cap
sheet's ceiling is six.

One structural fact survives, and it is the one that mattered for design: the
route can be lost at a large budget. That is what rung 4096 shows, from the same
prompt and the same route, twelve hours of clock time later.

## What this changes for the other lanes

- **B12, B13, B16 can run at 2048 as frozen.** The budget every campaign caps at
  is one this route serves. Nothing needs re-freezing for B11's sake.
- **A budget above 2048 is not available.** Any lane that needs a longer
  generation has a new problem, not a bigger number to try.
- **The per-request unit figure is unchanged at 2048**: 2294 units for this
  prompt at that budget, against the archived contrast's 2492 for its own
  1774-character prompt. The cap sheet's `per_request_units: 2492` is derived
  from the archived contrast's prompt and was never re-derived for B's, so B's
  own figure is its own.
- **Rate limits, quota and concurrency remain UNVERIFIED.** Six sends bound
  nothing. The cap sheet's treatment of headroom as unknown stands.

## A changed budget is a new freeze — stated once, plainly

This run measured the budget. It did not change it, so the freeze it ran under is
the cap sheet's and nothing here invalidates work already done. Had the served
budget come back different from 2048, that would have been a new freeze and no
older and newer run would have been comparable. Nothing is pooled across
budgets here, and the `units_per_rung` map in the artifact is the arithmetic
that makes that concrete: six different budgets, six different prices.

## Honesty of the accounting

- `charge_units`, `charge_scale`, `billed` and `provider_enforced_ceiling` are
  `unknown` on **every** rung, including the five that succeeded. The route
  reports its price as `usage.cost`, which the adapter deliberately does not
  read. Nothing was written as zero.
- The lost rung records `input_tokens: unknown` and `output_tokens: unknown`, not
  zeros. A lost send consumed an unknown amount; the receipt says so.
- The lost rung is `unsettled` with `dispatch_state: unresolved`. It is recorded
  as unresolved, not as a decided failure, because the send reached the wire and
  the answer did not come back. It is **not** a null run and **not** a cancelled
  run, and the artifact says which it is.
- Its reservation stands at 4342 units and its operation is unsettled. That
  exposure is real and is why the store snapshot matters.

## Every send is durable

All six sends are broker operations under one study-bound allocation
`invr1b11-budget-ladder`, study root `invr1b11-budget`:

| budget | operation row | allocation | study_root | reservation | receipt | conflicts |
|---:|---|---|---|---:|---|---:|
| 16 | 1 | bound | bound | 262 | `gw:invr1b11-budget-16` | 0 |
| 64 | 1 | bound | bound | 310 | `gw:invr1b11-budget-64` | 0 |
| 256 | 1 | bound | bound | 502 | `gw:invr1b11-budget-256` | 0 |
| 1024 | 1 | bound | bound | 1270 | `gw:invr1b11-budget-1024` | 0 |
| 2048 | 1 | bound | bound | 2294 | `gw:invr1b11-budget-2048` | 0 |
| 4096 | 1 | bound | bound | 4342 | `gw:invr1b11-budget-4096:lost-response` | 0 |

Each rung is its own operation identity, so no rung is a replay of another, and
the guard's ceiling is the store's `COUNT(*) FROM operations` re-read on every
check. `automatic_retries` is pinned to 0 for this reason: a 429 or a retryable
transport error at the shipped default of 3 would have spent four physical sends
on one rung and broken a six-send ceiling.

## A defect found in my own work, and what it cost

The six sends completed and settled. The artifact write then failed on
`TypeError: Object of type datetime is not JSON serializable` — `dict_row` hands
back `datetime` for the row timestamps, and `json.dumps` will not take one. The
send record was in the store and the receipts were decided; only the file was
missing.

I recovered the observation by **reading the store**, not by re-dispatching, and
the reason is structural rather than cautious: every operation id is now settled,
so `ensure_operation` returns `ALREADY_APPLIED` and the broker would replay the
settled receipt without reaching the wire. A re-dispatch could not have produced
new evidence even if the budget had allowed one. `_jsonable` now converts
datetimes and Decimals at the store read, and the artifact is the store's account
of six sends rather than a second execution's account of them. The artifact
carries `rebuilt_from_store: true` and says why.

The cost of my error was zero sends, which is the only reason it was free.

## Where this ran, and a note for whoever runs the next live lane

The frozen route is a **Windows loopback** listener (`127.0.0.1:4000`, `cx-router/1.1`,
Windows PID 39020) and the durable store is a **WSL** PostgreSQL socket. The two
are on different hosts, and WSL cannot reach the Windows loopback — `localhost`,
the default gateway and the host address all refuse. So the durable path runs in
one **Windows** process, reaching the router on `127.0.0.1:4000` and the store on
`127.0.0.1:5432` through the `wslrelay` forwarder.

The **gate** runs in **WSL**, because `tests/conftest_isolation.py` acquires a
run claim at configure time and touches `signal.SIGHUP`, which does not exist on
Windows. The gate itself reads only a file, so it would pass anywhere; the
infrastructure is what requires WSL. The next live lane should not rediscover
this.

The environment file `LIVE_ENV_PATH` names —
`/home/ubuntu/.config/agent-society-live.env` — **does not exist**, on WSL or on
Windows. `reports/workstreams/w0-routes.md` recorded that on 2026-09-30 and it is
still true. The credential is in `mcpServers.cx-agent.env` in `~/.claude.json`,
which is where the cap sheet's variable resolves from in practice. The cap sheet
is right to name the variable and nothing else; it is wrong about where the value
lives, and the shipped `_load_live_environment` cannot be the path a live lane
uses on this host.

## The catalog drifted

`reports/cap-sheets/b-live-cap.md` records "219 entries, 32 free-tier, the pinned
id present unprefixed, live read 2026-10-01". Today's read: **203 entries, 32
free-tier, the pinned id present, `reconcile_model_route` verdict `accepted`**.

The pinned id is present and the free signal is established, so the route
precondition is MET and the count is the thing that moved. 219 → 203 in a day is
a catalog changing under a freeze, and `w0-routes` already recorded 255 and
`w1-e1-boolean-r3` recorded 256 for the same query. **The catalog count on this
route is not a stable number and should not be cited as one.** The cap sheet's
precondition should read "pinned id present in the live catalog, re-read at
dispatch" rather than a count.

## The gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/b11-probe && \
  export SETTLEMENT_CLAIM_LEDGER=/tmp/b11_claims.jsonl && \
  export SETTLEMENT_TEST_DSN="dbname=invl02_b11 host=/var/run/postgresql user=b11probe password=$(cat /tmp/.b11pw)" && \
  export SETTLEMENT_TEST_TRUNCATE_DSN="$SETTLEMENT_TEST_DSN" && \
  export PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b11-probe:/mnt/d/AI/Agent-Society-v2/.worktrees/b11-probe/src && \
  /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b11_budget_probe.py -q -p no:cacheprovider'
```

`9 passed in 1.66s`

Every assertion is a literal read out of `budget-probe.json` or out of the
exported `store-rows.json`, not a value recomputed from the driver that wrote
them. The credential scan is real rather than promised: it reads the key that is
in the environment right now and searches this lane's written bytes for the
value. Verified non-vacuous — the scan found the value available and zero
occurrences across the files written.

The allocation assertion is the one that keeps a lost send from being paid for:
`consumed` is the five settled rungs' units and `reserved` is exactly the lost
rung's 4342, read from the rows rather than from the artifact's summary.

One assertion was **wrong and I fixed the assertion, not the artifact**. It read
`input_tokens == 370` for every rung, and the lost rung records `unknown`. The
artifact was right and my expectation was the defect: a lost send has no measured
prompt count, and a test demanding 370 there would have demanded a fabricated
number. The test now asserts 370 where an answer came back and `unknown` where
one did not, which is the claim the gate is actually for.

## Files

| Path | Status |
|---|---|
| `experiments/ad01/invr1b11_budget_probe.py` | new, mine |
| `scripts/b11_route_preflight.py` | new, mine |
| `reports/evidence/invr1b11-budget/budget-probe.json` | new, mine |
| `reports/evidence/invr1b11-budget/store-rows.json` | new, mine |
| `reports/workstreams/b11-probe.md` | new, mine |
| `tests/test_inv_b11_budget_probe.py` | new, mine |

**No production file was edited.** `scripts/invl02_live.py`,
`experiments/ad01/live_construct.py`, `src/settlement/*` and every module under
`reports/evidence/` are untouched. The durable path A1 and A7 built was already
sufficient for this lane; the driver composes it rather than extending it.

The four scratch files this lane used to set up its disposable role, bridge and
rehearsal (`.b11_setup_db.py`, `.b11_check_pg.py`, `.b11_rehearse.py`,
`.b11_reset.py`, `.b11_rebuild.py`, `.b11_export.py`, `.b11_run_gate.py`) are
**not committed**. The credential loader and the route preflight survive as
`scripts/b11_route_preflight.py`, which reads a config path and holds no secret,
because a later live lane on this host will need the same two facts and
rediscovering them costs a dispatch. The disposable database and its role were
**dropped after the export**; the gate passes with no database present at all,
which is the proof that the evidence and not the store is the artifact.

## Not established

- **Rate limits, quota, concurrency.** Six sends bound nothing. UNVERIFIED, and
  the cap sheet's treatment of it as unknown is unchanged.
- **Why the archived 502 is gone.** Transient route behaviour or a changed route,
  and one extra send would not have separated them. The cap sheet's ceiling is
  six and it is spent.
- **Whether 2048 is reliably served.** One success at 2048 is one observation.
  B12, B13 and B16 will supply more, and their runs are where reliability gets
  measured — not here, on a lane whose budget is a ceiling and not a campaign.
- **The unsettled 4096 operation.** It reached the wire and no answer came back.
  Its exposure stands and the store keeps it. It is not resolved by anything in
  this report.
