> Historical batch report, cut at `34463a6` on a branch whose commits do not
> resolve in the current repository. Current scoped status is reconciled in
> [PROJECT-LEDGER.md](PROJECT-LEDGER.md) and
> [STAGE-09-10-COMPLETION-MATRIX.md](STAGE-09-10-COMPLETION-MATRIX.md). Read it
> for what that campaign measured; its M3 verdict was superseded by the
> 2026-10-01 batch, which returned acquisition NEGATIVE on a denominator of one
> returned artifact.

# Stage 9 connected study: status at the merged tip

Against `34463a6` on `codex/implementation-investigation-learning-02`. Sixteen lanes, all
merged, every lane's claim verified against the real diff before acceptance.

## What the assignment asked, and where each part stands

| Part | State | Evidence |
|---|---|---|
| M0 inventory and map | done | `reports/PLAN-STAGE-09-CONNECTED.md`, all three findings reproduced at the source |
| M1 budget and authority | done | three currencies, unrepresentable collapse, 5563 held units untouched |
| M2 representations and worlds | **partial** | three real registrations, plus a real software world; the three representations now cross-compared (E1). **The software world is not part of a world-addressable harness**: `s09_arm_parity.episode_runner` raises for any name but `boolean` and `ordering`. |
| M3 prospective live pilot | **run twice; the repair is confirmed by execution, but the acquired capability reproduces the authored control** | `inv_r1_m3_run7` acquired 1 of 6 and refused all 24 use records, because `_fresh_use` never passed `--policy-source`. Run 8 (`inv_r1_m3b`, 30 model calls, 564 witness queries) passes it: **3 use records executed** a model-acquired `ENTRY` on real software tasks with `normalized_reduction` 0.769, 0.700 and 0.300, one of them a transfer task. The other 33 are refused. **Caveat, verified against the raw records: the acquired member's `method_source` is `reduce_software(..., method="ddmin", ...)`, which is the same call `seed-sw-ddmin` resolves to, and the authored control scores identically to the last digit on the first two tasks. So the execution is real and the plumbing is fixed, but the capability reproduces the authored baseline rather than deriving a method of its own.** The 30 refusals are the five empty repertoires; the other 3 are graph tasks the software-scoped member cannot answer. |
| M4 independent verification | **all three options measured; the choice of what to claim is the researcher's** | withholding parses but is invalid (Jev 0.21); summarising reduces to withholding; raising the cap was run live at 4096 tokens and produced 1 of 5 parsable, so compliance is a 20% event |
| E1 connected comparison and SWE | **the qualifying instrument now runs; first of four acquisition lineages complete** | the SWE world is real executable fault repair with a common-harness fork recorded (N-58), not the data-only `reduce_software` state machine the handoff excludes. Five defects were found under the first retracted run: a `candidate.strip()` dedup that made every in-function candidate an `IndentationError`, and - the one that decided the zero alone - a `repair` branch unreachable while probes remained, so the search dry-ran a correct repair, scored 2 of 2 and stopped with 149 probes unspent. All three search bounds are now derived from the panel (probe 60 to 303, suspect cap 4 to 10, turns 80 to 307), and `probe_reach` went 15/30 to 30/30 held-out. **Lineage L0 repaired 31 of 39 instances, which is exactly the reachable boundary**: 39 total (9 dev + 30 held-out) minus 8 whose reference repair is not in the candidate space at all - five `swapped_window` needing a two-part repair, `stale_accumulator` needing text the faulty program does not contain, one dev `off_by_one` needing an added term. All four lineages returned 31 of 39 independently on distinct record digests, and the per-family counts are measured: **16 of 24 families at rate 1.000, 3 at 0.500, 5 at 0.000** (124 of 156 `python-step` rows repaired). The five at zero are `stale_accumulator` on all three structures plus the two `for`-form `off_by_one`; the three at half are two `swapped_window` needing a two-part repair and one `index_drift` lost to public-set overfitting, where five candidates tie at 2 of 2 and the search applies the first, which fails the protected test. The honest reading is that the STEP representation repairs everything it can express and nothing it cannot, which makes the remainder a panel finding rather than a solver result. A correction: this lane first reported 12 families at 1.000; the artifact says 16 and the artifact is what is recorded. |
| E2 experience interventions | **re-run on a scored observable; tie, and negative** | all three arms score 1.0 and 0.0 on evidence — none read their observations |
| E3 autonomous selection | **run on four frozen yields; two-sided, not a win** | adaptive agenda vs a fitted constant under one envelope, three worlds, six budgets. Leads on retention and diagnosis at every budget, trails on held-out quality at 20 and 40. The control's schedule is six wide and is spent at budget 20 |
| E4 executable learner revision | **entry points untested (now pinned); blocked by the substrate, not by a runner** | `channel_headroom(split='dev', seeds=[0,1,2])` = **-0.0222** against a resample spread of **0.0667**, `measurable: false`. The best reachable probe scores below the incumbent and the gap is inside the noise. N-26: an admitted revision can have selected nothing and still report `informs_decision: True` — latent, E4 has no caller |

