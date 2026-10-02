"""Repair-transport construction calls stay counted.

A repair attempt whose ledger row exists but which settles no success
receipt must still count in calls_made and operation_ids, or the
exported totals drift from the recomputed ledger. Disposable database
only, never shared owners' databases.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from experiments.ad01 import construct as C
from experiments.ad01 import trajectory, worlds
from experiments.ad01.s09_run_isolation import DB_PREFIX, admin_dsn, \
    create_disposable_db, drop_disposable_db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RUN_TOKEN = "invfix%s" % uuid.uuid4().hex[:8]
MIGRATIONS = ROOT / "migrations"
ADMIN = admin_dsn()

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"

ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


def _fresh_db():
    database = create_disposable_db(RUN_TOKEN, admin_dsn=ADMIN,
                                    migrations_dir=MIGRATIONS)
    return database, database.dsn


def _drop_db(database):
    drop_disposable_db(database, admin_dsn=ADMIN)


class FlakyRepairAdapter(GatewayAdapter):
    """Succeeds every attempt except the numbered repair call, which
    raises in transit after the operation row exists."""

    label = "AD01-FLAKY-REPAIR"

    def __init__(self, fail_on_call: int):
        self._fail_on_call = fail_on_call
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        if len(self.calls) == self._fail_on_call:
            raise TimeoutError("lost in transit")
        source = ("not python {{{" if len(self.calls) == 1
                  else ACQUIRED_SOURCE)
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source,
                                         "notes": "ad01 recorded method"}),
                             {}, Usage(input_tokens=11, output_tokens=7),
                             "stop")

    def cancel(self, operation_id):
        return False


def test_the_store_is_named_for_this_run_not_for_this_process():
    """A pid suffix is a collision once two runs share a pid across worktrees.

    The whole suite ships in every worktree on one cluster, so a name derived
    from the process id is shared state between a run in this worktree and a
    sibling's. The name must carry the per-run token, and a second store
    derived in the same process must not land on this one.
    """
    first = create_disposable_db(RUN_TOKEN, admin_dsn=ADMIN)
    try:
        second = create_disposable_db(RUN_TOKEN, admin_dsn=ADMIN)
        try:
            assert first.name.startswith(DB_PREFIX + "_"), first.name
            assert RUN_TOKEN in first.name, first.name
            assert second.name != first.name
        finally:
            drop_disposable_db(second, admin_dsn=ADMIN)
    finally:
        drop_disposable_db(first, admin_dsn=ADMIN)


def test_repair_transport_call_stays_counted():
    database, DSN = _fresh_db()
    try:
        cid = "ad01-w0-I-94"
        trajectory.authorize_campaign(DSN, cid, authorized=100000)
        trajectory.ensure_campaign(
            DSN, cid, 0, "I", CHARTER,
            {"agenda_authorized": 100000, "max_boundaries": 6,
             "diagnostic_queries": 16})
        task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
        gw = FlakyRepairAdapter(fail_on_call=2)
        member = C.construct_method(
            DSN, campaign_id=cid, task=task,
            experience={"observations": []},
            budget={"max_output_tokens": 512},
            gateway=gw, model="ad01-construct-double")
        assert member["method_source"] == ACQUIRED_SOURCE
        ledger = [op for op in trajectory._campaign_operations(DSN, cid)
                  if op["effect"] == "model-inference"
                  and "-construct-" in op["id"]]
        assert len(ledger) == 3, [op["id"] for op in ledger]
        assert member["lineage"]["calls_made"] == 3
        assert len(member["operation_ids"]) == 3
    finally:
        _drop_db(database)
