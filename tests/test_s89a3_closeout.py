"""S89-A3 closeout: one proven public acquisition/check/retention/use path.

Provenance labels used here and in the workstream report:
SIMULATED_MODEL_SW_SOURCE is an authored control standing in for model
bytes at the gateway boundary only; every other layer is production code.
ARCHIVED_MODEL_SOURCE entries are actual live model bytes from
evidence_inv01_live and are never edited. A delegating wrapper counts as
valid execution through the fixed child path, not a novel algorithm.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DB = "s89_a3_closeout"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"
ACQ_CID = "ad01-w0-I-60"
REJ_CID = "ad01-w0-I-61"

SIMULATED_MODEL_SW_SOURCE = (
    "def acquired_sw_bare(task, oracle, max_queries=16):\n"
    "    return reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)

INVALID_SOURCE = "not python {{{"

FAILING_MEMBER_SOURCE = (
    "def acquired_sw_boom(task, oracle, max_queries=16):\n"
    "    raise RuntimeError(\"s89a3-control-failure\")\n"
)


def _scrub_runs():
    shutil.rmtree(ROOT / ".ad01-runs", ignore_errors=True)


@pytest.fixture(scope="module")
def store():
    assert "live" not in DSN
    assert DB.startswith("s89_a3_")
    subprocess.run(["createdb", "-h", "/var/run/postgresql",
                    "-U", "ubuntu", DB],
                   check=True, capture_output=True, text=True, timeout=60)
    try:
        from settlement import db
        db.apply_migrations(DSN, MIGRATIONS)
        yield DSN
    finally:
        subprocess.run(["dropdb", "-h", "/var/run/postgresql",
                        "-U", "ubuntu", DB],
                       capture_output=True, text=True, timeout=60)
        _scrub_runs()


class ScriptedModelBoundaryDouble:
    label = "S89A3-SCRIPTED-MODEL-BOUNDARY"

    def __init__(self, sources, usage=None):
        from settlement.gateway import Usage
        self._sources = list(sources)
        self._usage = usage or Usage(input_tokens=11, output_tokens=7)
        self.calls = []

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
                             json.dumps({"entry": source,
                                         "notes": "s89a3 scripted bytes"}),
                             {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _campaign(dsn, cid):
    from experiments.ad01 import trajectory
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return trajectory.ensure_campaign(
        dsn, cid, 0, "I", CHARTER,
        {"agenda_authorized": 100000, "max_boundaries": 6,
         "diagnostic_queries": 16})


def test_public_acquisition_check_retention_use(store, tmp_path):
    from experiments.ad01 import construct as C
    from experiments.ad01 import method_exec, trajectory, worlds
    contract = method_exec.child_contract()
    assert contract["callables"]["reduce_software"]["binding"] == \
        "reducers.reduce_software"
    _campaign(store, ACQ_CID)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gateway = ScriptedModelBoundaryDouble([SIMULATED_MODEL_SW_SOURCE])
    member = C.construct_method(
        store, campaign_id=ACQ_CID, task=task,
        experience={"observations": []},
        budget={"max_output_tokens": 512},
        gateway=gateway, model="s89a3-scripted-double")
    assert member["authored"] is False
    assert member["method_source"] == SIMULATED_MODEL_SW_SOURCE
    assert member["capability_id"].startswith("acquired-sw-")
    assert member["source_digest"] == hashlib.sha256(
        SIMULATED_MODEL_SW_SOURCE.encode("utf-8")).hexdigest()
    assert member["lineage"]["init_operation"]
    assert len(gateway.calls) == 1
    episode = trajectory.dev_episode(
        DEV_TASK, "seed-sw-greedy", max_queries=16,
        member=member, result=member["validation"]["result"])
    assert episode["disposition"] == "retained"
    assert episode["check"]["verdict"] == "preserved"
    assert episode["final_size"] < episode["initial_size"]
    executable = episode["executable"]
    assert executable["authored"] is False
    assert executable["method_source"] == SIMULATED_MODEL_SW_SOURCE
    assert executable["scope"] == {"family": "software"}
    repertoire = {"campaign_id": ACQ_CID, "members": [executable]}
    frozen = tmp_path / "s89a3-repertoire.json"
    trajectory.freeze_repertoire(
        {"campaign_id": ACQ_CID, "queries": 0, "episodes": [episode]},
        frozen)
    loaded = trajectory.load_repertoire(frozen)
    assert loaded["members"] == repertoire["members"]
    allocation = "ad01-campaign-%s" % ACQ_CID
    [record] = trajectory.run_use(
        loaded, 0, "I", [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        dsn=store, allocation_id=allocation)
    assert record["selected"] == member["capability_id"]
    assert record["executed"] == member["capability_id"]
    assert record["executed_source"] == SIMULATED_MODEL_SW_SOURCE
    assert record["fallback_reason"] == ""
    assert record["verdict"] == "preserved"
    assert record["operation_ids"]
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--dsn", store,
         "--allocation-id", allocation, "--world", "0", "--arm", "I",
         "--tasks", USE_TASK],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    [fresh] = json.loads(proc.stdout)
    assert fresh["selected"] == member["capability_id"]
    assert fresh["executed"] == member["capability_id"]
    assert fresh["executed_source"] == SIMULATED_MODEL_SW_SOURCE
    assert fresh["fallback_reason"] == ""


def test_archived_model_bytes_execute_through_fixed_child():
    from scripts import s89_diagnose as diag
    export_dir = str(ROOT / "evidence_inv01_live" / "exports")
    [candidate] = [c for c in diag.extract_candidates(export_dir)
                   if c["digest"].startswith("d8fa9e5e")]
    assert "NameError" in candidate["old_failure"]
    report = diag.run_candidate(
        candidate, execute_fn=diag.current_tree_execute, max_queries=16)
    assert report["new_outcome"] == "executed"
    assert report["next_failure"] is None


def test_invalid_candidate_refused_and_use_falls_back(store):
    from experiments.ad01 import construct as C
    from experiments.ad01 import trajectory, worlds
    _campaign(store, REJ_CID)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK)
    gateway = ScriptedModelBoundaryDouble([INVALID_SOURCE])
    with pytest.raises(C.ConstructionFailed):
        C.construct_method(
            store, campaign_id=REJ_CID, task=task,
            experience={"observations": []},
            budget={"max_output_tokens": 512},
            gateway=gateway, model="s89a3-scripted-double")
    assert len(gateway.calls) == 4
    broken = trajectory.dev_episode(
        DEV_TASK, "seed-sw-greedy", max_queries=1, break_candidate=True)
    assert broken["disposition"] == "rejected"
    assert broken["check"]["verdict"] != "preserved"
    assert broken["reason"]
    [empty] = trajectory.run_use(
        {"campaign_id": REJ_CID, "members": []}, 0, "I",
        [USE_TASK], {"tokens": 0, "sandbox_ops": 0})
    assert empty["selected"] == "incumbent"
    assert empty["executed"] == "incumbent"
    assert "no eligible repertoire member" in empty["fallback_reason"]
    failing = {"capability_id": "acquired-sw-s89a3boom",
               "method_source": FAILING_MEMBER_SOURCE,
               "entry": "acquired_sw_boom",
               "params": {"max_queries": 16},
               "scope": {"family": "software"}, "authored": False,
               "source_digest": hashlib.sha256(
                   FAILING_MEMBER_SOURCE.encode("utf-8")).hexdigest()}
    [fallback] = trajectory.run_use(
        {"campaign_id": REJ_CID, "members": [failing]}, 0, "I",
        [USE_TASK], {"tokens": 0, "sandbox_ops": 0},
        dsn=store, allocation_id="ad01-campaign-%s" % REJ_CID)
    assert fallback["requested"] == "acquired-sw-s89a3boom"
    assert fallback["selected"] == "acquired-sw-s89a3boom"
    assert fallback["executed"] == "incumbent"
    assert "member execution failed" in fallback["fallback_reason"]
