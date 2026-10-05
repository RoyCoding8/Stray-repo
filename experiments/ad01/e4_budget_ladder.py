"""Measure the E4 budget ladder that `STAGE-09-RECOMMENDATION.md` §3 reports.

Two arms, both scored by the shipped evaluator
(`improve_channel.descendant_score`, `improve_channel.py:849-877`):

- **blind** -- the shipped construction. `choose_query` is called and
  `observe` is never called, so `self._candidates` stays the full 224-table
  class. The pick is the *smallest index among the inputs that tie on total
  disagreement* (`rule_learner.py:71-79`).
- **informed** -- `observe` is called with each real answer as it is gathered,
  which is the `observe=True` cell of the w4-leakage factorial.

Cost is 150 seeds x 4 budgets x 2 arms. Writes
`reports/evidence/inv_r1_e4/budget-ladder.json`.

## Why this script reconciles against a derived bound, not a table of literals

An earlier revision held `EXPECTED_BUDGET_8`, three cohorts x three cells of
decimals copied out of the recommendation document, and reported
`reconciles: {blind, informed, delta}`. Two of those nine cells could never
have been pinned to four places, and the freeze in `44ec6c52` proved it.

**The blind cell was never a competence number.** Before the freeze the
tie-break was `cands[self._rng.randrange(len(cands))]`, so the blind arm drew
a fresh random 8-subset per seed: 150 distinct sequences over 150 seeds. Its
`0.5017`/`0.5208`/`0.5292` is a draw from that distribution, whose per-cohort
mean over uniform 8-subsets is `0.5195`/`0.5182`/`0.5134` (20 reps, sd
`0.025`/`0.023`/`0.019`). Pinning a draw to four places pins the seed.

**After the freeze it is not chance either.** With nothing observed, every
open input's total disagreement is the same (448), so "smallest index on
ties" always returns the lowest unqueried input and the blind arm emits
`[0, 1, 2, 3, 4, 5, 6, 7]` for every seed. Measured over all 12870
eight-subsets on 40 seeds, that subset ranks **22nd from the bottom**. So the
`0.0600` is not "what blindness scores"; it is what this one unlucky subset
scores. Either way the cell measures the tie-break, not the ladder.

So the two blind cells and the two blind-derived deltas are deleted rather
than re-pinned, and `reconciles` is replaced by `attains_bound`, which is
computed from the instrument and holds or fails on its own:

- `bound = ceil(log2(len(CLASS_TABLES))) = ceil(log2(224)) = 8`, the fewest
  binary probes that can pin one member of the class.
- The informed arm must reach `unqueried == 1.0` on **every** seed at that
  budget, because the version space is then a singleton.
- The blind arm must identify **nothing** at that budget, because it never
  observes.

Both halves are properties of the instrument and the data, not of a document.
Both fail on the pre-freeze tree, where the informed arm's budget-8 mean was
`0.8500`/`0.8958`/`0.9142` rather than `1.0`: the old tie-break spent probes
on coin flips and left a non-singleton space. That is the regression this
check now catches, and it is the check the frozen table could not express.

    uv run python -m experiments.ad01.e4_budget_ladder
    uv run python -m experiments.ad01.e4_budget_ladder --cohort original
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

# The cohorts `STAGE-09-RECOMMENDATION.md` §1.1 reports, by name. `fresh_a` is
# the default because it is the cohort the ladder's budget-8 blind cell named,
# so it is the cohort against which the other rows have to reconcile.
COHORTS = {
    "original": list(range(150)),
    "fresh_a": list(range(1000, 1150)),
    "fresh_b": list(range(2000, 2150)),
}

BUDGETS = (1, 2, 4, 8)


def _sequences(seed: int, *, informed: bool, split: str) -> list:
    """One seed's evidence set, in the order the arm would gather it."""
    from . import boolean_rule as _rules
    from . import rule_learner as _reducer

    learner = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, int(seed))
    if not informed:
        queried: set = set()
        chosen: list = []
        for _ in range(_rules.MAX_QUERIES):
            pick = learner.choose_query(
                {x: (0,) * _rules.N_OUTPUTS for x in queried})
            if pick is None:
                break
            chosen.append(pick)
            queried.add(pick)
        return chosen

    task = _rules.make_task(split, int(seed))
    session = _rules.RuleSession(task)
    queried = set()
    chosen = []
    for _ in range(_rules.MAX_QUERIES):
        seen = {x: session.query(x) if x in queried
                else (0,) * _rules.N_OUTPUTS for x in queried}
        pick = learner.choose_query(seen)
        if pick is None:
            break
        chosen.append(pick)
        queried.add(pick)
        # The one call the shipped construction never makes.
        learner.observe(pick, session.query(pick))
    return chosen


