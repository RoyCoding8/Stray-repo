# r3 freeze — W1 / E1 live Boolean output-shape campaign

Written BEFORE the first dispatch of run `w1-e1-boolean-r3`. No outcome from
this run informs any value in this file. Two reviews found that r2's headline
result rested on inputs the campaign chose rather than inputs the protocol
fixed, and this document is the answer to both findings: it names every
parameter, and for each one says plainly whether the protocol fixed it or this
campaign did.

**Supersedes** `w1-e1-boolean-r2`. r2's records are retained and are not
deleted, repaired, or re-run. They are reported alongside r3 as a different
protocol, not as a cell to merge.

## 1. Which parameters are the campaign's, not the protocol's

This is the section the r2 review asked for. The rule applied: if a shipped
function enforces a value, it is the protocol's. If a value exists only as a
constant and as prompt text, and the campaign's own driver is the only thing
that compares against it, then the campaign chose it and every outcome
measured against it is a statement about this campaign.

| Parameter | Value | Who fixed it | Evidence |
|---|---|---|---|
| Route endpoint | `http://localhost:4000/v1` | protocol | `live_construct.OUTPUT_ROUTE:36` |
| Requested model | `nvidia/nemotron-3-ultra-550b-a55b:free` | protocol | `OUTPUT_ROUTE:38`, re-frozen 2026-09-29 |
| Provider / tier | `nvidia` / `free` | protocol | `OUTPUT_ROUTE:40-41` |
| `max_output_tokens` | 2048 | protocol, and the provider enforces it | `OUTPUT_LIMITS:45`; every r2 text response reported `output_tokens: 2048` and `stop_reason: "length"` |
| Response length cap | **512 characters** | **THE CAMPAIGN. Not the protocol.** | see §2 |
| Score floor | 1.0 | protocol, a literal | `PREFLIGHT_SCORE_FLOOR:1446`, commented as untuned |
| Task seeds | `qual`=11, `audit`=23 | protocol | `OUTPUT_TASKS:51`, both refused otherwise by `output_operation_id:117` |
| Prompt template | `OUTPUT_PROMPT_TEMPLATE` | protocol | `live_construct.py:52-62` |
| Attempt numbers | 1 and 2 | protocol | `render_output_prompt:101` refuses anything else |
| Dispatch deadline | 300000 ms | protocol | the shipped preflight's own value, `live_construct.py:1501` |
| Gateway API surface | `chat` | protocol | `responses` is refused before the wire on a frozen route |
| Corpus, scorer, parser | Boolean rule session, `extract_and_validate_boolean` | protocol | `live_construct.py:917`, `:952` |

**The character cap is this campaign's parameter.** A conforming answer is 143
characters (§3), so the cap is not a physical floor of the exchange. It is a
length discipline the prompt asks for in prose and this campaign checks in
code.

## 2. The 512 cap: what the review said, and what is actually true

The r2 review reported that no shipped function compares a response's length
against `max_response_characters`, so r2's zero was measured against a limit
the campaign chose. **That is correct about the campaign driver and
incomplete about the repository.** Two shipped callers do compare, and they
are the ones that matter for the claim "the protocol fixes it":

- `scripts/invl02_live.py:1195` — `if len(text) > freeze["limits"]["max_response_characters"]` → finalizes `too-long` and continues to the next attempt. This is the shipped live driver.
- `experiments/ad01/offline_recompute.py:2266` — flags `response-character-cap-exceeded` in the offline recomputation.

So the accurate statement is narrower and more damning to r2 than the review's
own wording. The cap is a **protocol constant in the sense that the shipped
driver enforces it**, and a **campaign parameter in the sense that the value
512 has no derivation**. Nothing anywhere explains why 512. It is a literal in
a dict, copied into prompt prose, and the two enforcement sites read the same
literal. The shipped path *does* enforce a character cap; what no shipped code
establishes is that 512 is the right number.

