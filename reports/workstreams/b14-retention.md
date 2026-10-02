# B14 — the retention leg, and why it cannot be run

Lane B14. Branch `wt/b14-retention`, forked from `794520f`. The allocation is
in `reports/cap-sheets/b14-retention-freeze.md`, a **new freeze** rather than
an edit to `reports/cap-sheets/b-live-cap.md`.

## The result

**B14 is not runnable live, offline-only, or unrunnable — it is
unrunnable, and the number is 0 of 3.** Three members that this route
acquired live, carried through B3's own arrival path and executed on every
frozen task in their family, give `distinct_verdicts: ["preserved"]` on all
three. **27 measured executions, 0 members with a varying verdict.**

Sweeping the one choice the child menu offers widens the sample and does not
change the answer: **0 of 4 strategy arms measurable**, across both families
and both strategies, at 36 further executions. The menu
(`method_exec.child_contract`) is two values wide, so that is the whole of
what a model can vary on it.

**Zero dispatches were spent. The freeze authorises zero.**

## Why zero is the ceiling and not a preference

The parent sheet recorded B14 as unallocated and gated on B3: *"the
repertoire is closed and identical for every arm, so no difference in
`method_id` can be a retention effect."* B3 landed at `794520f` and opened
that gate. Opening it is not the same as there being something to measure
through it.

**One: the members this route produces carry a constant verdict.**
`invl02_liveacq_r4` is the only study in this tree that acquired members on
the pinned free route and kept the bytes with their receipts. It earned 3 of
6 arms, and its own `live_acquisition: "true"` with all four acquisition
legs passing is what makes those bytes the route's and not a recording. All
three name `"ddmin"`:

```python
def ENTRY(task, oracle, max_queries=16):
    result = reduce_graph(task, oracle, max_queries=max_queries, method="ddmin")
    return {"candidate": result["candidate"], "queries": result["queries"]}
```

Re-measured against the authored seed at a matched budget of 16, the
`ddmin` members are identical to `seed-*-ddmin` on the scored observable
**9 of 9 tasks, on both families**. Two artifacts, one policy.

**Two: the strategy sweep produces a different policy but not a different
verdict.** `greedy` differs from the seed on 0 of 9 graph tasks and 2 of 9
software tasks, so the choice is real and does move the scored observable. It
does not move the **verdict**, which is `preserved` everywhere. A verdict
that is constant is exactly what `retained_leg_verdict` exists to refuse, and
refusing it is the point.

**Three: acquisition is currently returning nothing to carry.** B12 ran the
construction study live today: **0 of 4 `python-step` lineages acquired**,
one send lost mid-stream, two 502s, and the one response that arrived was
5783 characters of prose at `stop_reason: length` that never reached a `def
ENTRY` and was refused as `unparseable-python`. B14 cannot hand a later task
a repertoire holding a member when the current run hands it nothing.

## What is runnable, and what was run instead

The **offline** leg is demonstrated and works. B3's own fixture member,
admitted through the same arrival path and executed through the same
out-of-process route the live members took, gives `["not_preserved",
"preserved"]` over 9 tasks and `retained_method_leg_measurable: true`. A
constant control returns its input and comes back `["preserved"]`, which is
what makes the varying one a discrimination rather than a shape.

