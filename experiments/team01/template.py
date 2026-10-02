from __future__ import annotations

import hashlib
import json
from pathlib import Path

from settlement.common import SettlementError

from . import oracle

TEMPLATE_VERSION = "coordination-template/1"
MAX_BUILDS = 2

DIRECTIVE = ("bind the producer/consumer interface contract before independent"
             " edits, then exercise a boundary case through both modules")

BUILDS = (
    {"id": "build-1-bind-first",
     "directive": DIRECTIVE,
     "shape": "decompose",
     "boundary_probe": False},
    {"id": "build-2-bind-first-with-probe",
     "directive": DIRECTIVE,
     "shape": "decompose",
     "boundary_probe": True},
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _dev_tasks(records: list) -> set:
    return {r["task_id"] for r in records}


def build_candidates(records: list, max_builds: int = MAX_BUILDS) -> list:
    if max_builds > MAX_BUILDS:
        raise SettlementError("at most %d template builds" % MAX_BUILDS)
    tasks = _dev_tasks(records)
    foreign = tasks - set(oracle.SPLITS["development"])
    if foreign:
        raise SettlementError("template builds use development evidence only:"
                              " refused %s" % sorted(foreign))
    if not tasks:
        return []
    candidates = []
    for spec in BUILDS[:max_builds]:
        won = [r for r in records if r.get("outcome") == "success"]
        known = sorted({r["episode_id"] for r in records
                        if r.get("probe") == "incompatible"
                        and r.get("outcome") == "failure"})
        candidates.append({
            "id": spec["id"], "version": TEMPLATE_VERSION,
            "directive": spec["directive"], "shape": spec["shape"],
            "boundary_probe": spec["boundary_probe"],
            "applicability": {
                "families": sorted(oracle.TASK_FAMILY[t] for t in tasks),
                "required_bindings": ["interface-contract", "owned-partition"],
                "refuses": "missing bindings or changed assumptions"},
            "required_inputs": ["interface-contract", "owned-partition"],
            "checks": ["public-boundary-probe"],
            "ceiling": {"model_invocations": 2, "input_tokens": 4000,
                        "output_tokens": 1000},
            "supporting_episodes": sorted(tasks),
            "known_failures": known,
            "dev_public_failures": sum(
                r.get("public", {}).get("failed", 0) for r in records),
            "dev_wins": len(won)})
    return candidates


def select_candidate(candidates: list, records: list) -> tuple:
    if not candidates:
        raise SettlementError("no template candidate to select")
    ranked = sorted(candidates,
                    key=lambda c: (c["dev_public_failures"], c["id"]))
    winner = ranked[0]
    frozen_out = [{"id": c["id"],
                   "reason": "more development public failures"
                             " (%d vs %d)" % (c["dev_public_failures"],
                                              winner["dev_public_failures"])}
                  for c in ranked[1:]]
    return winner, frozen_out


def freeze_template(evidence_root, *, winner: dict, frozen_out: list,
                    builds: list) -> dict:
    record = {"template": winner["id"], "version": TEMPLATE_VERSION,
              "directive": winner["directive"], "shape": winner["shape"],
              "boundary_probe": winner["boundary_probe"],
              "applicability": winner["applicability"],
              "required_inputs": winner["required_inputs"],
              "checks": winner["checks"], "ceiling": winner["ceiling"],
              "supporting_episodes": winner["supporting_episodes"],
              "known_failures": winner["known_failures"],
              "builds_attempted": [b["id"] for b in builds],
              "frozen_out": frozen_out,
              "source": "dev-evidence-only"}
    raw = (json.dumps(record, sort_keys=True) + "\n").encode()
    record["digest"] = _digest(raw)
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "template-frozen.json").write_bytes(
        (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
    return record


def freeze_none(evidence_root, *, reason: str) -> dict:
    record = {"template": "none", "version": TEMPLATE_VERSION,
              "digest": None, "frozen_out": [], "source": "dev-evidence-only",
              "reason": reason}
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "template-frozen.json").write_bytes(
        (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
    return record


def load_template(evidence_root) -> dict | None:
    try:
        return json.loads((Path(evidence_root) / "template-frozen.json")
                          .read_text())
    except (OSError, ValueError):
        return None


def apply_template(record: dict, task_id: str) -> dict:
    if not record or record.get("template") == "none":
        return {"applicable": False, "changed_decision": False,
                "reason": "no frozen template: cold policy",
                "directive": {}}
    family = oracle.TASK_FAMILY.get(task_id, "")
    if family not in record.get("applicability", {}).get("families", []):
        return {"applicable": False, "changed_decision": False,
                "reason": "family %s outside frozen applicability" % family,
                "directive": {}}
    directive = {"shape": record["shape"],
                 "boundary_probe": record["boundary_probe"],
                 "binding_first": True}
    return {"applicable": True, "changed_decision": True,
            "reason": "frozen %s binds %s first" % (record["template"], family),
            "directive": directive}