This campaign therefore reports every result at **two caps**:

- **Cap A, 512** — the frozen constant, enforced exactly as the shipped driver
  enforces it.
- **Cap B, unbounded** — the shipped parser's own implied limit, which is the
  cap at which the answer is decided entirely by the protocol and not by a
  number this campaign inherited.

A response is judged at Cap B by `extract_and_validate_boolean` alone. Cap A
and Cap B are not two thresholds on one score; they are two different
questions, and §4 of RESULTS reports both.

## 3. The conforming-answer length, computed before any dispatch

The protocol's own payload validator accepts any object of the shape
`{"specs": [{"const": 0|1, "mask": 0..15, "pair": null|[i,j]} x4]}` with no
other keys (`BOOLEAN_TOP_KEYS`, `BOOLEAN_SPEC_KEYS`, `live_construct.py:892-893`).
The shortest such object is 143 characters, measured with the same
`json.dumps(..., separators=(",",":"))` the campaign uses for candidate digests:

```
{"specs":[{"const":0,"mask":0,"pair":null},{"const":0,"mask":0,"pair":null},{"const":0,"mask":0,"pair":null},{"const":0,"mask":0,"pair":null}]}
```

143 < 512. **The 512 cap therefore does not make a conforming answer
impossible.** It is a hard constraint the model can satisfy and did not. The
brief asked me to check rather than assume this, and the answer is that length
alone is not the binding constraint. What binds is a different, protocol-level
fact, recorded in §5.

## 4. Coverage: both seeds, both attempts, full allowance

`OUTPUT_TASKS` holds two frozen seeds, so the input space over
(task, attempt) is exactly 4 distinct prompts per arm. `render_output_prompt`
takes no sampling parameter — confirmed by reading `ModelRequest` in
`src/settlement/gateway.py`, which carries `reasoning_effort` and no
temperature, `top_p`, or seed, and by scanning `gateway_http.py`, which builds
no sampling field into either payload. There is no protocol knob that would
make two dispatches differ except (task, attempt).

Planned grid, per arm, is all 4 (task × attempt) cells:

| | attempt 1 | attempt 2 |
|---|---|---|
| `qual` seed 11 | yes | yes |
| `audit` seed 23 | yes | yes |

Two arms × 4 cells = 8 construction opportunities, matching `N = 4 × 1 cell ×
2 treatments` in the cap sheet. Model-call ceiling is `N × 2 = 16`.

**Where r2 spent 8 of 16 and zero on repairs, r3 spends 8 of 16 and the
remaining 8 are the second-attempt draws.** No draw is discarded and retried:
every (task, attempt, arm) cell is dispatched exactly once. A second draw at
the same cell is available from the reserve if the first is a transport loss,
and the exposure file records which.

## 5. What n means here, stated before any count

Four draws at one prompt are four samples from one experiment, not four
experiments. The cap sheet's replication rule asks for disjointness of ancestor
chains and says explicitly that requiring distinct digests would bias
acquisition sampling. That rule answers "are these the same lineage?", which
is a question about bookkeeping. It is not a question about whether the
*inputs* differ, and r2 answered the second question with a digest test
applied to the first.

So, stated plainly before any count:

- **A lineage is a distinct operation identity.** Four distinct
  (arm, task, attempt) cells give four distinct operation ids, so the
  bookkeeping count is honest.
- **The independent inputs are the 4 (task, attempt) prompts per arm.** Two
  tasks at one attempt is two different questions. Two attempts at one task is
  the same question asked twice, and the template's only delta is the literal
  string `Attempt 1 of 2` versus `Attempt 2 of 2`. Nothing else changes.
- **n is therefore reported as draws, never as opportunities**, and a draw at
  a repeated prompt is labelled as such.
- **The arm varies too.** P1 gets an empty history, P2 gets two dev-split
  predictor digests. So P1 versus P2 is the only comparison in this campaign
  that varies a substantive input, and even that is one bit of context against
  a single frozen task family.

