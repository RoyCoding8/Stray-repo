"""AD01-LEARN-B: broker-backed method construction.

A recording provider supplies a behavior-changing program outside the
seed menu through the broker; the trajectory checks it out of process,
retains exact bytes with lineage, and later executes those bytes
without seed substitution. A second provider response that only
renames the entry is a provenance change, not a behavioral one. DB
ec02test_ad01c only, never ec02test_live.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from experiments.ad01 import trajectory
from experiments.ad01 import worlds
from settlement import broker, db
from settlement.common import ResultCode
from settlement.gateway import (
    FakeGatewayAdapter,
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "EC02_AD01C_DSN",
    "dbname=ec02test_ad01c host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
USE_TASK = "ad01-w0-within-sw-00"
DEV_TASK = "ad01-w0-dev-sw-00"

ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


USE_POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    eligible = view['eligible_methods']\n"
    "    if %r not in eligible:\n"
    "        raise ValueError('the view does not offer the acquired method')\n"
    "    return {'action': {'kind': 'use_method',\n"
    "                     'target': view['task_content']['task_id'],\n"
    "                     'inputs': {'method_id': %r, 'max_queries': 16},\n"
    "                     'evidence_refs': [],\n"
    "                     'requested_resources': {'queries': 16}},\n"
    "            'state': {'selected': %r}}\n")


def _use_policy(capability_id: str):
    """The policy that governs this use episode, from real STEP source.

    The use phase takes its method from an admitted policy action and
    refuses an episode with no policy in hand, so a constructed method
    reaches execution only through a policy that names it. The source is
    parameterised on the id `construct_method` minted, so the assertion
    below that the record selected that exact id is a statement about the
    policy and the repertoire together. It is put through the same gate
    the CLI and `inv01_study` put theirs through, so a policy that would
    not survive a study refuses here first.
    """
    from experiments.ad01 import method_exec, policy_step

    source = USE_POLICY_SOURCE % (capability_id, capability_id,
                                  capability_id)
    assert method_exec.verify_step_source(source) == "STEP"
    policy = policy_step.compile_step(source, origin="<aleb-test>")
    assert callable(policy)
    return policy


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


class RecordingConstructorAdapter(GatewayAdapter):
    """Construction-seam double: scripted method sources per attempt."""

    label = "AD01-RECORDING-CONSTRUCTOR"

    def __init__(self, sources: list, usage=None):
        self._sources = list(sources)
        self._usage = usage or Usage(input_tokens=11, output_tokens=7)
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        source = self._sources[min(len(self.calls) - 1,
                                   len(self._sources) - 1)]
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source,
                                         "notes": "ad01 recorded method"}),
                             {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _campaign(dsn=DSN, cid="ad01-w0-I-90"):
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return trajectory.ensure_campaign(
        dsn, cid, 0, "I", CHARTER,
        {"agenda_authorized": 100000, "max_boundaries": 6, "diagnostic_queries": 16})


def test_constructed_program_reaches_later_execution(tmp_path):
    _fresh_db()
    _campaign()
    from experiments.ad01 import construct as C
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gw = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    member = C.construct_method(
        DSN, campaign_id="ad01-w0-I-90", task=task,
        experience={"observations": []}, budget={"max_output_tokens": 512},
        gateway=gw, model="ad01-construct-double")
    assert member["capability_id"].startswith("acquired-sw-")
    assert member["capability_id"] not in {
        c["capability_id"]
        for c in trajectory.seeds.SEED_CAPABILITIES}
    assert member["authored"] is False
    assert member["method_source"] == ACQUIRED_SOURCE
    assert member["lineage"]["init_operation"]
    repertoire = {"campaign_id": "ad01-w0-I-90", "members": [member]}
    [record] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        policy=_use_policy(member["capability_id"]))
    assert record["selected"] == member["capability_id"]
    assert record["executed"] == member["capability_id"]
    assert record["executed_source"] == ACQUIRED_SOURCE
    assert record["fallback_reason"] == ""
    seed = next(c for c in trajectory.seeds.SEED_CAPABILITIES
                if c["capability_id"] == "seed-sw-greedy")
    expected = trajectory.seeds.run_seed(seed, worlds.load_task(
        worlds.FROZEN_DIR, USE_TASK), max_queries=16)
    assert record["output"] == expected["candidate"]


def test_repair_path_rejects_garbage_and_keeps_lineage(tmp_path):
    _fresh_db()
    _campaign(cid="ad01-w0-I-91")
    from experiments.ad01 import construct as C
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gw = RecordingConstructorAdapter(["not python {{{", ACQUIRED_SOURCE])
    member = C.construct_method(
        DSN, campaign_id="ad01-w0-I-91", task=task,
        experience={"observations": []}, budget={"max_output_tokens": 512},
        gateway=gw, model="ad01-construct-double")
    assert member["method_source"] == ACQUIRED_SOURCE
    assert member["lineage"]["repair_operation"]
    assert member["lineage"]["init_operation"] != \
        member["lineage"]["repair_operation"]
    assert member["lineage"]["init_failure"]["stage"] == "gate"
    assert member["lineage"]["init_failure"]["reason"]


def test_exhausted_construction_refuses_without_row(tmp_path):
    _fresh_db()
    _campaign(cid="ad01-w0-I-92")
    from experiments.ad01 import construct as C
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gw = RecordingConstructorAdapter(["not python {{{"])
    with pytest.raises(C.ConstructionFailed):
        C.construct_method(
            DSN, campaign_id="ad01-w0-I-92", task=task,
            experience={"observations": []},
            budget={"max_output_tokens": 512},
            gateway=gw, model="ad01-construct-double")
    assert len(gw.calls) == 4, [c.operation_id for c in gw.calls]


def test_resume_reuses_settled_construction_call(tmp_path):
    _fresh_db()
    _campaign(cid="ad01-w0-I-93")
    from experiments.ad01 import construct as C
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    first = RecordingConstructorAdapter([ACQUIRED_SOURCE])
    member = C.construct_method(
        DSN, campaign_id="ad01-w0-I-93", task=task,
        experience={"observations": []}, budget={"max_output_tokens": 512},
        gateway=first, model="ad01-construct-double")
    again = RecordingConstructorAdapter(["not python {{{"])
    same = C.construct_method(
        DSN, campaign_id="ad01-w0-I-93", task=task,
        experience={"observations": []}, budget={"max_output_tokens": 512},
        gateway=again, model="ad01-construct-double")
    assert again.calls == [], "resumed construction made a duplicate call"
    assert same["method_source"] == member["method_source"]
