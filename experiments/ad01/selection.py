"""AD01 repertoire selection: binding-aware over capability_releases.

Binding-aware selection only: a caller passes an explicit release id and
the store resolves that release's active eligible binding. No release
means no binding, and the caller falls back to the explicit incumbent.
The retired global-newest scan and the first-family-match fallback could
let an unrelated release decide a use. The release `fallback` substitution
is retired for the same reason: every disposition that reaches selection is
a promoting one, so substituting a fallback member could only ever execute
unassessed bytes while the use record still named the requested capability.
Absent pinned bytes now refuse, and `trajectory._use_refusal` reports why. A promoting bind (limited or
default) additionally requires a qualifying current assessment for the
exact frozen bytes, protocol, evaluator and scope; the release row pins
that provenance so fresh-process use resolves identical bytes.
"""

from __future__ import annotations

import hashlib

ELIGIBLE_DISPOSITIONS = ("default", "limited")

PROMOTING = ("limited", "default")


class StaleBind(Exception):
    pass


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def active_binding_for(dsn: str, family: str,
                       release_id: str | None = None) -> dict | None:
    if release_id is None:
        return None
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT * FROM capability_releases WHERE id = %s",
            (release_id,)).fetchone()
        conn.commit()
        rows = [row] if row is not None else []
    eligible = []
    for row in rows:
        if row is None:
            continue
        record = dict(row)
        scope = dict(record.get("scope") or {})
        if family and scope.get("family", family) != family:
            continue
        if record.get("disposition") not in ELIGIBLE_DISPOSITIONS:
            continue
        eligible.append(record)
    if not eligible:
        return None
    return eligible[-1]


def binding_provenance(binding: dict) -> dict:
    return dict((binding or {}).get("invalidation") or {})


