"""C3 connected qualification: six trajectories + 72 use records.

Runs through the connected implementation: DB-backed campaigns, the
model-backed learner and broker construction served by labeled
recording doubles at the gateway seams, repertoire freeze with digest
integrity, and fresh-process CLI use. Covers successful acquisition,
no-candidate, and causal I/R controls. Old authored fixtures live in
evidence-ad01/c3-authored and are never overwritten here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import learner as L
from experiments.ad01 import rotation, trajectory

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 96,
        "model_calls": 60}

ACQUIRED_SW = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
ACQUIRED_GR = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_graph(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)


def _arm_tasks(world: int, arm: str) -> list:
    ordered = [s["task_id"] for s in rotation.r_schedule(world)[:3]]
    if arm == "I":
        return [ordered[2], ordered[1], ordered[0]]
    return ordered


def _proposal_scripts(tasks: list, budgets: dict | None = None) -> list:
    scripts = []
    for target in tasks:
        family = "graph" if "-gr-" in target else "software"
        scripts.append({"text": json.dumps({
            "basis_references": ["obs-%s-seed" % target],
            "question": "investigate %s" % target,
            "next_action": {"kind": "development", "diagnostic": family,
                            "task_id": target,
                            "max_queries": (budgets or {}).get(target, 4)},
            "requested_resources": {"diagnostic_queries": 1}})})
    return scripts


class _C3Gateway:
    """Double at the gateway seam with split script streams.

    Learner operations draw from the proposal stream, construction
    operations from the family stream matching the task named in the
    operation id. Every call still travels through broker ensure and
    dispatch with settled receipts and measured costs; only the provider
    answers are recorded.
    """

    label = "AD01-C3-DEMUX-DOUBLE"

    def __init__(self, learner_scripts: list):
        self._learner = L.RecordingGatewayAdapter(learner_scripts)
        self._software = L.RecordingGatewayAdapter(
            [{"text": json.dumps({"entry": ACQUIRED_SW})}])
        self._graph = L.RecordingGatewayAdapter(
            [{"text": json.dumps({"entry": ACQUIRED_GR})}])

    def check_discovery(self):
        return self._learner.check_discovery()

    def check_auth(self):
        return self._learner.check_auth()

    def _stream(self, operation_id: str):
        if "-learner-" in operation_id:
            return self._learner
        if "-gr-" in operation_id:
            return self._graph
        return self._software

    def infer(self, request):
        return self._stream(request.operation_id).infer(request)

    def cancel(self, operation_id):
        return False


def run_trajectory(world: int, arm: str, out_dir: Path, dsn: str,
                   *, agenda_authorized: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = _arm_tasks(world, arm)
    budgets = {tasks[1]: 0} if arm == "I" else {}
    gateway = _C3Gateway(_proposal_scripts(tasks, budgets))
    cid = trajectory.campaign_id(world, arm, 0)
    trajectory.authorize_campaign(dsn, cid,
                                  authorized=agenda_authorized)
    seed = trajectory.ensure_campaign(
        dsn, cid, world, arm, dict(CHARTER),
        dict(CAPS, agenda_authorized=agenda_authorized), tasks=tasks)
    propose = L.propose_from_model(
        dsn, cid=cid, gateway=gateway, model="c3-connected-double",
        charter=dict(CHARTER), world=world, arm=arm,
        allocation_id=seed["allocation_id"])
    campaign = trajectory.run_campaign(
        world, arm, dict(CHARTER),
        dict(CAPS, agenda_authorized=agenda_authorized), tasks=tasks,
        propose=propose, campaign_seq=0, dsn=dsn,
        gateway=gateway, model="c3-connected-double",
        constructor="model")
    frozen = out_dir / ("repertoire-w%d-%s.json" % (world, arm))
    repertoire = trajectory.freeze_repertoire(campaign, frozen)
    assert repertoire["members"], \
        "connected trajectory retained nothing"
    membership = trajectory.worlds.world_membership(
        trajectory.worlds.FROZEN_DIR)
    use_tasks = []
    for pool in ("within", "transfer"):
        for domain in ("software", "graph"):
            use_tasks.extend(
                membership[str(world)][pool][domain][:3])
    use_path = out_dir / ("use-w%d-%s.json" % (world, arm))
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(frozen), "--world", str(world),
         "--arm", arm, "--tasks", ",".join(use_tasks),
         "--dsn", dsn, "--allocation-id", trajectory._alloc_id(campaign["campaign_id"])],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    records = json.loads(proc.stdout)
    accounting = trajectory.cost_union(campaign, records, dsn=dsn)
    campaign["accounting"] = accounting
    (out_dir / ("accounting-w%d-%s.json" % (world, arm))).write_text(
        json.dumps(accounting, sort_keys=True, indent=1) + "\n")
    use_path.write_text(json.dumps(records, sort_keys=True,
                                   indent=1) + "\n")
    (out_dir / ("campaign-w%d-%s.json" % (world, arm))).write_text(
        json.dumps(campaign, sort_keys=True, indent=1,
                   default=str) + "\n")
    return {
        "world": world, "arm": arm,
        "dispatched": [b["task_id"] for b in campaign["boundaries"]],
        "dispositions": [e["disposition"] for e in campaign["episodes"]],
        "acquired": sorted(
            {e["executable"]["capability_id"]
             for e in campaign["episodes"]
             if e.get("disposition") == "retained"}),
        "model_calls": accounting["total"]["model_calls"],
        "accounting": accounting["total"],
        "operation_ids": sorted(accounting["operations"]),
        "use": len(records)}


def run_trajectories(out_dir: Path, dsn: str, *, agenda_authorized: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"trajectories": [], "use_records": 0, "dsn_label": "doubled"}
    for world in (0, 1, 2):
        for arm in ("I", "R"):
            entry = run_trajectory(world, arm, out_dir, dsn,
                                   agenda_authorized=agenda_authorized)
            summary["trajectories"].append(entry)
            summary["use_records"] += entry["use"]
    (out_dir / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=1) + "\n")
    return summary


if __name__ == "__main__":
    import os
    from experiments.ad01.s09_run_isolation import MissingRouteError
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path("evidence-ad01/c3-trajectories")
    # No socket default: a session that named no database store refuses
    # rather than connecting to a box the operator never pointed at.
    dsn = os.environ.get("EC02_C3_DSN", "")
    if not dsn:
        raise MissingRouteError(
            "EC02_C3_DSN must name the qualification's database store")
    assert "live" not in dsn
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(dsn, Path("migrations"))
    E.designate_db(dsn, kind="disposable",
                   purpose="C3 connected deterministic qualification")
    E.prepare_disposable_db(dsn, Path("migrations"))
    summary = run_trajectories(
        out, dsn, agenda_authorized=int(os.environ["AD01_AGENDA_AUTHORIZED"]))
    print(json.dumps(summary, indent=1))
