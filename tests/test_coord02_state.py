"""T-STATE lane tests: EC02 state/evidence contracts (ECA-02/04/05/06 + ECA-03 schema).

Real PostgreSQL (`ec02test_state`) + real subprocesses throughout. Labeled
doubles only at the model seam (`FakeGatewayAdapter`, explicitly DOUBLED
construction bytes). Never touches `ec02test_live`. Guard probe uses the
isolated `ec02test_sentinel2` database only.

RED-FIRST: every test below fails on the unmodified production code for the
intended requirement reason (not a guessed fixture shape).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import freeze as F
from experiments.coord02 import schemas_evidence as SE
from experiments.coord02 import experience as E
from experiments.coord02.controller import seed_episode
from settlement import broker, db, store
from settlement.common import Command, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get("EC02_STATE_DSN",
                     "dbname=ec02test_state host=/var/run/postgresql user=ubuntu")
SENTINEL_DSN = os.environ.get("EC02_STATE_SENTINEL_DSN",
                              "dbname=ec02test_sentinel2 host=/var/run/postgresql"
                              " user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

DOUBLED_PLAN = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "paths = sorted(req['task']['task_snapshot'].keys())",
    "plan = {'action': 'plan', 'shape': 'single', 'children': [{",
    "  'node_id': 'w1',",
    "  'obligation': 'T-STATE validity probe: apply valid reference tree',",
    "  'owned_paths': paths,",
    "  'output_contract': {'entry': 'whole-tree', 'checks': ['public']},",
    "  'input_bindings': {'base_%d' % i: p",
    "                     for i, p in enumerate(paths)}}]}",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'source_digest': req['source_digest'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'], 'proposal': plan, 'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""]) + "\n").encode()

DOUBLED_STOP = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'source_digest': req['source_digest'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'],",
    "        'proposal': {'action': 'stop',",
    "                   'reason': 'T-STATE validity probe: decline'},",
    "        'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""]) + "\n").encode()


@pytest.fixture()
def dsn():
    assert "live" not in DSN and "ec02test_state" in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="T-STATE lane tests")
    E.prepare_disposable_db(DSN, MIGRATIONS)
    for stale in Path("/tmp").glob("coord02-state-test-*"):
        shutil.rmtree(stale, ignore_errors=True)
    return DSN


def _tag(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _factory(root: Path):
    def _make(tag: str) -> dict:
        return {"local-process": LocalLauncher(root / tag)}
    return _make


def _requires(task_id: str) -> dict:
    return E._requires_for(task_id, E.snapshot_files(task_id))


# ---------------------------------------------------------------------------
# ECA-02: canonical per-operation records -> cell/phase/campaign totals
# ---------------------------------------------------------------------------

def _admit_model_op(dsn: str, operation_id: str, allocation_id: str,
                    usage: dict | None, outcome: str = "success") -> None:
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "t-state-probe", "messages": [{"role": "user",
                                                         "content": "probe"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id=allocation_id, attempt_id=None)
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    broker.dispatch_operation(
        dsn, operation_id, launchers={},
        gateway=FakeGatewayAdapter(text="t-state"),
        _crash_after_send=True)
    if usage is None:
        return
    admitted = broker.admit_launcher_receipt(
        dsn, operation_id, broker.ReceiptProposal(
            receipt_identity=f"tstate:{operation_id}",
            content={"usage": dict(usage)}, outcome=outcome,
            provenance="t-state"))
    assert admitted.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)


def test_eca02_nonuniform_union_recomputes_exactly_from_db_rows(dsn,
                                                               tmp_path):
    seed = seed_episode(dsn, _tag("eca02"), {"m": "1"})
    allocation = seed["allocation_id"]
    ops = {
        "tstate-op-a": {"input_tokens": 100, "output_tokens": 10,
                        "model_calls": 1},
        "tstate-op-b": {"input_tokens": 7, "output_tokens": 71,
                        "model_calls": 3},
    }
    for op_id, usage in ops.items():
        _admit_model_op(dsn, f"{op_id}-{uuid.uuid4().hex[:6]}", allocation,
                        usage)
    op_ids = [r for r in _op_ids_like(dsn, "tstate-op-")]
    assert len(op_ids) == 2
    shared = op_ids[0]
    _admit_model_op(dsn, f"tstate-nousage-{uuid.uuid4().hex[:6]}",
                    allocation, None)
    [nousage] = [r for r in _op_ids_like(dsn, "tstate-nousage-")]
    _admit_model_op(dsn, f"tstate-failed-{uuid.uuid4().hex[:6]}",
                    allocation,
                    {"input_tokens": 5, "output_tokens": 5,
                     "model_calls": 1},
                    outcome="failure")
    [failed] = [r for r in _op_ids_like(dsn, "tstate-failed-")]
    cancelled = f"tstate-cancelled-{uuid.uuid4().hex[:6]}"
    _admit_model_op(dsn, cancelled, allocation,
                    {"input_tokens": 1, "output_tokens": 1,
                     "model_calls": 1})
    store.request_cancellation(dsn, Command(
        request_id=_tag("cancel-req"), payload={"operation_id": cancelled}))
    store.confirm_cancellation(dsn, Command(
        request_id=_tag("cancel-confirm"),
        payload={"operation_id": cancelled}))
    cells = [
        {"cell_id": "cell-1",
         "operation_ids": [shared, op_ids[1], nousage, failed]},
        {"cell_id": "cell-2",
         "operation_ids": [shared, cancelled]},
    ]
    cells_all = [
        {"cell_id": "cell-1",
         "operation_ids": [shared, op_ids[1], failed]},
        {"cell_id": "cell-2",
         "operation_ids": [shared, cancelled]},
    ]
    union = SE.reconcile_campaign_union_from_store(dsn, cells_all)
    assert union["n_operations"] == 4
    assert sorted(union["operation_ids"]) == sorted(
        op_ids + [failed, cancelled])
    assert union["attribution"][shared] == ["cell-1", "cell-2"]
    totals = union["totals"]
    assert totals["model_tokens_in"] == 100 + 7 + 5 + 1
    assert totals["model_tokens_out"] == 10 + 71 + 5 + 1
    assert totals["model_calls"] == 1 + 3 + 1 + 1
    union_unknown = SE.reconcile_campaign_union_from_store(
        dsn, [{"cell_id": "cell-3", "operation_ids": [nousage, shared]}])
    assert union_unknown["totals"]["model_tokens_in"] == SE.UNKNOWN
    assert union_unknown["totals"]["model_tokens_in"] != 100
    assert union_unknown["totals"]["cpu_seconds"] == SE.UNKNOWN
    by_id = {r["operation_id"]: r
             for r in union["records"] + union_unknown["records"]}
    assert by_id[nousage]["usage"] is None
    assert by_id[failed]["settlement"] == "observed"
    assert by_id[failed]["receipts"] != []
    assert by_id[cancelled]["settlement"] == "cancelled"
    assert by_id[cancelled]["refusal"] is not None
    assert by_id[shared]["usage"] == {
        "input_tokens": 100, "output_tokens": 10, "model_calls": 1} or \
        by_id[shared]["usage"] == {
        "input_tokens": 7, "output_tokens": 71, "model_calls": 3}


def _op_ids_like(dsn: str, like: str) -> list:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operations WHERE id LIKE %s"
                        " ORDER BY id", (f"{like}%",))
            rows = [r[0] for r in cur.fetchall()]
            conn.commit()
            return rows


def test_eca02_unknown_usage_stays_unknown_never_zero(dsn):
    seed = seed_episode(dsn, _tag("eca02u"), {"m": "1"})
    _admit_model_op(dsn, f"tstate-u1-{uuid.uuid4().hex[:6]}",
                    seed["allocation_id"],
                    {"input_tokens": 4, "output_tokens": 4,
                     "model_calls": 1})
    _admit_model_op(dsn, f"tstate-u2-{uuid.uuid4().hex[:6]}",
                    seed["allocation_id"], None)
    known = _op_ids_like(dsn, "tstate-u1-")[0]
    unknown = _op_ids_like(dsn, "tstate-u2-")[0]
    union = SE.reconcile_campaign_union_from_store(
        dsn, [{"cell_id": "c", "operation_ids": [known, unknown]}])
    assert union["totals"]["model_tokens_in"] == SE.UNKNOWN
    assert union["totals"]["model_tokens_out"] == SE.UNKNOWN
    assert union["totals"]["model_calls"] == SE.UNKNOWN
    assert union["totals"]["model_tokens_in"] != 4


# ---------------------------------------------------------------------------
# ECA-04: unified digest identities across save/check/resume/use
# ---------------------------------------------------------------------------

def _trial_kwargs(freeze_id="f-state", digest="d" * 64):
    return {
        "freeze_id": freeze_id, "panel": "evaluation",
        "task_id": "c02-t16", "repeat": 1, "arm": "S",
        "source_sha": "s" * 40, "config_digest": "c",
        "package_digest": digest, "outcome": "success", "solved": True,
        "protected": {"passed": 1, "failed": 0, "total": 1},
        "failures": [],
        "costs": {"model_tokens_in": 1, "model_tokens_out": 1,
                  "model_calls": 1, "tool_invocations": 0,
                  "sandbox_ops": 1, "policy_exec_ops": 0,
                  "protected_check_ops": 0, "cpu_seconds": None,
                  "wall_seconds": None, "elapsed_seconds": None,
                  "abandoned_ops": 0},
        "receipts": ["op-1"],
    }


def test_eca04_freeze_writes_single_canonical_package_digest(tmp_path):
    entry = b"print('t-state')\n"
    digest = hashlib.sha256(entry).hexdigest()
    selection = {"selection": 1}
    dev_results = [{"lineage": 1, "validation": {"solved_tasks": []},
                    "entry_bytes": entry, "version_id": "v1",
                    "package_digest": digest}]
    lineages = [{"lineage": 1,
                 "exposure_manifest": E.exposure_manifest(1, [])}]
    frozen = E.freeze_selection(
        "f-state-canonical", {"status": "declared-by-t-state"},
        source_sha="s" * 40, selection=selection,
        dev_results=dev_results, lineages=lineages,
        accounting={"calls_used": 1, "live_calls_used": 0})
    package = frozen["package"]
    assert package["package_digest"] == digest
    assert "entry_digest" not in package
    assert F.verify_freeze(F.write_freeze(
        tmp_path / "canonical-freeze.json", frozen)) == []


def test_eca04_from_store_union_marks_known_usage_totals_but_not_nullables():
    from settlement import db as _db
    from psycopg.rows import dict_row
    seed = seed_episode(DSN, _tag("eca02n"), {"m": "1"})
    _admit_model_op(DSN, f"tstate-n1-{uuid.uuid4().hex[:6]}",
                    seed["allocation_id"],
                    {"input_tokens": 4, "output_tokens": 4,
                     "model_calls": 1})
    [known] = [r for r in _op_ids_like(DSN, "tstate-n1-")]
    union = SE.reconcile_campaign_union_from_store(
        DSN, [{"cell_id": "c", "operation_ids": [known]}])
    assert union["totals"]["model_tokens_in"] == 4
    assert union["totals"]["model_tokens_out"] == 4
    assert union["totals"]["model_calls"] == 1
    assert union["records"] != []
    assert union["records"][0]["usage"] == {
        "input_tokens": 4, "output_tokens": 4, "model_calls": 1}


def test_eca04_unmodified_saved_record_skips_but_fabricated_runs():
    digest = "e" * 64
    freeze = F.build_freeze("f-state-resume", source_sha="s" * 40)
    freeze["package"] = {"kind": "coordination-procedure/1",
                         "package_digest": digest}
    key = ("f-state-resume", "evaluation", "c02-t16", 1, "S")
    schedule = [{"panel": "evaluation", "task": "c02-t16", "repeat": 1,
                 "arm": "S"}]
    saved = {"procedure_digest": digest, "frozen_digest": digest,
             "outcome": "success", "receipts": ["op-real"],
             "operations": [{"operation_id": "op-real", "kind": "episode"}]}
    fabricated = {"procedure_digest": digest, "frozen_digest": digest,
                  "outcome": "success"}
    plan_saved = SE.resume_plan(
        freeze=freeze, schedule_cells=schedule,
        evidence_by_key={key: saved}, pending_by_key={},
        reconciled_operation_ids=frozenset({"op-real"}))
    assert plan_saved["skip"] == [key]
    assert plan_saved["run"] == []
    plan_fabricated = SE.resume_plan(
        freeze=freeze, schedule_cells=schedule,
        evidence_by_key={key: fabricated}, pending_by_key={},
        reconciled_operation_ids=frozenset({"op-real"}))
    assert plan_fabricated["skip"] == []
    assert plan_fabricated["run"] == [key]


def test_eca04_settled_failure_skips_unresolved_runs(dsn):
    digest = "f" * 64
    freeze = F.build_freeze("f-state-settled", source_sha="s" * 40)
    freeze["package"] = {"kind": "coordination-procedure/1",
                         "package_digest": digest}
    cells = [{"panel": "evaluation", "task": "c02-t16", "repeat": 1,
              "arm": "S"}]
    settled_key = ("f-state-settled", "evaluation", "c02-t16", 1, "S")
    seed = seed_episode(dsn, _tag("eca04"), {"m": "1"})
    _admit_model_op(dsn, f"tstate-settled-{uuid.uuid4().hex[:6]}",
                    seed["allocation_id"],
                    {"input_tokens": 2, "output_tokens": 2,
                     "model_calls": 1},
                    outcome="failure")
    [settled_op] = _op_ids_like(dsn, "tstate-settled-")
    settled = {"procedure_digest": digest, "frozen_digest": "",
               "outcome": "failure",
               "failures": [{"reason": "quoted failure"}],
               "receipts": [settled_op],
               "operations": [{"operation_id": settled_op,
                               "kind": "episode"}]}
    plan = SE.resume_plan(
        freeze=freeze, schedule_cells=cells,
        evidence_by_key={settled_key: settled}, pending_by_key={},
        reconciled_operation_ids=frozenset({settled_op}))
    assert plan["skip"] == [settled_key]
    ambiguous = dict(settled)
    ambiguous["receipts"] = ["op-never-recorded"]
    ambiguous["operations"] = [{"operation_id": "op-never-recorded",
                                "kind": "episode"}]
    plan2 = SE.resume_plan(
        freeze=freeze, schedule_cells=cells,
        evidence_by_key={settled_key: ambiguous}, pending_by_key={},
        reconciled_operation_ids=frozenset({settled_op}))
    assert plan2["run"] == [settled_key]


def test_eca04_resume_reads_canonical_package_digest_not_legacy():
    digest = "9" * 64
    freeze = F.build_freeze("f-state-canonical-read",
                            source_sha="s" * 40)
    freeze["package"] = {"kind": "coordination-procedure/1",
                         "package_digest": digest}
    key = ("f-state-canonical-read", "evaluation", "c02-t16", 1, "S")
    record = {"procedure_digest": digest, "frozen_digest": digest,
              "outcome": "success", "receipts": ["op-x"],
              "operations": [{"operation_id": "op-x", "kind": "episode"}]}
    plan = SE.resume_plan(
        freeze=freeze,
        schedule_cells=[{"panel": "evaluation", "task": "c02-t16",
                         "repeat": 1, "arm": "S"}],
        evidence_by_key={key: record}, pending_by_key={},
        reconciled_operation_ids=frozenset({"op-x"}))
    assert plan["skip"] == [key]
    stale = dict(record, procedure_digest="0" * 64,
                 frozen_digest="0" * 64)
    plan_stale = SE.resume_plan(
        freeze=freeze,
        schedule_cells=[{"panel": "evaluation", "task": "c02-t16",
                         "repeat": 1, "arm": "S"}],
        evidence_by_key={key: stale}, pending_by_key={},
        reconciled_operation_ids=frozenset({"op-x"}))
    assert plan_stale["run"] == [key]


# ---------------------------------------------------------------------------
# ECA-03 schema side: provenance survives grading round-trips
# ---------------------------------------------------------------------------

def test_eca03_provenance_fields_survive_validate_round_trip():
    kwargs = _trial_kwargs()
    kwargs["arm"] = "L"
    kwargs["executed_treatment"] = "L-acquired"
    kwargs["fallback_reason"] = None
    record = SE.build_trial_record(**kwargs)
    assert record["arm"] == "L"
    assert record["executed_treatment"] == "L-acquired"
    assert record["fallback_reason"] is None
    back = SE.validate_trial_record(json.loads(json.dumps(record)))
    assert back["arm"] == "L"
    assert back["executed_treatment"] == "L-acquired"
    assert back["fallback_reason"] is None
    fallback = SE.build_trial_record(
        **{**_trial_kwargs(), "arm": "L",
           "executed_treatment": "S-fallback",
           "fallback_reason": "none-selection:S-fallback"})
    assert SE.validate_trial_record(
        json.loads(json.dumps(fallback)))["fallback_reason"] == \
        "none-selection:S-fallback"


def test_eca03_from_checker_record_preserves_provenance():
    w_record = {"freeze_id": "f-state", "panel": "evaluation",
                "task_id": "c02-t16", "repeat": 1, "arm": "L",
                "procedure_digest": "a" * 64, "frozen_digest": "b" * 64,
                "outcome": "success",
                "executed_treatment": "L-acquired",
                "fallback_reason": None,
                "protected": {"passed": 1, "failed": 0, "total": 1},
                "failures": [],
                "costs": {"model_tokens": {"in": 3, "out": 2},
                          "model_calls": 1, "tool_invocations": 0,
                          "sandbox_ops": 2},
                "receipts": ["op-9"]}
    record = SE.from_checker_record(w_record, source_sha="s" * 40,
                                    config_digest="c")
    assert record["arm"] == "L"
    assert record["executed_treatment"] == "L-acquired"
    assert record["fallback_reason"] is None
    assert SE.validate_trial_record(
        json.loads(json.dumps(record)))["executed_treatment"] == \
        "L-acquired"


# ---------------------------------------------------------------------------
# ECA-05: stable campaign root, atomic admission, evidence protection
# ---------------------------------------------------------------------------

def test_eca05_acquire_reentry_same_root_sees_consumed_attempts(dsn,
                                                               tmp_path):
    from experiments.coord02 import oracle
    budget = E.construction_budget()
    first = E.acquire(
        dsn, tmp_path, task_ids=["c02-t16"],
        launcher_factory=_factory(tmp_path / "r1"),
        constructor=E.dev_constructor("c02-t16", solved=True),
        construction_gateway=FakeGatewayAdapter(text=""),
        budget=budget, campaign_root="tstate-root-reentry")
    assert first["ledger"].calls_used() == 4
    assert first["campaign_root"] == "tstate-root-reentry"
    second_ledger = E.ConstructionLedger(
        dsn, first["ledger"].allocation_id,
        attempt_prefix=first["ledger"].attempt_prefix)
    assert second_ledger.calls_used() == 4
    assert second_ledger.remaining() == 0
    with pytest.raises(E.ConstructionBudgetExhausted):
        second_ledger.request_call(
            E.construction_request(first["episodes"], budget, lineage=1,
                                   attempt="init"),
            gateway=FakeGatewayAdapter(text=""))


def test_eca05_unresolved_send_holds_capacity(dsn):
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, "tstate-unresolved", budget)
    prefix = _tag("tstate-unres")
    stranded_id = f"{prefix}-l-1-init-1"
    ensured = broker.ensure_operation(
        dsn, operation_id=stranded_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "t-state-probe", "messages": [{"role": "user",
                                                         "content": "probe"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id=seed["allocation_id"], attempt_id=None)
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    status = broker.dispatch_operation(
        dsn, stranded_id, launchers={}, gateway=FakeGatewayAdapter(text=""),
        _crash_after_send=True)
    assert status.dispatch_state not in E.TERMINAL_OPERATION_STATES
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"],
                                  attempt_prefix=prefix)
    assert ledger.unresolved_effects() == [stranded_id]
    with pytest.raises(E.ConstructionBudgetExhausted):
        ledger.request_call(
            E.construction_request({"packet_version": "coord02-experience/1",
                                    "probe_observations": []},
                                   budget, lineage=2, attempt="init"),
            gateway=FakeGatewayAdapter(text=""))


def test_eca05_concurrent_final_slot_admits_exactly_one(dsn):
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, _tag("tstate-race"), budget)
    prefix = _tag("tstate-race")
    ledgers = [E.ConstructionLedger(dsn, seed["allocation_id"],
                                    attempt_prefix=prefix)
               for _ in range(2)]
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    for lineage, attempt in ((1, "init"), (2, "init"), (1, "repair")):
        prior = None if attempt == "init" else {
            "kind": "parse", "reason": "seeded", "operation_id": "seed",
            "lineage": 1, "stage": "parse"}
        ledgers[0].request_call(
            E.construction_request(packet, budget, lineage=lineage,
                                   attempt=attempt, prior_failure=prior),
            gateway=FakeGatewayAdapter(
                text=json.dumps({"entry": "x = 1\n"})))
    assert ledgers[0].calls_used() == 3
    results: list = []
    prior_repair = {"kind": "parse", "reason": "seeded",
                    "operation_id": "seed", "lineage": 2, "stage": "parse"}

    def _race(ledger, out):
        try:
            ledger.request_call(
                E.construction_request(packet, budget, lineage=2,
                                       attempt="repair",
                                       prior_failure=prior_repair),
                gateway=FakeGatewayAdapter(
                    text=json.dumps({"entry": "x = 1\n"})))
            out.append("admitted")
        except E.ConstructionBudgetExhausted:
            out.append("refused")

    threads = [threading.Thread(target=_race, args=(ledgers[i], results))
               for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert sorted(results) == ["admitted", "refused"]
    assert E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix=prefix).calls_used() == 4


def test_eca05_designate_refuses_evidence_to_disposable_relabel():
    db.apply_migrations(SENTINEL_DSN, MIGRATIONS)
    E.designate_db(SENTINEL_DSN, kind="evidence",
                   purpose="T-STATE sentinel: live-like evidence")
    before = _designation_rows(SENTINEL_DSN)
    with pytest.raises(E.EvidenceDBProtected):
        E.designate_db(SENTINEL_DSN, kind="disposable",
                       purpose="attempted relabel")
    with pytest.raises(E.EvidenceDBProtected):
        E.prepare_disposable_db(SENTINEL_DSN, MIGRATIONS)
    after = _designation_rows(SENTINEL_DSN)
    assert after == before
    assert after[-1]["kind"] == "evidence"


def _designation_rows(dsn: str) -> list:
    from psycopg.rows import dict_row
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT kind, purpose FROM "
                        f"{E.DESIGNATION_TABLE} ORDER BY created_at")
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


# ---------------------------------------------------------------------------
# ECA-06: validity / quality / fallback separated in validate + select
# ---------------------------------------------------------------------------

def test_eca06_valid_but_failing_candidate_is_selectable(dsn, tmp_path):
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    tasks = ["c02-t16", "c02-t01"]
    failing = E.validate_on_development(
        dsn, entry_bytes=DOUBLED_PLAN, requires=requires,
        task_ids=tasks, launcher_factory=factory,
        constructor=E.dev_constructor("c02-t16", solved=False))
    assert failing["parse_ok"] is True
    assert failing["profile_ok"] is True
    assert failing["execution_admitted"] is True
    assert failing["solved_count"] == 0
    assert failing["fallback_count"] == 0
    assert failing["valid_execution"] is True
    selection = E.select_candidate(
        [{"lineage": 1, "validation": failing,
          "entry_bytes": DOUBLED_PLAN}])
    assert selection["selection"] == 1
    assert "neither candidate executable" not in selection["reason"]


def test_eca06_fallback_alone_never_establishes_validity(dsn, tmp_path):
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    tasks = ["c02-t16", "c02-t01"]
    declined = E.validate_on_development(
        dsn, entry_bytes=DOUBLED_STOP, requires=requires,
        task_ids=tasks, launcher_factory=factory,
        constructor=E.dev_constructor("c02-t16", solved=True))
    assert declined["parse_ok"] is True
    assert declined["execution_admitted"] is False
    assert declined["valid_execution"] is False
    selection = E.select_candidate(
        [{"lineage": 1, "validation": dict(declined),
          "entry_bytes": DOUBLED_STOP},
         {"lineage": 2, "validation": declined,
          "entry_bytes": DOUBLED_STOP}])
    assert selection["selection"] == "none"


def test_eca06_unparsable_candidate_reports_parse_failure(dsn, tmp_path):
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    broken = E.validate_on_development(
        dsn, entry_bytes=b"def broken(((", requires=requires,
        task_ids=["c02-t16"], launcher_factory=factory,
        constructor=E.dev_constructor("c02-t16", solved=True))
    assert broken["parse_ok"] is False
    assert broken["valid_execution"] is False
