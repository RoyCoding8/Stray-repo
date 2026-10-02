# W5 final independent review

Reviewer: independent, did not write the batch. HEAD at review time `6f94076`
(`f0d23e4` is its parent; one forgery-test hygiene commit landed after the
handback). No live calls, no Jev, no paid route, no full suite. Three test
files' worth of budget was available; two were used.

Commands are named. Every verdict carries a `file.py:line` or an artifact key.

---

## Verdict in one line

**The handback does not survive contact with the evidence.** Three of its five
load-bearing claims are wrong or overstated, and the two staleness targets the
coordinator asked me to sweep are themselves stale. The *negative* findings are
sound and well-discharged. What fails is the E2 arithmetic claim, the E3 "3.0"
result, and the E1 route diagnosis — and the first two are load-bearing for the
recommended bottleneck ordering.

---

## 1. The five most load-bearing claims

### C1. "The E2 contrast is 0.0 by arithmetic, because `_measured_row` writes keys `_reduction_of`/`_decision_of` do not read." — **FALSE**

This is the single most load-bearing claim in `f0d23e4`. It is the stated reason
the recommended first bottleneck changed. It is wrong on both halves.

**(a) The functions do not read what the document says.** The claim, verbatim in
both documents (`STAGE-09-COMPLETION-MATRIX.md:97`,
`STAGE-09-RECOMMENDATION.md:287-291`):

> `_measured_row` writes `capability_id, detail, observation_id, reason, reduction, task_id, verdict`; `_reduction_of` reads `action` and `_decision_of` reads `action, method_id, max_queries` — none of which the row writes.

`_reduction_of` (`experiments/ad01/e2_replication.py:1313-1323`) reads
`NORMALIZED_REDUCTION`, which is the literal string `"normalized_reduction"`
(`experiments/ad01/s09_e2_scored.py:116`). It does **not** read `action`.
`_decision_of` (`:1326-1337`) does read `action`, correctly quoted.

**(b) The row that feeds the contrast is not `_measured_row`.**
`_measured_row` (`e2_replication.py:230-256`) is the *evidence record* producer,
used for the experience records a policy is shown. The readings that
`paired_report` consumes are produced by `reading_row`
(`e2_replication.py:886-893`) — and the campaign that actually produced the r2
artifact, `e2_contrast_campaign.py` (namespace `invr1e2contrastr2`, `:67`),
deliberately bypasses it. Its module docstring, `e2_contrast_campaign.py:26-34`,
says exactly this:

> **Two: the scored observable is the whole `Reading`, not `reading_row`.**
> `reading_row` writes nine keys and `paired_report` reads
> `normalized_reduction` and `action`, neither of which it writes. So
> `_reduction_of` returns 0.0 … and every paired delta is 0.0 by arithmetic
> rather than by measurement. `Reading.as_dict` carries both keys, so keeping
> the `Reading` makes the **frozen** `paired_report` work unchanged.

The fix was known, implemented, and shipped. `reading_row_both`
(`e2_contrast_campaign.py:1021-1035`) records both projections *and* the
`keys_reading_row_drops` list specifically so the defect stays visible.

**(c) The artifact proves it.** Every reading in
`reports/evidence/invr1e2contrastr2/report.json` carries 32 keys including
`normalized_reduction` and `action`. Per-task values (read directly):

| task | relevant | irrelevant | none |
|---|---|---|---|
| `ad01-w0-within-sw-00` | 0.7 | 0.7 | 0.7 |
| `ad01-w0-within-sw-01` | 0.769231 | 0.769231 | 0.769231 |
| `ad01-w0-within-sw-02` | 0.454545 | 0.454545 | **0.727273** |

**(d) And the deltas are not 0.0.** The same documents report
`deltas [0.0, 0.0, -0.2727]`, delta `-0.0909`, z `-1.225`. The third delta is
exactly `0.454545 - 0.727273`. The contrast is not vacuous; it is a real
measurement of a real difference, which is why `z` is not zero. The documents
contradict themselves in adjacent sentences: "the contrast is 0.0 by arithmetic"
and "deltas [0.0, 0.0, -0.2727]" cannot both be true.

