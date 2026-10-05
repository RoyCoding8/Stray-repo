"""Compare the incumbent, blind eight-query and informed eight-query arms.

This is a diagnostic for the withdrawn E4 evidence-ceiling number.  The
blind arm mirrors ``learner_revision.evidence_ceiling``: it marks inputs as
queried but never feeds outputs back to the version-space learner.  The
informed arm calls ``observe`` after every real task query.  All three arms
are scored per task on a fresh, disjoint cohort and the raw scores are
printed as JSON. Overall accuracy is the primary metric; unqueried accuracy
is retained as a secondary diagnostic because the three arms have unequal
query counts.

The blind arm is **not** a sample of eight inputs.  ``44ec6c52`` froze
``choose_query`` into a total order, and with nothing observed every open
input's total disagreement ties, so "smallest index on ties" returns the
lowest unqueried input every time: the blind arm emits ``[0..7]`` on all 150
seeds.  Before the freeze it drew a fresh random 8-subset per seed.  The
``blind_arm_is_seed_independent`` field reports which regime produced the
numbers beside it, so no reader mistakes one for the other.

Run from the repository root:

    python experiments/ad01/evidence_ceiling_diagnostic.py
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as revision
from experiments.ad01 import rule_learner


SPLIT = "audit"
OLD_E4_SEEDS = tuple(range(150))
FRESH_SEEDS = tuple(range(1000, 1150))
INCUMBENT_EVIDENCE = (3,)


def _sequence(seed: int, *, informed: bool) -> list[int]:
    task = rules.make_task(SPLIT, seed)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    observed: dict[int, tuple[int, ...]] = {}
    chosen: list[int] = []
    for _ in range(rules.MAX_QUERIES):
        pick = learner.choose_query(observed)
        if pick is None:
            break
        output = session.query(pick)
        chosen.append(pick)
        if informed:
            observed[pick] = output
            learner.observe(pick, output)
        else:
            # Match the existing blind harness: only the queried mask changes.
            observed[pick] = (0,) * rules.N_OUTPUTS
    assert len(chosen) == len(set(chosen)) == rules.MAX_QUERIES
    return chosen


def _score(evidence: list[int], seed: int) -> dict:
    raw = channel.descendant_score(evidence, SPLIT, seed)
    return {
        "evidence": list(evidence),
        "overall": raw["overall"],
        "queried": raw["queried"],
        "unqueried": raw["unqueried"],
        "n_queried": raw["n_queried"],
        "learned_inputs": raw["learned_inputs"],
        "refused_inputs": raw["refused_inputs"],
    }


def _stats(values: list[float]) -> dict:
    mean = sum(values) / len(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    se = sd / len(values) ** 0.5
    return {"n": len(values), "mean": mean, "sample_sd": sd,
            "descriptive_se": se}


def _contrast(rows: list[dict], left: str, right: str,
              metric: str) -> dict:
    differences = [row[left][metric] - row[right][metric] for row in rows]
    result = _stats(differences)
    result.update({
        "left": left,
        "right": right,
        "metric": metric,
        "mean_left": sum(row[left][metric] for row in rows) / len(rows),
        "mean_right": sum(row[right][metric] for row in rows) / len(rows),
        "paired_differences": differences,
    })
    return result


def _task_digest(split: str, seed: int) -> str:
    task = rules.make_task(split, seed)
    return hashlib.sha256(repr(tuple(task["tables"])).encode()).hexdigest()


def run() -> dict:
    rows = []
    for seed in FRESH_SEEDS:
        blind = _sequence(seed, informed=False)
        informed = _sequence(seed, informed=True)
        rows.append({
            "seed": seed,
            "task_id": rules.make_task(SPLIT, seed)["task_id"],
            "incumbent": _score(list(INCUMBENT_EVIDENCE), seed),
            "blind8": _score(blind, seed),
            "informed8": _score(informed, seed),
            "sequences": {"blind8": blind, "informed8": informed},
        })

    old_task_ids = {rules.make_task(SPLIT, seed)["task_id"]
                    for seed in OLD_E4_SEEDS}
    fresh_task_ids = {rules.make_task(SPLIT, seed)["task_id"]
                      for seed in FRESH_SEEDS}
    old_digests = {_task_digest(SPLIT, seed) for seed in OLD_E4_SEEDS}
    fresh_digests = {_task_digest(SPLIT, seed) for seed in FRESH_SEEDS}
    blind_changed = sum(row["blind8"]["evidence"] !=
                        row["informed8"]["evidence"] for row in rows)
    # With nothing observed every open input's total disagreement ties, so the
    # frozen "smallest index on ties" returns the lowest unqueried input on
    # every seed. That is what makes the blind column a single subset rather
    # than a sample, and it is why no blind mean can be pinned to a literal.
    blind_is_fixed = len({tuple(row["sequences"]["blind8"]) for row in rows}) == 1
    assert not set(OLD_E4_SEEDS) & set(FRESH_SEEDS)
    assert len(old_task_ids) == len(OLD_E4_SEEDS)
    assert len(fresh_task_ids) == len(FRESH_SEEDS)
    assert len(old_digests) == len(OLD_E4_SEEDS)
    assert len(fresh_digests) == len(FRESH_SEEDS)
    assert not old_task_ids & fresh_task_ids
    assert not old_digests & fresh_digests
    assert all(row["blind8"]["n_queried"] == rules.MAX_QUERIES
               and row["informed8"]["n_queried"] == rules.MAX_QUERIES
               for row in rows)
    # Recompute the two historical numbers without editing their frozen
    # artifact.  The narrow value is the old one-probe boundary; the wide
    # value is the old blind harness described above.
    #
    # `44ec6c52` froze `choose_query` into a total order, so `evidence_ceiling`
    # recomputed under it returns 0.06 rather than the 0.5017 the withdrawn
    # artifact holds. Both numbers are reported, each labelled with the
    # tie-break that produced it, because a reader who saw only "0.06" under
    # the key "withdrawn" would take it for the historical value and conclude
    # the withdrawal was a correction rather than a re-derivation.
    narrow = revision.ceiling(SPLIT, list(OLD_E4_SEEDS))
    withdrawn = revision.evidence_ceiling(SPLIT, list(OLD_E4_SEEDS))

    return {
        "experiment": "E4 evidence-ceiling diagnostic",
        "split": SPLIT,
        "old_e4_seed_range": [OLD_E4_SEEDS[0], OLD_E4_SEEDS[-1]],
        "fresh_seed_range": [FRESH_SEEDS[0], FRESH_SEEDS[-1]],
        "fresh_cohort": {
            "n": len(FRESH_SEEDS),
            "seed_disjoint": True,
            "old_unique_task_ids": len(old_task_ids),
            "fresh_unique_task_ids": len(fresh_task_ids),
            "old_unique_truth_tables": len(old_digests),
            "fresh_unique_truth_tables": len(fresh_digests),
            "task_id_overlap_with_old_e4": len(old_task_ids & fresh_task_ids),
            "truth_table_overlap_with_old_e4": len(old_digests & fresh_digests),
        },
        "arm_semantics": {
            "incumbent": "one fixed probe, [3]",
            "blind8": "choose_query eight times; no learner.observe",
            "informed8": "query task then learner.observe after every pick",
            "primary_metric": "raw per-task overall accuracy",
            "secondary_metric": "raw per-task unqueried-input accuracy",
            "query_counts": {"incumbent": 1, "blind8": 8,
                             "informed8": 8},
            "actual_query_counts": {
                arm: sorted({row[arm]["n_queried"] for row in rows})
                for arm in ("incumbent", "blind8", "informed8")
            },
        },
        "sequence_difference_count": blind_changed,
        "historical_e4_references": {
            "narrow_probe_ceiling": narrow,
            "narrow_probe_ceiling_note": (
                "tie-break-independent: the argmax is over one-input means, "
                "so the freeze cannot move it"),
            "withdrawn_blind8": withdrawn,
            "withdrawn_blind8_interpretation": (
                "historical blind policy range, not evidence-learner headroom"),
            "withdrawn_blind8_note": (
                "RECOMPUTED under the frozen tie-break, so this is NOT the "
                "0.5017 the withdrawn artifact holds. That figure came from a "
                "random 8-subset drawn per seed from an unfrozen "
                "random.Random(seed) tie-break, whose per-cohort mean over "
                "uniform 8-subsets is 0.5195 (sd 0.025 over 20 reps). Both "
                "measure the same quantity; only the tie-break differs, so "
                "the gap between them is the freeze, not a correction."),
        },
        "blind_arm_is_seed_independent": blind_is_fixed,
        "contrasts": {
            "primary_overall": {
                "informed8_vs_blind8_equal_cost": _contrast(
                    rows, "informed8", "blind8", "overall"),
                "blind8_vs_incumbent1_unequal_budget": _contrast(
                    rows, "blind8", "incumbent", "overall"),
                "informed8_vs_incumbent1_unequal_budget": _contrast(
                    rows, "informed8", "incumbent", "overall"),
            },
            "secondary_unqueried": {
                "informed8_vs_blind8_equal_cost": _contrast(
                    rows, "informed8", "blind8", "unqueried"),
                "blind8_vs_incumbent1_unequal_budget": _contrast(
                    rows, "blind8", "incumbent", "unqueried"),
                "informed8_vs_incumbent1_unequal_budget": _contrast(
                    rows, "informed8", "incumbent", "unqueried"),
            },
        },
        "interpretation": (
            "Descriptive offline diagnostic only; it makes no learning, RSI, "
            "or formal statistical-significance claim. The equal-cost "
            "informed8-versus-blind8 overall contrast is primary."
        ),
        "raw_rows": rows,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