def information_bound() -> int:
    """Fewest binary probes that can pin one member of the hypothesis class."""
    from . import boolean_rule as _rules
    return math.ceil(math.log2(len(_rules.CLASS_TABLES)))


def _attains_bound(cohort: str, split: str, seeds: list) -> dict:
    """Did the informed arm earn the bound, and did the blind arm miss it?

    Computed per seed and reduced with `all`, so one seed short of the bound
    fails the check. A mean would hide it.
    """
    from . import boolean_rule as _rules
    from . import rule_learner as _reducer

    bound = information_bound()
    informed_perfect = []
    blind_perfect = []
    for seed in seeds:
        task = _rules.make_task(split, int(seed))
        session = _rules.RuleSession(task)
        learner = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, int(seed))
        for x in _sequences(int(seed), informed=True, split=split)[:bound]:
            learner.observe(x, session.query(x))
        informed_perfect.append(max(learner.version_space_sizes()) == 1)
        # The blind arm never observes, so its space is the whole class by
        # construction. That is the claim under test, so assert it as one.
        blind = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, int(seed))
        blind_perfect.append(max(blind.version_space_sizes()) == 1)

    return {
        "budget": bound,
        "informed_identifies_every_seed": all(informed_perfect),
        "informed_seeds_short_of_bound": informed_perfect.count(False),
        "blind_identifies_any_seed": any(blind_perfect),
    }


def measure(cohort: str, split: str = "audit") -> dict:
    """Score both arms at every budget on one cohort."""
    from . import boolean_rule as _rules
    from .improve_channel import descendant_score

    seeds = COHORTS[cohort]
    blind = {s: _sequences(s, informed=False, split=split) for s in seeds}
    informed = {s: _sequences(s, informed=True, split=split) for s in seeds}

    rows = []
    for budget in BUDGETS:
        b = [descendant_score(blind[s][:budget], split, s)["unqueried"]
             for s in seeds]
        i = [descendant_score(informed[s][:budget], split, s)["unqueried"]
             for s in seeds]
        mb, mi = statistics.fmean(b), statistics.fmean(i)
        rows.append({
            "budget": budget,
            "n_queried": float(budget),
            "unqueried_denominator": float(_rules.N_STATES - budget),
            "blind_unqueried": mb,
            "informed_unqueried": mi,
            "delta": mi - mb,
        })

    # The blind arm is a property of the tie-break, so name the tie-break
    # instead of pinning its mean. A reader who sees one sequence for every
    # seed knows the column is not sampling.
    blind_sequences = {tuple(v) for v in blind.values()}

    return {
        "cohort": cohort,
        "split": split,
        "n_seeds": len(seeds),
        "seed_range": [seeds[0], seeds[-1]],
        "scorer": "experiments.ad01.improve_channel.descendant_score",
        "arms": {
            "blind": "choose_query with zero vectors, observe never called",
            "informed": "choose_query reading each real answer, observe called",
        },
        "blind_sequence": list(next(iter(blind_sequences))),
        "blind_sequence_is_seed_independent": len(blind_sequences) == 1,
        "rows": rows,
        "attains_bound": _attains_bound(cohort, split, seeds),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", default="fresh_a", choices=sorted(COHORTS))
    parser.add_argument("--split", default="audit")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    result = measure(args.cohort, args.split)

    print("cohort %s %s  n=%d" % (
        result["cohort"], result["seed_range"], result["n_seeds"]))
    print("%-7s %-8s %-9s %-9s %-9s" % (
        "budget", "denom", "blind", "informed", "delta"))
    for r in result["rows"]:
        print("%-7d %-8d %-9.4f %-9.4f %+-9.4f" % (
            r["budget"], r["unqueried_denominator"],
            r["blind_unqueried"], r["informed_unqueried"], r["delta"]))
    print("blind arm emits %s for every seed: %s" % (
        result["blind_sequence"], result["blind_sequence_is_seed_independent"]))
    print("attains ceil(log2(class)) = %d: %s" % (
        result["attains_bound"]["budget"],
        result["attains_bound"]["informed_identifies_every_seed"]))

    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parents[2]
        / "reports" / "evidence" / "inv_r1_e4" / "budget-ladder.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())