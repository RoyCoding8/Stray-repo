"""S3 capabilities (IF-4, LEARN-1/7/9): versioned executable methods, scoped
releases, quarantine registry, consolidation proposals.

A published candidate binds reference version, change, causal hypothesis,
scope, dependencies, protocol id and development budget. Generated code stays
untrusted: publication executes the artifact digest through broker
sandbox-exec and never imports it.
"""

from __future__ import annotations

import json
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


def resolve_entry_path(manifest: dict) -> str:
    entries = [e for e in manifest.get("files", [])
               if e.get("kind", "file") != "dir"]
    if not entries:
        raise SettlementError("capability artifact has no executable entry")
    paths = [e["path"] for e in entries]
    named = manifest.get("entry")
    if named is None:
        fallback = next((p for p in paths if p.endswith(".py")), None)
        if fallback is None:
            raise SettlementError("capability artifact has no executable entry")
        return fallback
    if named not in paths:
        raise SettlementError(
            f"capability artifact entry {named!r} is not in the manifest files")
    return named


def _extract_entry(artifacts_root: str | Path, digest: str) -> tuple[str, bytes, list[str]]:
    raw = (Path(artifacts_root) / digest).read_bytes()
    import hashlib

    if hashlib.sha256(raw).hexdigest() != digest:
        raise SettlementError(f"capability artifact {digest[:12]} bytes do not match their digest")
    try:
        package = json.loads(raw.decode())
        files = {rel: bytes.fromhex(hexed) for rel, hexed in package["files"].items()}
        manifest = package["manifest"]
        entry_path = resolve_entry_path(manifest)
        return (entry_path, files[entry_path],
                list(manifest.get("verify_args", ["--selftest"])))
    except SettlementError:
        raise
    except (ValueError, KeyError, StopIteration) as exc:
        raise SettlementError(f"capability artifact {digest[:12]} has no loadable entry: {exc}")


def _verified_op(dsn: str, launcher: Any, allocation_id: str, entry_rel: str,
                 entry_bytes: bytes, args: list[str], version_id: str,
                 attempt_id: str | None) -> str:
    operation_id = f"cap-verify-{version_id}"
    launcher.stage_input(operation_id, "", entry_rel, entry_bytes)
    in_dir, _ = launcher.exec_dirs(operation_id, "")
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile,
                 "argv": [launcher.staged_python(), f"{in_dir}/{entry_rel}", *args],
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
    entry_rel, entry_bytes, args = _extract_entry(artifacts_root, artifact_digest)
    operation_id = _verified_op(dsn, launcher, allocation_id, entry_rel,
                                entry_bytes, args, version_id, attempt_id)

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
                  evaluator_version: str, versions: list, scope: dict) -> None:
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
            cur.execute("SELECT candidate_version, evaluator_version, supported_scope"
                        " FROM trial_protocols WHERE id = %s", (protocol_id,))
            protocol = cur.fetchone()
            bundle = _evidence_bundle(cur, protocol_id)
            version_rows = {v: get_version(dsn, v) or {} for v in versions}
            conn.commit()
    if protocol is None:
        raise SettlementError(f"unknown protocol {protocol_id}")
    pinned = protocol["evaluator_version"] or ""
    _check_tested_versions(protocol_id, protocol["candidate_version"] or "",
                           versions)
    _check_supported_scope(version_rows, scope, disposition)
    _check_trial_scope(protocol_id, dict(protocol.get("supported_scope") or {}),
                       scope, disposition)
    _check_receipt_backing(protocol_id, pinned, *bundle)
    receipt_versions = {r["evaluator_version"] for r in bundle[2]}
    if evaluator_version != pinned or evaluator_version in ("",) or \
            receipt_versions - {evaluator_version}:
        raise SettlementError(
            f"evaluator version pin mismatch for {protocol_id}: release pins"
            f" {evaluator_version!r}, protocol pins {pinned!r},"
            f" receipts used {sorted(receipt_versions)}")


PROMOTING = ("limited", "default")

SYNTHETIC_ORIGINS = ("synthetic-fixture", "synthetic-direct",
                     "direct-caller-outcome")


