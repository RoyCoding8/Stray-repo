# E4 headroom: a blind-sequence artifact, and how it was measured

Recovered record. The original lane report was written but never committed, and
its worktree was removed during cleanup. The findings below are the ones
`reports/STAGE-09-RECOMMENDATION.md` relies on, restated with the measurement
that produced each. The three cited JSON artifacts were lost with the
worktree; §"Reproducing this" says how to regenerate them.

## The defect

`experiments/ad01/learner_revision.py:966-977` builds `evidence_ceiling`'s
query sequence by calling `learner.choose_query({x: (0,)*N_OUTPUTS for x in
queried})` and recording the pick. It **never calls `learner.observe`**, so
`self._candidates` stays the full 224-table class for all eight steps. The
object is not a learner; it is a tie-break RNG over a static disagreement
function. The note at `:992-994` describing the sequence as "the frozen
reducer's own eight-input evidence set" is false as written.

## The zero vector is inert

`choose_query` (`experiments/ad01/rule_learner.py:40-50`) reads only the
**keys** of `queried`:

```python
open_inputs = [x for x in range(br.N_STATES) if x not in queried]
```

The dict's values are never read. A 2x3 factorial over 150 fresh seeds --
{observe on, observe off} x {zero fill, real values, bitwise-complement
values} -- produced **byte-identical sequences for all three value fills within
an `observe` level**, and `observe` alone moved the number. `Values=real,
observe=False` is identical to the shipped construction on 150/150 seeds.

**Consequence for the first draft of the recommendation:** it recommended
"pass the real observation vector". That is a no-op. A reviewer who tried it
would have wrongly concluded the reducer cannot choose well, and a freeze
would have been burned to discover nothing.

## The effect is real, grows on fresh cohorts, and is not leakage

| cohort | blind | informed | delta | z |
|---|---|---|---|---|
| original `range(150)` | 0.5017 (43rd pctile) | 0.8500 (99th pctile) | +0.3483 | +11.38 |
| fresh_a `range(1000,1150)` | 0.5208 | 0.8958 | +0.3750 | +13.17 |
| fresh_b `range(2000,2150)` | 0.5292 | 0.9142 | +0.3850 | +14.67 |

Disjointness is measured at the **truth-table level**, not the seed integer:
150 distinct tables per cohort, zero intersection in every pairing. The
informed arm sits at the 98.8th percentile of 400 random 8-subsets.

**The clincher is a cross-split control.** Choosing on `qual` and scoring on
`audit` -- splits that share **zero truth tables** -- still gives **+0.2675 at
z = +8.38**. Leakage cannot produce a gap against a task it cannot see.

An answer-key tripwire confirmed it is not the key: `RuleSession.query`
(`experiments/ad01/boolean_rule.py:213-221`) is the only route to a real answer
and refuses past budget, and a tripwire recording every read of
`_task["tables"]` during the informed arm saw exactly 8 reads per seed, all
from `query()` itself.

## The rival diagnoses, each excluded by measurement

- **Not the E4 boundary.** Its own range is `0.006222` on the original cohort
  and `-0.000889, z = -0.33` on fresh_a.
- **Not the budget.** Both arms spend 8/8. The delta is `+0.0000` at budgets 1
  and 2, `+0.0150` at 4, and appears only at full budget. (The `+0.0125`
  an earlier revision of this file gave at budget 4 was wrong; the measured
  figure is `+0.0150`.)
- **Not the denominator.** `unqueried` averages over `16 - n_queried`, so a
  one-input arm is scored on 15 and an eight-input arm on 8. The gap halves on
  `overall` but survives. The denominator issue bites incumbent-vs-reducer,
  not blind-vs-informed, since both arms ask for 8 inputs.

## The question this does not settle

Whether restoring `observe` inside `evidence_ceiling` counts as "altering the
learner" under `WORKER-PROMPT.md:86` is a coordinator judgement, not a
measurement. The narrower reading: `evidence_ceiling` is a *measurement
harness* over a frozen reducer, so making it measure what its own note claims
is a reporting correction in the same class as adding `overall`. Whether a
**descendant** may choose its own evidence against real observations is a
separate question that genuinely needs a fresh freeze, and fixing the harness
does not settle it.

Residual risk that could not be constructed away: a task family where
observing eight inputs does not identify the target, yet cross-split transfer
still shows a gap. On this instrument the hypothesis class is public and
identical for every task.

## Reproducing this

The three cited JSON artifacts are gone. Regenerate them with the same three
offline scripts the lane used, against the current source:

1. the 2x3 factorial over `observe` x value-fill, 150 fresh seeds -- expect
   byte-identical sequences across fills within an `observe` level;
2. the three-cohort informed-vs-blind ladder -- expect the table above;
3. the cross-split control, choosing on `qual` and scoring on `audit` -- expect
   +0.2675 at z = +8.38.

All three are offline, need no model and no network, and take seconds to a
couple of minutes. A disagreement means the source has moved since this
measurement, and the recommendation's E4 section should be re-derived rather
than re-read.
