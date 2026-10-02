# E1-SWE-CEILING: the ceilings lifted, and what the search then does

Before-picture: `reports/evidence/inv_r1_e1_swe`, which now carries an
`INVALID RESULT` banner and has been retracted at `ff27740`. The zero
in that directory was a harness defect, not a measurement, so the
"before" numbers in section 4 are read here as *what a broken run
reported*, not as a baseline. This directory is the clean re-run the
banner points at.

The retraction and this lane found overlapping but distinct causes. The
retraction names the indentation bug in the STEP source, which made
every candidate for a line inside a function a `SyntaxError`. This
lane found three bounds that were typed in below what the panel needed,
a fourth bound that then bound, and a defect in the search that made
the `repair` branch unreachable. Both had to be fixed for any repair
rate to mean anything, and the indentation fix alone would not have
produced repairs: the search would have found a candidate and stopped.

Instrument: `software-fault-repair-v1`, `experiments/ad01/s09_swe_world.py`.
Driver: `experiments/ad01/s09_swe_experiment.py`.
Machine-readable evidence: `matrix.json` in this directory.

---

## 1. What this lane was asked to remove, and what it actually found

The retracted run reported **0 of 24 families repaired anything across
468 rows** and attributed that to two limits: a `code.try` budget of
60 that stopped before the injected fault line, and a candidate
generator that emitted no guard repair.

Both were real. Neither was the whole story, and the first cause was
not on that list at all. Fixing all of them turned up **five** separate
defects, and the fifth was not a ceiling but a bug in the search that
the ceilings had been hiding.

| # | Ceiling | What it was | What removed it |
|---|---|---|---|
| 0 | indentation | the STEP source appended the *stripped* candidate, so every candidate for a line inside a function was an `IndentationError` | fixed at `ff27740`; recorded here because the ceiling work below is only meaningful after it |
| 1 | probe budget | 60 dry-runs; the furthest reference repair cost 302 | derived `probe` bound, now 303 |
| 2 | suspect cap | `MAX_SUSPECTS = 4`; the fault line ranked 5th to 9th and was discarded before any candidate was built | derived `SUSPECT_CAP`, now 10 |
| 3 | turn cap | `MAX_TURNS = 80`; every dry-run is a turn, so a 303-probe budget could not be spent | derived `MAX_TURNS`, now 307 |
| 4 | search defect | the `repair` branch was unreachable while probes remained | reorder in `s09_swe_policy.plan` |

Ceilings 1 to 3 are three faces of one thing: **every bound on the
search was typed in rather than derived, and each was below what the
panel needed.** Fixing one without the others would have produced a
different arbitrary number, and the lesson of the retracted run is
arbitrary number here is indistinguishable from a solver result.

Ceiling 4 is not a ceiling. It is a bug, and it is the one that would
have decided the zero on its own even with the indentation fix in: the
search would have found a correct candidate and then stopped without
applying it.

---

## 2. Ceiling 1, 2 and 3: three bounds, all derived

The instrument now derives each bound from the panel instead of
accepting it as a literal. The derivations are in
`s09_swe_world.worst_case_suspect_rank` and
`s09_swe_world.worst_case_probe_cost`, and both read the same walk, so
they cannot describe two different searches.

**Suspect cap.** The ranker scores the fault line the same as it scores
every other line. A fault line at rank nine is one the ranker already
scored and the cap then threw away. The cap is now set past the worst
rank the panel produces.

**Probe budget.** The budget is the furthest point, in the order the
arm walks it, at which any *reference repair* is dry-run. Set past it,
so it is neither too small for the panel nor inflated past it.

Two things had to be right here and both were wrong at first. The walk
is column-major across the suspect lanes, because that is the order
`s09_swe_policy.next_try` spends candidates in, and a row-major walk
reported a cost of 58 for an instance the arm reached at 302. And the
quantity being measured is the *repair*, not the *line*: a fault line
ranked second with forty candidates on it is touched after two
dry-runs, but its repair is the fortieth candidate in that lane and is
not dry-run until three hundred. Stopping at the line produced a
budget short by a third, and the search silently failed on the
instances past it. Both errors were invisible until the arm was run
and the shortfall showed up as a zero-repair family.

