"""AG01 shared agenda policy: observation grammar, rotation, R/Q selection.

Implements docs/design/AGENDA-01-IMPLEMENTATION.md section 4 and rows
AG01-D04 through AG01-D06 of reports/DECISIONS.md. Pure functions only:
no DB, no IO, no model calls. R and Q share candidate generation,
observation access, parser, rotation and every mechanical safety rule;
Q adds only continuation qualification (routes Q1/Q2/Q3).

Version note: this module publishes ``AG01-OBS-1`` / ``AG01-R-1`` /
``AG01-Q-1``. reports/DECISIONS.md rows AG01-D04/D05 use the slash form
(``AG01-OBS/1``); the hyphen form here follows the lane brief and is
filed as a change request in reports/workstreams/ag01-policy.md.
"""

from __future__ import annotations

from typing import Any

from .agenda import SEED_CLASSES, seed_order
from .common import SettlementError, payload_digest

OBS_GRAMMAR_VERSION = "AG01-OBS-1"
POLICY_R_VERSION = "AG01-R-1"
POLICY_Q_VERSION = "AG01-Q-2"

VALUES = ("true", "false", "unknown")
DECISIVE = ("true", "false")
OBS_FIELDS = ("prop", "scope", "dep", "dep_version",
              "value", "source_attempt", "receipt", "epoch")
OPEN = "open"
CONTINUATION = "continuation"


def _norm_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value in VALUES:
        return value
    return None


def parse_observations(raw: Any, current_epoch: int) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return {"grammar": OBS_GRAMMAR_VERSION, "observations": accepted,
                "rejected": [{"index": None, "reason": "observations-must-be-a-list"}],
                "conflicts": []}
    for index, item in enumerate(raw):
        obs, reason = _parse_one(item, current_epoch)
        if obs is None:
            rejected.append({"index": index, "reason": reason})
        else:
            obs["index"] = index
            accepted.append(obs)
    return {"grammar": OBS_GRAMMAR_VERSION, "observations": accepted,
            "rejected": rejected, "conflicts": _conflicts(accepted)}


def _parse_one(item: Any, current_epoch: int) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(item, dict):
        return None, "observation-must-be-a-mapping"
    for field in OBS_FIELDS:
        if field not in item:
            return None, f"missing-field:{field}"
    for field in ("prop", "scope", "dep", "source_attempt", "receipt"):
        if not isinstance(item[field], str) or not item[field].strip():
            return None, f"bad-field:{field}"
    for field in ("dep_version", "epoch"):
        if not isinstance(item[field], int) or item[field] < 0:
            return None, f"bad-field:{field}"
    value = _norm_value(item["value"])
    if value is None:
        return None, "bad-field:value"
    if item["epoch"] > current_epoch:
        return None, "future-epoch"
    obs = {field: item[field] for field in OBS_FIELDS}
    obs["value"] = value
    if item.get("simulated") is True:
        obs["simulated"] = True
    return obs, ""


