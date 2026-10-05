"""Re-derive M3's recorded numbers, and say which of them survive the freeze.

One command, every figure, no figure inherited:

    uv run python -m experiments.ad01.m3_revalidate

Answers three questions in order.

1. **Do the recorded figures reproduce?** Replays `e4_budget_ladder.measure`
   under the frozen `rule_learner` and under the pre-freeze learner
   reconstructed verbatim from `44ec6c52~1`, then compares both to the
   literals in `STAGE-09-RECOMMENDATION.md`.

2. **What is the blind arm?** Reports the sequence each arm emits, whether it
   varies by seed, and where that sequence ranks among all 12870 eight-subsets.
   A blind mean over a single fixed subset is not a competence score, and this
   is what makes that visible.

3. **What did the freeze move?** Reports identification over all 224 class
   members under three query rules, and the uniform-subset distribution the
   old blind number was a draw from.

The pre-freeze learner is reconstructed here rather than imported from Git, so
this file is the only place that knows what changed. It is read-only and
imported by no production module.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import statistics
import sys

from . import boolean_rule as br
from . import rule_learner as rl
from .improve_channel import descendant_score

CLASS = br.CLASS_TABLES
N_CAND = len(CLASS)
COHORTS = {"original": list(range(150)),
           "fresh_a": list(range(1000, 1150)),
           "fresh_b": list(range(2000, 2150))}
BUDGETS = (1, 2, 4, 8)
SPLIT = "audit"

# `reports/STAGE-09-RECOMMENDATION.md` §1.1, the budget-8 row per cohort.
RECORDED_BUDGET_8 = {
    "original": {"blind": 0.5017, "informed": 0.8500, "delta": 0.3483},
    "fresh_a": {"blind": 0.5208, "informed": 0.8958, "delta": 0.3750},
    "fresh_b": {"blind": 0.5292, "informed": 0.9142, "delta": 0.3850},
}


# --------------------------------------------------------------------------
# The two learners. Same class, same disagreement; they differ only in how a
# tie is broken, which is the whole of commit 44ec6c52.
# --------------------------------------------------------------------------

class PreFreezeLearner:
    """`rule_learner.VersionSpaceLearner` as of `44ec6c52~1`.

    Verbatim, except that the rng is stored under an explicit name rather than
    inherited from a base. Upstream read `random.Random(seed)` in `__init__`
    and drew with `cands[self._rng.randrange(len(cands))]`, so the query
    sequence depended on a seed that nothing had frozen.
    """

    def __init__(self, class_tables, seed):
        self._rng = random.Random(int(seed))
        self._candidates = [set(class_tables) for _ in range(br.N_OUTPUTS)]

    def observe(self, x, y):
        for bit in range(br.N_OUTPUTS):
            self._candidates[bit] = {
                t for t in self._candidates[bit] if ((t >> x) & 1) == y[bit]}

    def version_space_sizes(self):
        return [len(c) for c in self._candidates]

    def _disagreement(self, x):
        total = 0
        for cand in self._candidates:
            ones = sum((t >> x) & 1 for t in cand)
            total += min(ones, len(cand) - ones)
        return total

    def choose_query(self, queried, budget=br.MAX_QUERIES):
        if len(queried) >= budget:
            return None
        open_inputs = [x for x in range(br.N_STATES) if x not in queried]
        if not open_inputs:
            return None
        scored = [(self._disagreement(x), x) for x in open_inputs]
        best = max(s for s, _ in scored)
        cands = sorted(x for s, x in scored if s == best)
        return cands[self._rng.randrange(len(cands))]


def gather(seed, *, informed, learner_cls, split=SPLIT):
    """One seed's evidence set. Identical to `e4_budget_ladder._sequences`."""
    learner = learner_cls(CLASS, int(seed))
    if not informed:
        queried: set = set()
        chosen: list = []
        for _ in range(br.MAX_QUERIES):
            pick = learner.choose_query(
                {x: (0,) * br.N_OUTPUTS for x in queried})
            if pick is None:
                break
            chosen.append(pick)
            queried.add(pick)
        return chosen
    session = br.RuleSession(br.make_task(split, int(seed)))
    queried = set()
    chosen = []
    for _ in range(br.MAX_QUERIES):
        seen = {x: session.query(x) if x in queried
                else (0,) * br.N_OUTPUTS for x in queried}
        pick = learner.choose_query(seen)
        if pick is None:
            break
        chosen.append(pick)
        queried.add(pick)
        learner.observe(pick, session.query(pick))
    return chosen