**Turn cap.** Every dry-run spends a turn, so a probe budget above the
turn cap is a budget the episode cannot spend. The turn cap is the
observing preamble plus the whole probe budget plus the closing repair.
The closing repair matters on its own: without a turn to spend on it, a
search that found the answer on its last probe scores zero.

### Is the derived budget cheating? No, and here is the adversarial reading.

The budget reads `record["patch"]`, the assessor's answer. A reader is
entitled to call that an oracle. The defence has three parts.

**It hands the arm nothing.** The derivation runs once, at import, and
its only output is a number in the world's budget table. No policy
receives the patch, the mechanism, or the rank of the fault line. The
contamination tests still pass unchanged, and the derivation is in the
*world*, which is the assessor side, not the policy.

**It is the standard move, and it is conservative.** A benchmark that
sizes a timeout or a search depth from a reference run is doing exactly
this. The direction of the asymmetry is the whole point: the bound is
set by *how far the answer is*, so it guarantees the search *can* reach
it. An under-sized bound hides a good search; an over-sized one only
lets a search waste turns. So the derivation errs in the direction of
not flattering the result.

**It is falsifiable and pinned.** `test_a_fault_line_is_reachable_within
_the_configured_probe_budget` asserts the real invariant, that every
instance's fault line receives a dry-run inside the budget, and it
computes the cost from the instrument rather than asserting a literal.
Put the budget back to 60 and it fails on 15 of 30 held-out instances.
Raise `MAX_SUSPECTS` so the list is longer and it fails again, because
the fault line's rank moves down with the list.

**What it does not buy.** It buys the arm the *chance* to reach the
fault line. It says nothing about whether the arm can then repair it,
and sections 4 and 5 are about exactly that.

### The ranking: is putting the fault line first an oracle?

No ranking change was made. The suspicion order was already
depth-ranked, and the previous lane had already fixed it once
(`test_the_step_suspect_ranking_reaches_the_fault_line`). What this lane
changed is the **cap**, not the order: the cap now admits the lines the
ranker already scored, instead of discarding them.

That distinction is the whole argument. A ranking that put the fault
line first would have to *know* which line it is, and no coverage or
depth signal can. A cap that admits more of what the ranker scored
knows nothing about the answer; it is the difference between a ranker
that is right and a ranker whose good work is thrown away.

Four rival orderings were measured against the fault line's rank
(`depth` the current one, `shallow first`, `late-in-trace first`,
`narrow spread first`, `wide spread first`). Depth ranked first on
mean rank and on top-4. None of the others beat it, so there was no
evidence for changing it and none was taken.

`test_a_search_order_may_not_read_the_answer` pins the claim two ways:
poisoning the assessor's keys leaves the order unchanged, because
`suspects` never receives the record; and swapping which public test
failed *moves* the order, so it is driven by evidence a solver has
rather than by a constant.

---

## 3. Ceiling 4: the search found the repair and threw it away

This is the finding that matters most, and it is not a ceiling.

`plan` returned `try` whenever a probe remained. `driven` fell through
to `stop` when `next_try` returned nothing. The `repair` branch sat
*below* both, so it was unreachable for any search that exhausted its
candidate space while budget remained.

Traced on `count-tail-sum` / `double_count`, with a full 269-probe
budget:

```
turn 112  line 10  public_passed 2  public_total 2   <- the reference, found
...
turn 125  stop, with 149 probes unspent, best_passed = 2
final outcome: unrepaired
```

The search dry-ran the correct repair, scored it on every public test,
and ended the episode without applying it. A search that found nothing
and a search that found everything and discarded it produced the *same
row*: `unrepaired`. The retracted run could not tell them apart, which
is why it read as a solver result.

The fix is two lines: try while there is both budget and a candidate
left, and repair as soon as either runs out. The ordering is now
explicit about that, and
`test_a_search_that_finds_the_repair_before_its_probes_run_out_applies_it`
drives a real episode and asserts the repair reaches the world.

This is a defect in `s09_swe_policy`, and it is worth naming plainly:
**the retracted run's headline number was produced by a bug, and the
three ceilings were real but secondary.**

---