def bind_revision(dsn: str, *, release_id: str, versions: list,
                  scope: dict, disposition: str, fallback: str = "",
                  expected_versions: list | None,
                  policy_version: str = "",
                  protocol_id: str = "",
                  evaluator_version: str = "",
                  evidence_refs: list | None = None,
                  proposal_id: str = "",
                  candidate_digest: str = "",
                  request_id: str | None = None) -> dict:
    from psycopg.types.json import Json
    from settlement import store
    from settlement.common import Command, ResultCode
    if not release_id or not versions:
        raise ValueError("bind needs a release id and exact versions")
    if disposition not in ("candidate", "experimental", "limited",
                           "default", "quarantined", "retired"):
        raise ValueError("unknown disposition %r" % (disposition,))
    if not protocol_id:
        raise ValueError("bind needs a protocol id for release %r"
                         % (release_id,))
    if not evaluator_version:
        raise ValueError("bind needs an evaluator version for release %r"
                         % (release_id,))
    refs = [ref for ref in (evidence_refs or [])
            if isinstance(ref, str) and ref]
    if not refs:
        raise ValueError("bind needs non-empty evidence references"
                         " for release %r" % (release_id,))
    if not proposal_id or not candidate_digest:
        raise ValueError("bind pins exact frozen bytes for release %r:"
                         " proposal and candidate digest required"
                         % (release_id,))
    from . import records as _records
    proposal = _records.load_revision_proposal(dsn, proposal_id)
    if proposal is None:
        raise ValueError("no revision proposal %r for release %r"
                         % (proposal_id, release_id))
    freeze = _records.load_freeze(dsn, proposal_id)
    if freeze is None or not freeze.get("candidate_digest"):
        raise ValueError("no frozen candidate for proposal %r"
                         " (release %r)" % (proposal_id, release_id))
    if freeze["candidate_digest"] != candidate_digest:
        raise ValueError("bind bytes %r mismatch frozen bytes %r"
                         " (proposal %r)"
                         % (candidate_digest,
                            freeze["candidate_digest"], proposal_id))
    if proposal.get("protocol_id") != protocol_id:
        raise ValueError("bind protocol %r mismatches proposal protocol %r"
                         % (protocol_id, proposal.get("protocol_id")))
    assessment = _records.load_assessment(
        dsn, proposal_id, candidate_digest)
    if assessment is None:
        raise ValueError("absent assessment for proposal %r bytes %r"
                         " (release %r): assess frozen bytes before binding"
                         % (proposal_id, candidate_digest, release_id))
    if assessment.get("attempt_id") not in refs:
        raise ValueError("bind evidence must cite assessment %r"
                         " for release %r"
                         % (assessment.get("attempt_id"), release_id))
    if assessment.get("protocol_id") != protocol_id:
        raise ValueError("bind protocol %r mismatches assessment"
                         " protocol %r (release %r)"
                         % (protocol_id, assessment.get("protocol_id"),
                            release_id))
    if assessment.get("evaluator_version") != evaluator_version:
        raise ValueError("bind evaluator %r mismatches assessment"
                         " evaluator %r (release %r)"
                         % (evaluator_version,
                            assessment.get("evaluator_version"),
                            release_id))
    if dict(assessment.get("scope") or {}) != dict(scope or {}):
        raise ValueError("bind scope %r mismatches assessed scope %r"
                         " (release %r)"
                         % (scope, assessment.get("scope"), release_id))
    if disposition in PROMOTING and assessment.get("outcome") != "bind":
        raise ValueError("assessment %r forbids promotion: %s"
                         % (assessment.get("attempt_id"),
                            assessment.get("reason",
                                           assessment.get("outcome"))))
    from settlement.common import payload_digest
    request_payload = {"release": release_id, "versions": list(versions),
                       "scope": dict(scope), "disposition": disposition,
                       "fallback": fallback, "policy_version": policy_version,
                       "protocol_id": protocol_id,
                       "evaluator_version": evaluator_version,
                       "evidence_refs": refs, "proposal_id": proposal_id,
                       "candidate_digest": candidate_digest}
    canonical_request_id = "s09-bind-%s-%s" % (
        release_id, payload_digest(request_payload)[:12])
    if request_id is not None and request_id != canonical_request_id:
        raise ValueError("bind request id must be canonical")
    request_id = canonical_request_id
    provenance = {"proposal_id": proposal_id,
                  "candidate_digest": candidate_digest}

    def _fn(cur, control):
        cur.execute("SELECT * FROM capability_releases WHERE id = %s"
                    " FOR UPDATE", (release_id,))
        current = cur.fetchone()
        if current is None:
            if expected_versions not in (None, []):
                raise StaleBind(
                    "no binding for %r, expected %r" % (
                        release_id, expected_versions))
            cur.execute(
                "INSERT INTO capability_releases"
                " (id, protocol_id, versions, scope, disposition,"
                " fallback, policy_version, invalidation,"
                " evidence_refs, evaluator_version)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (release_id, protocol_id, Json(list(versions)),
                 Json(dict(scope)), disposition, fallback,
                 policy_version, Json(provenance), Json(refs),
                 evaluator_version))
            return (ResultCode.APPLIED, "bound %s" % release_id,
                    {"release_id": release_id,
                     "versions": list(versions)}, [], [])
        have = list(dict(current).get("versions") or [])
        if expected_versions != have:
            raise StaleBind(
                "stale bind for %r: expected %r, have %r" % (
                    release_id, expected_versions, have))
        cur.execute(
            "UPDATE capability_releases SET protocol_id = %s,"
            " versions = %s, scope = %s, disposition = %s,"
            " fallback = %s, policy_version = %s,"
            " invalidation = %s, evidence_refs = %s,"
            " evaluator_version = %s"
            " WHERE id = %s",
            (protocol_id, Json(list(versions)), Json(dict(scope)),
             disposition, fallback, policy_version,
             Json(provenance), Json(refs),
             evaluator_version, release_id))
        return (ResultCode.APPLIED, "rebound %s" % release_id,
                {"release_id": release_id,
                 "versions": list(versions)}, [], [])

    result = store.transact(dsn, Command(request_id=request_id,
                                         payload={"release_id": release_id,
                                                  "versions": list(versions),
                                                  "scope": dict(scope),
                                                  "disposition": disposition}),
                            _fn)
    if result.code not in (ResultCode.APPLIED,
                           ResultCode.ALREADY_APPLIED):
        raise StaleBind(result.detail or "bind refused")
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT * FROM capability_releases WHERE id = %s",
            (release_id,)).fetchone()
        conn.commit()
        return dict(row) if row is not None else {}


def _bound_member(members: list, versions: list,
                  candidate_digest: str = "") -> dict | None:
    wanted = set(versions or [])
    for member in members:
        if member.get("capability_id") not in wanted:
            continue
        source = member.get("method_source")
        if not candidate_digest or not isinstance(source, str):
            continue
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if member.get("source_digest") != candidate_digest or digest != candidate_digest:
            continue
        return member
    return None


def select_member(repertoire: dict, task: dict,
                  dsn: str | None = None,
                  release_id: str | None = None) -> dict | None:
    members = list(repertoire.get("members", []))
    family = task.get("family", "")
    if release_id is None:
        for member in members:
            if member.get("scope", {}).get("family") == family:
                return member
        return None
    binding = None
    if dsn is not None:
        binding = active_binding_for(dsn, family,
                                     release_id=release_id)
    elif isinstance(repertoire.get("active_binding"), dict):
        candidate = dict(repertoire["active_binding"])
        if candidate.get("disposition") in ELIGIBLE_DISPOSITIONS:
            scope = dict(candidate.get("scope") or {})
            if not family or scope.get("family", family) == family:
                binding = candidate
    if binding is None:
        return None
    chosen = _bound_member(members, list(binding.get("versions") or []),
                           str(binding_provenance(binding).get(
                               "candidate_digest") or ""))
    if chosen is not None:
        return chosen
    return None


def versioned_use_op_id(campaign_id: str, task_id: str,
                        method_version: str) -> str:
    return "ad01-%s-use-%s-%s" % (campaign_id, task_id, method_version)
