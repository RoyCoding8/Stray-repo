# B17 — the budget was not the reason

Lane B17. Branch `wt/b17-budgetfit`, forked from `7cc4df7`. B12 left 19
sends unspent and one response that arrived; this lane spends 4 of those
19 and accounts for the rest.

## The answer

**(a). The model produced prose where the protocol asked for code.** Not
(b), not (c), not (d), and each of those three is falsified by
measurement rather than by argument.

| hypothesis | supported | the measurement that decides it |
|---|---|---|
| (a) prose, not code | **yes** | 3 of 3 responses open with "Let me analyze the problem", all stop at `stop_reason: length`, none contains `def STEP` |
| (b) budget truncated a completable response | no | the responses were prose from their first byte; the truncation is real but is not the cause |
| (c) protocol asked for more than the budget carries | no | a **repairing** policy fits: 5551 characters, repairs 3 of 9 dev instances, and clears both 7000 and 2048 |
| (d) the 7000 limit rejected a legitimate artifact | no | the frozen loader admits the authored control's own 22734 bytes, and a 115-byte policy |

## The 22734 is not the response

This is the misreading the lane was warned about, and it is worth
stating plainly because it inverts the conclusion.

**22734 is the AUTHORED CONTROL's length.** It is what B12's 7000 cap
was compared against. The response B12 actually received was **5783
characters**, and the loader refused it as `unparseable-python`. B12
recorded this correctly and did not claim the model returned 22734
characters. What makes 22734 easy to misread is that it sits next to
the acceptance limit in the same artifact, so it reads like a ceiling
the route hit. It is not.