def _evidence_bundle(cur, protocol_id: str) -> tuple:
    cur.execute("SELECT id, task_id, candidate_digest, evaluator_id,"
                " evaluator_version, evaluation_op FROM trial_assignments"
                " WHERE protocol_id = %s ORDER BY id", (protocol_id,))
    assignments = cur.fetchall()
    bindings = {a["id"]: a for a in assignments}
    cur.execute("SELECT assignment_id, outcome, invocation_ref FROM trial_results"
                " WHERE assignment_id IN (SELECT id FROM trial_assignments"
                " WHERE protocol_id = %s)", (protocol_id,))
    results = cur.fetchall()
    cur.execute("SELECT assignment_id, evaluator_id, evaluator_version,"
                " invocation_ref, result FROM evaluator_receipts WHERE assignment_id IN"
                " (SELECT id FROM trial_assignments WHERE protocol_id = %s)",
                (protocol_id,))
    receipts = cur.fetchall()
    refs = [r["invocation_ref"] for r in receipts if r["invocation_ref"]]
    success_ops: set = set()
    broker: dict = {}
    if refs:
        from . import evaluation
        cur.execute("SELECT operation_id, outcome, content FROM receipts"
                    " WHERE operation_id = ANY(%s)", (refs,))
        by_op: dict[str, list] = {}
        for row in cur.fetchall():
            entry = broker.setdefault(row["operation_id"],
                                      {"success": False, "tallies": []})
            if row["outcome"] == "success":
                entry["success"] = True
                success_ops.add(row["operation_id"])
            by_op.setdefault(row["operation_id"], []).append(row["content"])
        for operation_id, contents in by_op.items():
            broker[operation_id]["tallies"] = evaluation._tallies(contents)
    aids = [a["id"] for a in assignments]
    submissions: dict = {}
    if aids:
        cur.execute("SELECT assignment_id, content FROM candidate_submissions"
                    " WHERE assignment_id = ANY(%s) ORDER BY id", (aids,))
        from .common import payload_digest
        for row in cur.fetchall():
            submissions.setdefault(row["assignment_id"], []).append(
                payload_digest(dict(row["content"] or {})))
    return assignments, results, receipts, success_ops, bindings, submissions, broker


def _check_tested_versions(protocol_id: str, tested: str,
                           versions: list) -> None:
    if tested.startswith("multi:"):
        want = set(tested[len("multi:"):].split("+"))
        if set(versions) != want:
            raise SettlementError(
                f"candidate version pin mismatch for {protocol_id}: release binds"
                f" {sorted(set(versions))}, protocol tested multi-family"
                f" {sorted(want)}")
        return
    if not tested or set(versions) != {tested}:
        raise SettlementError(
            f"candidate version pin mismatch for {protocol_id}: release binds"
            f" {sorted(set(versions))}, protocol tested {tested!r}")


def _supported_scope(version_row: dict) -> dict:
    return dict(version_row.get("applicability") or {}) or \
        dict(version_row.get("scope") or {})


def _implication_gaps(supported: dict, wanted: dict) -> tuple[list, list]:
    missing = [key for key in supported if key not in wanted]
    changed = [key for key in supported
               if key in wanted and wanted[key] != supported[key]]
    return missing, changed


def _implication_error(source: str, supported: dict, wanted: dict) -> str | None:
    missing, changed = _implication_gaps(supported, wanted)
    if not missing and not changed:
        return None
    parts = []
    if missing:
        parts.append(f"drops supported constraint {missing[0]!r}")
    if changed:
        parts.append(f"changes supported constraint {changed[0]!r}"
                     f" from {supported[changed[0]]!r}"
                     f" to {wanted[changed[0]]!r}")
    return (f"release scope {wanted} {' and '.join(parts)} for {source}"
            f" (tested applicability {supported}): broadening release refused")


def _check_supported_scope(version_rows: dict, scope: dict,
                           disposition: str) -> None:
    if disposition not in PROMOTING:
        return
    wanted = dict(scope or {})
    for version_id, row in version_rows.items():
        supported = _supported_scope(row)
        if not supported:
            raise SettlementError(
                f"release scope {wanted} has no tested applicability"
                f" for {version_id}: promotion refused")
        error = _implication_error(version_id, supported, wanted)
        if error is not None:
            raise SettlementError(error)


