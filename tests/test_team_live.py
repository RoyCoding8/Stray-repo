from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from settlement import broker, store
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import GatewayError, GatewayErrorKind, ModelResponse, Usage

from experiments.team01 import panel
from experiments.team01.oracle import SPLITS


@pytest.fixture()
def live_db():
    from settlement import db

    import os

    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    db.apply_migrations(dsn, ROOT / "migrations")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    yield dsn


def _tag(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


class ScriptedGateway:
    def __init__(self, text: str = '{"shape": "single"}',
                 usage: Usage | None = None,
                 error: GatewayError | None = None) -> None:
        self.text = text
        self.usage = usage or Usage(input_tokens=111, output_tokens=22)
        self.error = error
        self.requests: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.requests.append(request)
        if self.error is not None:
            return self.error
        return ModelResponse(request.operation_id, self.text,
                             {"simulated": True}, self.usage, "stop")

    def cancel(self, operation_id):
        return True


def _seed_campaign_alloc(dsn: str, tag: str, authorized: int = 100000) -> str:
    alloc = "%s-camp" % tag
    try:
        store.seed_allocation(dsn, Command(
            request_id="%s-seed" % tag,
            payload={"allocation_id": alloc, "domain": "cpu",
                     "authorized": authorized, "max_occupancy": 16}))
    except Exception as exc:
        if "already exists" not in str(exc):
            raise
    return alloc


def test_grant_sizing_math_is_finite_and_exact():
    from experiments.team01 import live

    env = live.size_campaign_envelope(per_call_exposure=663)
    assert env["caps"] == {"dev_episodes": 24, "template_builds": 2,
                           "eval_episodes": 48, "transfer_episodes": 24,
                           "probe_calls": 2}
    assert env["planner_calls"] == 24 + 48 + 24 + 2 + 2
    assert env["per_call_exposure"] == 663
    assert env["grant_authorized"] == (24 + 48 + 24 + 2 + 2) * 663
    assert env["retries"] == 0
    assert env["grant_authorized"] == 66300


def test_live_planner_records_every_call_with_usage(live_db):
    from experiments.team01 import live

    dsn = live_db
    tag = _tag("tlive")
    alloc = _seed_campaign_alloc(dsn, tag)
    gateway = ScriptedGateway(text='{"shape": "decompose"}')
    planner = live.LivePlanner(dsn, gateway, allocation_id=alloc,
                               model="scripted-model", tag=tag)
    decision = planner.propose("T", "team01-t05", 1, None)
    assert decision["shape"] == "decompose"
    assert len(planner.calls) == 1
    call = planner.calls[0]
    assert call["usage"] == {"in": 111, "out": 22}
    assert call["exposure"] > 0
    assert call["outcome"] == "model-shape"
    assert call["operation_id"]
    row = broker.read_operation(dsn, call["operation_id"])
    assert row is not None
    assert row["dispatch_state"] == "observed"
    assert row["payload"]["retries"] == 0
    assert decision["costs"] == {"in": 111, "out": 22, "tools": 0,
                                   "calls": 1}
    assert decision["simulated"] is False


def test_live_planner_honors_child_budget(live_db):
    from experiments.team01 import live

    dsn = live_db
    tag = _tag("tlive")
    alloc = _seed_campaign_alloc(dsn, tag)
    gateway = ScriptedGateway(text='{"shape": "decompose"}')
    planner = live.LivePlanner(dsn, gateway, allocation_id=alloc,
                               model="scripted-model", tag=tag)
    fixed = {"S": "single", "P": "alternatives"}
    for arm, task in (("S", "team01-t13"), ("P", "team01-t06"),
                      ("T", "team01-t09")):
        decision = planner.propose(arm, task, 1, None)
        kids = panel._children(decision["shape"], {p: "b" for p in
                              ("spec.json", "src/a.py")}, "fam-sng")
        assert len(kids) <= 2
        if arm in fixed:
            assert decision["shape"] == fixed[arm]
            assert decision["live_source"] == "forced"
    assert len(planner.calls) == 3
    assert len(gateway.requests) == 1
    live_call = planner.calls[2]
    row = broker.read_operation(dsn, live_call["operation_id"])
    assert row["payload"]["retries"] == 0
    gateway_bad = ScriptedGateway(text='{"shape": "swarm-of-ten"}')
    planner_bad = live.LivePlanner(dsn, gateway_bad, allocation_id=alloc,
                                   model="scripted-model", tag=tag + "b")
    decision = planner_bad.propose("T", "team01-t05", 1, None)
    assert decision["shape"] in ("single", "alternatives", "decompose")
    assert planner_bad.calls[0]["outcome"] == "fallback-invalid-shape"


def test_live_planner_falls_back_honestly_on_gateway_error(live_db):
    from experiments.team01 import live

    dsn = live_db
    tag = _tag("tlive")
    alloc = _seed_campaign_alloc(dsn, tag)
    error = GatewayError(GatewayErrorKind.TIMEOUT, "gateway request timed out",
                         True, "op-x")
    planner = live.LivePlanner(dsn, ScriptedGateway(error=error),
                               allocation_id=alloc, model="scripted-model",
                               tag=tag)
    decision = planner.propose("T", "team01-t05", 1, None)
    from settlement import team

    assert decision["shape"] == team.select_plan(
        panel._visible_info("team01-t05"))["shape"]
    assert planner.calls[0]["outcome"] == "fallback-timeout"
    assert planner.calls[0]["usage"] == {"in": 0, "out": 0}
    assert decision["live_source"] == "fallback"


def test_continuity_resume_submits_remaining_child_once(live_db, tmp_path):
    from experiments.team01 import live

    dsn = live_db
    tag = _tag("tlive")
    state_path = tmp_path / "continuity.json"
    gateway = ScriptedGateway(text='{"shape": "decompose"}')
    state = live.continuity_stage_a(
        dsn, tag=tag, task_id="team01-t05", runs_root=tmp_path / "runs",
        state_path=state_path, gateway=gateway)
    assert state["submitted"] == ["w1"]
    from settlement import team

    team.submission_tuple(dsn, state["plan_id"], 1, "w1")
    record = live.continuity_stage_b(
        dsn, state_path=state_path, runs_root=tmp_path / "runs",
        evidence_root=tmp_path / "ev", tag=tag, gateway=gateway)
    assert record["join"]["passed"] is True
    assert record["outcome"] == "success"
    assert record["resumed"] is True
    assert record["resubmitted"] == []
    with open(state_path.parent / "continuity.json") as handle:
        persisted = json.load(handle)
    assert persisted["submitted"] == ["w1"]
    assert persisted["pending"] == ["w2"]
    assert persisted["plan_id"] == state["plan_id"]
    assert persisted["task_id"] == "team01-t05"
    from settlement import db as _db
    from psycopg.rows import dict_row

    with _db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT node_id, COUNT(*) AS n FROM team_submissions"
                        " WHERE plan_id = %s GROUP BY node_id",
                        (state["plan_id"],))
            counts = {row["node_id"]: row["n"] for row in cur.fetchall()}
            conn.commit()
    assert counts == {"w1": 1, "w2": 1}


