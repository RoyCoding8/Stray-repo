"""EC02-ACCT slice 1: store-derived costs at the public callers.

Rejecting tests: run_cell must attest measured receipt usage, not the
100/20/1 constants; write_evidence must reconstruct its union from
durable operation rows, not copy cell totals onto every receipt; a
simulated (doubled) model call must record unknown measured cost plus an
explicit unmeasured-usage liability, never synthetic tokens. DB
ec02test_acct only, never ec02test_live.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02 import schemas_evidence as SE
from experiments.coord02.controller import seed_episode
from experiments.coord02.experience import snapshot_files
from settlement import broker, db, store
from settlement.common import Command, ResultCode
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_ACCT_DSN",
    "dbname=ec02test_acct host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

TASK = oracle.SPLITS["development"][0]
MARKER = "\n\nACCT_MODEL_REPAIR = 1\n"


def _fresh_db():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()


class MeteredAdapter(GatewayAdapter):
    """Model-seam double: valid repair bytes, caller-chosen usage/meta."""

    label = "ACCT-METERED"

    def __init__(self, task: str, usages: list, meta: dict | None = None):
        self._task = task
        self._usages = list(usages)
        self._meta = dict(meta or {})
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        usage = self._usages[min(len(self.calls) - 1,
                                 len(self._usages) - 1)]
        if "a-decision" in request.operation_id:
            proposal = {"action": "plan", "shape": "single",
                        "children": entry.plan_children(self._task,
                                                        "single")}
            return ModelResponse(request.operation_id, json.dumps(proposal),
                                 dict(self._meta), usage, "stop")
        snap = snapshot_files(self._task)
        owned = sorted(oracle.worker_files(self._task))
        return ModelResponse(
            request.operation_id,
            json.dumps({"files": {p: snap[p] + MARKER for p in owned},
                        "notes": "acct metered repair"}),
            dict(self._meta), usage, "stop")

    def cancel(self, operation_id):
        return False


def _cell(task=TASK, gw=None, tag="acct"):
    freeze = freeze_mod.build_freeze("coord02-%s" % tag,
                                     source_sha="%s-base" % tag)

    def launcher_factory(tag_: str) -> dict:
        return {"local-process": LocalLauncher(
            Path(tempfile.mkdtemp(prefix="acct-")) / tag_)}

    return entry.run_cell(
        DSN, freeze=freeze, task_id=task, panel="development",
        repeat=1, arm="A", launcher_factory=launcher_factory,
        package_digest="none", package_text="doubled-dev",
        source_sha="%s-base" % tag, config_digest="entry-%s" % tag,
        gateway=gw, model="%s-double" % tag)


def test_a_interprets_selected_program_not_task_snapshot():
    _fresh_db()
    seed = seed_episode(DSN, "acct-selected-source", snapshot_files(TASK))

    class SourceAdapter(MeteredAdapter):
        def infer(self, request):
            self.calls.append(request)
            action = "stop" if "selected-stop-program" in request.messages[0][
                "content"] else "unsupported"
            return ModelResponse(request.operation_id, json.dumps({"action": action}),
                                 {}, Usage(input_tokens=7, output_tokens=3), "stop")

    gateway = SourceAdapter(TASK, [])
    for name, action in (("stop", "stop"), ("other", "unsupported")):
        source = ("selected-%s-program" % name).encode()
        result = entry.arm_decision(
            "A", task_id=TASK, package_entry=source,
            package_digest="selected-%s" % name, package_text="public procedure",
            gateway=gateway, model="recording", dsn=DSN,
            run_id="acct-selected-%s" % name, allocation_id=seed["allocation_id"])
        assert result["kind"] == action
        prompt = gateway.calls[-1].messages[0]["content"]
        assert source.decode() in prompt
        assert "public procedure" in prompt
    assert len(gateway.calls) == 2


def test_trial_costs_equal_measured_receipt_usage():
    _fresh_db()
    gw = MeteredAdapter(TASK, [Usage(input_tokens=5, output_tokens=3),
                               Usage(input_tokens=7, output_tokens=11)])
    cell = _cell(gw=gw, tag="acct-measured")
    assert cell.outcome.get("status") in ("success", "join-failed-terminal"), \
        cell.outcome
    costs = cell.record["costs"]
    served = [5, 7]
    served_out = [3, 11]
    calls = len(gw.calls)
    assert calls >= 2, [c.operation_id for c in gw.calls]
    expect_in = served[0] + served[1] * (calls - 1)
    expect_out = served_out[0] + served_out[1] * (calls - 1)
    assert costs["model_tokens_in"] == expect_in, costs
    assert costs["model_tokens_out"] == expect_out, costs
    assert costs["model_calls"] == calls, costs
    assert not any("unmeasured" in liability["reason"]
                   for liability in cell.record["liabilities"]), \
        cell.record["liabilities"]
    kinds = {o["operation_id"]: o["kind"]
             for o in cell.record["operations"]}
    model_ops = [o for o, k in kinds.items()
                 if k in ("a_interpretation", "child_inference")]
    assert len(model_ops) == len(gw.calls) >= 2, kinds
    assert any(k == "a_interpretation" for k in kinds.values()), kinds
    assert any(k == "child_inference" for k in kinds.values()), kinds
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id = ANY(%s)",
                        (list(cell.record["receipts"]),))
            assert int(cur.fetchone()[0]) == len(cell.record["receipts"])
            conn.commit()


def test_simulated_call_records_unknown_plus_liability():
    _fresh_db()
    gw = MeteredAdapter(TASK, [Usage(), Usage()],
                        meta={"simulated": True})
    cell = _cell(gw=gw, tag="acct-simulated")
    assert cell.outcome.get("status") in ("success", "join-failed-terminal"), \
        cell.outcome
    costs = cell.record["costs"]
    assert costs["model_tokens_in"] == SE.UNKNOWN, costs
    assert costs["model_tokens_out"] == SE.UNKNOWN, costs
    assert costs["model_calls"] == SE.UNKNOWN, costs
    assert any("unmeasured" in liability["reason"]
               for liability in cell.record["liabilities"]), \
        cell.record["liabilities"]


def test_evidence_union_reconstructs_from_durable_rows(tmp_path):
    _fresh_db()
    gw = MeteredAdapter(TASK, [Usage(input_tokens=5, output_tokens=3),
                               Usage(input_tokens=7, output_tokens=11)])
    cell = _cell(gw=gw, tag="acct-union")
    summary = entry.write_evidence([cell], freeze=freeze_mod.build_freeze(
        "coord02-acct-union", source_sha="acct-union-base"),
        evidence_root=tmp_path / "evidence", dsn=DSN)
    union = summary["union"]
    costs = cell.record["costs"]
    assert union["totals"]["model_tokens_in"] == costs["model_tokens_in"], \
        union["totals"]
    assert union["totals"]["model_tokens_out"] == costs["model_tokens_out"], \
        union["totals"]
    assert union["totals"]["model_calls"] == costs["model_calls"], \
        union["totals"]
    assert union["totals"]["model_calls"] >= 2, union["totals"]
    assert costs["sandbox_ops"] > 0
    assert union["totals"]["sandbox_ops"] == costs["sandbox_ops"]
    assert all(union["totals"][field] == SE.UNKNOWN
               for field in SE.NULLABLE_COSTS)
    model_ops = [o for o in union["operation_ids"]
                 if o.endswith(":work:model") or ":a-decision" in o]
    trial_model_ops = [o["operation_id"] for o in cell.record["operations"]
                       if o["kind"] in ("a_interpretation",
                                        "child_inference")]
    assert sorted(model_ops) == sorted(trial_model_ops), \
        union["operation_ids"]
    assert len(model_ops) >= 2, union["operation_ids"]
    assert union["n_operations"] == len(union["operation_ids"])
    assert len(union["operation_ids"]) == len(set(
        union["operation_ids"]))


def test_evidence_union_enforces_ceilings_on_deduplicated_totals(
        tmp_path, monkeypatch, capsys):
    _fresh_db()
    gw = MeteredAdapter(TASK, [Usage(input_tokens=5, output_tokens=3)])
    cell = _cell(gw=gw, tag="acct-ceil")
    other = _cell(gw=gw, tag="acct-ceil2")
    freeze = freeze_mod.build_freeze("coord02-acct-ceil", source_sha="acct-ceil-base")
    freeze["campaign_budgets"] = dict(freeze["budgets"])
    freeze["campaign_budgets"]["input_tokens"] = cell.record["costs"]["model_tokens_in"]
    assert not entry.check_ceilings(cell.record["costs"], freeze["campaign_budgets"])
    assert not entry.check_ceilings(other.record["costs"], freeze["campaign_budgets"])
    summary = entry.write_evidence(
        [cell, cell], freeze=freeze, evidence_root=tmp_path / "dedup", dsn=DSN)
    assert summary["ceilings"] == {"breaches": [], "checked": True}
    summary = entry.write_evidence(
        [cell, cell, other], freeze=freeze,
        evidence_root=tmp_path / "union", dsn=DSN)
    assert summary["union"]["totals"]["model_tokens_in"] == sum(
        c.record["costs"]["model_tokens_in"] for c in (cell, other))
    assert summary["ceilings"]["breaches"] == ["ceiling-breach-input_tokens"]
    assert "ceiling-breach-input_tokens" in summary["checker"]["problems"]
    assert summary["checker"]["clean"] is False
    monkeypatch.setattr(entry.freeze_mod, "build_freeze", lambda *a, **k: freeze)
    monkeypatch.setattr(entry, "run_panel", lambda *a, **k: [cell, cell, other])
    assert entry.main([
        "--doubled", "--dsn", DSN, "--evidence-root", str(tmp_path / "cli")]) == 1
    assert json.loads(capsys.readouterr().out)["clean"] is False


def test_shared_operation_counted_once_across_cells():
    _fresh_db()
    seed = seed_episode(DSN, "acct-shared-%s" % uuid.uuid4().hex[:8],
                        {"m": "1"})
    allocation = seed["allocation_id"]
    for op_id, usage in (
            ("acct-shared-%s-a" % uuid.uuid4().hex[:8],
             {"input_tokens": 7, "output_tokens": 11, "model_calls": 1}),
            ("acct-shared-%s-b" % uuid.uuid4().hex[:8],
             {"input_tokens": 13, "output_tokens": 29, "model_calls": 1})):
        ensured = broker.ensure_operation(
            DSN, operation_id=op_id, effect=broker.MODEL_INFERENCE,
            payload={"model": "acct-shared",
                     "messages": [{"role": "user", "content": "probe"}],
                     "max_output_tokens": 16, "deadline_ms": 10_000},
            allocation_id=allocation)
        assert ensured.code in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED)
        advanced = store.advance_dispatch(
            DSN, Command(request_id="acct-adv-%s" % op_id,
                         payload={"operation_id": op_id,
                                  "launcher_id": "gateway",
                                  "provider_id": "acct-shared"}))
        assert advanced.code in (ResultCode.APPLIED,
                                 ResultCode.ALREADY_APPLIED)
        admitted = broker.admit_launcher_receipt(
            DSN, op_id, broker.ReceiptProposal(
                receipt_identity="acct:%s" % op_id,
                content={"usage": dict(usage)}, outcome="success",
                provenance="acct"))
        assert admitted.code in (ResultCode.APPLIED,
                                 ResultCode.ALREADY_APPLIED)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operations WHERE id LIKE "
                        "'acct-shared-%' ORDER BY id")
            ids = [r[0] for r in cur.fetchall()]
            conn.commit()
    assert len(ids) == 2
    union = SE.reconcile_campaign_union_from_store(
        DSN, [{"cell_id": "cell-1", "operation_ids": [ids[0], ids[1]]},
              {"cell_id": "cell-2", "operation_ids": [ids[1]]}])
    assert union["totals"]["model_tokens_in"] == 20, union["totals"]
    assert union["totals"]["model_calls"] == 2, union["totals"]
    assert union["n_operations"] == 2


@pytest.mark.parametrize("kind,settlement,expected", [
    ("episode", "observed", (1, 0, 0, 0, 0)),
    ("policy_step", "observed", (1, 0, 1, 0, 0)),
    ("check", "observed", (1, 0, 0, 1, 0)),
    ("probe", "observed", (0, 1, 0, 0, 0)),
    ("cancelled", "cancelled", (1, 0, 0, 0, 1)),
    ("failed", "unresolved", (1, 0, 0, 0, 0)),
])
def test_union_counts_each_admitted_resource_once(kind, settlement, expected):
    record = SE.build_operation_record(
        operation_id="shared", kind=kind, effect=SE.KIND_EFFECTS[kind],
        receipts=[], usage=None, settlement=settlement,
        refusal={"reason": "cancelled"} if settlement == "cancelled" else None,
        liability=None, artifacts=[])
    union = SE.reconcile_campaign_union([
        {"cell_id": cell, "operations": [record]} for cell in ("a", "b")])
    fields = ("sandbox_ops", "tool_invocations", "policy_exec_ops",
              "protected_check_ops", "abandoned_ops")
    assert tuple(union["totals"][field] for field in fields) == expected
    assert union["n_operations"] == 1
    assert union["attribution"] == {"shared": ["a", "b"]}
    assert all(union["totals"][field] == SE.UNKNOWN
               for field in SE.NULLABLE_COSTS)


def test_public_cell_resume_preserves_operations_and_usage():
    _fresh_db()
    gw = MeteredAdapter(TASK, [Usage(input_tokens=5, output_tokens=3)])
    first = _cell(gw=gw, tag="acct-resume")
    calls = len(gw.calls)
    second = _cell(gw=gw, tag="acct-resume")
    assert second.outcome["run_id"] == first.outcome["run_id"]
    assert second.record == first.record
    assert len(gw.calls) == calls


def test_unmeasured_operation_raises_strict():
    _fresh_db()
    seed = seed_episode(DSN, "acct-strict-%s" % uuid.uuid4().hex[:8],
                        {"m": "1"})
    op_id = "acct-strict-%s" % uuid.uuid4().hex[:8]
    ensured = broker.ensure_operation(
        DSN, operation_id=op_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "acct-strict",
                 "messages": [{"role": "user", "content": "probe"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id=seed["allocation_id"])
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    advanced = store.advance_dispatch(
        DSN, Command(request_id="acct-adv-%s" % op_id,
                     payload={"operation_id": op_id,
                              "launcher_id": "gateway",
                              "provider_id": "acct-strict"}))
    assert advanced.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    admitted = broker.admit_launcher_receipt(
        DSN, op_id, broker.ReceiptProposal(
            receipt_identity="acct:%s" % op_id,
            content={"usage": {"input_tokens": 7, "output_tokens": 11}},
            outcome="success", provenance="acct"))
    assert admitted.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    with pytest.raises(SE.TrialError):
        SE.costs_for_operations(DSN, [op_id])