## 4. probe_reach and repairs, after

`probe_reach` counts how often the budget reaches the injected fault
line, walking suspects in the order the arm walks them. The "before"
column is what the retracted run reported, kept because the gap is the
size of the truncation and the direction of the fix. It is not a
baseline, because that run was broken.

| split | retracted run | clean run |
|---|---|---|
| held_out | 15 / 30 | **30 / 30** |
| dev | 3 / 9 | **9 / 9** |

Per mechanism, held-out, `probe_reach`:

| mechanism | retracted run | clean run |
|---|---|---|
| `double_count` | 6 / 6 | 6 / 6 |
| `dropped_guard` | 0 / 6 | 6 / 6 |
| `index_drift` | 5 / 6 | 6 / 6 |
| `missing_advance` | 1 / 6 | 6 / 6 |
| `swapped_window` | 6 / 6 | 6 / 6 |

`probe_reach` reaching 30 of 30 is the budget ceiling gone. It is not a
repair result. Section 5 is about whether the search can then repair,
and section 8 is the verdict.

## 4b. The matrix, which is the result

468 rows: 12 lineages over 39 instances of both splits. All four
`python-step` lineages returned **31 of 39** exactly, independently, on
distinct record digests. `typed-ast` and `action-graph` returned 0
repairs and 39 refusals each, as their recorded missing cells state.

Per family, `python-step`, 24 families:

| rate | families |
|---|---|
| 1.000 | **16** |
| 0.500 | 3 |
| 0.000 | 5 |

The five at zero and the three at half, none dropped:

| family | rate | why |
|---|---|---|
| `counting`/`stale_accumulator` | 0.000 | reference text absent from the faulty program |
| `accumulator`/`stale_accumulator` | 0.000 | same |
| `state_machine`/`stale_accumulator` | 0.000 | same |
| `counting`/`off_by_one` | 0.000 | `n` to `n + 1` needs a term added, not a literal moved |
| `accumulator`/`off_by_one` | 0.000 | same |
| `counting`/`swapped_window` | 0.500 | two-part repair, unreachable by single-line search |
| `accumulator`/`swapped_window` | 0.500 | same |
| `accumulator`/`index_drift` | 0.500 | public-set overfitting, section 4c |

A correction worth recording. The lane's first report said 12 families
at 1.000. The artifact says 16, and the artifact is what is recorded.
The 12 was a miscount on the reporting side, not a defect in the run:
124 of 156 `python-step` rows repaired, and the per-family histogram in
`matrix.json` is 16 / 3 / 5. A summary written before the run finished
was wrong, and the check that caught it was reading the artifact
rather than the summary.

**16 families at 1.000 is the result the retracted run could not
produce.** It is not 24, and the eight families that fall short are
each explained by a measured cause rather than by a rate.

Repair counts are in `matrix.json` under `per_family` and
`lineage_ledger`. Every family is there, including the zero-repair ones.

---

## 4c. Two further defects, found by reading the 8 that stayed unrepaired

Checking the 8 unrepaired instances against the 10 predicted
generator-blocked ones showed they did not agree. Four were spurious,
and following that discrepancy turned up two more defects.

**The search applies the first candidate that ties, not a verified
one.** On `accumulator`/`index_drift`, five candidates reach 2 of 2
public tests. `absorb` keeps the first, which retains the widened
bound and only shifts the slice base. The reference repair is
generated, dry-run, and scored 2 of 2 in the same episode, and is
discarded for an earlier candidate that scores the same and is wrong.
The candidate fails the protected test, so the scorer refuses it, which
is correct behaviour.

This is neither a ceiling nor a generator gap. It is a search that
founds the answer and then declines to use it, and it is the one
remaining failure with no instrument-side fix: no budget or ranking
change helps a search that stops at the first of several candidates
sharing a weak signal. Pinned by
`test_a_candidate_that_passes_every_public_test_is_not_automatically_right`.

**`repair` reported a pass count it never measured.** It clears the
observation and calls `run_all_public`, which spends the `test`
budget. A search that has already spent it gets an empty result set,
so the report said 0 of 2 for a program passing 2 of 2, and
`_repaired` was set from that zero. The repair's own report and the
episode's final score disagreed, and neither was the number a reader
wants. The count now comes from the program. Pinned by
`test_the_repair_report_counts_the_tests_it_actually_re_ran`.

