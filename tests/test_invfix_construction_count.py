"""Repair-transport construction calls stay counted.

A repair attempt whose ledger row exists but which settles no success
receipt must still count in calls_made and operation_ids, or the
exported totals drift from the recomputed ledger. Disposable database
only, never shared owners' databases.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from experiments.ad01 import construct as C
from experiments.ad01 import trajectory, worlds
from settlement import broker, db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PID = os.getpid()
DSN = "dbname=inv_fix_construct_%d host=/var/run/postgresql user=ubuntu" % PID
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"

ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


def _fresh_db():
    with db.connect(
            "dbname=postgres host=/var/run/postgresql user=ubuntu",
            autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DROP DATABASE IF EXISTS "inv_fix_construct_%d"'
                        % PID)
            cur.execute('CREATE DATABASE "inv_fix_construct_%d"' % PID)
    db.apply_migrations(DSN, MIGRATIONS)


def _drop_db():
    with db.connect(
            "dbname=postgres host=/var/run/postgresql user=ubuntu",
            autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DROP DATABASE IF EXISTS "inv_fix_construct_%d"'
                        % PID)


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


def test_repair_transport_call_stays_counted():
    _fresh_db()
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
        _drop_db()