def _check_trial_scope(protocol_id: str, trial_supported: dict, scope: dict,
                       disposition: str) -> None:
    if disposition not in PROMOTING:
        return
    supported = dict(trial_supported or {})
    if not supported:
        return
    error = _implication_error(f"trial protocol {protocol_id}", supported,
                               dict(scope or {}))
    if error is not None:
        raise SettlementError(error)


def _check_receipt_backing(protocol_id: str, pinned: str, assignments: list,
                           results: list, receipts: list,
                           success_ops: set, bindings: dict | None = None,
                           submissions: dict | None = None,
                           broker: dict | None = None) -> None:
    from . import evaluation

    if assignments and not receipts:
        raise SettlementError(
            f"protocol {protocol_id} has an empty evaluator-receipt set:"
            " release refused")
    by_result = {r["assignment_id"]: r for r in results}
    by_receipt = {r["assignment_id"]: r for r in receipts}
    missing = [a["id"] for a in assignments
               if a["id"] not in by_result or a["id"] not in by_receipt]
    if missing:
        raise SettlementError(
            f"protocol {protocol_id} has {len(missing)} assignments without"
            " authenticated evaluator results: release refused")
    for aid, row in by_result.items():
        rec = by_receipt[aid]
        bound = (bindings or {}).get(aid) or {}
        if not bound.get("evaluation_op"):
            raise SettlementError(
                f"assignment {aid} has no immutable evaluation binding:"
                " release refused")
        if rec["invocation_ref"] != bound["evaluation_op"]:
            raise SettlementError(
                f"assignment {aid} outcome is not bound to its evaluation"
                f" invocation {bound['evaluation_op']!r}: release refused")
        if (rec.get("evaluator_id"), rec["evaluator_version"]) != \
                (bound["evaluator_id"], bound["evaluator_version"]):
            raise SettlementError(
                f"assignment {aid} evaluator {rec.get('evaluator_id')}"
                f" v{rec['evaluator_version']} does not match its bound evaluator"
                f" {bound['evaluator_id']} v{bound['evaluator_version']}:"
                " evaluator replacement refused")
        digests = (submissions or {}).get(aid, [])
        if not digests or digests[-1] != bound["candidate_digest"]:
            raise SettlementError(
                f"candidate submission for assignment {aid} does not match its"
                " bound digest: mismatched candidate bytes refused")
        derived = dict(rec["result"] or {})
        if not rec["invocation_ref"] or \
                rec["invocation_ref"] != row["invocation_ref"]:
            raise SettlementError(
                f"assignment {aid} outcome is not bound to its evaluator"
                " invocation: release refused")
        if derived.get("outcome") != row["outcome"]:
            raise SettlementError(
                f"assignment {aid} outcome diverges from its evaluator receipt:"
                " release refused")
        if rec["evaluator_version"] != pinned or not pinned:
            raise SettlementError(
                f"evaluator version pin mismatch for {protocol_id}: protocol pins"
                f" {pinned!r}, receipt uses {rec['evaluator_version']!r}")
        detail = derived.get("detail")
        origin = dict(detail or {}).get("origin", "") \
            if isinstance(detail, dict) else ""
        if derived.get("simulated") is True or origin in SYNTHETIC_ORIGINS:
            raise SettlementError(
                f"assignment {aid} evaluator receipt is synthetic fixture data:"
                " release refused")
        task = detail.get("task_id") if isinstance(detail, dict) else None
        if task != bound.get("task_id"):
            raise SettlementError(
                f"assignment {aid} receipt names task {task!r}, bound task is"
                f" {bound.get('task_id')!r}: task identity mismatch refused")
        seen = (broker or {}).get(rec["invocation_ref"],
                                  {"success": False, "tallies": []})
        evaluation._check_claimed_outcome(rec["invocation_ref"],
                                          seen["success"], seen["tallies"],
                                          row["outcome"])
        if row["outcome"] == "success" and \
                rec["invocation_ref"] not in success_ops:
            raise SettlementError(
                f"assignment {aid} success has no succeeding evaluator"
                " invocation: release refused")


