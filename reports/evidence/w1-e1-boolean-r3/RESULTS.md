# W1 / E1 r3 results — live Boolean output-shape campaign

Campaign `w1-e1-boolean-r3`. Freeze: `FREEZE.md`, written before the first
dispatch. Driver: `experiments/ad01/w1_e1_campaign_r3.py`. Verifier tests:
`tests/test_w1_e1_campaign_r3.py`. r2 forensics:
`experiments/ad01/w1_e1_r2_forensics.py`. Route probe:
`experiments/ad01/w1_e1_route_probe_r3.py`.

**Headline.** Zero constructions, and the 512-character cap is not why. The
three responses that reached the campaign fail at any length, because the
model narrates instead of committing. But **9 of 12 records are lost sends**,
so the largest single cause of this campaign's zero is the route's
availability, and r3 reproduces r2's failure mode rather than escaping it.
What it says about the model rests on three responses from one arm.

## 1. What was frozen, and which parameters are the campaign's

`FREEZE.md` carries the full table. The short form, in the order a reader
needs it:

**The protocol's**, and enforced by shipped code: the route
(`http://localhost:4000/v1`, `nvidia/nemotron-3-ultra-550b-a55b:free`,
provider `nvidia`, tier `free`), `max_output_tokens: 2048`, the score floor
of 1.0, the two task seeds (`qual`=11, `audit`=23), the prompt template, the
two attempt numbers, the 300 s dispatch deadline, and the `chat` surface.

**This campaign's, not the protocol's**: the **512-character response cap**.
Nothing derives the number 512. It is a literal in a dict, copied into the
prompt's prose, and read by two shipped callers. It is not compared by
`LiveGuard`, by `render_output_prompt`, by `extract_and_validate_boolean`, or
by the scorer, so on the acquisition path the cap is a length discipline the
prompt asks for in words and this campaign checks in code.

The review said no shipped function compares a response's length against
`max_response_characters`. That is true of `live_construct.py` and false of
the repository: `scripts/invl02_live.py:1195` finalizes `too-long` and
`scripts/…` continues to the next attempt, and
`experiments/ad01/offline_recompute.py:2266` flags
`response-character-cap-exceeded`. So the honest statement is narrower than
either the review's or r2's: **the cap is a protocol constant that the shipped
driver enforces, and a number whose value no shipped code justifies.** The
campaign is therefore reported at two caps throughout.

## 2. Results at each cap, and whether the cap explains the outcome