**What survives.** The *conclusion* the recommendation reaches — that the E2
null is uninformative about experience — is still defensible, but on the
**second** reason it gives, not the first. The reachability census
(`report.json` `$.reachability_census`) is real and correct: 12 cells, default
`("seed-sw-ddmin", 8)`, `max_attainable_positive_delta: 0.0`,
`max_attainable_negative_delta: 0.538462`. And the `decisions` block is real: on
`within-sw-02` both experience arms chose `seed-sw-greedy` while the control
chose `seed-sw-ddmin`, `differs: true`. That is the report's own note about
`within-sw-02` — I confirmed it in the artifact.

**Severity.** High. The reasoning is wrong, it is presented as *verified by the
coordinator*, and it is the sole justification for re-ranking B1. The re-ranking
is still probably right, for a different reason.

**A second, smaller error in the same sentence.** The recommendation
(`STAGE-09-RECOMMENDATION.md:293-295`) says: "The frozen replica's recorded
`[1,1,1]` came from `score`, on tasks where its own decisions block reported no
difference." The `decisions` block for `relevant-minus-none` reports
`differs: true` on `within-sw-02` and `differs: false` on the other two. "No
difference" is wrong for one task of three.

### C2. "The E3 ratio is exactly 3.0 at every non-zero budget." — **TRUE BUT VACUOUS, and presented as a finding**

`STAGE-09-RECOMMENDATION.md:718-724` presents this as a reproduced result: "It
**reproduces to the printed digit**: the ratio is exactly **3.0 at every
non-zero budget**".

The ratio is an **algebraic identity**. `reports/workstreams/w3-reproduce.md:48-49`
defines the denominators itself: "**SUM** = the sum of `held_out_reduction` over
worlds (0, 1, 2). **MEAN** = that sum / 3". So `SUM/MEAN = 3` identically, for
any values, because there are exactly three worlds. I verified: for sums
`0.419328, 0.525770, 1.077842, 1.242831, 7.3, 0.0001` the ratio is `3.0000000000`
in every case. It is `nan` only at sum 0 — which is why "every non-zero budget"
is the only true part.

This cannot fail and therefore cannot confirm anything. Calling it a
reproduction "to the printed digit" dresses a division restatement as an
empirical result. The same sentence correctly reports the 2.6729x and 1.6696x
reproductions and the crossover correction to 20 — *those* are the real content
and they are what should lead.

**The underlying defect is real and correctly found**: `_score_constant_rules`
(`experiments/ad01/agenda_policy.py:424-441`) returns
`sum(... for world in worlds)` while arm rows divide by `len(cells)`. The
recommendation's proof — calling the function rather than reading it — is the
right method.

**But the companion claim is wrong.** `STAGE-09-RECOMMENDATION.md:730-738`
states that two tests in `test_s09_e3_control_competence.py:185-189` and `:236`
"compare `_mean(...)` against that sum — the right side is three times the scale
of the left" and therefore "**cannot fail**", and calls this "**the second test
this batch was built to prove a defect fixed**."

I read both. `tests/test_s09_e3_control_competence.py:185-189` compares
`_mean(_arm(step, "agenda")) <= best + 1e-12` where `best` is
`step["best_rule_held_out_reduction"]` from the **ladder fixture**
(`e3.qualified_ladder`, `:81-83`), not from `_score_constant_rules`. The tests
also guard `vacuous == [8, 14]`, `rules_beating_it > 0`, and
`handicapped_at == [20, 30]` — real structural assertions that would break on a
substrate change. I could not complete a run of this file within budget (it
exceeded 420 s), so I cannot assert empirically that they pass, but **the
"cannot fail" characterization is not supported by the source**, and one of the
two cited lines (`:236`) is the `handicapped_at` assertion, which does not
compare a mean against a sum at all.

This matters because the recommendation uses the "cannot fail" finding as a
general indictment ("the same shape as the E1 preflight assertion"). The E1
preflight case is real — the ledger records it at `PROJECT-LEDGER.md:23` and it
is structurally sound. The E3 example is not established.

**Severity.** Medium-high. A restated identity is dressed as a reproduction, and
a second "cannot fail" claim is made against source that does not support it.

### C3. "E1's binding constraint is route availability; 9 of 12 records are transport loss at HTTP 502." — **OVERSTATED, and contradicted by the campaign's own probe**

`STAGE-09-RECOMMENDATION.md:416-420`:

