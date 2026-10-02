# Stage 09: four open causes, four different questions

The four open causes in `reviews/STAGE-09-SUITE-AFTER.md` §6, each
reproduced under `scripts/run_bounded.py` and then read from the source
rather than fixed by adjusting a number. Fifteen rows. Four files. Nine
of the rows turned out to be stale tests meeting deliberate changes, two
were a second cause hiding behind a five-row count, one was an
unfailable assertion, and two were mine and wrong.

Every fix here is a test edit. No product file changed, so no lane's owned
file is implicated.

| Rows | File | Verdict | Commit that moved the behaviour |
|---|---|---|---|
| 4 | `test_bdr01_host_boundary.py` | 2 stale (`f1d8ada`), 2 stale (`77001fc`) | 2026-09-29 and 2026-09-26 |
| 4 | `test_gateway_usage_unknown.py` | stale, product correct | `59a10df`, 2026-09-24 02:05:57 |
| 5 | `test_ec02ad_verif.py` | 3 environmental, 1 unfailable, 2 a second cause | `ff65b2a` 2026-09-16, `a41d4b3` 2026-09-20 |
| 2 | `test_broker_prepare.py` | stale, product correct | `59a10df`, 2026-09-24 02:05:57 |

## 1. BDR-01: the replay trace

`f1d8ada` (2026-09-29 06:14) set `result["query_trace"] = None` when a
durable receipt replays a settled operation. The census read all four
rows as that. Two are. The other two are `policy=None`, below.

**What the replay path does today.** `method_exec` builds the trace on
the host side, in `serve`, one row per `oracle.query` the child made. It
lives in a local list and goes nowhere else: `_durable_receipt` reads
`receipt_identity, outcome, content, content_digest`, and `_result`
rebuilds `candidate`, `queries` and the digests from that. The receipt
does not carry the walk. Replaying a settled operation therefore cannot
reconstruct it, at any number of replays.

**What the boundary actually protects.** The replay must be idempotent
for everything the receipt can answer, and must not claim to have done
something in the process that did not do it. Both matter; they pull in
opposite directions on one field.

### The two answers, and what an adversarial replay gains

**Answer A — idempotent replay: compare the trace, and reject on
difference.** The replay reconstructs the first walk and refuses if it
differs. The gain an adversary gets: to pass, it must supply a walk that
matches, and a walk it never took is one it must have read off the first
run's evidence and re-asserted. That converts an honesty property into a
verifiability one, and it verifies the wrong thing: the walk was graded
inside the first child process, and the replay runs a *different* child
with the same source and the same durable operation identity. A
mismatching trace would most often mean the oracle's world state moved,
not that anyone lied, and the field is not the receipt, so a refusal here
throws away a genuinely settled operation over a value the store never
owned. It also buys nothing against the adversary that matters, because
the adversary controls the *first* run: it can simply make the first walk
whatever it likes, and every later replay then matches it perfectly. The
check would authenticate a self-consistent story rather than a true one.

**Answer B — honest absence: report `None` and let the reader know a
walk was not observed.** The gain an adversary gets: it can make a walk
that never happened *disappear*, and a `None` is indistinguishable from a
genuine "we did not watch this one." So the exposure is real, and it is
bounded by something the trace is not allowed to be: the operation is
already durably settled and its `output` and `queries` still come back
verbatim. What the adversary cannot do is convert a `None` into a claim.
`control_distinctness.py:225` reads `_TRACE_KEYS` to compare walks
between arms, and the gate needs two *observed* walks to say anything; a
`None` on one side is a missing comparison, not a matching one. Under
Answer A the same comparison could be satisfied by two fabricated walks.

The difference is which failure the boundary is willing to accept. B
accepts "this run cannot see the walk" and refuses to guess. A accepts
"this run can prove the walk" and is wrong whenever the store cannot
supply it. For a security-adjacent boundary, a value that cannot be
verified from durable state must not be reported as verified, and `[]`
is the worst of the three: it is affirmative evidence of a walk that
did not happen, and it is the only one of the three that a comparison
gate can mistake for a match.

