"""S2 grouped-derivation evidence (IF-3): observations, claims, warrants,
opposition/retraction, admissibility with epoch-guarded support cache.

A claim is supported while any valid derivation discharges the same
obligation through one fully live premise group. Retracting a premise kills
only the groups that contain it. Stale cached admission never bypasses a
committed invalidation: every consequential use validates ``evidence_epoch``
and recomputes the affected closure.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import artifacts, db, store
from .common import Command, CommandResult, MissingEvidence, ResultCode, SettlementError

_RELATIONS = ("required-support", "opposition", "background", "attribution", "equivalence")
_SCOPES = {"public": ("public",), "candidate": ("public", "candidate"),
           "evaluator": ("public", "candidate", "hidden", "evaluator"),
           "operator": ("public", "candidate", "hidden", "evaluator")}


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def _bump_inside(cur) -> int:
    cur.execute("UPDATE control SET evidence_epoch = evidence_epoch + 1 WHERE id = 1"
                " RETURNING evidence_epoch")
    return int(cur.fetchone()["evidence_epoch"])


def register_observation(dsn: str, cmd: Command, attempt_id: str, content: dict,
                         source_identity: str = "", conditions: dict | None = None) -> CommandResult:
    authenticated = bool(source_identity)

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM attempts WHERE id = %s", (attempt_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown attempt {attempt_id}")
        receipt = f"obs_{cmd.request_id}"
        cur.execute("INSERT INTO observations (receipt_id, attempt_id, source_identity,"
                    " conditions, content, authenticated) VALUES (%s, %s, %s, %s, %s, %s)",
                    (receipt, attempt_id, source_identity, _j(conditions or {}),
                     _j(content), authenticated))
        cur.execute("INSERT INTO attempt_observations (attempt_id, content) VALUES (%s, %s)",
                    (attempt_id, _j({"receipt_id": receipt, "content": content})))
        epoch = _bump_inside(cur)
        detail = "authenticated observation receipt" if authenticated else "unauthenticated note"
        return (ResultCode.APPLIED, detail,
                {"receipt_id": receipt, "authenticated": authenticated, "evidence_epoch": epoch},
                [("evidence.observed", {"receipt_id": receipt, "authenticated": authenticated})], [])
    return store.transact(dsn, cmd, _fn)


def propose_claim(dsn: str, cmd: Command, claim_id: str, proposition: dict,
                  scope: dict | None = None, assumptions: list | None = None,
                  access_label: str = "public") -> CommandResult:
    if access_label not in _SCOPES["evaluator"]:
        raise SettlementError(f"unknown access label {access_label!r}")

    def _fn(cur, control):
        cur.execute("INSERT INTO claims (id, proposition, scope, assumptions, access_label)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    (claim_id, _j(proposition), _j(scope or {}), _j(assumptions or []),
                     access_label))
        epoch = _bump_inside(cur)
        return (ResultCode.APPLIED, f"claim {claim_id} proposed",
                {"claim_id": claim_id, "evidence_epoch": epoch},
                [("evidence.claimed", {"claim_id": claim_id})], [])
    return store.transact(dsn, cmd, _fn)


def admit_warrant(dsn: str, cmd: Command, derivation_id: str, claim_id: str, procedure: str,
                  proc_version: str, premise_groups: list[list[tuple[str, str]]],
                  scope: dict | None = None, assumptions: list | None = None,
                  result: dict | None = None) -> CommandResult:
    if not procedure or not proc_version:
        raise SettlementError("warrant needs an exact procedure and version")
    if not premise_groups or any(not group for group in premise_groups):
        raise SettlementError("warrant needs at least one non-empty premise group")
    for group in premise_groups:
        for ref, kind in group:
            if kind not in ("claim", "observation", "artifact") or not ref:
                raise SettlementError(f"bad premise {(ref, kind)!r}")

    def _fn(cur, control):
        cur.execute("SELECT id FROM claims WHERE id = %s", (claim_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown claim {claim_id}")
        cur.execute("INSERT INTO derivations (id, claim_id, procedure, proc_version, scope,"
                    " assumptions, result) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (derivation_id, claim_id, procedure, proc_version, _j(scope or {}),
                     _j(assumptions or []), _j(result or {})))
        for group_id, group in enumerate(premise_groups):
            for ref, kind in group:
                cur.execute("INSERT INTO derivation_premises (derivation_id, group_id,"
                            " premise_ref, premise_kind) VALUES (%s, %s, %s, %s)",
                            (derivation_id, group_id, ref, kind))
                cur.execute("INSERT INTO evidence_relations (src_ref, dst_ref, kind)"
                            " VALUES (%s, %s, 'required-support')"
                            " ON CONFLICT (src_ref, dst_ref, kind) DO NOTHING",
                            (ref, derivation_id))
        epoch = _bump_inside(cur)
        return (ResultCode.APPLIED, f"warrant {derivation_id} admitted",
                {"derivation_id": derivation_id, "claim_id": claim_id, "evidence_epoch": epoch},
                [("evidence.warranted", {"derivation_id": derivation_id})], [])
    return store.transact(dsn, cmd, _fn)


def register_opposition(dsn: str, cmd: Command, opposition_id: str, claim_id: str,
                        kind: str, body: dict | None = None) -> CommandResult:
    if kind not in ("opposition", "defeat"):
        raise SettlementError(f"unknown opposition kind {kind!r}")

    def _fn(cur, control):
        cur.execute("SELECT id FROM claims WHERE id = %s", (claim_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown claim {claim_id}")
        cur.execute("INSERT INTO oppositions (id, claim_id, kind, body) VALUES (%s, %s, %s, %s)",
                    (opposition_id, claim_id, kind, _j(body or {})))
        cur.execute("INSERT INTO evidence_relations (src_ref, dst_ref, kind)"
                    " VALUES (%s, %s, 'opposition')"
                    " ON CONFLICT (src_ref, dst_ref, kind) DO NOTHING",
                    (opposition_id, claim_id))
        epoch = _bump_inside(cur) if kind == "defeat" else int(control["evidence_epoch"])
        return (ResultCode.APPLIED, f"{kind} {opposition_id} registered",
                {"opposition_id": opposition_id, "claim_id": claim_id, "evidence_epoch": epoch},
                [("evidence.opposed", {"claim_id": claim_id, "kind": kind})], [])
    return store.transact(dsn, cmd, _fn)


def retract(dsn: str, cmd: Command, target_ref: str, reason: str = "") -> CommandResult:
    def _fn(cur, control):
        cur.execute("INSERT INTO retractions (target_ref, reason) VALUES (%s, %s)"
                    " ON CONFLICT (target_ref) DO UPDATE SET reason = EXCLUDED.reason",
                    (target_ref, reason))
        cur.execute("UPDATE derivations SET status = 'invalid' WHERE id = %s", (target_ref,))
        invalidated = cur.rowcount
        epoch = _bump_inside(cur)
        return (ResultCode.APPLIED, f"retracted {target_ref}",
                {"target_ref": target_ref, "derivations_invalidated": invalidated,
                 "evidence_epoch": epoch},
                [("evidence.retracted", {"target_ref": target_ref})], [])
    return store.transact(dsn, cmd, _fn)


def _live_premise(cur, ref: str, kind: str, stack: frozenset, artifacts_root: str | None) -> bool:
    cur.execute("SELECT 1 FROM retractions WHERE target_ref = %s", (ref,))
    if cur.fetchone() is not None:
        return False
    if kind == "observation":
        cur.execute("SELECT authenticated FROM observations WHERE receipt_id = %s", (ref,))
        row = cur.fetchone()
        return row is not None and bool(row["authenticated"])
    if kind == "artifact":
        cur.execute("SELECT availability FROM artifact_versions WHERE digest = %s", (ref,))
        row = cur.fetchone()
        if row is None or row["availability"] != "available":
            return False
        if artifacts_root is not None:
            return artifacts.bytes_match(artifacts_root, ref)
        return True
    return _supported(cur, ref, stack, artifacts_root)[0]


def _covers(claim_scope: dict, derivation_scope: dict) -> bool:
    return all(derivation_scope.get(key) == value for key, value in claim_scope.items())


def _supported(cur, claim_id: str, stack: frozenset, artifacts_root: str | None) -> tuple[bool, list]:
    if claim_id in stack:
        return False, []
    cur.execute("SELECT scope FROM claims WHERE id = %s", (claim_id,))
    claim = cur.fetchone()
    if claim is None:
        return False, []
    cur.execute("SELECT 1 FROM oppositions WHERE claim_id = %s AND kind = 'defeat'"
                " AND status = 'active'", (claim_id,))
    if cur.fetchone() is not None:
        return False, []
    cur.execute("SELECT id, scope FROM derivations WHERE claim_id = %s AND status = 'valid'",
                (claim_id,))
    live = []
    for row in cur.fetchall():
        if not _covers(dict(claim["scope"] or {}), dict(row["scope"] or {})):
            continue
        cur.execute("SELECT group_id, premise_ref, premise_kind FROM derivation_premises"
                    " WHERE derivation_id = %s ORDER BY group_id", (row["id"],))
        groups: dict[int, list] = {}
        for premise in cur.fetchall():
            groups.setdefault(int(premise["group_id"]), []).append(premise)
        for group in groups.values():
            if all(_live_premise(cur, p["premise_ref"], p["premise_kind"],
                                 stack | {claim_id}, artifacts_root) for p in group):
                live.append(row["id"])
                break
    return (bool(live), live)


def current_support(dsn: str, claim_id: str, artifacts_root: str | Path | None = None) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            supported, live = _supported(cur, claim_id, frozenset(), str(artifacts_root) if artifacts_root else None)
            cur.execute("SELECT evidence_epoch FROM control WHERE id = 1")
            epoch = int(cur.fetchone()["evidence_epoch"])
            cur.execute("SELECT version FROM support_cache WHERE claim_id = %s", (claim_id,))
            cached = cur.fetchone()
            version = int(cached["version"]) + 1 if cached else 1
            detail = {"derivations": live}
            cur.execute("INSERT INTO support_cache (claim_id, supported, version, epoch, detail)"
                        " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (claim_id) DO UPDATE SET"
                        " supported = EXCLUDED.supported, version = EXCLUDED.version,"
                        " epoch = EXCLUDED.epoch, detail = EXCLUDED.detail, updated_at = now()",
                        (claim_id, supported, version, epoch, _j(detail)))
            conn.commit()
    return {"claim_id": claim_id, "supported": supported, "version": version,
            "epoch": epoch, "derivations": live}


def check_use(dsn: str, claim_id: str, evidence_epoch: int,
              artifacts_root: str | Path | None = None) -> dict:
    current = int(store.get_control(dsn)["evidence_epoch"])
    if int(evidence_epoch) < current:
        raise MissingEvidence(f"stale admissibility: saw epoch {evidence_epoch}, now {current}")
    snapshot = current_support(dsn, claim_id, artifacts_root)
    if not snapshot["supported"]:
        raise MissingEvidence(f"claim {claim_id} has no live derivation at epoch {current}")
    return snapshot


def scoped_claims(dsn: str, caller_scope: str) -> list[dict]:
    labels = _SCOPES.get(caller_scope, ("public",))
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, proposition, scope, access_label FROM claims"
                        " WHERE access_label = ANY(%s) ORDER BY id", (list(labels),))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows


def record_relation(dsn: str, cmd: Command, src_ref: str, dst_ref: str, kind: str,
                    detail: dict | None = None) -> CommandResult:
    if kind not in _RELATIONS:
        raise SettlementError(f"unknown relation kind {kind!r}")

    def _fn(cur, control):
        cur.execute("INSERT INTO evidence_relations (src_ref, dst_ref, kind, detail)"
                    " VALUES (%s, %s, %s, %s)"
                    " ON CONFLICT (src_ref, dst_ref, kind) DO NOTHING",
                    (src_ref, dst_ref, kind, _j(detail or {})))
        return (ResultCode.APPLIED, f"relation {kind} recorded",
                {"src_ref": src_ref, "dst_ref": dst_ref, "kind": kind},
                [("evidence.related", {"kind": kind})], [])
    return store.transact(dsn, cmd, _fn)


def claim_support_view(dsn: str, claim_id: str, caller_scope: str = "public") -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM claims WHERE id = %s", (claim_id,))
            claim = cur.fetchone()
            if claim is None:
                raise SettlementError(f"unknown claim {claim_id}")
            cur.execute("SELECT id, procedure, proc_version, status FROM derivations"
                        " WHERE claim_id = %s ORDER BY id", (claim_id,))
            derivations = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT derivation_id, group_id, premise_ref, premise_kind"
                        " FROM derivation_premises WHERE derivation_id IN"
                        " (SELECT id FROM derivations WHERE claim_id = %s) ORDER BY 1, 2",
                        (claim_id,))
            premises = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, kind, status FROM oppositions WHERE claim_id = %s", (claim_id,))
            opposition = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT supported, version, epoch FROM support_cache WHERE claim_id = %s",
                        (claim_id,))
            cache = cur.fetchone()
            conn.commit()
    return {"claim": {k: (dict(v) if isinstance(v, dict) else v) for k, v in dict(claim).items()},
            "derivations": derivations, "premises": premises, "opposition": opposition,
            "cache": dict(cache) if cache else None,
            "artifact_availability": artifacts.scoped_artifacts(dsn, caller_scope)}
