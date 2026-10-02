# W5 verification of the d30bbf2 and fc757e4 corrections

Final verification reviewer. I wrote none of the code or prose under review.

Scope: check the five corrections at `d30bbf2` and `fc757e4` against source, sweep
both handback documents for surviving false, overstated or stale claims, then answer
whether the handback ships. I did not re-litigate the batch.

Environment for every command below. `uv run`, `S09ISO_DISABLE=1`, `PYTHONPATH` set to
the repo and `src`, the three `SETTLEMENT_*DSN` variables unset, no
`PYTEST_DISABLE_PLUGIN_AUTOLOAD`. No live model call, no Jev, no paid route. Test runs
were two named files only; the full suite was never run. No file was edited except this
one, and nothing was committed.

---

## 1. The five corrections

### C1. The retracted E2 claim — **CORRECT**

The retraction is right on both halves, and I confirmed it by calling the functions
rather than by reading prose.

`experiments/ad01/e2_replication.py:1322` reads `NORMALIZED_REDUCTION`, and that
constant is the literal string `"normalized_reduction"`
(`experiments/ad01/s09_e2_scored.py:116`). It does not read `action`.
`experiments/ad01/e2_replication.py:1335` (`_decision_of`) is the one that reads
`action`, which is what the coordinator quoted correctly.

The rows carry both keys. From `reports/evidence/invr1e2contrastr2/report.json`, every
arm block has `normalized_reduction` and `action` in its key set. A representative
reading, `readings.relevant["ad01-w0-within-sw-00"]`, has
`normalized_reduction: 0.7` and
`action.inputs: {max_queries: 8, method_id: "seed-sw-ddmin"}`.

The contrast is real, not zero. The artifact's `paired` block gives
`deltas: [0.0, 0.0, -0.27272727272727276]`, `delta: -0.09090909090909093`,
`z: -1.2247448713915892`, `measured: true`, `n: 3`, with `contrast_on:
"normalized_reduction"`. The per-task derivation the retraction quotes
(`0.4545 - 0.7273 = -0.2727`) is the third delta.

One nuance the documents do not state, which strengthens rather than weakens the
retraction. There is a **second, distinct wiring defect that is still live**, and it is
not the one the coordinator described. `_measured_row`
(`e2_replication.py:250-256`) writes the key `"reduction"`, while `_reduction_of` reads
`NORMALIZED_REDUCTION`. Those are different strings. I confirmed by execution:

```
reading_row writes NORMALIZED_REDUCTION key? False
reading_row writes "action"?             False
_measured_row writes NORMALIZED_REDUCTION key? False
_measured_row writes "reduction"?        True
reading_row output keys: ['agreement','arm','detail','evidence','evidence_total',
                          'evidence_varied','score','scored','selected','verdict']
_reduction_of(reading_row(...)) = 0.0
_decision_of(reading_row(...))  = {'method_id': '', 'max_queries': None}
```

So `reports/evidence/invr1e2contrast/RESULT.md:110-118` and `:425-427`, and the
module docstring at `experiments/ad01/e2_contrast_campaign.py:26-34`, describe a **real
and still-unrepaired** defect on the `reading_row` path. That is not the claim that was
retracted. The retracted claim was that this mechanism explains the **r2** contrast, and
it does not, because r2's driver kept the whole `Reading` and bypassed `reading_row`.

