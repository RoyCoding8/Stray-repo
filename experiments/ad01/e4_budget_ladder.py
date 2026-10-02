"""Measure the E4 budget ladder that `STAGE-09-RECOMMENDATION.md` §3 reports.

The ladder table in that document carried four rows of per-budget `unqueried`
means. An earlier revision of the table carried blind `0.0611`/`0.0560`/
`0.1125` and informed `0.1250`/`0.9083` at budgets 1/2/4/8. No artifact on
HEAD held any of them, so nothing could check them; a grep for `0.9083` returns
exactly one hit, which reads as clean. This script is that check, and it writes
its own output so the next reader does not have to re-derive it.

Three of four cells in each column were wrong. Only the budget-8 blind cell
matched. The `0.9083` was `0.5208 + 0.3750 + 0.0125` -- the budget-4 delta
added into the budget-8 row, an arithmetic slip on a column never measured.

Two arms, both scored by the shipped evaluator
(`improve_channel.descendant_score`, `improve_channel.py:507-535`):

- **blind** -- the shipped construction. `choose_query` is called with zero
  vectors and `observe` is never called, so `self._candidates` stays the full
  224-table class and the pick is `cands[rng.randrange(16)]`, a uniform draw
  over open inputs (`rule_learner.py:33-50`).
- **informed** -- `observe` is called with each real answer as it is gathered,
  which is the `observe=True` cell of the w4-leakage factorial.

Cost is 150 seeds x 4 budgets x 2 arms. The budget-8 row reproduces the
`0.5208`/`0.8958`/`+0.3750` triple the recommendation already reports, which is
what confirms the construction is the intended one.

    uv run python -m experiments.ad01.e4_budget_ladder
    uv run python -m experiments.ad01.e4_budget_ladder --cohort original

Writes `reports/evidence/inv_r1_e4/budget-ladder.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The cohorts `STAGE-09-RECOMMENDATION.md` §1.1 reports, by name. `fresh_a` is
# the default because it is the cohort the ladder's budget-8 blind cell named,
# so it is the cohort against which the other three rows have to reconcile.
COHORTS = {
    "original": list(range(150)),
    "fresh_a": list(range(1000, 1150)),
    "fresh_b": list(range(2000, 2150)),
}

BUDGETS = (1, 2, 4, 8)

# The budget-8 figures `STAGE-09-RECOMMENDATION.md` §1.1 already reports for each
# cohort, so `--cohort fresh_b` checks itself against what the document says
# rather than against fresh_a's numbers. An earlier revision of this script
# asserted fresh_a's literals unconditionally, which made a correct fresh_b run
# print three `false` and read as a failed reconciliation.
EXPECTED_BUDGET_8 = {
    "original": {"blind": 0.5017, "informed": 0.8500, "delta": 0.3483},
    "fresh_a": {"blind": 0.5208, "informed": 0.8958, "delta": 0.3750},
    "fresh_b": {"blind": 0.5292, "informed": 0.9142, "delta": 0.3850},
}


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


def _mean(values: list) -> float:
    return sum(values) / len(values)


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
        mb, mi = _mean(b), _mean(i)
        rows.append({
            "budget": budget,
            "n_queried": float(budget),
            "unqueried_denominator": float(_rules.N_STATES - budget),
            "blind_unqueried": mb,
            "informed_unqueried": mi,
            "delta": mi - mb,
        })

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
        "rows": rows,
        "expected_budget_8": EXPECTED_BUDGET_8[cohort],
        "reconciles": {
            "blind": round(rows[-1]["blind_unqueried"], 4)
            == EXPECTED_BUDGET_8[cohort]["blind"],
            "informed": round(rows[-1]["informed_unqueried"], 4)
            == EXPECTED_BUDGET_8[cohort]["informed"],
            "delta": round(rows[-1]["delta"], 4)
            == EXPECTED_BUDGET_8[cohort]["delta"],
        },
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
    print("reconciles with the recommendation's budget-8 row: %s"
          % (result["reconciles"],))

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
