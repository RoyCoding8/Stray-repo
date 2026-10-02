"""BDR-01 slice 1: acquired candidate bytes must not execute in the host.

Rejecting test for review finding BDR-01: trajectory._run_member called
exec() on retained method_source and invoked the result in-process, so a
candidate shared the process and the live oracle objects that judge it.
The required behavior is execution through the bounded profile outside
the trusted host. The canary needs no imports: it stores an attribute on
the injected reducers module. In-process execution pollutes the host
module object; out-of-process execution contains the write in the child.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "EC02_AD01C_DSN",
    "dbname=ec02test_ad01c host=/var/run/postgresql user=ubuntu")

CANARY_SOURCE = (
    "def bdr01_canary(task, oracle, max_queries=16):\n"
    "    reducers.bdr01_host_pollution = True\n"
    "    return {'candidate': task, 'queries': 0}\n"
)

CANARY_MEMBER = {
    "capability_id": "bdr01-pollution-canary",
    "method_source": CANARY_SOURCE,
    "entry": "bdr01_canary",
    "params": {"max_queries": 1},
    "scope": {"family": "software"},
    "authored": False,
    "qualified_on": "ad01-w0-dev-sw-00",
}


def test_acquired_execution_uses_broker_profile(tmp_path):
    from experiments.ad01 import trajectory, worlds
    from settlement import broker
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, ROOT / "migrations")
    E.designate_db(DSN, kind="disposable", purpose="BDR-01 broker profile")
    E.prepare_disposable_db(DSN, ROOT / "migrations")
    trajectory.authorize_campaign(DSN, "ad01-broker", authorized=1000)
    trajectory.ensure_campaign(DSN, "ad01-broker", 0, "I", {},
                               {"agenda_authorized": 1000})
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    result = trajectory._run_member(
        dict(CANARY_MEMBER), task, dsn=DSN,
        allocation_id="ad01-campaign-ad01-broker", operation_id="ad01-broker-use-0")
    assert result["candidate"] == task
    assert result["operation_id"]
    op = broker.read_operation(DSN, result["operation_id"])
    assert op is not None and op["payload"]["effect"] == "sandbox-exec"
    assert op["payload"]["payload"]["profile"] == "local-process"
    replay = trajectory._run_member(
        dict(CANARY_MEMBER), task, dsn=DSN,
        allocation_id="ad01-campaign-ad01-broker", operation_id="ad01-broker-use-0")
    assert replay == result
    with db.connect(DSN) as conn:
        assert conn.execute("SELECT count(*) FROM receipts WHERE operation_id = %s",
                            (result["operation_id"],)).fetchone()[0] == 1


def test_broker_query_count_survives_replay():
    from experiments.ad01 import trajectory, worlds
    from experiments.coord02 import experience as E
    from settlement import db
    db.apply_migrations(DSN, ROOT / "migrations")
    E.designate_db(DSN, kind="disposable", purpose="BDR-01 query replay")
    E.prepare_disposable_db(DSN, ROOT / "migrations")
    trajectory.authorize_campaign(DSN, "query-replay", authorized=1000)
    trajectory.ensure_campaign(DSN, "query-replay", 0, "I", {},
                               {"agenda_authorized": 1000})
    member = {**CANARY_MEMBER, "method_source": (
        "def bdr01_canary(task, oracle, max_queries=16):\n"
        "    oracle.query(task)\n"
        "    return {'candidate': task, 'queries': 999}\n")}
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    kwargs = {"dsn": DSN, "allocation_id": "ad01-campaign-query-replay",
              "operation_id": "ad01-query-replay-use"}
    first = trajectory._run_member(member, task, **kwargs)
    assert first["queries"] == 1
    assert trajectory._run_member(member, task, **kwargs) == first


def test_acquired_member_cannot_touch_host_modules():
    from experiments.ad01 import trajectory, worlds
    from experiments.representation import reducers
    assert not hasattr(reducers, "bdr01_host_pollution")
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    own = trajectory._run_member(dict(CANARY_MEMBER), task)
    assert own["candidate"] == task
    assert not hasattr(reducers, "bdr01_host_pollution"), \
        "candidate executed in the trusted host process"


def test_importing_member_is_refused_before_spawn():
    from experiments.ad01 import method_exec
    with __import__("pytest").raises(method_exec.MethodExecutionError,
                                     match="imports-forbidden"):
        method_exec.verify_member({**CANARY_MEMBER,
                                   "method_source": "import os\n" +
                                   CANARY_SOURCE})


def test_hung_member_hits_the_wall_clock_bound():
    from experiments.ad01 import method_exec, trajectory, worlds
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    looping = {**CANARY_MEMBER,
               "method_source": (
                   "def bdr01_canary(task, oracle, max_queries=16):\n"
                   "    while True:\n"
                   "        pass\n"),
               "entry": "bdr01_canary"}
    with __import__("pytest").raises(method_exec.MethodExecutionError,
                                     match="timeout"):
        trajectory._run_member(looping, task, timeout_ms=500)


def test_store_backed_use_attributes_sandbox_operations():
    from experiments.ad01 import trajectory
    from experiments.coord02 import experience as E
    from settlement import db
    db.apply_migrations(DSN, ROOT / "migrations")
    E.designate_db(DSN, kind="disposable", purpose="BDR-01 use accounting")
    E.prepare_disposable_db(DSN, ROOT / "migrations")
    campaign = {"campaign_id": "use-accounting"}
    trajectory.authorize_campaign(DSN, campaign["campaign_id"], authorized=1000)
    authority = trajectory.ensure_campaign(DSN, campaign["campaign_id"], 0, "I", {},
                                           {"agenda_authorized": 1000})
    records = trajectory.run_use(
        {**campaign, "members": [CANARY_MEMBER]}, 0, "I", ["ad01-w0-within-sw-00"], {},
        dsn=DSN, allocation_id=authority["allocation_id"])
    assert len(records[0]["operation_ids"]) == 1
    union = trajectory.cost_union(campaign, records, dsn=DSN)
    assert union["use"]["sandbox_ops"] == union["total"]["sandbox_ops"] == 1
    assert union["acquisition"]["sandbox_ops"] == 0
    assert records[0]["costs"]["sandbox_ops"] == 1


def test_failed_member_falls_back_with_attribution():
    from experiments.ad01 import trajectory
    repertoire = {"campaign_id": "bdr01-fallback",
                  "members": [{**CANARY_MEMBER,
                                "method_source": "import os\n" +
                                CANARY_SOURCE}]}
    [record] = trajectory.run_use(repertoire, 0, "I",
                                  ["ad01-w0-within-sw-00"],
                                  {"tokens": 0, "sandbox_ops": 0})
    assert record["requested"] == CANARY_MEMBER["capability_id"]
    assert record["executed"] == "incumbent"
    assert "imports-forbidden" in record["fallback_reason"]
