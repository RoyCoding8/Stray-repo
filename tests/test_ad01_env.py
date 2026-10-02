"""AD01 environment: frozen worlds, controls, checker, rotation, seeds.

Model-free lane. Seams are disk (frozen task JSON + manifests, verified in
real subprocesses) and pure in-memory checks. No DB seam exists here, so no
PG tests; no model inference seam exists, so no doubles.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FREEZE_ID = "ad01"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_freeze_id_is_ad01():
    from experiments.ad01 import worlds
    assert worlds.FREEZE_ID == FREEZE_ID


def test_freeze_deterministic_across_processes(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for target in (first, second):
        proc = subprocess.run(
            [sys.executable, "-m", "experiments.ad01.worlds",
             "build", str(target)],
            cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr
    first_files = sorted(p.relative_to(first) for p in first.rglob("*")
                         if p.is_file())
    second_files = sorted(p.relative_to(second) for p in second.rglob("*")
                          if p.is_file())
    assert first_files == second_files
    assert (first / "manifest.json").read_bytes() == \
        (second / "manifest.json").read_bytes()
    assert (first / "manifest.sha256").read_text() == \
        (second / "manifest.sha256").read_text()
    for rel in first_files:
        assert (first / rel).read_bytes() == (second / rel).read_bytes()


def test_committed_freeze_matches_manifest():
    from experiments.ad01 import worlds
    assert worlds.verify_committed() == []


def _committed_tasks():
    from experiments.ad01 import worlds
    root = worlds.FROZEN_DIR
    tasks = []
    for path in sorted(root.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        tasks.append(json.loads(path.read_text()))
    return tasks


def test_overlap_audit_clean_on_committed_freeze():
    from experiments.ad01 import worlds
    assert worlds.audit_committed() == []


def test_overlap_audit_catches_dev_use_leakage():
    from experiments.ad01 import worlds
    tasks = _committed_tasks()
    dev = next(t for t in tasks if "-dev-" in t["task_id"])
    use = next(t for t in tasks if "-within-" in t["task_id"]
               and t["family"] == dev["family"])
    leaked = dict(use)
    if dev["family"] == "software":
        leaked["ops"] = [dict(o) for o in dev["ops"]]
        leaked["fault"] = dev["fault"]
    else:
        leaked["vertices"] = list(dev["vertices"])
        leaked["edges"] = [list(e) for e in dev["edges"]]
    assert worlds.audit_tasks(tasks + [leaked]) != []


def test_overlap_audit_catches_transfer_without_structural_change():
    from experiments.ad01 import worlds
    tasks = _committed_tasks()
    transfer = next(t for t in tasks if "-transfer-" in t["task_id"])
    dev = next(t for t in tasks if "-dev-" in t["task_id"]
               and t["family"] == transfer["family"])
    relabeled = dict(transfer, template=dev["template"])
    swapped = [relabeled if t["task_id"] == transfer["task_id"] else t
               for t in tasks]
    assert worlds.audit_tasks(swapped) != []


def test_overlap_audit_catches_wrong_seed():
    from experiments.ad01 import worlds
    tasks = _committed_tasks()
    victim = tasks[0]
    tampered = dict(victim, seed=victim["seed"] + 1)
    swapped = [tampered if t["task_id"] == victim["task_id"] else t
               for t in tasks]
    assert worlds.audit_tasks(swapped) != []


def _expected_rotation(world: int) -> list:
    order = []
    for index in range(3):
        order.append("ad01-w%d-dev-sw-%02d" % (world, index))
        order.append("ad01-w%d-dev-gr-%02d" % (world, index))
    return order


def test_r_rotation_schedule_exact_all_worlds():
    from experiments.ad01 import rotation
    for world in (0, 1, 2):
        schedule = rotation.r_schedule(world)
        assert [step["task_id"] for step in schedule] == \
            _expected_rotation(world)
        assert [step["seq"] for step in schedule] == list(range(6))
        assert [step["domain"] for step in schedule] == \
            ["software", "graph"] * 3


def test_r_rotation_covers_dev_set_only():
    from experiments.ad01 import rotation, worlds
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    for world in (0, 1, 2):
        dev = {t for tasks in
               membership[str(world)]["dev"].values() for t in tasks}
        scheduled = {s["task_id"] for s in rotation.r_schedule(world)}
        assert scheduled == dev


def test_seed_capabilities_labeled_authored():
    from experiments.ad01 import seeds
    assert len(seeds.SEED_CAPABILITIES) == 4
    for capability in seeds.SEED_CAPABILITIES:
        assert capability["authored"] is True
        assert capability["origin"] == "supplied-rpr01"
        assert "acquired" not in capability
        assert capability["freeze"] == FREEZE_ID


def test_seed_capabilities_cover_both_methods_and_domains():
    from experiments.ad01 import seeds
    assert {(c["method"], c["family"])
            for c in seeds.SEED_CAPABILITIES} == \
        {("ddmin", "software"), ("greedy", "software"),
         ("ddmin", "graph"), ("greedy", "graph")}


def test_seed_runs_yield_checked_candidates():
    from experiments.ad01 import seeds
    from experiments.representation import checkers
    by_id = {c["capability_id"]: c for c in seeds.SEED_CAPABILITIES}
    for capability_id, task_id in (
            ("seed-sw-ddmin", "ad01-w0-dev-sw-00"),
            ("seed-sw-greedy", "ad01-w0-dev-sw-01"),
            ("seed-gr-ddmin", "ad01-w0-dev-gr-00"),
            ("seed-gr-greedy", "ad01-w0-dev-gr-01")):
        task = next(t for t in _committed_tasks()
                    if t["task_id"] == task_id)
        result = seeds.run_seed(by_id[capability_id], task)
        assert result["queries"] <= 16
        check = (checkers.check_software if task["family"] == "software"
                 else checkers.check_graph)
        verdict = check(task, result["candidate"])["verdict"]
        assert verdict == "preserved"


def test_seed_rejects_unknown_capability():
    from experiments.ad01 import seeds
    import pytest
    with pytest.raises(KeyError):
        seeds.run_seed({"capability_id": "acquired-magic",
                        "authored": False}, {})


def _control_labels(record, control_id):
    assert record["control_id"] == control_id
    assert record["authored"] is True
    assert record["origin"] == "ad01-controls"


def test_control_evidence_path_base():
    from experiments.ad01 import controls
    task = controls.load("ad01-w0-dev-sw-00")
    record = controls.evidence_path(task, controls.incumbent(task),
                                    controls.break_candidate(task))
    _control_labels(record, "c0-evidence-path")
    assert record["changed"] is True
    assert record["label_stable"] is True
    same = controls.evidence_path(task, controls.incumbent(task),
                                  controls.incumbent(task))
    assert same["changed"] is False
    dirty = controls.evidence_path(task, controls.incumbent(task),
                                   controls.contaminate(task, "run-9"))
    assert dirty["changed"] is True


def test_control_cheap_suffices():
    from experiments.ad01 import controls
    record = controls.cheap_suffices("ad01-w0-dev-sw-00", "seed-sw-greedy")
    _control_labels(record, "c1-cheap-suffices")
    assert record["accepted"] > 0
    assert record["reduced"] is True
    assert record["status"] in ("locally-irreducible", "budget-exhausted")
    starved = controls.cheap_suffices("ad01-w0-dev-sw-00", "seed-sw-greedy",
                                      max_queries=1)
    assert starved["accepted"] == 0
    assert starved["reduced"] is False


def test_control_dependency_invalidates_naive_deletion():
    from experiments.ad01 import controls
    record = controls.dependency_invalidates("ad01-w0-transfer-sw-00")
    _control_labels(record, "c2-dependency")
    assert record["bulk_verdict"] == "not_preserved"
    assert record["surgical_verdict"] == "preserved"
    assert record["bulk_reason"] == "witness-lost-agree"
    assert record["two_distractors_verdict"] == "preserved"


def test_control_novel_direction_unproductive():
    from experiments.ad01 import controls
    record = controls.novel_order_unproductive("ad01-w0-dev-gr-02",
                                               budget=8)
    _control_labels(record, "c3-novel-unproductive")
    assert record["seed_verdict"] == "preserved"
    assert record["novel_verdict"] == "preserved"
    assert record["novel_final"] > record["seed_final"]
    assert record["winner"] == "seed"
    generous = controls.novel_order_unproductive("ad01-w0-dev-gr-02",
                                                 budget=64)
    assert generous["novel_final"] == generous["seed_final"]
    rigged = controls.compare({"final": 14, "queries": 8},
                              {"final": 10, "queries": 8})
    assert rigged["winner"] == "novel"


def test_control_diagnostic_resolves_uncertainty():
    from experiments.ad01 import controls
    record = controls.diagnostic_resolves("ad01-w0-dev-sw-00")
    _control_labels(record, "c4-diagnostic")
    assert record["diagnostic_verdict"] == "preserved"
    assert record["nondiagnostic_verdict"] == "not_preserved"


def test_control_prior_negative_blocks_repeat(tmp_path):
    from experiments.ad01 import controls
    ledger = controls.NegativeLedger(tmp_path / "negatives.json")
    first = controls.prior_negative(ledger, "ad01-w0-dev-sw-00")
    _control_labels(first, "c5-prior-negative")
    assert first["refused"] is False
    assert first["consumed"] == 1
    repeat = controls.prior_negative(ledger, "ad01-w0-dev-sw-00")
    assert repeat["refused"] is True
    assert repeat["consumed"] == 0
    fresh = controls.NegativeLedger(tmp_path / "negatives.json")
    again = controls.prior_negative(fresh, "ad01-w0-dev-sw-00")
    assert again["refused"] is True
    assert again["consumed"] == 0


def _incumbent_records():
    from experiments.ad01 import checker, worlds
    records = []
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    digest = checker.freeze_digest(worlds.FROZEN_DIR)
    for world in ("0", "1", "2"):
        for arm in ("I", "R"):
            for kind in ("within", "transfer"):
                for domain in ("software", "graph"):
                    for task_id in membership[world][kind][domain]:
                        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                        size = (len(task["ops"])
                                if domain == "software"
                                else len(task["vertices"])
                                + len(task["edges"]))
                        records.append({
                            "record_id": "%s-%s-%s" % (world, arm,
                                                       task_id),
                            "freeze": FREEZE_ID, "freeze_digest": digest,
                            "world": int(world), "arm": arm,
                            "task_id": task_id, "domain": domain,
                            "verdict": "preserved",
                            "initial_measure": size, "final_measure": size,
                            "normalized_reduction": 0.0,
                            "costs": {"tokens": 10, "witness_queries": 2,
                                      "sandbox_ops": 1},
                            "output": task})
    return records


def test_checker_accepts_complete_use_records():
    from experiments.ad01 import checker, worlds
    result = checker.verify_use_records(_incumbent_records(),
                                        worlds.FROZEN_DIR)
    assert result["problems"] == []
    assert result["unevaluable"] == []


def test_checker_rejects_altered_record():
    from experiments.ad01 import checker, worlds
    records = _incumbent_records()
    victim = next(r for r in records
                  if r["task_id"] == "ad01-w0-within-sw-00")
    tampered = dict(victim)
    broken = dict(victim["output"])
    broken["ops"] = broken["ops"][:2]
    tampered["output"] = broken
    swapped = [tampered if r["record_id"] == victim["record_id"] else r
               for r in records]
    result = checker.verify_use_records(swapped, worlds.FROZEN_DIR)
    assert any("quality-mismatch" in p for p in result["problems"])


def test_checker_rejects_missing_record():
    from experiments.ad01 import checker, worlds
    records = _incumbent_records()
    dropped = [r for r in records
               if r["record_id"] != "1-R-ad01-w1-transfer-gr-01"]
    assert len(dropped) == len(records) - 1
    result = checker.verify_use_records(dropped, worlds.FROZEN_DIR)
    assert any("missing-record" in p for p in result["problems"])


def test_checker_rejects_duplicate_record():
    from experiments.ad01 import checker, worlds
    records = _incumbent_records()
    result = checker.verify_use_records(records + [records[0]],
                                        worlds.FROZEN_DIR)
    assert any("duplicate-record" in p for p in result["problems"])


def test_checker_rejects_wrong_freeze_reference():
    from experiments.ad01 import checker, worlds
    records = _incumbent_records()
    for record in records:
        record["freeze"] = "rpr-01"
    result = checker.verify_use_records(records, worlds.FROZEN_DIR)
    assert any("wrong-freeze-reference" in p for p in result["problems"])


def test_checker_rejects_unknown_scored_as_zero():
    from experiments.ad01 import checker, worlds
    records = _incumbent_records()
    victim = next(r for r in records
                  if r["task_id"] == "ad01-w0-within-sw-01")
    masked = dict(victim, verdict="unknown", initial_measure=0,
                  final_measure=0, normalized_reduction=0.0,
                  output=None)
    swapped = [masked if r["record_id"] == victim["record_id"] else r
               for r in records]
    result = checker.verify_use_records(swapped, worlds.FROZEN_DIR)
    assert any("unknown-scored-as-zero" in p for p in result["problems"])


def test_benefit_rule_frozen_and_pinned():
    from experiments.ad01 import benefit, worlds
    manifest = json.loads((worlds.FROZEN_DIR / "manifest.json").read_text())
    assert manifest["benefit_rule_digest"] == benefit.digest()
    assert benefit.BENEFIT_RULE["freeze"] == FREEZE_ID
    assert benefit.BENEFIT_RULE["cost_ratio_limit"] == 1.25


def _benefit_records(improved=False, regressed=False, unknown_cost=False):
    from experiments.ad01 import seeds
    from experiments.representation import checkers
    records = _incumbent_records()
    out = []
    for record in records:
        record = dict(record)
        if record["arm"] == "I" and improved:
            capability = next(
                c for c in seeds.SEED_CAPABILITIES
                if c["family"] == record["domain"]
                and c["method"] == "greedy")
            result = seeds.run_seed(capability, record["output"])
            candidate = result["candidate"]
            check = (checkers.check_software
                     if record["domain"] == "software"
                     else checkers.check_graph)
            assert check(record["output"], candidate)["verdict"] == \
                "preserved"
            size = (len(candidate["ops"])
                    if record["domain"] == "software"
                    else len(candidate["vertices"]) + len(candidate["edges"]))
            record["output"] = candidate
            record["final_measure"] = size
            record["normalized_reduction"] = \
                (record["initial_measure"] - size) / record["initial_measure"]
        if regressed and record["arm"] == "I" and \
                record["domain"] == "software" and record["world"] == 0 \
                and record["task_id"].endswith("-00"):
            broken = dict(record["output"])
            broken["ops"] = broken["ops"][:2]
            record = dict(record, verdict="not_preserved",
                          normalized_reduction=0.0, output=broken)
        if unknown_cost and record["record_id"].endswith(
                "ad01-w0-within-sw-00"):
            costs = dict(record["costs"])
            costs["tokens"] = "unknown"
            record = dict(record, costs=costs)
        out.append(record)
    return out


def test_benefit_evaluation():
    from experiments.ad01 import benefit, worlds
    good = _benefit_records(improved=True)
    assert checker_clean(good) == []
    verdict = benefit.evaluate(good)
    assert verdict["verdict"] == "benefit", verdict["reasons"]
    tied = _benefit_records()
    assert benefit.evaluate(tied)["verdict"] == "no-benefit"
    regressed = _benefit_records(improved=True, regressed=True)
    assert benefit.evaluate(regressed)["verdict"] == "no-benefit"
    unknown = _benefit_records(improved=True, unknown_cost=True)
    assert benefit.evaluate(unknown)["verdict"] == "unevaluable"


def checker_clean(records):
    from experiments.ad01 import checker, worlds
    return checker.verify_use_records(records,
                                      worlds.FROZEN_DIR)["problems"]


def test_agency_surface_namespaces_distinguishable():
    from experiments.ad01 import records
    assert set(records.AGENCY_SCHEMA["human_set"]) & \
        set(records.AGENCY_SCHEMA["system_chosen"]) == set()
    envelope = records.make_envelope(
        {"objective": "smaller-valid-examples",
         "freeze_id": FREEZE_ID},
        {"selected_opportunity": "cost-pattern-3",
         "diagnostic": "keep-only-chain"})
    for key, field in envelope["charter"].items():
        assert field["set_by"] == "human", key
    for key, field in envelope["trajectory"].items():
        assert field["set_by"] == "system", key
    assert set(envelope["charter"]) & set(envelope["trajectory"]) == set()


def test_agency_surface_rejects_mixed_provenance():
    from experiments.ad01 import records
    import pytest
    with pytest.raises(ValueError):
        records.make_envelope({"selected_opportunity": "x"}, {})
    with pytest.raises(ValueError):
        records.make_envelope({}, {"objective": "y"})
    with pytest.raises(ValueError):
        records.make_envelope({"objective": "y", "mystery": 1}, {})


def test_agency_surface_records_interventions():
    from experiments.ad01 import records
    envelope = records.make_envelope({"objective": "smaller-valid-examples"},
                                     {"selected_opportunity": "q"})
    updated = records.record_intervention(envelope, "stop",
                                          "allocation-exhausted")
    interventions = updated["charter"]["interventions"]["value"]
    assert interventions[-1] == {"kind": "stop",
                                 "reason": "allocation-exhausted",
                                 "set_by": "human"}
    assert updated["charter"]["interventions"]["set_by"] == "human"
    blob = json.loads(json.dumps(updated))
    assert blob == updated
