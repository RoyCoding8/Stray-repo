# L1 — Retire the raw preflight dispatch

Lane A1. Branch `wt/a1-preflight`, forked from `f03db5b`. Repair of the two
seams `reports/workstreams/inv-a.md` named as S1 and S2.

## What changed and why

### S1 — a preflight send with no identity, no allocation, no receipt

`experiments/ad01/live_construct.py:_preflight_dispatch` built a
`ModelRequest` by hand and handed it to `LiveGuard.infer`, which called the
wrapped adapter directly. `preflight_operation_id` minted an id that nothing
admitted, so the send had no operation row, no reservation, no receipt and no
exposure.

The fix follows the shape `experiments/ad01/construct.py:_call` and
`experiments/ad01/learner_revision.py:_dispatch` already use, rather than a
new one. A new `_DurablePreflightGateway` in `live_construct.py` wraps the
adapter and calls `broker.ensure_operation` then
`broker.dispatch_operation` for every send. `_preflight_dispatch` and
`preflight_run` take a `dsn` and an `allocation_id`, and both are required
together: an operation admitted without an allocation is a row the store
cannot charge.

A durable send ends in a receipt rather than a return value, so
`_response_from_receipt` rebuilds the `ModelResponse` or `GatewayError` the
guard already knows how to read. That is why the guard stays the outer object.
It keeps the route check, the cost block and the evidence ledger, which are
per-attempt observations of one send. What it no longer owns is the send's
admission.

Two properties come from that placement rather than from bookkeeping:

- **A second dispatch of one operation id sends once.** The adapter reads the
  store's receipts before dispatching; a settled operation returns its
  settled text and never reaches the gateway.
- **The spend is the store's count.** `spent_dispatches` runs
  `SELECT COUNT(*) FROM operations WHERE allocation_id = %s`, which moves as
  sends happen and survives a resume or another process.

### S2 — the guard's parallel dispatch counter

`LiveGuard` gained a `spend_reader`. `spent_dispatches` calls it when present,
so `is_ceiling_reached` answers to the store rather than to an integer this
object maintained beside the broker's.

`dispatch_count` (previously `live_construct.py:603`, `self.dispatch_count += 1`)
**was not deleted, and that is a deliberate departure from the lane's
wording.** It is the length of the attempt ledger, and
`experiments/ad01/offline_recompute.py:2125` requires
`candidate_view["dispatch_count"] == len(dispatches)`, which counts refused
attempts as well as sends. Deleting it would have broken that reader and about
twenty test files this lane does not own. It is now documented as the attempt
count rather than the send count, and it is no longer what the ceiling reads.
Two counters of the *send* count was the defect; an attempt count beside the
store's send count is two different facts. **If the coordinator wants the
attribute gone, that is an `offline_recompute` change plus a wave across the
test files that read it, and it belongs to whoever owns those.**

### The four `scripts/invl02_live.py` guard sites

Three of the four named sites (`:1174`, `:1950`, `:2418`) were **already
durable**. Their guard wraps `_DurableBrokerOutput`, which calls
`ensure_operation` with the study allocation, so each send already had a row,
a reservation and a receipt. What they lacked was a store-backed ceiling: they
seeded `already_spent` once at construction. `_guard` now takes an optional
`dsn`/`allocation_id` and installs a `spend_reader`, and `run_e0`, `run_e12`
and `_run_output_locked` pass the dsn they already hold. The allocation is
read off the durable gateway rather than threaded through a signature, because
the gateway is what admits every send on those paths.

The fourth site, `probe` (`:4200`), is **still a bare send**, and it is
reported below rather than changed. See "Not completed".

### The r2 and r3 campaigns

Both took `already_spent` from a JSON file (`exposure.json`), which is the
file-counter defect named as S5. Both now take `--dsn` and `--allocation-id`,
wrap the adapter in `_DurablePreflightGateway`, read the ceiling from the
store, and refuse when one is given without the other. r3's `retry` verb got
the same treatment, because it is a second dispatch site in the same file.

