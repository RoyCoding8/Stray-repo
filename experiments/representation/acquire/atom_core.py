"""Authored shared atom core fixture for Representation Lane D.

Domain-blind coarse search over abstract atom indices. The core never sees
raw source tasks, only an anonymous atom list. It exposes an explicit
tunable interface through ``encoded_object.tunables`` with keys
``chunk_frac``, ``max_proposals`` and ``order``. Stage adapters supply the
tunables; the core bytes are identical across stages.
"""

from __future__ import annotations

import json
import sys

DEFAULT_TUNABLES = {"chunk_frac": 2, "max_proposals": 4, "order": "tail"}
ORDERS = ("head", "tail")


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


def _tunables(raw):
    tun = dict(DEFAULT_TUNABLES)
    if raw is None:
        return tun
    if not isinstance(raw, dict):
        return None
    try:
        frac = int(raw.get("chunk_frac", 2))
        maxp = int(raw.get("max_proposals", 4))
        order = str(raw.get("order", "tail"))
    except (TypeError, ValueError):
        return None
    if frac < 1 or maxp < 1 or maxp > 16 or order not in ORDERS:
        return None
    tun.update({"chunk_frac": frac, "max_proposals": maxp, "order": order})
    return tun


def _proposal(kept, chunk, order):
    if not kept or chunk < 1:
        return list(kept)
    if order == "head":
        doomed = set(kept[:chunk])
    else:
        doomed = set(kept[-chunk:])
    trial = [atom for atom in kept if atom not in doomed]
    return trial if trial else list(kept)


def main(argv):
    if argv == ["--selftest"]:
        print(json.dumps({"status": "ok", "data": {"atom_core": True}}))
        return 0
    resp_path = argv[1]
    try:
        req = json.load(open(argv[0], encoding="utf-8"))
        action = req["action"]
        payload = req["payload"]
        if action not in ("start", "advance"):
            return _finish(resp_path, _refuse(req, "unsupported",
                                              "core handles start/advance only"))
        enc = payload["encoded_object"]
        atoms = enc["atoms"]
        if not isinstance(atoms, list) or not atoms or \
                any(not isinstance(a, int) for a in atoms):
            return _finish(req, _refuse(req, "malformed",
                                        "encoded atoms must be a nonempty int list"))
        tun = _tunables(enc.get("tunables"))
        if tun is None:
            return _finish(resp_path, _refuse(req, "malformed",
                                              "tunables outside the interface"))
        if action == "start":
            kept = list(atoms)
            chunk = max(1, len(kept) // tun["chunk_frac"])
            used = 0
        else:
            state = req.get("state") or {}
            kept = list(state.get("kept", atoms))
            last = state.get("last")
            feedback = payload.get("feedback") or {}
            if feedback.get("verdict") == "preserved" and \
                    isinstance(last, list) and last:
                kept = list(last)
            chunk = max(1, int(state.get("chunk", 1)) // 2)
            used = int(state.get("used", 0))
        if used >= tun["max_proposals"]:
            return _finish(resp_path, _final(req, kept))
        trial = _proposal(kept, chunk, tun["order"])
        state = {"kept": kept, "last": trial, "chunk": chunk, "used": used + 1}
        if trial == kept:
            return _finish(resp_path, _final(req, kept))
        out = _base(req)
        out.update({"status": "ok", "result": {"proposal": {"kept": trial}},
                    "state": state})
        return _finish(resp_path, out)
    except (KeyError, TypeError, ValueError, OSError):
        try:
            req = json.load(open(argv[0], encoding="utf-8"))
        except (OSError, ValueError):
            raise SystemExit(1)
        return _finish(resp_path, _refuse(req, "malformed", "unreadable request"))


def _final(req, kept):
    out = _base(req)
    out.update({"status": "final", "result": {"final_object": {"kept": kept}}})
    return out


def _finish(resp_path, out):
    json.dump(out, open(resp_path, "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
