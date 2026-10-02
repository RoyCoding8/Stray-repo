# W5 review pass 2 — experimental validity

Reviewer lane. I wrote none of the code under review. Read-only on the main checkout;
this file is my only write. No commit. No live model call, no Jev, no paid route.
No test file was run: every claim below is a `file.py:line` citation, an artifact field,
or one of four `uv run python -c` probes whose output is quoted inline. That is inside
the three-file budget with the budget unspent.

Pass 1 is at `reports/workstreams/w5-review-pass1.md` and I read it in full. Where I
agree with it I say so in one line and move on. My question is different: **would a
hostile, well-informed reviewer accept these as experiments?** Pass 1 asked whether the
code is right and whether the handback overstates. I asked whether a *result* is
interpretable regardless of its sign.

**Headline.** Three of the four live findings are valid and I can show why. E1 r2 is
not. Its `n=4` is illusory, the arm comparison is uninterpretable, and the record's own
stated justification for not spending the repair allowance is **false** — I checked it
by running the shipped functions. That is a validity failure, not a presentation
failure, and it is fixable in about ten lines.

---

## 1. The seven questions

### Q1. Is E1 r2's arm comparison confounded? — **INVALID**

Both arms are the same model, the same route, the same task, the same seed, the same
frozen budget and the same instruction. They differ only in whether a two-element
digest summary is prepended (`P1` `history: []`, `P2` `history: [{...}, {...}]`).
`RESULTS.md:25` calls the cell-for-cell identity "a real result about this pair, and it
is a negative one."

It is not a result about the pair. It is an **equivalence of a ceiling**. Six dispatches
across both arms returned content the shipped parser rejects — I ran
`extract_and_validate_boolean` over all six saved responses:

```
L01-P1 -> would-not-parse: boolean payload is not JSON: Expecting value: line 1 column 1 (char 0)
L01-P2 -> would-not-parse: ... (same, all six)
```

Not one response contains a candidate object; every `{` in every reply is the model
echoing the schema back out of the prompt. So `P1` and `P2` never reached the state
where prior-task information could change the answer. They both failed *upstream of the
contrast*. A tie between two arms that never reached the variable is a tie about the
ceiling, not about experience-conditioning, and the assignment's §W2 asks precisely
whether experience matters.

**The cell should not be reported as a comparison at all.** The honest statement is
one number, not two: "6 answered dispatches, 0 parseable candidates, ceiling not
reached." The two-arm table invites a reader to compute a difference, and the correct
difference is undefined.

Note this is not pass 1's overstatement finding. Pass 1 said "the zero is about the
model" carries more weight than the evidence supports. I agree with that one line. This
is a different claim: the *arm contrast* has no estimand, independent of how the zero is
attributed.

### Q2. Are the 4 lineages per arm independent? — **INVALID, and this is the n=4 problem**

This is the most serious finding in my pass, and the answer is clean.

`WORKER-PROMPT.md:55` requires "at least four independent construction opportunities"
per cell, and `reports/cap-sheets/w1-e1-cap.md` §Replication definition defines
independence as **disjoint ancestor chains, never digest difference**, and explicitly
concedes that "two independent model calls that converge on identical programs are
independent lineages."

The concession is about *outputs*. It is the wrong axis. These lineages are not
independent in their **inputs**. I hashed `raw_prompt` across all eight records:

```
L01-P1  prompt_sha defd000933b84e00  len 982
L02-P1  prompt_sha defd000933b84e00  len 982
L03-P1  prompt_sha defd000933b84e00  len 982
L04-P1  prompt_sha defd000933b84e00  len 982
DISTINCT prompt_sha within P1: 1

L01-P2  prompt_sha 43d4d38883b6377e8d88  len 1336
L02-P2  prompt_sha 43d4d38883b6377e8d88  len 1336
L03-P2  prompt_sha 43d4d38883b6377e8d88  len 1336
L04-P2  prompt_sha 43d4d38883b6377e8d88  len 1336
DISTINCT prompt_sha within P2: 1
DISTINCT prompt_sha overall: 2
```

