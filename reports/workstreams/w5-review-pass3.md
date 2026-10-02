# W5 review pass 3 — the recommendation

Reviewer: independent pass 3. Target: the architectural advice in
`reports/STAGE-09-COMPLETION-MATRIX.md` §5, not the code claims (pass 1) and not the
experimental validity (pass 2). No edits to the matrix, no commits, no full suite. Every
number below is from a named source line or from a command in this file.

---

## 1. The three recommendations, one line each

| Recommendation | Verdict |
|---|---|
| **Keep** accounting/provenance spine, five-way taxonomy, `route_matches` | **UNFALSIFIABLE** as written. Restates what already exists and is claimed to be strong. Two of the three are separately testable; the spine clause is not. |
| **Simplify** — delete the 3×3 from reporting, no fourth control, no DSL | **WRONG in one clause, SOUND in the rest.** Deleting the matrix contradicts `WORKER-PROMPT.md:62` and deletes a mechanism the tree already implements at `experiments/ad01/s09_swe_ast.py:303`. The "no fourth control / no DSL / no new subsystem" half is sound and I endorse it. |
| **Change** the revision boundary | **WRONG on the evidence given.** The `0.5017` vs `0.00622` gap does not measure what the recommendation claims it measures. It is a budget effect, not a decision effect. See §2. |

**Falsifiability, item by item.** Of the three, only the third is falsifiable, and the
experiment that falsifies it has effectively already been run (§2). "Keep the provenance
spine" is close to unfalsifiable: no experiment can show the spine is wrong, only that it
was unnecessary. It is a restatement of §2's capability, and §5 presents it as a decision.
The five-way taxonomy and `route_matches` *are* falsifiable in a specific form — whether
each of the five verdicts has ever been exercised by a real event, and whether any
legitimate route field variation exists. Neither is currently tested.

**One honest objection to the spine clause.** The matrix claims the spine is "why §2 can be
honest at all" (§5). §6 then records two files in the same evidence directory
(`campaign.json` vs `exposure.json`) that disagree about the same eight attempts. The
spine did not prevent that. What made §2 honest was a human reading raw JSON records. The
clause credits the machinery for an outcome it did not produce.

---

## 2. "Change the revision boundary" — the finding

The recommendation rests on one number: the boundary's expressive range is `0.00622`
against a decision spanning `0.0587`–`0.5017`, "roughly 70x". The first half is measured
on a different cohort from the second, and the comparison is confounded.

### 2.1 The two halves are not commensurable

`result.json` `$.ceiling` has `n: 75`; `$.evidence_ceiling` has `n_seeds: 150`. The cause is
in `experiments/ad01/learner_revision.py:911-940`: `ceiling()` takes the argmax on
`seeds[0::2]` and scores on the held-out half, so 75. `evidence_ceiling()` (`:943`) scores
the reducer against the incumbent on all 150. Recomputing both on the same 150 seeds and
the same `audit` split:

```
incumbent x=3 mean       0.058667      (matches $.evidence_ceiling.incumbent_mean)
best single input  x=12  0.066222
worst single input x=9   0.056889
single-input range on the SAME 150 seeds: 0.009333
reducer 8-input mean     0.501667      (matches $.evidence_ceiling.reducer_mean)
like-for-like ratio 0.443 / 0.009333 = 47.5x, not 71.2x
```

The headline is inflated by cohort mismatch. This is a reporting defect, not a fatal one.

### 2.2 The `0.443` is budget, not decision

This is the load-bearing problem. `evidence_ceiling()` compares a one-input incumbent
against an eight-input reducer sequence (`mean_queries: 8.0`). Two things change at once:
how many inputs the descendant observes, and which eight. The matrix treats the result as
the value of a *better decision*. It is not.

A same-shape, same-budget control — a per-seed random 8-subset, blind, no selection at all:

```
seeds   0-149  reducer delta=+0.4430 z=17.4 | per-seed random8 delta=+0.4605 z=19.6 | advantage of CHOICE = -0.0175
seeds   0-149  reducer delta=+0.4430 z=17.4 | per-seed random8 delta=+0.4447 z=19.6 | advantage of CHOICE = -0.0017
seeds 200-349  reducer delta=+0.4878 z=18.8 | per-seed random8 delta=+0.4394 z=16.7 | advantage of CHOICE = +0.0483
seeds 200-349  reducer delta=+0.4878 z=18.8 | per-seed random8 delta=+0.4411 z=16.7 | advantage of CHOICE = +0.0467
seeds 400-549  reducer delta=+0.4085 z=17.5 | random8 delta=+0.4802 z=17.7 | advantage of CHOICE = -0.0717
```

