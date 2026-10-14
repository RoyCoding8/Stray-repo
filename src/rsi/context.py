"""Bounded, immutable context packets for persistent investigations."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from psycopg.rows import dict_row

from settlement import db, store
from settlement.common import Command, ResultCode, SettlementError, payload_digest

from . import experience, memory

SCHEMA = "rsi-context/1"
MAX_PACKET_BYTES = 65_536
MAX_LIMIT = memory._MAX_QUERY_LIMIT
POLICIES = {
    "structured/1": "structured",
    "raw-history/1": "raw-history",
    "adaptive/1": "structured",
}
DEFAULT_BUDGET = {
    "packet_bytes": 48_000,
    "scan_bytes": 131_072,
    "excerpt_bytes": 8_192,
    "actions": 8,
}
_CONTINUATION_FIELDS = {
    "objective", "objective_revision", "state_revision", "open_questions",
    "artifact_refs", "previous_observation",
}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_STOP_WORDS = {"and", "are", "for", "from", "how", "that", "the", "this", "with"}


def _json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SettlementError(f"context data must be finite JSON: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _canonical_json(value: Any) -> Any:
    return json.loads(_json(value))


def _validate_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise SettlementError("context request must be an object")
    required = {
        "investigation_id", "objective_revision", "state_revision", "decision_id",
        "attempt_id", "operation_id", "continuation", "purpose", "scope", "policy",
        "limit", "required_observation_ids", "required_claim_ids",
    }
    if required - request.keys():
        raise SettlementError("context request is missing required fields")
    out = _canonical_json(request)
    for field in ("investigation_id", "decision_id", "attempt_id", "operation_id"):
        value = out.get(field)
        if not isinstance(value, str) or not value or len(value) > 200:
            raise SettlementError(f"{field} must be a bounded non-empty string")
    for field in ("objective_revision", "state_revision", "limit"):
        if type(out.get(field)) is not int or out[field] < (1 if field == "limit" else 0):
            raise SettlementError(f"{field} must be a valid integer")
    if out["limit"] > MAX_LIMIT:
        raise SettlementError(f"limit must be at most {MAX_LIMIT}")
    if out.get("policy") not in POLICIES:
        raise SettlementError("policy must be structured/1, raw-history/1, or adaptive/1")
    if not isinstance(out.get("purpose"), str) or not out["purpose"].strip():
        raise SettlementError("purpose must be a non-empty string")
    if not isinstance(out.get("scope"), dict):
        raise SettlementError("scope must be an object")
    continuation = out.get("continuation")
    if not isinstance(continuation, dict) or set(continuation) != _CONTINUATION_FIELDS:
        raise SettlementError("continuation must contain the six original P01 fields")
    ids = out.get("required_observation_ids")
    if (not isinstance(ids, list) or any(type(item) is not int or item < 1 for item in ids)
            or len(ids) > 256 or len(set(ids)) != len(ids)):
        raise SettlementError("required_observation_ids must be distinct positive integers")
    claim_ids = out.get("required_claim_ids")
    if (not isinstance(claim_ids, list) or any(not isinstance(item, str) or not item for item in claim_ids)
            or len(claim_ids) > 256 or len(set(claim_ids)) != len(claim_ids)):
        raise SettlementError("required_claim_ids must be distinct non-empty strings")
    supplied_budget = out.get("budget", {})
    if not isinstance(supplied_budget, dict) or set(supplied_budget) - set(DEFAULT_BUDGET):
        raise SettlementError("budget must contain packet_bytes, scan_bytes, excerpt_bytes, and actions")
    budget = {**DEFAULT_BUDGET, **supplied_budget}
    if any(type(value) is not int or value <= 0 for value in budget.values()):
        raise SettlementError("context budget values must be positive integers")
    if budget["packet_bytes"] > MAX_PACKET_BYTES:
        raise SettlementError(f"packet_bytes must be at most {MAX_PACKET_BYTES}")
    out["budget"] = budget
    return out


def _request_ids(request: dict) -> tuple[str, str]:
    prefix = f"rsi-context:{request['investigation_id']}:{request['state_revision']}"
    return prefix + ":pin", prefix + ":packet"


def _pin(dsn: str, request: dict) -> dict:
    pin_id, _ = _request_ids(request)
    payload = {"request": request}

    def apply(cur, _control):
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            raise SettlementError("P02 memory revision clock is unavailable")
        pin = {"request": request, "memory_revision": int(row["revision"])}
        return ResultCode.APPLIED, "context request pinned", pin, [], []

    result = store.transact(dsn, Command(request_id=pin_id, payload=payload), apply)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return result.data


def _query(dsn: str, request: dict, revision: int, artifacts_root: str) -> dict:
    return memory.query(
        dsn, purpose=request["purpose"], investigation_id=request["investigation_id"],
        scope=request["scope"], artifacts_root=artifacts_root, visibility="learner",
        revision=revision, view=POLICIES[request["policy"]],
        claim_ids=request["required_claim_ids"],
        observation_ids=request["required_observation_ids"], limit=request["limit"],
    )


def _required_needs(request: dict, view: dict) -> list[dict]:
    found_observations = {item["observation_id"] for item in view["observations"]}
    found_claims = {item["claim_id"] for item in view["claims"]}
    needs = []
    for observation_id in request["required_observation_ids"]:
        if observation_id not in found_observations:
            needs.append({"kind": "observation", "id": observation_id,
                          "reason": "required observation is unavailable at the pinned revision"})
    if request["policy"] != "raw-history/1":
        for claim_id in request["required_claim_ids"]:
            if claim_id not in found_claims:
                needs.append({"kind": "claim", "id": claim_id,
                              "reason": "required claim is unavailable at the pinned revision"})
    elif request["required_claim_ids"]:
        for claim_id in request["required_claim_ids"]:
            unavailable = any(item.get("claim_id") == claim_id
                              for item in view["missing_information"]
                              if isinstance(item, dict))
            if unavailable:
                needs.append({"kind": "claim", "id": claim_id,
                              "reason": "required claim has no available historical evidence"})
            elif not view["observations"]:
                needs.append({"kind": "claim", "id": claim_id,
                              "reason": "required claim has no available historical evidence"})
    return needs


def _words(purpose: str) -> list[str]:
    return list(dict.fromkeys(word.casefold() for word in _WORD.findall(purpose)
                              if word.casefold() not in _STOP_WORDS))


def _inspect(text: str, terms: list[str], scan_left: int, excerpt_left: int) -> tuple[dict, int, int]:
    raw = text.encode("utf-8")
    scanned = min(len(raw), scan_left)
    visible = raw[:scanned].decode("utf-8", errors="ignore")
    folded = visible.casefold()
    matches = [(term, folded.find(term)) for term in terms]
    matches = [(term, pos) for term, pos in matches if pos >= 0]
    if not matches or excerpt_left <= 0:
        return {"matched": bool(matches), "terms": [term for term, _ in matches],
                "excerpt": ""}, scanned, 0
    term, position = min(matches, key=lambda item: item[1])
    start = max(0, position - min(80, max(0, excerpt_left // 4)))
    end = min(len(visible), start + excerpt_left)
    excerpt = visible[start:end]
    while len(excerpt.encode("utf-8")) > excerpt_left:
        excerpt = excerpt[:-1]
    context_words = [word.casefold() for word in _WORD.findall(visible[position:position + 192])
                     if word.casefold() not in _STOP_WORDS and word.casefold() != term]
    feedback = next(iter(dict.fromkeys(context_words)), None)
    return {"matched": True, "terms": [item[0] for item in matches],
            "excerpt": excerpt, "match": term, "feedback": feedback}, scanned, len(excerpt.encode("utf-8"))


def _excerpt(text: str, budget: int) -> str:
    raw = text.encode("utf-8")[:budget]
    return raw.decode("utf-8", errors="ignore")


def _packet_size(packet: dict) -> int:
    continuation = {**packet["request"]["continuation"], "context_packet": packet}
    return len(_json(continuation))


def _set_size_count(packet: dict) -> int:
    packet["counts"]["packet_bytes"] = 0
    size = _packet_size(packet)
    for _ in range(4):
        packet["counts"]["packet_bytes"] = size
        next_size = _packet_size(packet)
        if next_size == size:
            return size
        size = next_size
    packet["counts"]["packet_bytes"] = size
    return size


def _root_ids(claim: dict) -> set[int]:
    return set(claim.get("support", [])) | set(claim.get("opposition", []))


def _build_packet(dsn: str, request: dict, pin: dict, artifacts_root: str) -> dict:
    revision = pin["memory_revision"]
    queried = _query(dsn, request, revision, artifacts_root)
    source_claims = list(queried.get("claims", []))
    source_observations = list(queried.get("observations", []))
    observations_by_id = {item["observation_id"]: item for item in source_observations}
    required_claim_ids = set(request["required_claim_ids"])
    selected_claims = [item for item in source_claims if item["claim_id"] in required_claim_ids]
    optional_claims = [item for item in source_claims if item["claim_id"] not in required_claim_ids]
    selected_observation_ids = set(request["required_observation_ids"])
    selected_observation_ids.update(i for claim in selected_claims for i in _root_ids(claim))

    if request["policy"] == "raw-history/1":
        selected_claims = []
        selected_observation_ids.update(observations_by_id)
    else:
        for claim in optional_claims:
            selected_claims.append(claim)
        selected_observation_ids.update(observations_by_id)

    observations = [observations_by_id[i] for i in sorted(selected_observation_ids)
                    if i in observations_by_id]
    needs = _required_needs(request, {**queried, "claims": selected_claims})
    required_roots = set(request["required_observation_ids"])
    required_roots.update(i for claim in selected_claims if claim["claim_id"] in required_claim_ids
                          for i in _root_ids(claim))
    if request["policy"] == "raw-history/1" and request["required_claim_ids"]:
        structured = memory.query(
            dsn, purpose=request["purpose"], investigation_id=request["investigation_id"],
            scope=request["scope"], artifacts_root=artifacts_root, visibility="learner",
            revision=revision, view="structured", claim_ids=request["required_claim_ids"],
            observation_ids=[], limit=max(1, len(request["required_claim_ids"])),
        )
        by_claim = {claim["claim_id"]: claim for claim in structured.get("claims", [])}
        for claim_id in request["required_claim_ids"]:
            claim = by_claim.get(claim_id)
            if claim is None:
                needs.append({"kind": "claim", "id": claim_id,
                              "reason": "required claim is unavailable at the pinned revision"})
            else:
                required_roots.update(_root_ids(claim))
        if required_roots - set(observations_by_id):
            needs.append({"kind": "claim",
                          "reason": "required historical evidence is unavailable"})
    omissions = list(queried.get("missing_information", []))
    counts = {"claims": len(selected_claims), "observations": len(observations),
              "scanned_bytes": 0, "excerpt_bytes": 0, "actions": 0, "packet_bytes": 0}
    memory_view = {
        "revision": revision,
        "purpose": request["purpose"],
        "scope": request["scope"],
        "view": POLICIES[request["policy"]],
        "claims": selected_claims,
        "observations": observations,
        "missing_information": omissions,
    }
    excerpts: list[dict] = []
    scan_left = request["budget"]["scan_bytes"]
    excerpt_left = request["budget"]["excerpt_bytes"]
    action_limit = request["budget"]["actions"]
    terms = _words(request["purpose"])
    if request["policy"] == "adaptive/1":
        # Each inspection operates only on a P02-resolved learner-visible string.
        inspection_terms = terms
        for item in observations:
            if counts["actions"] >= action_limit or scan_left <= 0 or excerpt_left <= 0:
                omissions.append({"reason": "adaptive inspection reached its finite budget"})
                break
            text = item.get("content", {}).get("task_instruction", "")
            if not isinstance(text, str):
                continue
            result, scanned, used = _inspect(text, inspection_terms, scan_left, excerpt_left)
            counts["actions"] += 1
            counts["scanned_bytes"] += scanned
            counts["excerpt_bytes"] += used
            scan_left -= scanned
            excerpt_left -= used
            # Stable action identity is scoped to this pinned request and ordinal.
            action_payload = {"request_digest": _digest(request), "revision": revision,
                              "ordinal": counts["actions"], "observation_id": item["observation_id"],
                              "result": result}
            action_id = f"rsi-context-inspect:{_digest(action_payload)}"

            def save_action(cur, _control, data=result):
                return ResultCode.APPLIED, "context inspection cached", data, [], []

            store.transact(dsn, Command(request_id=action_id, payload=action_payload), save_action)
            if result["matched"] and result["excerpt"]:
                excerpts.append({"observation_id": item["observation_id"],
                                 "text": result["excerpt"], "matched_terms": result["terms"]})
            if result.get("feedback"):
                inspection_terms = [result["feedback"]]
    else:
        for item in observations:
            if excerpt_left <= 0:
                break
            text = item.get("content", {}).get("task_instruction", "")
            if isinstance(text, str):
                excerpt = _excerpt(text, excerpt_left)
                size = len(excerpt.encode("utf-8"))
                if excerpt:
                    excerpts.append({"observation_id": item["observation_id"], "text": excerpt})
                    counts["excerpt_bytes"] += size
                    excerpt_left -= size

    # Optional bundles and observations are removed whole until the complete P01
    # continuation fits. Required roots and their opposition always travel together.
    packet = {
        "schema": SCHEMA,
        "status": "needs_information" if needs else "ready",
        "request": request,
        "memory_view": memory_view,
        "excerpts": excerpts,
        "omissions": omissions,
        "needs": needs,
        "counts": counts,
        "digest": "0" * 64,
    }
    size = _set_size_count(packet)
    while size > request["budget"]["packet_bytes"]:
        optional = next((claim for claim in reversed(selected_claims)
                         if claim["claim_id"] not in required_claim_ids), None)
        if optional is not None:
            selected_claims.remove(optional)
            referenced = set().union(*(_root_ids(claim) for claim in selected_claims)) if selected_claims else set()
            referenced.update(required_roots)
            memory_view["claims"] = selected_claims
            memory_view["observations"] = [item for item in observations
                                            if item["observation_id"] in referenced]
            observations = memory_view["observations"]
            excerpts = [item for item in excerpts
                        if item["observation_id"] in {o["observation_id"] for o in observations}]
            packet["excerpts"] = excerpts
            packet["counts"]["claims"] = len(selected_claims)
            packet["counts"]["observations"] = len(observations)
            omissions.append({"claim_id": optional["claim_id"],
                              "reason": "optional claim bundle exceeded the packet budget"})
        else:
            # Trim only optional, unclaimed observations to recover packet overhead.
            optional_ids = [item["observation_id"] for item in observations
                            if item["observation_id"] not in required_roots
                            and item["observation_id"] not in set().union(
                                *(_root_ids(claim) for claim in selected_claims) if selected_claims else set())]
            if excerpts:
                removed = excerpts.pop()
                packet["excerpts"] = excerpts
                packet["counts"]["excerpt_bytes"] -= len(removed["text"].encode("utf-8"))
            elif optional_ids:
                drop_id = optional_ids[-1]
                observations = [item for item in observations if item["observation_id"] != drop_id]
                memory_view["observations"] = observations
                packet["counts"]["observations"] = len(observations)
                omissions.append({"observation_id": drop_id,
                                  "reason": "optional observation exceeded packet budget"})
            else:
                if not needs:
                    needs.append({"kind": "budget", "reason": "required context exceeds packet budget"})
                packet["status"] = "needs_information"
                # The caller can inspect the need, but cannot dispatch an
                # incomplete root bundle as though it were admitted context.
                selected_claims = []
                observations = []
                excerpts = []
                memory_view["claims"] = []
                memory_view["observations"] = []
                packet["excerpts"] = []
                packet["counts"]["claims"] = 0
                packet["counts"]["observations"] = 0
                packet["counts"]["excerpt_bytes"] = 0
                size = _set_size_count(packet)
                break
        size = _set_size_count(packet)
    packet["memory_view"]["missing_information"] = omissions
    packet["omissions"] = omissions
    packet["needs"] = needs
    packet["counts"]["claims"] = len(packet["memory_view"]["claims"])
    packet["counts"]["observations"] = len(packet["memory_view"]["observations"])
    packet["status"] = "needs_information" if needs else "ready"
    size = _set_size_count(packet)
    packet["digest"] = _digest({key: value for key, value in packet.items() if key != "digest"})
    return packet


def build(dsn: str, request: dict, *, artifacts_root) -> dict:
    """Pin and construct one immutable packet for an investigation state revision."""
    clean = _validate_request(request)
    pin = _pin(dsn, clean)
    if pin.get("request") != clean or type(pin.get("memory_revision")) is not int:
        raise SettlementError("pinned context request is malformed")
    _, packet_id = _request_ids(clean)
    payload = {"request_digest": _digest(clean), "memory_revision": pin["memory_revision"]}

    # A completed packet is immutable across retries. Read it before resolving
    # sources so later source loss cannot replace cached bytes.
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT payload_digest, result_data FROM command_journal WHERE request_id = %s",
                    (packet_id,))
        cached = cur.fetchone()
        conn.commit()
    if cached is not None:
        if cached["payload_digest"] != payload_digest(payload):
            raise SettlementError("context packet identity was reused with a different pinned request")
        data = cached["result_data"]
        return json.loads(data) if isinstance(data, str) else data

    packet = _build_packet(dsn, clean, pin, str(artifacts_root))

    def finalize(cur, _control):
        return ResultCode.APPLIED, "context packet finalized", packet, [], []

    result = store.transact(dsn, Command(request_id=packet_id, payload=payload), finalize)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return result.data


def _same_observations(dsn: str, snapshot: dict, artifacts_root) -> bool:
    observations = snapshot.get("observations")
    if not isinstance(observations, list):
        return False
    ids = [item.get("observation_id") for item in observations if isinstance(item, dict)]
    if len(ids) != len(observations) or any(type(item) is not int for item in ids):
        return False
    resolved = experience.resolve(dsn, ids, artifacts_root=artifacts_root,
                                  revision=snapshot.get("revision"), visibility="learner")
    if resolved.get("missing_information"):
        return False
    return resolved.get("observations") == observations


def _same_claims(dsn: str, packet: dict, artifacts_root) -> bool:
    view = packet["memory_view"]
    claims = view.get("claims")
    if not isinstance(claims, list):
        return False
    if not claims:
        return True
    req = packet["request"]
    def load(revision):
        result = memory.query(
            dsn, purpose=req["purpose"], investigation_id=req["investigation_id"],
            scope=req["scope"], artifacts_root=artifacts_root, visibility="learner",
            revision=revision, view="structured",
            claim_ids=[claim["claim_id"] for claim in claims],
            observation_ids=[], limit=max(1, len(claims)),
        )
        return {claim["claim_id"]: claim for claim in result.get("claims", [])}

    pinned = load(view["revision"])
    current = load(None)
    return all(pinned.get(claim["claim_id"]) == claim
               and current.get(claim["claim_id"]) == claim for claim in claims)


def _legacy_validate(dsn: str, packet: dict, artifacts_root) -> dict:
    snapshot = packet.get("memory_view")
    if not isinstance(snapshot, dict):
        return {"status": "stale", "reason": "legacy memory snapshot is malformed"}
    if not _same_observations(dsn, snapshot, artifacts_root):
        return {"status": "stale", "reason": "legacy memory evidence changed or is unavailable"}
    claims = snapshot.get("claims", [])
    for item in claims:
        history = memory.history(dsn, item.get("claim_id", ""), artifacts_root=artifacts_root)
        match = next((row for row in history if row.get("version") == item.get("version")), None)
        if match is None or any(match.get(key) != item.get(key) for key in (
                "claim_id", "version", "revision", "kind", "text", "scope", "support",
                "opposition", "derived_from", "supersedes")):
            return {"status": "stale", "reason": "legacy memory claim version changed or is unavailable"}
    return {"status": "ready", "reason": "legacy memory snapshot remains available"}


def validate(dsn: str, packet: dict, *, artifacts_root) -> dict:
    """Validate the exact pinned packet and its selected P02 source bytes."""
    if not isinstance(packet, dict):
        return {"status": "stale", "reason": "context packet is malformed"}
    if packet.get("schema") == "p02-legacy":
        return _legacy_validate(dsn, packet, artifacts_root)
    if packet.get("schema") != SCHEMA or not isinstance(packet.get("request"), dict):
        return {"status": "stale", "reason": "context packet schema is unsupported"}
    content = {key: value for key, value in packet.items() if key != "digest"}
    if packet.get("digest") != _digest(content):
        return {"status": "stale", "reason": "context packet digest does not match"}
    view = packet.get("memory_view")
    if not isinstance(view, dict) or type(view.get("revision")) is not int:
        return {"status": "stale", "reason": "context memory view is malformed"}
    try:
        request = _validate_request(packet["request"])
        pin_id, packet_id = _request_ids(request)
    except SettlementError as exc:
        return {"status": "stale", "reason": str(exc)}
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT payload_digest, result_data FROM command_journal WHERE request_id = %s",
                    (pin_id,))
        pin_row = cur.fetchone()
        cur.execute("SELECT payload_digest, result_data FROM command_journal WHERE request_id = %s",
                    (packet_id,))
        packet_row = cur.fetchone()
        conn.commit()
    if pin_row is None or packet_row is None:
        return {"status": "stale", "reason": "context request or packet is not pinned"}
    pin_data = pin_row["result_data"]
    packet_data = packet_row["result_data"]
    if isinstance(pin_data, str):
        pin_data = json.loads(pin_data)
    if isinstance(packet_data, str):
        packet_data = json.loads(packet_data)
    if (pin_data != {"request": request,
                     "memory_revision": view["revision"]}
            or packet_data != packet):
        return {"status": "stale", "reason": "context packet differs from its pinned journal content"}
    if not _same_observations(dsn, view, artifacts_root) or not _same_claims(dsn, packet, artifacts_root):
        return {"status": "stale", "reason": "selected memory evidence is changed or unavailable"}
    return {"status": packet.get("status", "stale"), "reason": "pinned context dependencies are valid"}