def _verdict_inside(cur, protocol_id: str) -> dict:
    cur.execute("SELECT 1 FROM trial_protocols WHERE id = %s", (protocol_id,))
    if cur.fetchone() is None:
        raise SettlementError(f"unknown protocol {protocol_id}")
    cur.execute("SELECT a.task_group, a.arm, r.outcome FROM trial_assignments a"
                " LEFT JOIN trial_results r ON r.assignment_id = a.id"
                " WHERE a.protocol_id = %s ORDER BY a.id", (protocol_id,))
    rows = cur.fetchall()
    missing = sum(1 for r in rows if r["outcome"] is None)
    if missing:
        raise SettlementError(f"protocol {protocol_id} has {missing} assigned cases without outcomes")
    groups: dict[str, dict[str, int]] = {}
    for row in rows:
        cell = groups.setdefault(row["task_group"], {"candidate": 0, "reference": 0})
        if row["outcome"] == "success":
            cell[row["arm"]] += 1
    cand = sum(cell["candidate"] for cell in groups.values())
    ref = sum(cell["reference"] for cell in groups.values())
    regressed = sorted(name for name, cell in groups.items()
                       if cell["candidate"] < cell["reference"])
    label = ("observed-gain" if cand > ref and not regressed else
             "regression" if ref > cand else "inconclusive")
    return {"label": label, "regressed_groups": regressed}


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
    _release_gate(dsn, protocol_id, disposition, evaluator_version, versions,
                  scope)
    from . import evidence  # noqa: PLC0415

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM capability_releases WHERE id = %s", (release_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"release {release_id} already exists")
        label = _verdict_inside(cur, protocol_id)["label"]
        if label == "regression" and disposition not in ("quarantined", "retired"):
            raise SettlementError(f"protocol {protocol_id} regressed: release refused")
        if label == "inconclusive" and disposition in ("limited", "default"):
            raise SettlementError(f"protocol {protocol_id} inconclusive: limited/default refused")
        cur.execute("SELECT DISTINCT evaluator_version FROM evaluator_receipts"
                    " WHERE assignment_id IN (SELECT id FROM trial_assignments"
                    " WHERE protocol_id = %s)", (protocol_id,))
        receipt_versions = {r["evaluator_version"] for r in cur.fetchall()}
        cur.execute("SELECT candidate_version, evaluator_version, supported_scope"
                    " FROM trial_protocols WHERE id = %s", (protocol_id,))
        protocol = cur.fetchone()
        pinned = (protocol["evaluator_version"] or "") if protocol else ""
        if evaluator_version != pinned or evaluator_version in ("",) or \
                receipt_versions - {evaluator_version}:
            raise SettlementError(f"evaluator version pin mismatch for {protocol_id}")
        tested = (protocol["candidate_version"] or "") if protocol else ""
        _check_tested_versions(protocol_id, tested, versions)
        cur.execute("SELECT id, applicability, scope FROM capability_versions"
                    " WHERE id = ANY(%s)", (list(versions),))
        _check_supported_scope({r["id"]: r for r in cur.fetchall()}, scope,
                               disposition)
        trial_supported = dict((protocol or {}).get("supported_scope") or {})
        _check_trial_scope(protocol_id, trial_supported, scope, disposition)
        _check_receipt_backing(protocol_id, pinned, *_evidence_bundle(cur, protocol_id))
        epoch = int(control["evidence_epoch"])
        for claim_id in (evidence_refs or []):
            evidence.check_use(dsn, claim_id, epoch)
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


def release(dsn: str, cmd: Command) -> CommandResult:
    payload = cmd.payload
    for key in ("release_id", "protocol_id", "versions", "scope", "disposition"):
        if key not in payload:
            raise SettlementError(f"release command needs {key}")
    return scoped_release(
        dsn, cmd, release_id=str(payload["release_id"]),
        protocol_id=str(payload["protocol_id"]), versions=list(payload["versions"]),
        scope=dict(payload["scope"]), disposition=str(payload["disposition"]),
        fallback=str(payload.get("fallback", "")),
        policy_version=str(payload.get("policy_version", "")),
        invalidation=payload.get("invalidation"),
        evidence_refs=payload.get("evidence_refs"),
        evaluator_version=str(payload.get("evaluator_version", "")))


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
