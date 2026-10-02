"""R01-011/R01-012: live A/B/C executes end to end through the broker contract.

Drives settlement.experiment.run_abcs on real PostgreSQL plus real
subprocess sandboxes and the live CLI in deterministic mode. Asserts the
development phase runs first, all arms use matched broker-routed tools,
costs reconcile to actual receipts, insufficient grants refuse before
provider dispatch, and releases honor the R4b evaluator-evidence gates.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, "experiments")

import pytest
from psycopg.rows import dict_row

from settlement import capabilities, db, experiment
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher

from doubles import ScriptedDouble
from fault_tasks import BY_ID, DEV_IDS, PANEL_IDS, TASKS, TRANSFER_IDS
from test_s3_helpers import EXPERIMENTS, seed_env

GRADER = str(EXPERIMENTS / "run_tests.py")
METHOD = str(EXPERIMENTS / "offbyone_fixer.py")


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _double(competence):
    fixes = {t["id"]: t["fixed"] for t in TASKS}
    broken = {t["id"]: t["broken"] for t in TASKS}
    return ScriptedDouble(competence, fixes, broken)


def _full_double():
    competence = {("A", "panel-triangular"): True,
                  ("B", "panel-triangular"): True, ("B", "panel-batcher"): True}
    for dev_id in DEV_IDS:
        competence[("DEV", dev_id)] = True
    return _double(competence)


def _run(dsn, launcher, env, tmp_roots, tag, double, panel_ids=PANEL_IDS,
         transfer_ids=TRANSFER_IDS, dev_ids=DEV_IDS, lessons=None):
    return experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=tmp_roots["artifacts"],
        allocation_id=env["allocation_id"], investigation_id=env["investigation_id"],
        tasks=[BY_ID[i] for i in (dev_ids + panel_ids + transfer_ids)],
        dev_ids=dev_ids, panel_ids=panel_ids, transfer_ids=transfer_ids,
        lessons=lessons, double=double, grader_path=GRADER,
        protocol_prefix=tag, fixer_version="fixer-v1")


def _db_settled(dsn, operation_id):
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT dispatch_state, reservation_id FROM operations"
                        " WHERE id = %s", (operation_id,))
            op = dict(cur.fetchone())
            cur.execute("SELECT amount, state FROM reservations WHERE id = %s",
                        (op["reservation_id"],))
            reservation = dict(cur.fetchone())
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (operation_id,))
            receipts = [dict(r) for r in cur.fetchall()]
            conn.commit()
    terms = [r for r in receipts if r["outcome"] in ("success", "failure")]
    assert op["dispatch_state"] in ("observed", "reconciled")
    assert reservation["state"] == "settled"
    assert terms, f"{operation_id} settled without a terminal receipt"
    usage = dict((terms[-1].get("content") or {}).get("usage") or {})
    charge = usage.get("charge_units")
    if (bool(usage.get("billed", False)) and isinstance(charge, int)
            and not isinstance(charge, bool)
            and 0 <= charge <= int(reservation["amount"])):
        return charge
    return int(reservation["amount"])


def test_end_to_end_broker_routed_costs(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r01e", authorized=500_000)
    double = _full_double()
    report = _run(dsn, launcher, env, tmp_roots, "r01e", double)
    assert report["simulated"] is True
    dev = report["development"]
    assert set(dev["outcomes"]) == set(DEV_IDS)
    assert all(o["outcome"] == "success" for o in dev["outcomes"].values())
    assert dev["lesson_provenance"] == "model-authored"
    assert "range(n + 1)" in dev["lessons"]["off_by_one"]
    assert dev["methods"] == {"off_by_one": "fixer-v1"}
    assert dev["reused"] == []
    for arm in ("A", "B", "C"):
        assert set(report["model_ops"][arm]) == set(PANEL_IDS + TRANSFER_IDS)
    calls = double.calls
    for arm, expected in (("DEV", 3), ("A", 5), ("B", 5), ("C", 5)):
        assert sum(1 for c in calls if c.get("arm") == arm) == expected
    assert sum(1 for c in calls if c.get("author_lesson")) == 1
    assert report["verdicts"]["panel-C"]["label"] == "regression"
    assert report["verdicts"]["panel-C"]["candidate_successes"] == 0
    assert report["verdicts"]["panel-B"]["label"] == "observed-gain"
    for name in ("transfer-B", "transfer-C"):
        assert report["verdicts"][name]["label"] == "inconclusive"
    assert len(report["invocations"]) == len(PANEL_IDS)
    assert len(report["abstentions"]) == len(TRANSFER_IDS)
    ops = report["accounting"]["ops"]
    for op_id, entry in ops.items():
        assert entry["settled"] == _db_settled(dsn, op_id), op_id
        assert entry["unresolved"] == 0, op_id
    totals = report["accounting"]["totals"]
    assert totals["settled"] == sum(e["settled"] for e in ops.values())
    assert totals["unresolved"] == 0
    arm_settled = {arm: sum(e["settled"] for e in ops.values() if e["arm"] == arm)
                   for arm in ("A", "B", "C")}
    assert arm_settled["A"] > 0
    assert report["budgets"]["A"]["settled_usage"] == arm_settled["A"]
    assert report["budgets"]["C"]["unique_op_cost"] > \
        report["budgets"]["A"]["unique_op_cost"]
    assert report["budgets"]["C"]["unresolved_exposure"] == 0
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM expenditure_ledger"
                        " WHERE category = 'retrieval'")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM expenditure_ledger"
                        " WHERE category = 'use' AND note LIKE 'method invocation%'")
            assert cur.fetchone()[0] == sum(
                e["settled"] for e in ops.values() if e["kind"] == "invoke") > 0
            cur.execute("SELECT detail FROM trial_results WHERE assignment_id = %s",
                        ("r01e-panel-B:candidate:panel-triangular",))
            detail = dict(cur.fetchone()[0])
            conn.commit()
    assert detail["lesson_digest"] == dev["lesson_digest"]
    assert detail["method"] == "fixer-v1"
    assert "offbyone_fixer" not in sys.modules


def test_insufficient_grant_refuses_before_dispatch(migrated_db, tmp_roots,
                                                    launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r01g", authorized=5)
    double = _full_double()
    with pytest.raises(SettlementError):
        _run(dsn, launcher, env, tmp_roots, "r01g", double)
    assert double.calls == []
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts")
            assert cur.fetchone()[0] == 0
            conn.commit()


def test_experiment_release_needs_complete_evaluator_evidence(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r01r", authorized=500_000)
    report = _run(dsn, launcher, env, tmp_roots, "r01r", _double({("DEV", "dev-sum"): True}),
                  panel_ids=["panel-triangular"], transfer_ids=[],
                  dev_ids=["dev-sum"])
    assert report["verdicts"]["panel-C"]["label"] == "inconclusive"
    pid = "r01r-panel-C"

    def _release(tag, **over):
        args = {"release_id": f"r01r-{tag}", "protocol_id": pid,
                "versions": ["fixer-v1"], "scope": {"family": "off_by_one"},
                "disposition": "quarantined", "fallback": "baseline-v0",
                "policy_version": "sel-v1", "invalidation": {},
                "evidence_refs": [], "evaluator_version": "v1"}
        args.update(over)
        return capabilities.scoped_release(
            dsn, Command(request_id=f"r01r-{tag}", payload={}), **args)
    with pytest.raises(SettlementError, match="inconclusive: limited/default"):
        _release("verdict", disposition="limited")
    with pytest.raises(SettlementError, match="synthetic fixture data"):
        _release("sim")
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM trial_assignments WHERE protocol_id = %s"
                        " ORDER BY id LIMIT 1", (pid,))
            victim = cur.fetchone()[0]
            cur.execute("DELETE FROM evaluator_receipts WHERE assignment_id = %s",
                        (victim,))
    with pytest.raises(SettlementError,
                       match="without authenticated evaluator results"):
        _release("gap")
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            from psycopg.types.json import Json
            cur.execute("INSERT INTO capability_versions (id, family, applicability,"
                        " scope) VALUES ('other-v9', 'off_by_one', %s, %s)"
                        " ON CONFLICT (id) DO NOTHING",
                        (Json({"family": "off_by_one"}),
                         Json({"family": "off_by_one"})))
    with pytest.raises(SettlementError, match="candidate version pin mismatch"):
        _release("ver", release_id="r01r-rel-ver", versions=["other-v9"])


def test_cli_deterministic_end_to_end_and_live_refusal(migrated_db, tmp_roots):
    dsn = migrated_db
    env = seed_env(dsn, "r01c", authorized=500_000)
    root = EXPERIMENTS.parent
    base = [sys.executable, "experiments/run_live_abc.py", "--dsn", dsn,
            "--allocation", env["allocation_id"], "--artifacts-root",
            str(tmp_roots["artifacts"]), "--investigation",
            env["investigation_id"], "--protocol-prefix", "r01c",
            "--dev", "dev-sum", "--panel", "panel-triangular",
            "--transfer", "transfer-sign"]
    demo = subprocess.run(base + ["--deterministic"], cwd=root,
                          capture_output=True, text=True, timeout=300,
                          check=False)
    assert demo.returncode == 0, demo.stdout + demo.stderr
    payload = json.loads(demo.stdout)
    assert payload["simulated"] is True
    assert payload["verdicts"]["panel-C"]["label"] == "inconclusive"
    assert payload["verdicts"]["transfer-C"]["label"] == "inconclusive"
    assert payload["development"]["lesson_provenance"] == "model-authored"
    assert payload["development"]["methods"] == {"off_by_one": "fixer-v1"}
    assert payload["accounting"]["unresolved"] == 0
    scrubbed = {k: v for k, v in os.environ.items()
                if not k.startswith("SETTLEMENT_GATEWAY_")}
    refused = subprocess.run(base, cwd=root, capture_output=True, text=True,
                             timeout=60, env=scrubbed, check=False)
    assert refused.returncode == 2