def ladder_mean(learner_cls, cohort, informed, budget):
    """The ladder's mean at one budget, under one learner."""
    seeds = COHORTS[cohort]
    return statistics.fmean(
        descendant_score(gather(s, informed=informed, learner_cls=learner_cls)
                         [:budget], SPLIT, s)["unqueried"] for s in seeds)


# --------------------------------------------------------------------------
# Identification. Answered per class member, never per sample, because the
# claim under test is a worst-case bound over a finite class.
# --------------------------------------------------------------------------

def _answer_as(table, x):
    return tuple((table >> x) & 1 for _ in range(br.N_OUTPUTS))


def _pinned(table, sequence):
    learner = rl.VersionSpaceLearner(CLASS, 0)
    for x in sequence:
        learner.observe(x, _answer_as(table, x))
    return max(learner.version_space_sizes()) == 1


def _frozen_sequence(table):
    learner = rl.VersionSpaceLearner(CLASS, 0)
    chosen = []
    for _ in range(br.MAX_QUERIES):
        pick = learner.choose_query({x: _answer_as(table, x) for x in chosen})
        if pick is None:
            break
        chosen.append(pick)
        learner.observe(pick, _answer_as(table, pick))
    return chosen


def _fixed_sequence(table):
    return list(range(br.MAX_QUERIES))


def _random_sequence(seed):
    rng = random.Random(seed)
    chosen = []
    for _ in range(br.MAX_QUERIES):
        chosen.append(rng.choice([x for x in range(br.N_STATES)
                                  if x not in chosen]))
    return chosen