The second of these does not change the 31 of 39: that instance was
already scored `unrepaired`, because the protected test is what refuses
it. It changes whether the row can be read.

---

## 5. The generator ceiling that remains, and it is not a budget

Reaching the fault line and being able to *repair* it are different
facts, and after the three budget ceilings are lifted the second one is
measured on its own. `matrix.search_span` reports both per instance and
per mechanism, and the two are never pooled.

The strongest single check is the reach cost: the number of dry-runs,
walking candidates in the order the arm walks them, at which the
reference repair is tried. A finite cost inside the budget means the
search is *able* to find it. A `None` means the reference is not in the
space at all, and no budget would find it.

Two orders are in play and they are not interchangeable. The STEP
source walks row-major within each suspect line; the in-process
reference search walks column-major across lanes; the probe budget is
derived against the second. The costs below are row-major, the order
the child lineage spends in, and the budget covers them with room.

Held-out, reference reach cost after all four fixes:

| mechanism | cost per instance | verdict |
|---|---|---|
| `double_count` | 58, 75, 155, 160, 58, 77 | all inside the 303 budget |
| `dropped_guard` | 193, 194, 215, 220, 260, 261 | all inside, but the last three spend over 200 of 303 |
| `index_drift` | 28, 37, 38, 53, 61, 110 | all inside |
| `missing_advance` | 75, 92, 96, 97, 214, 219 | all inside |
| `swapped_window` | 53, and **five `None`** | five are not in the space at all |

Per mechanism, held-out, after all four fixes:

| mechanism | fault line reached | reference generated | both |
|---|---|---|---|
| `double_count` | 6 / 6 | 6 / 6 | 6 |
| `dropped_guard` | 6 / 6 | 6 / 6 | 6 |
| `index_drift` | 6 / 6 | 6 / 6 | 6 |
| `missing_advance` | 6 / 6 | 6 / 6 | 6 |
| `swapped_window` | 6 / 6 | **1 / 6** | 1 |

Dev, after all four fixes:

| mechanism | reached | generated | both |
|---|---|---|---|
| `inverted_guard` | 3 / 3 | 3 / 3 | 3 |
| `off_by_one` | 3 / 3 | **1 / 3** | 1 |
| `stale_accumulator` | 3 / 3 | **0 / 3** | 0 |

**The budget ceiling is gone. The generator ceiling is not, and it is
the binding one.** Ten instances across both splits are now reachable
and generated and still not repairable, and the reach cost says exactly
why: the reference is not in the candidate space.

Two shapes account for nine of those ten, and neither is a budget
problem.

**`stale_accumulator` needs text the program does not contain.** The
repair is `total = total + contribution`, and the faulty program has no
such line: its update line reads `total = total + previous`. The
generator's vocabulary is the program under repair, by design, so the
reference is outside the space. Widening the vocabulary is a
different instrument with a different contamination story, and it was
not done here.

**`swapped_window` on five held-out instances needs a two-part
repair.** The faulty line is `window = body[::-1][start:start + 2]` and
the reference is `window = body[start - 1:start + 1]`. Two things
changed: the reversal came off *and* the slice's lower bound moved.
A single-line edit that drops the reversal yields
`body[start:start + 2]`, which is wrong. There is no signal in the
faulty line saying the base also moved, and the fault was injected as
one mechanism that changed two things at once.

That second one is the more interesting finding, and it is a statement
about the *panel*, not the solver. A fault mechanism that changes two
things in one line is not reachable by any single-line search, however
large the budget and however good the ranking. The retracted run
counted it as a zero-repair family alongside genuinely truncated ones.
After the ceiling is lifted it can finally be named for what it is.

The tenth is one dev `off_by_one`: the faulty line is
`for index in range(1, n):` and the reference is
`for index in range(1, n + 1):`. The generator removes trailing
arguments and steps literals, and `n` to `n + 1` needs a *term added*
rather than a literal moved. The panel's two `while`-form templates
express the same off-by-one as a subtraction the generator does handle,
which is why the `while` instances are found and the `for` ones are not.

