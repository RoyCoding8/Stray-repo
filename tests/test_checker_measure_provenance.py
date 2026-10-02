from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VICTIM_TASK = "ad01-w0-within-sw-00"


def _measure(candidate: dict) -> int:
    if candidate["family"] == "software":
        return len(candidate["ops"])
    return len(candidate["vertices"]) + len(candidate["edges"])


def _improved_records() -> tuple[list[dict], dict]:
    from experiments.ad01 import checker, seeds, worlds
    from experiments.representation import checkers

    digest = checker.freeze_digest(worlds.FROZEN_DIR)
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    records = []
    for world in ("0", "1", "2"):
        for arm in ("I", "R"):
            for kind in ("within", "transfer"):
                for domain in ("software", "graph"):
                    for task_id in membership[world][kind][domain]:
                        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                        initial = _measure(task)
                        records.append({
                            "record_id": "%s-%s-%s" % (world, arm, task_id),
                            "freeze": worlds.FREEZE_ID, "freeze_digest": digest,
                            "world": int(world), "arm": arm,
                            "task_id": task_id, "domain": domain,
                            "verdict": "preserved",
                            "initial_measure": initial,
                            "final_measure": initial,
                            "normalized_reduction": 0.0,
                            "costs": {"tokens": 10, "witness_queries": 2,
                                      "sandbox_ops": 1},
                            "output": task})

    victim = next(record for record in records
                  if record["task_id"] == VICTIM_TASK)
    task = worlds.load_task(worlds.FROZEN_DIR, VICTIM_TASK)
    capability = next(candidate for candidate in seeds.SEED_CAPABILITIES
                      if candidate["family"] == "software"
                      and candidate["method"] == "greedy")
    candidate = seeds.run_seed(capability, task)["candidate"]
    check = (checkers.check_software if victim["domain"] == "software"
             else checkers.check_graph)
    assert check(task, candidate)["verdict"] == "preserved"
    final = _measure(candidate)
    victim["output"] = candidate
    victim["final_measure"] = final
    victim["normalized_reduction"] = (
        (victim["initial_measure"] - final) / victim["initial_measure"])
    return records, victim


def test_forged_initial_measure_is_unevaluable():
    from experiments.ad01 import checker, worlds

    records, victim = _improved_records()
    final = victim["final_measure"]
    forged = dict(victim, initial_measure=1_000_000,
                  normalized_reduction=(1_000_000 - final) / 1_000_000)
    records = [forged if record is victim else record for record in records]

    result = checker.verify_use_records(records, worlds.FROZEN_DIR)

    assert result["problems"] == []
    assert result["unevaluable"] == [
        "measure-mismatch %s" % forged["record_id"]]


def test_forged_final_measure_is_a_problem():
    from experiments.ad01 import checker, worlds

    records, victim = _improved_records()
    forged = dict(victim, final_measure=victim["initial_measure"] - 1)
    records = [forged if record is victim else record for record in records]

    result = checker.verify_use_records(records, worlds.FROZEN_DIR)

    assert result["problems"] == [
        "measure-mismatch %s" % forged["record_id"]]
    assert result["unevaluable"] == []


def test_legitimate_initial_measure_verifies_clean():
    from experiments.ad01 import checker, worlds

    records, _ = _improved_records()

    result = checker.verify_use_records(records, worlds.FROZEN_DIR)

    assert result == {"problems": [], "unevaluable": []}