The recommendation says exactly this and no more at
`reports/STAGE-09-RECOMMENDATION.md:296-297` ("A wiring defect of the kind described may
still exist in `_measured_row` for callers that use it; it does not explain this
contrast"). That is accurate. **The live defect is under-disclosed, not
over-disclosed**, and closing it is B1's first named action.

No surviving sentence in either handback document asserts the false version. The
retraction is struck through at `STAGE-09-RECOMMENDATION.md:287` and restated in
prose at `:288-298`; the matrix carries the same correction at
`reports/STAGE-09-COMPLETION-MATRIX.md:97`. A grep for the false assertion across
`reports/` and `docs/` returns only struck-through, retracted, or historical-record
context.

### C2. "Route availability" to "2048-token output budget" — **INCORRECT as written, and the correct reading is a third one**

The corrected claim is better than the one it replaced, and the 9-of-12 tally is
right. But line 734 contradicts the artifact it cites, and the contradiction runs the
wrong way.

`reports/evidence/w1-e1-boolean-r3/route-probe.json` `$.probes`:

| probe | status | note |
|---|---|---|
| `campaign-prompt-budget-16` | 200 | `finish_reason: length`, 72 content chars |
| `campaign-prompt-budget-256` | 200 | `finish_reason: length`, 1034 content chars |
| `campaign-prompt-budget-2048` | **null** | `TimeoutError: timed out` after 182.06 s |
| `short-prompt-budget-2048` | **502** | `error_type: "empty"`, 6.0 s |

`STAGE-09-RECOMMENDATION.md:732-735` says "the same campaign prompt returns 200 at 16 and
256 output tokens and 502s at the protocol's own 2048; **a short prompt returns 502 at
2048 but a different one returns 200 at 2048**, so the trigger is the requested budget,
not the prompt".

There is no 200 at any 2048 budget anywhere in the probe. The two 2048 outcomes are a
timeout and a 502. The "a different one returns 200 at 2048" clause has no referent in
the artifact.

This is inherited, not invented. The probe's own `findings` entry
`output-budget-causes-the-502` ends "a short prompt returns 200 at 2048", and
`reports/evidence/w1-e1-boolean-r3/RESULTS.md:206-210` repeats it. The probe's finding
text and the probe's probe data disagree, and line 734 sides with the text.

**The third reading.** The data does not separate budget from prompt, because the two
variables are not crossed. Both 200s are the campaign prompt at low budget; the only
2048 outcomes are a timeout (campaign prompt) and a 502 (short prompt). The short
prompt is the one data point that is *not* a failure, and it is also the one with the
smallest request. So the evidence supports: **the route fails above 256 requested
output tokens, and r3 ran at 2048** (`campaign-manifest.json:27`,
`max_output_tokens: 2048`; `route-probe.json` `frozen_max_output_tokens: 2048`).
"Output budget" is the right correction to "availability". "The trigger is the requested
budget, not the prompt" is **not established**, because no short-prompt-at-2048 success
exists to establish it.

Note also that the `budget-2048` campaign arm is a **timeout**, not a 502. So
`:733` ("502s at the protocol's own 2048") is also imprecise for that arm.

Severity: the load-bearing part of the correction is sound and the plan it drives
(measure at a budget the route accepts) follows. The two sub-clauses are wrong as
written.

### C3. E3's "ratio exactly 3.0" — **CORRECT, and the identity claim is right**

`MEAN = SUM/3` over exactly three worlds, so `SUM/MEAN = 3` identically. I confirmed
`selection.WORLDS == (0, 1, 2)` and `len == 3` by execution. The document now says so
at `STAGE-09-RECOMMENDATION.md:753-755`, in the same terms, and demotes it to an
identity. The matrix never carried the ratio as a finding: it reports the corrected
`0.139776` against `0.083721` at `:183` and `:187`. Correct.

**Does the E3 finding still stand without the ratio?** Yes, on two independent legs,
and I re-derived both from source rather than from the recorded JSON.

The crossover. I ran `e3.qualified_ladder(worlds=(0,1,2))` and got, per budget,
`agenda_mean / control_mean / best_rule_held_out_reduction`:

| budget | agenda mean | control mean | best (sum) | agenda > control |
|---|---|---|---|---|
| 8 | 0.000000 | 0.000000 | 0.000000 | tie |
| 14 | 0.083721 | 0.000000 | 0.000000 | **agenda wins** |
| 20 | 0.083721 | 0.000000 | 0.419328 | agenda |
| 30 | 0.111748 | 0.111111 | 0.525770 | agenda (barely) |
| 40 | 0.144745 | 0.359281 | 1.077842 | control |
| 60 | 0.205876 | 0.391007 | 1.242831 | control |

The crossover against the oracle is 20, not 30, and 14 is the agenda's only win against
a best of `0.000000`. The ladder's own module docstring
(`experiments/ad01/s09_e3_selection.py:220-232`) says the counts are world-set
dependent, and my table reproduces that: 0.111748 versus 0.111111 at budget 30 is the
degenerate pooled sign the ledger names at `reports/PROJECT-LEDGER.md:43`.

The arm counts. `agenda_policy.control_competence` re-derives 96 beating the default at
budget 20 over three worlds and 94 at budget 30, matching the matrix table at
`STAGE-09-COMPLETION-MATRIX.md:183`.

**Is the sum/mean defect still real in source, or only a presentation mismatch the
ladder handles?** It is real in source, and the ladder does not handle it. I called the
function:

```
WORLDS = (0, 1, 2) len = 3
budget 20: best SUM over 3 worlds = 0.419327731092437
  MEAN would be = 0.13977591036414566
```

`experiments/ad01/agenda_policy.py:435-440` returns
`sum(... for world in worlds)`. `experiments/ad01/s09_e3_selection.py:283` divides the
arm rows: `sum(reductions) / len(reductions)`. So
`best_rule_held_out_reduction` carries a **sum** in a field named as a reduction, and
every consumer that compares it to an arm mean is comparing across a factor of three.

This is **not** merely presentational, for two reasons.

First, the quantity is consumed. `agenda_policy.py:480` uses it as the yardstick for
`rules_beating_it` and `gap_to_best`, and the two tests read it. The wrong scale is not
confined to a report field.

Second, the name says `held_out_reduction`, so any future reader or refactor that
trusts the name computes a wrong comparison silently. Nothing in the code marks the
field as a sum.

The correct reading of the field's own semantics: dividing the sum by `len(worlds)`
gives `0.139776` at budget 20 against the agenda's `0.083721`, a margin of **1.67x**,
not 2.7x. Both documents now report 1.67x. The direction survives; the magnitude was a
denominator artifact, exactly as corrected.

### C4. "Two tests cannot fail" to "one assertion cannot fail" — **INCORRECT. Both still compare a mean against a sum**

This correction went the wrong way, and it is the one that matters, because the
surviving text now understates the defect it was correcting.

`reports/STAGE-09-RECOMMENDATION.md:765-767` says: "The assertion at
`test_s09_e3_control_competence.py:185-189` does compare `_mean(...)` against the sum,
and **the one at `:236` compares a mean against a mean**, so the earlier claim that
both cannot fail is half wrong."

That is false. Line 235-236 reads:

```python
assert _mean(_arm(step, "agenda")) \
    <= step["best_rule_held_out_reduction"] + 1e-12, (
```

The right-hand side is `step["best_rule_held_out_reduction"]`, which I traced to its
origin: `s09_e3_selection.py:293-294` copies it from
`competence["best_held_out_reduction"]`, which is `agenda_policy.py:505` returning
`best`, which is `agenda_policy.py:480` `max(by_rule.values())` over
`_score_constant_rules`, which is a **sum**. Same right-hand side as line 189. Both
assertions compare a **mean against a sum**.

My table above shows both evaluate true at every budget, and shows why that is not
coverage. At budget 14 `best_rule_held_out_reduction` is `0.000000`, so line 186's
`if best <= 0.0: continue` skips the assertion at 189 entirely, and the guard is absent
at precisely the budget where the agenda's only win sits. At every other budget the sum
is 3x the corresponding mean, so the comparison is satisfied by roughly a factor of
three of slack rather than by the property it names.

The two tests **do** pass. `uv run pytest tests/test_s09_e3_control_competence.py`
gives `8 passed in 94.84s (exit code 0)`, run under the required environment. So the
file is green, which is the point: the guards are green and cannot detect the defect
they are named for.

The heading at `:747` still reads "two of its assertions cannot fail" and the closing
sentence at `:772-773` still reads "**two tests this batch were built to prove a defect
fixed, and neither can fail.**" The body and the heading now contradict each other, and
the previous review's objection at
`reports/workstreams/w5-final-review.md:139-141` was the opposite of what the correction
says. The previous reviewer was wrong that `:236` is the `handicapped_at` assertion; the
correction is wrong that `:236` compares a mean against a mean. **Both are mean against
sum.**

**Is the remaining unfailable assertion material to E3's negative?** Yes, and it is
worse than one. Both are. The negative rests on the crossover at 20 and the arm counts,
both of which are read against `best_rule_held_out_reduction`. A yardstick on the wrong
scale inflates the oracle in every comparison, so the "oracle still ahead" claim at 1.67x
is directionally right but the tests do not independently establish it, and the budget-14
skip means the one budget where the guard would have bitten is the one budget where it
is skipped. The statement at `:767-768`, "the ceiling and handicap that E3's negative
rests on are not machine-guarded today", is correct and is if anything understated.

### C5. `w4-leakage.md` on HEAD — **CORRECT**

Present at `fc757e4`. `git ls-tree fc757e4 -- reports/workstreams/w4-leakage.md` returns
blob `551dba56`, and `git status --short` on that path is clean, so it is tracked at
HEAD and unmodified.

The restated numbers match what the recommendation cites. Comparing
`reports/workstreams/w4-leakage.md:43-45` and `:52-53` against
`STAGE-09-RECOMMENDATION.md:93-98` and `:109-111`: the cohort table matches row for row
(`0.5017/+0.3483/+11.38`, `0.5208/+0.3750/+13.17`, `0.5292/+0.3850/+14.67`), and the
cross-split control matches (`+0.2675` at `z = +8.38`, zero overlap). The factorial
table at `w4-leakage.md:32` matches `:56-61`. No discrepancy.

**Is the document honest about the three absent JSONs?** Honest, and the disclosure is
better than the recommendation's. `w4-leakage.md:90-91` opens with "The three cited JSON
artifacts are gone." I confirmed all three are absent from the tree:
`w4-leakage.json`, `w4-leakage-factorial.json`, `w4-leakage-controls.json`.

It does **not** overstate re-derivability, but it is one step short of honest. The
"Reproducing this" section (`:93-97`) describes the three re-derivations by intent and
expected value, and says "the same three offline scripts the lane used" without naming
one. No script matching `*w4*leakage*`, `*e4_leakage*`, or `*blind_sequence*` exists in
the tree. So a reader who follows `:90-97` has a target value and a procedure but no
command to run. The claim is checkable in principle and not yet checkable in practice.

The recommendation, by contrast, cites all three files as bare artifact names at
`:51`, `:85`, and `:120` with no statement that they are absent. A reader of the
recommendation alone will look for three files that are not there. That is a
disclosure gap in the recommendation, not in the lane record.

---

## 2. Does B1 need re-arguing on the census alone?

**No, and it is already re-argued.** `STAGE-09-RECOMMENDATION.md:284-286` now frames the
two reasons as "make the null uninformative about experience", and the first is struck
through as RETRACTED with its own reason withdrawn (`:298`, "the bottleneck ordering
below no longer rests on it"). The ordering is not resting on it.

The census alone carries B1, and it carries it well. From
`reports/evidence/invr1e2contrastr2/report.json` `$.reachability_census`:
`max_attainable_positive_delta: 0.0`, `max_attainable_negative_delta: 0.538462`, a
twelve-cell grid, and `default_decision: ["seed-sw-ddmin", 8]`. The rows show
`seed-sw-ddmin@8` at `normalized_reduction: 0.7` against a `ceiling: 0.7` on target
`ad01-w0-within-sw-00`, so the zero-information default is at the ceiling. The
instrument's own `reading` field says it plainly: "The negative side is not bounded this
way, so a negative delta is the one the instrument can produce."

That is a structural argument, not a measurement of the effect, and it does not depend
on the retracted mechanism. B1 is sound as written. The census is the stronger of the
two reasons anyway, since it bounds what any future run of this panel can produce.

One thing B1 should be explicit about, because it is a live defect rather than a
hypothetical: the census shows `ddmin@8` is optimal, and `_reduction_of`/`_decision_of`
are mis-wired on the `reading_row` path. Those are the same wiring family. B1's
"wire the repaired leg to the report" at `:307-309` is the right action, and `:296-297`
already discloses the defect may still exist. No re-arguing needed.

## 3. Is the E3 defect still real in source once the ratio is withdrawn?

**Yes. Real, live, consumed, and not handled by the ladder.** See C3 above for the
execution output.

The distinction worth naming, because it is the crux of the question: withdrawing the
ratio does not withdraw the defect, because the ratio was a *symptom* of the defect
being read on the wrong scale. The defect is that
`agenda_policy._score_constant_rules` returns a sum
(`experiments/ad01/agenda_policy.py:435-440`) while every arm row reports a mean
(`experiments/ad01/s09_e3_selection.py:283`), and the sum is then stored under a field
named `best_rule_held_out_reduction`
(`experiments/ad01/s09_e3_selection.py:293-294`) and consumed as a yardstick at
`agenda_policy.py:480` and in two tests.

It is not a presentation mismatch, on three counts. The wrong value is compared, not
just reported: `gap_to_best` and `rules_beating_it` both derive from it. The
`vacuous == [8, 14]` guard at `:196` depends on the sum being `0.0` where the mean
would also be `0.0`, so it survives by luck, not by design. And at budget 14 the sum
is `0.000000` while the mean is `0.083721`, so the field says "no constant can qualify
anything" at the one budget where the agenda actually wins.

The documents are right that the defect is live and right that the corrected margin is
1.67x. They are wrong that only one test fails to guard it.

## 4. Surviving false, overstated or stale claims

Swept both handback documents, plus the ledger and the roadmap. One real instance, in
the ledger, which is the document the task flagged as not yet updated. One inherited
instance in evidence prose. Two internal inconsistencies in the ledger's E3 cell.

### 4.1 The third instance. `reports/PROJECT-LEDGER.md:44` re-asserts the retracted ratio

This is the failure mode the previous review caught twice. The ledger was updated at
`00358a4`, which is **newer** than both corrections, and it re-asserts the ratio as a
recomputed result:

> "Recomputed across all 196 rules with fresh instances, **the ratio is exactly 3.0 at
> every non-zero budget.**"

`STAGE-09-RECOMMENDATION.md:753-755` and `docs/design/REFINEMENT-ROADMAP.md:28` both
now say it is an identity, not a result. The ledger says the opposite, in the present
tense, as a finding. It is the only place in the corpus that still does.

Ordering, confirmed:

```
00358a4  2026-09-30 05:46:00 -0400  Bring the project ledger and roadmap to the E2 and E3 results
fc757e4  2026-09-30 05:43:53 -0400  Land the E4 leakage record...
d30bbf2  2026-09-30 05:42:48 -0400  Retract the coordinator's E2 arithmetic claim, and three more
d30bbf2 ancestor of 00358a4?  YES
```

So the ledger was written **after** the retraction, and reintroduced the retracted
claim while the recommendation and roadmap, written in the same commit, had it right.
This is the exact shape the previous review flagged: a claim that was true at an earlier
commit and is not now, or rather a correction that was made and then not propagated to
the one document that carries the same sentence.

The ledger's **line 62** is correct. It carries the E2 retraction in full and in the
present tense, and it names `_reduction_of` reading `NORMALIZED_REDUCTION`. So the
ledger is internally consistent on E2 and inconsistent on E3. That asymmetry is itself
the tell.

### 4.2 `reports/PROJECT-LEDGER.md:44` cites two different values for the same quantity

The same cell names the agenda's mean at budget 20 as both `0.156883` and `0.083721`.
It uses `0.156883` for the 2.7x ratio and `0.083721` for the corrected 1.67x margin.

I traced both. `0.1568834941383961` lives at
`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json` under
`/committed_ladder/ladder[2]/arms[0]/held_out_reduction_mean`, and also under
`/regenerated_shared/...` and `/shared_versus_fresh/cells[16]/shared`. The
`committed_ladder` and `regenerated_shared` blocks are the **withdrawn shared-instance**
substrate, which `PROJECT-LEDGER.md:46` itself flags as a retracted path.

My live recompute of `e3.qualified_ladder(worlds=(0,1,2))` gives `0.083721` at budget
20, matching the fresh path and matching `STAGE-09-COMPLETION-MATRIX.md:183`. So the
ledger's 2.7x is a fresh **numerator** (`0.419328`) over a shared-path **denominator**
(`0.156883`). The 1.67x is fresh over fresh and is the correct figure. The 2.7x is not
merely an artifact of the sum/mean scale; it also mixes substrates. Both need to go.

### 4.3 `reports/evidence/invr1e2contrast/RESULT.md:110-118` and `:425-427` — correct, and understated

This is not a false claim. It describes the `reading_row` defect, and I confirmed that
defect is live (§1, C1). If anything it is **under**-claimed: it says the estimator
reads two keys the row does not write, and that is exactly right.

The one thing to fix is scope. `RESULT.md:427` says the defect "makes **that
instrument's** contrast 0.0 by arithmetic rather than by measurement", where "that
instrument" is `invr1e2contrast` (r1). Confirmed: r1's `report.json` has
`deltas: [0.0]`, a single-element list. So the sentence is true for r1 and false for r2.
It sits in a file scoped to r1 and it is not cross-referenced, so a reader who has just
read the retraction could carry it forward. A one-clause note pointing at the r2
retraction would close it.

This is low severity. It is a historical evidence record, correctly scoped by its own
directory.

### 4.4 Things I checked and found sound

Stated so the coordinator knows the sweep was not partial.

The E2 delta figures at `STAGE-09-RECOMMENDATION.md:279-280` and
`PROJECT-LEDGER.md:62` match the artifact exactly (`-0.0909`, `[0.0, 0.0, -0.2727]`,
`z -1.225`). The `within-sw-02` decision-divergence claim is confirmed in the
artifact's `decisions` block: `differs: true`, treatment `seed-sw-greedy`, control
`seed-sw-ddmin`, at `ad01-w0-within-sw-02` only.

The E1 tally at `:422` is right. `RESULTS.md:50-51` tabulates `invalid-program 3 /
transport-loss 9` at both caps, and `campaign-manifest.json:27` confirms
`max_output_tokens: 2048`, so r3 did run at the budget the correction names.

The E4 numbers cited in the recommendation match `w4-leakage.md` exactly (§1, C5).

The 1728-reducer-outcomes claim at `STAGE-09-RECOMMENDATION.md:315-317` and
`STAGE-09-COMPLETION-MATRIX.md:97` is outside the five corrections and I did not
independently re-derive it. **Undetermined**, not verified and not contradicted.

`docs/design/REFINEMENT-ROADMAP.md:28` is current on all three of E1's output budget,
E2's census, and E3's ratio identity. It is the document that got the ratio right. The
ledger is the one that did not.

---

## 5. Ship or not ship

**No. Do not ship as-is.** Four changes, all mechanical, none of them structural.

The batch's architecture is sound and the previous review said so. Every remaining defect
is a sentence in a document that has the right answer next to the wrong one. None of
these require re-measuring anything. All of them are the failure class the previous
review already named, which is why I am naming them rather than shipping around them.

### The smallest change set

**1. `reports/PROJECT-LEDGER.md:44` — remove the re-asserted ratio, and the mixed-substrate
2.7x.** Delete the sentence "Recomputed across all 196 rules with fresh instances, the
ratio is exactly 3.0 at every non-zero budget." Replace the 2.7x derivation with the
fresh-over-fresh 1.67x only, since `0.156883` is the withdrawn shared path and the cell
already has the correct `0.139776 / 0.083721`. This is the blocking item: it is a
retracted claim currently stated as a finding, in the project's own status document.

**2. `reports/STAGE-09-RECOMMENDATION.md:765-767` and `:747`, `:772-773` — fix the E3
test correction, which went the wrong way.** Replace "the one at `:236` compares a mean
against a mean" with the fact that `:236` compares a mean against the same sum, via
`best_rule_held_out_reduction` (`s09_e3_selection.py:293-294` from
`agenda_policy.py:505` from `:480` from `_score_constant_rules`). The heading and the
closing sentence already say "two"; restore the body to agree. Also worth adding one
sentence, because it is the sharpest form of the finding: at budget 14 the sum is
`0.000000` while the mean is `0.083721`, so line 186's `continue` skips the guard at the
one budget where the agenda wins.

**3. `reports/STAGE-09-RECOMMENDATION.md:733-735` — correct the E1 probe reading.** Drop
"a different one returns 200 at 2048" (no such result exists) and the "502s at the
protocol's own 2048" for the campaign arm (that one is a timeout, not a 502). The
defensible claim is: the route returns 200 at 16 and 256 and fails at 2048, r3 ran at
2048, so the budget is the exposure. Drop the "not the prompt" clause, which the probe
cannot support because it never crosses the two variables.

**4. `reports/STAGE-09-RECOMMENDATION.md:51`, `:85`, `:120` — disclose that the three E4
JSONs are not on disk.** `w4-leakage.md:90` already says so; the recommendation cites
the three files as if they were present. One clause fixes it. Naming the re-derivation
scripts in `w4-leakage.md:93-97` would be better still, and would need the scripts
recovered, which is outside this handback.

### Why not ship with only item 1

Item 1 is the hard blocker. A status document that re-asserts a retracted claim as a
result is the exact defect this batch exists to eliminate, and the ledger is the
document a reader trusts first.

Items 2 and 3 are not optional in the same way, and I want to be plain about why. Item 2
is a correction that made the document less accurate than the sentence it replaced. The
previous review's error was real, but the fix over-corrected, and the result is a
document whose heading, whose closing sentence, and whose body now disagree with each
other about how many assertions cannot fail. Item 3 is a claim that cites an artifact and
misreads it in a way I demonstrated from the artifact's own data.

I could ship items 2 through 4 as follow-ups. I would not, because the previous review's
verdict was that the handback did not survive contact with the evidence, and shipping a
document where two of the five corrections introduce a new inaccuracy and a third
contradicts its own cited artifact is the same outcome by a different route.

### What is genuinely sound

Stating this plainly, because it is the majority of the work and it deserves to be said.

The E2 retraction is correct and well-executed. It is struck through rather than
quietly edited, it names the false mechanism, it names the coordinator's evidence error
("a grep for key names across a function body that returned matches from a neighbouring
docstring"), and it separates the withdrawn claim from the still-live defect. That is
better disclosure discipline than most finished work.

The E3 ratio correction is correct and the identity is stated in exactly the right terms.

The census-based B1 ordering is sound and needs no re-arguing.

The `w4-leakage` record is accurate, matches what the recommendation cites, and is more
candid about its own artifact gap than the document that cites it.

The E4 evidence, the E1 tally, the 1728-reducer defect's disclosure, and the honest
negatives are all intact. The three untrue-until-retracted claims the previous review
found are all genuinely fixed in both handback documents. The corrections were mostly
right. Items 2 and 3 are the exceptions, and both are single sentences.

After those four changes I would ship it. The underlying work is sound; what is left is
four sentences.