`f1d8ada` chose B and said why in its own message ("an empty list would
say the member ran and asked nothing, which is a different claim, and it
is the claim the gate must not mistake for a match"). That is the same
reasoning as the three-path rule in `control_arm_result.py:109`. The
tests were written in 2026-09 (`5af6384`, 2026-09-16) and assert
`replay == result` over the whole record, which was true when the trace
was absent from the record entirely and stopped being true when it
became a field that distinguishes. B is kept, and both sides are now
pinned: the first call's trace is non-empty, the replay's is `None`.

## 2. BDR-01: the two rows that were not the trace

`77001fc` (2026-09-26 01:13) deleted first-family-match selection from
`run_use`. The method identity must come from an admitted `use_method`
action, because `run_use` previously stamped the policy digest on the
record *afterwards*, and a digest written after execution is a label
rather than a governance record. With no policy, `_use_policy_action`
raises `_UsePolicyRefused` and the record is a refusal: `requested` is
the literal string `"refused"`, `operation_ids` is `[]`, `costs` is
`{"witness_queries": 0}`.

Two tests still called `run_use` with no policy, so they were asserting
on a refusal record and never reached the use accounting or the fallback
they are named for. `test_failed_member_falls_back_with_attribution`
asserted `record["requested"] == "bdr01-pollution-canary"` against the
string `"refused"`; `test_store_backed_use_attributes_sandbox_operations`
asserted one operation id against zero. Both now admit the canary
through a policy in the shape `policy_step.validate_action` accepts, so
the properties they protect are exercised again rather than deleted. This
is the same grant `a41d4b3` (2026-09-20) made to the other six suites
that needed it.

## 3. Gateway usage: `failure` is right and the test was stale

`59a10df` (2026-09-24 02:05:57) replaced the single error path in
`_model_error_receipt` with three classes: `pre-send-route-refusal` and
`observed-provider-failure` are decided `failure`s, `lost-response` is
`unknown`. A `GatewayError` carrying `response_received` is the second
class, so `outcome` is `failure` for both a malformed token count and a
noncanonical `charge_scale`.

The tests asserted `unknown`. The malformed one was written at `91e8f9d`
(2026-09-23 22:04), four hours before the change. The noncanonical one
was written at `48d0af6` (2026-09-24 00:55), 73 minutes before it.

`failure` is correct and the product is unchanged. The answer arrived,
so the send was not lost and the units were never unresolved. That is the
same reasoning `8943c08` (2026-09-28) gave when a decided `failure`
released 66,447 units that an `unknown` had held forever, and the same
one `_crash_after_reset` and the raising-gateway path still use for
`unknown`: a send that produced no response at all is genuinely
unresolved, and a send that produced a response is not.

The charge is held either way, which is the property these two rows are
really about. `store.receipt_actual_cost` returns `None` for a billed
usage missing a token count, and for any `charge_scale` that is not
`CANONICAL_CHARGE_SCALE` (1000) -- 7 provider-scale units are not 7
settlement units. Measured before the rewrite, both cases on both APIs:
`(consumed, reserved) == (0, 9)`, `actual_cost` unset, the full
exposure still reserved. The rewritten tests assert that ledger pair,
the partial evidence, and `response_class`, which is what makes the row
worth a reader: a reader can see the provider sent a bill in the wrong
denomination and that nobody guessed at it.

## 4. Broker prepare: retry scaling is dead code

`59a10df` also made `ensure_operation` refuse a non-zero `retries` with
"use distinct operation identities". `exposure_schedule` still
multiplied by `retries + 1` (`broker.py:151`, `:157`), and the two tests
asserted the multiplied number: `exposure == 51` for `retries=2`, and
`(8 + STOP_SETTLE_S + 1) * 2` for `retries=1`. Neither is reachable.

Established from the source, not by adjusting the number. Every live
caller already passes `RETRIES = 0`: `acquire/campaign.py:43`,
`team01/solver.py:45`, `team01/live.py:28`, `broker.py:1503`. The one
caller that means to retry, `e2_replication.RETRIES = 1`, retries with
*distinct operation identities* -- `operation_id_for(campaign_id,
task_id, arm, attempt)` -- not with the multiplier, and it never passes
`retries` to `ensure_operation` at all.
`tests/test_broker_route_recovery.py:513` already asserts the refusal.

So the tests were guarding a removed feature. The refusal is the correct
rule, and it is the safer one: one operation identity must mean one send,
because a retry under the same identity is exactly what makes "was this
charged twice" unanswerable afterwards. The multiplier is not deleted
here -- `exposure_schedule` is public and `authority.py:221` and
`loop.py:424` still call it with a `retries` argument -- but the broker
no longer admits a non-zero one, so the branches are unreachable from
`ensure_operation` and no test should assert them.

`REVIEW-03` R03-009 is the standing finding on the other half of this:
`wf_ensure_dispatch` exhausts retries only when the failure count exceeds
`retry_max`, so a positive budget never exhausts. That is the workflow
retry, a different parameter from the reservation multiplier, and it is
not repaired here.

## 5. EC02-AD01 verif: three causes in a five-row count

**Three rows were environmental.** `AD01_ROOT` and `VERIF_ROOT` both
pointed at `.worktrees/verif`, which does not exist: `.worktrees/` is
empty and `git worktree list` does not name it. The failures were
`FileNotFoundError` on a `cwd=`, `git clone` exiting 128, and a probe
file read from a directory that is not there.

The brief asked whether these tests still verify a real property. They
do, and each was checked before the path was touched: all twelve premise
paths are tracked, the scratch-path grep (`worktrees/verif`, `/tmp/ec02`)
returns nothing outside this file, `entry.admitted_child_factory` and
`entry.arm_child_factory` are both absent, `dispatch_admitted_child` and
`run_child_factory` are both callable, and
`reviews/probes/ec02_completion_review.py` exists. Both roots are now
derived from `__file__` rather than pinned, so the tests run from any
checkout. Measured: the three rows went from red in 1.87s (dead path, all
three failing before their own assertions) to 3 passed in 55.75s.

**One row could not fail.** `test_verif_fresh_checkout_...` ended with

```python
assert head.stdout.strip().startswith(VERIF_TIP) or True
```

`or True` *is* the assertion. `VERIF_TIP = "3d697b8"` is decoration on
the discarded left operand, and the row passed against a worktree that
did not exist. It is replaced with a resolution of the tip and a check
that it is a full 40-character commit id that `git cat-file` can reach,
which is the property the line was reaching for and which survives the
tip moving. Proven with a mutation: forcing `tip = "not-a-commit"` gives
`AssertionError: not a full commit id: 'not-a-commit'`.

**Two rows were a different cause entirely.** `test_verif_ad01_sigkill_...`
and `test_verif_ad01_resume_spend_equals_direct_run` were counted with
the path failure but were not caused by it, and only became visible once
the path resolved. The CLI refuses to seed a campaign with no agenda
authority -- `ad01-traj refused: campaign requires explicit caller agenda
authority: no authority for study 'ad01-w0-I-07' in this store` -- so
the run died before it could be killed and the row's own message read
"SIGKILL never landed mid-run". The CLI has carried
`--agenda-authorized` for exactly this grant since `a41d4b3`
(2026-09-20), which added it to six other suites and not this one. Both
calls now pass it.

That exposed a third thing in the same row. `_ad01_boundaries` filtered
settled boundaries on `content["claimed_ops"]`, a key that
`ff65b2a` (2026-09-16 23:35) deleted along with the `_claimed_ops`
helper that minted it. The removed values were
`op-<cid>-<seq>-diagnostic` and `op-<cid>-<seq>-episode`: strings composed
at write time and never matched against an operation row. So "no
duplicate or empty claimed operation identities after resume" was
asserting that arithmetic on a fabricated list had no duplicates. It is
replaced with the identities the store actually holds -- the boundary
`seq` and its `observation_id`, both read from the durable rows -- and
`ff65b2a`'s own replacement, `settled` on `kind == "boundary"` alone, is
what `_read_campaign` now uses.

Both new guards were proven to fail both ways: duplicating a boundary row
gives `resume settled the same boundary sequence twice: [0, 1, 0]`, and
blanking the observation id gives `duplicate or empty observation
identities after resume: [None, None]`.

File: 5 failed, 23 passed -> 28 passed.

## 6. Two assertions of mine that were wrong

Recorded because the method that caught them is the one that should have
been applied before writing the first line of the gateway rewrite.

- I asserted `receipt["actual_cost"] is None`. There is no
  `actual_cost` column on a receipt row; it is a `KeyError`. The ledger
  pair is the real statement, and reading the row is what showed that.
- I asserted `records[0]["status"] != "refused"`. Only a refusal record
  carries `status` (`_policy_refused_record`); a success record has no
  such key, and its absence is what says the use phase did not refuse.

Both were caught by running the store and reading what it wrote, not by
the green result. Neither made it into a commit.

## What is not claimed

- No product file was changed, so nothing here asserts a product defect is
  fixed. All four causes are test-side or environmental.
- `exposure_schedule`'s `retries` multiplier is still reachable from
  `authority.admit_study_call` and `loop.admit_effect`. Both are
  unreachable with a non-zero value from any live caller today, but the
  parameter is still public API and is not removed here.
- `REVIEW-03` R03-009, the workflow retry budget, is untouched.
- The ten `invr3` rows in §5 of the suite-after review share a cause with
  rows this lane did not own and are not addressed by any commit here.