**Within each arm there is exactly one distinct input, sent four times.** All eight
records also carry `seed: 11` and `task_id: "rule-qual-194dba80c87f"`. The prompt is a
pure function of `(arm, split, seed, attempt)` — `render_output_prompt`
(`live_construct.py:100-110`) takes no sampling parameter and `output_permitted_history()`
(`:125-149`) is deterministic over the fixed dev seeds `(3, 7)`. The four lineages differ
only in `round_run_id`, which appears in the *operation id* and nowhere in the prompt.

The frozen seed does not mean "every lineage replays the same program." It means
**every lineage replays the same experiment.** What the eight dispatches measure is one
prompt answered eight times by a stochastic model. That is a legitimate and useful
measurement — it is what the "6 of 6 behaved identically" claim actually rests on — but
it is **not** four construction opportunities per arm, and the effective n for any
per-cell statistic is 1 input × k draws, not 4.

The cap sheet's independence test is a *digest* test, and it was applied where a
*lineage* test belonged. The operational question "did this lineage have its own ancestor
chain" is answerable from the record and was not asked: `distinct prompt_sha` is 1 per
arm. `distinct_behaviours: 0` is reported, and the cap sheet says behavioural
duplication "is never enforced" — correct as a rule about *outputs*, and beside the
point here, because the duplication is in the *inputs*.

This is a validity failure, exactly as the brief anticipated. It is also the cheapest
thing in the batch to fix (below).

### Q3. Were sampling and selection rules fixed before outcomes were seen? — **QUESTIONABLE, and the record's own justification is false**

The cap sheet's §Stopping rule says "Sampling and selection rules are fixed here,
before assessment," and `OUTPUT_LIMITS` at `live_construct.py:43-50` carries
`repairs_per_task: 1` and `automatic_retries: 0` as pre-declared constants. So the
*rule* was predeclared. What was not fixed in advance is whether the rule would be
applied.

`campaign.json $.planned` records `repairs_planned: 0` with this justification:

> "unspent, and not spendable here: `render_output_prompt` refuses an attempt outside
> (1, 2) and `output_operation_id` refuses any seed outside the frozen pair, so a
> repair would have to reuse the same task and the same identity"

I ran both shipped functions. **The stated reason does not hold.**

```
OUTPUT_TASKS = {'qual': 11, 'audit': 23}
P1 qual seed=11 attempt=1 -> invl02-output-ab98249ed8c5-P1-qual-0011-a1
P1 qual seed=11 attempt=2 -> invl02-output-ab98249ed8c5-P1-qual-0012-a2   <- exists
P1 audit seed=23 attempt=1 -> invl02-output-ab98249ed8c5-P1-audit-0023-a1
attempt1 len 353  attempt2 len 353  differ: True
```

`render_output_prompt` **accepts `attempt=2`** and produces a *different* prompt (the
template at `:56` embeds `"Attempt {attempt} of 2."`, so the byte strings differ). The
guard at `:101-102` rejects only attempts outside `(1, 2)` — it *invites* a second
attempt. And `OUTPUT_TASKS` has two entries, so the "frozen pair" is not one task: the
`audit` seed 23 is equally frozen and was never used.

So the allowance was spendable three ways — attempt 2 on the same task, or the frozen
audit task — and the recorded reason for not spending it is factually wrong. The
`README.md:159-162` and `RESULTS.md:119-123` repeat the same false claim.

What actually happened is simpler and is stated nowhere: `w1_e1_campaign_r2.py:483-486`
hardcodes `attempt: 1` in the prompt render, the operation id, the evidence dict and
`_entry()`. The driver has no second-attempt branch. The allowance was left unspent
because the driver has no code path that spends it, and the record attributes that to a
constraint in the frozen protocol that does not exist.