A blind random 8-subset matches or beats the frozen reducer's own choice, on three
disjoint seed blocks. The advantage of the *choice* is indistinguishable from zero. The
`0.443` is the effect of letting a descendant observe 8 inputs instead of 1. Fixed subsets
confirm it: `range(0..7)` scores `0.060`, `range(16)` scores `0.060`, and random 8-subsets
score `0.49`–`0.60`. The metric moves on *count*, not identity.

**So `evidence_ceiling` is not the headroom available to a wider revision boundary.** It is
the headroom available to a *wider query budget*. Those are different interfaces, and the
matrix's conclusion needs the first.

### 2.3 What the number actually supports

`0.00622` is a real and load-bearing measurement: within the frozen one-input decision, the
choice genuinely does not matter, and the six `delegates-to-unchanged-reducer` refusals were
correct. The B3 diagnosis of the *blocker* stands. §3.6's "the blocker is the boundary, not
the substrate and not the prompt" survives.

What does not survive is the inference from headroom magnitude to "highest-value move
available". The same 0.443 is available to a revision that simply spends more queries — an
interface change that keeps `_STRATEGY_SOURCE` as a selector and widens only the evidence
*set* the descendant receives. That is a strictly smaller change than the one recommended,
and the batch contains no evidence that the larger one is required.

### 2.4 The experiment that tells the two stories apart

The recommendation does not name one. Here it is, and it is cheap — it needs no live calls,
no new freeze, and it runs on existing code:

> **Give a same-budget control.** Hold the descendant's evidence budget fixed at the
> incumbent's (1 input) and at the proposed widened boundary's (8 inputs). At each budget,
> compare the reducer's choice against a random choice of the same size, paired by seed.
> If the reducer's choice beats random at matched budget, evidence selection is a real
> decision and widening the boundary exposes genuine headroom. If it does not — as my
> numbers say it does not — then the decision is not the lever, the budget is, and the
> correct change is to the evidence set, not to `_STRATEGY_SOURCE`.

The second arm is a fourth control, and §5 explicitly forbids adding one. That prohibition
is what protects this finding from being run. **The "no fourth control" clause is doing
load-bearing work in the wrong direction** — it forecloses the one control that would settle
the recommendation's own central question. I would narrow that clause to "no fourth control
on the E4 boundary as frozen", which keeps the freeze intact and permits a budget-matched
control measured offline against the sealed results.

I have already run this control. It does not support the recommendation as written. I am
not redesigning the boundary; I am reporting that the evidence the recommendation cites
does not point where it says it points.

### 2.5 Is the two-member source wrong at all?

Possibly, for a reason the matrix does not give. `_STRATEGY_SOURCE`
(`experiments/ad01/improve_channel.py:136`) is a two-member menu and `leaf_construct` (`:1196`)
installs one of them. A revision is a selector. That is a fair description of the
mechanism. Whether a *selector* is the right interface for "improving the learner" is a
research question the batch has not answered, and the 70x figure is not evidence against
the selector. Widening `_STRATEGY_SOURCE` from two members to a continuum of authored
strategies would be fitting the interface to a result whose measurement is confounded. The
recommendation is right that this needs its own freeze (B3 already says so) and I do not
dispute that. I dispute that the batch's evidence establishes the direction.

---

## 3. Deleting the 3×3 matrix — suppression, not simplification

**It is not honest as written, and the assignment already forbids it.**

`WORKER-PROMPT.md:62`, the exact clause §5 is arguing against:

> If a representation cannot express a required action, show the concrete limitation,
> leave the cell missing and continue supported cells.

The recommendation proposes deleting the nine-cell frame from reporting. That removes the
only surface stating "one constructible cell of nine". §1 of the matrix already says it
("E1 has one constructible cell today, not nine") and §6 already preserves it. Deleting the
*table* does not delete the *fact*, but it does remove the counted denominator, which is
the part that makes the gap legible to a reader who does not read §3.2.