The three quantities are kept apart throughout this lane's artifact:
the **response** (5783 characters observed here, 5382 and 5561 in this
lane's own two), the **authored control** (22734), and the
**acceptance limit** (7000, a constant in B12's driver).

## (d) is false, and it is the hypothesis that makes raising a number look like progress

The frozen loader `verify_step_source` has no length rule at all. It
admits any parseable Python with exactly one top-level
`def STEP(view, state)`. Measured here: the authored control's own 22734
bytes are **admitted**, and a 115-byte policy is **admitted**.

So B12's recorded refusal, `over-length`, is `MAX_SOURCE_CHARACTERS` in
B12's own driver, not a property of the instrument. And the only artifact
that ever reached that cap was the authored **control** — no model
artifact was ever long enough to be rejected, because no model artifact
ever parsed. **No legitimate artifact was rejected at 7000, because none
was ever rejected by anything other than the parser.**

## (c) is false, and this is the measurement that matters

The claim that the protocol asked for more than the budget can carry
fails on a construction. A compact policy that **actually repairs** is:

- **5551 characters**, against a 2048-token budget worth roughly 8000;
- admitted by the frozen loader;
- **repairs 3 of 9 dev instances** through the instrument's own scorer;
- under B12's 7000 cap, and under this lane's own 6000 ceiling.

It is authored offline with zero model calls, so it is a size witness
and never an acquired lineage. Its repair rate is a lower bound on what
the budget can carry, not a claim about the model. The point is only
that **a repairing artifact fits comfortably**. The budget was never the
binding constraint.

## (b) is false as stated, and the nuance is worth keeping

The budget did cut every response. B12's send used 1946 of 2048 tokens
and stopped with 102 unused, ending mid-literal inside a prose trace
(`- window4: "`). Both of this lane's responses stopped at
`output_tokens: 2048` with `stop_reason: length`.

So the truncation is real and measurable. What it is not is a truncated
*policy*. The one fenced block in B12's response is a **restatement of
the faulty program**, not a policy, and the only `def` in it is that
restatement. No continuation of that text was ever going to become a
`def STEP`. Raising the budget would have bought more of the same trace.

## (a) is what the evidence supports, under a protocol changed to give it its best chance

The live arm changed the protocol, frozen before any send: the artifact's
size is stated in **tokens and characters together**, and an analysis
budget is named explicitly. B12 stated 7000 characters against a
2048-token budget — two numbers that disagree, with the larger one
inviting exactly the overrun under study.

Under that changed protocol the model still answered in prose. Both
responses opened with "Let me analyze the problem"; one restated the
program in a fence, the other emitted no code at all; neither contains
`def STEP`; both ran to the budget and were refused `unparseable-python`.

**Every B17 row is marked NON-COMPARABLE with B12.** A changed protocol
does not make older results comparable, and no number here is pooled
with B12's. The only comparison B17 makes is between its own rows.

This is a bounded negative: the size-fitted protocol does not buy
acquisition. Sixteen sends remain unspent and this lane does not spend
them hunting for a positive.

## Every send is durable, and one of them was mine to explain

Four physical sends, four store operations, all under one study-bound
allocation `invr1b17-budget-fit-construction`:

| send | dev task | result | receipt |
|---|---|---|---|
| `probe-b17` | none — a diagnostic | **lost-response**, unresolved | `unknown` |
| `a1` | `swe-dev-count-lead-sum-53207d` | **refused pre-send, 0 sends** | no receipt |
| `a2` | `swe-dev-count-lead-sum-bd7678` | 5382 chars, prose, `stop_reason: length` | `success` |
| `a3` | `swe-dev-scan-depth-5968e4` | 5561 chars, prose, `stop_reason: length` | `success` |
| `a4` | `swe-dev-count-lead-sum-53207d` | route returned 502 | `failure` |

**`probe-b17` was my error and it cost a send.** Diagnosing an
allocation refusal I called `broker.infer` directly with
`deadline_ms=5000`; the route began streaming and the read expired
before the deadline I gave it. It reached the wire, no answer came back,
and it settled `lost-response`/`unresolved` with its exposure standing. A
probe should have used the real deadline or no wire call at all.

`a1` was refused **pre-send** by the broker — the study allocation had
not been seeded yet when that send was first attempted — and it spent no
send. A later retry of the same identity was refused by the broker's
request-identity check (`broker-prep-invr1b17-budgetfit-a1 reused with
different payload`), which is the identity fence doing its job on a
payload from an aborted attempt. `a4` carries the same dev slot with a
fresh identity, which is why its number differs from `a1`.

**4 of 19 sends used. 15 unspent.**

## Honesty of the accounting

- `charge_units`, `charge_scale`, `billed` and `provider_enforced_ceiling`
  are `unknown` on **every** row, including both that returned text. The
  route publishes its price as `usage.cost`, which the adapter
  deliberately does not read. Nothing was written as zero.
- The lost send records `unknown` token counts and is `unsettled` with
  `dispatch_state: unresolved`. It is not a null run and not a cancelled
  run.
- The 502 is a decided `failure` with a status. That is a different
  state from `unknown` and the two stay distinct.
- **This lane's own tiktoken estimate reads `-1` on the send host**,
  because tiktoken is not installed in the venv that reaches the router.
  `-1` is recorded as unavailable rather than as a count, and the
  receipt's `output_tokens` is the authority for what the route produced.
  The offline token measurements in the verdict section were taken on the
  host that has tiktoken and are labelled as cl100k_base proxies.

## No sealed value reached a prompt

Construction runs on dev. Every prompt is built from the world's own
public projection. The gate does not take that on trust: each dev
instance's fault label, mechanism name, protected-case args and
differing reference lines are recorded as
`sealed_values_per_dev_instance`, and every stored prompt is searched for
all of them. Zero hits on every row.

Public test EXPECTED values are deliberately excluded from that list: a
failing public test publishes its own expected value in the public view,
so requiring their absence would assert something false about the
instrument.

## The credential scan is non-vacuous, and proven so

The scan reads the **value** in the environment right now and searches
this lane's written bytes for it, never for the variable name. Before any
live send I proved the scan can fail: it planted a known-bad value in a
temporary file, the scan caught it and named the file, and the plant was
removed. `test_the_credential_scan_is_non_vacuous` asserts that catch.

The scan reads the environment first, then the WSL home, then the Windows
`USERPROFILE`, then the explicit `/mnt/c/...` path. **B12's equivalent
scan read only `~/.claude.json` and took a vacuous branch under WSL**,
where that file does not exist, so a planted credential sat unread and
the test passed. This lane names the environment each branch read, and
`test_the_scan_searches_every_environment_the_value_could_be_in` asserts
all four sources are searched.

No credential value appears in this report, in the artifact, in the store
rows, or in any test. The variable name `SETTLEMENT_GATEWAY_KEY` appears
in the scan's source and nowhere in the evidence.

## The gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/Agent-Society-v2/.worktrees/b17-budgetfit && \
  export SETTLEMENT_CLAIM_LEDGER=/tmp/b17_claims.jsonl && \
  export PYTHONPATH=$PWD:$PWD/src && \
  /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b17_budget_fit.py -q -p no:cacheprovider'
```

`31 passed in 2.24s`

Every assertion is a literal read out of `budget-fit.json` or
`store-rows.json`, not a value recomputed from the driver that wrote
them. The load-bearing one is
`test_no_response_at_or_over_the_budget_is_a_complete_artifact`, which
names every budget-exhausted row and asserts none of them is recorded as
a complete artifact.

**Seven tamper tests, each caught:**

| tamper | caught by |
|---|---|
| a budget-exhausted response marked admitted | 1 test |
| `charge_units` written as `0` instead of `unknown` | 1 test |
| a prose response counted as opening a `STEP` | 1 test |
| the budget widened to the rung B11 measured lost | 1 test |
| spend recorded as 20 of 19 | 1 test |
| B17 marked comparable with B12 | 1 test |
| a sealed value planted in a prompt | 1 test |

Each tamper test first asserts the check **passes** on the untampered
artifact and then asserts it **fails** after the mutation. My first
version of these asserted the tampered payload was still valid, which
proved nothing; the fix is in `_tamper`.

The disposable store was **not** dropped before the gate ran and the gate
reads only files, so it passes with no database present. It is dropped
after this report is committed.

## Files

| Path | Status |
|---|---|
| `experiments/ad01/invr1b17_budget_fit.py` | new, mine |
| `experiments/ad01/invr1b17_compact_reference.py` | new, mine |
| `experiments/ad01/invr1b17_credential_scan.py` | new, mine |
| `reports/evidence/invr1b17-budgetfit/budget-fit.json` | new, mine |
| `reports/evidence/invr1b17-budgetfit/store-rows.json` | new, mine |
| `reports/workstreams/b17-budgetfit.md` | new, mine |
| `tests/test_inv_b17_budget_fit.py` | new, mine |

**No production file was edited.** `src/settlement/*`,
`scripts/invl02_live.py`, `experiments/ad01/live_construct.py` and every
module under `reports/evidence/` are untouched, and B12's four evidence
files are unmodified. The read timeout was set through the adapter's own
override hook rather than by editing a shipped file, exactly as B12 did.

Scratch files used for setup are **not committed**.

## Not established

- **Whether the model can construct a SWE policy at all.** This lane did
  not establish it and does not claim it. Three prose responses at one
  budget, under a protocol that told the model in tokens how big the
  artifact had to be, is three observations of the same behaviour. It is
  evidence that this route at this budget did not produce a policy, not
  evidence of incapability.
- **Rate limits, quota, concurrency.** Four sends bound nothing.
  UNVERIFIED, unchanged from B11 and B12.
- **Whether the 502s are prompt-length dependent.** One 502 here, four
  in B12. Still unresolved, and separating them would cost sends this
  study has no mandate to spend.
- **The lost `probe-b17` operation.** It reached the wire and no answer
  came back. Its exposure stands and the store keeps it. It is not
  resolved by anything in this report.
- **Whether a size-fitted protocol helps a different model.** This lane
  measured one route at one budget. The result is about that route.
