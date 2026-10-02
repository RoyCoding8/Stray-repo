"""Authored graph-family adapter fixture for Representation Lane D.

Translation only, no search: ``encode`` maps a graph task to an abstract
atom list (vertex units first, then edge units, mirroring the baseline
atomization) plus declared auxiliary material carrying the source snapshot
the core never sees raw; ``decode`` maps kept atom indices back to an
id-preserving subgraph. Applicability refuses non-graph tasks, over-cap
graphs and malformed shapes; witness preservation is left to the oracle.
"""

from __future__ import annotations

import json
import sys

FAMILY = "graph"
MAX_VERTICES = 10
MAX_EDGES = 18
TUNABLES = {"chunk_frac": 2, "max_proposals": 4, "order": "tail"}


def _base(req):
    return {"profile": req["profile"], "profile_version": req["profile_version"],
            "action": req["action"], "task_id": req["task_id"],
            "composition_id": req["composition_id"],
            "core_digest": req["core_digest"],
            "adapter_digest": req["adapter_digest"]}


def _refuse(req, reason, detail=""):
    out = _base(req)
    out.update({"status": "refuse", "reason": reason, "detail": detail[:256]})
    return out


def _check_shape(task):
    vertices = task.get("vertices")
    edges = task.get("edges")
    if not isinstance(vertices, list) or not isinstance(edges, list):
        return "invalid-task"
    if len(vertices) > MAX_VERTICES or len(edges) > MAX_EDGES:
        return "over-cap"
    if any(not isinstance(v, int) for v in vertices):
        return "invalid-task"
    vset = set(vertices)
    if len(vset) != len(vertices):
        return "invalid-task"
    for entry in edges:
        if (not isinstance(entry, (list, tuple)) or len(entry) != 2
                or entry[0] not in vset or entry[1] not in vset
                or entry[0] == entry[1]):
            return "invalid-task"
    seen = set()
    for entry in edges:
        key = tuple(sorted(entry))
        if key in seen:
            return "invalid-task"
        seen.add(key)
    return ""


def _units(task):
    return [("v", v) for v in task["vertices"]] + \
        [("e", i) for i in range(len(task["edges"]))]


def _encode(req):
    task = req["payload"]["source_task"]
    spec = req["payload"]["domain_spec"]
    if not isinstance(task, dict) or task.get("family") != FAMILY:
        return _refuse(req, "unsupported", "not a graph task")
    if not isinstance(spec, dict) or spec.get("family") != FAMILY:
        return _refuse(req, "unsupported", "domain-spec family mismatch")
    problem = _check_shape(task)
    if problem:
        return _refuse(req, "unsupported", problem)
    units = _units(task)
    aux = {"task": task, "tunables": dict(TUNABLES)}
    out = _base(req)
    out.update({"status": "ok",
                "result": {"encoded_object": {"atoms": list(range(len(units))),
                                              "tunables": dict(TUNABLES),
                                              "family": FAMILY},
                           "aux": aux,
                           "applicability": {"supported": True,
                                             "reason": "graph-shrink"}}})
    return out


def _decode(req):
    proposal = req["payload"]["proposal"]
    source = req["payload"]["source_task"]
    aux = req["payload"]["aux"]
    try:
        task = aux.get("task") or source
        units = _units(task)
        kept = proposal["kept"]
        if not isinstance(kept, list) or \
                any(not isinstance(i, int) or i < 0 or i >= len(units)
                    for i in kept):
            return _refuse(req, "malformed", "kept indices out of range")
        if sorted(kept) != kept:
            return _refuse(req, "malformed", "kept indices unordered")
        keep = set(kept)
        gone = {units[i][1] for i in range(len(units))
                if i not in keep and units[i][0] == "v"}
        drop_e = {units[i][1] for i in range(len(units))
                  if i not in keep and units[i][0] == "e"}
        keep_v = [v for v in task["vertices"] if v not in gone]
        if not keep_v:
            return _refuse(req, "malformed", "empty vertex set")
        kept_v = set(keep_v)
        edges = [list(e) for e in task["edges"]]
        keep_e = [e for i, e in enumerate(edges)
                  if i not in drop_e and e[0] in kept_v and e[1] in kept_v]
        candidate = {"family": FAMILY, "task_id": task["task_id"],
                     "vertices": keep_v, "edges": keep_e,
                     "seed": task.get("seed")}
    except (KeyError, TypeError, AttributeError):
        return _refuse(req, "malformed", "undecodable proposal")
    out = _base(req)
    out.update({"status": "ok", "result": {"candidate_source": candidate}})
    return out


def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"gr_adapter": True}}))
        return 0
    try:
        req = json.load(open(argv[0], encoding="utf-8"))
        action = req["action"]
        if action == "encode":
            out = _encode(req)
        elif action == "decode":
            out = _decode(req)
        else:
            out = _refuse(req, "unsupported", "adapter cannot start")
    except (KeyError, TypeError, ValueError, OSError):
        raise SystemExit(1)
    json.dump(out, open(argv[1], "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