## The two findings that changed what the study can say

**The instrument worlds published their own answer.** `task_id` was
`order-dev-0005`, and `make_task` derives the hidden target from that seed. Verified
through the real action contract, not a mock:

```
comparisons spent : 0   (budget is 8)
FINAL              : {'overall': 1.0, 'exact': True, 'n_comparisons': 0}
```

A policy holding only the public view scored full marks without spending a query. That
voided every acquisition claim on the Boolean and ordering worlds. The identifier is now a
digest; the seed stays on the task for the grader. Your call was to fix the ids and leave
r4's frozen bundle as history, and that is what happened. One consequence to record: r4's
own eight prompts embed the old identifiers, so r4's reservation sizing no longer
re-renders and **refuses with the prompt named**. The 18688 units that sizing computed
are unchanged, and they are a campaign sizing rather than held exposure.

**The launch gate was judging the study by its own output.** It read the bundle the study
was about to write and passed on a digest list, an action field, and two distinct digests.
The digest and the action came from *different* records, and a single valid retained policy
was scored `unproven`. Launch is now qualified by executing reviewer policies through the
real out-of-process step boundary, and the post-effect join is a separate call.

## Repairable defects, closed

- **Budget.** A null provider charge became a verified zero, was scaled by a dispatch count
  into a unit ceiling, and 5563 reservation units were subtracted from it to report
  `-5563 dispatches`. Now three currencies, and `Sends` cannot be multiplied by a unit
  figure at all. Jev read this as a dimensional error rather than the liability decision a
  prior session reported, at 0.99 confidence.
- **The budget had gone silent.** The ledger deleted the unit ceiling the preflight read,
  and that read sat inside a bare `except`. Every study would have reported the budget
  unresolved forever. The ceiling is a count of sends again.
- **Route pin.** A contract could pin a resolved model the study was not running, because
  the guard read `and` where it needed `or`. Found by probing the real route.
- **The AST timing test.** Three lanes reported it as environment flake. It is a test whose
  1000 ms budget sat below its own cold-start cost, measured at 0.36 to 0.89 s. The
  published `mechanism: true` was host-dependent because of it.
- **The coverage gate.** A campaign module missing from `CAMPAIGN_GLOBS` has no import
  edge to any test, so a test exercising it silently leaves the intersection. Four modules
  were missing.
- **The panel gate.** Twelve draws from a support of twenty-four are all distinct 3.55% of
  the time, and nothing checked. The panel now audits four properties and refuses before
  returning.

## Negative results, which are results

**Autonomous investigation selection is active and loses.** The treatment was inactive
before: the proposer closed over the loop task, so every trajectory ran the authored
schedule. It now chooses from a coordinator-supplied portfolio and reaches real admitted
operations. **The severing counterexample is now RUN** (2026-09-27, 24 cells, both arms,
digest-pinned, in `inv_r1_e3_selection/e3-sever-control.json`): the severed arm is a strict
prefix of the connected one in every cell, and the effect vanished in all 24, 18 of which
had an effect to lose. So "the effect is caused by the decision, not by the schedule" is
established on executed evidence for the first time, and the earlier complaint — that no
test referenced `sever` — is now closed.

