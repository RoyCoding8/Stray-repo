from __future__ import annotations

import sys

sys.path.insert(0, "experiments")

import pytest

from settlement import broker, capabilities, evaluation, experiment, store, trials
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher

from doubles import ScriptedDouble
from fault_tasks import (BY_ID, DEV_IDS, LESSON_OFF_BY_ONE, PANEL_IDS, TASKS,
                         TRANSFER_IDS)
from test_s3_helpers import EXPERIMENTS, acquire, publish_method, seed_env, stage_method


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _publish_fixer(dsn, launcher, env, tmp_roots, tag, version_id):
    receipt = stage_method(dsn, tmp_roots["staging"],
                           EXPERIMENTS / "offbyone_fixer.py", "offbyone_fixer.py")
    publish_method(dsn, tag, tmp_roots["artifacts"], receipt)
    capabilities.publish_candidate(
        dsn, Command(request_id=f"{tag}-pubcap"), tmp_roots["artifacts"], launcher,
        env["allocation_id"], version_id=version_id, family="off_by_one",
        invocation={"entry": "offbyone_fixer.py"},
        effect={"sandbox": "local-process"}, resource={},
        artifact_digest=receipt["digest"],
        applicability={"family": "off_by_one"}, reference_version="baseline-v0",
        change="bound-inclusion rewrites", hypothesis="fixes off-by-one",
        protocol_id=f"{tag}-p", budget={"units": 500})
    return receipt


def _double():
    fixes = {t["id"]: t["fixed"] for t in TASKS}
    broken = {t["id"]: t["broken"] for t in TASKS}
    competence = {("A", "panel-triangular"): True,
                  ("B", "panel-triangular"): True, ("B", "panel-batcher"): True}
    return ScriptedDouble(competence, fixes, broken)


def test_full_simulated_abc(migrated_db, tmp_roots, launcher):
    from settlement import db

    dsn = migrated_db
    env = seed_env(dsn, "s3abc", authorized=500_000)
    _publish_fixer(dsn, launcher, env, tmp_roots, "s3abc", "fixer-v1")
    report = experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=tmp_roots["artifacts"],
        allocation_id=env["allocation_id"], investigation_id=env["investigation_id"],
        tasks=TASKS, dev_ids=DEV_IDS, panel_ids=PANEL_IDS,
        transfer_ids=TRANSFER_IDS, lessons={"off_by_one": LESSON_OFF_BY_ONE},
        double=_double(), grader_path=str(EXPERIMENTS / "run_tests.py"),
        protocol_prefix="s3abc", fixer_version="fixer-v1")
    assert report["simulated"] is True
    assert all(cell["simulated"] for arm in report["arms"].values()
               for cell in arm.values())
    assert report["verdicts"]["panel-C"]["label"] == "observed-gain"
    assert report["verdicts"]["panel-C"]["candidate_successes"] == 3
    assert report["verdicts"]["panel-B"]["label"] == "observed-gain"
    for name in ("transfer-B", "transfer-C"):
        assert report["verdicts"][name]["label"] == "inconclusive"
    assert len(report["invocations"]) == len(PANEL_IDS)
    assert len(report["abstentions"]) == len(TRANSFER_IDS)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for op_id in report["invocations"]:
                cur.execute("SELECT dispatch_state FROM operations WHERE id = %s",
                            (op_id,))
                assert cur.fetchone()[0] in ("observed", "reconciled")
                cur.execute("SELECT COUNT(*) FROM receipts WHERE operation_id = %s",
                            (op_id,))
                assert cur.fetchone()[0] >= 1
            conn.commit()
    attempts = [a for arm in report["attempts"].values() for a in arm]
    assert len(set(attempts)) == len(attempts) == \
        (len(PANEL_IDS) + len(TRANSFER_IDS)) * 3
    caps = {arm: b["matched_caps"] for arm, b in report["budgets"].items()}
    assert caps["A"] == caps["B"] == caps["C"]
    assert report["budgets"]["C"]["unique_op_cost"] > \
        report["budgets"]["A"]["unique_op_cost"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for pid in ("s3abc-panel-B", "s3abc-panel-C",
                        "s3abc-transfer-B", "s3abc-transfer-C"):
                totals = trials.development_expenditure(dsn, pid)
                cur.execute("SELECT COALESCE(SUM(amount), 0) FROM expenditure_ledger"
                            " WHERE protocol_id = %s AND category != 'use'", (pid,))
                assert cur.fetchone()[0] == totals["development_total"]
            conn.commit()
    assert "offbyone_fixer" not in sys.modules
    assert "candidate" not in sys.modules


def _release_setup(dsn, launcher, env, tag):
    evaluation.register_evaluator(dsn, Command(request_id=f"{tag}-eval"),
                                  "s3-eval", "v1")
    return "s3-eval"


def _grade(dsn, launcher, env, tag, ok=True):
    op = f"{tag}-g"
    broker.ensure_operation(dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process",
                                     "argv": ["true"] if ok else ["false"],
                                     "timeout_ms": 30_000,
                                     "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher})
    return op


def _compared_protocol(dsn, launcher, env, tag, cand_ok, ref_ok, group="panel"):
    pid = f"{tag}-p"
    trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-frz"), protocol_id=pid,
        candidate_version=f"{tag}-cand", reference_version=f"{tag}-ref",
        evaluator_version="v1",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": group, "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
        uncertainty={})
    trials.assign(dsn, Command(request_id=f"{tag}-a1", payload={}), pid,
                  "t1", group, "candidate", {})
    trials.assign(dsn, Command(request_id=f"{tag}-a2", payload={}), pid,
                  "t1", group, "reference", {})
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-r1", payload={}),
        receipt_id=f"{tag}-r1", assignment_id=f"{pid}:candidate:t1",
        evaluator_id="s3-eval", evaluator_version="v1",
        invocation_ref=_grade(dsn, launcher, env, f"{tag}-c", cand_ok),
        result={"outcome": "success" if cand_ok else "failure"})
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-r2", payload={}),
        receipt_id=f"{tag}-r2", assignment_id=f"{pid}:reference:t1",
        evaluator_id="s3-eval", evaluator_version="v1",
        invocation_ref=_grade(dsn, launcher, env, f"{tag}-f", ref_ok),
        result={"outcome": "success" if ref_ok else "failure"})
    return pid


