"""EC02-ACQ slice 1: eligible-repair orchestration.

Rejecting tests: a parseable-but-profile-invalid init must reach its
allowed repair with the concrete check failure (not merely keep/parse
failures); a missing repair leaves no repair row; every attempt row
maps to its own admitted call; development episode child work comes
from the model-backed path, not the unchanged-source constructor. DB
ec02test_acq only, never ec02test_live.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from experiments.coord02 import experience as E
from experiments.coord02 import oracle
from experiments.coord02.experience import snapshot_files
from settlement import db
from settlement.gateway import (
    FakeGatewayAdapter,
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_ACQ_DSN",
    "dbname=ec02test_acq host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parents[2] / "migrations"

TASK = "c02-t01"
MARKER = "\n\nACQ_MODEL_CHILD = 1\n"

PROFILE_INVALID = "import sys\nsys.exit(3)\n"


def _fresh_db():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="EC02-ACQ eligible-repair orchestration")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _factory(root: Path):
    def make(tag: str) -> dict:
        return {"local-process": LocalLauncher(root / tag)}
    return make


class OrderedConstructionAdapter(GatewayAdapter):
    """Construction-seam double: scripted responses per attempt."""

    label = "ACQ-ORDERED-CONSTRUCTION"

    def __init__(self, scripts: list):
        self._scripts = list(scripts)
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        text = self._scripts[min(len(self.calls) - 1,
                                 len(self._scripts) - 1)]
        return ModelResponse(request.operation_id, text, {},
                             Usage(input_tokens=7, output_tokens=11),
                             "stop")

    def cancel(self, operation_id):
        return False


class ModelChildAdapter(GatewayAdapter):
    """Child-seam double: model repair bytes with a marker."""

    label = "ACQ-MODEL-CHILD"

    def __init__(self, task: str):
        self._task = task
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        snap = snapshot_files(self._task)
        owned = sorted(oracle.worker_files(self._task))
        return ModelResponse(
            request.operation_id,
            json.dumps({"files": {p: snap[p] + MARKER for p in owned},
                        "notes": "acq model child"}),
            {}, Usage(input_tokens=3, output_tokens=5), "stop")

    def cancel(self, operation_id):
        return False


def _valid_entry() -> str:
    source = E._acquire_probe_plan_entry().decode("utf-8")
    assert source.strip()
    return source


def _episodes(tmp_path):
    return E.acquire_episodes(
        DSN, tmp_path, task_ids=[TASK],
        launcher_factory=_factory(tmp_path),
        constructor=E.dev_constructor(TASK, solved=False))


def test_default_acquire_needs_no_authored_child_constructor(tmp_path):
    _fresh_db()
    gateway = OrderedConstructionAdapter([json.dumps({"entry": _valid_entry()})])
    result = E.acquire(
        DSN, tmp_path, task_ids=[TASK], launcher_factory=_factory(tmp_path),
        construction_gateway=gateway, campaign_root="acq-default")
    assert len(result["episodes"]) == 1
    outcome = result["episodes"][0]["episode"]["outcome"]
    assert outcome["status"] == "stopped", outcome
    assert outcome["plan_id"] is None
    assert outcome["probe_calls"] == 1
    assert len(gateway.calls) == 2
    assert all(lineage["profile"]["ok"] for lineage in result["lineages"])
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM team_outputs")
            assert cur.fetchone()[0] == 0
        conn.commit()


def test_profile_invalid_init_reaches_repair_with_feedback(tmp_path):
    _fresh_db()
    episodes = _episodes(tmp_path)
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn=DSN, campaign="acq-%s"
                                        % uuid.uuid4().hex[:8], budget=budget)
    ledger = E.ConstructionLedger(DSN, seed["allocation_id"])
    gateway = OrderedConstructionAdapter([
        json.dumps({"entry": PROFILE_INVALID}),
        json.dumps({"entry": _valid_entry()}),
        json.dumps({"entry": _valid_entry()}),
    ])
    lineages = E.construct_lineages(
        episodes, budget, ledger=ledger, gateway=gateway,
        launcher_factory=_factory(tmp_path))
    first, second = lineages
    assert first["parsed"]["ok"], first["parsed"]
    assert first["repair"] is not None, \
        "parseable-but-profile-invalid init reached no repair"
    assert first["repair"]["operation_id"] != \
        first["init"]["operation_id"]
    assert first["repair_failure"]["stage"] == "profile", \
        first["repair_failure"]
    assert first["repair_failure"]["reason"]
    assert first["repair_kept"]["usable"]
    assert first["repair_parsed"]["ok"]
    assert second["repair"] is None, \
        "clean init minted a repair row without a repair call"
    assert second["repair_kept"] is None
    assert second["repair_parsed"] is None
    assert ledger.calls_used() == 3, ledger.accounting()
    op_ids = [c["operation_id"] for c in ledger.calls
              if c.get("valid", True)]
    assert len(set(op_ids)) == len(op_ids) == 3, op_ids


def test_validation_stages_skip_missing_repair():
    assert E.validation_stages({"repair": None,
                                "repair_kept": None}) == ["init"]
    assert E.validation_stages(
        {"repair": {"operation_id": "op-r"},
         "repair_kept": {"usable": True}}) == ["init", "repair"]
    assert E.validation_stages(
        {"repair": {"operation_id": "op-r"},
         "repair_kept": {"usable": False, "reason": "empty"}}) == ["init"]


def test_validation_child_work_comes_from_the_model(tmp_path):
    _fresh_db()
    gw = ModelChildAdapter(TASK)
    child_seed = E.seed_episode(
        DSN, "acq-children-%s" % uuid.uuid4().hex[:8], {"m": "1"})
    from experiments.coord02.entry import (
        arm_policy_entry,
        run_child_factory,
    )
    inner = run_child_factory(
        DSN, task_id=TASK, gateway=gw, model="acq-model-child",
        allocation_id=child_seed["allocation_id"])

    def factory(task_id: str):
        def _build(node, child, rendered, operation_id=None,
                   attempt_id=None):
            return inner(node, child, rendered,
                         operation_id=operation_id,
                         attempt_id=attempt_id)
        return _build

    snap = snapshot_files(TASK)
    entry_bytes = arm_policy_entry("S", task_id=TASK, package_digest="none")
    validation = E.validate_on_development(
        DSN, entry_bytes=entry_bytes,
        requires=E._requires_for(TASK, snap), task_ids=[TASK],
        launcher_factory=_factory(tmp_path),
        constructor_factory=factory)
    assert validation["execution_admitted"], validation
    assert gw.calls, "validation child work never reached the model"
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM team_outputs WHERE"
                        " output::text LIKE %s", ("%ACQ_MODEL_CHILD%",))
            assert int(cur.fetchone()[0]) >= 1, \
                "no model child bytes were submitted"
            conn.commit()
