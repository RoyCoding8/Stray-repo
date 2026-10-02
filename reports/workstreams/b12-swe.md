# B12 — the SWE matrix, constructed live

Lane B12. Branch `wt/b12-swe`, forked from `e7d0e3f`. The SWE construction
run on the cap sheet's verified free route, at the bounds
`reports/cap-sheets/b-live-cap.md` froze.

## The result

**Zero acquired lineages out of four. 5 dispatches, 5 physical sends.**
Every cell is a no-acquisition row, and none is replaced by an authored
arm. That is the honest reading of this route at this budget, and it is
recorded as such rather than searched past.

| cell | lineages | acquired | no-acquisition | dispatches |
|---|---:|---:|---:|---:|
| `python-step` | 4 | 0 | 4 | 5 |

Two other representation cells were **not run**: `typed-ast` and
`action-graph` are refused by their own frozen loaders for reasons
recorded in `reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`, and no
prompt changes a loader's node set. So the matrix here is one cell of four
lineages, which is the whole matrix rather than a trimmed one.

## What the four lineages actually did

| lineage | framing | send | outcome |
|---|---|---|---|
| L0 | probe-first | `L0-a1` | response lost; settled `unknown` |
| L1 | direct-diagnosis | `L1-a1` | route returned 502 |
| L2 | localise-then-edit | `L2-a1` | route returned 502 |
| L3 | exhaustive-then-commit | `L3-a1` | **5783 characters returned, refused by the loader** |
| L3 | repair of L3-a1 | `L3-a2` | route returned 502 |

One send produced text. Three died at the route. The single text response
is the informative one, and it is the finding:

**The one response that arrived was truncated by the budget, not by the
model's ability.** `stop_reason: length`, `output_tokens: 2048`, exactly
the requested budget. The model opened with `Let me analyze the task...`
and worked through a manual trace of the failing test case in prose,
solving the arithmetic in its reasoning and never reaching a `def STEP`
definition. The loader refused it as `unparseable-python`, correctly: what
came back was analysis, not policy.

## The length finding the study rests on

The authored control policy is **22734 characters**. This lane's own gate
accepts at most 7000. 2048 output tokens is roughly eight thousand
characters, so **no response at the frozen budget could have carried the
authored policy**. That comparison is recorded in the artifact as
`authored_control.control_is_unreachable_at_this_budget: true`, and the
gate asserts it.

This is why the study asks whether a *smaller* policy can repair rather
than asking for a copy of the authored one. The comparison is real, and it
is recorded rather than assumed.

## The finding about the read timeout

The first send was lost at **61.4 seconds** against a 300000 ms deadline
that had barely begun. Root cause: `HttpGatewayAdapter`'s shipped
**read timeout is 60000 ms** (`src/settlement/gateway_http.py:541`). The
route began streaming a multi-thousand-character policy and took longer
than a minute, so the read expired mid-stream.

**No production file was edited.** The adapter reads its credential from the
environment variable `gateway.api_key_env` names, which is
`SETTLEMENT_GATEWAY_KEY`, and its timeouts from
`gateway_timeout_overrides()`, which reads
`SETTLEMENT_GATEWAY_TIMEOUT_READ_MS`. This lane sets that to 280000 ms —
under the cap sheet's deadline, over the shipped default. Leaving a
60-second read under a 300-second deadline would have silently replaced the
frozen bound with a different one, and every later send would have failed
the same way.

**No credential value appears in this report, in this repository, or in any
evidence file it references.** `SETTLEMENT_GATEWAY_KEY` is named here and
nothing else is; the value lives outside Git, and the gate scans this
lane's written bytes for it rather than taking this claim on trust.

The cost of finding this was **one send**. The cost of not finding it would
have been the whole study.

## Two sends this lane spent on itself

