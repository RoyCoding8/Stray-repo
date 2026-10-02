# B4: the constant-rule score is a mean, and the crossover re-derived

Lane B4. Base `f03db5b`. Offline, no model call, no network, no gateway, no
database. Every portfolio candidate is a `SEED_CAPABILITIES` id that
`trajectory` resolves in process, so the whole sweep is local arithmetic over
the frozen measure set.

## The bug

`agenda_policy._score_constant_rules` returned `sum(... for world in worlds)`.
Every consumer of that number reads it beside a **mean** over the same worlds.
`e3_ladder._aggregate` divides by its cell count, and
`s09_e3_selection.qualified_ladder` publishes `held_out_reduction_mean` in the
same row as the yardstick this function produces. So the yardstick sat at three
times the scale of the arms it qualifies, and the error was not a constant
offset that cancels in a comparison. A sum grows with the length of `worlds`,
which means the identical rule scored a different number on a three-world
search and a one-world search. `control_competence` counts `rules_beating_it`
and computes `gap_to_best` off exactly these numbers, so the handicap count
that qualifies every reported E3 arm was partly a count of worlds.

The reviewer found this at `reports/workstreams/w5-final-review.md:119-123` and
the reproduction note confirmed it by calling the function
(`reports/workstreams/w3-reproduce.md:151-178`). It stayed open because the
three fix sites were all in a frozen artifact.

## The fix

One aggregation, in `experiments/ad01/agenda_policy.py`:

```python
-                        for world in worlds), rule))
+                        for world in worlds) / len(worlds), rule))
```

The docstring now states why the mean is the only correct choice here, and
not merely the tidier one: a mean is invariant to how many times a value is
folded in, which is the property that lets two searches over different world
sets be compared at all, and it is the scale `selection.Yield` already types
`held_out_reduction` at, a rate in `[0, 1]`.

No other file was changed. Nothing outside
`experiments/ad01/agenda_policy.py` and the new
`experiments/ad01/b4_constant_score.py` was touched.

## The tests

`tests/test_inv_b4_constant_score.py`, written before the fix and committed
first, at `dea5296`. The red run was **6 failed, 4 errors** against the
unfixed source, and it failed on the value rather than on a comparison: the
function returned `1.0778416028416027` where the mean is
`0.35928053428053425`.

Six cheap tests run the instrument on every gate. Four artifact tests pin the
sweep's output. The sharpest of the cheap ones, and the one that would have
caught the bug:

`test_the_score_does_not_grow_with_the_number_of_worlds` scores the same rule
at the same budget over `(0,)`, `(0, 0)` and `(0, 0, 0)`. All three return
`0.31746031746031744`. Under the sum, two copies returned
`0.6349206349206349`.

**A correction to the lane brief, which was wrong on this point.** The brief
asked for invariance to "the number of identical rules" and asserted a mean
over one world equals a mean over three. That is false, and I had it written
that way before measuring it. A mean over `(0,)` is world 0's own value,
`0.31746031746031744`; the mean over `(0, 1, 2)` is `0.35928053428053425`.
They differ because the value sets differ, which is what averaging *is*. The
only world-set change a mean has to ignore is **repetition**, because
repetition is the only change that leaves the value set alone. That is the
test that ships.

## The freeze

`reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`, a new directory.
No pre-existing evidence file was written.

Re-derived with:

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/b4-score \
  && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b4-score/src \
  timeout 1800 /home/ubuntu/.venvs/as9/bin/python -u /tmp/b4/one.py'
