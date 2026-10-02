"""S3 capabilities (IF-4, LEARN-1/7/9): versioned executable methods, scoped
releases, quarantine registry, consolidation proposals.

A published candidate binds reference version, change, causal hypothesis,
scope, dependencies, protocol id and development budget. Generated code stays
untrusted: publication executes the artifact digest through broker
sandbox-exec and never imports it.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import artifacts, broker, db, store
from .common import Command, CommandResult, ResultCode, SettlementError

DISPOSITIONS = ("candidate", "experimental", "limited", "default",
                "quarantined", "retired")


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def get_version(dsn: str, version_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM capability_versions WHERE id = %s", (version_id,))
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def quarantine_status(dsn: str, version_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM quarantine_registry WHERE version_id = %s",
                        (version_id,))
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def pinned_quarantines(dsn: str, attempt_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT p.version_id, q.reason FROM attempt_capability_pins p"
                        " JOIN quarantine_registry q ON q.version_id = p.version_id"
                        " WHERE p.attempt_id = %s ORDER BY p.version_id", (attempt_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def pin_capability(dsn: str, attempt_id: str, version_id: str) -> dict:
    if get_version(dsn, version_id) is None:
        raise SettlementError(f"unknown capability version {version_id}")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM attempts WHERE id = %s", (attempt_id,))
            if cur.fetchone() is None:
                raise SettlementError(f"unknown attempt {attempt_id}")
            cur.execute("INSERT INTO attempt_capability_pins (attempt_id, version_id)"
                        " VALUES (%s, %s) ON CONFLICT DO NOTHING", (attempt_id, version_id))
            conn.commit()
    return {"attempt_id": attempt_id, "version_id": version_id}


def _extract_entry(artifacts_root: str | Path, digest: str) -> tuple[Path, list[str], Path]:
    raw = (Path(artifacts_root) / digest).read_bytes()
    package = json.loads(raw.decode())
    files = {rel: bytes.fromhex(hexed) for rel, hexed in package["files"].items()}
    manifest = package["manifest"]
    entries = [e for e in manifest.get("files", []) if e.get("kind", "file") != "dir"]
    if not entries:
        raise SettlementError("capability artifact has no executable entry")
    named = manifest.get("entry")
    entry = next((e for e in entries if e["path"] == named),
                 next(e for e in entries if e["path"].endswith(".py")))
    work = Path(tempfile.mkdtemp(prefix="cap-verify-"))
    target = work / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(files[entry["path"]])
    return target, list(manifest.get("verify_args", ["--selftest"])), work


def _verified_op(dsn: str, launcher: Any, allocation_id: str, entry: Path,
                 args: list[str], version_id: str, attempt_id: str | None) -> str:
    operation_id = f"cap-verify-{version_id}"
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile, "argv": [sys.executable, str(entry), *args],
                 "timeout_ms": 30_000, "max_output_bytes": 65_536},
        allocation_id=allocation_id, attempt_id=attempt_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"capability verification not admitted: {ensured.detail}")
    status = broker.dispatch_operation(dsn, operation_id,
                                       launchers={launcher.profile: launcher})
    if status.dispatch_state not in ("observed", "reconciled"):
        raise SettlementError(
            f"capability verification never observed: {status.next_decision}")
    row = broker.read_operation(dsn, operation_id) or {}
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s",
                        (operation_id,))
            receipts = [dict(r) for r in cur.fetchall()]
            conn.commit()
    _ = row
    if not any(r["outcome"] == "success" for r in receipts):
        raise SettlementError("capability verification executed but did not succeed")
    return operation_id


def publish_candidate(dsn: str, cmd: Command, artifacts_root: str | Path,
                      launcher: Any, allocation_id: str, *, version_id: str,
                      family: str = "", invocation: dict | None = None,
                      effect: dict | None = None, resource: dict | None = None,
                      artifact_digest: str = "", applicability: dict | None = None,
                      evidence_refs: list | None = None, reference_version: str = "",
                      change: str = "", hypothesis: str = "", scope: dict | None = None,
                      dependencies: list | None = None, protocol_id: str = "",
                      budget: dict | None = None, attempt_id: str | None = None) -> CommandResult:
    if not version_id or not artifact_digest:
        raise SettlementError("candidate needs a version id and artifact digest")
    if not artifacts.artifact_available(dsn, artifacts_root, artifact_digest):
        raise SettlementError(f"artifact {artifact_digest[:12]} is not available")
    entry, args, _work = _extract_entry(artifacts_root, artifact_digest)
    operation_id = _verified_op(dsn, launcher, allocation_id, entry, args,
                                version_id, attempt_id)

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM capability_versions WHERE id = %s", (version_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"capability version {version_id} already exists")
        cur.execute(
            "INSERT INTO capability_versions (id, family, invocation, effect, resource,"
            " artifact_digest, applicability, evidence_refs, reference_version, change_desc,"
            " hypothesis, scope, dependencies, protocol_id, budget, verification_op)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (version_id, family, _j(invocation or {}), _j(effect or {}),
             _j(resource or {}), artifact_digest, _j(applicability or {}),
             _j(evidence_refs or []), reference_version, change, hypothesis,
             _j(scope or {}), _j(dependencies or []),
             protocol_id, _j(budget or {}), operation_id))
        return (ResultCode.APPLIED, f"candidate {version_id} published",
                {"version_id": version_id, "verification_op": operation_id},
                [("capability.published", {"version_id": version_id})], [])
    return store.transact(dsn, cmd, _fn)


def _release_gate(dsn: str, protocol_id: str, disposition: str,
                  evaluator_version: str) -> None:
    from . import trials  # noqa: PLC0415

    verdict = trials.verdict(dsn, protocol_id)
    label = verdict["label"]
    if label == "regression" and disposition not in ("quarantined", "retired"):
        raise SettlementError(f"protocol {protocol_id} regressed: release refused")
    if label == "inconclusive" and disposition in ("limited", "default"):
        raise SettlementError(
            f"protocol {protocol_id} inconclusive: limited/default release refused")
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT evaluator_version FROM trial_protocols WHERE id = %s",
                        (protocol_id,))
            protocol = cur.fetchone()
            cur.execute("SELECT DISTINCT evaluator_version FROM evaluator_receipts"
                        " WHERE assignment_id IN (SELECT id FROM trial_assignments"
                        " WHERE protocol_id = %s)", (protocol_id,))
            receipt_versions = {r["evaluator_version"] for r in cur.fetchall()}
            conn.commit()
    if protocol is None:
        raise SettlementError(f"unknown protocol {protocol_id}")
    pinned = protocol["evaluator_version"] or ""
    if evaluator_version != pinned or evaluator_version in ("",) or \
            receipt_versions - {evaluator_version}:
        raise SettlementError(
            f"evaluator version pin mismatch for {protocol_id}: release pins"
            f" {evaluator_version!r}, protocol pins {pinned!r},"
            f" receipts used {sorted(receipt_versions)}")


def scoped_release(dsn: str, cmd: Command, *, release_id: str, protocol_id: str,
                   versions: list[str], scope: dict, disposition: str,
                   fallback: str = "", policy_version: str = "",
                   invalidation: dict | None = None, evidence_refs: list | None = None,
                   evaluator_version: str = "") -> CommandResult:
    if disposition not in DISPOSITIONS:
        raise SettlementError(f"unknown disposition {disposition!r}")
    if not versions:
        raise SettlementError("release needs exact versions")
    for version_id in versions:
        if get_version(dsn, version_id) is None:
            raise SettlementError(f"unknown capability version {version_id}")
        if quarantine_status(dsn, version_id) is not None and \
                disposition not in ("quarantined", "retired"):
            raise SettlementError(f"version {version_id} is quarantined")
    _release_gate(dsn, protocol_id, disposition, evaluator_version)
    from . import evidence  # noqa: PLC0415

    epoch = int(store.get_control(dsn)["evidence_epoch"])
    for claim_id in (evidence_refs or []):
        evidence.check_use(dsn, claim_id, epoch)

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM capability_releases WHERE id = %s", (release_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"release {release_id} already exists")
        cur.execute(
            "INSERT INTO capability_releases (id, protocol_id, versions, scope, disposition,"
            " fallback, policy_version, invalidation, evidence_refs, evaluator_version)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (release_id, protocol_id, _j(versions), _j(scope), disposition, fallback,
             policy_version, _j(invalidation or {}), _j(evidence_refs or []),
             evaluator_version))
        cur.execute("UPDATE control SET release_epoch = release_epoch + 1 WHERE id = 1")
        return (ResultCode.APPLIED, f"release {release_id} {disposition}",
                {"release_id": release_id, "disposition": disposition},
                [("capability.released", {"release_id": release_id})], [])
    return store.transact(dsn, cmd, _fn)


def releases_for_scope(dsn: str, family: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM capability_releases ORDER BY created_at")
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return [r for r in rows
            if not family or dict(r["scope"] or {}).get("family", family) == family]


def quarantine(dsn: str, cmd: Command, version_id: str, reason: str = "") -> CommandResult:
    if get_version(dsn, version_id) is None:
        raise SettlementError(f"unknown capability version {version_id}")

    def _fn(cur, control):
        cur.execute("INSERT INTO quarantine_registry (version_id, reason)"
                    " VALUES (%s, %s) ON CONFLICT (version_id) DO UPDATE"
                    " SET reason = EXCLUDED.reason",
                    (version_id, reason))
        cur.execute("UPDATE control SET release_epoch = release_epoch + 1 WHERE id = 1")
        return (ResultCode.APPLIED, f"version {version_id} quarantined",
                {"version_id": version_id, "reason": reason},
                [("capability.quarantined", {"version_id": version_id})], [])
    return store.transact(dsn, cmd, _fn)


def save_router_policy(dsn: str, cmd: Command, *, version: str,
                       mapping: dict, evidence_refs: list | None = None) -> CommandResult:
    if not version or not isinstance(mapping, dict):
        raise SettlementError("router policy needs a version and family mapping")

    def _fn(cur, control):
        cur.execute("INSERT INTO router_policies (version, mapping, evidence_refs)"
                    " VALUES (%s, %s, %s) ON CONFLICT (version) DO UPDATE SET"
                    " mapping = EXCLUDED.mapping, evidence_refs = EXCLUDED.evidence_refs",
                    (version, _j(mapping), _j(evidence_refs or [])))
        return (ResultCode.APPLIED, f"router policy {version} saved",
                {"version": version},
                [("capability.router_saved", {"version": version})], [])
    return store.transact(dsn, cmd, _fn)


def route(dsn: str, policy_version: str, family: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT mapping FROM router_policies WHERE version = %s",
                        (policy_version,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown router policy {policy_version}")
    version_id = dict(row["mapping"] or {}).get(family)
    if not version_id:
        return {"family": family, "decision": "abstain", "version_id": None}
    if quarantine_status(dsn, version_id) is not None:
        return {"family": family, "decision": "abstain", "version_id": None,
                "reason": f"{version_id} quarantined"}
    return {"family": family, "decision": "select", "version_id": version_id}


def evaluate_router(dsn: str, policy_version: str,
                    cases: list[dict]) -> dict:
    scored = []
    for case in cases:
        routed = route(dsn, policy_version, case["family"])
        expected = case.get("expected")
        if routed["decision"] == "abstain":
            verdict = "abstain"
        elif expected is None:
            verdict = "selected"
        else:
            verdict = "correct" if routed["version_id"] == expected else "wrong-version"
        scored.append({"family": case["family"], "expected": expected,
                       "got": routed["version_id"], "verdict": verdict})
    return {"policy_version": policy_version, "cases": scored,
            "correct": sum(1 for s in scored if s["verdict"] == "correct"),
            "wrong": sum(1 for s in scored if s["verdict"] == "wrong-version"),
            "abstained": sum(1 for s in scored if s["verdict"] == "abstain")}


def propose_consolidation(dsn: str, cmd: Command, *, proposal_id: str,
                          subject_versions: list[str], action: str,
                          costs: dict | None = None, affected: list | None = None,
                          rationale: str = "") -> CommandResult:
    if action not in ("reuse", "retire"):
        raise SettlementError(f"unknown consolidation action {action!r}")
    if not subject_versions:
        raise SettlementError("consolidation needs subject versions")

    def _fn(cur, control):
        cur.execute("INSERT INTO consolidation_proposals (id, subject_versions, action,"
                    " costs, affected, rationale) VALUES (%s, %s, %s, %s, %s, %s)",
                    (proposal_id, _j(subject_versions), action, _j(costs or {}),
                     _j(affected or []), rationale))
        return (ResultCode.APPLIED, f"consolidation {proposal_id} proposed",
                {"proposal_id": proposal_id, "action": action},
                [("capability.consolidation_proposed", {"proposal_id": proposal_id})], [])
    return store.transact(dsn, cmd, _fn)
