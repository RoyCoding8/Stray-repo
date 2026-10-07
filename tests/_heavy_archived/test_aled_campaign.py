"""AD01-LEARN-D: campaign construction wiring, resume, accounting.

Development boundaries with constructor="model" build methods through
the broker and run acquired bytes; failures reject; resume restores
episode budgets and retained bytes without new calls; accounting
includes construction. DB ec02test_ad01c only, never ec02test_live.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from test_s09_migrate_callers import first_eligible

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "EC02_AD01C_DSN",
    "dbname=ec02test_ad01c host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"
FUNDED_AGENDA_AUTHORITY = 100000


def _grant(seq=0, amount=FUNDED_AGENDA_AUTHORITY):
    from experiments.ad01 import trajectory as T
    T.authorize_campaign(DSN, T.campaign_id(0, "I", seq),
                         authorized=amount)

ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="AD01-LEARN construction+campaign")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _develop(target: str, max_queries: int = 4):
    def propose(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % target,
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": target,
                                "max_queries": max_queries},
                "requested_resources": {"diagnostic_queries": 1}}
    return propose


class RecordingConstructorAdapter:
    label = "AD01-RECORDING-CONSTRUCTOR"

    def __init__(self, sources: list):
        from settlement.gateway import Usage
        self._sources = list(sources)
        self._usage = Usage(input_tokens=11, output_tokens=7)
        self.calls: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        source = self._sources[min(len(self.calls) - 1,
                                   len(self._sources) - 1)]
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source}),
                             {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def test_boundary_has_only_real_operation_ids():
    _fresh_db()
    from experiments.ad01 import trajectory as T
    _grant(0)
    campaign = T.run_campaign(0, "I", CHARTER,
                              {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 16},
                              tasks=[DEV_TASK], dsn=DSN)
    settled, _ = T._read_campaign(DSN, campaign["campaign_id"])
    with T._read_conn(DSN) as conn:
        for op in settled[0].get("claimed_ops", []):
            assert conn.execute("SELECT id FROM operations WHERE id = %s",
                                (op,)).fetchone(), op
    assert settled[0]["observation"]["detail"]


def test_accepted_proposal_survives_before_effects(monkeypatch):
    import pytest
    from experiments.ad01 import trajectory as T
    _fresh_db()
    caps = {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 16}
    cid = T.campaign_id(0, "I")
    target = "ad01-w0-dev-sw-01"
    diagnostic = T.run_diagnostic

    def crash(*args, **kwargs):
        settled, pending = T._read_campaign(DSN, cid)
        assert not settled
        assert pending[0]["decision"]["next_action"]["task_id"] == target
        raise RuntimeError("interrupt after acceptance")

    monkeypatch.setattr(T, "run_diagnostic", crash)
    with pytest.raises(RuntimeError, match="interrupt after acceptance"):
        _grant(0)
        T.run_campaign(0, "I", CHARTER, caps, tasks=[DEV_TASK],
                       propose=_develop(target), dsn=DSN)
    monkeypatch.setattr(T, "run_diagnostic", diagnostic)
    resumed = T.resume_campaign(
        DSN, cid, CHARTER, caps, tasks=[DEV_TASK],
        propose=lambda *args: pytest.fail("accepted proposal must be reused"))
    assert resumed["episodes"][0]["task_id"] == target
    assert resumed["boundaries"][0]["decision"]["next_action"]["task_id"] == target
    assert not T._read_campaign(DSN, cid)[1]


def test_episode_identity_and_bytes_are_not_campaign_wide():
    _fresh_db()
    from experiments.ad01 import trajectory as T
    other = ACQUIRED_SOURCE.replace("acquired_order", "second_order")
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE, other])
    tasks = [DEV_TASK, "ad01-w0-dev-sw-01"]

    def propose(experience, charter):
        return _develop(tasks[experience["boundary"]["seq"]])(experience, charter)

    _grant(0)
    out = T.run_campaign(0, "I", CHARTER,
                         {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 2, "diagnostic_queries": 64},
                         tasks=tasks, propose=propose, dsn=DSN,
                         gateway=gw, model="double", constructor="model")
    assert len(gw.calls) == 2
    assert gw.calls[0].operation_id != gw.calls[1].operation_id
    assert [e["executable"]["method_source"] for e in out["episodes"]] == [
        ACQUIRED_SOURCE, other]
    assert [e["task_id"] for e in out["episodes"]] == tasks


def test_remaining_query_authority_clamps_development():
    from experiments.ad01 import trajectory as T
    out = T.run_campaign(0, "I", CHARTER,
                         {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 1},
                         tasks=[DEV_TASK], propose=_develop(DEV_TASK, 16))
    assert out["queries"] <= 1


def test_failed_construction_calls_are_counted():
    _fresh_db()
    from experiments.ad01 import trajectory as T
    gw = RecordingConstructorAdapter(["not python {{{"])
    _grant(0)
    out = T.run_campaign(0, "I", CHARTER,
                         {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 16},
                         tasks=[DEV_TASK], propose=_develop(DEV_TASK), dsn=DSN,
                         gateway=gw, model="double", constructor="model")
    assert len(gw.calls) == 4
    assert out["model_calls"] == out["construction_calls"] == 4


def test_campaign_cannot_mint_agenda_authority():
    import pytest
    from experiments.ad01 import trajectory as T
    _fresh_db()
    with pytest.raises(ValueError, match="agenda authority"):
        T.ensure_campaign(DSN, "ad01-w0-I-99", 0, "I", CHARTER, {})
    with T._read_conn(DSN) as conn:
        assert conn.execute("SELECT id FROM allocations").fetchall() == []


def test_use_cost_union_reads_metered_operations(monkeypatch):
    from experiments.ad01 import trajectory as T
    from experiments.ad01.learner import RecordingGatewayAdapter
    from settlement import broker, store
    from settlement.common import Command
    from settlement.gateway import Usage
    _fresh_db()
    store.seed_allocation(DSN, Command(request_id="use-budget", payload={
        "allocation_id": "use-budget", "domain": "cpu", "authorized": 10000}))
    operation = "ad01-use-metered"
    gateway = RecordingGatewayAdapter([{"text": "used", "usage": {
        "input_tokens": 13, "output_tokens": 17, "charge_units": 31,
        "billed": True}}])

    def metered_member(member, task, **kwargs):
        broker.ensure_operation(DSN, operation_id=operation,
                                effect=broker.MODEL_INFERENCE,
                                payload={"model": "metered", "messages": [
                                    {"role": "user", "content": "use task"}],
                                    "max_output_tokens": 100, "deadline_ms": 1000},
                                allocation_id="use-budget")
        broker.dispatch_operation(DSN, operation, launchers={}, gateway=gateway)
        return {"candidate": task, "queries": 0, "operation_ids": [operation]}

    monkeypatch.setattr(T, "_run_member", metered_member)
    repertoire = {"campaign_id": "metered", "members": [{
        "capability_id": "metered-member", "scope": {"family": "software"},
        "method_source": ACQUIRED_SOURCE}]}
    records = T.run_use(repertoire, 0, "I", [USE_TASK],
                        {"tokens": 0, "sandbox_ops": 0},
                        policy=first_eligible)
    assert records[0]["executed"] == "metered-member"
    union = T.cost_union({"campaign_id": "metered", "operation_ids": []},
                         records, dsn=DSN)
    assert union["use"]["tokens"] == union["total"]["tokens"] == 30
    assert union["total"]["charge_units"] == 31
    assert union["total"]["model_calls"] == 1
    shared = T.cost_union({"campaign_id": "metered",
                           "operation_ids": [operation]}, records, dsn=DSN)
    assert shared["total"]["charge_units"] == 31
    assert shared["shared_operations"] == [operation]
    broker.ensure_operation(DSN, operation_id="unresolved-use",
                            effect=broker.MODEL_INFERENCE,
                            payload={"model": "metered", "messages": [
                                {"role": "user", "content": "pending"}],
                                "max_output_tokens": 100, "deadline_ms": 1000},
                            allocation_id="use-budget")
    records[0]["operation_ids"].append("unresolved-use")
    unknown = T.cost_union({"campaign_id": "metered"}, records, dsn=DSN)
    assert unknown["total"]["charge_units"] is None
    assert unknown["total"]["tokens"] is None
    assert unknown["operations"]["unresolved-use"]["charge_units"] is None


def test_campaign_constructs_and_retains_acquired(tmp_path):
    _fresh_db()
    from experiments.ad01 import trajectory
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    _grant(0)
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 2, "diagnostic_queries": 16},
        tasks=[DEV_TASK], propose=_develop(DEV_TASK), dsn=DSN,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "retained", episode
    assert episode["executable"]["method_source"] == ACQUIRED_SOURCE
    assert episode["executable"]["authored"] is False
    assert campaign["dev_episodes"] == 1
    assert campaign["model_calls"] == 1, campaign
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    repertoire = trajectory.load_repertoire(frozen)
    from settlement import store
    from settlement.common import Command
    store.seed_allocation(DSN, Command(request_id="campaign-use-budget",
                                       payload={
        "allocation_id": "campaign-use-budget", "domain": "cpu",
        "authorized": 100000}))
    [record] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        policy=first_eligible, dsn=DSN,
        allocation_id="campaign-use-budget")
    assert record["executed_source"] == ACQUIRED_SOURCE
    assert record["fallback_reason"] == ""
    union = trajectory.cost_union(campaign, [record], dsn=DSN)
    assert union["acquisition"]["model_calls"] == 1, union
    assert union["acquisition"]["sandbox_ops"] == 1, union


def test_construction_failure_rejects_episode():
    _fresh_db()
    from experiments.ad01 import trajectory
    gw = RecordingConstructorAdapter(["not python {{{"])
    _grant(0)
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 16},
        tasks=[DEV_TASK], propose=_develop(DEV_TASK), dsn=DSN,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "rejected", episode
    assert "construction" in episode["reason"], episode
    assert len(gw.calls) == 4, [c.operation_id for c in gw.calls]


def test_resume_restores_budgets_and_bytes_without_new_calls():
    _fresh_db()
    from experiments.ad01 import trajectory
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    cid = trajectory.campaign_id(0, "I", 40)
    plan = [DEV_TASK, "ad01-w0-dev-sw-01"]

    def propose(experience, charter):
        target = plan[len(experience["observations"]) - 1]
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % target,
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": target, "max_queries": 4},
                "requested_resources": {"diagnostic_queries": 1}}

    _grant(40)
    first = trajectory.run_campaign(
        0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 16},
        tasks=list(plan), propose=propose, dsn=DSN, campaign_seq=40,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    assert first["campaign_id"] == cid
    assert first["dev_episodes"] == 1
    calls_after_first = len(gw.calls)
    resumed = trajectory.resume_campaign(
        DSN, cid, CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 2, "diagnostic_queries": 16},
        tasks=list(plan), propose=propose,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    assert resumed["campaign_id"] == cid
    assert resumed["dev_episodes"] == 2, resumed
    assert len(gw.calls) == calls_after_first + 1, \
        [c.operation_id for c in gw.calls]
    assert {c.operation_id.split("-construct")[0] for c in gw.calls} == {
        "ad01-%s-b0-%s" % (cid, DEV_TASK),
        "ad01-%s-b1-ad01-w0-dev-sw-01" % cid}
    retained = [e["executable"] for e in resumed["episodes"]
                if e.get("disposition") == "retained"]
    assert len(retained) == 2
    assert {e["method_source"] for e in retained} == {ACQUIRED_SOURCE}


def test_resume_without_plan_continues_full_schedule():
    _fresh_db()
    from experiments.ad01 import trajectory
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    cid = trajectory.campaign_id(0, "I", 44)
    plan = [DEV_TASK, "ad01-w0-dev-sw-01", "ad01-w0-dev-sw-02"]

    def propose(experience, charter):
        target = plan[len(experience["observations"]) - 1]
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % target,
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": target, "max_queries": 4},
                "requested_resources": {"diagnostic_queries": 1}}

    _grant(44)
    trajectory.run_campaign(
        0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1,
                          "diagnostic_queries": 16},
        tasks=list(plan), propose=propose, dsn=DSN, campaign_seq=44,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    resumed = trajectory.resume_campaign(
        DSN, cid, CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 3,
                            "diagnostic_queries": 16},
        propose=propose, gateway=gw, model="ad01-campaign-double",
        constructor="model")
    assert resumed["dev_episodes"] == 3, resumed
    assert [e["task_id"] for e in resumed["episodes"]] == plan
    assert len(gw.calls) == 2, [c.operation_id for c in gw.calls]
    assert resumed["episodes"][2]["disposition"] == "rejected"
    assert "lineage cap reached" in resumed["episodes"][2]["reason"]


@pytest.mark.parametrize("model_cap", [4, 60])
def test_resume_after_final_construction_call_restores_member(monkeypatch, model_cap):
    from experiments.ad01 import trajectory

    _fresh_db()
    gw = RecordingConstructorAdapter(["not python {{{"] * 3 + [ACQUIRED_SOURCE])
    caps = {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1,
            "diagnostic_queries": 16, "model_calls": model_cap}
    publish = trajectory._publish_boundary

    def interrupt(*args, **kwargs):
        raise RuntimeError("interrupted before boundary publication")

    monkeypatch.setattr(trajectory, "_publish_boundary", interrupt)
    with pytest.raises(RuntimeError, match="interrupted before boundary"):
        _grant(45)
        trajectory.run_campaign(
            0, "I", CHARTER, caps, tasks=[DEV_TASK],
            propose=_develop(DEV_TASK), dsn=DSN, campaign_seq=45,
            gateway=gw, model="ad01-campaign-double", constructor="model")
    assert len(gw.calls) == 4
    from settlement.launcher_local import LocalLauncher
    monkeypatch.setattr(LocalLauncher, "dispatch", lambda *args, **kwargs:
                        pytest.fail("settled validation must not execute again"))
    monkeypatch.setattr(trajectory, "_publish_boundary", publish)
    resumed = trajectory.resume_campaign(
        DSN, trajectory.campaign_id(0, "I", 45), CHARTER, caps,
        tasks=[DEV_TASK], propose=_develop(DEV_TASK), gateway=gw,
        model="ad01-campaign-double", constructor="model")
    assert len(gw.calls) == 4
    assert resumed["construction_calls"] == 4
    assert resumed["episodes"][0]["disposition"] == "retained"
    assert resumed["episodes"][0]["executable"]["method_source"] == ACQUIRED_SOURCE
    union = trajectory.cost_union(resumed, [], dsn=DSN)
    assert union["acquisition"]["model_calls"] == 4
    assert union["acquisition"]["sandbox_ops"] == 1


def test_construction_call_cap_spans_boundaries():
    from experiments.ad01 import trajectory

    _fresh_db()
    gw = RecordingConstructorAdapter(["not python {{{"] * 3 + [ACQUIRED_SOURCE])
    _grant(46)
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 2,
                          "diagnostic_queries": 16},
        tasks=[DEV_TASK, DEV_TASK], propose=_develop(DEV_TASK), dsn=DSN,
        campaign_seq=46, gateway=gw, model="ad01-campaign-double",
        constructor="model")
    assert len(gw.calls) == 4
    assert campaign["construction_calls"] == 4
    assert [episode["disposition"] for episode in campaign["episodes"]] == [
        "retained", "no-candidate"]
    assert campaign["episodes"][1]["fallback_reason"] == (
        "construction call cap reached (4/trajectory)")


def test_lineage_limit_survives_resume():
    from experiments.ad01 import trajectory

    _fresh_db()
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    caps = {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 2,
            "diagnostic_queries": 16}
    plan = [DEV_TASK] * 3
    _grant(47)
    first = trajectory.run_campaign(
        0, "I", CHARTER, caps, tasks=plan, propose=_develop(DEV_TASK),
        dsn=DSN, campaign_seq=47, gateway=gw,
        model="ad01-campaign-double", constructor="model")
    assert len(gw.calls) == 2
    assert len(first["episodes"]) == 2
    resumed = trajectory.resume_campaign(
        DSN, first["campaign_id"], CHARTER, {**caps, "max_boundaries": 3},
        tasks=plan, propose=_develop(DEV_TASK), gateway=gw,
        model="ad01-campaign-double", constructor="model")
    assert len(gw.calls) == 2
    assert len(resumed["episodes"]) == 3
    assert resumed["episodes"][2]["disposition"] == "rejected"
    assert "lineage cap reached" in resumed["episodes"][2]["reason"]
    assert resumed["construction_calls"] == 2


def test_gateway_without_dsn_is_loud():
    import pytest
    from experiments.ad01 import trajectory
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    with pytest.raises(ValueError, match="gateway needs a dsn"):
        trajectory.run_campaign(
            0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1,
                              "diagnostic_queries": 16},
            tasks=[DEV_TASK], propose=_develop(DEV_TASK),
            gateway=gw, model="ad01-campaign-double",
            constructor="model")


def test_model_call_cap_gates_construction():
    _fresh_db()
    from experiments.ad01 import trajectory
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    _grant(0)
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"agenda_authorized": FUNDED_AGENDA_AUTHORITY, "max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 0},
        tasks=[DEV_TASK], propose=_develop(DEV_TASK), dsn=DSN,
        gateway=gw, model="ad01-campaign-double", constructor="model")
    assert campaign["episodes"] == []
    assert campaign["stop"]["reason"] == "model call cap reached"
    assert gw.calls == []


def test_construction_prompt_states_import_fails_validation():
    from experiments.ad01.construct import _prompt
    text = _prompt({"family": "software"}, {}, {}, None)
    assert "import" in text
    assert "fails validation" in text