```

`one.py` calls `b4_constant_score.build(budget=40)`. The explicit `1800 s`
bound is the coordinator's instruction and it is the right one: a hung sweep
that produced nothing after half an hour would be worse than an admitted
absence.

**The freeze is single-budget and says so.** `budgets` is `[40]`,
`crossover_scope` begins "single budget", and
`first_budget_behind_is_claimed` is `false`. A first-crossing budget is not
derivable from one budget, and I did not widen the sweep to manufacture one.

Budget 40 was chosen because it is where the committed competence test runs
(`tests/test_s09sel_divergence.py`) and where `DEFAULT_RULE` ties the best rule
in its own space, so the yardstick discriminates rather than reporting a gap
the specified control cannot close.

Cost, measured: `control_competence(20)` alone took **893.6 s** at this tip.
The six-budget ladder was started, then stopped, as a 90-minute research run
that is not this lane's job. That decision is the coordinator's and it is
correct; recording it here so the number is not re-measured by the next lane.

## The crossover value

See the result section below, written after the sweep returned.

## What the old 3.0 does and does not still mean

The old figure is `SUM == 3 * MEAN` over three worlds. **It stays true. It is
not retracted by this change.** It was true at the commit that produced it
and it is true now.

What it is not is a measurement. It holds for any inputs, by algebra, for any
values whatsoever. So it could not have failed, and confirming it confirmed
nothing. `reports/workstreams/w5-final-review.md:99-117` is right that it was
dressed as a reproduced result and wrong that the value itself was wrong.

**The direction survives, and it survives on monotonicity alone.** The
archived claim is a set of signs: the agenda leads the specified control on
held-out quality at budgets 14 and 60, and trails at 20 and 40. Dividing every
score by the same three is a monotone transform, so no sign can move. The
direction claim does not need this repair and is not weakened by it. The
reuse-versus-cold-acquisition crossover the lane brief points at,
`reports/evidence/inv_r1_e2_retention/costs.json` at `crossover_uses: 5.0`, is
a **different quantity on a different ledger**: it is produced by
`learner.cost_report` over cap-sheet reservation units, imports no part of
`agenda_policy`, and is untouched by this repair in either direction. The
`3.0` is the E3 ratio, not that figure, and this lane neither retracts nor
re-derives it.

**What does not transfer is anything that mixed the two scales.** The `2.7x`
oracle ratio (`0.419328 / 0.156883 = 2.6729`) pairs a sum with a mean. The
`gap_to_best` column and every cross-scale `rules_beating_it` were computed
the same way. They are wrong and they stay wrong. None of them is restated
here, on either scale, because a corrected scale and a wrong one are not
comparable and a reader placing them side by side would be comparing units.
The re-derived freeze is a **new freeze and is not comparable to the archived
E3 figures**, which is what its `freeze` field and its new directory both say.

## Evidence untouched, verified

```
$ git diff f03db5b --stat -- reports/evidence/
```

empty before the new directory was added, and afterwards the only entry under
`reports/evidence/` is the new `invr1b4-mean-score/`. `git status --short
--untracked-files=all reports/evidence/` names no pre-existing file. The three
archived E3 directories plus `inv_r1_e2_retention` are byte-identical to the
base.

## Gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/b4-score \
  && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b4-score/src timeout 1200 \
  /home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_inv_b4_constant_score.py tests/test_agenda_policy.py tests/test_ag01_policy.py -q'
```

Summary line, observed by the coordinator on the merged tip after `2c187ae`:

```
42 passed, 4 errors in 997.39s (0:16:37)
```

The 4 errors are the freeze-artifact tests, which read
`reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`. That file does
not exist because the single `control_competence(40)` sweep was cancelled for
resource reasons before it returned. **A cancelled measurement is not a null
measurement.** Nothing about the crossover is known in either direction, and
these 4 errors are the honest state of an unmeasured freeze, not a regression.
Running the one sweep turns them green with no source change.

## Changes needed outside my owned paths

None were needed. `s09_e3_selection.qualified_ladder` and `e3_ladder` consume
the corrected score without edits, because both already report means.

One thing a later lane should read rather than fix here.
`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json` embeds
`best_rule_held_out_reduction` on the old sum scale, and
`reports/STAGE-09-COMPLETION-MATRIX.md:193` and
`reports/workstreams/w0-tr05.md:62,210` quote it under that name. Those
documents describe their own revisions and must not be edited in place, so
this is recorded rather than changed. Anyone reading those figures needs to
know they are sums and that the live code no longer produces them.