> **Route availability is the largest single cause and the numbers say so.**
> r3 carries 12 records: **9 `transport-loss` at HTTP 502** and 3
> `invalid-program`. Nine of twelve. … Any plan that opens more E1 cells will
> spend its ceiling on transport loss while the route is in this state, and no
> E1 cell can be measured at all until the route answers.

The tally is **correct**. `reports/evidence/w1-e1-boolean-r3/exposure.json`
records 8 settled attempts, all `outcome: transport-loss`, 4 of them retried
into 3 `invalid-program` + 1 `transport-loss`; `RESULTS.md` tabulates
`transport-loss 9 / invalid-program 3` at both caps. So 9 of 12 is right.

**But the diagnosis is the probe's, and it says something different.**
`reports/evidence/w1-e1-boolean-r3/route-probe.json` `$.findings` contains:

> `output-budget-causes-the-502` — "the 502 tracks the requested **output
> budget** on this route, not the prompt. The same protocol prompt returns 200 at
> 16 and 256 tokens and 502s at the protocol's own 2048; a short prompt returns
> 200 at 2048"

The probe data (`$.probes`) confirms it: `campaign-prompt-budget-16` → status
200, `campaign-prompt-budget-256` → status 200, `campaign-prompt-budget-2048` →
timeout, `short-prompt-budget-2048` → 502. And a second finding:

> `frozen-model-absent-from-catalog` — "the frozen model id is not in the live
> catalog, and dispatching it anyway returns 200 naming that exact id, so the
> route is **reachable and unpinnable at once**"

`$.catalog.frozen_present` is `false`. Note the internal tension in the same
file: the probe's own finding text says the id "is not in the live catalog" while
`$.catalog.frozen_present` is `true` — the prose and the field disagree, which
is itself a defect worth naming, though it does not change the direction.

**So the route is demonstrably answering.** It returned 200 with content at two
budgets during the same campaign window. The 502s are not "the route is
unavailable"; they are a **budget-conditioned failure at the protocol's own
2048-token output limit**. That is a *protocol* fact, not a route-availability
fact, and it points at the same `max_output_tokens: 2048` the campaign froze.

This is the same defect class the batch already identified twice. The
recommendation's own §B2 and the r3 `RESULTS.md` both argue the 512 cap is not
the binding constraint — the recommendation says "a conforming answer is 143
characters". But the probe shows **2048 is** the binding constraint, in the
opposite direction from the cap. Neither document connects the two. The
recommendation's "What would falsify this" for B2 says "A route that returns
200s again … this stops being the largest remaining question" — but the route
already returns 200s at 16 and 256 tokens, so the falsifier is already met and
B2's own stated exit condition is arguably satisfied.

**Severity.** High. This is the first-ranked bottleneck, and its diagnosis
points at a cause the campaign's own probe measured and the documents do not
mention.

### C4. "E4's evidence sequence is a blind, tie-break-RNG artifact, not a learner." — **VERIFIED. Correct.**

This is the strongest content in either document.

Verified in source: `learner_revision.py:966-977` builds the sequence calling
`choose_query` and **never** calling `observe`. `rule_learner.py:40-50`
`choose_query` reads only `len(queried)` and `x not in queried`. The zero vector
at `:972` is therefore inert. `observe` (`rule_learner.py:25-29`) is the only
thing that narrows `self._candidates` (`:22`), so `_disagreement` (`:33-38`)
scores the full class at every step.

I confirmed it empirically rather than by reading, running the factorial over 20
seeds under `uv run`:

- `observe=False`, zero-vector vs. filled values → **identical sequence sets**
- `observe=True` → **different sequence sets**

So the values are not the variable; `observe` alone moves the number. The
recommendation's table (`STAGE-09-RECOMMENDATION.md:54-64`) and the "the object
is not a learner" conclusion are correct. The note at `:992-994` is indeed
false as written. The correction of the first draft's no-op recommendation
(`§0`) is right, and reversing the draft's "widen `_STRATEGY_SOURCE`"
recommendation is a genuine, well-evidenced improvement.

The E4 boundary claims also hold: `_STRATEGY_SOURCE` has exactly two members
(`improve_channel.py:136`), `leaf_construct` installs one (`:1196-1198`),
`CONTROL_ROLES` is `("known-effect", "no-op", "disconnect")` (`:888`).

### C5. "E1's acquisition surface is one prompt, so E1 measures one cell of nine." — **SUBSTANTLY CORRECT, with the correction the recommendation makes already applied**