**Why this is a validity finding and not a bookkeeping one.** The predeclared rule
("1 repair per opportunity") and the executed rule ("0 repairs") differ. Under
`WORKER-PROMPT.md:109` ("Predetermine sampling and selection rules") and the cap sheet's
own §Stopping rule, a reader is entitled to know whether the stopping decision preceded
the outcomes. On this evidence it did not: the *rule* was written after r1's failure
(commit `c8bbc0f` "Freeze the W1/E1 cap sheet before any dispatch" is 13 commits before
r2's `97b320a`), the *executor* has one branch, and the post-hoc explanation for not
using the second branch is wrong. I cannot prove the order of the authorial decision
from the artifacts — that is undetermined — but the justification on record is false, and
that alone is enough to stop a reviewer trusting the stopping rule.

### Q4. Do the three counts support "0 acquisitions"? — **VALID**

The counts are construction events 0, unique source programs 0, retained records 8, and
they do support 0 acquisitions. Three independent reasons:

1. **No bytes.** `candidate_digest: null` on all eight, `candidate_digests: []` in both
   cells, `score_distribution.n: 0` with `min`/`median`/`max` all `null`. Nothing was
   parsed, so nothing could be scored, so nothing could be acquired. A reading in which
   any of the 8 are acquisitions requires one of them to contain a program, and I ran
   the shipped parser on all six saved responses: none parses.
2. **The sub-classification is real, not prose.** `invalid-program` carries
   `invalid_program_defect` of `over-length` or `would-not-parse`
   (`README.md:132-134`), and the field is populated: `over-length`, `response_characters: 5211`.
   This is the one place where the taxonomy earns its keep on E1, and I confirmed the
   split is *caused* by the cap and not merely asserted: with the length check in place
   the response is never offered to the parser, and the parser rejects the same bytes
   anyway when I bypass the cap. So `over-length` and `would-not-parse` coincide here,
   which is a fact about this model's behaviour, not a masking artefact.
3. **The floor is separate and not the reason.** `PREFLIGHT_SCORE_FLOOR = 1.0`
   (`live_construct.py:1446`) and `reference_scores.oracle_overall: 1` mean the bar *is*
   the oracle. `RESULTS.md:88-91` says so plainly. This does not affect the acquisition
   count (nothing was scored), but it does mean that had anything parsed, a
   `poor-task-result` would have been indistinguishable from near-miss competence. Worth
   knowing before the next run; not a defect in this one.

**What would have to be in the record to tell acquisitions apart from non-acquisitions,
and whether it is:** the record would need either a parseable candidate or a per-record
statement that the parser was reached and refused. The second exists only indirectly
(`invalid_program_defect: over-length` is inferred from length, not from a parse
attempt). Given that I independently reproduced the parse failure, the conclusion holds.
Pass 1's §2.2 finding — that `verify()` never recomputes `reason` or the defect
classification — is the same gap seen from the other side, and I agree with it; it means
the *reason* is unverifiable offline even though the *count* is right.

### Q5. Does the five-way taxonomy partition what happened, and does it preserve "a failed preflight is never model inability"? — **VALID, with one honest caveat**

`PREFLIGHT_OUTCOMES` (`live_construct.py:1432-1440`) is seven tuples, and the
`WORKER-PROMPT.md:48` five are a strict subset: `route-refusal`, `transport-loss`,
`empty-content`, `invalid-program`, `poor-task-result`. The two additions
(`constructed`, `pre-dispatch-refusal`) are both *terminal-positive* or
*nothing-was-sent*, so neither can launder a harness fact into a model fact. The
assignment's requirement is met structurally, not by convention.

The key ordering decision is right. In `w1_e1_campaign_r2.py:549-556` the length check
runs **before** `extract_and_validate_boolean`, and it fires `finalize_evidence(...,
parse_outcome="too-long")` — a distinct value from `"parse-failed"`. So a reply that
never stopped talking and a reply that stopped and was still not a program are
separately recorded, which is what the assignment asks for at `:48`. The six
`invalid-program` records all carry `parse_outcome: "pending"` in the dispatch block but
`invalid_program_defect: "over-length"` in the verdict, and both agree.

**Does `invalid-program` absorb distinctions the assignment needs?** It absorbs exactly
one, and it is the right one to absorb: over-length vs would-not-parse is a
*cause* distinction, carried in a sub-field, not lost. I verified it is not masking
anything by running the parser on the raw bytes and getting `would-not-parse` for all
six. On this evidence the five-way split is a genuine partition of what happened, and
`route-refusal` correctly vanished from r2 — the two 502s are `transport-loss`, and the
six answered dispatches carry `route_error: None` against frozen `provider: "nvidia"`,
which is the direct evidence that the r1 route defect did not recur.

**Caveat, and it is a real one.** `transport-loss` and `invalid-program` are not
symmetric. A 502 is *known* to be apparatus. A `stop_reason: length` is a joint
product of the model's behaviour and a **frozen protocol choice** (512 characters
against 2048 output tokens, `live_construct.py:44-45`) that the assignment never
mandated. Labelling it `invalid-program` — a term that reads as "the program was
invalid" — invites exactly the misreading `WORKER-PROMPT.md:48` warns against, and
`RESULTS.md:9` fell into it ("this time the zero is about the model"). The taxonomy is
correct; the *narrative gloss* on it was not. `over-length` as a sixth top-level outcome,
or `protocol-nonconformance`, would have preserved the partition and removed the
invitation.