- **`L0-a1`** (lost) and **`L1-a1`** (502) were dispatched while diagnosing
  the read timeout, before the artifact existed. Both are durable
  operations under the study allocation and both cost real wire sends. The
  artifact reconciles them explicitly rather than leaving the store's count
  exceeding the sum of the lineage rows.
- The lane then hit a provenance defect: on a resumed run, an already-spent
  operation is READ rather than re-sent, and my first implementation
  recorded it as a bare outcome — **losing L3's 5783-character response
  from the artifact while the store still held it**. The gate caught it. A
  re-read now recovers the text from the receipt's own content and re-runs
  the gate offline, marked `source_recovered_from_store`.

No send was re-spent to recover anything. That is B11's pattern and it held:
the evidence is the store's account, not a second execution's.

## Every send is durable

All five sends are broker operations under one study-bound allocation
`invr1b12-swe-construction`, study root `invr1b12-swe`:

| send | operation row | allocation | reservation | receipt |
|---|---|---|---:|---|
| `L0-a1` | 1 | bound | 2700 | `unknown` (lost-response) |
| `L1-a1` | 1 | bound | 2703 | `failure` (502) |
| `L2-a1` | 1 | bound | 2702 | `failure` (502) |
| `L3-a1` | 1 | bound | 2723 | `success` |
| `L3-a2` | 1 | bound | 2771 | `failure` (502) |

`automatic_retries` is pinned to 0. A 502 is retryable and the shipped
default is 3, which would have spent four physical sends on one lineage and
broken the ceiling. The one authorised repair is a second *prompt* carrying
the loader's own refusal, not a transport retry — and it was spent only on
L3, the one lineage that produced a repairable candidate. The two 502s did
not earn a repair, because there was nothing to show back.

**19 physical sends of the 25 authorised were left unspent.** The cap sheet
prices 24 dispatches; this run used 5.

## Honesty of the accounting

- `charge_units`, `charge_scale`, `billed` and `provider_enforced_ceiling`
  are `unknown` on **every** send, including the one that returned text.
  The route publishes its price as `usage.cost`, which the adapter
  deliberately does not read. Nothing was written as zero.
- The lost send records `input_tokens: unknown` and `output_tokens:
  unknown`. A lost send consumed an unknown amount.
- The lost send is `unsettled` with `dispatch_state: unresolved`. It is not
  a null run and not a cancelled run, and the artifact says which.
- Three sends that returned 502 are `failure` with a status, which is a
  different decided state from `unknown`. They stay distinct.

## The catalog drifted again

The cap sheet records "219 entries". This run's read at dispatch: **203
entries, 32 free-tier, pinned id present, verdict `accepted`**. B11 saw
255, 256, 219 and 203. The count is not a stable number and the artifact's
precondition is the pinned id's presence, re-read at dispatch. The gate
deliberately does **not** assert a count.

## No sealed value reached a prompt

Construction runs on `dev`. Every prompt is built from
`SweSession.policy_view()`, the world's own public projection, so a leak
would need the projection itself to carry one. The gate does not take that
on trust: each dev instance's `FAULT_LABEL_KEYS` values, its mechanism
name, its protected-case args and its differing reference lines are
recorded as `sealed_values_per_dev_instance`, and every stored prompt is
searched for all of them.

Public test EXPECTED values are deliberately excluded from that list. A
failing public test publishes its own expected value in the public view, so
requiring their absence would assert something false about the instrument.

**I verified this scan is not vacuous** by planting the real sealed
reference line into a stored prompt; the gate failed and named the file and
the value. I also planted the real credential value into the workstream
report; the gate failed and named the file.

## A defect in this lane's own gate, found by using it

The credential scan read `~/.claude.json` and took the "no credential
present, the scan is vacuous" branch — **under WSL, where the gate runs**.
WSL and Windows have different home directories and WSL has no
`~/.claude.json`, so the planted credential was sitting in a file the scan
had never read and the test passed.