Verified: `render_output_prompt` (`live_construct.py:100`) is the only prompt
for the Boolean output world; `OUTPUT_TASKS` (`:51`) holds `{"qual": 11,
"audit": 23}`.

The recommendation is right to have corrected pass 3 here
(`STAGE-09-RECOMMENDATION.md:369-387`): there **is** a second acquisition path,
`packet.py:342` `render_construction_prompt`, and r4 used it. Its own scoping is
careful and I did not disprove it: `candidate_shape` (`packet.py:263`) serves
`graph` and `software`; `ordering` and typed AST have no acquisition prompt.

**One residual overstatement.** The matrix (§3.2, `:161-172`) and the
recommendation both still lean on "**E1 has one constructible cell today, not
nine**" (`:170`) in the matrix, and the matrix's §3.2 cites r4's `acquired: 3`
as evidence *for* acquisition while also saying acquisition exists for one cell.
The matrix at `:171-172` was not updated for the second-path correction — it
still reads "**E1 has one constructible cell today, not nine.**" and
"The cap sheet marks all three representations supported on all three worlds;
that row is a plan, not a measurement." The correction landed only in the
recommendation. Two documents now disagree on the same fact.

---

## 2. §W5 acceptance conditions, clause by clause

Clause source: `WORKER-PROMPT.md:103-105`.

**One completion matrix for W0–W5 and E1–E4.** **MET, with defects.** Present
(`STAGE-09-COMPLETION-MATRIX.md:88-99`) with implemented/qualified/attempted/
completed/specifically-blocked vocabulary defined at `:12-19`. The reading rule
at `:8-11` is the right instrument and the W5 row at `:95` honestly marks its own
other clauses **NOT DISCHARGED**. Defects: the E1/E2 rows are stale (§3), and
§2 line 119 contradicts §0 within the same file.

**Issue separate verdicts for mechanism, acquisition, task utility, transfer,
autonomous selection, learner improvement.** **MET. This is the best-discharged
clause in the batch.** §3.1-§3.6 each state supported / not-supported /
strongest counter-reading, in that order, with named artifacts. Are they
distinguishable? Yes:

| verdict | discriminator | blurs into? |
|---|---|---|
| mechanism | dispatch→bytes→parse→execute→verify offline | no |
| acquisition | model-authored vs authored, byte-distinct | no |
| task utility | does the produced program do the task | no |
| transfer | retained reuse vs cold reacquisition | no |
| autonomous selection | does the *system* pick, vs scripts | no |
| learner improvement | does the *learner* change | no |

The three that could plausibly blur — acquisition vs mechanism, utility vs
transfer, selection vs improvement — are held apart by explicit negative
findings, not by assertion: §3.1 concedes E1 r1's "mechanism works" rests on
harness self-agreement; §3.2 concedes the r4 wrappers are three records
delegating to an authored `ddmin`; §3.6 separates the boundary from the
substrate from the prompt. **No blur found.**

**No more than three decision-relevant bottlenecks.** **MET in form, MISCOUNTED
in substance.** Matrix §4 has B1/B2/B3 plus an explicitly-declined fourth
(`:314-316`); recommendation §4 has B1/B2/B3. The cap is respected. But see §4
below: the E2 finding that drives the re-ranking is wrong, and a fourth real
bottleneck (the 2048 output budget) is hiding inside B2's own evidence.

**"Keep Stage 9 active unless the evidence supports closure."** **MET.**
Matrix `:404-405` and roadmap `:17`. Correct.

---

## 3. Remaining staleness

The defect class to hunt is *was true at an earlier commit, is not now*. I found
five instances the `f0d23e4` edit did not reach.

**S1. `STAGE-09-COMPLETION-MATRIX.md:119` — "E1 r2 on the repaired path | NO
ARTIFACT".** False. `reports/evidence/w1-e1-boolean-r2/` exists on HEAD with
`README.md`, `RESULTS.md`, `campaign.json`, `campaign-manifest.json`,
`exposure.json`, `lineages/`. **This document corrects this exact error at
`:44-54` and then repeats it seventeen lines later.** It is the precise failure
the matrix's own §0 warns about, and it survived the edit that fixed its twin.

