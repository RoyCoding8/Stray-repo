"""The reader-against-echoer ordering, and the two mutations that break it.

The scorer separates a policy that reads the verdicts and re-routes from one
that copies them into an input key and decides nothing. That claim is worth
nothing unless it can be shown to fail when the separation is removed, so
this module measures the ordering three times: as it stands, with the leg
reverted to the input comparison it replaced, and with the candidate
comparison forced to report no movement.

Each mutation is applied to a copy of the source in a temporary directory
and is confirmed to have landed by asserting the exact replacement count
before anything is measured. A string replace that hits an identical block
in a different branch would otherwise report a green that was never earned,
which is the failure this file exists to make impossible.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

SCORED = Path(__file__).resolve().parents[3] / "experiments" / "ad01" / "s09_e2_scored.py"

ACTORS = (
    ("reader", "PROMPTED_SHAPE_READER"),
    ("echoer", "ECHOES_WITHOUT_READING"),
    ("blind", "IGNORES_THE_VIEW"),
    ("plan-only-reader", "READS_THE_VERDICT"),
)

CANDIDATE_BLOCK = '''    first = scored["candidate"]
    second = alternate["candidate"]
    first_digest, second_digest = _candidate_digest(first), \\
        _candidate_digest(second)
    varied = 1 if first_digest != second_digest else 0
    return {"varied": varied, "total": 1, "sites": [CANDIDATE_SITE],
            "ratio": float(varied),
            "scored_inputs": dict(scored["action"].get("inputs") or {}),
            "alternate_inputs": dict(alternate["action"].get("inputs") or {}),
            "control_inputs": _without_verbatim(
                dict(scored["action"].get("inputs") or {})),
            "candidate_digest_scored": first_digest,
            "candidate_digest_alternate": second_digest}'''

INPUT_BLOCK = '''    first = dict(scored["action"].get("inputs") or {})
    second = dict(alternate["action"].get("inputs") or {})
    sites, varied = [], 0
    for name in sorted(set(first) | set(second)):
        if name in VERBATIM:
            continue
        if first.get(name) != second.get(name):
            varied += 1
        sites.append(name)
    first_digest = second_digest = ""
    return {"varied": varied, "total": len(sites), "sites": sites,
            "ratio": varied / len(sites) if sites else 0.0,
            "scored_inputs": first, "alternate_inputs": second,
            "control_inputs": _without_verbatim(first),
            "candidate_digest_scored": first_digest,
            "candidate_digest_alternate": second_digest}'''

MUTATIONS = (
    {
        "name": "leg-reverted-to-action-inputs",
        "description": "the observable the correction replaced: compare the"
                       " two runs' action inputs instead of the candidates"
                       " the world produced. The whole leg body is replaced,"
                       " not just its first statement, so the reverted leg is"
                       " the old leg rather than a hybrid of the two",
        "old": CANDIDATE_BLOCK,
        "new": INPUT_BLOCK,
    },
    {
        "name": "candidate-comparison-disabled",
        "description": "the leg reports the candidate as never moving, so a"
                       " scorer that cannot detect a read would look exactly"
                       " like this one",
        "old": "    varied = 1 if first_digest != second_digest else 0",
        "new": "    varied = 0  # mutated: candidate comparison disabled",
    },
)


def measure(target: dict, observations: list, eligible_methods: list) -> dict:
    """Score every actor once, in the scorer currently importable."""
    import json as _json

    from experiments.ad01 import e2_replication as replica
    from experiments.ad01 import s09_e2_scored as scorer

    scores = {}
    for name, attribute in ACTORS:
        source = getattr(replica, attribute)
        reading = scorer.score_response(
            _json.dumps({"entry": source}), dict(target), list(observations),
            origin="authored-control", arm=name,
            eligible_methods=list(eligible_methods), remaining={"steps": 1})
        scores[name] = {
            "scored": reading.scored,
            "score": reading.score,
            "evidence": reading.evidence,
            "candidate_moved": (reading.candidate_digest_scored
                                != reading.candidate_digest_alternate),
            "candidate_digest_scored": reading.candidate_digest_scored,
            "candidate_digest_alternate": reading.candidate_digest_alternate,
            "detail": reading.detail,
        }
    return scores


def ordering(scores: dict) -> dict:
    reader = scores.get("reader") or {}
    echoer = scores.get("echoer") or {}
    return {
        "reader_score": reader.get("score"),
        "echoer_score": echoer.get("score"),
        "reader_above_echoer": (reader.get("score") is not None
                                and echoer.get("score") is not None
                                and reader["score"] > echoer["score"]),
        "gap": (None if reader.get("score") is None
                else reader["score"] - echoer["score"]),
    }


def _apply_and_measure(mutation: dict, target: dict, observations: list,
                       eligible_methods: list) -> dict:
    """Mutate a copy of the scorer, measure, and restore.

    The replace is asserted to land exactly once before anything is measured.
    The scorer module is reloaded from the mutated file so the measurement
    cannot read a cached copy of the original.
    """
    import importlib

    source = SCORED.read_text(encoding="utf-8")
    count = source.count(mutation["old"])
    if count != 1:
        return {"mutation": mutation["name"], "landed": False,
                "matches_found": count,
                "error": "the replacement did not land exactly once, so no"
                         " measurement from it would mean anything"}
    mutated = source.replace(mutation["old"], mutation["new"])
    backup = SCORED.read_text(encoding="utf-8")
    try:
        SCORED.write_text(mutated, encoding="utf-8")
        from experiments.ad01 import s09_e2_scored as scorer
        importlib.reload(scorer)
        scores = measure(target, observations, eligible_methods)
        return {"mutation": mutation["name"],
                "description": mutation["description"],
                "landed": True, "matches_found": count,
                "scores": scores, "ordering": ordering(scores),
                "scores_within_max": all(
                    (row["score"] or 0.0) <= scorer.MAX_SCORE
                    for row in scores.values()),
                "max_score": scorer.MAX_SCORE}
    finally:
        SCORED.write_text(backup, encoding="utf-8")
        importlib.reload(scorer)


def instrument_evidence(target: dict, observations: list,
                        eligible_methods: list) -> dict:
    from experiments.ad01 import s09_e2_scored as scorer

    baseline = measure(target, observations, eligible_methods)
    return {
        "schema": "e2-replica-r2-instrument-v1",
        "leg": scorer.LEG_EVIDENCE,
        "observable": "the candidate the world produced, compared across the"
                      " arm's own verdicts and the flipped ones",
        "baseline": {"scores": baseline, "ordering": ordering(baseline)},
        "mutations": [_apply_and_measure(m, target, observations,
                                        eligible_methods)
                      for m in MUTATIONS],
    }


def main() -> int:
    from experiments.ad01 import e2_replication as replica
    from experiments.ad01 import learner, worlds

    body = replica.verify_freeze(replica.freeze())
    task_id = body["target_task_ids"][0]
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    visible = learner.visible_opportunities(body["cohort_world"])
    arms = replica.arms_for(task, source_task_ids=body["source_task_ids"],
                            filler_task_ids=body["filler_task_ids"],
                            visible=visible)
    evidence = instrument_evidence(
        task, arms[replica.ARM_RELEVANT]["observations"],
        replica.eligible_for(task))
    evidence["target_task_id"] = task_id
    out = Path(__file__).resolve().parent / "instrument_evidence.json"
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True),
                   encoding="utf-8")
    print(json.dumps(evidence["baseline"]["ordering"], indent=2,
                     sort_keys=True))
    for mutation in evidence["mutations"]:
        print("%s landed=%s reader_above_echoer=%s"
              % (mutation["mutation"], mutation.get("landed"),
                 (mutation.get("ordering") or {}).get("reader_above_echoer")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