Worse, the mechanism the assignment asks for is **already implemented in the tree**.
`experiments/ad01/s09_swe_ast.py:303` `missing_cells()` returns exactly it — two cells,
each with `missing_cell`, a `witness` (the loader's own refusal, quoted), and a
`consequence`. The module docstring says the point outright: "What the node set cannot do is
recorded as data... `expressivity()` reports it rather than leaving a reader to infer the
limit from a zero repair rate." The pattern exists, it is the sanctioned one, and §5
proposes to remove the table that would carry it.

The cap sheet is the concrete case. `reports/cap-sheets/w1-e1-cap.md:73-75` marks all three
representations supported on all three worlds. The matrix calls that row "a plan, not a
measurement" — which is right — and then proposes deleting the surface that would show the
gap, rather than correcting the row. **Correct the row to carry the missing cells with
witnesses. That is what the prompt asks and what `missing_cells()` already does.**

On the re-adding risk: real but secondary. The stronger argument is the assignment's.

**The "no DSL / no new subsystem / no fourth control" half of the Simplify clause is sound
and I endorse it without reservation.** Those three are correct, and they are the only part
of §5 that is a decision rather than a restatement.

---

## 4. The bottleneck the batch did not name

**The E2 study is unrun, the matrix ranks it second-largest, and it is not in the list.**

§1, W2/E2 row: "**The experiment** has not been re-run on the repaired metric... **This is
the largest remaining question after E1.**" §4 then lists B1 (acquisition prompts), B2 (no
recorded live construction), B3 (revision boundary). E2 is absent.

This is not a close call. `WORKER-PROMPT.md:66-75` (§W2) specifies four contrasts: relevant
vs no experience vs irrelevant/shuffled experience; retained reuse vs cold reacquisition;
within-domain vs held-out-domain adaptation; controlled observation perturbations. Plus two
independent campaign namespaces. §1 and §3.4 record **all** of these as unrun or void. The
instrument was repaired at `d42049c` (the `QUALITY` constant is gone; only a comment
referring to it survives, at `experiments/ad01/experience_axis.py:890`), and the matrix's
own §5 recommendation does not mention re-running it.

The cap is being met by dropping a real one. And it is dropped for a structural reason worth
naming: **all three listed bottlenecks require building more capability** (four prompts, a
live run, a wider interface). E2 requires *running a study on an instrument that is already
repaired and qualified*. The batch's momentum is toward construction, and the bottleneck list
inherited the momentum. The cheapest and most decision-relevant item in the whole document —
re-running E2 on a metric that can now vary — is the one with no lane and no commit.

Second-order, and it makes this worse: `d42049c` is a repair with no red-proof against the
live question, only against old code. A repaired instrument that has never been run is an
untested repair. E2 is the batch's only repaired-and-unrun artifact.

**Recommendation to the coordinator:** replace B1 or B2 with the E2 re-run. It is cheaper
than B1 (no new prompts), cheaper than B3 (no new freeze), and it is the only item that can
convert an existing negative-in-principle into an actual answer. My honest expectation is a
null, given r4's `CONTROL_WINS`. An instrument's capacity to produce a positive is itself
unproven, and §6 says so without treating it as a bottleneck.

---

## 5. Did the keep/simplify/change split honestly represent where the effort went?

**No. The largest coherent engineering effort in the batch is invisible in §5.**

Batch size, `git diff --shortstat 16f0784..HEAD`: **159 files, 12,658 insertions, 865
deletions.** Runtime containment and route-contract repair, by commit:

```
60d64ae  Stage hashed bytes exactly, on every host                757+5
655feb3  Install the child limits the launcher declares            745+14
ec89dcd  Contain a failing preexec_fn                              690+58
564465c  Make machine-consumed paths host-independent              581+4
98c23c7  Give child limits one cross-platform authority             519+12
4e1ed25  Derive the free signal once, for both halves               369+38
ccd3df3  Name repository-relative paths with forward slashes       338+5
3721cd6  Give the counting guard the same route owner              331+15
395d360  Re-freeze the route onto the id the provider serves         68+12
0a17ca9  Read staged bytes at the writer, not at the launch          31+9
```