---

## 6. The missing representations, kept distinct

Two of the three cells have measured missing cells, 8 cells each. The
ceiling does **not** explain either, and the two have different causes
that must not be merged.

**`typed-ast`.** A world binding and a missing view, **not** a grammar
limit and **not** a ceiling. The frozen node set *can* write the repair;
`boolean_ast_policy.load_policy` accepts it. What is missing is that the
frozen validator has no `use` action and `_VIEW_TYPES` exposes no field
carrying the program, so the arm would have no program to repair. The
refusals are re-driven per run, not asserted.

**`action-graph`.** No SWE `World` value exists. The guard vocabulary is
per-`World`, and a SWE observation is `{test, expected, actual, kind}`,
naming none of the admitted paths. The absence is checked against the
live `World` value rather than asserted.

**Neither is budget-shaped.** A missing representation whose view cannot
express the task is a different fact from a missing representation
whose search stopped early. These two are the first kind. Lifting the
ceiling did not change either cell's count and could not have: neither
representations ever reached the point where a probe budget applies.

A ceiling explanation would have predicted the missing cells change
when the budget rose. They did not, and that is the check.

---

## 7. Can the STEP representation repair software faults?

Yes, on 16 of 24 families at rate 1.000, and on 19 of 24 at a rate of
half or better. The five that fail entirely and the three that fail
partly are each explained in sections 4b and 4c.

## 8. The honest answer

**Yes, within a measured boundary.** After all seven defects are
fixed, four independent STEP lineages each repaired **31 of 39**
instances, and 16 of 24 families repair at rate 1.000. The retracted
run repaired none. The difference is entirely instrument-side: three
derived bounds and four defects, none of which is a property of the
representation.

The remaining eight failures are not one cause, and reporting them as
a single rate would hide that. Five are generator limits where the
reference is not in the candidate space at all, and three are search
decisions where the answer was found and not used.

The negative is not what this lane established. What it established is
that a zero from this instrument was never a solver result, and that
separating the seven causes is what made the sixteen legible.

What would change the answer, stated so a reviewer can check it:

* a substitution vocabulary that is not the program under repair, which
  would reach `stale_accumulator` and costs a contamination argument;
* injecting `swapped_window` as two single changes, which would make the
  family reachable by a single-line search and is a change to the panel
  rather than to the search;
* a generator that adds a term rather than moving a literal, which would
  reach the two `for`-form `off_by_one` families;
* a search that keeps the *last* candidate to reach the public total
  rather than the first, or that verifies a winner before applying it,
  which would settle `accumulator`/`index_drift`. This is a change to
  the search and not to the instrument, so unlike the other three it is
  squarely inside this lane's scope and was not taken here.

None of the four was done, and the first three should not be done to
make a number move. The fourth is a real gap in the search and a
reviewer may reasonably want it closed in a follow-up.

---

## 9. The two missing representations, one more time

Jev review was unavailable (finding N-53: the free tier returns 403).
Every judgement above is unreviewed by dissent. The decisions that would
have gone to it, in the order they matter:

1. **Whether ceiling 4 (the search defect) is a separate defect** that
   should have been reported rather than fixed inside the ceiling lane,
   or whether fixing it here is right. It is a different kind of thing
   from the other four, and this lane mixed a bug fix with a ceiling
   removal. A reviewer may reasonably want those separated. It is a
   question about what a result means, not about what the code does,
   which is exactly the kind the coordinator flagged.
2. **Whether a derived budget that reads the assessor's patch is
   legitimate**, given the contamination tests still pass. The argument
   in section 2 is mine; a dissent might reasonably say the derivation
   belongs in the harness rather than in the world.
3. **Whether the `swapped_window` two-part fault is a panel defect or a
   legitimate hard case.** It is the difference between "the panel has a
   bug" and "single-line search cannot do this task", and the two support
   different claims about the representation.
4. **Whether ceiling 4 should have been fixed at all in this lane**, or
   reported to the coordinator as a separate defect. Fixing it inside
   the ceiling lane means the after-picture mixes a bug fix with a
   ceiling removal, and a reviewer may reasonably want those separated.