This is exactly the failure mode the gate exists to prevent, found in the
gate itself. `_credential_value()` now reads the environment variable, the
WSL home, the Windows `USERPROFILE`, and the explicit `/mnt/c/...` path,
and the vacuous branch says which environment it ran in rather than
passing quietly. Re-verified with the planted credential: the gate now
fails under WSL and names the file.

## The use arm

The use arm ran and spent **zero dispatches**. Every lineage is
no-acquisition, so there is no acquired policy to run over held-out
instances, and each row records why it was not run.

That is worth stating plainly, because it is a departure from the cap
sheet's pricing. The sheet prices use at one send per instance
(`4 lineages x 4 held-out instances = 16`), on the assumption that use is
a wire call. It is not: use is local execution of bytes already in hand.
The artifact records `dispatches_used_by_use_arm: 0` and the gate asserts
it. Had there been acquired lineages, they would have run under WSL in the
existing bounded child, because model-authored bytes are untrusted
candidate code and the coordinator host does not execute them.

## The gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/Agent-Society-v2/.worktrees/b12-swe && \
  export SETTLEMENT_CLAIM_LEDGER=/tmp/b12_claims.jsonl && \
  export SETTLEMENT_TEST_DSN="dbname=invl02_b12 host=/var/run/postgresql user=b12swe password=$(cat /tmp/.b12pw)" && \
  export SETTLEMENT_TEST_TRUNCATE_DSN="$SETTLEMENT_TEST_DSN" && \
  export PYTHONPATH=... && \
  /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b12_swe_construction.py -q -p no:cacheprovider'
```

`14 passed in 2.96s`

Every assertion is a literal read out of `campaign.json` or
`store-rows.json`, not a value recomputed from the driver that wrote them.
Three assertions count operations against **distinct lineage attempts**
rather than attempts in general, because four identical responses would be
one lineage wearing four names.

**Four tamper tests, each caught:**

| tamper | caught by |
|---|---|
| a no-acquisition row marked acquired with the control's digest | 3 tests |
| a sealed reference line planted in a stored prompt | 2 tests |
| `charge_units` written as `0` instead of `unknown` | 1 test |
| the real credential planted in the workstream report | 1 test |

The disposable store was **dropped after the export**; the gate reads only
files, so it passes with no database present.

## Files

| Path | Status |
|---|---|
| `experiments/ad01/invr1b12_swe_construction.py` | new, mine |
| `reports/evidence/invr1b12-swe/campaign.json` | new, mine |
| `reports/evidence/invr1b12-swe/construction.json` | new, mine |
| `reports/evidence/invr1b12-swe/use.json` | new, mine |
| `reports/evidence/invr1b12-swe/store-rows.json` | new, mine |
| `reports/workstreams/b12-swe.md` | new, mine |
| `tests/test_inv_b12_swe_construction.py` | new, mine |

**No production file was edited.** `src/settlement/*`, `scripts/invl02_live.py`,
`experiments/ad01/live_construct.py` and every module under
`reports/evidence/` are untouched. The durable path A1 and A7 built was
sufficient; the driver composes it rather than extending it, and the read
timeout was a configuration change through the adapter's own override hook
rather than an edit.

Scratch files used for setup are **not committed**.

## Not established

- **Whether the model can construct a SWE policy at all.** Four lineages at
  one budget is four observations, and three of them died at the route
  rather than at the model. This is not evidence of incapability; it is
  evidence that this route at 2048 tokens did not deliver a policy in five
  tries. The cap sheet's remaining 19 sends are unspent and could price the
  question properly, but that is a new decision, not mine to make here.
- **Rate limits, quota, concurrency.** Five sends bound nothing.
  UNVERIFIED, unchanged from the cap sheet.
- **Whether 502 is prompt-length dependent.** The three 502s and one
  truncated success are suggestive but one success cannot establish a
  relationship. Separating them would cost sends this lane no longer has a
  mandate to spend.
- **The unsettled L0-a1 operation.** It reached the wire and no answer came
  back. Its exposure stands and the store keeps it.