**But the same sentence fails for a second and more serious reason: E3's decisions reach
no store at all.** `run_investigations` (`selection.py:761`) accepts no `dsn`,
`_run_development` builds its `DecisionConsumer` with `dsn=None` (`selection.py:724-726`),
and every candidate the portfolio offers is a `SEED_CAPABILITIES` id, so
`trajectory._run_member` short-circuits at `trajectory.py:1318` to a pure in-process
reducer. The store-backed `method_exec` branch below it is unreachable from E3. Measured:
a full connected run at budget 40 opens **zero** database connections and writes **zero**
rows to `operations`. The gate, the checker and the execution are real; the persistence is
not. **The most accurate claim E3 supports is that autonomous selection has a measured
causal effect inside the harness, with no durable operation behind it yet.** Wiring a dsn
through `selection.py` is the fix and it has not been made.
But the
held-out optimum is identical in all three qualified worlds, so a constant already names
it and adaptation has nothing to discover. From 30 units up the fixed control wins. The
control is the strongest world-blind rule pair, fitted by exhaustive search over all
**196** combinations (`2 x 2 x 7 x 7`, `test_s09sel_divergence.py:150-160`), so this is
adaptation against a genuinely competent baseline, not a strawman.

**QUALIFIED 2026-09-29 — the competence claim above is verified at one budget, not
across the ladder.** `test_s09sel_divergence.py:135` searches all 196 constant pairs and
asserts none beats `DEFAULT_RULE`. It passes, at `BUDGET = 40`, a module constant, and at
40 the default is genuinely optimal. Counting the rules that beat it per budget:

| budget | 8 | 14 | 20 | 30 | 40 | 60 |
|---|---|---|---|---|---|---|
| rules beating `DEFAULT_RULE` | 0 | 0 | **96** | **94** | 0 | 4 |

At budgets 20 and 30 the default is beaten by roughly half the search space. The
sentence above is therefore true where it is checked and unqualified everywhere else,
and it cites that test as its proof — so a reader who follows the citation finds a green
test and concludes the claim holds. **A check narrower than the claim made from it is
worse than no check.** `TASKS.md` C18 carries the row; `fitted_fixed_rule`
(`agenda_policy.py:296`) adds the control the claim was reaching for and changes the
sign of the result. Evidence: `reports/evidence/inv_r1_e3_fitted_control/`. The figure "98" in an
earlier draft of this line matched neither the test nor `selection.best_fixed_allocation`
and is not supported by the code.
**No benefit is claimed.**

**The learner-revision channel has no headroom — but the first estimator I used
to say so could not return a positive number, and the conclusion survived only
after a different measurement.** `channel_headroom`
(`experiments/ad01/improve_channel.py:615`) compares `reachable_lineage_spread`
over the **full** cohort against `noise_floor` over **half** cohorts
(`seeds[0::2]` vs `seeds[1::2]`, line 596). A spread measured on n/2 samples is
structurally larger than one measured on n, so `headroom < 0` holds by
construction. The scaling sweep in `reports/evidence/inv_r1_e4/headroom.json`
shows it: negative at every cohort size from n=3 to n=384, both terms shrinking
together, never crossing. **A negative headroom from that estimator is not
evidence about the substrate.**