### Q6. Are E2's and E4's "completed" states honest categories? — **QUESTIONABLE for E2, VALID for E4**

**E2 is a category error, and the matrix contradicts itself about it.** The
`STAGE-09-COMPLETION-MATRIX.md:8-10` reading rule says:

> "A row is `completed` only where a named artifact carries the claim... **A negative
> valid study completes its question. An unrun study does not.**"

Then `:59` marks W2/E2 **"completed" (the metric is fixed; the question is unrun)**, and
`:64` marks E2 **"metric repaired, study unrun"** with the honest note "A repaired
instrument is not a result." The document applies its own rule against itself in two
adjacent rows.

I established the chronology from git rather than prose. Every E2 run predates the
repair:

```
d42049c  2026-09-29 21:31:41 -0400  Measure the E2 benefit leg instead of reading a constant off a verdict
ca21253  2026-09-29 06:44:53 +0000  The echoer no longer outscores the reader...   <- newest E2 evidence
git merge-base --is-ancestor d42049c ca21253  ->  NOT ancestor
```

So `d42049c` cannot have influenced any E2 artifact on disk. There is no E2 result in
either direction. `completed` is the wrong word for a milestone whose only deliverable
is a repaired instrument. **This is not the matrix papering over it** — §3.4 and the
`§4 B1` bottleneck both say E2 is unrun, and the ledger's outstanding-work checkbox is
unticked. The prose is honest. The *state label* is what is wrong, and the state label
is the thing a program manager reads. It should read `implemented` or `qualified`, and
the matrix's own vocabulary at `:13-14` already has both.

**E4's "completed, negative" is honest.** This is the strongest single piece of
experimental work in the batch, and I want to be explicit that I checked it adversarially
and it held. Six dispatches, six `model-acquired`, zero admitted, six identical
refusal reasons, and — the part that matters — the refusal is *correct*:
`reducer_own_choice: 0`, `selected_at_first_step: 0`, and each reply computes
`x = len(view.get("experience", []))`, which is 0 on the step that spends the probe.
The instrument refused a revision that would have changed nothing, and it says why.

E4 also passes the independence test E1 fails, and passes it for the right reason: the
six dispatches carry **one** prompt digest but six **syntactically distinct**
executables, and the outcome is a *property of the interface* (a selector over a
2-element menu) rather than a property of one task. That is why a single frozen prompt
is defensible there and not in E1: E4 measures what the *boundary can express*, and
re-asking the same boundary question with the same model adds nothing. E1 measures what
the *model constructs on a task*, where the task is the variable.

One E4 caveat, which is pass 1 territory and I agree with it in one line: the
`0.00622` figure is a selected upper bound and the 70x ratio built on it is soft. Not
repeating it.

Two E4 records I checked and found internally inconsistent, worth flagging because a
hostile reviewer will find them:

- `campaign.json $.acquisition` reads `{"acquisition": "no-reply", "detail": "no
  dispatch was attempted"}` while `$.acquisition_summary.acquired` reads `6` and
  `$.outcome.blockers` lists "no live-acquired attributable model bytes". The top-level
  `acquisition` block contradicts the summary in the same file. One of the two is stale.