**That is a demonstration of the instrument, not an acquisition.** Those
bytes were written in a test. Their `origin` is `fixture-stand-in`, the
artifact's own label field reads `OFFLINE DEMONSTRATION, NOT A LIVE
ACQUISITION`, and the gate fails if any offline row claims `origin:
"acquired"` or `acquired_from_provider: true`.

The B14 driver has **no gateway parameter and names no adapter**, so the zero
is enforced by the module's shape rather than by a promise in prose. The gate
asserts that: a reference to `build_gateway`, `gateway.`, `HttpGatewayAdapter`
or `preflight_route` in the driver fails the test.

## A second blocker, independent of acquisition

Even with a varying member in hand, B14 would still be gated. The three
powered panels are all `graph`, and
`w2_retention_campaign.qualification_census()` reads **0 rows** — the gate's
five authored policies hardcode a `seed-sw-` method, so a graph target is
refused before any reading is taken. `wt/b13b-replseed` repairs the seed
hardcoding and is not merged here. Both blockers sit on the dispatch path and
both are recorded rather than worked around.

## Honesty of the accounting

- **`dispatches: 0`, `requests: 0`, `total_units: 0`.** Not `unknown`. Zero
  is the measured count, and it is exact because nothing reached the wire.
- `per_request_units: 2492` is stated so a later sheet pricing this route
  uses the same arithmetic, and **nothing here is pooled** with a run under
  any other budget.
- `billed` and `charge_units` are `null`, not zero. The route reports price as
  `usage.cost`, which the adapter does not read.
- Carried-in historical exposure is accounted separately and **not netted**:
  a verified uncertain `5563` units and true exposure `>= 5563`. Zero is not
  zero minus 5563.
- **No key value appears in anything this lane wrote.** `SETTLEMENT_GATEWAY_KEY`
  is named and nothing else is.

## The credential scan is proved non-vacuous

B12 found this failure inside its own gate: the scan read `~/.claude.json`,
which does not exist under WSL where the gate runs, and took the
"nothing to search for" branch while the planted value sat unread. This
lane's scan reads the environment variable, the WSL home, `USERPROFILE` and
the explicit `/mnt/c/...` path.

Three assertions, so the zero means something:

1. a real credential is actually located (length >= 16), so the scan is not
   running on an absence;
2. **a planted value is caught** — a marker plus the real value is written to
   a temporary copy of the artifact, the scan must name that file, and the
   file is removed afterwards;
3. the unplanted owned files return zero offenders.

The freeze names the variable and records that the shipped `LIVE_ENV_PATH`
does not exist on this host, which is a route fact rather than a key.

## The route, re-read today

The router answered `401` to an unauthenticated `GET /models`, which is a
live listener refusing an anonymous probe. That is the cheap preflight
`scripts/b11_route_preflight.py` exists for, and it cost zero sends. The
catalog **count** is deliberately not pinned: B11 recorded 255, 256, 219 and
203 entries for the same query, so the precondition is the pinned id's
presence, never a count.

## The gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/Agent-Society-v2/.worktrees/b14-retention && \
  export SETTLEMENT_CLAIM_LEDGER=/tmp/b14_claims.jsonl && \
  export SETTLEMENT_TEST_DSN="dbname=invl02_b14retention host=/var/run/postgresql user=ubuntu" && \
  export SETTLEMENT_TEST_TRUNCATE_DSN="$SETTLEMENT_TEST_DSN" && \
  PYTHONPATH=.:src /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b14_retention.py -q -p no:cacheprovider'
```

Every assertion is a literal read out of `retention.json` or out of the
freeze, never recomputed from the driver that wrote them.

**Eight tamper checks, all eight fired.** Each was run by mutating one field,
running the test that should catch it, and restoring the file:

| tamper | result |
|---|---|
| a live member relabelled as varying | caught |
| an offline row relabelled `origin: "acquired"` | caught |
| the offline demonstration's label dropped | caught |
| a dispatch count of 3 against a ceiling of 0 | caught |
| the offline constant control flipped to measurable | caught |
| the pinned model id no longer ending in `:free` | caught |
| the credential planted inside an owned file | caught |
| a line appended to `b-live-cap.md` | caught |

The credential scan needed a check of its own, because B12's version of this
gate once passed while its plant sat unread. The plant here goes into the
artifact **at its own path**, so the real owned list is what has to find it,
and a separate assertion plants into a temporary file to prove the scan
function itself works before the removal.

Two assertions in this file were **wrong and I fixed the assertion, not the
artifact**:

- The dispatch test asserted `dispatches == 0` as a literal. It now reads
  the cap out of the freeze document and asserts `spent <= cap`, so editing
  one side without the other fails instead of passing.
- The parent-sheet test compared a `git diff` and failed on an unchanged
  file, because the sheet is checked out CRLF and Windows and WSL git
  normalise it differently. It now compares the **content** of the working
  tree against the blob at `794520f` with terminators normalised. A change to
  that document is a change to its words, so the words are what is checked.

The gateway scan is enforced against the driver's **AST with every docstring
and comment stripped**, not its raw text. A text scan for `gateway` flagged
the artifact's own honest `gateway_used: False` field, which is the field
recording that nothing was sent.

## Files

| Path | Status |
|---|---|
| `reports/cap-sheets/b14-retention-freeze.md` | new, mine |
| `reports/evidence/invr1b14-retention/retention.json` | new, mine |
| `experiments/ad01/invr1b14_retention.py` | new, mine |
| `tests/test_inv_b14_retention.py` | new, mine |
| `reports/workstreams/b14-retention.md` | new, mine |

**No production file was edited.** `src/settlement/*`,
`experiments/ad01/w2_retention_campaign.py`, `assessment_profile.py`,
`method_exec.py` and every module under `reports/evidence/` are untouched.
The B3 arrival path and the campaign's leg measurement were already correct;
this lane composed them and measured what they say.

Three scratch probes used to establish the finding before the driver existed
were **not committed**; the driver re-derives every number they printed.

## Not established

- **Whether this route could return a varying member at a budget or framing
  nobody has tried.** Nothing here bounds that. Four observations on a
  menu two values wide is a small sample of the route's behaviour, and this
  study says so in the artifact rather than in a message.
- **Whether an acquired member with a genuinely different walk would vary.**
  The `reason` field separates `ok-preserved` from `ok-incumbent` and B3's
  fixture does vary, so the mechanism works. It is the route's bytes that
  do not carry it.
- **Rate limits, quota, concurrency.** Zero sends bound nothing.
- **Whether the panel blocker lifts on `wt/b13b-replseed`.** It is another
  owner's branch and this lane did not read it as merged.