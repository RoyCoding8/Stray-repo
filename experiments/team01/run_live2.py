"""Live repair-path runner (Team 01 correction campaign).

Runs S/P/T repair episodes plus labeled diagnostic probes through
solver.run_live_repair_episode with the real broker-routed gateway.
Writes episode records under --evidence-root and run envelopes under
--runs-root. Every episode draws a bounded per-episode allocation; the
driver reports totals but never tops up a budget after seeing outcomes.

Probes (diagnostic, never scored):
  substitution : replace w1 constructor bytes with valid-but-wrong patch
  disconnect   : drop w1 constructor output, expect refusal
  incompatible : decompose with an authored interface break on w2,
                 then one bounded repair round or refusal
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from settlement.launcher_local import LocalLauncher  # noqa: E402

from experiments.team01 import live as _live  # noqa: E402
from experiments.team01 import oracle, solver  # noqa: E402

TASK_PROBES = {
    "team01-t01": {
        "wrong_w1": None,  # filled by _wrong_patch
        "renamed_w2": None,
    },
}


def _wrong_patch(task_id: str) -> dict:
    snap = {"spec.json": (oracle.TASKS / task_id / "spec.json").read_text()}
    for mod in sorted((oracle.TASKS / task_id / "src").glob("*.py")):
        snap["src/" + mod.name] = mod.read_text()
    files = dict(snap)
    if task_id == "team01-t01":
        files["src/numops.py"] = files["src/numops.py"].replace(
            "return (max(numbers) - min(numbers)) if numbers else 0",
            "return len(numbers)")
    return {p: files[p] for p in files if p.startswith("src/")}


def _renamed_patch(task_id: str) -> dict:
    tdir = oracle.TASKS / task_id
    mods = sorted((tdir / "src").glob("*.py"))
    owned = [m for m in mods if m.name != "app.py"]
    target = owned[-1]
    body = target.read_text()
    stem = target.stem
    fn = {"numops": "summarize", "textops": "transform",
          "producer": "to_base", "consumer": "from_base",
          "detect": "detect", "operate": "operate",
          "compute": "compute", "validate": "validate"}.get(stem)
    if fn is not None:
        body = body.replace("def %s(" % fn, "def x%s(" % fn, 1)
    return {"src/" + target.name: body}


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--task", default="team01-t01")
    parser.add_argument("--arms", default="S,P,T")
    parser.add_argument("--probes", default="substitution,disconnect,"
                                            "incompatible")
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--tag", default="live2")
    parser.add_argument("--shape-override", default="",
                        help="pinned shape for the incompatible probe only")
    args = parser.parse_args(argv)
    dsn = args.dsn
    from settlement import db as _db
    _db.apply_migrations(dsn, ROOT / "migrations")
    runs_root = Path(args.runs_root)
    evidence_root = Path(args.evidence_root)
    runs_root.mkdir(parents=True, exist_ok=True)
    gateway = _live.make_gateway()
    launchers = {"local-process": LocalLauncher(str(runs_root))}
    summary = {"tag": args.tag, "task": args.task, "at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "episodes": []}
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        record = solver.run_live_repair_episode(
            dsn, gateway=gateway, launchers=launchers, runs_root=runs_root,
            evidence_root=evidence_root, tag=args.tag, task_id=args.task,
            arm=arm)
        summary["episodes"].append(_brief(record))
        print("%s %s outcome=%s protected=%s" % (
            arm, record["episode_id"], record["outcome"],
            json.dumps(record.get("protected"))[:120]))
    probes = [p.strip() for p in args.probes.split(",") if p.strip()]
    if "substitution" in probes:
        record = solver.run_live_repair_episode(
            dsn, gateway=gateway, launchers=launchers, runs_root=runs_root,
            evidence_root=evidence_root, tag=args.tag, task_id=args.task,
            arm="S", probe="substitution",
            substitute={"w1": _wrong_patch(args.task)})
        summary["episodes"].append(_brief(record))
        print("probe substitution outcome=%s" % record["outcome"])
    if "disconnect" in probes:
        record = solver.run_live_repair_episode(
            dsn, gateway=gateway, launchers=launchers, runs_root=runs_root,
            evidence_root=evidence_root, tag=args.tag, task_id=args.task,
            arm="S", probe="disconnect", disconnect=["w1"])
        summary["episodes"].append(_brief(record))
        print("probe disconnect outcome=%s" % record["outcome"])
    if "incompatible" in probes:
        record = solver.run_live_repair_episode(
            dsn, gateway=gateway, launchers=launchers, runs_root=runs_root,
            evidence_root=evidence_root, tag=args.tag, task_id=args.task,
            arm="T", probe="incompatible",
            shape_override=args.shape_override or None,
            authored_nodes={"w2": {
                "files": _renamed_patch(args.task),
                "label": "diagnostic: renamed module entry point"}},
            repair_rounds=1)
        summary["episodes"].append(_brief(record))
        print("probe incompatible outcome=%s repairs=%s" % (
            record["outcome"], record["repairs"]))
    (evidence_root / "vertical-path-summary.json").write_text(
        json.dumps(summary, indent=2))
    return 0


def _brief(record: dict) -> dict:
    protected = record.get("protected") or {}
    return {"episode_id": record["episode_id"], "arm": record["arm"],
            "probe": record.get("probe"), "shape": record.get("shape"),
            "outcome": record["outcome"],
            "protected": "%s/%s" % (protected.get("passed"),
                                    protected.get("total")),
            "model_calls": record.get("model_calls"),
            "tool_calls": record.get("tool_calls"),
            "usage": record.get("usage"),
            "repairs": record.get("repairs")}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