- The ledger at `:51` says the disconnect control is "**missing from**
  `improve_channel.CONTROL_ROLES`, so the campaign that ran did not use it." The code
  disagrees: `improve_channel.py:888` is
  `CONTROL_ROLES = ("known-effect", "no-op", "disconnect")`, and
  `fcf26da` (2026-09-26) is what put it there — three days *before* the E4 campaign ran.
  The disconnect arm is present in the artifact and reports
  `changed_decision: true, reached_boundary: false`. **The ledger's own load-bearing
  qualification claim is wrong**, and it is wrong in the direction that makes E4 look
  *less* qualified than it is. Pass 1 did not flag either.

### Q7. What is the cheapest untried experiment, and was its absence principled? — **An oversight. A finding.**

**The experiment:** spend the already-frozen, already-authorized, already-ceilinged
repair allowance. The cap sheet set `N x 2 = 16` model calls; the run spent 8. The
second 8 were pre-authorized, pre-ceilinged, and — as I showed in Q3 — mechanically
available. `w1_e1_campaign_r2.py:483-486` hardcodes `attempt: 1`, so this is a
ten-line change to the driver: take the attempt from the lineage loop, render attempt 2,
let the second dispatch run, keep the first as a recorded failure.

Cost: **8 model calls against an existing ceiling, 0 new cap sheet, 0 new authorization,
0 new freeze.** It is the cheapest thing available anywhere in this batch, and
`STAGE-09-COMPLETION-MATRIX.md:251-264` already identified a campaign at this exact
ceiling as "Cheapest item in this document" before r2 spent half of it.

**Was the absence principled? No.** Three tests:

1. *Was it foreclosed before outcomes?* The cap sheet froze a repair allowance. The
   preflight prompt the model actually received says **"Attempt 1 of 2"** — the protocol
   told the model a second attempt existed, and the harness never made one. That is not
   a designed constraint; it is an unbuilt branch.
2. *Was the exclusion justified?* The recorded justification is **false**, verified in
   Q3 by running the two functions it cites.
3. *Would it plausibly have produced a positive result?* **Unknown, and I decline to
   guess.** But the asymmetry is decisive: pass 1 noted the cost of not running it is
   that "a negative with an untried in-protocol second attempt is not the model's
   verdict, it is the protocol's." I sharpen that. A cell where **6 of 6** dispatches
   spent the entire budget reasoning in prose, and the protocol's own declared second
   attempt went unused, cannot support a claim about the model's construction ability
   *or* its construction inability. It supports a claim about one prompt and one budget.
   `RESULTS.md:9` ("this time the zero is about the model") is the sentence that the
   unspent allowance makes false, and the ledger propagated it at `:38`.

**The second-cheapest untried experiment**, for the record, because it addresses Q2 and
Q1 together: run the four lineages on **four distinct tasks** rather than four repeats
of one. `OUTPUT_TASKS` already holds two frozen seeds (`qual: 11`, `audit: 23`) and
`rules.make_task` will build more. Without distinct tasks, E1 cannot produce a
per-cell n=4 at all, and the §W1 "four independent construction opportunities" line
stays unsatisfiable no matter how many dispatches are spent.

---

## 2. The single most serious validity problem

**E1 r2 has one distinct experimental input per arm, replicated four times, and is
reported as a four-lineage two-arm comparison.**

Everything else in my pass is a smaller version of this or a presentation issue. The
arm contrast has no estimand (Q1) *because* the four lineages are the same experiment
(Q2). The unspent repair that would have varied the one input that matters was skipped on
a false justification (Q3). And the `n=4` that the cap sheet's independence rule was
written to guarantee does not exist.

The batch's *count* is right. Zero constructions is zero constructions, the three counts
are three numbers, and the taxonomy partition is sound (Q4, Q5). What does not survive
is the *cell as an experiment*: a reader who takes `4 lineages per arm, identical
outcomes` at face value will conclude that prior-task information does not change
construction outcomes. Nothing in this campaign can support that, and the report invites
it.

