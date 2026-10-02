"""S2 context views and durable continuation (RUN-2, RUN-5).

A context view names its decision, source versions, transformations,
governing references and unresolved limitations. A continuation document
carries composition version, position, completed refs, unresolved operation
ids, obligations and the next decision; it is stored as an immutable artifact
and installed via the store so a fresh worker resumes with no shared memory.

Hidden-evaluation boundary: retrieval filters by caller scope in SQL. A table
name is not isolation; the access-label predicate below is the enforcement
point reused by the broker and store, and candidate builders cannot remove it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from psycopg import errors as _pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import artifacts, broker, db, evidence, store
from .common import Command, CommandResult, ResultCode, SettlementError, new_id

_LATEST_VERSION = 1


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def build_context(dsn: str, cmd: Command, decision: dict, source_refs: list[dict],
                  transforms: list[dict] | None = None, governing_refs: list[str] | None = None,
                  limitations: list[str] | None = None, caller_scope: str = "public",
                  mandatory: list[str] | None = None) -> CommandResult:
    mandatory = list(mandatory or [])
    visible_claims = {row["id"] for row in evidence.scoped_claims(dsn, caller_scope)}
    visible_digests = {row["digest"] for row in artifacts.scoped_artifacts(dsn, caller_scope)}
    missing = [key for key in mandatory if key not in decision or decision[key] in (None, "", [])]
    withheld: list[str] = []
    kept: list[dict] = []
    for ref in source_refs:
        target = ref.get("claim_id") or ref.get("digest") or ""
        if ref.get("claim_id") and target not in visible_claims:
            withheld.append(target)
        elif ref.get("digest") and target not in visible_digests:
            withheld.append(target)
        else:
            kept.append(ref)
    staged = bool(missing or withheld)

    def _fn(cur, control):
        view_id = f"ctx_{cmd.request_id}"
        cur.execute("INSERT INTO context_views (id, decision, sources, transforms,"
                    " governing_refs, limitations, staged, version)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (view_id, _j(decision), _j(kept), _j(transforms or []),
                     _j(governing_refs or []),
                     _j(list(limitations or []) + (["missing: " + m for m in missing])
                         + (["withheld: " + w for w in withheld])),
                     staged, _LATEST_VERSION))
        data: dict[str, Any] = {"view_id": view_id, "version": _LATEST_VERSION, "staged": staged,
                                "sources": kept, "missing": missing, "withheld": withheld}
        if missing:
            data["narrowed_decision"] = {k: v for k, v in decision.items() if k not in missing}
        return (ResultCode.APPLIED, "staged context" if staged else "context built", data,
                [("context.built", {"view_id": view_id, "staged": staged})], [])
    return store.transact(dsn, cmd, _fn)


def save_continuation(dsn: str, cmd: Command, artifacts_root: str | Path, investigation_id: str,
                      attempt_id: str, composition_version: str, position: dict,
                      completed_refs: list, unresolved_ops: list[str], obligations: dict,
                      next_decision: dict, ownership_generation: int | None = None) -> CommandResult:
    doc = {"investigation_id": investigation_id, "composition_version": composition_version,
           "position": position, "completed_refs": completed_refs,
           "unresolved_ops": list(unresolved_ops), "obligations": obligations,
           "next_decision": next_decision}
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    roots = Path(artifacts_root)
    roots.mkdir(parents=True, exist_ok=True)
    target = roots / digest
    created = False
    if not target.is_file():
        tmp = roots / (digest + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(tmp, target)
        fd = os.open(roots, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        created = True

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM investigations WHERE id = %s", (investigation_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown investigation {investigation_id}")
        cur.execute("INSERT INTO artifact_versions (digest, size, manifest, format, version,"
                    " availability, scope, path) VALUES (%s, %s, %s, 'continuation', %s,"
                    " 'available', %s, %s) ON CONFLICT (digest) DO NOTHING",
                    (digest, len(raw), _j({"continuation": investigation_id}),
                     composition_version, investigation_id, digest))
        cur.execute("INSERT INTO continuation_docs (id, investigation_id, composition_version,"
                    " position, completed_refs, unresolved_ops, obligations, next_decision)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (id) DO UPDATE SET position = EXCLUDED.position,"
                    " completed_refs = EXCLUDED.completed_refs,"
                    " unresolved_ops = EXCLUDED.unresolved_ops, obligations = EXCLUDED.obligations,"
                    " next_decision = EXCLUDED.next_decision",
                    (digest, investigation_id, composition_version, _j(position),
                     _j(completed_refs), _j(list(unresolved_ops)), _j(obligations),
                     _j(next_decision)))
        cur.execute("SELECT id, lifecycle, ownership_generation FROM attempts WHERE id = %s",
                    (attempt_id,))
        attempt = cur.fetchone()
        if attempt is None:
            raise SettlementError(f"unknown attempt {attempt_id}")
        if attempt["lifecycle"] in ("completed", "failed", "cancelled"):
            raise SettlementError(f"attempt {attempt_id} is {attempt['lifecycle']}")
        if ownership_generation is not None and int(ownership_generation) != int(
                attempt["ownership_generation"]):
            raise SettlementError(f"attempt {attempt_id} owned by generation"
                                  f" {attempt['ownership_generation']}")
        cur.execute("UPDATE attempts SET continuation_ref = %s, updated_at = now() WHERE id = %s",
                    (digest, attempt_id))
        return (ResultCode.APPLIED, "continuation stored and installed",
                {"continuation_id": digest, "attempt_id": attempt_id},
                [("work.continued", {"attempt_id": attempt_id}),
                 ("artifact.published", {"digest": digest})], [])
    result = store.transact(dsn, cmd, _fn)
    if created and result.code != ResultCode.APPLIED:
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM artifact_versions WHERE digest = %s", (digest,))
                orphan = cur.fetchone() is None
                conn.commit()
        if orphan:
            try:
                target.unlink()
            except OSError:
                pass
    return result


def resume_package(dsn: str, investigation_id: str, caller_scope: str = "evaluator") -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM continuation_docs WHERE investigation_id = %s"
                        " ORDER BY created_at DESC LIMIT 1", (investigation_id,))
            row = cur.fetchone()
            if row is None:
                raise SettlementError(f"no continuation for {investigation_id}")
            doc = {k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
                   for k, v in dict(row).items()}
            cur.execute("SELECT id FROM attempts WHERE investigation_id = %s"
                        " AND lifecycle NOT IN ('completed', 'failed', 'cancelled')", (investigation_id,))
            live = [r["id"] for r in cur.fetchall()]
            cur.execute("SELECT id FROM attempts WHERE investigation_id = %s", (investigation_id,))
            every = [r["id"] for r in cur.fetchall()]
            cur.execute("SELECT attempt_id, content FROM attempt_observations WHERE attempt_id = ANY(%s)"
                        " ORDER BY id", (every or ["~none"],))
            observations = [{"attempt_id": r["attempt_id"],
                               "content": dict((r["content"] or {}).get("content", r["content"] or {}))}
                            for r in cur.fetchall()]
            conn.commit()
    reconciliation = store.restart_reconciliation(dsn)
    pending = [op for op in reconciliation["unfinished_operations"]
               if op["id"] in set(doc["unresolved_ops"])
               or (live and op.get("attempt_id") in live)]
    support = {row["id"]: evidence.current_support(dsn, row["id"]) for row in
               evidence.scoped_claims(dsn, caller_scope)}
    try:
        from . import team as _team

        team_state = _team.team_state(dsn, investigation_id)
    except _pg_errors.UndefinedTable:
        team_state = {"plans": [], "submissions": [], "joins": []}
    return {"continuation": doc, "live_attempts": live, "pending_operations": pending,
            "observations": observations, "support": support, "team": team_state,
            "reconciliation": {"execution_versions": reconciliation["execution_versions"]}}


POLICY_VERSION = "d02-seed-v1"
_RENDER_VERSION = "render-seed-v1"

_PACKET_KINDS = ("diagnose", "construct", "resume", "team")
_PACKET_SCOPES = ("public", "candidate", "evaluator", "operator")

_REQUIRED = {
    "diagnose": ("development_inputs", "attempted_behaviors", "outcomes",
                 "task_specs", "unresolved_observations", "output_contract"),
    "construct": ("intervention", "examples", "development_feedback",
                  "invocation_contract", "applicability", "effect_envelope",
                  "revision_budget", "candidate_lineage"),
    "resume": ("objective", "selected_versions", "completed_outcomes",
               "pending_operations", "obligations", "next_decision", "allocation"),
    "team": ("team_plan", "team_inputs", "team_output_contract"),
}
_KNOWN_SLOTS = frozenset(s for slots in _REQUIRED.values() for s in slots)

_OUTPUT_CONTRACTS = {
    "diagnose": {
        "entry": "diagnose-bottleneck",
        "response_shape": {"explanations": [{"cause": "str", "support": ["ref"],
                                             "counterevidence": ["ref"]}],
                           "intervention": {"action": "str"},
                           "probe": "str|null"},
        "rules": ["cite only delivered refs", "mark unresolved outcomes explicitly",
                  "abstain when required inputs are missing"]},
    "construct": {
        "entry": "construct-method",
        "response_shape": {"code": "<utf8 source honoring the access policy>",
                           "no_candidate": "reason|null"},
        "rules": ["honor the pinned invocation contract",
                  "stage the file and verify with --selftest before publishing",
                  "stay inside applicability and effect envelope",
                  "abstain when required inputs are missing"]},
    "resume": {
        "entry": "resume-investigation",
        "response_shape": {"next_decision": "str", "actions": ["str"],
                           "replayed_effects": "none"},
        "rules": ["never replay completed external effects",
                  "reconcile pending operations first",
                  "abstain when required inputs are missing"]},
    "team": {
        "entry": "team-child-work",
        "response_shape": {"outputs": {"path": "content"},
                           "notes": "str|null"},
        "rules": ["stay inside owned paths",
                  "bind every input to the snapshot digest",
                  "abstain when required inputs are missing"]},
}

_BUNDLE_CAP = 32


class _Need(Exception):
    def __init__(self, reason: str, proposal: str = "") -> None:
        super().__init__(reason)
        self.proposal = proposal


class _Stale(Exception):
    pass


def _check_decision(decision: Any) -> dict:
    if not isinstance(decision, dict):
        raise SettlementError("decision must be a dict")
    kind = decision.get("decision_kind")
    if kind not in _PACKET_KINDS:
        raise SettlementError(f"unknown decision kind {kind!r}")
    access = decision.get("access", "public")
    if access not in _PACKET_SCOPES:
        raise SettlementError(f"unknown access scope {access!r}")
    budget = decision.get("budget", {})
    if (not isinstance(budget, dict) or not isinstance(budget.get("input_chars"), int)
            or not isinstance(budget.get("output_reserve"), int)
            or budget["input_chars"] <= 0 or budget["output_reserve"] < 0):
        raise SettlementError("decision budget needs positive input_chars and output_reserve")
    extra = decision.get("required_inputs", [])
    if not isinstance(extra, list) or any(not isinstance(name, str) for name in extra):
        raise SettlementError("required_inputs must be a list of slot names")
    unknown = [name for name in extra if name not in _KNOWN_SLOTS]
    if unknown:
        raise SettlementError(f"unknown required inputs {unknown!r}")
    versions = decision.get("current_versions", {})
    if not isinstance(versions, dict):
        raise SettlementError("current_versions must be a dict")
    ordered = list(_REQUIRED[kind]) + [name for name in extra if name not in _REQUIRED[kind]]
    contract = decision.get("candidate_contract", {})
    if not isinstance(contract, dict) or any(
            k in contract and not isinstance(contract[k], dict)
            for k in ("invocation", "applicability", "effect", "resource")):
        raise SettlementError("candidate_contract must be a dict of dicts")
    return {"kind": kind, "purpose": str(decision.get("purpose", "")),
            "required": ordered, "allowed_actions": list(decision.get("allowed_actions", [])),
            "access": access, "budget": budget, "versions": versions,
            "contract": contract,
            "investigation_id": str(decision.get("investigation_id", "")),
            "episode_id": str(decision.get("episode_id", ""))}


def _row(cur, sql: str, args: tuple) -> dict | None:
    cur.execute(sql, args)
    found = cur.fetchone()
    return dict(found) if found is not None else None


def _rows(cur, sql: str, args: tuple) -> list[dict]:
    cur.execute(sql, args)
    return [dict(r) for r in cur.fetchall()]


def _fetch_state(dsn: str, spec: dict) -> dict:
    iid, eid = spec["investigation_id"], spec["episode_id"]
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            inv = _row(cur, "SELECT * FROM investigations WHERE id = %s", (iid,))
            ep = _row(cur, "SELECT * FROM development_episodes WHERE id = %s", (eid,))
            attempts = _rows(cur, "SELECT id, allocation_id, lifecycle FROM attempts"
                                  " WHERE investigation_id = %s ORDER BY id", (iid,))
            aids = [a["id"] for a in attempts] or ["~none"]
            seen = _rows(cur, "SELECT attempt_id, content FROM attempt_observations"
                              " WHERE attempt_id = ANY(%s) ORDER BY id", (aids,))
            observations = _rows(cur, "SELECT receipt_id, attempt_id, source_identity,"
                                      " conditions, content, authenticated FROM observations"
                                      " WHERE attempt_id = ANY(%s) ORDER BY receipt_id", (aids,))
            receipts = _rows(cur, "SELECT receipt_identity, operation_id, outcome, content"
                                  " FROM receipts WHERE operation_id IN"
                                  " (SELECT id FROM operations WHERE attempt_id = ANY(%s))"
                                  " ORDER BY receipt_identity", (aids,))
            cont = _row(cur, "SELECT * FROM continuation_docs WHERE investigation_id = %s"
                             " ORDER BY created_at DESC LIMIT 1", (iid,))
            pins = _rows(cur, "SELECT attempt_id, version_id FROM attempt_capability_pins"
                              " WHERE attempt_id = ANY(%s) ORDER BY attempt_id, version_id",
                         (aids,))
            alloc_ids = sorted({a["allocation_id"] for a in attempts if a["allocation_id"]})
            allocs = (_rows(cur, "SELECT id, authorized, consumed, reserved FROM allocations"
                                 " WHERE id = ANY(%s) ORDER BY id", (alloc_ids,)) if alloc_ids else [])
            conn.commit()
    recon = store.restart_reconciliation(dsn)
    live = {a["id"] for a in attempts}
    pending = [dict(op) for op in recon["unfinished_operations"]
               if op.get("attempt_id") in live]
    control = store.get_control(dsn)
    return {"inv": inv, "ep": ep, "attempts": attempts, "seen": seen,
            "observations": observations, "receipts": receipts, "cont": cont,
            "pins": pins, "allocs": allocs, "pending": pending,
            "epoch": int(control.get("evidence_epoch", 0)),
            "authority_version": control.get("authority_version")}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _s_development_inputs(state: dict, spec: dict) -> dict:
    ep = state["ep"]
    refs = list((ep or {}).get("trigger_refs") or [])
    if not ep or not refs:
        raise _Need("no trigger experience refs",
                    "observe the episode with task-id trigger refs first")
    return {"trigger_refs": _jsonable(refs), "bottleneck": ep.get("bottleneck", ""),
            "predicted_effect": ep.get("predicted_effect", "")}


def _s_attempted_behaviors(state: dict, spec: dict) -> dict:
    if not state["seen"] and not state["observations"]:
        raise _Need("no attempted behaviors recorded",
                    "run the development batch before diagnosis")
    return {"attempts": [{"attempt_id": r["attempt_id"], "content": _jsonable(r["content"])}
                         for r in state["seen"]],
            "observations": [{"receipt_id": r["receipt_id"], "content": _jsonable(r["content"])}
                             for r in state["observations"]]}


def _s_outcomes(state: dict, spec: dict) -> dict:
    if not state["receipts"]:
        raise _Need("no observed outcomes or costs",
                    "record operation receipts before diagnosis")
    costs = {a["id"]: {"authorized": a["authorized"], "consumed": a["consumed"],
                       "reserved": a["reserved"]} for a in state["allocs"]}
    return {"receipts": [{"operation_id": r["operation_id"], "outcome": r["outcome"],
                          "content": _jsonable(r["content"])} for r in state["receipts"]],
            "costs": costs}


def _s_task_specs(state: dict, spec: dict) -> dict:
    if state["inv"] is None:
        raise _Need("unknown investigation", "admit the investigation first")
    return {"objective": state["inv"].get("objective", ""),
            "scope": _jsonable(state["inv"].get("scope") or {})}


def _s_unresolved_observations(state: dict, spec: dict) -> dict:
    open_rows = [{"receipt_id": r["receipt_id"], "content": _jsonable(r["content"])}
                for r in state["observations"]]
    if not open_rows:
        return {"open": [], "state": "none-open"}
    return {"open": open_rows}


def _s_output_contract(state: dict, spec: dict) -> dict:
    return {"contract": _OUTPUT_CONTRACTS[spec["kind"]], "policy_version": POLICY_VERSION}


def _s_intervention(state: dict, spec: dict) -> dict:
    ep = state["ep"] or {}
    if not ep.get("intervention"):
        raise _Need("no selected intervention", "propose an intervention first")
    return {"intervention": _jsonable(ep["intervention"]),
            "predicted_effect": ep.get("predicted_effect", "")}


def _visible_claims(dsn: str, access: str) -> list[dict]:
    return evidence.scoped_claims(dsn, access)


def _s_examples(state: dict, spec: dict) -> dict:
    claims = state["visible_claims"]
    if not claims:
        raise _Need("no permitted examples visible",
                    "propose claims at an admitted scope or narrow the decision")
    return {"claims": [{"claim_id": c["id"], "scope": _jsonable(c.get("scope") or {}),
                        "access_label": c.get("access_label", "")} for c in claims]}


def _s_development_feedback(state: dict, spec: dict) -> dict:
    ep = state["ep"] or {}
    if not ep.get("explanations"):
        raise _Need("no development feedback recorded",
                    "diagnose the episode before construction")
    return {"explanations": _jsonable(ep["explanations"]),
            "probe_ops": _jsonable(ep.get("probe_ops") or []),
            "checks": _jsonable(ep.get("checks") or [])}


def _pinned_capability(dsn: str, spec: dict) -> tuple[dict | None, str]:
    versions = spec["versions"]
    vid = str(versions.get("candidate_version") or versions.get("capability_version") or "")
    if not vid:
        return None, ""
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cap = _row(cur, "SELECT * FROM capability_versions WHERE id = %s", (vid,))
            quar = _row(cur, "SELECT * FROM quarantine_registry WHERE version_id = %s", (vid,))
            conn.commit()
    if cap is None:
        raise _Stale(f"pinned version {vid} is unknown: refresh the selection")
    if quar is not None:
        raise _Stale(f"pinned version {vid} is quarantined: refresh the selection")
    return dict(cap), vid


def _artifact_bytes_ok(dsn: str, digest: str, artifacts_root: Any) -> tuple[str, bool | None]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT availability FROM artifact_versions WHERE digest = %s",
                       (digest,))
            conn.commit()
    if row is None:
        return "unknown", None
    if row["availability"] != "available":
        return str(row["availability"]), False
    if artifacts_root is None:
        return "available-unverified", None
    return "available", artifacts.bytes_match(artifacts_root, digest)


def _check_pinned_bytes(dsn: str, digest: str, artifacts_root: Any) -> list[str]:
    if not digest:
        return ["no-artifact-bytes"]
    status, ok = _artifact_bytes_ok(dsn, digest, artifacts_root)
    if status == "unknown":
        raise _Need(f"pinned artifact {digest[:12]} has no record",
                    "publish the artifact bytes first")
    if ok is False or status not in ("available", "available-unverified"):
        raise _Stale(f"pinned artifact {digest[:12]} is {status}: refresh the selection")
    if ok is None:
        return [f"bytes-unverified:{status}"]
    return [f"bytes-ok:{digest[:12]}"]


def _declared_contract(spec: dict, slot: str) -> dict | None:
    declared = (spec.get("contract") or {}).get(slot)
    return declared if isinstance(declared, dict) else None


def _s_invocation_contract(state: dict, spec: dict) -> dict:
    cap, vid = _pinned_capability(state["dsn"], spec)
    if cap is None:
        declared = _declared_contract(spec, "invocation")
        if declared is None:
            raise _Need("no candidate version pinned", "pin a capability version first")
        return {"version": "", "source": "entry-declared-pre-candidate",
                "invocation": _jsonable(declared)}
    quals = _check_pinned_bytes(state["dsn"], cap.get("artifact_digest", ""),
                                state["artifacts_root"])
    state["byte_quals"].extend(quals)
    state["source_versions"].append({"version_id": vid,
                                    "artifact_digest": cap.get("artifact_digest", "")})
    return {"version": vid, "invocation": _jsonable(cap.get("invocation") or {}),
            "effect": _jsonable(cap.get("effect") or {}),
            "resource": _jsonable(cap.get("resource") or {}),
            "artifact_digest": cap.get("artifact_digest", "")}


def _s_applicability(state: dict, spec: dict) -> dict:
    cap, _ = _pinned_capability(state["dsn"], spec)
    if cap is None:
        declared = _declared_contract(spec, "applicability")
        if declared is None:
            raise _Need("no candidate version pinned", "pin a capability version first")
        return {"version": "", "source": "entry-declared-pre-candidate",
                "applicability": _jsonable(declared)}
    return {"version": cap["id"], "applicability": _jsonable(cap.get("applicability") or {})}


def _s_effect_envelope(state: dict, spec: dict) -> dict:
    cap, _ = _pinned_capability(state["dsn"], spec)
    if cap is None:
        contract = spec.get("contract") or {}
        effect, resource = contract.get("effect"), contract.get("resource")
        if not isinstance(effect, dict) or not isinstance(resource, dict):
            raise _Need("no candidate version pinned", "pin a capability version first")
        return {"version": "", "source": "entry-declared-pre-candidate",
                "effect": _jsonable(effect), "resource": _jsonable(resource)}
    return {"version": cap["id"], "effect": _jsonable(cap.get("effect") or {}),
            "resource": _jsonable(cap.get("resource") or {})}


def _s_revision_budget(state: dict, spec: dict) -> dict:
    ep = state["ep"]
    if ep is None:
        raise _Need("unknown development episode", "observe the episode first")
    return {"ceilings": {"max_explanations": ep.get("max_explanations", 0),
                         "max_probes": ep.get("max_probes", 0),
                         "max_candidates": ep.get("max_candidates", 0)},
            "used": {"probes_used": ep.get("probes_used", 0)},
            "allocation": {a["id"]: {"authorized": a["authorized"],
                                     "consumed": a["consumed"]} for a in state["allocs"]},
            "episode_state": ep.get("state", "")}


def _s_candidate_lineage(state: dict, spec: dict) -> dict:
    ep = state["ep"] or {}
    cands = list(ep.get("candidates") or [])
    if not cands:
        return {"candidates": [], "state": "no-prior-candidates"}
    return {"candidates": _jsonable(cands)}


def _s_objective(state: dict, spec: dict) -> dict:
    if state["inv"] is None:
        raise _Need("unknown investigation", "admit the investigation first")
    return {"objective": state["inv"].get("objective", ""),
            "scope": _jsonable(state["inv"].get("scope") or {}),
            "disposition": state["inv"].get("disposition", "")}


def _s_selected_versions(state: dict, spec: dict) -> dict:
    ep = state["ep"] or {}
    if state["pins"]:
        return {"pins": [{"attempt_id": p["attempt_id"], "version_id": p["version_id"]}
                         for p in state["pins"]]}
    bound = dict(ep.get("bindings") or {})
    selected = dict(ep.get("selection") or {})
    if bound or selected:
        return {"bindings": _jsonable(bound), "selection": _jsonable(selected)}
    raise _Need("no selected versions pinned",
                "pin a capability version to a live attempt first")


def _s_completed_outcomes(state: dict, spec: dict) -> dict:
    done = [{"operation_id": r["operation_id"], "outcome": r["outcome"],
             "content": _jsonable(r["content"])}
            for r in state["receipts"] if r["outcome"] in ("success", "failure")]
    if not done:
        return {"completed": [], "state": "none-completed"}
    return {"completed": done}


def _s_pending_operations(state: dict, spec: dict) -> dict:
    return {"pending": [{"id": op.get("id"), "dispatch_state": op.get("dispatch_state"),
                         "reconcile_state": op.get("reconcile_state")}
                        for op in state["pending"]]}


def _s_obligations(state: dict, spec: dict) -> dict:
    if state["inv"] is None:
        raise _Need("unknown investigation", "admit the investigation first")
    merged = dict(state["inv"].get("obligations") or {})
    if state["cont"]:
        merged.update(dict(state["cont"].get("obligations") or {}))
    return {"obligations": _jsonable(merged)}


def _s_next_decision(state: dict, spec: dict) -> dict:
    nxt = dict((state["cont"] or {}).get("next_decision") or {})
    if not nxt:
        raise _Need("no continuation next decision", "save a continuation first")
    return {"next_decision": _jsonable(nxt),
            "composition_version": (state["cont"] or {}).get("composition_version", "")}


def _s_allocation(state: dict, spec: dict) -> dict:
    if not state["allocs"]:
        raise _Need("no allocation bound", "bind a finite allocation first")
    return {"allocations": [{k: a[k] for k in ("id", "authorized", "consumed", "reserved")}
                            for a in state["allocs"]]}


def _team_summary(dsn: str, spec: dict) -> dict:
    from . import team as _team

    plan_id = str((spec.get("versions") or {}).get("plan_id") or "")
    if not plan_id:
        raise _Need("no team plan pinned", "propose a team plan first")
    try:
        return _team.plan_summary(dsn, plan_id)
    except LookupError:
        raise _Need(f"unknown team plan {plan_id}", "propose a team plan first")


def _s_team_plan(state: dict, spec: dict) -> dict:
    summary = _team_summary(state["dsn"], spec)
    return {"plan_id": summary["plan_id"], "shape": summary["shape"],
            "revision": summary["revision"],
            "children": [{"node_id": c["node_id"], "obligation": c["obligation"],
                          "owned_paths": c["owned_paths"]} for c in summary["children"]]}


def _s_team_inputs(state: dict, spec: dict) -> dict:
    summary = _team_summary(state["dsn"], spec)
    if not summary["snapshot_digest"] or not summary["children"]:
        raise _Need("team plan has no bound inputs", "propose a team plan first")
    return {"snapshot_digest": summary["snapshot_digest"],
            "inputs": {c["node_id"]: c["input_digests"] for c in summary["children"]}}


def _s_team_output_contract(state: dict, spec: dict) -> dict:
    summary = _team_summary(state["dsn"], spec)
    if not summary["interface_contract"]:
        raise _Need("team plan has no interface contract", "propose a team plan first")
    return {"interface_contract": _jsonable(summary["interface_contract"]),
            "contracts": {c["node_id"]: _jsonable(c["output_contract"])
                          for c in summary["children"]}}


_RESOLVERS = {
    "development_inputs": _s_development_inputs,
    "attempted_behaviors": _s_attempted_behaviors,
    "outcomes": _s_outcomes,
    "task_specs": _s_task_specs,
    "unresolved_observations": _s_unresolved_observations,
    "output_contract": _s_output_contract,
    "intervention": _s_intervention,
    "examples": _s_examples,
    "development_feedback": _s_development_feedback,
    "invocation_contract": _s_invocation_contract,
    "applicability": _s_applicability,
    "effect_envelope": _s_effect_envelope,
    "revision_budget": _s_revision_budget,
    "candidate_lineage": _s_candidate_lineage,
    "objective": _s_objective,
    "selected_versions": _s_selected_versions,
    "completed_outcomes": _s_completed_outcomes,
    "pending_operations": _s_pending_operations,
    "obligations": _s_obligations,
    "next_decision": _s_next_decision,
    "allocation": _s_allocation,
    "team_plan": _s_team_plan,
    "team_inputs": _s_team_inputs,
    "team_output_contract": _s_team_output_contract,
}


def _referenced_claims(state: dict) -> list[str]:
    ep = state["ep"] or {}
    found = []
    for ref in list(ep.get("trigger_refs") or []):
        cid = ref.get("claim_id") if isinstance(ref, dict) else None
        if cid and cid not in found:
            found.append(cid)
    return found


def _claim_candidates(dsn: str, state: dict, spec: dict) -> list[dict]:
    wanted = _referenced_claims(state)
    if spec["kind"] == "construct":
        wanted = wanted + [c["id"] for c in state["visible_claims"] if c["id"] not in wanted]
    if not wanted:
        return []
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM claims WHERE id = ANY(%s)", (wanted,))
            rows = {r["id"]: dict(r) for r in cur.fetchall()}
            conn.commit()
    visible = {c["id"] for c in state["visible_claims"]}
    return [rows[cid] for cid in wanted if cid in rows and cid in visible]


def _derivation_routes(dsn: str, claim_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id FROM derivations WHERE claim_id = %s AND status = 'valid'"
                        " ORDER BY id", (claim_id,))
            dids = [r["id"] for r in cur.fetchall()]
            premises = (_rows(cur, "SELECT derivation_id, group_id, premise_ref, premise_kind"
                                    " FROM derivation_premises WHERE derivation_id = ANY(%s)"
                                    " ORDER BY derivation_id, group_id", (dids,)) if dids else [])
            conn.commit()
    grouped: dict[str, dict[int, list]] = {}
    for p in premises:
        grouped.setdefault(p["derivation_id"], {}).setdefault(int(p["group_id"]), []).append(p)
    return [{"derivation": did, "premises": groups[gid]}
            for did, groups in sorted(grouped.items()) for gid in sorted(groups)]


def _retracted(dsn: str, ref: str) -> bool:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM retractions WHERE target_ref = %s", (ref,))
            hit = cur.fetchone() is not None
            conn.commit()
    return hit


def _rests_on_artifacts(dsn: str, derivation_ids: list) -> bool:
    if not derivation_ids:
        return False
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM derivation_premises WHERE derivation_id = ANY(%s)"
                        " AND premise_kind = 'artifact' LIMIT 1", (list(derivation_ids),))
            hit = cur.fetchone() is not None
            conn.commit()
    return hit


def _premise_usable(dsn: str, ref: str, kind: str, artifacts_root: Any) -> tuple[bool, str]:
    if _retracted(dsn, ref):
        return False, "retracted"
    if kind == "observation":
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                row = _row(cur, "SELECT authenticated, content FROM observations"
                                " WHERE receipt_id = %s", (ref,))
                conn.commit()
        if row is None or not row["authenticated"]:
            return False, "unauthenticated-or-unknown"
        return True, ""
    if kind == "artifact":
        status, ok = _artifact_bytes_ok(dsn, ref, artifacts_root)
        if ok is True:
            return True, ""
        if ok is None:
            return False, f"bytes-unverifiable:{status}"
        return False, status
    support = evidence.current_support(dsn, ref, artifacts_root)
    if not support["supported"]:
        return False, "unsupported-claim"
    if artifacts_root is None and _rests_on_artifacts(dsn, support["derivations"]):
        return False, "bytes-unverifiable:artifact-backed"
    return True, ""


def _oppositions(dsn: str, claim_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _rows(cur, "SELECT id, kind, status, body FROM oppositions"
                              " WHERE claim_id = %s ORDER BY id", (claim_id,))
            conn.commit()
    return rows


def _premise_content(dsn: str, ref: str, kind: str) -> dict:
    if kind == "observation":
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                row = _row(cur, "SELECT content FROM observations WHERE receipt_id = %s",
                           (ref,))
                conn.commit()
        return {"ref": ref, "kind": kind,
                "content": _jsonable((row or {}).get("content") or {})}
    if kind == "artifact":
        status, _ = _artifact_bytes_ok(dsn, ref, None)
        return {"ref": ref, "kind": kind, "availability": status}
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT proposition FROM claims WHERE id = %s", (ref,))
            conn.commit()
    return {"ref": ref, "kind": kind,
            "content": _jsonable((row or {}).get("proposition") or {})}


def _build_bundle(dsn: str, claim: dict, spec: dict, state: dict) -> dict:
    cid = claim["id"]
    routes = _derivation_routes(dsn, cid)
    usable = []
    blocked = []
    for route in routes:
        checks = [(p, _premise_usable(dsn, p["premise_ref"], p["premise_kind"],
                                      state["artifacts_root"])) for p in route["premises"]]
        if all(ok for _, (ok, _) in checks):
            usable.append({"derivation": route["derivation"],
                           "premises": [{"ref": p["premise_ref"], "kind": p["premise_kind"]}
                                        for p in route["premises"]]})
        else:
            blocked.append((route["derivation"],
                            sorted({why for _, (ok, why) in checks if not ok})))
    opposition = _oppositions(dsn, cid)
    defeated = any(o["kind"] == "defeat" and o["status"] == "active" for o in opposition)
    usable.sort(key=lambda r: (len(r["premises"]), r["derivation"]))
    selected = usable[0] if usable and not defeated else None
    quals = [f"access:{claim.get('access_label', '')}(authoritative)",
             f"scope:{json.dumps(claim.get('scope') or {}, sort_keys=True)}"]
    if selected:
        quals.append(f"route:{selected['derivation']}({len(selected['premises'])} premises)")
    if len(usable) > 1:
        quals.append(f"alternatives:{len(usable) - 1}")
    for opp in opposition:
        quals.append(f"counterevidence:{opp['id']}:{opp['kind']}:{opp['status']}")
    if defeated:
        quals.append("disposition:defeated")
    for did, reasons in blocked:
        quals.append(f"blocked:{did}:{','.join(reasons)}")
    bundle = {"claim_id": cid, "proposition": _jsonable(claim.get("proposition") or {}),
              "scope": _jsonable(claim.get("scope") or {}),
              "assumptions": _jsonable(claim.get("assumptions") or []),
              "access_label": claim.get("access_label", ""),
              "disposition": "defeated" if defeated else ("supported" if selected
                                                          else "unsupported"),
              "selected_route": selected,
              "alternative_routes": [r for r in usable if r != selected],
              "opposition": [{"id": o["id"], "kind": o["kind"], "status": o["status"],
                              "body": _jsonable(o.get("body") or {})} for o in opposition],
              "premise_content": [_premise_content(dsn, p["ref"], p["kind"])
                                  for p in (selected["premises"] if selected else [])],
              "qualifications": quals,
              "next_obligation": f"revalidate beyond epoch {state['epoch']}"}
    return bundle


def _settle_bundles(dsn: str, state: dict, spec: dict) -> tuple[list[dict], list[dict]]:
    rows = _claim_candidates(dsn, state, spec)
    omitted = max(0, len(rows) - _BUNDLE_CAP)
    bundles = [_build_bundle(dsn, claim, spec, state) for claim in rows[:_BUNDLE_CAP]]
    omissions = ([{"section": "evidence", "dropped_items": omitted,
                   "reason": "bundle-cap"}] if omitted else [])
    referenced = set(_referenced_claims(state))
    for bundle in bundles:
        if bundle["claim_id"] not in referenced:
            continue
        if bundle["disposition"] == "defeated":
            raise _Stale(f"claim {bundle['claim_id']} is defeated: refresh the selection")
        if bundle["disposition"] == "unsupported":
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM derivations WHERE claim_id = %s LIMIT 1",
                                (bundle["claim_id"],))
                    warranted = cur.fetchone() is not None
                    cur.execute("SELECT 1 FROM retractions WHERE target_ref = %s LIMIT 1",
                                (bundle["claim_id"],))
                    hit_self = cur.fetchone() is not None
                    conn.commit()
            if not warranted:
                state["gaps"].append({"slot": "evidence", "claim_id": bundle["claim_id"],
                                      "reason": "no admitted warrant",
                                      "proposal": "admit a warrant or narrow the decision"})
            elif any("bytes-unverifiable" in q
                     for q in bundle["qualifications"]):
                state["gaps"].append({"slot": "evidence", "claim_id": bundle["claim_id"],
                                      "reason": "support bytes unverifiable without artifacts root",
                                      "proposal": "rebuild with an artifacts root"})
            elif hit_self:
                raise _Stale(f"claim {bundle['claim_id']} was retracted:"
                             " refresh the selection")
            else:
                raise _Stale(f"support for claim {bundle['claim_id']} collapsed:"
                             " refresh the selection")
    return bundles, omissions


def _render_text(packet_id: str, spec: dict, contents: dict, order: list,
                 bundles: list, gaps: list) -> str:
    lines = [f"packet {packet_id}", f"kind {spec['kind']}",
             f"policy {POLICY_VERSION}", f"purpose {spec['purpose']}",
             "== mandatory =="]
    for name in order:
        lines.append(f"[{name}]")
        lines.append(json.dumps(contents.get(name, {}), sort_keys=True,
                                separators=(",", ":")))
    lines.append("== evidence ==")
    for bundle in bundles:
        lines.append(json.dumps(bundle, sort_keys=True, separators=(",", ":")))
    lines.append("== gaps ==")
    lines.append(json.dumps(gaps, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def _wire(packet_id: str, rendered: str) -> str:
    return json.dumps({"packet_id": packet_id, "policy_version": POLICY_VERSION,
                       "rendered": rendered}, sort_keys=True, separators=(",", ":"))


def _footprint_artifacts(dsn: str, bundles: list, source_versions: list,
                         artifacts_root: Any) -> list[dict]:
    digests = [s.get("artifact_digest", "") for s in source_versions
               if s.get("artifact_digest")]
    for bundle in bundles:
        for premise in bundle.get("premise_content", []):
            if premise.get("kind") == "artifact" and premise.get("ref"):
                digests.append(premise["ref"])
    seen = []
    for digest in dict.fromkeys(d for d in digests if d):
        status, ok = _artifact_bytes_ok(dsn, digest, artifacts_root)
        seen.append({"digest": digest, "availability": status,
                     "bytes_ok": ok})
    return seen


def build_packet(dsn: str, cmd: Command, *, decision: dict,
                 artifacts_root: str | Path | None = None) -> CommandResult:
    spec = _check_decision(decision)
    state = _fetch_state(dsn, spec)
    state.update({"dsn": dsn, "artifacts_root": artifacts_root, "gaps": [],
                  "byte_quals": [], "source_versions": [],
                  "visible_claims": _visible_claims(dsn, spec["access"])})
    contents: dict[str, Any] = {}
    stales: list[dict] = []
    for name in spec["required"]:
        try:
            contents[name] = _RESOLVERS[name](state, spec)
        except _Need as exc:
            state["gaps"].append({"slot": name, "reason": str(exc),
                                  "proposal": exc.proposal})
        except _Stale as exc:
            stales.append({"slot": name, "reason": str(exc)})
    try:
        bundles, cap_omissions = _settle_bundles(dsn, state, spec)
    except _Stale as exc:
        bundles, cap_omissions = [], []
        stales.append({"slot": "evidence", "reason": str(exc)})
    gaps = list(state["gaps"]) + [{"slot": s["slot"], "reason": s["reason"],
                                   "stale": True} for s in stales]
    outcome = "stale" if stales else ("needs_information" if gaps else "ready")
    packet_id = f"pkt_{cmd.request_id}"
    order = spec["required"]
    rendered = _render_text(packet_id, spec, contents, order, bundles, gaps)
    total = len(_wire(packet_id, rendered)) + spec["budget"]["output_reserve"]
    bound = spec["budget"]["input_chars"]
    omissions = list(cap_omissions)
    if total > bound:
        if outcome == "ready":
            outcome = "needs_information"
        gaps = gaps + [{"slot": "budget",
                        "reason": f"full packet with opposition needs {total} chars"
                                  f" beyond {bound}: nothing stripped",
                        "proposal": "stage a narrower decision sequence"}]
        rendered = _render_text(packet_id, spec, contents, order, bundles, gaps)
        total = len(_wire(packet_id, rendered)) + spec["budget"]["output_reserve"]
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    footprint = {"policy_version": POLICY_VERSION, "render_version": _RENDER_VERSION,
                 "evidence_epoch": state["epoch"],
                 "authority_version": state.get("authority_version"),
                 "allowed_actions": spec["allowed_actions"],
                 "source_versions": {"requested": _jsonable(spec["versions"]),
                                     "pinned": state["source_versions"]},
                 "transforms": [{"name": "render-seed", "version": _RENDER_VERSION}],
                 "artifacts": _footprint_artifacts(dsn, bundles, state["source_versions"],
                                                   artifacts_root),
                 "derivation_routes": {b["claim_id"]: (b["selected_route"] or {}).get(
                     "derivation") for b in bundles},
                 "oppositions": [o["id"] for b in bundles for o in b["opposition"]],
                 "operation_states": [{"id": op.get("id"),
                                       "dispatch_state": op.get("dispatch_state")}
                                      for op in state["pending"]],
                 "byte_qualifications": state["byte_quals"]}
    snapshot = {"evidence_epoch": state["epoch"],
                "authority_version": state.get("authority_version"),
                "investigation_id": spec["investigation_id"],
                "episode_id": spec["episode_id"],
                "current_versions": _jsonable(spec["versions"])}
    token_estimate = {"chars": total, "labeled": "chars-not-tokens"}
    data = {"packet_id": packet_id, "outcome": outcome, "rendered": rendered,
            "rendered_digest": digest, "mandatory_content": contents,
            "evidence_bundles": bundles, "gaps": gaps, "footprint": footprint,
            "omissions": omissions, "token_estimate": token_estimate}

    def _fn(cur, control):
        cur.execute("INSERT INTO context_packets (id, decision_kind, purpose, decision,"
                    " policy_version, source_snapshot, mandatory_content, evidence_bundles,"
                    " gaps, footprint, omissions, rendered, rendered_digest, outcome,"
                    " token_estimate, evidence_epoch) VALUES (%s, %s, %s, %s, %s, %s, %s,"
                    " %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (packet_id, spec["kind"], spec["purpose"], _j(decision),
                     POLICY_VERSION, _j(snapshot), _j(contents), _j(bundles), _j(gaps),
                     _j(footprint), _j(omissions), rendered, digest, outcome,
                     _j(token_estimate), state["epoch"]))
        detail = {"ready": "packet ready", "needs_information": "packet needs information",
                  "stale": "packet stale"}[outcome]
        return (ResultCode.APPLIED, detail, data,
                [("context.packet_built", {"packet_id": packet_id, "outcome": outcome,
                                           "decision_kind": spec["kind"]})], [])
    return store.transact(dsn, cmd, _fn)


def load_packet(dsn: str, packet_id: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM context_packets WHERE id = %s", (packet_id,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown packet {packet_id}")
    return {k: (_jsonable(v) if isinstance(v, (dict, list)) else v)
            for k, v in dict(row).items()}


def bind_packet_invocation(dsn: str, cmd: Command, packet_id: str, operation_id: str,
                           artifacts_root: str | Path | None = None) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT outcome, rendered, rendered_digest, mandatory_content,"
                    " decision_kind FROM context_packets WHERE id = %s", (packet_id,))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown packet {packet_id}: binding refused")
        if row["outcome"] != "ready":
            raise SettlementError(f"packet {packet_id} is {row['outcome']}: binding refused")
        if hashlib.sha256((row["rendered"] or "").encode()).hexdigest() != row[
                "rendered_digest"]:
            raise SettlementError(f"packet {packet_id} bytes do not match digest")
        cur.execute("SELECT payload FROM operations WHERE id = %s", (operation_id,))
        op = cur.fetchone()
        if op is None:
            raise SettlementError(f"unknown operation {operation_id}: binding refused")
        body = op["payload"] or {}
        if row["decision_kind"] == "team":
            admitted = {broker.MODEL_INFERENCE, broker.SANDBOX_EXEC}
            if not isinstance(body, dict) or body.get("effect") not in admitted:
                raise SettlementError(f"operation {operation_id} is not an admitted"
                                      " team effect: binding refused")
        elif not isinstance(body, dict) or body.get("effect") != broker.MODEL_INFERENCE:
            raise SettlementError(f"operation {operation_id} is not model inference:"
                                  " binding refused")
        wire_in = json.dumps(body, sort_keys=True, separators=(",", ":"))
        input_digest = hashlib.sha256(wire_in.encode()).hexdigest()
        if artifacts_root is not None:
            pinned = dict((dict(row["mandatory_content"] or {}).get(
                "invocation_contract") or {}))
            pinned_digest = pinned.get("artifact_digest", "")
            if pinned_digest and not artifacts.bytes_match(artifacts_root, pinned_digest):
                raise SettlementError(f"packet {packet_id} pinned bytes"
                                      f" {pinned_digest[:12]} unavailable")
        cur.execute("SELECT operation_id FROM packet_invocations WHERE packet_id = %s",
                    (packet_id,))
        bound_ops = {found["operation_id"] for found in cur.fetchall()}
        if bound_ops - {operation_id} and packet_id not in wire_in:
            raise SettlementError(f"packet {packet_id} already bound to another"
                                  " operation: binding refused")
        cur.execute("INSERT INTO packet_invocations (packet_id, operation_id,"
                    " rendered_digest, input_digest) VALUES (%s, %s, %s, %s)"
                    " ON CONFLICT DO NOTHING",
                    (packet_id, operation_id, row["rendered_digest"], input_digest))
        if cur.rowcount == 0:
            return (ResultCode.ALREADY_APPLIED, "packet already bound",
                    {"packet_id": packet_id, "operation_id": operation_id,
                     "rendered_digest": row["rendered_digest"],
                     "input_digest": input_digest}, [], [])
        return (ResultCode.APPLIED, f"packet {packet_id} bound to {operation_id}",
                {"packet_id": packet_id, "operation_id": operation_id,
                 "rendered_digest": row["rendered_digest"],
                 "input_digest": input_digest},
                [("context.packet_bound", {"packet_id": packet_id,
                                           "operation_id": operation_id})], [])
    return store.transact(dsn, cmd, _fn)


def _route_usable_now(dsn: str, route: dict, artifacts_root: Any) -> bool:
    return all(_premise_usable(dsn, p["ref"], p["kind"], artifacts_root)[0]
               for p in route["premises"])


def revalidate_packet(dsn: str, packet_id: str,
                      artifacts_root: str | Path | None = None) -> dict:
    row = load_packet(dsn, packet_id)
    reasons: list[str] = []
    notes: list[str] = []
    if hashlib.sha256((row.get("rendered") or "").encode()).hexdigest() != row.get(
            "rendered_digest"):
        reasons.append("rendered bytes no longer match the bound digest")
    decision = dict(row.get("decision") or {})
    versions = dict(decision.get("current_versions") or {})
    vid = str(versions.get("candidate_version") or versions.get("capability_version")
              or "")
    if vid:
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                quar = _row(cur, "SELECT * FROM quarantine_registry WHERE version_id = %s",
                            (vid,))
                cap = _row(cur, "SELECT artifact_digest FROM capability_versions"
                                " WHERE id = %s", (vid,))
                conn.commit()
        if cap is None:
            reasons.append(f"pinned version {vid} no longer exists")
        elif quar is not None:
            reasons.append(f"pinned version {vid} is quarantined")
        elif cap.get("artifact_digest"):
            status, ok = _artifact_bytes_ok(dsn, cap["artifact_digest"], artifacts_root)
            if ok is False or status not in ("available", "available-unverified"):
                reasons.append(f"pinned artifact {cap['artifact_digest'][:12]} is {status}")
            elif ok is None:
                notes.append(f"pinned bytes unverified:{status}")
    for bundle in list(row.get("evidence_bundles") or []):
        cid = bundle["claim_id"]
        if any(o["kind"] == "defeat" and o["status"] == "active"
               for o in _oppositions(dsn, cid)):
            reasons.append(f"claim {cid} is defeated")
            continue
        selected = bundle.get("selected_route") or {}
        if selected and _route_usable_now(dsn, selected, artifacts_root):
            continue
        live = [r for r in _derivation_routes(dsn, cid)
                if _route_usable_now(dsn, {"premises": [
                    {"ref": p["premise_ref"], "kind": p["premise_kind"]}
                    for p in r["premises"]]}, artifacts_root)]
        if live and not selected:
            notes.append(f"claim {cid} usable via route {live[0]['derivation']}")
        elif live:
            notes.append(f"claim {cid} selected route failed over to"
                         f" {live[0]['derivation']}")
        else:
            reasons.append(f"claim {cid} has no usable support route")
    footprint = dict(row.get("footprint") or {})
    snapshot = dict(row.get("source_snapshot") or {})
    iid = snapshot.get("investigation_id", "")
    current: set[str] = set()
    if iid:
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id FROM attempts WHERE investigation_id = %s", (iid,))
                aids = [r["id"] for r in cur.fetchall()] or ["~none"]
                cur.execute("SELECT id FROM operations WHERE attempt_id = ANY(%s)"
                            " AND (dispatch_state IN ('dispatching', 'sent', 'unresolved')"
                            " OR cancel_state = 'requested'"
                            " OR reconcile_state = 'conflict')", (aids,))
                current = {r["id"] for r in cur.fetchall()}
                conn.commit()
    pinned_ops = {op.get("id") for op in footprint.get("operation_states", [])}
    if current != pinned_ops:
        reasons.append("working state changed: pending operations differ")
    control = store.get_control(dsn)
    return {"packet_id": packet_id, "valid": not reasons, "reasons": reasons,
            "notes": notes, "outcome": row.get("outcome"),
            "current_epoch": int(control.get("evidence_epoch", 0))}


def _next_action(row: dict) -> str:
    if row.get("outcome") == "ready":
        return "invoke through a bound operation"
    missing = sorted({g.get("slot", "") for g in row.get("gaps", []) if not g.get("stale")})
    stale = sorted({g.get("reason", "") for g in row.get("gaps", []) if g.get("stale")})
    if stale:
        return "refresh invalidated sources then rebuild: " + "; ".join(stale)
    return "supply missing material: " + ", ".join(missing)


def recent_packets(dsn: str, limit: int = 20) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM context_packets ORDER BY created_at"
                            " DESC LIMIT %s", (max(int(limit), 1),))
            except _pg_errors.UndefinedTable:
                conn.rollback()
                return []
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    summaries = []
    for row in rows:
        footprint = dict(row.get("footprint") or {})
        quals = list(footprint.get("byte_qualifications") or [])
        for bundle in list(row.get("evidence_bundles") or []):
            quals.extend(bundle.get("qualifications", []))
        sources = dict(footprint.get("source_versions") or {})
        summaries.append({"packet_id": row["id"], "decision_kind": row["decision_kind"],
                          "purpose": row.get("purpose", ""), "outcome": row.get("outcome"),
                          "policy_version": row.get("policy_version", ""),
                          "source_versions": sources,
                          "transform_versions": footprint.get("transforms", []),
                          "qualifications": quals,
                          "rendered_digest": row.get("rendered_digest", ""),
                          "gaps": _jsonable(row.get("gaps") or []),
                          "omissions": _jsonable(row.get("omissions") or []),
                          "next_action": _next_action(
                              {"outcome": row.get("outcome"),
                               "gaps": _jsonable(row.get("gaps") or [])})})
    return summaries
