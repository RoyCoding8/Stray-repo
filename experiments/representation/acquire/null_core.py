"""Authored null core fixture for the core-substitution attribution control.

Same profile as the shared atom core but returns the full atom set as its
final object on ``start`` without proposing anything: paired with the same
adapters, any improvement observed with the searching core must come from
core proposals, not from adapter translation.
"""

from __future__ import annotations

import json
import sys


def _base(req):
    return {"profile": req["profile"], "profile_version": req["profile_version"],
            "action": req["action"], "task_id": req["task_id"],
            "composition_id": req["composition_id"],
            "core_digest": req["core_digest"],
            "adapter_digest": req["adapter_digest"]}


def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"null_core": True}}))
        return 0
    resp_path = argv[1]
    try:
        req = json.load(open(argv[0], encoding="utf-8"))
        if req["action"] not in ("start", "advance"):
            raise KeyError("no-search core handles start/advance only")
        atoms = req["payload"]["encoded_object"]["atoms"]
        if not isinstance(atoms, list) or not atoms:
            raise KeyError("no atoms")
    except (KeyError, TypeError, ValueError, OSError):
        raise SystemExit(1)
    out = _base(req)
    out.update({"status": "final", "result": {"final_object": {"kept": atoms}}})
    json.dump(out, open(resp_path, "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