def _capability_row(dsn, version_id):
    from settlement import db

    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family) VALUES (%s, %s)"
                        " ON CONFLICT (id) DO NOTHING", (version_id, "x"))


def test_router_mixed_with_regression(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "s3r")
    _release_setup(dsn, launcher, env, "s3r")
    _capability_row(dsn, "base-v1")
    _capability_row(dsn, "feat-v2")
    pid_x = _compared_protocol(dsn, launcher, env, "s3rx", True, False)
    pid_y = _compared_protocol(dsn, launcher, env, "s3ry", False, True)
    pid_v1 = _compared_protocol(dsn, launcher, env, "s3rv1", True, False)
    assert trials.verdict(dsn, pid_x)["label"] == "observed-gain"
    assert trials.verdict(dsn, pid_y)["label"] == "regression"
    with pytest.raises(SettlementError, match="regressed"):
        capabilities.scoped_release(
            dsn, Command(request_id="s3r-bad", payload={}), release_id="rel-y2",
            protocol_id=pid_y, versions=["feat-v2"], scope={"family": "Y"},
            disposition="limited", fallback="base-v1", policy_version="sel-v1",
            invalidation={}, evidence_refs=[], evaluator_version="v1")
    capabilities.scoped_release(
        dsn, Command(request_id="s3r-rx", payload={}), release_id="rel-x2",
        protocol_id=pid_x, versions=["feat-v2"], scope={"family": "X"},
        disposition="limited", fallback="base-v1", policy_version="sel-v1",
        invalidation={"on": "Y-regression"}, evidence_refs=[],
        evaluator_version="v1")
    capabilities.scoped_release(
        dsn, Command(request_id="s3r-ry", payload={}), release_id="rel-y1",
        protocol_id=pid_v1, versions=["base-v1"], scope={"family": "Y"},
        disposition="default", fallback="base-v1", policy_version="sel-v1",
        invalidation={}, evidence_refs=[], evaluator_version="v1")
    capabilities.save_router_policy(dsn, Command(request_id="s3r-pol", payload={}),
                                    version="rp-1", mapping={"X": "feat-v2",
                                                             "Y": "base-v1"})
    scored = capabilities.evaluate_router(dsn, "rp-1", [
        {"family": "X", "expected": "feat-v2"},
        {"family": "Y", "expected": "base-v1"},
        {"family": "Z"},
        {"family": "X", "expected": "feat-v2"}])
    assert scored["correct"] == 3
    assert scored["abstained"] == 1
    capabilities.save_router_policy(dsn, Command(request_id="s3r-pol2", payload={}),
                                    version="rp-2", mapping={"Y": "feat-v2"})
    bad = capabilities.evaluate_router(dsn, "rp-2", [{"family": "Y",
                                                      "expected": "base-v1"}])
    assert bad["wrong"] == 1
    assert {r["id"] for r in capabilities.releases_for_scope(dsn, "Y")} == {"rel-y1"}


def test_budget_quarantine_cancel_while_dispatched(migrated_db, tmp_path):
    from settlement import db, run
    from settlement.run import Composition, SuspendNode

    dsn = migrated_db
    launcher = LocalLauncher(tmp_path / "runs")
    env = seed_env(dsn, "s3d", authorized=100)
    acquire(dsn, "s3d", "s3d-att", env)
    op = "s3d-op"
    broker.ensure_operation(dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process", "argv": ["true"],
                                     "timeout_ms": 30_000,
                                     "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    status = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                       _crash_after_send=True)
    assert status.dispatch_state == "dispatching"
    from settlement.common import ResultCode

    refused = store.reserve(dsn, Command(request_id="s3d-over", payload={
        "allocation_id": env["allocation_id"], "reservation_id": "s3d-r-over",
        "amount": 10_000, "operation_id": "s3d-other"}))
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    broker.request_cancel(dsn, op, {"local-process": launcher})
    broker.note_worker_stopped(dsn, op)
    broker.confirm_cancel(dsn, op)
    late = broker.admit_launcher_receipt(dsn, op, broker.ReceiptProposal(
        receipt_identity=f"late:{op}", content={"containment": False},
        outcome="success", provenance="local-1"))
    assert late.code.value == "applied"
    row = broker.read_operation(dsn, op)
    assert row["cancel_state"] == "confirmed"
    assert row["dispatch_state"] == "observed"
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id) VALUES ('s3d-v')")
    capabilities.pin_capability(dsn, "s3d-att", "s3d-v")
    capabilities.quarantine(dsn, Command(request_id="s3d-q", payload={}),
                            "s3d-v", "cancelled-flight defect")
    comp = Composition(revision=1, root=SuspendNode(node_id="s",
                                                   pending_observation="o"),
                       authority_version=1)
    decision = run.check_eligibility(dsn, "s3d-att", comp)
    assert not decision["eligible"]