No test calls `r2._run`, `r3._run` or `r3._retry_transport_losses`, so the
signature change is safe. `tests/test_w1_e1_campaign_r3.py` drives `verify`
through `main`, which is untouched.

## Gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/a1-preflight && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a1-preflight/src timeout 1200 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_a_preflight_durable.py tests/test_w1_guard_route_owner.py tests/test_s09_gateway_route.py -q'
```

`17 passed, 1 warning in 25.58s`

The warning is `PytestCacheWarning` on `.pytest_cache`, a WSL/Windows
permission artifact of the worktree path. It is present on the clean base
commit too.

## The three requirement tests

All three are in `tests/test_inv_a_preflight_durable.py` and all three run
against a real PostgreSQL database through the `migrated_db` fixture.

| Requirement | Test |
|---|---|
| Every preflight operation id is a row with a receipt and a settled-or-unknown outcome | `test_a_preflight_send_is_an_operation_with_a_receipt_and_exposure` |
| A second call with the same operation id issues no second send | `test_a_second_dispatch_of_one_operation_id_sends_once` |
| The ceiling is read from the store, not an in-process integer | `test_the_ceiling_is_the_stores_count_and_not_this_processs_integer` |

The third constructs its guard with **no `already_spent` at all**, admits and
dispatches two real broker operations the guard never saw, sets the ceiling to
2, and asserts the send is refused with `refusal_kind == "ceiling"`, that no
operation row was written for the refused attempt, and that the adapter
recorded no send. An in-process integer would read zero and would send.

The adapter is `_RoutedAdapter`, an offline stub, because
`FakeGatewayAdapter` answers with `{"simulated": True}` and no route fields at
all, which the shipped guard refuses on the route check before any of these
claims could be observed. No network, no credential, no live route.

TDD was followed: all three failed first with
`TypeError: _preflight_dispatch() got an unexpected keyword argument 'dsn'`,
which is the defect stated as an interface.

## Raw sends found but not owned

These are real `.infer(` call sites outside this lane's paths. Each is either
already broker-owned or named by another lane.

| Site | State |
|---|---|
| `src/settlement/boot.py:163` | RAW liveness probe at boot. No operation, no receipt. Named in `inv-a.md` (a1) item 2; not in any lane's owned paths. |
| `experiments/ad01/run_c3_qualification.py:95` | RAW live study driver. Named in `inv-a.md` (a1) item 5; not in any lane's owned paths. |
| `scripts/s09_pilot.py:229` | RAW delegating wrapper. Named in `inv-a.md` (a1) item 15 and already described by `tests/test_s09_a8_production_adoption.py::test_the_recorder_is_still_a_second_admission_path` as a second admission path. |
| `scripts/invl02_live.py:4200` (`probe`) | Still a bare send. See below. |
| `experiments/run_dev_episode.py:119` | A scripted double, not a real send. |

## Not completed

**`probe` (`scripts/invl02_live.py:4200`) is still a raw send, deliberately.**
Its signature is `probe(out, *, read_ms, max_tokens, api)`, its `probe` verb
reads only `--out`, `--read-ms` and `--api`, and it is handed a bare
`HttpGatewayAdapter` rather than a durable gateway. It is given no `--dsn`, so
it can create no operation row and there is no store for the ceiling to read.

Making it durable means changing the invocation contract: add `--dsn` and an
allocation, which is a change to the verb's interface rather than a repair of
an authority boundary. `tests/test_c14_live_already_spent_source.py`
(`test_probe_refuses_rather_than_seeding_a_ceiling_it_cannot_ground` and
`test_probe_still_claims_no_dsn_on_the_command_line`) asserts on the current
shape of that verb, and that file is not this lane's to change. **Recorded for
the coordinator: `probe` needs either a `--dsn` (and a matching change to
`tests/test_c14_live_already_spent_source.py`) or an explicit decision that a
diagnostic probe is outside the durable-dispatch requirement.** The code
already states the honest version of itself in a comment at that site: its
spend is zero by construction.

`invl02_live.py` also keeps `_already_spent`, `_output_already_spent` and
`_output_evidence_spent` as three reads of the same currency. They are not a
second dispatch counter and are out of scope here, but they are the same fact
read three ways and are worth one owner.

## Regression runs

`LiveGuard` is constructed in about twenty test files and `scripts/invl02_live.py`
is read from disk at runtime by the C14 assertions, so the change was run
against its consumers rather than assumed safe. Every number below was
measured by running the base commit and this branch over the same file list.

**Guard consumers** (10 files, 142 tests):

```
tests/test_live_integration.py tests/test_s09_n203_dispatch_ceiling.py
tests/test_s09_r6_small_defects.py tests/test_w1_live_preflight.py
tests/test_json_repair.py tests/test_r123_gates.py
tests/test_m0_empty_receipts.py tests/test_s09o_prelive.py
tests/test_w1_preflight_verdict_teeth.py
tests/test_c14_live_already_spent_source.py
```

`2 failed, 139 passed, 1 skipped`. Both failures are
`tests/test_c14_live_already_spent_source.py`, and both reproduce on the
stashed base commit with the same file list:

- `test_the_dead_name_is_no_longer_a_reader_anywhere` asserts the dead name is
  read from exactly `["scripts/s09_pilot.py:1109"]`. On this worktree that
  reader is at `scripts/s09_pilot.py:1101`. `scripts/s09_pilot.py` is **not in
  this lane's diff**, so the line moved under the test from another lane's
  concurrent work in the shared checkout. Pre-existing, and a shared-worktree
  ordering artifact rather than a property of this branch.
- `test_the_probe_verb_offers_no_dsn_flag` initially failed here and **does not
  reproduce**. It failed only in the run where I was editing
  `scripts/invl02_live.py` concurrently: the assertion reads
  `inspect.getsource(driver.main)` from disk at runtime, so it read a
  half-written file. It passes on this branch in isolation and in the clean
  confirmation run below. My first instinct was that I had added a `--dsn` to
  the probe verb. I had not, and the block at `scripts/invl02_live.py:4340`
  still offers `--out`, `--read-ms` and `--api` only.

**Durable-gateway consumers**: `tests/test_output_evidence.py`,
`tests/test_r4_live_blockers.py`, `tests/test_resume_exposure_fidelity.py`.
`6 failed, 106 passed`, all six in `test_output_evidence.py`, and **all six
reproduce identically on the stashed base**. They are the pre-existing
`test_output_run_real_gateway_route_mismatch_is_terminal`,
`test_output_route_uses_authorized_exact_ids`, four
`test_model_list_preflight_refuses_*` cases, and they fail at
`test_output_evidence.py:1546` with `DID NOT RAISE ValueError`, which is a
gateway-route-pricing assertion about `HttpGatewayAdapter` and not about
dispatch durability.

**r2/r3 campaigns**: `tests/test_w1_e1_campaign_r2.py`,
`tests/test_w1_e1_campaign_r3.py`, `tests/test_w1_e1_claim_rederivation.py`.
`49 passed`.

**Clean confirmation run** (gate plus both failing suites, no concurrent edits):

```
pytest tests/test_inv_a_preflight_durable.py tests/test_w1_guard_route_owner.py
       tests/test_s09_gateway_route.py tests/test_c14_live_already_spent_source.py
       tests/test_output_evidence.py -q
```

`7 failed, 113 passed` — exactly the seven base failures and no others. **No
test regressed on this branch.**

Not measured, and left that way on purpose: the full suite. Four other lanes
were running concurrently in the same WSL instance, and the coordinator's
resource policy caps this lane at one scoped run.