**The conclusion is still a negative, and it now rests on a measurement that can
discriminate.** The reachable descendant set is {3, 11}; their means differ by
-0.00138 with a standard error of 0.00123 (z = -1.12 at N=1500, so ~4619 seeds
would resolve it). More decisive, the ceiling over **every input the instrument
accepts** is 0.00267 — all sixteen input means fall between 0.0588 and 0.0609.
Choosing a better probe is the only lever this channel has, so a wider menu
cannot help either. **There is no headroom out there to reach.** The apparatus
itself is qualified: over 24 seeds the known-effect revision moves descendants
+0.2596, a no-op moves them exactly 0.0, and a disconnect moves them exactly 0.0
against a descendant that learned nothing. A qualified apparatus returning a
negative is a real negative, which is the handoff's own standard for completing
an experiment. **No live campaign was run, and that was the right call: it would
have spent budget measuring noise.** The estimator defect is recorded as N-63
and was deliberately not edited, because fixing it is a substrate decision and
the paired measurement already answers the question.

**The intervention boundary is real:
`imp_source` picks a probe input, `drive_improve_round` spends it, and the output bit
selects the descendant package. Two tests drive real rounds and confirm different probe
inputs build descendants with different digests. But the reachable descendant range across
all sixteen development probes is 0.0087, while two halves of the *same* cohort with no
decision difference at all disagree by 0.0107 to 0.0120. The entire effect is noise, and
the halves disagree on which probe wins. `channel_headroom()` reports this as
`measurable: False` so a study can be told before it is run.

The apparatus is qualified: a known-effect revision moves descendants +0.2596, a no-op moves
them **exactly** 0.0, and a disconnect produces **exactly** 0.0 against a run that learned
nothing. A moving no-op marks the apparatus unqualified, not merely unproven. So the
machinery is sound and the question it was built to answer has no answer on this substrate.

## E3, run properly, and what it says

`run_e3` is an **eligibility screen** and always was: the keys it writes
are `arm`, `arm_revisions`, `arms`, `available`, `eligible`, `evidence`,
`evidence_digest`, `execution`, `imp_digest`, `operation_id`,
`package_digest`, `reason`, `receipt_identity`, `status`, `study`, and
it returns `status: eligibility-screen`. The words `control`, `quality`
and `diagnos` do not occur in it. So my earlier line — *"E3 | run,
negative | treatment active, loses to a competent control"* — described
an experiment that was never run, and Jev scored that claim at 0.02.

The experiment was buildable, and I had been treating it as a decision
rather than a task. It is now run: `experiments/ad01/s09_e3_selection.py`,
evidence in `evidence/inv_r1_e3_selection/`, ten tests in
`tests/test_s09_e3_selection.py`. It reuses the treatment and control the
prior lane left behind — `agenda_policy.AgendaPolicy` and
`agenda_policy.FixedPolicy` — and measures the four yields the handoff
froze, on three worlds at six budgets, under one envelope each.

| budget | retained (ag / ctl) | held-out (ag / ctl) | charged (ag / ctl) | choices (ag / ctl) |
|---|---|---|---|---|
| 14 | 3 / 0 | 0.145 / 0.000 | 36 / 27 | 5 / 4 |
| 20 | 4 / 3 | 0.157 / 0.253 | 45 / 46 | 6 / 6 |
| 40 | 10 / 3 | 0.219 / 0.251 | 101 / 46 | 12 / 6 |
| 60 | 17 / 3 | 0.234 / 0.123 | 167 / 46 | 19 / 6 |

**The result is two-sided and neither column supports a claim on its
own.** The agenda retains and diagnoses more at every budget; the
control holds out better at 20 and 40. The cause is visible in the last
two columns: the control's schedule is six investigations wide and is
fully spent at a budget of 20, after which it charges 46 and stops
while the envelope is still unspent. The agenda keeps spending.

**RETRACTED 2026-09-27 — the ladder above is not three runs per budget.**
`crossover()` at `s09_e3_selection.py:117-127` constructs the policy once per
arm with `policy = make_policy()` and only *then* loops `for world in worlds`,
so one stateful instance walks all three worlds and all six budgets. The
control's totals are cumulative prefix sums of a single traversal: 19, then 27
(`+8`, the fourth step), then 46 (`+9+10`, the fifth and sixth), and 46 is the
full six-step schedule total `6+6+7+8+9+10` — after which no budget adds
anything. Every published row reconciles exactly under this reading, so the
numbers are internally consistent, but they are **one trajectory labelled as
eighteen**. The `_arms()` factory fixed sharing across *arms*; it did not fix
sharing across *worlds* and *budgets*, and the artifact was committed in the
same commit as the fix, so the committed JSON was produced by pre-fix code and
never regenerated. **The "the control is stopped by its own schedule"
explanation is an artifact of the harness rather than a property of the
baseline, and the no-benefit conclusion is not established by this evidence.**
E3 must be re-run before it supports any claim.

