"""E4's headroom claim, written to a data artifact instead of a docstring.

    .venv/bin/python reports/evidence/inv_r1_e4/make_evidence.py

Every number in `headroom.json` comes out of one run of this script, and
the script writes the cohort inputs next to the numbers so a reader can
reproduce them rather than being asked to run pytest. The controls block
records the three apparatus controls with the deltas they actually
produced, because "the apparatus is qualified" is a claim about numbers
and belongs beside them.

The population block is the answer to "is there no headroom, or can my
probe not reach it". It evaluates both reachable descendants on one large
cohort and reports the difference as a paired estimate with its standard
error, so the two readings separate: a probe that cannot reach headroom
still shows a real effect, only too small for the sampled cohort, while an
absent effect converges to zero as the cohort grows.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel

HERE = Path(__file__).resolve().parent

DOCUMENTED_SPLIT = "dev"
DOCUMENTED_SEEDS = [0, 1, 2]
CONTROL_SPLIT = "qual"
CONTROL_SEEDS = list(range(24))
POPULATION_N = 1500

# The three controls the handoff requires. Each is a real measurement over
# CONTROL_SEEDS, not a hand-written delta, so the recorded `as_expected`
# cannot drift away from what the apparatus did.
CONTROLS = {
    "known-effect": list(channel.GENERAL_POSITION),
    "no-op": [3],
    "disconnect": [16],
}


def _measured(evidence, split, seeds):
    return channel.evaluate_descendants(
        list(evidence), split=split, seeds=seeds)


def main() -> int:
    headroom = channel.channel_headroom(
        split=DOCUMENTED_SPLIT, seeds=DOCUMENTED_SEEDS)
    floor = channel.noise_floor(
        split=DOCUMENTED_SPLIT, seeds=DOCUMENTED_SEEDS)

    incumbent = _measured([3], CONTROL_SPLIT, CONTROL_SEEDS)
    nothing = _measured([], CONTROL_SPLIT, CONTROL_SEEDS)
    controls = []
    for role, evidence in CONTROLS.items():
        measured = _measured(evidence, CONTROL_SPLIT, CONTROL_SEEDS)
        detail = channel.descendant_score(
            evidence, CONTROL_SPLIT, CONTROL_SEEDS[0])
        # A disconnect is not measured against the incumbent. It named an
        # input the instrument refuses, so the right comparison is against a
        # descendant that learned nothing at all; that is the only reading
        # under which "disconnected" and "no-op" are different failures.
        reference, reference_name = (
            (nothing, "descendant-that-learned-nothing")
            if role == "disconnect" else (incumbent, "incumbent"))
        as_expected = channel.descendant_delta(
            measured, reference)["delta"] == 0.0
        if role == "known-effect":
            as_expected = (
                as_expected
                or channel.descendant_delta(
                    measured, incumbent)["delta"] > 0.0)
        controls.append({
            "role": role,
            "evidence": list(evidence),
            "split": CONTROL_SPLIT,
            "n_seeds": len(CONTROL_SEEDS),
            "mean": measured["mean"],
            "incumbent_mean": incumbent["mean"],
            "reference": reference_name,
            "delta": channel.descendant_delta(measured, reference)["delta"],
            "delta_vs_incumbent": channel.descendant_delta(
                measured, incumbent)["delta"],
            "refused_inputs": detail["refused_inputs"],
            "learned_inputs": detail["learned_inputs"],
            "as_expected": as_expected,
        })

    verdict = channel.qualify_apparatus(controls)

    low = [channel.descendant_score([3], DOCUMENTED_SPLIT, s)["unqueried"]
           for s in range(POPULATION_N)]
    high = [channel.descendant_score([11], DOCUMENTED_SPLIT, s)["unqueried"]
            for s in range(POPULATION_N)]
    paired = [h - low_ for low_, h in zip(low, high)]
    mean_low = sum(low) / POPULATION_N
    mean_high = sum(high) / POPULATION_N
    difference = mean_high - mean_low
    sd = statistics.pstdev(paired)
    se = sd / POPULATION_N ** 0.5
    seeds_needed = ((1.96 * sd / abs(difference)) ** 2
                    if difference else None)

    by_seed = {
        "n": POPULATION_N,
        "split": DOCUMENTED_SPLIT,
        "incumbent_evidence": [3],
        "alternative_evidence": [11],
        "mean_incumbent": mean_low,
        "mean_alternative": mean_high,
        "difference": difference,
        "paired_sd": sd,
        "paired_se": se,
        "z": difference / se if se else None,
        "seeds_for_95pct_resolution": seeds_needed,
        "interpretation": (
            "Both reachable descendants were scored on one large cohort. "
            "The paired difference is the entire headroom the channel can "
            "express, measured with a standard error small enough to "
            "trust. An effect that is present but unreachable at the "
            "documented cohort size would still separate here; a null "
            "that converges to zero as the cohort grows is the substrate "
            "answer, not the probe answer."),
    }

    reachable = {}
    for probe in range(16):
        result = channel.evaluate_lineage(
            [probe], split=DOCUMENTED_SPLIT, seeds=DOCUMENTED_SEEDS)
        reachable[probe] = result["mean"]

    # The reachable pair only bounds the menu. This bounds the substrate:
    # every one of the sixteen inputs the instrument accepts, scored on one
    # large cohort, so "the menu is too narrow" and "the decision has no
    # range" can be told apart. A revision choosing a better probe is the
    # only lever the channel has, so the range over all sixteen probes is
    # the ceiling on any revision of this decision.
    per_input = {p: [channel.descendant_score(
        [p], DOCUMENTED_SPLIT, s)["unqueried"] for s in range(POPULATION_N)]
        for p in range(16)}
    input_means = {p: sum(v) / POPULATION_N
                   for p, v in per_input.items()}
    best_input = max(input_means, key=input_means.get)
    worst_input = min(input_means, key=input_means.get)
    ceiling_paired = [b - w for b, w in zip(
        per_input[best_input], per_input[worst_input])]
    ceiling_mean = sum(ceiling_paired) / POPULATION_N
    ceiling_se = (statistics.pstdev(ceiling_paired) / POPULATION_N ** 0.5)

    ceiling = {
        "n_seeds": POPULATION_N,
        "split": DOCUMENTED_SPLIT,
        "input_means": input_means,
        "best_input": best_input,
        "worst_input": worst_input,
        "ceiling": input_means[best_input] - input_means[worst_input],
        "paired_se": ceiling_se,
        "z": ceiling_mean / ceiling_se if ceiling_se else None,
        "interpretation": (
            "Every input the instrument accepts, scored on one cohort. This "
            "is the ceiling on any revision of this decision, because "
            "choosing a better probe is the only lever the channel offers. "
            "If the ceiling is itself negligible then no probe, and no "
            "wider menu, could produce a descendant effect worth "
            "measuring, and the blocker is the substrate rather than the "
            "instrument's reach."),
    }

    scaling = []
    for n in (3, 6, 12, 24, 48, 96, 192, 384):
        report = channel.channel_headroom(
            split=DOCUMENTED_SPLIT, seeds=list(range(n)))
        # The estimator is a PAIRED difference now, not a whole-cohort
        # spread minus a half-cohort one. `reachable_spread`, `noise_floor`
        # and `headroom` are gone: comparing a spread measured on n samples
        # with one measured on n/2 is what made the old number negative at
        # every cohort size. Recording the shape that exists is the point of
        # this file - a generator that silently wrote the old keys would keep
        # a stale claim alive.
        scaling.append({"n_seeds": n,
                        "estimator": report["estimator"],
                        "delta": report["delta"],
                        "paired_sd": report["paired_sd"],
                        "paired_se": report["paired_se"],
                        "z": report["z"],
                        "measurable": report["measurable"],
                        "best_probe": report["best_probe"],
                        "incumbent_mean": report["incumbent_mean"]})

    evidence = {
        "experiment": "E4 one bounded executable learner revision",
        "channel_version": channel.CHANNEL_VERSION,
        "decision_under_study": channel.DECISION,
        "evaluator": channel.EVALUATOR_ID,
        "reproduce": {
            "command": ".venv/bin/python "
                       "reports/evidence/inv_r1_e4/make_evidence.py",
            "generator": "reports/evidence/inv_r1_e4/make_evidence.py",
            "module": "experiments/ad01/improve_channel.py",
            "python": ".venv/bin/python (needs dbos for the import chain)",
            "database": "none; the channel is file-backed and offline",
            "note": "output is deterministic; re-running rewrites this file",
        },
        "inputs": {
            "documented_headroom": {
                "split": DOCUMENTED_SPLIT,
                "seeds": DOCUMENTED_SEEDS,
                "n_seeds": len(DOCUMENTED_SEEDS),
                "resample_count": len(DOCUMENTED_SEEDS),
            },
            "controls": {
                "split": CONTROL_SPLIT,
                "seeds": CONTROL_SEEDS,
                "n_seeds": len(CONTROL_SEEDS),
            },
            "population": {"split": DOCUMENTED_SPLIT,
                           "n_seeds": POPULATION_N},
        },
        "headroom": headroom,
        "noise_floor": {
            "resample_spread": floor["resample_spread"],
            "best_probe_agrees": floor["best_probe_agrees"],
            "half_a_spread": floor["half_a"]["spread"],
            "half_b_spread": floor["half_b"]["spread"],
            "half_a_best_probe": floor["half_a"]["best_probe"],
            "half_b_best_probe": floor["half_b"]["best_probe"],
        },
        "reachable_evidence": list(channel.REACHABLE_EVIDENCE),
        "reachable_descendant_means": reachable,
        "scaling": scaling,
        "controls": controls,
        "qualification": verdict,
        "population": by_seed,
        "ceiling": ceiling,
    }
    (HERE / "headroom.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
