"""Authored software-family adapter fixture for Representation Lane D.

Translation only, no search: ``encode`` maps a software task to an abstract
atom list (one atom per op position) plus declared auxiliary material
carrying the source snapshot the core never sees raw; ``decode`` maps kept
atom indices back to an op subsequence. Applicability refuses non-software
tasks, over-cap sequences and malformed ops; witness preservation is left
to the oracle.
"""

from __future__ import annotations

import json
import sys

FAMILY = "software"
MAX_OPS = 24
OP_NAMES = ("set", "get", "clear", "del")
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


def _check_ops(ops):
    if not isinstance(ops, list) or not ops or len(ops) > MAX_OPS:
        return False
    for entry in ops:
        if not isinstance(entry, dict) or entry.get("op") not in OP_NAMES:
            return False
        if entry["op"] == "set" and ("key" not in entry or "value" not in entry):
            return False
        if entry["op"] == "get" and ("key" not in entry or "id" not in entry):
            return False
        if entry["op"] == "del" and "key" not in entry:
            return False
    return True


def _encode(req):
    task = req["payload"]["source_task"]
    spec = req["payload"]["domain_spec"]
    if not isinstance(task, dict) or task.get("family") != FAMILY:
        return _refuse(req, "unsupported", "not a software task")
    if not isinstance(spec, dict) or spec.get("family") != FAMILY:
        return _refuse(req, "unsupported", "domain-spec family mismatch")
    if not _check_ops(task.get("ops")):
        if isinstance(task.get("ops"), list) and len(task["ops"]) > MAX_OPS:
            return _refuse(req, "unsupported", "over-cap")
        return _refuse(req, "unsupported", "invalid-task")
    witness = task.get("witness") or {}
    if not isinstance(witness, dict) or "observation" not in witness:
        return _refuse(req, "unsupported", "no designated observation")
    atoms = list(range(len(task["ops"])))
    aux = {"task": task, "tunables": dict(TUNABLES)}
    out = _base(req)
    out.update({"status": "ok",
                "result": {"encoded_object": {"atoms": atoms,
                                              "tunables": dict(TUNABLES),
                                              "family": FAMILY},
                           "aux": aux,
                           "applicability": {"supported": True,
                                             "reason": "software-shrink"}}})
    return out


def _decode(req):
    proposal = req["payload"]["proposal"]
    source = req["payload"]["source_task"]
    aux = req["payload"]["aux"]
    try:
        kept = proposal["kept"]
        ops = (aux.get("task") or source)["ops"]
        if not isinstance(kept, list) or \
                any(not isinstance(i, int) or i < 0 or i >= len(ops)
                    for i in kept):
            return _refuse(req, "malformed", "kept indices out of range")
        if sorted(kept) != kept:
            return _refuse(req, "malformed", "kept indices unordered")
        task = aux.get("task") or source
        candidate = {"family": FAMILY, "task_id": task["task_id"],
                     "fault": task["fault"],
                     "ops": [ops[i] for i in kept],
                     "witness": task["witness"], "seed": task.get("seed")}
    except (KeyError, TypeError):
        return _refuse(req, "malformed", "undecodable proposal")
    out = _base(req)
    out.update({"status": "ok", "result": {"candidate_source": candidate}})
    return out


def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"sw_adapter": True}}))
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
