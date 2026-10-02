"""EC02 M2 apparatus qualification battery (lane M2).

DB ec02test_m2 only (EC02_M2_DSN); doubled gateway only (FakeGatewayAdapter).
Never touches ec02test_live. Each test exercises existing production
machinery directly — no stand-ins; first-run failures discover seam
shape (red), fixes converge on the real seam (green).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import checker
from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02.controller import (
    EpisodeConfig,
    check_bindings,
    derive_status,
    list_step_receipts,
    load_frozen_package,
    resume_episode,
    run_episode,
    seed_episode,
)
from experiments.coord02.experience import (
    _dev_bindings,
    _dev_interface_contract,
    _dev_join_rules,
    _dev_source_interfaces,
    _requires_for,
    dev_constructor,
    snapshot_files,
)
from experiments.coord02.policy_exec import run_probe_call
from experiments.coord02.schemas_evidence import (
    refused_trial_record,
    require_settled_failure,
    resume_plan,
)
from settlement import broker, capabilities, db, team
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_M2_DSN", "dbname=ec02test_m2 host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

DEV_TASK = oracle.SPLITS["development"][0]


@pytest.fixture()
def dsn():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    return DSN


def _proposal(arm, task, phase="post-probe"):
    with tempfile.TemporaryDirectory(prefix="coord02-m2-") as area:
        root = Path(area)
        program, request, response = [root / p for p in
                                      ("policy.py", "request.json",
                                       "response.json")]
        program.write_bytes(entry.arm_policy_entry(
            arm, task_id=task, package_digest="retained-program"))
        request.write_text(json.dumps(dict(
            profile="coordination-procedure",
            profile_version="coordination-procedure/1",
            decision_id="m2", package_digest="retained-program",
            source_digest="snapshot", plan_revision=0, phase=phase,
            task={"task_snapshot": json.loads(
                entry.selected_source_text(task)),
                  "observations": [],
                  "dependency_versions": {"role-app": "1"}})))
        subprocess.run([sys.executable, str(program), str(request),
                        str(response)], check=True, capture_output=True,
                       timeout=10)
        return json.loads(response.read_text())["proposal"]


def test_m2_ec01_policy_branch_changes_accepted_work():
    single = _proposal("S", DEV_TASK)
    assert single["shape"] == "single"
    assert _proposal("S", DEV_TASK) == single
    conditional = _proposal("F", DEV_TASK)
    assert conditional["shape"] == "decompose"
    assert len(conditional["children"]) == 2
    assert single != conditional


def _decide(dsn, task, text):
    seed = seed_episode(dsn, "m2-ec02-%s" % uuid.uuid4().hex[:6],
                        snapshot_files(task))
    return entry.arm_decision(
        "A", task_id=task, package_entry=None, package_digest="none",
        package_text="doubled", gateway=FakeGatewayAdapter(text=text),
        model="doubled", dsn=dsn,
        run_id="run-m2-ec02-%s" % uuid.uuid4().hex[:6],
        allocation_id=seed["allocation_id"])


def test_m2_ec02_model_response_governs_interpreted_decision(dsn):
    plan_a = {"action": "plan", "shape": "single",
              "children": [{"node_id": "w9", "obligation": "alpha",
                            "owned_paths": [],
                            "output_contract": {"entry": "whole-tree",
                                                "checks": ["public"]},
                            "input_bindings": {}}]}
    plan_b = {"action": "plan", "shape": "single",
              "children": [{"node_id": "w7", "obligation": "beta",
                            "owned_paths": [],
                            "output_contract": {"entry": "whole-tree",
                                                "checks": ["public"]},
                            "input_bindings": {}}]}
    got_a = _decide(dsn, DEV_TASK, json.dumps(plan_a))
    got_b = _decide(dsn, DEV_TASK, json.dumps(plan_b))
    assert got_a["kind"] == "interpreted"
    assert got_a["proposal"]["children"][0]["node_id"] == "w9"
    assert got_b["proposal"]["children"][0]["node_id"] == "w7"
    fallback = _decide(dsn, DEV_TASK, "not-json")
    assert fallback["proposal"]["action"] == "plan"
    assert fallback["proposal"]["children"][0]["node_id"] == "w1"


def _propose(dsn, seed, task, children):
    payload = oracle.build_solver_payload(task)
    join_rules = dict(_dev_join_rules(task))
    join_rules["join"] = "accept"
    return team.propose_team_plan(
        dsn, Command(request_id="m2-ec03-%s" % uuid.uuid4().hex[:6],
                     payload={}),
        parent_obligation="%s:repair" % seed["investigation_id"],
        snapshot_digest=seed["snapshot_digest"], shape="single",
        children=children,
        interface_contract=_dev_interface_contract(task, payload),
        join_rules=join_rules,
        allocation_id=seed["allocation_id"])


def test_m2_ec03_refused_plan_dispatches_no_child_effects(dsn):
    seed = seed_episode(dsn, "m2-ec03-%s" % uuid.uuid4().hex[:6],
                        snapshot_files(DEV_TASK))
    try:
        refused = _propose(dsn, seed, DEV_TASK, [])
    except SettlementError:
        refused = None
    assert refused is None or refused.code != ResultCode.APPLIED
    assert team.team_state(dsn, seed["investigation_id"])["plans"] == []
    admitted = _propose(dsn, seed, DEV_TASK,
                        entry.plan_children(DEV_TASK, "single"))
    assert admitted.code == ResultCode.APPLIED
    plan_id = admitted.data["plan_id"]
    assert team.child_nodes(dsn, plan_id) != []
    assert team.team_state(dsn, seed["investigation_id"])["submissions"] == []


def _digest_of(snapshot, path):
    return hashlib.sha256(snapshot[path].encode()).hexdigest()


def test_m2_ec04_binding_eligibility(dsn, tmp_path):
    from experiments.coord02 import experience as E
    snapshot = snapshot_files(DEV_TASK)
    path = sorted(snapshot)[0]
    good_requires = {"role-x": {"digest": _digest_of(snapshot, path),
                                "abi": "py-module", "version": "1"}}
    good_bindings = [{"name": "role-x", "path": path,
                      "abi": "py-module", "version": "1"}]
    assert check_bindings(snapshot, good_bindings, good_requires,
                          dsn, "m2-version") == {"ok": True}
    assert check_bindings(snapshot, [], good_requires,
                          dsn, "m2-version")["ok"] is False
    bad_requires = {"role-x": {"digest": "0" * 64,
                               "abi": "py-module", "version": "1"}}
    assert check_bindings(snapshot, good_bindings, bad_requires,
                          dsn, "m2-version")["ok"] is False
    seed = seed_episode(dsn, "m2-ec04-%s" % uuid.uuid4().hex[:6],
                        {"m": "1"})
    launcher = LocalLauncher(tmp_path / "m2-ec04-runs")
    staged = E.stage_gate(
        dsn, tmp_path / "m2-ec04-staging", tmp_path / "m2-ec04-art",
        entry_bytes=entry.arm_policy_entry(
            "S", task_id=DEV_TASK, package_digest="m2-ec04"),
        requires={},
        version_id="coord02-m2-%s" % uuid.uuid4().hex[:6],
        launcher=launcher, allocation_id=seed["allocation_id"],
        description="M2 EC-04 quarantine demonstration")
    assert staged["ok"] is True
    version_id = staged["version_id"]
    assert check_bindings(snapshot, good_bindings, good_requires,
                          dsn, version_id) == {"ok": True}
    E.revoke_binding_eligibility(dsn, version_id=version_id,
                                 reason="demonstrated incompatibility")
    quarantined = check_bindings(snapshot, good_bindings, good_requires,
                                 dsn, version_id)
    assert quarantined == {"ok": False,
                           "reason": "package %s is quarantined"
                           % version_id}


def test_m2_schedule_counterbalanced_and_selection_pure():
    schedule = freeze_mod.build_schedule()
    assert len(schedule) == (12 + 12 + 6) * 2 * 4
    by_cell: dict = {}
    for cell in schedule:
        by_cell.setdefault(
            (cell["panel"], cell["task"], cell["repeat"]), []).append(
                cell["arm"])
    assert by_cell
    for (panel, task, repeat), arms in by_cell.items():
        assert sorted(arms) == ["A", "F", "L", "S"]
        first = arms[0]
        want = freeze_mod.ARMS[(oracle.ALL_TASKS.index(task) + repeat)
                               % len(freeze_mod.ARMS)]
        assert first == want, (panel, task, repeat)
    freeze = freeze_mod.build_freeze("m2-sched", source_sha="m2")
    before = json.dumps(freeze["schedule"], sort_keys=True)
    cells = freeze_mod.select_panel_cells \
        if hasattr(freeze_mod, "select_panel_cells") else None
    from experiments.coord02 import schemas_evidence as SE
    got = SE.select_panel_cells(freeze, panel="evaluation")
    assert json.dumps(freeze["schedule"], sort_keys=True) == before
    want_order = [(c["task"], c["repeat"], c["arm"]) for c in
                  freeze["schedule"] if c["panel"] == "evaluation"]
    assert [(c["task"], c["repeat"], c["arm"]) for c in got] == want_order
    assert cells is None or True


def _launchers(root: Path):
    def _make(tag: str) -> dict:
        return {"local-process": LocalLauncher(root / tag)}
    return _make


def _episode_cfg(dsn, tag, task, entry_bytes):
    snapshot = snapshot_files(task)
    seed = seed_episode(dsn, tag, snapshot)
    payload = oracle.build_solver_payload(task)
    requires = _requires_for(task, snapshot)
    package_digest = hashlib.sha256(entry_bytes).hexdigest()
    return EpisodeConfig(
        run_id="run-%s" % tag, task_id=task,
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=_dev_interface_contract(task, payload),
        join_rules=_dev_join_rules(task),
        bindings=_dev_bindings(requires, snapshot),
        source_interfaces=_dev_source_interfaces(task),
        package={"version_id": "coord02-M2-%s" % tag,
                 "package_digest": package_digest,
                 "entry_bytes": entry_bytes, "requires": requires},
        snapshot_digest=seed["snapshot_digest"]), seed


def test_m2_ec05_two_source_behaviors_give_different_observations(dsn,
                                                                  tmp_path):
    task = "c02-t11"
    seed = seed_episode(dsn, "m2-ec05-%s" % uuid.uuid4().hex[:6],
                        snapshot_files(task))
    launcher = LocalLauncher(tmp_path / "m2-ec05-runs")
    ifaces = _dev_source_interfaces(task)
    observations = [run_probe_call(
        dsn, launcher, run_id="run-m2-ec05", task_id=task, seq=0,
        idx=i, interface="observe-broken", interface_bytes=ifaces[
            "observe-broken"], call_input=dict(probe),
        allocation_id=seed["allocation_id"])["observation"]
        for i, probe in enumerate(oracle.DIA_PROBES[task])]
    assert len(observations) == 2
    assert observations[0]["output"] != observations[1]["output"]
    assert observations[0]["error"] is None
    assert observations[1]["error"] is None
    first = _proposal("S", task)
    assert first["action"] == "plan"


def test_m2_ec06_integration_join_and_failed_join(dsn, tmp_path):
    cfg, _seed = _episode_cfg(
        dsn, "m2-ec06-%s" % uuid.uuid4().hex[:6], DEV_TASK,
        entry.arm_policy_entry("S", task_id=DEV_TASK,
                               package_digest="m2-ec06"))
    good = run_episode(dsn, cfg, {"local-process": LocalLauncher(
        tmp_path / "m2-ec06-runs")},
        dev_constructor(DEV_TASK, solved=True))
    assert good.get("status") == "success"
    assert (good.get("candidate_digest") or "") != ""
    freeze = freeze_mod.build_freeze("m2-ec06", source_sha="m2")
    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=DEV_TASK, panel="development",
        repeat=1, arm="S", launcher_factory=_launchers(tmp_path),
        package_text="doubled-dev")
    assert cell.outcome.get("status") == "submit-refused"
    assert "no constructor artifact" in cell.outcome.get("reason", "")
    assert cell.record["solved"] is False
    assert cell.record["outcome"] == "failure"
    assert cell.record["failures"] != []
    assert cell.record["receipts"] != []
    assert entry.check_ceilings(cell.record["costs"]) == []
    task = "c02-t21"
    bad_cfg, _bad_seed = _episode_cfg(
        dsn, "m2-ec06f-%s" % uuid.uuid4().hex[:6], task,
        entry.arm_policy_entry("S", task_id=task,
                               package_digest="m2-ec06"))
    failed = run_episode(dsn, bad_cfg,
                         {"local-process": LocalLauncher(
                             tmp_path / "m2-ec06f-runs")},
                         dev_constructor(task, solved=False))
    assert failed.get("status") == "join-failed-terminal"
    assert failed.get("candidate_digest") is None
    assert failed.get("liabilities") != []
    assert failed.get("revision", 1) >= 2


def test_m2_ec07_same_db_resume_preserves_sentinel_and_settled_ops(dsn,
                                                                   tmp_path):
    task = DEV_TASK
    cfg, _seed = _episode_cfg(
        dsn, "m2-ec07-%s" % uuid.uuid4().hex[:6], task,
        entry.arm_policy_entry("S", task_id=task,
                               package_digest="m2-ec07"))
    launchers = {"local-process": LocalLauncher(tmp_path / "m2-ec07-runs")}
    first = run_episode(dsn, cfg, launchers,
                        dev_constructor(task, solved=True))
    assert first.get("status") == "success"
    sentinel_before = derive_status(dsn, cfg)["sentinel"]
    receipts_before = list_step_receipts(dsn, cfg.run_id, cfg.task_id)
    resumed = resume_episode(dsn, cfg, launchers,
                             dev_constructor(task, solved=True))
    assert resumed.get("status") == "success"
    assert derive_status(dsn, cfg)["sentinel"] == sentinel_before
    assert list_step_receipts(dsn, cfg.run_id, cfg.task_id) \
        == receipts_before
    freeze = freeze_mod.build_freeze("m2-ec07", source_sha="m2")
    key = ("m2-ec07", "evaluation", task, 1, "S")
    evidence = {key: {"procedure_digest": "none", "frozen_digest": "",
                      "outcome": "success",
                      "receipts": ["m2-ec07-op-1"],
                      "operations": [{"operation_id": "m2-ec07-op-1"}]}}
    plan = resume_plan(freeze=freeze,
                       schedule_cells=[{"panel": "evaluation", "task": task,
                                        "repeat": 1, "arm": "S"},
                                       {"panel": "evaluation", "task": task,
                                        "repeat": 2, "arm": "S"}],
                       evidence_by_key=evidence, pending_by_key={})
    assert plan["skip"] == [key]
    assert len(plan["run"]) == 1


def test_m2_ec08_bounded_failure_is_explicit(dsn, tmp_path):
    task = DEV_TASK
    launchers = {"local-process": LocalLauncher(
        tmp_path / "m2-ec08-runs")}
    cfg, seed = _episode_cfg(dsn, "m2-ec08-%s" % uuid.uuid4().hex[:6],
                             task, b"def broken(((")
    empty = run_episode(dsn, cfg, launchers,
                        dev_constructor(task, solved=True))
    malformed_cfg, malformed_seed = _episode_cfg(
        dsn, "m2-ec08m-%s" % uuid.uuid4().hex[:6], task,
        b"open(__import__('sys').argv[2], 'w').write('{m2-malformed')\n")
    invalid = run_episode(dsn, malformed_cfg, launchers,
                          dev_constructor(task, solved=True))
    assert {empty.get("status"), invalid.get("status")} == {
        "policy-empty", "policy-invalid"}
    for outcome, state in ((empty, seed), (invalid, malformed_seed)):
        assert outcome.get("candidate_digest") is None
        assert [entry for entry in outcome.get("liabilities", [])
                if entry.get("party") == "policy"] != []
        assert team.team_state(
            dsn, state["investigation_id"])["plans"] == []
    refused = refused_trial_record(
        freeze_id="m2-ec08", panel="evaluation", task_id=task, repeat=1,
        arm="S", source_sha="m2", config_digest="m2",
        package_digest="none",
        protected={"passed": 0, "failed": 1, "total": 1},
        failures=[{"reason": "over-budget refusal"}],
        costs={"model_tokens_in": 10, "model_tokens_out": 2,
               "model_calls": 1, "tool_invocations": 1, "sandbox_ops": 4,
               "policy_exec_ops": 1, "protected_check_ops": 1,
               "cpu_seconds": 0.1, "wall_seconds": 0.2,
               "elapsed_seconds": 0.2, "abandoned_ops": 0},
        receipts=["m2-ec08-op"], operations=[])
    assert refused["outcome"] == "refusal" and refused["solved"] is False
    with pytest.raises(Exception):
        require_settled_failure({"settlement": "unresolved"}, {})
    with pytest.raises(Exception):
        require_settled_failure({"settlement": "observed"},
                                {"model_tokens_in": "unknown"})


def test_m2_ec09_checker_rejects_tampered_evidence(dsn, tmp_path):
    from experiments.coord02 import schemas_evidence as SE
    task = oracle.SPLITS["evaluation"][0]
    freeze = freeze_mod.build_freeze("m2-ec09", source_sha="m2")
    freeze_path = tmp_path / "freeze.json"
    freeze_mod.write_freeze(freeze_path, freeze)
    root = tmp_path / "ev"
    record = checker.make_record(freeze, root, panel="evaluation",
                                 task=task, repeat=1, arm="S")
    expected_missing = {
        "missing-pair %s-%s-%s-r%s-%s" % key
        for key in freeze_mod.expected_pairs(
            freeze["schedule"], "evaluation", freeze["freeze_id"])
        if key[2] != task or key[3] != 1 or key[4] != "S"}
    baseline = checker.check_evidence(root, freeze_path,
                                      panels=("evaluation",))
    assert set(baseline["problems"]) == expected_missing
    pair = "%s-%s-%s-%s-r%d" % (freeze["freeze_id"], "evaluation",
                                "S", task, 1)
    record_path = root / "episodes" / ("%s.json" % pair)
    record_path.unlink()
    deleted = checker.check_evidence(root, freeze_path,
                                     panels=("evaluation",))
    assert ("missing-pair %s-evaluation-%s-r1-S"
            % (freeze["freeze_id"], task)) in deleted["problems"]
    record_path.write_text(json.dumps(record))
    tampered = dict(json.loads(record_path.read_text()))
    tampered["procedure_digest"] = "0" * 64
    record_path.write_text(json.dumps(tampered))
    assert any(problem.startswith("wrong-procedure-digest")
               for problem in checker.check_evidence(
                   root, freeze_path,
                   panels=("evaluation",))["problems"])
    record_path.write_text(json.dumps(record))
    checker.make_record(freeze, root, panel="evaluation", task=task,
                        repeat=2, arm="S", receipts=list(
                            record["receipts"]))
    assert any(problem.startswith("receipt-reuse")
               for problem in checker.check_evidence(
                   root, freeze_path,
                   panels=("evaluation",))["problems"])
    assert SE.cell_key("m2-ec09", "evaluation", task, 1, "S") == \
        ("m2-ec09", "evaluation", task, 1, "S")


def test_m2_ec10_fresh_load_uses_pinned_bytes(dsn, tmp_path):
    from experiments.coord02 import experience as E
    wanted = entry.arm_policy_entry("S", task_id=DEV_TASK,
                                    package_digest="m2-ec10")
    seed = seed_episode(dsn, "m2-ec10-%s" % uuid.uuid4().hex[:6],
                        {"m": "1"})
    launcher = LocalLauncher(tmp_path / "m2-ec10-runs")
    staged = E.stage_gate(
        dsn, tmp_path / "m2-ec10-staging", tmp_path / "m2-ec10-art",
        entry_bytes=wanted, requires={},
        version_id="coord02-m2-%s" % uuid.uuid4().hex[:6],
        launcher=launcher, allocation_id=seed["allocation_id"],
        description="M2 EC-10 pinned-byte demonstration")
    assert staged["ok"] is True
    loaded = load_frozen_package(dsn, tmp_path / "m2-ec10-art",
                                 staged["version_id"])
    assert loaded["entry_bytes"] == wanted
    with pytest.raises(SettlementError):
        load_frozen_package(dsn, tmp_path / "m2-ec10-art",
                            "coord02-m2-missing")
    E.revoke_binding_eligibility(dsn, version_id=staged["version_id"],
                                 reason="m2 retention-scope demo")
    with pytest.raises(SettlementError):
        load_frozen_package(dsn, tmp_path / "m2-ec10-art",
                            staged["version_id"])


def test_m2_workload_pressure_and_held_out_diagnostics():
    families = {task: oracle.TASK_FAMILY[task]
                for task in oracle.SPLITS["evaluation"]}
    assert sorted(set(families.values())) == ["cpl", "dia", "rw", "sco",
                                              "sep", "sng"]
    held_out_dia = [task for task in oracle.SPLITS["evaluation"]
                    + oracle.SPLITS["transfer"]
                    if task in oracle.DIA_PROBES]
    assert held_out_dia != []
    for task in held_out_dia:
        assert len(oracle.DIA_PROBES[task]) == 2
    grouping_task = oracle.SPLITS["development"][2]
    assert oracle.TASK_FAMILY[grouping_task] == "cpl"
    assert _proposal("S", grouping_task)["shape"] == "single"
    assert _proposal("F", grouping_task)["shape"] == "decompose"