def test_empty_output_classified_separately_from_timeout():
    from experiments.team01 import live

    assert live._classify_error(
        "gateway responses output has no text") == "empty-output"
    assert live._classify_error(
        "gateway request timed out") == "timeout"


def test_reconciliation_agrees_reserved_and_consumed(live_db):
    from experiments.team01 import live

    dsn = live_db
    tag = _tag("tlive")
    alloc = _seed_campaign_alloc(dsn, tag)
    gateway = ScriptedGateway()
    planner = live.LivePlanner(dsn, gateway, allocation_id=alloc,
                               model="scripted-model", tag=tag)
    planner.propose("T", "team01-t01", 1, None)
    planner.propose("S", "team01-t13", 1, None)
    report = live.reconcile_campaign(
        dsn, [call["operation_id"] for call in planner.calls])
    assert report["operations"] == 2
    assert report["agreement"] is True
    assert report["reserved"] == sum(
        call["exposure"] for call in planner.calls)
    assert report["unresolved"] == 0
    assert report["timeouts"] == 0 and report["refusals"] == 0


def test_template_build_cap_refuses_third_attempt(live_db, tmp_path):
    from experiments.team01 import live

    dsn = live_db
    tag = _tag("tlive")
    alloc = _seed_campaign_alloc(dsn, tag)
    gateway = ScriptedGateway(text='{"build": "build-2-bind-first-with-probe"}')
    dev = panel.run_development(
        dsn, evidence_root=tmp_path / "ev", runs_root=tmp_path / "runs",
        tag=tag)
    first = live.build_live_template(dsn, gateway, dev, tmp_path / "ev",
                                     allocation_id=alloc, tag=tag + "a")
    second = live.build_live_template(dsn, gateway, dev, tmp_path / "ev",
                                      allocation_id=alloc, tag=tag + "b")
    assert first["builds_attempted"] == ["build-2-bind-first-with-probe"]
    assert second["builds_attempted"] == ["build-2-bind-first-with-probe"]
    with pytest.raises(SettlementError, match="at most"):
        live.build_live_template(dsn, gateway, dev, tmp_path / "ev",
                                 allocation_id=alloc, tag=tag + "c")


def test_budget_ledger_stops_at_boundary():
    from experiments.team01 import live

    ledger = live.BudgetLedger({"dev_episodes": 1, "template_builds": 2,
                                "eval_episodes": 48, "transfer_episodes": 24,
                                "probe_calls": 2})
    ledger.spend("dev_episodes")
    with pytest.raises(SettlementError, match="envelope exhausted"):
        ledger.spend("dev_episodes")
    assert ledger.used("dev_episodes") == 1
    assert ledger.remaining("eval_episodes") == 48