**One-sentence fix:** either spend the repair allowance across four distinct tasks
(10 lines in `w1_e1_campaign_r2.py`, against an existing ceiling), or relabel the E1 r2
row from a two-arm comparison to a single-input replication and drop the arm table.
The first is better and costs nothing that is not already authorized.

---

## 3. Are the E1 / E2 / E4 "completed" states honest categories?

| | Matrix label | Honest? |
|---|---|---|
| **E1** | `attempted, then specifically blocked` / `attempted, 0 constructions` | **No, and stale.** Pass 1 §2.1 established the matrix asserts r2 does not exist at the commit that created it. I re-confirm against `97b320a` and add the validity layer: the state is not merely mislabelled, it is mislabelled *about an experiment that was not run four times*. `attempted` is the right word; the count of opportunities behind it is not. |
| **E2** | `completed` (metric fixed, question unrun) | **No. Category error.** The matrix's own rule at `:10` says an unrun study does not complete. The prose says so too (`:59`, `:64`, `§3.4`). Only the state label is wrong, and it is the label a manager reads. Should read `implemented` or `qualified`. |
| **E4** | `completed, negative` | **Yes.** A study ran, produced a recorded result, and the negative is bounded and correctly attributed to the boundary rather than the model. This is what `completed` is for. |

The E2 label is the only one that misrepresents a *state*. The E1 label is stale
(pass 1's finding, which I confirm) and additionally understates a validity problem
(pass 2's). Neither is a reason to distrust the underlying records, which are
self-consistent and offline-verifiable.

---

## 4. Cheapest untried experiment, and whether its absence was principled

**Spend the frozen repair allowance: 8 additional dispatches at `attempt: 2`, against
the existing `N x 2 = 16` ceiling, with 4 distinct tasks per arm instead of 4 repeats
of one.** No new cap sheet, no new authorization, no new freeze, no paid route, no Jev.
It requires changing `attempt: 1` at `w1_e1_campaign_r2.py:483,484,486,496` to a loop
variable and varying `seed` across the four lineages.

**Its absence was an oversight, not a principle.** The supporting evidence is that the
justification offered for it is demonstrably false (Q3), that the prompt sent to the
model advertised an attempt 2 that never existed, and that the cap sheet had already
budgeted for it. An oversight is a finding, and this is one.

I want to be careful about what it would have bought. It is **not** a claim that the
result would have been positive. It might well have been the same six over-length
replies, and the finding "this model reasons before it answers, and telling it to answer
second does not help" is a real and useful finding. What the unspent allowance costs is
the *ability to say that*. The current record supports only "this model, this prompt,
this budget, first try."

---

## 5. Undetermined

Stated as such. I did not guess at any of these.

1. **Whether the authorial decision to skip the repair preceded or followed the r2
   outcomes.** The code shows *one* attempt branch and the commit history shows the cap
   sheet was frozen 13 commits before the run, but git does not record when a human
   decided not to use the allowance. The written justification is false; whether it was
   believed when written is not determinable from the artifacts.
2. **Whether a second attempt would have produced a construction.** Not tested. I am not
   asserting it would have.
3. **Whether E3's ladder numbers reproduce.** Pass 1 left this open and I did not re-run
   1176 simulations per budget. The sum/mean *mechanism* is confirmed in source and the
   derived ratios are arithmetic; the underlying ladder is not mine to re-derive here.
4. **Which E4 `$.ceiling` and `headroom.json` `$.ceiling` is the intended measurement.**
   They share a key name and disagree. Pass 1 recorded this; I did not resolve it.
5. **Why E4's top-level `acquisition` block says `no-reply` / "no dispatch was
   attempted"** while the same file's `acquisition_summary.acquired` says `6` and six
   dispatches with replies and 16-160s latencies are present. I found the
   contradiction; I did not determine which field is authoritative or which code path
   wrote the stale one.
6. **Whether the free route's HTTP 502s are rate-limiting, transient strain, or
   something else.** Two events cannot distinguish these. Unchanged from pass 1.
7. **Whether the four distinct tasks I recommend would produce distinct lineages.** They
   would produce distinct *prompts*; whether the model then produces distinct
   behaviour is exactly the open question, and it is only answerable by running it.

---

## 6. What I did not find

Stated explicitly, because the instruction was not to manufacture objections, and
because most of this batch is genuinely careful.

- **The three-count discipline is correct and load-bearing.** Construction events, unique
  source programs and retained records are three numbers and `campaign.json $.counts`
  says so in the record itself. The prior evidence got this wrong and the batch fixed it
  in the place a reader would look.
- **The route repair is proven, not asserted.** Six answered dispatches carry
  `provider: "Nvidia"` against frozen `provider: "nvidia"` with `route_error: None`. That
  is the exact contradiction that killed r1, and it is gone. This is the strongest
  positive result in the batch and pass 1 and I agree it holds.
- **E4 is valid experimental work.** Six live dispatches, six correct refusals, a
  diagnosed cause (`reducer_own_choice: 0` with a model expression that provably
  evaluates to 0), a bounded null on both sides, and a qualification suite whose
  disconnect arm is *present in the artifact* even though the ledger says otherwise. The
  matrix's framing of E4 is the right framing.
- **The taxonomy is a real partition.** Seven outcomes, no merges, the length check
  ordered before the parser so the causes stay separable, and `transport-loss` correctly
  distinguished from `invalid-program` on the two 502s. The assignment's requirement at
  `WORKER-PROMPT.md:48` is met structurally.
- **The disclosure culture is real.** `§6` of the matrix records the full-suite breaches,
  the unscoped `pkill`, the broken venv and the two lanes that wrote into the
  coordinator's checkout, unprompted. The ledger's "What is still not proven" table is
  nine rows long and every row names the artifact that would change it. This is why the
  defects above were findable.
- **E1's exposure accounting is closed and says so correctly.** 8 of 8 settled, 0 pending,
  0 driver faults, `parse_outcome: "transport-error"` on exactly the two 502s and
  `"pending"` on the six answered ones. The distinction between a lost send and an
  unstarted send is correctly recorded.
- **I did not run a single test file.** Everything above is source, artifact, or one of
  four quoted probes. The three-file budget is unspent, and per the brief I did not go
  looking for a fourth.

---

## 7. Summary for the coordinator

**Blocking for validity, both cheap:**

1. `experiments/ad01/w1_e1_campaign_r2.py:483,484,486,496` — spend the frozen repair
   allowance. Vary `attempt` and `seed` across the four lineages so the cell has four
   distinct inputs, not four repeats of one. 8 calls against the existing ceiling of 16.
   Without this, E1 r2 cannot support a per-cell claim of any kind.
2. `campaign.json $.planned.repairs_note`, `README.md:159-162`, `RESULTS.md:119-123` —
   delete the "not spendable" justification. It is false, and I verified it by running
   `render_output_prompt(…, 2)` and `output_operation_id(…, seed=23, attempt=2)`, both of
   which succeed. A record that explains an omission with a constraint that does not
   exist is worse than a record that admits the branch was never written.

**Honest-state corrections, no code:**

3. `reports/STAGE-09-COMPLETION-MATRIX.md:59` — E2's state label. `completed` contradicts
   the matrix's own rule at `:10`. Use `implemented` or `qualified`.
4. `reports/PROJECT-LEDGER.md:51` — the E4 disconnect control **is** in
   `improve_channel.CONTROL_ROLES` (`:888`, since `fcf26da`, 2026-09-26) and **is** in
   the campaign artifact. The claim that it is missing is wrong, and it understates E4.
5. `reports/evidence/inv_r1_e4/run/campaign.json` `$.acquisition` — `{acquisition:
   "no-reply", detail: "no dispatch was attempted"}` contradicts
   `$.acquisition_summary.acquired: 6` and `$.outcome.blockers[1]` in the same file.

**Naming, one line:**

6. `RESULTS.md:9` — "this time the zero is about the model" is the sentence the unspent
   repair allowance makes false. `RESULTS.md:78` already has the right version
   ("under this protocol it does not"); the headline should match it.

**Not blocking:** E4 stands as `completed, negative`. The three counts stand. The
taxonomy stands. The route-repair evidence is the batch's strongest result and I did not
weaken it.
