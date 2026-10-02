"""C3 qualification: six deterministic trajectories + 72 use records.

Labeled doubles only (no live calls). Each trajectory runs through the
public run_campaign entry with a recording propose double whose outputs
are chosen independently of implementation. I arms choose opportunities;
R arms take the frozen curriculum item, then share the learner.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import rotation, trajectory

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}


def choosing_propose(plan: list, budgets: dict | None = None):
    state = {"n": 0}

    def propose(seen, asked):
        assert seen["observations"], "learner saw no experience"
        assert asked.get("objective") == CHARTER["objective"], \
            "learner saw a manufactured charter: %r" % (asked,)
        if state["n"] >= len(plan):
            seed = seen["observations"][0]
            return {"basis_references": [seed["observation_id"]],
                    "question": "done", "next_action": {"kind": "stop"},
                    "requested_resources": {}}
        target = plan[state["n"]]
        budget = (budgets or {}).get(target, 16)
        state["n"] += 1
        seed = seen["observations"][0]
        family = "graph" if "-gr-" in target else "software"
        return {"basis_references": [seed["observation_id"]],
                "question": "investigate %s" % target,
                "next_action": {"kind": "development",
                                "diagnostic": family,
                                "task_id": target,
                                "max_queries": budget},
                "requested_resources": {"diagnostic_queries": 1}}

    return propose


def run_trajectories(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"trajectories": [], "use_records": 0}
    for world in (0, 1, 2):
        dev = rotation.r_schedule(world)
        sw = [s["task_id"] for s in dev if s["domain"] == "software"]
        for arm in ("I", "R"):
            if arm == "I":
                tasks = [sw[1], sw[0], sw[2]]
                budgets = {sw[0]: 0}
            else:
                tasks = [s["task_id"] for s in dev[:3]]
                budgets = {}
            campaign = trajectory.run_campaign(
                world, arm, dict(CHARTER), dict(CAPS), tasks=tasks,
                propose=choosing_propose(tasks, budgets))
            frozen = out_dir / ("repertoire-w%d-%s.json" % (world, arm))
            repertoire = trajectory.freeze_repertoire(campaign, frozen)
            membership = trajectory.worlds.world_membership(
                trajectory.worlds.FROZEN_DIR)
            use_tasks = []
            for pool in ("within", "transfer"):
                for domain in ("software", "graph"):
                    use_tasks.extend(
                        membership[str(world)][pool][domain][:3])
            records = trajectory.run_use(
                repertoire, world, arm, use_tasks,
                {"tokens": 0, "sandbox_ops": 0})
            (out_dir / ("use-w%d-%s.json" % (world, arm))).write_text(
                json.dumps(records, sort_keys=True, indent=1) + "\n")
            (out_dir / ("campaign-w%d-%s.json" % (world, arm))).write_text(
                json.dumps(campaign, sort_keys=True, indent=1,
                           default=str) + "\n")
            summary["trajectories"].append({
                "world": world, "arm": arm,
                "dispatched": [b["task_id"] for b in
                               campaign["boundaries"]],
                "dispositions": [e["disposition"] for e in
                                 campaign["episodes"]],
                "use": len(records)})
            summary["use_records"] += len(records)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=1) + "\n")
    return summary


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path("evidence-ad01/c3-trajectories")
    summary = run_trajectories(out)
    print(json.dumps(summary, indent=1))