That splits the two regimes, and the split is why no benefit is claimed:

- **At 14 the comparison is fair** and the agenda wins outright. The
  control retains nothing in any world because it cannot afford to, and
  both arms wanted the same work.
- **From 20 it is not a fair comparison of selection.** The control is
  stopped by its own schedule rather than by the envelope. Its
  held-out wins at 20 and 40 are a constant policy's ceiling, not
  evidence that it chose better than an alternative.

Two harness defects of mine surfaced only because the tests were written
to be able to fail. Sharing one policy instance across worlds let world
1's trajectory decide what world 2 was allowed to pick — `_untried`,
`_step` and `_stop` accumulate, and two of my three asserted signs were
an artefact of that. And the saturation test originally used
`spent < 3 * budget`, which is true of the tight budgets too and could
not tell the two regimes apart. **The numbers above are NOT post-fix** - see the
retraction above; the committed artifact was produced by the pre-fix driver.

The prior lane's finding stands and is the reason the ceiling is
unbeatable: over the qualified worlds the held-out-optimal
(capability, depth) is world-invariant, so a constant already names the
optimum. Jev scored "run this, it beats a competent control" at 0.02 on
the old `run_e3`; on the measured ladder the honest summary is that
adaptive selection converts an open-ended envelope into more retained
behaviours than a fixed schedule can, and does not hold out better
quality for it.

## Still open, and not mine to close

1. ~~**The offline verifier hashes its own source**~~ **CLOSED in code, and this line was the
   stale half of the story.** `experiments/ad01/offline_recompute.py:1910-1917` now *reports*
   `verifier_digest()` rather than checking it, with the reasoning that a checker cannot
   attest its own integrity against a value frozen before it was written, and the verifier is
   no longer listed in `OUTPUT_CODE_PATHS` (`:31-36`). No frozen bundle is unverifiable by
   construction any more. **What is still open is the other half, which I had inverted:** M4's
   real blocker is that the model on the free route will not answer in the admitted format, so
   there is no clean baseline to test against and therefore still no tamper test. A working
   verifier and a missing baseline are different problems; I had filed them as one and named
   the wrong one as the cause.
2. **Against the r4 bundle, all seven tamper examples "reject" with a problem list
   identical to its own 15-problem baseline**, so they prove nothing there. Five of seven now
   reject against a clean baseline: Lane J closed foreign study identity and
   absent-usage-as-zero, and both are verified by test rather than by reading.
3. **E2 is complete, and the completion is a negative.**

   All five contrasts ran. Then the handoff's third pass — challenge every
   positive conclusion — ran a 2×2 and a six-cell replication, and the
   result is that **the `diagnostic` field echoes the most recent family
   token in context, identically with and without experience.** Every
   contrast that read a difference in it was reading an echo, which is why
   two of them reported a positive.

   | contrast | status |
   |---|---|
   | relevant vs no experience | **retracted** — the difference was the echo |
   | relevant vs size-matched irrelevant | **retracted** — same reason |
   | retained vs cold reacquisition | **survives** — a cost result from the cap sheet, no model behaviour |
   | source-to-target adaptation | **void** — the arm never left the echo, so the contrast is uninformative |
   | observation substitution | **survives** — about envelope defects in acquired bytes, not family preference |

   A dependent variable that echoes its input cannot support a claim that
   the input influenced the output, and all five contrasts had that shape.
   The next step is a scored observable — the quality of the returned policy
   on the target task — not another sample of this one. Full reasoning in
   `reports/evidence/inv_r1_e2_challenge/`.
