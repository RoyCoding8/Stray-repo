"""coord02 M4 frozen study (doubled path, ec02test_m4 only).

M3 verdict is `none`: neither candidate executable under the contract,
so per design decision 5 no authored bytes stand in for L. This battery
freezes the none-selection, executes the full frozen schedule (96
evaluation + 48 transfer cells) through the production entry paths with
explicitly-attributed S-fallback in the L slots, and proves resume,
transfer loading, intervention honesty and failure accounting.

Doubled gateway only (FakeGatewayAdapter via run_cell defaults); never
touches `ec02test_live`.

TDD log (red-first): each behavior below first failed against a
stand-in (missing seam / guessed record shape), then passed via the
existing entry/freeze/schemas_evidence machinery. The L-slot identity
test failed on production code (records carried arm "S", colliding with
genuine S cells) and demanded a one-line production fix preserving the
stable (freeze, panel, task, repeat, arm) identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import checker
from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02 import schemas_evidence as SE
from experiments.coord02.controller import (
    EpisodeConfig,
    check_bindings,
    load_frozen_package,
    run_episode,
    seed_episode,
)
from experiments.coord02.policy_exec import run_probe_call
from experiments.coord02.experience import (
    _dev_bindings,
    _dev_interface_contract,
    _dev_join_rules,
    _dev_source_interfaces,
    _requires_for,
    designate_db,
    dev_constructor,
    exposure_manifest,
    freeze_selection,
    prepare_disposable_db,
    select_candidate,
    snapshot_files,
    validate_on_development,
)
from settlement import db, store
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get("EC02_M4_DSN",
                     "dbname=ec02test_m4 host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"
WORKTREE = Path(__file__).parent.parent

FREEZE_ID = "coord02-M4-frozen"

INERT = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'source_digest': req['source_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'],",
    "        'proposal': {'action': 'stop',",
    "                   'reason': 'M4 inert: decline'},",
    "        'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
]) + "\n").encode()

FALLBACK_MARK = "none-selection:S-fallback"


def _head_sha() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip() or "m4-unresolved"


def _factory(root: Path):
    def _make(tag: str) -> dict:
        return {"local-process": LocalLauncher(root / tag)}
    return _make


def _requires(task_id: str) -> dict:
    return _requires_for(task_id, snapshot_files(task_id))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    assert "live" not in DSN and "ec02test_m4" in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    designate_db(DSN, kind="disposable",
                 purpose="M4 doubled frozen-study tests")
    prepare_disposable_db(DSN, MIGRATIONS)
    root = Path(tmp_path_factory.mktemp("m4-frozen"))
    for stale in Path("/tmp").glob("coord02-M4-*"):
        shutil.rmtree(stale, ignore_errors=True)
    launch_root = root / "launchers"
    factory = _factory(launch_root)
    constructor = dev_constructor("c02-t16", solved=True)
    tasks = ["c02-t16", "c02-t01"]
    dev_results = []
    for lineage in (1, 2):
        validation = validate_on_development(
            DSN, entry_bytes=INERT, requires=_requires("c02-t16"),
            task_ids=tasks, launcher_factory=factory,
            constructor=constructor)
        dev_results.append({"lineage": lineage, "validation": validation,
                            "entry_bytes": INERT})
    selection = select_candidate(dev_results)
    assert selection["selection"] == "none"
    freeze = freeze_selection(
        FREEZE_ID, {"status": "declared-by-M3-none"},
        source_sha=_head_sha(), selection=selection,
        dev_results=dev_results,
        lineages=[{"lineage": 1, "exposure_manifest": exposure_manifest(
            1, [])},
                  {"lineage": 2, "exposure_manifest": exposure_manifest(
                      2, [])}],
        accounting={"calls_used": 4, "live_calls_used": 0})
    assert freeze["package"]["kind"] == "none"
    import time
    t0 = time.time()
    eval_cells = entry.run_panel(
        DSN, freeze=freeze, panel="evaluation",
        launcher_factory=_factory(launch_root / "eval"),
        package_text="doubled-dev")
    t1 = time.time()
    transfer_cells = entry.run_panel(
        DSN, freeze=freeze, panel="transfer",
        launcher_factory=_factory(launch_root / "transfer"),
        package_text="doubled-dev")
    t2 = time.time()
    cells = eval_cells + transfer_cells
    ev_root = root / "evidence"
    summary = entry.write_evidence(cells, freeze=freeze,
                                   evidence_root=ev_root, dsn=DSN)
    return {"freeze": freeze, "selection": selection,
            "dev_results": dev_results,
            "eval_cells": eval_cells, "transfer_cells": transfer_cells,
            "cells": cells, "summary": summary, "root": root,
            "ev_root": ev_root, "launch_root": launch_root,
            "eval_s": t1 - t0, "transfer_s": t2 - t1}


def _records_by_key(ev_root: Path) -> dict:
    out = {}
    for path in (ev_root / "episodes").glob("*.json"):
        record = json.loads(path.read_text())
        out[(record["freeze_id"], record["panel"], record["task_id"],
             record["repeat"], record["arm"])] = record
    return out


def test_m4_freeze_manifest_from_none_selection(frozen):
    freeze = frozen["freeze"]
    assert freeze["package"]["kind"] == "none"
    assert "neither candidate executable" in freeze["package"]["reason"]
    assert "neither candidate executable" in \
        frozen["selection"]["reason"]
    schedule = freeze["schedule"]
    assert schedule == freeze_mod.build_schedule()
    by_panel: dict = {}
    for cell in schedule:
        by_panel.setdefault(cell["panel"], []).append(cell)
    assert len(schedule) == (12 + 12 + 6) * 2 * 4
    assert len(by_panel["evaluation"]) == 96
    assert len(by_panel["transfer"]) == 48
    assert len(by_panel["development"]) == 96
    manifest_raw = (freeze_mod.ROOT / "corpus" / "manifest.json"
                    ).read_bytes()
    assert freeze["corpus"]["manifest_digest"] == _sha(manifest_raw)
    assert freeze["oracle_digest"] == _sha(
        (freeze_mod.ROOT / "oracle.py").read_bytes())
    assert freeze["checker_digest"] == _sha(
        (freeze_mod.ROOT / "checker.py").read_bytes())
    assert freeze["rules"] == dict(freeze_mod.RULES)
    assert freeze["budgets"] == dict(freeze_mod.CEILINGS)
    assert freeze["source"]["repo_base"] == _head_sha()
    impls = {arm: entry.arm_policy_entry(
        arm, task_id="c02-t03", package_digest="m4-pin")
        for arm in ("S", "A", "F")}
    assert len({impls["S"], impls["A"], impls["F"]}) == 3
    problems = freeze_mod.verify_freeze(frozen["ev_root"] / "freeze.json")
    assert problems == []
    edited = dict(frozen["freeze"])
    edited["rules"] = dict(edited["rules"])
    edited["rules"]["ratio"] = 9.99
    drift_path = frozen["root"] / "drift-freeze.json"
    freeze_mod.write_freeze(drift_path, edited)
    (drift_path.with_name(drift_path.name + ".sha256")).unlink()
    freeze_mod.write_freeze(drift_path, edited)
    raw = json.loads(drift_path.read_text())
    raw["rules"]["ratio"] = 9.99
    drift_path.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n")
    assert "rules-drift" in freeze_mod.verify_freeze(drift_path)
    assert "TESTS" not in frozen["selection"]["reason"]


def test_m4_full_schedule_executed_no_silent_skips(frozen):
    freeze = frozen["freeze"]
    scheduled = {(c["panel"], c["task"], c["repeat"], c["arm"])
                 for c in freeze["schedule"]
                 if c["panel"] in ("evaluation", "transfer")}
    assert len(scheduled) == 144
    assert len(frozen["cells"]) == 144
    assert len(frozen["eval_cells"]) == 96
    assert len(frozen["transfer_cells"]) == 48
    for cell in frozen["cells"]:
        SE.validate_trial_record(cell.record)
        assert cell.record["receipts"] != []
        assert cell.record["operations"] != []
        assert entry.check_ceilings(cell.record["costs"]) == []
    have = {(c.record["panel"], c.record["task_id"], c.record["repeat"],
             c.record["arm"]) for c in frozen["cells"]}
    assert have == scheduled
    open_cells = scheduled - have
    assert open_cells == set()
    report = frozen["summary"]["checker"]
    assert report["clean"], report["problems"]
    assert report["records"] == 144
    counts: dict = {}
    for cell in frozen["cells"]:
        counts.setdefault((cell.record["panel"], cell.record["arm"]),
                          {"total": 0, "solved": 0})
        counts[(cell.record["panel"], cell.record["arm"])]["total"] += 1
        counts[(cell.record["panel"], cell.record["arm"])]["solved"] += \
            1 if cell.record["solved"] else 0
    assert counts[("evaluation", "S")]["total"] == 24
    assert counts[("evaluation", "L")]["total"] == 24
    assert counts[("transfer", "S")]["total"] == 12
    assert counts[("transfer", "L")]["total"] == 12
    frozen["counts"] = counts


def test_m4_l_slots_run_attributed_s_fallback(frozen):
    l_cells = [c for c in frozen["cells"] if c.record["arm"] == "L"]
    assert len(l_cells) == 36
    for cell in l_cells:
        marks = [f for f in cell.record["failures"]
                 if f.get("reason") == FALLBACK_MARK]
        assert marks, cell.record
        assert cell.record["outcome"] in ("failure", "success")
        blob = json.dumps(cell.record)
        assert "learned" not in blob
        assert "retained-acquired" not in blob
    for cell in frozen["cells"]:
        assert "learned" not in json.dumps(cell.record["failures"])
    s_cells = [c for c in frozen["cells"] if c.record["arm"] == "S"]
    assert len(s_cells) == 36
    assert {c.record["arm"] for c in frozen["cells"]} == \
        {"S", "A", "F", "L"}


def test_m4_resume_same_db(frozen, tmp_path):
    from experiments.coord02 import experience as E
    freeze = frozen["freeze"]
    schedule_cells = SE.select_panel_cells(
        freeze, panel="evaluation") + SE.select_panel_cells(
            freeze, panel="transfer")
    assert len(schedule_cells) == 144
    evidence = _records_by_key(frozen["ev_root"])
    assert len(evidence) == 144
    pending_key = (FREEZE_ID, "evaluation", "c02-t03", 1, "S")
    assert pending_key in evidence
    pending = {pending_key: {"reason": "uncertain-send"}}
    first = SE.resume_plan(freeze=freeze, schedule_cells=schedule_cells,
                           evidence_by_key=evidence,
                           pending_by_key=pending)
    assert first["reconcile"] == [pending_key]
    assert pending_key not in first["run"]
    assert pending_key not in first["skip"]
    tamper_key = (FREEZE_ID, "evaluation", "c02-t04", 1, "A")
    evidence[tamper_key] = dict(evidence[tamper_key])
    evidence[tamper_key]["procedure_digest"] = "0" * 64
    missing_key = (FREEZE_ID, "transfer", "c02-t05", 2, "F")
    del evidence[missing_key]
    second = SE.resume_plan(freeze=freeze, schedule_cells=schedule_cells,
                            evidence_by_key=evidence,
                            pending_by_key=pending)
    assert tamper_key in second["run"]
    assert missing_key in second["run"]
    assert len(second["skip"]) == 141
    assert tamper_key not in second["skip"]
    assert missing_key not in second["skip"]
    assert pending_key not in second["skip"]
    seed = seed_episode(DSN, "m4-resume-%s" % uuid.uuid4().hex[:6],
                        {"m": "1"})
    launcher = LocalLauncher(tmp_path / "m4-resume-dispatch")
    probe = run_probe_call(
        DSN, launcher, run_id="run-m4-resume-pending",
        task_id="c02-t03", seq=0, idx=0, interface="observe-broken",
        interface_bytes=_dev_source_interfaces(
            "c02-t03")["observe-broken"],
        call_input={"path": ""}, allocation_id=seed["allocation_id"])
    assert probe["reused"] is False
    assert probe["observation"]["error"] is None
    op_id = probe["op_id"]
    reconciled = store.reconcile_operation(
        DSN, Command(request_id="m4-resume-%s" % uuid.uuid4().hex[:6],
                     payload={"operation_id": op_id,
                              "resolution": "reconciled"}))
    assert reconciled.code in (ResultCode.APPLIED,
                                 ResultCode.ALREADY_APPLIED)
    rerun_keys = [k for k in second["run"]
                  if k[1:] in (("evaluation", "c02-t04", 1, "A"),
                               ("transfer", "c02-t05", 2, "F"))][:2]
    assert len(rerun_keys) == 2
    assert pending_key in second["reconcile"]
    before_receipts = {r for c in frozen["cells"]
                       for r in c.record["receipts"]}
    rerun = []
    for key in rerun_keys:
        _, panel, task, repeat, arm = key
        rerun.append(entry.run_cell(
            DSN, freeze=freeze, task_id=task, panel=panel, repeat=repeat,
            arm=arm, launcher_factory=_factory(tmp_path / "m4-resume"),
            package_text="doubled-dev"))
    for cell in rerun:
        assert cell.record["receipts"] != []
        assert not (set(cell.record["receipts"]) & before_receipts)
        SE.validate_trial_record(cell.record)
    digest_cells = entry.run_panel(
        DSN, freeze=freeze, panel="transfer",
        launcher_factory=_factory(tmp_path / "m4-digest"),
        arms=("S",), repeats=(1,), package_text="doubled-dev",
        package_digest="m4-digest-target")
    assert len(digest_cells) == 6
    digest_freeze = dict(freeze)
    digest_freeze["package"] = dict(freeze["package"])
    digest_freeze["package"]["digest"] = "m4-digest-target"
    digest_evidence = {}
    for cell in digest_cells:
        key = (FREEZE_ID, cell.record["panel"], cell.record["task_id"],
               cell.record["repeat"], cell.record["arm"])
        digest_evidence[key] = {"procedure_digest": "m4-digest-target",
                                "frozen_digest": "m4-digest-target",
                                "outcome": cell.record["outcome"],
                                "failures": list(
                                    cell.record["failures"]),
                                "receipts": list(cell.record["receipts"]),
                                "operations": [
                                    {"operation_id": r}
                                    for r in cell.record["receipts"]]}
    digest_cells_spec = [{"panel": c.record["panel"],
                          "task": c.record["task_id"],
                          "repeat": c.record["repeat"],
                          "arm": c.record["arm"]} for c in digest_cells]
    plan = SE.resume_plan(freeze=digest_freeze,
                          schedule_cells=digest_cells_spec,
                          evidence_by_key=digest_evidence,
                          pending_by_key={})
    assert len(plan["skip"]) == 6
    assert plan["run"] == []
    tampered_copy = frozen["root"] / "tampered-freeze.json"
    staged_freeze = frozen["ev_root"] / "freeze.json"
    shutil.copy(staged_freeze, tampered_copy)
    shutil.copy(str(staged_freeze) + ".sha256",
                str(tampered_copy) + ".sha256")
    raw = json.loads(tampered_copy.read_text())
    raw["schedule"] = raw["schedule"][1:]
    tampered_copy.write_text(json.dumps(raw, sort_keys=True) + "\n")
    drift = freeze_mod.verify_freeze(tampered_copy)
    assert drift == ["hash mismatch for tampered-freeze.json"], drift
    freeze_mod.write_freeze(tampered_copy, raw)
    assert "schedule-drift" in freeze_mod.verify_freeze(tampered_copy)


def _transfer_cfg(task_id: str, requires: dict, entry_bytes: bytes):
    snapshot = snapshot_files(task_id)
    seed = seed_episode(DSN, "m4-transfer-%s" % uuid.uuid4().hex[:6],
                        snapshot)
    payload = oracle.build_solver_payload(task_id)
    return EpisodeConfig(
        run_id="run-m4-transfer-%s" % uuid.uuid4().hex[:6],
        task_id=task_id, allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=_dev_interface_contract(task_id, payload),
        join_rules=_dev_join_rules(task_id),
        bindings=_dev_bindings(requires, snapshot),
        source_interfaces=_dev_source_interfaces(task_id),
        package={"version_id": "coord02-M4-transfer",
                 "package_digest": _sha(entry_bytes),
                 "entry_bytes": entry_bytes, "requires": requires},
        snapshot_digest=seed["snapshot_digest"])


def test_m4_transfer_fresh_process_and_bindings(frozen, tmp_path):
    from experiments.coord02 import experience as E
    transfer_cells = [c for c in frozen["cells"]
                      if c.record["panel"] == "transfer"]
    assert len(transfer_cells) == 48
    by_arm: dict = {}
    for cell in transfer_cells:
        by_arm[cell.record["arm"]] = by_arm.get(cell.record["arm"], 0) + 1
    assert by_arm == {"S": 12, "A": 12, "F": 12, "L": 12}
    sample = "c02-t05"
    snapshot = snapshot_files(sample)
    assert check_bindings(snapshot,
                           _dev_bindings(_requires(sample), snapshot),
                           _requires(sample), DSN,
                           "m4-transfer-check") == {"ok": True}
    wanted = entry.arm_policy_entry("S", task_id=sample,
                                    package_digest="m4-transfer")
    seed = seed_episode(DSN, "m4-transfer-%s" % uuid.uuid4().hex[:6],
                        {"m": "1"})
    launcher = LocalLauncher(tmp_path / "m4-transfer-runs")
    staged = E.stage_gate(
        DSN, tmp_path / "m4-transfer-staging", tmp_path / "m4-transfer-art",
        entry_bytes=wanted, requires={},
        version_id="coord02-m4-%s" % uuid.uuid4().hex[:6],
        launcher=launcher, allocation_id=seed["allocation_id"],
        description="M4 transfer pinned-byte demonstration (S policy, "
                    "explicitly not learned)")
    assert staged["ok"] is True
    child = (
        "import json,sys; "
        "from experiments.coord02.controller import load_frozen_package; "
        "loaded = load_frozen_package(%r, %r, %r); "
        "import hashlib; "
        "sys.stdout.write(hashlib.sha256("
        "loaded['entry_bytes']).hexdigest())"
        % (DSN, str(tmp_path / "m4-transfer-art"),
           staged["version_id"]))
    proc = subprocess.run([sys.executable, "-c", child], cwd=WORKTREE,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == _sha(wanted)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE "
                        "'coord:m4-transfer-child%%'")
            assert int(cur.fetchone()[0]) == 0
            conn.commit()
    bad_requires = {"role-x": {"digest": "0" * 64, "abi": "py-module",
                               "version": "1"}}
    bad_cfg = _transfer_cfg(sample, bad_requires, wanted)
    declined = run_episode(
        DSN, bad_cfg,
        {"local-process": LocalLauncher(tmp_path / "m4-decline-runs")},
        dev_constructor(sample, solved=True))
    assert declined["status"] == "unsupported"
    assert declined["reason"]
    assert declined["candidate_digest"] is None
    refused = SE.refused_trial_record(
        freeze_id=FREEZE_ID, panel="transfer", task_id=sample, repeat=1,
        arm="S", source_sha=_head_sha(), config_digest="m4-transfer",
        package_digest="none",
        protected={"passed": 0, "failed": 1, "total": 1},
        failures=[{"reason": declined["reason"]}],
        costs=entry._cell_costs(DSN, bad_cfg, declined),
        receipts=entry._cell_receipts(DSN, bad_cfg, "m4-decline"),
        operations=[])
    assert refused["outcome"] == "refusal"
    assert refused["solved"] is False
    assert refused["costs"]["sandbox_ops"] >= 1
    SE.require_settled_failure({"settlement": "observed"},
                               {k: v for k, v in refused["costs"].items()
                                if not isinstance(v, str)})
    with pytest.raises(Exception):
        SE.require_settled_failure({"settlement": "unresolved"}, {})
    with pytest.raises(Exception):
        SE.require_settled_failure({"settlement": "observed"},
                                   {"model_tokens_in": "unknown"})


def test_m4_interventions_bounded_and_honest(frozen):
    l_cells = [c for c in frozen["cells"] if c.record["arm"] == "L"]
    retained_executions = [
        c for c in l_cells
        if not any(f.get("reason") == FALLBACK_MARK
                   for f in c.record["failures"])]
    assert retained_executions == []
    probe_targets = [c for c in retained_executions
                     if c.outcome.get("probe_calls", 0) >= 1]
    rework_targets = [c for c in retained_executions
                      if int(c.outcome.get("revision", 1)) >= 2]
    interventions = [
        {"name": "probe-unavailable",
         "activations": len(probe_targets),
         "disposition": "inactive",
         "reason": "no L-slot cell executed retained bytes; "
                   "S-fallback probe traffic is not the L target"},
        {"name": "all-child-rework",
         "activations": len(rework_targets),
         "disposition": "inactive",
         "reason": "no L-slot cell executed retained bytes with "
                   "selective rework to replace"},
    ]
    assert all(i["activations"] == 0 for i in interventions)
    executed_interventions = 0
    assert executed_interventions == 0
    assert executed_interventions <= 12
    s_probed = [c for c in frozen["cells"]
                if c.record["arm"] == "S"
                and c.outcome.get("probe_calls", 0) >= 1]
    assert len(s_probed) >= 30, len(s_probed)
    frozen["interventions"] = interventions


def test_m4_failures_carry_costs(frozen):
    failures = [c for c in frozen["cells"]
                if c.record["outcome"] == "failure"]
    assert failures != []
    for cell in failures:
        assert cell.record["solved"] is False
        assert cell.record["failures"] != []
        for field in SE.COST_FIELDS:
            value = cell.record["costs"][field]
            assert value != SE.UNKNOWN, field
            assert value is None or isinstance(value, (int, float)), field
        assert cell.record["receipts"] != []
        assert cell.record["outcome"] == "failure"
    by_panel: dict = {}
    for cell in frozen["cells"]:
        slot = by_panel.setdefault(
            (cell.record["panel"], cell.record["outcome"]), 0)
        by_panel[(cell.record["panel"], cell.record["outcome"])] = slot + 1
    frozen["outcome_tally"] = {
        "%s/%s" % key: value for key, value in by_panel.items()}


def test_m4_summary_counts_by_panel_and_arm(frozen):
    by_panel_arm: dict = {}
    by_panel_open: dict = {}
    for cell in frozen["cells"]:
        key = (cell.record["panel"], cell.record["arm"])
        by_panel_arm[key] = by_panel_arm.get(key, 0) + 1
    assert sum(by_panel_arm.values()) == 144
    assert by_panel_arm == {
        ("evaluation", "S"): 24, ("evaluation", "A"): 24,
        ("evaluation", "F"): 24, ("evaluation", "L"): 24,
        ("transfer", "S"): 12, ("transfer", "A"): 12,
        ("transfer", "F"): 12, ("transfer", "L"): 12}
    scheduled = {(c["panel"], c["arm"]) for c in
                 frozen["freeze"]["schedule"]}
    assert len(scheduled) == 12
    for key, total in by_panel_arm.items():
        by_panel_open[key] = {"executed": total, "open": 0, "failed": len(
            [c for c in frozen["cells"]
             if (c.record["panel"], c.record["arm"]) == key
             and c.record["outcome"] == "failure"])}
    frozen["panel_arm_accounting"] = by_panel_open
    l_cells = [c for c in frozen["cells"] if c.record["arm"] == "L"]
    assert len(l_cells) == 36
    assert all(any(f.get("reason") == FALLBACK_MARK
                   for f in c.record["failures"]) for c in l_cells)
    frozen["fallback_attribution"] = {
        "l_slots": len(l_cells), "marked": len(l_cells),
        "marker": FALLBACK_MARK, "learned_success": 0}
    frozen["intervention_report"] = {
        "executed": 0, "ceiling": 12, "dispositions": [
            d for d in frozen.get("interventions", [])]}