def _conflicts(accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for obs in accepted:
        key = (obs["prop"], obs["scope"], obs["dep"], obs["dep_version"])
        groups.setdefault(key, []).append(obs)
    out = []
    for key, members in sorted(groups.items()):
        seen = sorted({m["value"] for m in members if m["value"] in DECISIVE})
        if len(seen) > 1:
            out.append({"prop": key[0], "scope": key[1], "dep": key[2],
                        "dep_version": key[3], "values": seen,
                        "indexes": [m["index"] for m in members]})
    return out


def rotation_order(candidates: list[dict[str, Any]],
                   cursor: int = 0,
                   tie_order: list[str] | None = None) -> dict[str, Any]:
    stubs = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or "id" not in candidate \
                or "seed_class" not in candidate:
            raise SettlementError("rotation needs candidate id and seed_class")
        stubs.append({"id": candidate["id"],
                      "seed_class": candidate["seed_class"],
                      "tie_key": candidate.get("tie_key", candidate["id"])})
    if tie_order:
        pos = {key: index for index, key in enumerate(tie_order)}
        result = seed_order(
            stubs, cursor=cursor,
            rank=lambda item: (pos.get(item.get("tie_key", item.get("id")),
                                       len(pos)), str(item.get("id"))))
    else:
        result = seed_order(stubs, cursor=cursor)
    by_id = {c["id"]: c for c in candidates}
    return {"ordered": [by_id[item["id"]] for item in result["ordered"]],
            "next_cursor": result["next_cursor"]}


def advance_cursor(cursor: int, steps: int = 1) -> int:
    return (int(cursor) + int(steps)) % len(SEED_CLASSES)


def _current(dep_versions: dict[str, int], obs: dict[str, Any]) -> bool:
    return dep_versions.get(obs["dep"]) == obs["dep_version"]


def eligible(option: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    blocks: list[str] = []

    def check(ok: bool, good: str, bad: str) -> None:
        (reasons if ok else blocks).append(good if ok else bad)

    check(option.get("disposition") == OPEN,
          "disposition-open", f"blocked:disposition-{option.get('disposition')}")
    epoch = state.get("epoch", 0)
    expiry = option.get("expiry_epoch")
    check(expiry is None or epoch <= expiry, "not-expired", "blocked:expired")
    dep_versions = state.get("dep_versions", {})
    prereqs_ok = True
    for pre in option.get("prerequisites", []):
        have = dep_versions.get(pre.get("dep"))
        if have is None or have < pre.get("min_version", 0):
            prereqs_ok = False
    check(prereqs_ok, "prerequisites-satisfied", "blocked:prerequisite-missing")
    cost = option.get("cost", 0)
    root = option.get("allocation_root", "")
    spent = option.get("spent", state.get("spent", {}).get(root, 0))
    cap = option.get("cap", state.get("caps", {}).get(root))
    check(cap is None or spent + cost <= cap,
          "within-cap", "blocked:cap-exhausted")
    remaining = state.get("remaining")
    check(remaining is None or remaining >= 1 + cost,
          "authority-available", "blocked:insufficient-authority")
    check(option.get("effect_identity") not in state.get("pending", []),
          "no-pending-effect", "blocked:pending-effect-replay")
    neg = _current_negative(option, state)
    check(neg is None, "no-current-negative",
          f"blocked:negative-history-current:{neg}" if neg else "")
    stale = _stale_negatives(option, state)
    if stale:
        reasons.append(f"stale-negative-invalidated:{','.join(stale)}")
    return {"eligible": not blocks, "reasons": reasons + blocks}


def _neg_key(neg: dict[str, Any]) -> str:
    return f"{neg.get('probe')}|{neg.get('scope')}|{neg.get('dep')}"


def _current_negative(option: dict[str, Any],
                      state: dict[str, Any]) -> str | None:
    dep_versions = state.get("dep_versions", {})
    for neg in state.get("negatives", []):
        if neg.get("probe") != option.get("probe_id") \
                or neg.get("scope") != option.get("scope"):
            continue
        if dep_versions.get(neg.get("dep")) == neg.get("dep_version"):
            return _neg_key(neg)
    return None


def _stale_negatives(option: dict[str, Any],
                     state: dict[str, Any]) -> list[str]:
    dep_versions = state.get("dep_versions", {})
    out = []
    for neg in state.get("negatives", []):
        if neg.get("probe") != option.get("probe_id") \
                or neg.get("scope") != option.get("scope"):
            continue
        current = dep_versions.get(neg.get("dep"))
        if current is not None and current != neg.get("dep_version"):
            out.append(_neg_key(neg))
    return sorted(out)


def _cited(continuation: dict[str, Any],
           observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = continuation.get("cited", [])
    found = []
    for ref in refs:
        for obs in observations:
            if all(obs.get(k) == ref.get(k)
                   for k in ("prop", "scope", "dep", "dep_version")):
                found.append(obs)
    return found


def _addresses(continuation: dict[str, Any]) -> bool:
    probe = continuation.get("next_probe") or {}
    residual = continuation.get("residual_question")
    return bool(residual) and bool(probe) and probe.get("question") == residual


def _declared_pair(probe: dict[str, Any]) -> dict[str, Any] | None:
    by_value = {o.get("value"): o.get("consequence")
                for o in (probe.get("outcomes") or [])}
    if by_value.get("true") is None or by_value.get("true") == by_value.get("false"):
        return None
    return by_value


def _route_q1(continuation: dict[str, Any], observations: list[dict[str, Any]],
              state: dict[str, Any]) -> tuple[bool, str]:
    dep_versions = state.get("dep_versions", {})
    if not _addresses(continuation):
        return False, "q1:probe-misses-residual-question"
    if _declared_pair(continuation.get("next_probe") or {}) is None:
        return False, "q1:no-declared-discriminating-consequence"
    residual = continuation.get("residual_question") or {}
    for obs in _cited(continuation, observations):
        if obs["value"] not in DECISIVE:
            continue
        if not _current(dep_versions, obs):
            continue
        if obs.get("scope") != continuation.get("scope"):
            continue
        if obs.get("prop") != residual.get("prop"):
            continue
        return True, (f"q1:decision-change:{obs['prop']}:{obs['scope']}:"
                      f"{obs['dep']}@{obs['dep_version']}={obs['value']}")
    return False, "q1:no-residual-matching-citation"


def _settled(probe: dict[str, Any], observations: list[dict[str, Any]],
             state: dict[str, Any]) -> bool:
    question = probe.get("question") or {}
    return any(obs["value"] in DECISIVE
               and _current(state.get("dep_versions", {}), obs)
               and all(obs.get(k) == question.get(k)
                       for k in ("prop", "scope", "dep"))
               for obs in observations)


def _route_q2(continuation: dict[str, Any], observations: list[dict[str, Any]],
              state: dict[str, Any]) -> tuple[bool, str]:
    probe = continuation.get("next_probe") or {}
    outcomes = [o for o in (probe.get("outcomes") or [])
                if o.get("value") in ("true", "false")]
    distinct = sorted({str(o.get("consequence")) for o in outcomes})
    if len(outcomes) < 2 or len(distinct) < 2:
        return False, "q2:no-declared-distinction"
    if _settled(probe, observations, state):
        return False, "q2:settled-by-current-evidence"
    dep_versions = state.get("dep_versions", {})
    anchored = any(obs.get("value") in DECISIVE
                   and _current(dep_versions, obs)
                   and obs.get("scope") == continuation.get("scope")
                   for obs in _cited(continuation, observations))
    if not anchored:
        return False, "q2:no-current-decisive-in-scope-citation"
    return True, (f"q2:discriminating-probe:{probe.get('id')}:"
                  f"{len(outcomes)}-declared-outcomes")


def _route_q3(continuation: dict[str, Any]) -> tuple[bool, str]:
    rep = continuation.get("replication")
    if not rep:
        return False, "q3:no-replication-protocol"
    total = rep.get("total", 0)
    done = rep.get("completed", 0)
    if not rep.get("declared_before_first_sample"):
        return False, "q3:protocol-not-prefrozen"
    if rep.get("stop_reached"):
        return False, "q3:stopping-condition-reached"
    if not isinstance(total, int) or total <= 0 or done < 0 or done >= total:
        return False, "q3:no-remaining-obligation"
    return True, (f"q3:replication-remainder:{rep.get('protocol')}:"
                  f"{done}-of-{total}")


def qualify_continuation(continuation: dict[str, Any],
                         observations: list[dict[str, Any]],
                         state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(continuation, dict) or not continuation.get("parent_attempt"):
        return {"qualified": False, "route": None,
                "reasons": ["unqualified:missing-continuation-link"]}
    for route, verdict in (("Q1", _route_q1(continuation, observations, state)),
                           ("Q2", _route_q2(continuation, observations, state)),
                           ("Q3", _route_q3(continuation))):
        passed, reason = verdict
        if passed:
            return {"qualified": True, "route": route, "reasons": [reason]}
    return {"qualified": False, "route": None,
            "reasons": [verdict[1] for verdict in
                        (_route_q1(continuation, observations, state),
                         _route_q2(continuation, observations, state),
                         _route_q3(continuation))]}


def _well_formed_continuation(candidate: dict[str, Any]) -> tuple[bool, str]:
    cont = candidate.get(CONTINUATION) or {}
    for field in ("parent_attempt", "residual_question", "next_probe",
                  "stop_condition"):
        if not cont.get(field):
            return False, f"malformed-continuation:missing-{field}"
    if not isinstance(candidate.get("cap"), int) or candidate["cap"] <= 0:
        return False, "malformed-continuation:no-finite-cap"
    return True, ""


def _snapshot(policy_input: dict[str, Any]) -> dict[str, Any]:
    return {"candidates": policy_input.get("candidates", []),
            "observations": policy_input.get("observations", []),
            "state": policy_input.get("state", {}),
            "cursor": policy_input.get("cursor", 0),
            "tie_order": policy_input.get("tie_order"),
            "grammar": OBS_GRAMMAR_VERSION}


def _decide(policy_version: str, qualified_only: bool,
            policy_input: dict[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot(policy_input)
    state = snapshot["state"]
    parsed = parse_observations(snapshot["observations"], state.get("epoch", 0))
    observations = parsed["observations"]
    candidates = snapshot["candidates"]
    cursor = snapshot["cursor"]
    evaluated: list[dict[str, Any]] = []
    order = rotation_order(
        [c for c in candidates if isinstance(c, dict) and "id" in c and "seed_class" in c],
        cursor=cursor,
        tie_order=snapshot.get("tie_order")) if candidates \
        else {"ordered": [], "next_cursor": cursor}
    by_id = {c["id"]: c for c in order["ordered"]}
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("id") not in by_id:
            evaluated.append({"id": (candidate or {}).get("id"),
                              "skipped": "malformed-candidate"})
            continue
        record: dict[str, Any] = {"id": candidate["id"]}
        check = eligible(candidate, state)
        record["eligible"] = check["eligible"]
        record["eligible_reasons"] = check["reasons"]
        if not check["eligible"]:
            record["skipped"] = "ineligible"
            evaluated.append(record)
            continue
        if candidate.get("kind") == CONTINUATION:
            ok, why = _well_formed_continuation(candidate)
            if not ok:
                record["skipped"] = why
                evaluated.append(record)
                continue
            verdict = qualify_continuation(
                candidate[CONTINUATION], observations, state)
            record["continuation"] = verdict
            if qualified_only and not verdict["qualified"]:
                record["skipped"] = "unqualified-continuation"
                evaluated.append(record)
                continue
        cost = candidate.get("cost", 0)
        if (state.get("remaining") is not None
                and state["remaining"] < 1 + cost):
            record["skipped"] = "unaffordable"
            evaluated.append(record)
            continue
        selection = {"option_id": candidate["id"],
                     "kind": candidate.get("kind", "initial"),
                     "probe": candidate.get("probe_id"),
                     "cost": cost,
                     "route": (record.get(CONTINUATION) or {}).get("route")
                     if candidate.get("kind") == CONTINUATION
                     else None}
        digest = payload_digest(snapshot)
        return {"policy_version": policy_version, "grammar": OBS_GRAMMAR_VERSION,
                "decision": "select", "selection": selection,
                "input_digest": digest, "cursor": order["next_cursor"],
                "reasons": [f"selected:{candidate['id']}"],
                "evaluated": evaluated + [record],
                "parse": {"accepted": len(observations),
                          "rejected": len(parsed["rejected"])}}
    digest = payload_digest(snapshot)
    return {"policy_version": policy_version, "grammar": OBS_GRAMMAR_VERSION,
            "decision": "idle", "selection": None, "input_digest": digest,
            "cursor": order["next_cursor"], "reasons": ["idle:no-selectable-candidate"],
            "evaluated": evaluated,
            "parse": {"accepted": len(observations),
                      "rejected": len(parsed["rejected"])}}


def decide_R(policy_input: dict[str, Any]) -> dict[str, Any]:
    return _decide(POLICY_R_VERSION, False, policy_input)


def decide_Q(policy_input: dict[str, Any]) -> dict[str, Any]:
    return _decide(POLICY_Q_VERSION, True, policy_input)


def match_wake(condition: dict[str, Any],
               event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(condition, dict) or not isinstance(event, dict):
        return {"matched": False, "reasons": ["malformed-wake-shape"]}
    kind = condition.get("type")
    if kind == "prerequisite-version":
        if event.get("kind") != "prerequisite-available":
            return {"matched": False, "reasons": ["kind-mismatch"]}
        if not condition.get("name") or not isinstance(
                condition.get("min_version"), int):
            return {"matched": False, "reasons": ["malformed-condition"]}
        if event.get("name") == condition["name"] \
                and isinstance(event.get("version"), int) \
                and event["version"] >= condition["min_version"]:
            return {"matched": True,
                    "reasons": [f"prerequisite-ready:{condition['name']}"]}
        return {"matched": False, "reasons": ["prerequisite-not-ready"]}
    if kind == "evidence-change":
        if event.get("kind") != "evidence-changed":
            return {"matched": False, "reasons": ["kind-mismatch"]}
        if not condition.get("dep") or not isinstance(
                condition.get("known_version"), int):
            return {"matched": False, "reasons": ["malformed-condition"]}
        if event.get("dep") == condition["dep"] \
                and isinstance(event.get("version"), int) \
                and event["version"] > condition["known_version"]:
            return {"matched": True,
                    "reasons": [f"evidence-changed:{condition['dep']}"]}
        return {"matched": False, "reasons": ["evidence-unchanged"]}
    if kind == "authorized-scan-due":
        if event.get("kind") != "scan-authorized":
            return {"matched": False, "reasons": ["kind-mismatch"]}
        if not condition.get("scan_id") or not isinstance(
                condition.get("due_epoch"), int):
            return {"matched": False, "reasons": ["malformed-condition"]}
        if event.get("scan_id") == condition["scan_id"] \
                and isinstance(event.get("epoch"), int) \
                and event["epoch"] >= condition["due_epoch"]:
            return {"matched": True,
                    "reasons": [f"scan-due:{condition['scan_id']}"]}
        return {"matched": False, "reasons": ["scan-not-due"]}
    return {"matched": False, "reasons": ["unknown-condition-type"]}