| | Cap A (512, frozen) | Cap B (unbounded, the parser's own limit) |
|---|---|---|
| constructed | 0 | 0 |
| poor-task-result | 0 | 0 |
| invalid-program | 3 | 3 |
| transport-loss | 9 | 9 |
| **construction events** | **0** | **0** |

**The cap does not explain the outcome, and this is the load-bearing result of
this run.** The shortest payload the protocol's own validator accepts is
**143 characters** (`{"specs":[{"const":0,"mask":0,"pair":null} …x4]}`), so a
512 cap leaves ample room and cannot make a conforming answer impossible. The
three responses that reached the campaign are 5425, 4805 and 4685 characters.
Re-judged at Cap B with no length check at all, all three still fail:
`extract_and_validate_boolean` refuses each with "boolean payload is not
JSON". So moving the cap to any value changes no classification.

The mechanism is visible in the bytes. The model does not emit a too-long
program. It **narrates its reasoning in prose and is cut off at the
output-token ceiling before it ever writes the JSON object.** In
`P1-qual-a1-retry1` the literal token `specs` appears twice, and both
occurrences are inside English sentences ("The predictor is represented as a
list of 4 specs, each spec is an object with…"). The response runs to 5425
characters of derivation and stops mid-word ("…XOR) flips the"). Every
response that arrived reported `stop_reason: "length"` with
`output_tokens: 2048` against the requested cap of 2048, so the provider
enforced the budget and the model spent all of it thinking.

That is a protocol-level fact, not a cap-level one, and it is the correct
reading of r2 as well. Re-judging **r2's own stored bytes** under this run's
rules (`w1_e1_r2_forensics.py`): r2 recorded 6 text responses, all 6 over the
512 cap, and **0 of 6 parse at any length.** r2's headline is therefore
correct as a classification and wrong as an explanation. The cap decided the
label; the model's failure to commit a program decided the result.

## 3. Task × attempt coverage, and what n means

The grid is 2 arms × 2 seeds × 2 attempts = **8 cells, all 8 dispatched**,
which is the cap sheet's `N = 4 × 1 supported cell × 2 treatments`. All 8
prompts have distinct digests, confirmed in the manifest.

**r2's coverage was narrower than its own summary claimed, and the evidence
says so directly.** All eight of its records carry `split=qual seed=11` and
operation ids ending `-qual-0011-a1`. Its manifest records exactly two prompt
digests, one per arm. So r2 dispatched **one task identity, at attempt 1,
across both arms, eight times.** The audit seed the protocol freezes beside
`qual` was never dispatched at all, and the "four independent lineages per
treatment" were two prompts sent four times each. That is a supersession
reason in its own right, stronger than the one this campaign's code first
carried, and it is why r2's rows are reported beside r3 rather than merged
into it.

**n is draws, not opportunities.** The cap sheet's replication rule asks for
disjointness of ancestor chains and states that requiring distinct digests
would bias acquisition sampling. That is a rule about lineage bookkeeping. It
does not make the *inputs* differ, and r2 answered the input question with a
digest test. What the protocol can actually vary is now measured: `ModelRequest`
carries `reasoning_effort` and no temperature, `top_p`, or seed, and
`gateway_http` builds no sampling field into either payload. **The protocol
offers 4 distinct prompts per arm and no repetition axis.** A draw at a
repeated prompt would be 4 samples from one experiment, not 4 experiments.

| arm | draws | distinct prompts | repeat draws | outcomes |
|---|---:|---:|---:|---|
| P1 | 8 | 4 | 4 | 3 invalid-program, 5 transport-loss |
| P2 | 4 | 4 | 0 | 4 transport-loss |

**The P1 arm's 8 draws are 4 distinct prompts drawn twice, and the campaign
says so in its own summary rather than counting 8 opportunities.** They are 4
first attempts plus 4 reserve retries of cells whose first draw was a 502, and
the retries reused the same operation identity, so they are retries and not
replications. Every draw at a prompt is a repeat by construction once the
reserve is spent.

**Arm coverage is confounded with retry order, and this limits what the arms
can be compared on.** The exposure grid lists P1 cells first, the retry pass
follows that order, and the ceiling was reached during the P1 block. So all
three responses that arrived are P1, and **P2 has no response bytes at all.**
The P1-versus-P2 comparison the cell exists to make is therefore not
established: it is not "P1 produces longer output than P2", it is "the reserve
ran out before P2 was retried once". A reader must not take the arm contrast
from this run.

## 4. Construction events / unique programs / retained records

| | |
|---|---:|
| construction events | **0** |
| unique source programs | **0** |
| retained artifact records | **12** |

Twelve records: the 8 planned cells plus 4 retry records. Zero construction
events and zero unique programs is honest and is not a defect in the counting.
A construction event is a cell whose bytes parsed and ran; no bytes parsed.

## 5. `billed` / `charge_units` for every attempt

**All 12 records: `billed: "unknown"`, `charge_units: "unknown"`.** The
aggregate is **null, not zero**, and unknown is never written as zero.

This is a harness fact, measured. The live body returns
`usage.cost: 0` and a `cost_details` block. The adapter's `_decode_usage`
reads `charge_units`, `charge_scale` and `billed`, none of which this route
returns, so every field stays unknown. `gateway_http.py:356-368` documents the
`usage.cost: 0` measurement and states that `usage.cost` is deliberately not a
channel, so the adapter behaves as designed. **The consequence is that this
route cannot convert exposure into cost at all**, which is exactly the gap that
left r2's eight attempts uncosted. r3 closes the reporting half: the number is
stated, its cause is identified, and it is not passed off as free.

Token counts are recorded where the body carried them: the three responses
that arrived report `input_tokens` 370 or 371 and `output_tokens` 2048, against
a requested cap of 2048. The nine lost sends report `"unknown"` for every
token field, which is the honest value for a 502.

## 6. Live calls against the cap sheet line

| | |
|---|---:|
| cap sheet ceiling, `N × 2` | **16** |
| dispatches spent | **16** |
| of which carried in from a driver-faulted first attempt | 4 |
| of which the 8 planned cells | 8 |
| of which reserve retries of lost sends | 4 |

**The campaign spent exactly its ceiling and no more**, and the guard refused
the fifth retry on that ceiling rather than exceeding it. The 4 carried-in
dispatches were a driver fault of this lane's own (a `KeyError` on a field
name, caught and fixed). They are carried into the guard's ledger on resume
rather than erased, because a campaign that crashes its way to a fresh
allowance is not the same campaign. Retries reuse the same `round_run_id` and
therefore the same `output_operation_id`, so they are one lineage drawn twice
and are counted as such, per the cap sheet's "≤ 1 retry per operation identity"
row. Retries were spent only on cells whose first draw was an HTTP 502, which
is the route's availability and not a model result.

One bookkeeping note, reported because the summary publishes it: the exposure
file's `attempts_settled` (8) does not match the count re-derived from the
records (12), because the 4 retry records are written by the retry pass and the
grid's settled count is not rewritten for them. The summary reports both
numbers and `exposure_agrees_with_records: false`. The re-derived 12 is the one
the tables above use. This is the check red-proof #9 asked for, and it caught a
real inconsistency in my own bookkeeping rather than passing silently.

## 7. The route defect r3 hit, measured

The 8 planned cells all returned **HTTP 502** from the router
(`"router: upstream response interrupted"`, `"router: upstream unreachable"`).
Reproduced outside this driver, with plain `curl` and the same prompt, so it
is not a defect in the campaign code.

Two further measured facts about the route, recorded in `route-probe.json`:

- **The frozen model is absent from the live catalog.** The catalog returns
  256 entries and does not list `nvidia/nemotron-3-ultra-550b-a55b:free`;
  the same model appears as `kilo/nvidia/nemotron-3-ultra-550b-a55b:free`.
  Dispatching the frozen id anyway returns HTTP 200 naming that exact id. The
  route is reachable and unpinnable at once. This is the same class of
  configuration drift the 2026-09-29 re-freeze corrected once already, and the
  cap sheet's "Route spelling re-frozen" precondition is not actually holding.
- **The 502 correlates with the requested output budget, not the prompt.** The
  same protocol prompt returns 200 at `max_tokens` 16 and 256, and 502s at the
  protocol's own 2048. A short prompt returns 200 at 2048. The two variables
  separate cleanly, and the protocol's `max_output_tokens: 2048` is what puts
  this route into the failing combination.

None of this is patched. This lane may not edit a shipped module, so all three
route findings are reported and left to the route contract's owner.

## 8. A second defect found in r2's census, reported not patched

`w1_e1_campaign_r2.acquisition_census` skips any path containing a
`.worktrees` component, and its `REPO_ROOT` is derived from the driver's own
location. **Run from inside a worktree, that filter discards every file in the
repository: 451 files exist, 0 are parsed, and the census reports
`files_examined: 0` while still asserting its conclusion.** Measured:
449 files parsed from the coordinator root, 0 from a worktree root.

r2's published manifest is unaffected, because r2 ran from the coordinator
checkout and recorded 41 acquisition sites over 449 files. The conclusion
stands. But any lane that reruns the census from a worktree gets a census that
searched nothing and cannot tell the difference, which is the failure mode the
census was written to prevent. Reported, not patched.

## 9. The verifier, and its red-proof

`verify` withdraws `LiveGuard.infer` first, then re-derives every claim field
from the stored bytes. The recorded `reason` is display-only and is never an
input to a verdict. Re-derived: response digest, character count, Cap A
outcome, Cap B verdict, candidate digest, score, prompt identity, operation
identity, and the route through the shipped `route_matches`.

On this campaign's own 12 records, with the three denominators published
separately so no table can collapse them:

| | |
|---|---:|
| records on disk | **12** |
| of which carry response bytes to re-derive | **3** |
| of which are lost sends with nothing to attest | **9** |
| re-derived clean | **3** |
| failures | **0** |

A 502 leaves no bytes to re-derive, which is neither a pass nor a failure, so
it is counted in its own column. The earlier phrasing "12 checked, 3 passed"
put two different denominators in one sentence and was wrong to read as a
coverage figure.

**One tradeoff, stated because it is the only place this campaign
re-implements a shipped rule.** `settlement.gateway_http.route_matches` is a
pure field comparison, but importing it executes that module's `import httpx`,
and the offline contract is that a third party reproduces every number with
the directory and the repository and nothing else. So the comparison exists
here in two forms: the shipped rule, and a restatement in
`_route_fields_match` for a host where importing `gateway_http` fails on its
transport. `_assert_route_rules_agree` checks both against a fixed case list
on every run, so they cannot drift apart and the verifier's verdict cannot
depend on which host it ran on.

The shipped half is read by import where that works, and out of the parsed
source where it does not, so the agreement is pinned on a host that cannot
import the module at all. Reading it out of the source is not a third copy:
it executes the repository's own text with `httpx` never imported, so it
cannot drift the way a copy can. Every other check in `verify` calls shipped
code; the restatement is the exception.

The red-proofs are in `tests/test_w1_e1_campaign_r3.py`, 13 tests, all green.
Eight are forgeries of my own construction, written so that a verifier tuned to
catch only the known r2 forgery cannot pass them:

1. the r2 forgery rebuilt: a 144-character response carrying a
   5211-character `reason`, with the record's own prose, outcome and counts all
   agreeing with each other;
2. a forged character count over correct bytes;
3. a forged `over_length` flag on a conforming answer;
4. a fabricated perfect score;
5. `invalid-program` on a payload that parses (the mirror of #1, and the
   branch r2's taxonomy could hide);
6. **swapped response bytes with a recomputed digest**, so the candidate
   digest and the Cap B verdict are also recomputed to match — the check most
   obvious integrity controls would pass;
7. a paid route (`provider: openai`) stamped onto a dispatched response;
8. a qual-split record filed under the audit seed.

Two more tests pin the control that makes the red-proofs meaningful: an
untampered corpus of 3 records must verify clean, and `verify` must reach for
the gateway zero times. Without the first, a verifier that refuses everything
would pass every red-proof.

One further fix came out of writing the tests: `summarize` was trusting
`exposure.json`'s `attempts_settled`. It now re-derives the count from the
records and publishes the file's own number beside it, so an under-reporting
exposure file is visible rather than authoritative. That was a real gap in my
own code, found by red-proof #9 before it reached a live record.

## 10. What E1 now shows, and does not

**Shows.** The model, asked to commit a Boolean predictor through the shipped
path, spent its entire output-token budget narrating its reasoning and never
emitted the JSON object, in all three responses that reached the campaign, and
in all six of r2's independent responses six days of protocol drift earlier.
That is reproducible across both frozen tasks and both attempt numbers, so it
is a property of the model on this protocol rather than of one campaign's
inputs. The 512 cap does not explain it: the responses fail at any cap, and a
conforming answer would fit in 143 characters.

**And the shape of r3's zero is r2's shape, which is the honest headline.**
Nine of r3's twelve records are lost sends and only three ever returned bytes,
exactly as r2 recorded six of eight lost and six returned. So r3 did not
escape r2's failure mode; it reproduced it with better coverage. **The largest
single cause of r3's zero is the route's availability, not the character cap
and not the model.** The cap is ruled out by measurement, but ruling it out
does not promote the model to the explanation, because 9 of 12 attempts never
reached the model at all. What r3 establishes about the model rests on three
responses, all from one arm.

**Does not show.** It says nothing about model *capability*, because the
responses never reached the point of being a wrong program. It does not
establish the P1-versus-P2 contrast the cell exists to make: the reserve was
spent entirely on P1, so P2 has no response bytes and the arm difference is
unmeasured. It says nothing about the other E1 cells, which the acquisition
census confirms have no shipped acquisition path at all. And it cannot produce
independent repetitions of one construction, because the protocol offers no
sampling axis.