4. **r4's reservation sizing no longer re-renders** and refuses with the prompt named. That
   is correct for a frozen campaign and it means r4's allowance can no longer be re-derived
   from current source. The 18688 units that sizing computed are unchanged; they cannot
   be re-derived from current source. **[Settled `94443a7`: 18688 = `4 × 2294 + 4 × 2378`,
sourced from the test bodies at `f3af21a`. It was a sizing, not held liability.]**
5. **The model narrates when the prompt carries observations, and Jev's dissent is what
   found out why.** I reported this as a substrate blocker. Jev scored the diagnosis 0.34
   while scoring the decision to stop at 0.87, and the low score sent me to a variable I
   had not swept. Varying *only* how the observations are presented: eight rows gives 5732
   characters, three gives 5268, a withheld string 8167, and **no rows 167** — valid JSON,
   parsing through the real validator against the real 512 cap.

   So the model does not fail the format; it does the task out loud and the cap falls
   between the derivation and the payload. Every earlier probe kept the rows in the prompt,
   which is why none of them saw it.

   **The remaining choice is the researcher's, and Jev says so at 0.83.** Withholding parses
   but is not a valid design (Jev 0.21): a predictor committed with no observations is a
   fixed guess. Its preferred alternative, summarising, parses at 143 characters with a
   count-only summary and fails at 4818 with the actual spend data — the narration is
   triggered by the data values, not their presence, so a summary that keeps the data is
   the data. That leaves raising the cap, whose consequence I have deliberately not
   tested because loosening `extract_fenced_json` changes what the study measures.
   Three options, all measured; the decision is what the study should claim.

## M3's gate sequence, once the verifier can establish a clean baseline

The pre-launch qualification already proves with two chains and every link correctly marked
unpersisted. The preflight reads in dispatches. The route is pinned and the study's own
validator accepts it while refusing a paid tier and a model mismatch. The cap sheet prices the
campaign from real request bounds. The send ceiling is now enforced on the path a dispatch
actually takes. What remains is the reissued freeze, which is item 1.

## Decisions taken without dissent, 2026-09-27

**Jev was unavailable for the final hours of this assignment.** Two invocations, minutes
apart, both returned `403 RestrictedModelsError` — "Free tier users do not have access to
this model" — on model `typesafe-ai/jev`. Not transient, and a model-entitlement refusal
rather than an auth failure, so the alternate key the skill checks would not have helped.
Recorded as N-53, committed as `74261ef`.

**No substitute was built and no score was invented.** Every lane working this shift was
instructed not to call Jev, not to fabricate a score, and to name in its own report which
of its decisions would otherwise have gone to Jev. Those named decisions are the real
deliverable here: they are the places where this branch's own judgement stands alone.

**What this costs, stated plainly.** The handoff asks for Jev "at consequential decisions:
experimental identifiability, representation expressivity, evidence validity, alternative
root causes and final architectural implications." The coverage audit independently found
that **no persisted Jev artifact exists for E1, E3 or E4** — three of the five consequential
decisions in this batch — so those were already unreviewed before Jev went down, and the
retractions in this report were made without dissent. The E4 headroom decision in particular
is a negative result that an adversarial reader should re-examine on a branch where Jev
works, because "the substrate has no headroom" and "my probe cannot reach the headroom"
are different conclusions with the same number attached.

The next conceptual decisions should be taken with Jev restored. They should not be taken
on this branch's own judgement, and this report should be read with that limitation
attached to every conclusion in it.

## What the campaign cost

16 lanes, 41 merged commits, 57 files, +13,923/−495, plus four independent reviews. Sixteen worktrees created and
torn down, zero `wt/*` branches remaining, zero leaked disposable databases. No model
dispatch was spent. The key is absent from the tracked tree; its presence in pushed history
at `00473ac` and `9eaa551` is the known, accepted, reported condition, and removing it needs
a rewrite the assignment forbids.