Add the test files that cover them — `test_launcher_local_bounds.py` (508),
`test_swe_executor_capability.py` (435), `test_w1_live_preflight.py` (364),
`test_launcher_local_preexec.py` (364), `test_gateway_free_signal.py` (290),
`test_view_contract_swe.py` (267), `test_staging_fidelity_crlf.py` (259),
`test_w1_guard_route_owner.py` (253) — plus 85 files archived to `tests/_heavy_archived/`.
That is roughly **7,200 of 12,658 insertions, a majority of the batch**, spent on runtime
containment, path/staging fidelity, child limits and the route contract.

§5's **Keep** list names three things: the provenance spine, the five-way taxonomy,
`route_matches`. Two are E1/E4 research apparatus. The third is the *final* route repair,
`route_matches` at `src/settlement/gateway_http.py:180` — one function, one of ten commits in
that line. **The nine preceding repairs, the containment work, the host-capability
consolidation, the staging fidelity work, and the 85-file test archive appear nowhere in the
keep/simplify/change split.**

The one place they surface, §4's unlisted fourth candidate, dismisses them:

> no supported Linux execution environment on this host. It is real, it is named in §2, and
> it is not on this list because no amount of work on this codebase changes it.

That is a deployment fact and the dismissal is fair. But it is the *only* sentence in §5 or
§4 that acknowledges where the batch's effort went, and it is there to exclude it. The
structure of §5 is: keep the research apparatus, simplify two small reporting items, change
one research interface. The shape of the batch is: fix the runtime until it could run at
all, then run four studies, three of which came back negative or unrun. **A reader of §5
would conclude the batch was mostly research. It was mostly containment.**

Concretely, a recommendation that named the containment work as a choice would have to
answer: was one cross-platform child-limit authority (`98c23c7`, then `655feb3`) the right
call, or did it front-run a deployment that never arrived? Was the 85-file test archive
(commit `7238352`) a containment measure or an untested regression surface? §5 endorses none
of it, criticizes none of it. That is the tell — a recommendation that implicitly ratifies
whatever was built is not a recommendation.

I do not think this batch was wrong to spend the effort. Without it nothing runs. But a
keep/simplify/change split that leaves the majority of the diff unmentioned is not
accounting for it.

---

## 6. Undetermined

- **Whether any of the five `preflight_verdict` outcomes beyond `route-refusal` and
  `transport-loss` has ever been produced by a real event.** The taxonomy is defined at
  `experiments/ad01/live_construct.py:1434-1438`; the batch exercised two of five. Three are
  untested branches, not verified machinery.
- **Whether a legitimate route field variation exists that `route_matches` would wrongly
  reject.** The "keep" is a bet on a two-member route contract being complete. Untested
  either way, and it is now the single owner of that judgement.
- **Whether the E1 `campaign.json` / `exposure.json` disagreement (§6) is a bookkeeping defect
  or a real double-spend.** Unresolved in the batch and outside what I can reach read-only.
- **Whether E2 on a repaired metric produces separation.** I expect a null. I have no
  measurement, and the only way to get one is the study the recommendation omits.
- **Whether `0.00622` is stable.** It is measured on 75 held-out seeds. I recomputed the
  like-for-like range at 0.009333 on 150. The order of magnitude holds; the ratio does not.
- **Whether the E4 model replies would differ under a widened boundary.** All six named input
  0. Under any interface that requires a real choice, the same replies are uninformative.
  The matrix says "more dispatches cannot help", which is right about the current boundary
  and silent about a different one.

---

## 7. Bottom line

The Keep list is mostly unfalsifiable and the Simplify list contains one clause that
contradicts the assignment and deletes a mechanism the tree already implements. The Change
recommendation rests on a number whose two halves are measured on different cohorts and
whose effect is budget, not decision — a blind random 8-subset matches the frozen reducer
at 47x the claimed headroom. The bottleneck the batch dropped is the E2 re-run, which its
own matrix calls the second-largest remaining question. And the majority of the batch's
12,658 lines is absent from a keep/simplify/change split that therefore does not describe
this batch.

Two things in §5 I would keep unchanged: the refusal to add a fourth control *to the frozen
E4 boundary*, and the refusal to build a DSL or a new subsystem. The boundary itself needs
its own freeze, as B3 already says. What should not survive is the claim that the batch's
evidence establishes which way that freeze should go.