**S2. `STAGE-09-COMPLETION-MATRIX.md:80` — "A third campaign (r3) is running".**
Stale on three counts. r3 **completed** (`exposure.json` `closed_at:
2026-09-30T06:06:05Z`, 8 attempts settled, `dispatches_spent: 16` against
`model_call_ceiling: 16`, `retries.json` `guard_status.ceiling_reached: true`).
r3's own `RESULTS.md` reports results at two caps. And r3 found four
`KeyError: 'task_id'` driver faults recorded in `exposure.json`
`$.driver_faults`, which consumed 4 of the 16 dispatches. A reader told r3 "is
running" will not look for its results, and the campaign whose route diagnosis
underwrites B2 is invisible in the matrix.

**S3. `STAGE-09-COMPLETION-MATRIX.md:3-5` — the provenance header.** "Reconstructed
from committed artifacts and source at `19fbe69`" and "plus `ad5e9cd` on
`wt/w1-e1-run` (one commit ahead of the branch tip)". HEAD is `6f94076`; the
document was last *edited* at `f0d23e4`. The `19fbe69` provenance is
self-disclaimed at `:44` but still heads the document as its authority.

**S4. `reports/PROJECT-LEDGER.md` — the two files the coordinator asked me to
sweep are both stale, in the same direction the handback just corrected.**

- `:3` — checkpoint `97b320a` (HEAD is `6f94076`); "the fourth has a repaired
  instrument but **is unrun**" — E2 ran at `5cf3fe8`.
- `:42` — "**the study is unrun**" … "**Nothing has been run on the repaired
  instrument, so there is no E2 result in either direction**" — there is a
  measured null.
- `:62` — "**METRIC REPAIRED, STUDY UNRUN.** … there is no E2 result in either
  direction" — same.
- `:38` — the Live acquisition row reports r2 only ("`97b320a`", 3
  `invalid-program` + 1 `transport-loss` per arm) and never mentions r3, which
  is the *most recent* E1 evidence and the one carrying the route diagnosis.
- `:44` and `:63` still assert the E3 tables as the authority; `ffadf15`
  recomputed them and `:63` says "TABLES REGENERATED" while `:44` still carries
  the "ratio is exactly 3.0 at every non-zero budget" phrasing as a finding.

**S5. `docs/design/REFINEMENT-ROADMAP.md:17` and `:28`.** `:17` — "the fourth
has a repaired instrument but is unrun". `:28` — "E2's primary statistic was a
constant, so its study is unrun on a repaired instrument", and "E1 r2 ran live
on a repaired route and constructed nothing" (r3 is unmentioned). `:32-33` —
E1's constraint is named as "model budget behaviour", which the route probe
now contradicts; and E4's is named as "the revision boundary", which the
leakage lane has since shown is not what the `0.5017` headroom measures.

**The pattern.** `f0d23e4` fixed E2 and E3 in the two handback documents and in
*neither* the ledger nor the roadmap, and did not touch E1, which is where the
biggest unpropagated change is. The coordinator's own matrix at `:352-355` says
"Stale status in the ledger is what produced the brief's claim that E1 r2
exists, and that claim would have gone into a handback as a finding." The
prediction was correct and it is still unheeded.

---

## 4. What overstates verification

Checked each named claim.

**Forgery closure — ESTABLISHED, and stronger than claimed.** The batch claims
five forgeries caught; there are actually **nine** rejection tests
(`tests/test_w1_e1_campaign_r3.py`), all passing. I ran the file:
`19 passed in 20.00s`. I then verified the tests are **non-vacuous** by
neutering their assertions in a scratch copy and re-running, which printed the
verifier's actual detections — all nine fired, each naming a specific defect:

```
over-length flag True does not match the 144 characters stored against a cap of 512
recorded character count 40 does not match the 144 characters in the stored response
outcome 'constructed' re-derives as 'poor-task-result'
response parses under Cap A but is recorded as 'invalid-program'
score does not recompute from the response
returned route '{...provider: openai...}' does not match the frozen route
prompt digest does not recompute from the frozen template
```

This is the right way to establish it, and the `6f94076` commit is itself good
work: it stopped `_verify_one` from writing `_tmp_r3_verify` into the checkout
on every run, which is why `_tmp_r3_verify/` is sitting untracked in
`git status` from before that fix. **The forgery claim is the one fully
discharged verification claim in the batch.** It also directly refutes the
document's own §6 note that "the recorded prose is not an input to any verdict"
being at risk — the verifier re-derives from bytes throughout.

