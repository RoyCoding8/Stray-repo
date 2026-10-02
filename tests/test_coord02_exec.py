"""T-EXEC red-first battery (lane ECA-01 entry side), DB ec02test_exec only.

Doubled gateway only at the model seam via the labeled RECORDING
adapter below. Never touches ec02test_live.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02.experience import snapshot_files
from settlement import db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_EXEC_DSN", "dbname=ec02test_exec host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

DEV_TASK = oracle.SPLITS["development"][0]


class RecordingAdapter(GatewayAdapter):
    """Labeled model-seam double: replays one unexpected valid proposal."""

    label = "RECORDING-DOUBLE"

    def __init__(self, proposal: dict):
        self._proposal = dict(proposal)
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        return ModelResponse(
            request.operation_id, json.dumps(self._proposal),
            {"recording-double": True},
            Usage(input_tokens=7, output_tokens=11), "stop")

    def cancel(self, operation_id):
        return False


@pytest.fixture()
def dsn():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()
    return DSN


class RepairRecordingAdapter(RecordingAdapter):
    """Replays one unexpected-but-valid repair file set per child call."""

    def __init__(self, task: str, marker: str):
        self._task = task
        self._marker = marker
        super().__init__({"action": "plan", "shape": "single",
                          "children": entry.plan_children(task, "single")})

    def infer(self, request):
        if "a-decision" in request.operation_id:
            return super().infer(request)
        snap = snapshot_files(self._task)
        owned = sorted(oracle.worker_files(self._task))
        repair = {p: snap[p] + "\n" + self._marker for p in owned}
        self.calls.append(request)
        return ModelResponse(
            request.operation_id, json.dumps({"files": repair,
                                              "notes": "repair double"}),
            {"recording-repair": True},
            Usage(input_tokens=7, output_tokens=11), "stop")


def test_recording_model_output_changes_submitted_bytes(dsn, tmp_path):
    task = DEV_TASK
    freeze = freeze_mod.build_freeze("coord02-exec-red",
                                     source_sha="exec-red-base")
    snap = snapshot_files(task)
    owned = sorted(oracle.worker_files(task))
    marker = "EXEC_REPAIR = 1\n"
    gw = RepairRecordingAdapter(task, marker)

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=task, panel="development",
        repeat=1, arm="A", launcher_factory=launcher_factory,
        package_digest="none", package_text="doubled-dev",
        source_sha="exec-red-base", config_digest="entry-red",
        gateway=gw, model="recording-double")
    assert gw.calls, "recording adapter never consulted at the model seam"
    tree = entry.restage_tree(dsn, cell.outcome)
    assert tree is not None, "no restaged tree to compare"
    assert any(marker.strip() in tree.get(p, "") for p in owned), \
        "model repair bytes did not reach submitted bytes (causal break)"
    assert all("coord02-admitted" not in body
               for body in tree.values())


def _run(dsn, tmp_path, task, arm, proposal, **kw):
    freeze = freeze_mod.build_freeze("coord02-exec-%s" % arm,
                                     source_sha="exec-base")
    gw = RecordingAdapter(proposal)

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    return entry.run_cell(
        dsn, freeze=freeze, task_id=task, panel="development",
        repeat=1, arm=arm, launcher_factory=launcher_factory,
        package_digest="none", package_text="doubled-dev",
        source_sha="exec-base", config_digest="entry-exec",
        gateway=gw, model="recording-double", **kw)


def test_model_stop_diverges_from_model_plan(dsn, tmp_path):
    task = DEV_TASK
    plan_children = entry.plan_children(task, "single")
    plan_children[0]["obligation"] = "RECORDING plan w1"
    planned = _run(dsn, tmp_path, task, "A",
                   {"action": "plan", "shape": "single",
                    "children": plan_children})
    stopped = _run(dsn, tmp_path, task, "A",
                   {"action": "stop", "reason": "nothing to do"})
    assert stopped.record["failures"] != []
    assert any("model-stop" in str(f) for f in
               stopped.record["failures"])
    assert stopped.record["arm"] == "A"
    assert planned.outcome.get("status") != stopped.outcome.get("status") \
        or planned.record["failures"] != stopped.record["failures"]


def test_model_unsupported_diverges_from_model_plan(dsn, tmp_path):
    task = DEV_TASK
    plan_children = entry.plan_children(task, "single")
    plan_children[0]["obligation"] = "RECORDING plan w1"
    planned = _run(dsn, tmp_path, task, "A",
                   {"action": "plan", "shape": "single",
                    "children": plan_children})
    refused = _run(dsn, tmp_path, task, "A",
                   {"action": "unsupported", "reason": "no binding"})
    assert any("model-unsupported" in str(f) for f in
               refused.record["failures"])
    assert planned.record["failures"] != refused.record["failures"]


def test_fixture_route_unreachable_in_live_mode(dsn, tmp_path):
    freeze = freeze_mod.build_freeze("coord02-exec-fixture",
                                     source_sha="exec-base")

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    for label in ("LIVE", "live-model"):
        with pytest.raises(ValueError, match="unknown constructor label"):
            entry.run_cell(
                dsn, freeze=freeze, task_id=DEV_TASK, panel="development",
                repeat=1, arm="S", launcher_factory=launcher_factory,
                package_digest="none", package_text="doubled-dev",
                source_sha="exec-base", config_digest="entry-exec",
                gateway=RecordingAdapter(
                    {"action": "plan", "shape": "single",
                     "children": entry.plan_children(DEV_TASK, "single")}),
                model="recording-double", constructor_label=label)


def test_poisoned_reference_loaders_change_nothing(dsn, tmp_path):
    task = DEV_TASK
    freeze = freeze_mod.build_freeze("coord02-exec-poison",
                                     source_sha="exec-base")
    gw = RecordingAdapter({"action": "plan", "shape": "single",
                           "children": entry.plan_children(task, "single")})

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    before = dict(oracle.build_solver_payload(task)["files"])
    with _poisoned_overlays():
        cell = entry.run_cell(
            dsn, freeze=freeze, task_id=task, panel="development",
            repeat=1, arm="S", launcher_factory=launcher_factory,
            package_digest="none", package_text="doubled-dev",
            source_sha="exec-base", config_digest="entry-exec",
            gateway=gw, model="recording-double")
    after = dict(oracle.build_solver_payload(task)["files"])
    assert before == after
    assert cell.record["receipts"] != []


class _poisoned_overlays:
    def __enter__(self):
        import unittest.mock as mock
        self._patches = [
            mock.patch.object(oracle, "overlay_files",
                              return_value={}),
            mock.patch.object(oracle, "prepare_tree",
                              side_effect=RuntimeError("poisoned")),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False


def test_l_executes_retained_bytes_not_s_policy(dsn, tmp_path):
    task = DEV_TASK
    retained = entry.arm_policy_entry(
        "S", task_id=task, package_digest="retained-test")
    freeze = freeze_mod.build_freeze("coord02-exec-l",
                                     source_sha="exec-base")
    gw = RecordingAdapter({"action": "plan", "shape": "single",
                           "children": entry.plan_children(task, "single")})

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=task, panel="development",
        repeat=1, arm="L", launcher_factory=launcher_factory,
        package_entry=retained, package_digest="retained-test",
        package_text="doubled-dev",
        source_sha="exec-base", config_digest="entry-exec",
        gateway=gw, model="recording-double")
    assert cell.record["arm"] == "L"
    assert cell.record["package_digest"] == "retained-test"
    assert cell.record["receipts"] != []


def test_l_without_package_takes_attributed_s_fallback(dsn, tmp_path):
    task = DEV_TASK
    freeze = freeze_mod.build_freeze("coord02-exec-lnone",
                                     source_sha="exec-base")
    gw = RecordingAdapter({"action": "plan", "shape": "single",
                           "children": entry.plan_children(task, "single")})

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=task, panel="development",
        repeat=1, arm="L", launcher_factory=launcher_factory,
        package_entry=None, package_digest="none",
        package_text="doubled-dev",
        source_sha="exec-base", config_digest="entry-exec",
        gateway=gw, model="recording-double")
    assert cell.record["arm"] == "L"
    assert any("none-selection:S-fallback" in str(f) for f in
               cell.record["failures"])


def test_over_budget_attempt_dispenses_nothing(dsn, tmp_path):
    from experiments.coord02.controller import seed_episode
    from settlement import broker
    from settlement import db as _db
    from settlement.common import ResultCode
    seed = seed_episode(dsn, "exec-over-%s" % os.urandom(3).hex(),
                        {"m": "1"})
    alloc = seed["allocation_id"]
    ensured = broker.ensure_operation(
        dsn, operation_id="coord:exec-over-budget-probe",
        effect=broker.MODEL_INFERENCE,
        payload={"model": "recording-double",
                 "messages": [{"role": "user", "content": "probe"}],
                 "max_output_tokens": 8, "deadline_ms": 1000},
        allocation_id=alloc)
    assert ensured.code in (ResultCode.APPLIED,
                            ResultCode.ALREADY_APPLIED)
    assert entry.check_ceilings({"model_calls": 10 ** 9}) != []
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT consumed, authorized FROM allocations "
                        "WHERE id = %s", (alloc,))
            row = cur.fetchone()
        conn.commit()
    assert row is not None
    assert row[0] <= row[1]