def identification():
    """Missed counts for three query rules over all 224 class members.

    The random rule is swept over many seed conventions rather than pinned to
    one, because its seed is exactly what the freeze removed: no single value
    is a property of the class.
    """
    out = {}
    for label, picker in (("frozen", _frozen_sequence),
                          ("fixed_input_order", _fixed_sequence)):
        missed = sum(1 for t in CLASS if not _pinned(t, picker(t)))
        out[label] = {"missed": missed, "of": N_CAND}
    by_convention = {}
    for cname, conv in (("class_index", lambda i, t: i),
                        ("class_table_value", lambda i, t: t),
                        ("always_zero", lambda i, t: 0)):
        by_convention[cname] = sum(
            1 for i, t in enumerate(CLASS)
            if not _pinned(t, _random_sequence(conv(i, t))))
    spread = sorted(sum(1 for i, t in enumerate(CLASS)
                        if not _pinned(t, _random_sequence(s)))
                    for s in range(200))
    out["pre_freeze_random"] = {
        "missed_by_seed_convention": by_convention,
        "missed_over_200_conventions": {
            "min": spread[0], "max": spread[-1],
            "median": spread[len(spread) // 2]},
        "note": ("a function of the unfrozen seed, so no single count is a "
                 "class property; reported as a range"),
    }
    return out


def blind_arm_mechanism(subset_seeds=40):
    """What each arm emits, and where the blind subset ranks among all of them."""
    blind = {tuple(gather(s, informed=False, learner_cls=rl.VersionSpaceLearner))
             for s in COHORTS["original"]}
    informed = {tuple(gather(s, informed=True, learner_cls=rl.VersionSpaceLearner))
                for s in COHORTS["original"]}

    # Every open input ties on disagreement at zero observations, so the frozen
    # tie-break returns the lowest unqueried input every time. Measure that
    # rather than assert it.
    learner = rl.VersionSpaceLearner(CLASS, 0)
    tie_values = sorted({learner._disagreement(x) for x in range(br.N_STATES)})

    seeds = COHORTS["fresh_a"][:subset_seeds]
    ranked = sorted(
        (statistics.fmean(descendant_score(list(c), SPLIT, s)["unqueried"]
                          for s in seeds), list(c))
        for c in itertools.combinations(range(br.N_STATES), br.MAX_QUERIES))
    blind_subset = list(next(iter(blind)))
    rank = [i for i, (_, c) in enumerate(ranked) if c == blind_subset][0]

    return {
        "blind_sequences_distinct": len(blind),
        "blind_sequence": blind_subset,
        "informed_sequences_distinct": len(informed),
        "disagreement_values_with_no_observations": tie_values,
        "blind_ties_with_every_open_input": len(tie_values) == 1,
        "subset_rank_exhaustive": {
            "n_subsets": len(ranked), "seeds_each": len(seeds),
            "blind_rank_from_worst": rank,
            "worst": {"score": ranked[0][0], "subset": ranked[0][1]},
            "best": {"score": ranked[-1][0], "subset": ranked[-1][1]},
            "mean_over_all_subsets": statistics.fmean(
                [sc for sc, _ in ranked]),
        },
    }


def uniform_subset_distribution(reps=20):
    """The distribution the old blind number was one draw from."""
    out = {}
    for name, seeds in COHORTS.items():
        means = []
        for rep in range(reps):
            rng = random.Random(70000 + rep)
            means.append(statistics.fmean(
                descendant_score(sorted(rng.sample(range(br.N_STATES),
                                                   br.MAX_QUERIES)),
                                 SPLIT, s)["unqueried"] for s in seeds))
        out[name] = {"mean": statistics.fmean(means),
                     "sd": statistics.stdev(means), "reps": reps}
    return out


# `reports/PROJECT-LEDGER.md` states the old blind arm was "the mean over
# *random* 8-subsets (measured: 20 reps, mean 0.5138, sd 0.0169)". Those two
# numbers are only reproducible if the re-derivation's own random seed and
# rep-seed convention are known, so the sweep below reports the range the
# pair could have come from instead of assuming the ledger's.
LEDGER_CHANCE_PAIR = (0.5138, 0.0169)


def ledger_chance_pair(reps=20, offsets=64):
    """Does any cohort/offset convention land on the ledger's exact pair?"""
    cells, hits = [], []
    for name, seeds in COHORTS.items():
        for offset in range(offsets):
            means = []
            for rep in range(reps):
                rng = random.Random(offset * 1000 + rep)
                means.append(statistics.fmean(
                    descendant_score(sorted(rng.sample(range(br.N_STATES),
                                                       br.MAX_QUERIES)),
                                     SPLIT, s)["unqueried"] for s in seeds))
            cell = {"cohort": name, "offset": offset,
                    "mean": statistics.fmean(means),
                    "sd": statistics.stdev(means)}
            cells.append(cell)
            if (abs(cell["mean"] - LEDGER_CHANCE_PAIR[0]) < 5e-4
                    and abs(cell["sd"] - LEDGER_CHANCE_PAIR[1]) < 5e-4):
                hits.append(cell)
    means = [c["mean"] for c in cells]
    sds = [c["sd"] for c in cells]
    near_mean = sum(1 for c in cells if abs(c["mean"] - LEDGER_CHANCE_PAIR[0]) < 1e-3)
    closest_sd = min(sds, key=lambda v: abs(v - LEDGER_CHANCE_PAIR[1]))
    return {
        "target_pair": list(LEDGER_CHANCE_PAIR),
        "conventions_swept": len(cells),
        "exact_hits": hits,
        "mean_range": [min(means), max(means)],
        "sd_range": [min(sds), max(sds)],
        "conventions_within_1e_3_of_mean": near_mean,
        "closest_sd_to_target": closest_sd,
        "closest_sd_gap": abs(closest_sd - LEDGER_CHANCE_PAIR[1]),
        "reproduces": bool(hits),
    }


def ladder_table(learner_cls):
    return {c: {b: {"blind": ladder_mean(learner_cls, c, False, b),
                    "informed": ladder_mean(learner_cls, c, True, b)}
                for b in BUDGETS}
            for c in COHORTS}


def reproduce():
    """Both learners against the recommendation's budget-8 literals."""
    frozen = ladder_table(rl.VersionSpaceLearner)
    pre = ladder_table(PreFreezeLearner)
    rows = {}
    for c in COHORTS:
        rec = RECORDED_BUDGET_8[c]
        rows[c] = {
            "recorded": rec,
            "pre_freeze": {k: pre[c][8][k] for k in ("blind", "informed")},
            "frozen": {k: frozen[c][8][k] for k in ("blind", "informed")},
            "pre_freeze_reproduces": all(
                abs(pre[c][8][k] - rec[k]) < 5e-5 for k in ("blind", "informed")),
            "frozen_reproduces": all(
                abs(frozen[c][8][k] - rec[k]) < 5e-5
                for k in ("blind", "informed")),
        }
        for k in ("blind", "informed"):
            rows[c]["pre_freeze"][k + "_delta"] = round(
                pre[c][8][k] - rec[k], 6)
            rows[c]["frozen"][k + "_delta"] = round(
                frozen[c][8][k] - rec[k], 6)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="print the full record instead of the tables")
    args = parser.parse_args(argv)

    out = {
        "class_size": N_CAND,
        "max_queries": br.MAX_QUERIES,
        "ceil_log2_class": math.ceil(math.log2(N_CAND)),
        "reproduction": reproduce(),
        "identification": identification(),
        "blind_arm": blind_arm_mechanism(),
        "uniform_8_subset": uniform_subset_distribution(),
        "ledger_chance_pair": ledger_chance_pair(),
    }
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    print("class=%d  MAX_QUERIES=%d  ceil(log2)=%d"
          % (N_CAND, br.MAX_QUERIES, math.ceil(math.log2(N_CAND))))

    print("\n== 1. do the recorded budget-8 figures reproduce? ==")
    print("%-9s %-9s %-10s %-10s %s" % ("cohort", "field", "recorded",
                                       "re-derived", "verdict"))
    for c, r in out["reproduction"].items():
        for k in ("blind", "informed"):
            for regime in ("pre_freeze", "frozen"):
                got = r[regime][k]
                print("%-9s %-9s %-10.4f %-10.4f %s"
                      % (c if k == "blind" else "", k,
                         r["recorded"][k], got,
                         "MATCH" if abs(got - r["recorded"][k]) < 5e-5
                         else "differs by %+.4f" % (got - r["recorded"][k])))
        print("   pre_freeze reproduces both: %s | frozen reproduces both: %s"
              % (r["pre_freeze_reproduces"], r["frozen_reproduces"]))

    print("\n== 2. identification over all %d class members ==" % N_CAND)
    for label in ("frozen", "fixed_input_order"):
        i = out["identification"][label]
        print("  %-19s missed %d of %d" % (label, i["missed"], i["of"]))
    rnd = out["identification"]["pre_freeze_random"]
    print("  %-19s missed %s by seed convention"
          % ("pre_freeze_random", rnd["missed_by_seed_convention"]))
    print("  %-19s missed min=%d max=%d median=%d over 200 conventions"
          % ("pre_freeze_random",
             rnd["missed_over_200_conventions"]["min"],
             rnd["missed_over_200_conventions"]["max"],
             rnd["missed_over_200_conventions"]["median"]))

    print("\n== 3. what is the blind arm? ==")
    b = out["blind_arm"]
    print("  blind sequences distinct over %d seeds: %d  -> %s"
          % (len(COHORTS["original"]), b["blind_sequences_distinct"],
             b["blind_sequence"]))
    print("  disagreement with no observations: %s (all tie: %s)"
          % (b["disagreement_values_with_no_observations"],
             b["blind_ties_with_every_open_input"]))
    r = b["subset_rank_exhaustive"]
    print("  that subset ranks %d of %d from the bottom (worst=%.4f, "
          "mean=%.4f)"
          % (r["blind_rank_from_worst"], r["n_subsets"], r["worst"]["score"],
             r["mean_over_all_subsets"]))
    print("  informed sequences distinct over the same seeds: %d"
          % b["informed_sequences_distinct"])

    print("\n== 4. the distribution the old blind figure was a draw from ==")
    for c, v in out["uniform_8_subset"].items():
        print("  %-9s uniform-8 mean %.4f  sd %.4f" % (c, v["mean"], v["sd"]))

    pair = out["ledger_chance_pair"]
    print("\n== 5. the ledger's chance pair (%.4f, sd %.4f) ==" % tuple(
        pair["target_pair"]))
    print("  swept %d cohort/offset conventions at 20 reps: reproduces: %s"
          % (pair["conventions_swept"], pair["reproduces"]))
    print("  mean across conventions %.4f-%.4f, sd %.4f-%.4f"
          % (pair["mean_range"][0], pair["mean_range"][1],
             pair["sd_range"][0], pair["sd_range"][1]))
    print("  %d conventions land within 0.001 of the target mean; the closest"
          " any sd comes is %.4f, a gap of %.4f"
          % (pair["conventions_within_1e_3_of_mean"],
             pair["closest_sd_to_target"], pair["closest_sd_gap"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())