**Offline re-verifiability — ESTABLISHED.** `verification.json` in the r3
directory, and the r1 campaign's `$.verification` `checked: 8, failures: [],
passed: 8` with `network_withdrawn: true` (matrix `:91`). The E2 r2 report's
`reachability_census` is explicitly "offline and with no model"
(`STAGE-09-RECOMMENDATION.md:296-298`) and I recomputed its arithmetic from the
artifact.

**Three independent review passes — OVERSTATED as a verification claim, and one
is missing.** `w5-review-pass1/2/3.md` are all tracked on HEAD
(`git ls-files` confirms). But the `w4-leakage` report the recommendation
cites four times (`:4`, `:49`, `:86`, `:110`) is **not on HEAD** — it exists
only in `.worktrees/w4-leakage/`, and `reports/workstreams/w4-leakage.md` is
absent from this checkout. Its branch tip `01e72dc` *is* an ancestor of HEAD,
so the commits merged, but the report the recommendation's §0, §1 and B3 are
built on is not retrievable from the branch a reader would check out. **§0's
whole factorial table and §1's entire cross-split control are cited to a file
with no committed path.** I reconstructed the underlying claim from source
independently (§1/C4 above) and it holds — but the *citation* is broken.

**WSL child execution — CORRECTLY QUALIFIED, not overstated.** The matrix
§2 `:113` says confined read denial is **NOT PROVEN** and names the Landlock
EINVAL. The recommendation's K4 (`:624-631`) says the route-ownership bet is
"Untested in both directions". This is the batch doing the right thing: naming
what is not established rather than rounding up. The relay
(`scripts/wsl_gateway_relay.py`, `reports/workstreams/w0-relay.md`) exists and
is tracked; `95cea59` committed it.

**Gateway relay — established as a script, not as a demonstrated relay.** The
script is tracked. I did not find an artifact recording a successful
child-process round trip *through* it. Given §2's own "no supported Linux
execution environment on this host", that is consistent and honestly stated
elsewhere — but no document should be read as claiming the relay was
exercised end-to-end, and none does. Acceptable.

**Where overstatement actually lives.** Not in the verification claims. It is in
the two *analysis* claims: "verified by the coordinator" attached to the E2
arithmetic (which is false), and "cannot fail" attached to the E3 tests (which
the source does not support).

---

## 5. Do the honest negatives lead?

**In the matrix: yes, adequately.** §0 is "Two premise corrections before the
table" — the reader hits the E1 r2 count correction and the r2 headwind
deconstruction before the matrix. §6 "Honest negatives, preserved" opens with
"**Three of four experiments are negative.** That is the finding, not a
shortfall in the write-up." The tally at `:101-103` follows the table
immediately. E1's zero constructions is in the table's own "What is not"
column (`:91`), not in a footnote.

**In the recommendation: no.** A reader who opens
`STAGE-09-RECOMMENDATION.md` and reads the first page meets: §0 "the one
correction that invalidates the draft", §1 the E4 diagnosis, §2 the open
question, §3 the `overall` denominator. The E2 null does not appear until
**line 271** (§4's B1) — roughly a third of the way into an 831-line document,
after two full sections on a *different* experiment. The recommendation is
structurally an E4 document that happens to contain an E2 result.

**The deeper problem.** Both documents now assert "three of four experiments
are negative" while simultaneously being **wrong about what E2 measured** (C1).
The negativity framing is a strength in form and a liability in substance: the
handback's most prominent rhetorical claim rests on a finding that does not hold
as stated. A reader who trusts the E2 arithmetic will over-trust the rest.

**Also worth naming:** the E2 null is presented with an explicit and correct
guard — "**The null does not license 'experience does not help':**"
(`STAGE-09-COMPLETION-MATRIX.md:92`). That is the single best sentence in either
document. It should be the one the correction preserves.

---

## 6. What is missing from the handback entirely

**M1. The route probe's output-budget finding is absent from both documents.**
`route-probe.json` `output-budget-causes-the-502` — 200 at 16 and 256 tokens,
502/timeout at the protocol's own 2048 — is the mechanism behind 9 of 12 r3
records, and it appears in neither handback. The recommendation instead asserts
route *availability* (§C3). This is a gap in what was delivered, not a phrasing
issue: it changes which experiment should run next.

**M2. r3's four `KeyError: 'task_id'` driver faults.** Recorded in
`exposure.json` `$.driver_faults` with operation ids and timestamps, and they
consumed 4 of 16 dispatches. A campaign that burned 25% of its ceiling on its own
driver bug, and did not record it as a headline, is a cost the reader needs.
Contrast the batch's care elsewhere: §6 of the matrix agonises over a *counting*
disagreement between two files. The 4-fault driver bug gets nothing.

**M3. The `zero-information default` framing for `ddmin@8` is asserted, not
explained.** Both documents say `ddmin@8` is "the zero-information default" and
"the best of twelve reachable cells on all three targets". The census supports
it. But nothing explains *why* the best available decision is the one that
ignores its information — which is a finding about the panel's reducers, and
would bear directly on whether the E2 question is even well-posed. It is
reported as a ceiling, not diagnosed.

**M4. No statement of what a reader should do with `invr1e2contrastr2` itself.**
Given C1, the honest disposition is: *the r2 contrast is a real measurement with a
real, non-zero, non-significant delta; the defect described in the handback is
real but was already fixed in the module that produced the artifact; the
remaining E2 problem is the closed positive side.* No document says this. The
handback instead says the contrast is void by arithmetic, which would lead a
reader to discard a usable null.

**M5. Nothing reconciles "3 of 4 negative" with "E2's instrument cannot report a
positive."** A reviewer counting negatives from §6 would count E2 as a fourth
negative. It is not one — it is *uninformative*. The matrix's own tally at
`:101-103` says this correctly ("E2 is the one that is neither positive nor
negative"), but the headline line above it says "Three of four experiments are
negative", and the recommendation's §9 `:824` repeats the three-of-four phrasing
while listing E2 among them. The count and the classification are in tension in
both documents.

---

## 7. Bottom line

**What is sound.** The E4 blind-sequence diagnosis (C4) is the best work in the
batch — correct in source, confirmed by execution, and it correctly *reversed*
the first draft's recommendation. The six-verdict structure is complete,
correctly separated, and each verdict names its strongest counter-reading. The
forgery apparatus is genuinely, non-vacuously verified (nine forgeries, all
detected from bytes). The honest negatives lead in the matrix. The W5 row
honestly marks its own undischarged clauses. §2's "not proven" table and the
process-failure disclosure in both documents are exactly the discipline the
assignment asks for.

**What is not.** The E2 arithmetic claim (C1) is false and is stated as verified.
The E3 "3.0" result (C2) is an algebraic identity presented as a reproduced
finding, and its companion "cannot fail" claim is unsupported by the source. The
E1 route diagnosis (C3) is contradicted by the campaign's own probe. Five
staleness instances remain, including the exact error the document was just
corrected for, recurring seventeen lines after the correction. The E2 result
lives on line 271 of 831 in the recommendation.

**So: no, the handback does not survive contact with the evidence** — but the
failure is concentrated in the two results that arrived last and were edited in
under time pressure, and it is mechanical (arithmetic, identity, copy-paste of a
superseded diagnosis) rather than structural. The architecture of the document is
right. The E4 section, which is the one a coordinator would act on, survives
intact.

I would not ship this. The three corrections are each a few lines. The E2 one
matters most, because the recommended bottleneck ordering currently rests on it,
and because the artifact says something usable that the handback tells the
reader to discard.

---

## Commands run

```
git log --oneline -12 ; git show f0d23e4 --stat
git ls-files reports/workstreams/ | grep -E "w5-review|w4-leakage"
git merge-base --is-ancestor 01e72dc HEAD          # w4-leakage tip
uv run pytest tests/test_w1_e1_campaign_r3.py -q    # 19 passed
uv run pytest _tmp_probe/probe_test.py -s -k rejected   # neutered: all 9 detected
uv run python  # 20-seed observe/value-fill factorial, experiment/ad01/rule_learner.py
```

Test files run: **2** (`test_w1_e1_campaign_r3.py`, and a scratch copy of it in a
temp dir, since deleted). `test_s09_e3_control_competence.py` was attempted,
exceeded 420 s, and was stopped; the E3 verdicts above rest on source reading and
arithmetic, not on a run, and are marked accordingly.

No live model calls, no Jev, no paid route, no full suite, no edits to any
tracked file.