This is a finding about the harness and it is recorded as one: **the shipped
protocol cannot produce statistically independent repetitions of the same
construction.** It offers 4 distinct prompts per arm and no sampling axis. A
campaign that wanted 16 independent draws would have to change the protocol,
and this lane may not change the protocol.

## 6. Taxonomy, with `over-length` kept out of `invalid-program`

The seven `PREFLIGHT_OUTCOMES` values are kept exactly as
`live_construct.py:1432-1440` defines them. r2 reported every over-length
response as `invalid-program` and then sub-classified it in a reporting field
after the fact. This campaign separates the two decisions at the moment of
classification:

- `over-length` is **this campaign's** classification, raised when a response
  exceeds Cap A and is then set aside for the Cap B re-judgement. It is never
  written into the `outcome` field, and it is never counted as an
  `invalid-program`.
- `invalid-program` is **the parser's** verdict, reached only when the response
  is within Cap A and `extract_and_validate_boolean` refuses it.

Every attempt is recorded whether it succeeded, failed, or was refused. The
five-way taxonomy the brief names stays distinct: `route-refusal`,
`transport-loss`, `empty-content`, `invalid-program`, `poor-task-result`.

## 7. Exposure: written before effects, cost converted

`exposure.json` is written before the first dispatch and rewritten after every
attempt, carrying the planned grid, the settled count, and the guard's
dispatch ledger. `billed` and `charge_units` are read from the provider's own
usage body and reported for every attempt, including failures. r2 left all
eight as `unknown` and therefore counted exposure in attempts and never in
cost; if the provider does not report a charge this run will say so
explicitly rather than letting `unknown` pass as zero.

## 8. Verification: re-derive, never trust a recorded `reason`

A reviewer built a self-consistent forgery that verified clean under r2: a
144-character response carrying a `reason` about a 5211-character one. r2's
verifier trusted the recorded `reason` string and the recorded `outcome`.

This campaign's verifier **withdraws the gateway first** and then re-derives
every claim field from the stored observations:

1. `sha256(raw_response)` must equal the recorded `response_digest`, and
   `raw_response` must be byte-identical to the dispatch's own stored
   `raw_response`.
2. The character count is recomputed from the bytes. No recorded length is
   trusted.
3. The response is re-fed to the protocol's own `extract_and_validate_boolean`
   and `RuleSession.score`. The taxonomy value is recomputed from what those
   return, and compared against the recorded value.
4. The candidate digest is recomputed from the re-parsed payload.
5. `over-length` and `invalid-program` are separated by recomputing both
   questions, not by reading either label.
6. The prompt is re-rendered from the frozen template and its digest compared
   to the recorded `prompt_digest`, so a swapped prompt is caught.

A forgery must therefore be self-consistent against the *bytes*, not merely
against the record's own prose. A short response whose `reason` mentions a
long one fails at step 2, because the reason is never read.

## 9. Stopping rule, fixed in advance

The study stops when the planned 8-opportunity grid is filled. A refusal, a
transport loss, or a no-candidate outcome does **not** authorise a replacement
episode. No authored solver is written after a failure. No prompt is reworded
after seeing a response. No cap is moved after seeing a length. There is no
search for a positive result past the grid, and a negative result is reported
as the result.

## 10. Lineage

| | |
|---|---|
| Campaign id | `w1-e1-boolean-r3` |
| Study root | `invl02-output-shape-550b-r4` (protocol's), campaign root `w1-e1-boolean-r3` |
| Cap sheet | `reports/cap-sheets/w1-e1-cap.md` |
| Standing authority | live testing on a verified free model, this assignment |
| Prior runs retained | `w1-e1-boolean-r1` (invalid, harness), `w1-e1-boolean-r2` (protocol-chosen cap; one task identity at attempt 1, dispatched eight times) |
