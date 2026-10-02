"""ECR2-02/05 evidence-lane tests (lane E).

Operation-union accounting over canonical operation records, frozen-order
selection without mutating the freeze, over-budget admission refusal,
refused-cell accounting, and labeled derived corrections. Real
PostgreSQL (ec02test_evid); doubled gateway only where model text is
needed. Never touches ec02test_live.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import schemas_evidence as E
from settlement import broker, db, store
from settlement.common import Command, ResultCode

DSN = os.environ.get("EC02_EVID_DSN",
                     "dbname=ec02test_evid host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"


@pytest.fixture()
def dsn():
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    return DSN


def _usage(inp, out, calls=1):
    return {"input_tokens": inp, "output_tokens": out,
            "model_calls": calls}


def _op(op_id, kind, inp=None, out=None, **over):
    fields = {"operation_id": op_id, "kind": kind,
              "effect": E.KIND_EFFECTS[kind],
              "receipts": ["r:%s" % op_id],
              "usage": None if inp is None else _usage(inp, out),
              "settlement": "observed", "refusal": None,
              "liability": None, "artifacts": []}
    fields.update(over)
    return E.build_operation_record(**fields)


def test_union_nonuniform_shared_replayed_counts_once():
    shared = _op("op-shared", "policy_step", 100, 20)
    ops_a = [_op("op-construct", "construction", 500, 100),
             _op("op-plan", "a_interpretation", 300, 40),
             shared,
             _op("op-source", "child_inference", 50, 5),
             _op("op-check", "check", 10, 2),
             _op("op-fail", "failed", 70, 9,
                 settlement="observed",
                 liability={"party": "solver", "reason": "bad-join",
                            "operation": "op-fail"})]
    ops_b = [_op("op-probe", "probe", 30, 4),
             shared,
             _op("op-cancel", "cancelled", None, None,
                 settlement="cancelled",
                 refusal={"reason": "over-budget"}),
             _op("op-unknown", "child_inference", None, None)]
    union = E.reconcile_campaign_union(
        [{"cell_id": "cell-a", "operations": ops_a},
         {"cell_id": "cell-b", "operations": ops_b}])
    assert union["n_operations"] == 9
    assert union["attribution"]["op-shared"] == ["cell-a", "cell-b"]
    assert union["totals"]["model_tokens_in"] == "unknown"
    assert union["totals"]["model_tokens_out"] == "unknown"
    assert union["totals"]["model_calls"] == "unknown"
    assert union["totals"]["cpu_seconds"] == "unknown"
    assert union["by_kind"]["failed"] == 1
    assert union["by_kind"]["cancelled"] == 1


def test_union_exact_sums_when_all_usage_known():
    known = [_op("op-k1", "policy_step", 100, 20),
             _op("op-k2", "construction", 500, 100)]
    union = E.reconcile_campaign_union(
        [{"cell_id": "cell-a", "operations": known}])
    assert union["totals"]["model_tokens_in"] == 600
    assert union["totals"]["model_tokens_out"] == 120
    assert union["totals"]["model_calls"] == 2


def test_union_rejects_conflicting_replay_and_bad_tokens():
    op = _op("op-x", "policy_step", 10, 2)
    twin = dict(op)
    twin["usage"] = _usage(99, 2)
    with pytest.raises(E.TrialError):
        E.reconcile_campaign_union(
            [{"cell_id": "a", "operations": [op]},
             {"cell_id": "b", "operations": [twin]}])
    with pytest.raises(E.TrialError):
        _op("op-bad", "policy_step", 10, 2,
            usage={"in": 10, "out": 2})
    with pytest.raises(E.TrialError):
        E.build_operation_record(operation_id="op-noeff", kind="policy_step",
                                 effect="divination", receipts=["r"],
                                 usage=_usage(1, 1), settlement="observed",
                                 refusal=None, liability=None, artifacts=[])


def test_over_budget_attempt_dispatches_nothing(dsn):
    store.seed_allocation(dsn, Command(
        request_id="ecr202-root",
        payload={"allocation_id": "ecr202-root", "domain": "cpu",
                 "authorized": 5, "max_occupancy": 4}))
    op_id = "ecr202-over-budget"
    ensured = broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "m", "messages": [{"role": "user",
                                             "content": "x" * 400}],
                 "max_output_tokens": 10000, "deadline_ms": 300_000},
        allocation_id="ecr202-root")
    assert ensured.code not in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED)
    assert broker.read_operation(dsn, op_id) is None
    status = broker.dispatch_operation(dsn, op_id, launchers={},
                                       gateway=None)
    assert status.dispatch_state == "unknown"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts WHERE operation_id = %s",
                        (op_id,))
            assert cur.fetchone()[0] == 0
            conn.commit()


def test_frozen_nondefault_order_preserved_and_filter_pure():
    schedule = [{"panel": "evaluation", "task": "t%d" % i, "repeat": 1,
                 "arm": arm} for i, arm in enumerate(("L", "F", "A", "S"))]
    before = copy.deepcopy(schedule)
    freeze = {"freeze_id": "f1", "schedule": schedule}
    cells = E.select_panel_cells(freeze, panel="evaluation")
    assert [c["arm"] for c in cells] == ["L", "F", "A", "S"]
    assert [E.cell_key("f1", c["panel"], c["task"], c["repeat"], c["arm"])
            for c in cells] == [("f1", "evaluation", "t%d" % i, 1, arm)
                                for i, arm in enumerate(("L", "F", "A", "S"))]
    assert freeze["schedule"] == before
    assert cells is not freeze["schedule"]


def test_resume_skips_only_verified_and_reconciles_pending():
    key = ("f1", "evaluation", "t0", 1, "S")
    freeze = {"freeze_id": "f1", "package": {"digest": "p"}}
    good = {"freeze_id": "f1", "panel": "evaluation", "task_id": "t0",
            "repeat": 1, "arm": "S", "procedure_digest": "p",
            "input_digest": "i", "outcome": "success",
            "protected": {"passed": 1, "failed": 0, "total": 1},
            "failures": [], "frozen_digest": "p",
            "receipts": ["op-good-1"],
            "operations": [{"operation_id": "op-good-1"}]}
    tampered = dict(good, procedure_digest="q")
    pending = {"op-pending": {"dispatch_state": "dispatching"}}
    plan = E.resume_plan(freeze=freeze, schedule_cells=[
        {"panel": "evaluation", "task": "t0", "repeat": 1, "arm": "S"},
        {"panel": "evaluation", "task": "t1", "repeat": 1, "arm": "S"}],
        evidence_by_key={key: good}, pending_by_key={})
    assert plan["skip"] == [key]
    plan = E.resume_plan(freeze=freeze, schedule_cells=[
        {"panel": "evaluation", "task": "t0", "repeat": 1, "arm": "S"}],
        evidence_by_key={key: tampered}, pending_by_key={})
    assert plan["skip"] == []
    assert plan["run"] == [key]
    plan = E.resume_plan(freeze=freeze, schedule_cells=[
        {"panel": "evaluation", "task": "t0", "repeat": 1, "arm": "S"}],
        evidence_by_key={key: good},
        pending_by_key={key: pending})
    assert plan["reconcile"] == [key]
    assert plan["skip"] == []


def test_refused_cell_zero_success_keeps_observed_cost():
    record = E.refused_trial_record(
        freeze_id="f1", panel="evaluation", task_id="t0", repeat=1,
        arm="S", source_sha="s", config_digest="c", package_digest="p",
        protected={"passed": 0, "failed": 1, "total": 1},
        failures=["declined incompatible binding"],
        costs={"model_tokens_in": 40, "model_tokens_out": 5,
               "model_calls": 1, "tool_invocations": 0, "sandbox_ops": 2,
               "policy_exec_ops": 0, "protected_check_ops": 1,
               "cpu_seconds": None, "wall_seconds": 1.0,
               "elapsed_seconds": 1.0, "abandoned_ops": 0},
        receipts=["op-refuse-1"],
        operations=[{"operation_id": "op-refuse-1", "kind": "failed"}])
    assert record["outcome"] == "refusal"
    assert record["solved"] is False
    assert record["costs"]["model_tokens_in"] == 40
    with pytest.raises(E.TrialError):
        E.require_settled_failure({"settlement": "unresolved"},
                                  {"model_tokens_in": 0,
                                   "model_tokens_out": 0})
    with pytest.raises(E.TrialError):
        E.require_settled_failure({"settlement": "observed"},
                                  {"model_tokens_in": "unknown"})


def test_derived_correction_preserves_raw_and_separates_package():
    raw = E.build_trial_record(
        freeze_id="f1", panel="evaluation", task_id="t0", repeat=1,
        arm="S", source_sha="s", config_digest="c", package_digest="p",
        outcome="failure", solved=False,
        protected={"passed": 0, "failed": 1, "total": 1},
        failures=["join failed"],
        costs={"model_tokens_in": 10, "model_tokens_out": 2,
               "model_calls": 1, "tool_invocations": 0, "sandbox_ops": 2,
               "policy_exec_ops": 0, "protected_check_ops": 1,
               "cpu_seconds": None, "wall_seconds": 1.0,
               "elapsed_seconds": 1.0, "abandoned_ops": 0},
        receipts=["op-1"], operations=[{"operation_id": "op-1",
                                        "kind": "episode"}])
    fixed = E.derive_correction(raw, reason="tally recount",
                                fixes={"protected": {"passed": 0, "failed": 1,
                                                    "total": 1}})
    assert fixed["kind"] == "derived-correction"
    assert fixed["raw"] == raw
    assert fixed["record"]["protected"] == {"passed": 0, "failed": 1,
                                            "total": 1}
    assert E.executed_package({"digest": "p", "provenance": "retained-bytes"}) == "p"
    with pytest.raises(E.TrialError):
        E.executed_package({"digest": "S", "provenance": "baseline-label"})
