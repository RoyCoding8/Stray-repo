"""Run bounded P10 campaigns over the single mutable P05 agenda owner."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from psycopg.rows import dict_row
from psycopg.types.json import Json

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError, StaleRevision, payload_digest
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

from . import agenda, archive, gate, genome, investigation, task, verifier

_PROTOCOL_SCHEMA = "p10-assessment/1"
_EXPORT_SCHEMA = "p10-campaign-export/1"
_MAX_PROTOCOL_BYTES = 262_144
_MAX_ROUNDS = 32
_MAX_WAKES = 10_000


def _canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        return json.loads(raw), raw
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SettlementError(f"campaign data must be finite JSON: {exc}") from exc


def route_identity(base_url: str) -> str:
    """Return a credential-free identity for one exact configured route URL."""
    if not isinstance(base_url, str) or not base_url.strip():
        raise SettlementError("route base URL is required")
    parsed = urlsplit(base_url)
    if (not parsed.scheme or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise SettlementError("route base URL cannot contain credentials, query or fragment")
    return hashlib.sha256(base_url.rstrip("/").encode("utf-8")).hexdigest()


def _parse_protocol(protocol, max_turns):
    protocol, raw = _canonical(protocol)
    if len(raw) > _MAX_PROTOCOL_BYTES:
        raise SettlementError("assessment protocol exceeds byte bound")
    if not isinstance(protocol, dict) or set(protocol) != {"schema", "rounds"}:
        raise SettlementError("assessment protocol needs exactly schema and rounds")
    if protocol["schema"] != _PROTOCOL_SCHEMA:
        raise SettlementError(f"assessment protocol must use {_PROTOCOL_SCHEMA}")
    rounds = protocol["rounds"]
    if not isinstance(rounds, list) or not 0 < len(rounds) <= _MAX_ROUNDS:
        raise SettlementError(f"assessment protocol needs 1..{_MAX_ROUNDS} rounds")
    required = {"id", "after_turn", "epoch", "parent", "candidate", "model", "route_identity"}
    ids, milestones = set(), []
    for item in rounds:
        if not isinstance(item, dict) or set(item) != required:
            raise SettlementError("each assessment round must have the pinned protocol fields")
        if any(not isinstance(item[key], str) or not item[key].strip()
               for key in required - {"after_turn"}):
            raise SettlementError("assessment round identities must be non-empty strings")
        if item["id"] in ids:
            raise SettlementError("assessment round ids must be unique")
        ids.add(item["id"])
        turn = item["after_turn"]
        if type(turn) is not int or turn < 0 or turn > max_turns:
            raise SettlementError("assessment milestones must be within the charter turn cap")
        milestones.append(turn)
        route = item["route_identity"]
        if len(route) != 64 or any(c not in "0123456789abcdef" for c in route):
            raise SettlementError("route_identity must be a lowercase SHA-256 digest")
    if milestones != sorted(milestones):
        raise SettlementError("assessment milestones must be nondecreasing")
    return protocol, raw


def _round_tasks(dsn, artifacts_root, protocol):
    by_epoch, anchors = {}, {}
    for round_ in protocol["rounds"]:
        with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT tasks,budget,policy,execution FROM rsi_gate_epochs WHERE digest=%s",
                        (round_["epoch"],))
            epoch = cur.fetchone()
        if epoch is None:
            raise SettlementError("assessment round names an unknown gate epoch")
        if epoch["policy"] != gate.POLICY:
            raise SettlementError("assessment round uses an unsupported gate policy")
        budget = epoch["budget"]
        if budget.get("model") != round_["model"]:
            raise SettlementError("assessment model differs from frozen gate budget")
        if round_["parent"] == round_["candidate"]:
            raise SettlementError("assessment comparison needs a changed candidate")
        specs = epoch["tasks"]
        tasks = {digest: task.load(dsn, artifacts_root, digest) for digest in specs}
        if any(specs[d] != {"split": item.split, "evaluator": item.evaluator_version}
               for d, item in tasks.items()):
            raise SettlementError("gate epoch task or evaluator identity drifted")
        if {item.split for item in tasks.values()} != {"dev", "val", "anchor"}:
            raise SettlementError("assessment epoch needs dev, val and anchor tasks")
        genome.load(dsn, artifacts_root, round_["parent"])
        genome.load(dsn, artifacts_root, round_["candidate"])
        by_epoch.setdefault(round_["epoch"], {"specs": specs, "tasks": tasks,
                                               "budget": budget, "execution": epoch["execution"]})
        if by_epoch[round_["epoch"]]["specs"] != specs:
            raise SettlementError("one epoch has contradictory task declarations")
        anchors[round_["id"]] = [item for item in tasks.values() if item.split == "anchor"]
    return by_epoch, anchors


def _validate_authority(cur, campaign_id, charter, protocol, by_epoch):
    cur.execute("SELECT authority_version FROM control WHERE id=1")
    control = cur.fetchone()
    cur.execute("SELECT authority_grant FROM grants WHERE version=%s", (charter["grant_version"],))
    grant_row = cur.fetchone()
    if control is None or grant_row is None or int(control["authority_version"]) != charter["grant_version"]:
        raise SettlementError("pinned campaign grant is not current")
    authority = dict(grant_row["authority_grant"] or {})
    assessment_tasks = {digest for epoch in by_epoch.values() for digest in epoch["specs"]}
    comparison_genomes = {value for round_ in protocol["rounds"]
                          for value in (round_["parent"], round_["candidate"])}
    if (authority.get("kind") != "rsi-agenda"
            or authority.get("agenda_id") != campaign_id
            or not assessment_tasks <= set(authority.get("assessment_task_ids", []))
            or not comparison_genomes <= set(authority.get("genome_ids", []))):
        raise SettlementError("grant does not authorize assessment tasks and comparison genomes")


def _validate_exposure(dsn, artifacts_root, charter, anchors_by_round):
    development = [task.load(dsn, artifacts_root, item["task_id"])
                   for item in charter["opportunities"]]
    development_ids = {gate.anchor_identity(item) for item in development}
    seen = set()
    for anchors in anchors_by_round.values():
        current = {gate.anchor_identity(item) for item in anchors}
        if len(current) != len(anchors):
            raise SettlementError("protected anchor content repeats within an assessment round")
        if development_ids & current:
            raise SettlementError("protected anchor content overlaps development work")
        if seen & current:
            raise SettlementError("protected anchor content repeats across assessment rounds")
        seen.update(current)


def _protocol_package(raw, staging_root):
    manifest = {"kind": "p10-assessment", "schema": _PROTOCOL_SCHEMA,
                "files": [{"path": "protocol.json", "kind": "file", "size": len(raw),
                           "digest": hashlib.sha256(raw).hexdigest()}]}
    package = artifacts.stage_package(
        None, staging_root, manifest=manifest, files={"protocol.json": raw},
        scope="rsi-assessment-protocol", access_label="evaluator",
        format="p10-assessment", version="1",
    )
    return package


def start(dsn, *, campaign_id, charter, protocol, staging_root, artifacts_root):
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        raise SettlementError("campaign_id must be non-empty")
    charter, _ = _canonical(charter)
    if not isinstance(charter, dict):
        raise SettlementError("campaign charter must be an object")
    charter = agenda._parse(charter)
    parsed, raw = _parse_protocol(protocol, charter["max_turns"])
    agenda._load_catalogue(dsn, artifacts_root, charter, allow_missing=False)
    by_epoch, anchors = _round_tasks(dsn, artifacts_root, parsed)
    _validate_exposure(dsn, artifacts_root, charter, anchors)
    protocol_package = _protocol_package(raw, staging_root)
    supplied = charter.get("assessment_protocol")
    if supplied is not None and supplied != protocol_package["digest"]:
        raise SettlementError("charter assessment_protocol differs from published protocol digest")
    charter["assessment_protocol"] = protocol_package["digest"]
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        agenda._authority(cur, campaign_id, charter)
        _validate_authority(cur, campaign_id, charter, parsed, by_epoch)
    result = artifacts.publish_package(
        dsn,
        Command(request_id="p10-protocol:" + protocol_package["digest"],
                payload={"digest": protocol_package["digest"]}),
        artifacts_root, protocol_package,
    )
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    state = agenda.create(dsn, agenda_id=campaign_id, charter=charter,
                          artifacts_root=artifacts_root)
    return {"campaign_id": campaign_id, "revision": state["revision"],
            "status": state["status"], "protocol_digest": protocol_package["digest"],
            "charter_digest": state["charter_digest"]}


def inspect(dsn, campaign_id):
    state = agenda.read(dsn, campaign_id)
    if state is None:
        return None
    return {"campaign_id": campaign_id, "revision": state["revision"],
            "turns": state["turns"], "status": state["status"],
            "protocol_digest": state["charter"].get("assessment_protocol"),
            "flight_pending": state["flight"] is not None,
            "last_result_status": (state.get("last_result") or {}).get("status")}


def suspend(dsn, campaign_id, expected_revision):
    return agenda.control(dsn, campaign_id, expected_revision, "suspend")


def resume(dsn, campaign_id, expected_revision):
    return agenda.control(dsn, campaign_id, expected_revision, "resume")


def stop(dsn, campaign_id, expected_revision):
    return agenda.control(dsn, campaign_id, expected_revision, "stop")


def _assignment_id(campaign_id, round_id):
    digest = hashlib.sha256(f"{campaign_id}:{round_id}".encode()).hexdigest()
    return "p10-assignment-" + digest


def _gate_id(campaign_id, round_id):
    digest = hashlib.sha256(f"{campaign_id}:{round_id}".encode()).hexdigest()
    return "p10-gate-" + digest


def _deadline_passed(charter):
    return datetime.now(UTC) >= datetime.fromisoformat(charter["deadline"])


def _assign_due(dsn, campaign_id, state, protocol):
    assigned_rows = agenda.export(dsn, campaign_id)["decisions"]
    assigned = {row["data"].get("round_id") for row in assigned_rows
                if row["kind"] == "p10.assessment.assignment"}
    due = next((item for item in protocol["rounds"]
                if item["id"] not in assigned and item["after_turn"] <= state["turns"]), None)
    if due is None:
        return None
    assignment_id, gate_id = _assignment_id(campaign_id, due["id"]), _gate_id(campaign_id, due["id"])
    expected_revision = int(state["revision"])
    data = {"agenda_id": campaign_id, "agenda_revision": expected_revision,
            "round_id": due["id"], "after_turn": due["after_turn"],
            "protocol_digest": state["charter"]["assessment_protocol"],
            "gate_id": gate_id, "epoch": due["epoch"], "parent": due["parent"],
            "candidate": due["candidate"], "model": due["model"],
            "route_identity": due["route_identity"]}
    command = Command(
        request_id=f"p10-assignment:{campaign_id}:{due['id']}:{expected_revision}",
        payload={"agenda_id": campaign_id, "expected_revision": expected_revision,
                 "assignment_id": assignment_id, "data": data},
    )

    def admit(cur, control):
        cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (campaign_id,))
        current = cur.fetchone()
        if current is None or int(current["revision"]) != expected_revision:
            raise StaleRevision("campaign changed before assessment assignment")
        if current["status"] not in {"active", "complete"}:
            raise SettlementError("campaign control prevents assessment assignment")
        if current["flight"] is not None:
            raise SettlementError("P01 flight is unresolved before assessment")
        if int(current["turns"]) < due["after_turn"]:
            raise StaleRevision("assessment milestone is no longer due")
        pending = agenda._pending_assessment(cur, campaign_id)
        if pending is not None:
            raise StaleRevision("an earlier assessment assignment is still pending")
        if _deadline_passed(current["charter"]):
            raise StaleRevision("campaign deadline passed before assessment assignment")
        cur.execute("SELECT 1 FROM rsi_decisions WHERE id=%s OR (subject=%s AND kind=%s AND data->>'round_id'=%s)",
                    (assignment_id, campaign_id, "p10.assessment.assignment", due["id"]))
        if cur.fetchone() is not None:
            return ResultCode.ALREADY_APPLIED, "assessment already assigned", data, [], []
        agenda._authority(cur, campaign_id, current["charter"])
        cur.execute("INSERT INTO rsi_decisions (id,kind,actor,subject,data)"
                    " VALUES (%s,'p10.assessment.assignment','fixed',%s,%s)",
                    (assignment_id, campaign_id, Json(data)))
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,updated_at=now() WHERE agenda_id=%s",
                    (campaign_id,))
        return (ResultCode.APPLIED, "assessment assigned", data,
                [("rsi.campaign.assessment-assigned", {"campaign_id": campaign_id,
                                                       "round_id": due["id"]})], [])

    result = store.transact(dsn, command, admit)
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return result.data
    if result.code == ResultCode.STALE_REVISION:
        return None
    raise SettlementError(result.detail)


def _pending(dsn, campaign_id):
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        return agenda._pending_assessment(cur, campaign_id)


def _load_protocol(dsn, state, artifacts_root):
    digest = state["charter"].get("assessment_protocol")
    if not isinstance(digest, str) or len(digest) != 64:
        raise SettlementError("campaign has no pinned assessment protocol")
    raw = (Path(artifacts_root) / digest).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise SettlementError("assessment protocol artifact digest mismatch")
    package = json.loads(raw)
    if (package.get("scope") != "rsi-assessment-protocol"
            or package.get("manifest", {}).get("schema") != _PROTOCOL_SCHEMA):
        raise SettlementError("assessment protocol artifact has the wrong identity")
    protocol_bytes = bytes.fromhex(package["files"]["protocol.json"])
    protocol = json.loads(protocol_bytes)
    parsed, canonical = _parse_protocol(protocol, state["charter"]["max_turns"])
    if canonical != protocol_bytes:
        raise SettlementError("assessment protocol bytes are not canonical")
    return digest, parsed


def _run_assignment(dsn, campaign_id, assignment, agent, checker, staging_root, artifacts_root):
    data = assignment.get("data", assignment)
    provider = getattr(agent, "provider", None)
    if provider is None or provider.model != data["model"]:
        return {"status": "control", "reason": "launcher model differs from pinned assessment"}
    try:
        current_route = route_identity(provider.base_url)
    except SettlementError as exc:
        return {"status": "control", "reason": str(exc)}
    if current_route != data["route_identity"]:
        return {"status": "control", "reason": "launcher route differs from pinned assessment"}
    report = gate.run(
        dsn, agent, checker, gate_id=data["gate_id"], epoch=data["epoch"],
        parent=data["parent"], candidate=data["candidate"],
        token_allocation=agenda.read(dsn, campaign_id)["charter"]["allocations"]["tokens"]["id"],
        cpu_allocation=agenda.read(dsn, campaign_id)["charter"]["allocations"]["cpu"]["id"],
        staging_root=staging_root, artifacts_root=artifacts_root,
        route_identity=data["route_identity"],
    )
    return {"status": "unscored" if report["disposition"] == "incomplete" else "assessed",
            "round_id": data["round_id"], "gate": report}


def run(dsn, agent, checker, campaign_id, *, staging_root, artifacts_root,
        max_wakes, wall_seconds):
    if type(max_wakes) is not int or not 0 < max_wakes <= _MAX_WAKES:
        raise SettlementError(f"max_wakes must be an integer in 1..{_MAX_WAKES}")
    if isinstance(wall_seconds, bool) or not isinstance(wall_seconds, (int, float)) \
            or not math.isfinite(wall_seconds) or wall_seconds <= 0:
        raise SettlementError("wall_seconds must be finite and positive")
    end = time.monotonic() + float(wall_seconds)
    initial = agenda.read(dsn, campaign_id)
    if initial is None:
        raise SettlementError("unknown campaign " + campaign_id)
    _, protocol = _load_protocol(dsn, initial, artifacts_root)
    results = []
    for _ in range(max_wakes):
        if time.monotonic() >= end:
            return {"status": "deadline", "results": results}
        state = agenda.read(dsn, campaign_id)
        if state["status"] in {"suspended", "stopped"}:
            return {"status": state["status"], "revision": state["revision"], "results": results}
        pending = _pending(dsn, campaign_id)
        if pending is not None:
            outcome = _run_assignment(dsn, campaign_id, pending, agent, checker,
                                      staging_root, artifacts_root)
            results.append(outcome)
            if outcome["status"] in {"unscored", "control"}:
                return {**outcome, "results": results}
            continue
        assigned = agenda.export(dsn, campaign_id)["decisions"]
        assigned_rounds = {row["data"].get("round_id") for row in assigned
                           if row["kind"] == "p10.assessment.assignment"}
        due = next((item for item in protocol["rounds"] if item["id"] not in assigned_rounds
                    and item["after_turn"] <= state["turns"]), None)
        if due is not None:
            if _deadline_passed(state["charter"]):
                return {"status": "deadline", "revision": state["revision"], "results": results}
            admitted = _assign_due(dsn, campaign_id, state, protocol)
            if admitted is None:
                current = agenda.read(dsn, campaign_id)
                if current is not None and _pending(dsn, campaign_id) is not None:
                    continue
                if current is not None and _deadline_passed(current["charter"]):
                    return {"status": "deadline", "revision": current["revision"], "results": results}
                results.append({"status": "unchanged", "reason": "revision changed during admission"})
            else:
                results.append({"status": "assigned", "round_id": due["id"]})
            continue
        if state["status"] == "complete":
            return {"status": "complete", "revision": state["revision"], "results": results}
        if _deadline_passed(state["charter"]):
            return {"status": "deadline", "revision": state["revision"], "results": results}
        if state["status"] != "active":
            return {"status": "control", "revision": state["revision"], "results": results}
        outcome = agenda._wake(dsn, agent, checker, campaign_id,
                               staging_root=staging_root, artifacts_root=artifacts_root)
        results.append(outcome)
        if outcome["status"] in {"pending", "deferred", "unchanged", "stale"}:
            return {**outcome, "results": results}
    state = agenda.read(dsn, campaign_id)
    return {"status": "bound", "revision": state["revision"], "results": results}


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _query_rows(dsn, sql, params=()):
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def export(dsn, campaign_id, *, artifacts_root):
    state = agenda.read(dsn, campaign_id)
    if state is None:
        return None
    agenda_export = agenda.export(dsn, campaign_id)
    decisions = _query_rows(
        dsn, "SELECT id,kind,actor,subject,data,created_at FROM rsi_decisions "
        "WHERE subject=%s AND (kind LIKE 'p05.%%' OR kind LIKE 'p10.%%') ORDER BY created_at,id",
        (campaign_id,),
    )
    assignments = [row for row in decisions if row["kind"] == "p10.assessment.assignment"]
    gate_ids = [row["data"]["gate_id"] for row in assignments]
    protocol_digest = state["charter"]["assessment_protocol"]
    protocol_package_bytes = (Path(artifacts_root) / protocol_digest).read_bytes()
    if hashlib.sha256(protocol_package_bytes).hexdigest() != protocol_digest:
        raise SettlementError("assessment protocol artifact digest mismatch during export")
    protocol_package = json.loads(protocol_package_bytes)
    protocol = json.loads(bytes.fromhex(protocol_package["files"]["protocol.json"]))
    gate_decisions, baselines = [], []
    for gate_id in gate_ids:
        final = archive.decision(dsn, "gate:" + gate_id)
        baseline = archive.decision(dsn, "gate-baseline:" + gate_id)
        if final is not None:
            gate_decisions.append({"id": "gate:" + gate_id, **final})
        if baseline is not None:
            baselines.append({"id": "gate-baseline:" + gate_id, **baseline})
    epoch_ids = sorted({row["data"]["epoch"] for row in assignments}
                       | {row["epoch"] for row in protocol["rounds"]})
    gate_runs = _query_rows(
        dsn, "SELECT id,epoch,parent,candidate,created_at FROM rsi_gate_runs WHERE id=ANY(%s) ORDER BY id",
        (gate_ids,),
    ) if gate_ids else []
    epochs = _query_rows(
        dsn, "SELECT digest,tasks,budget,policy,execution,created_at FROM rsi_gate_epochs "
        "WHERE digest=ANY(%s) ORDER BY digest", (epoch_ids,),
    ) if epoch_ids else []
    anchor_exposures = _query_rows(
        dsn, "SELECT identity,task,gate,created_at FROM rsi_anchor_uses "
        "ORDER BY created_at,gate,identity",
    )
    investigation_ids = {item.get("investigation_id") for item in state["charter"]["opportunities"]
                         if item.get("investigation_id")}
    investigation_ids.update(row["data"].get("investigation_id") for row in agenda_export["decisions"]
                             if row["kind"] == "p05.choice")
    investigations = [history for ident in sorted(investigation_ids)
                       if (history := investigation.export(dsn, ident)) is not None]

    operation_ids = set()
    for history in investigations:
        operation_ids.update(effect["id"] for effect in history["unresolved_effects"])
        operation_ids.update(effect["id"] for effect in _query_rows(
            dsn, "SELECT id FROM operations WHERE attempt_id IN "
            "(SELECT id FROM attempts WHERE investigation_id=%s)",
            (history["state"]["investigation_id"],)))
    for assignment in assignments:
        data = assignment["data"]
        epoch = next((item for item in epochs if item["digest"] == data["epoch"]), None)
        if epoch is None:
            continue
        specs = epoch["tasks"]
        for phase, split, subjects in (
            ("val", "val", (data["parent"], data["candidate"])),
            ("anchor", "anchor", (data["parent"], data["candidate"])),
        ):
            for digest, spec in specs.items():
                if spec["split"] == split:
                    operation_ids.update("rsi-gate-" + gate._digest(
                        {"gate": data["gate_id"], "phase": phase, "task": digest,
                         "genome": subject}) for subject in subjects)
        baseline = next((item["data"] for item in baselines if item["subject"] == data["gate_id"]), None)
        for check in (baseline or {}).get("checks", []):
            operation_ids.update((check.get("episode"), check.get("verifier")))
        for digest in (baseline or {}).get("task_ids", []):
            operation_ids.add("rsi-gate-" + gate._digest(
                {"gate": data["gate_id"], "phase": "regression", "task": digest,
                 "genome": data["candidate"]}))
        phase_tasks = {
            "val": [digest for digest, spec in specs.items() if spec["split"] == "val"],
            "anchor": [digest for digest, spec in specs.items() if spec["split"] == "anchor"],
            "regression": (baseline or {}).get("task_ids", []),
        }
        for phase, digests in phase_tasks.items():
            subjects = (data["parent"], data["candidate"]) if phase != "regression" else (data["candidate"],)
            for digest in digests:
                for subject in subjects:
                    episode_id = "rsi-gate-" + gate._digest(
                        {"gate": data["gate_id"], "phase": phase, "task": digest,
                         "genome": subject})
                    operation_ids.add(episode_id)
                    evaluator = specs[digest]["evaluator"]
                    operation_ids.add(verifier.operation_id_for(episode_id, evaluator))
    operations = _query_rows(
        dsn, "SELECT id,attempt_id,allocation_id,reservation_id,payload_digest,payload,"
        "dispatch_state,reconcile_state,cancel_state,receipt_provenance,execution_version,settled,created_at "
        "FROM operations WHERE id=ANY(%s) ORDER BY id", (sorted(operation_ids),),
    ) if operation_ids else []
    present_ops = [row["id"] for row in operations]
    receipts = _query_rows(
        dsn, "SELECT receipt_identity,operation_id,content_digest,content,outcome,created_at "
        "FROM receipts WHERE operation_id=ANY(%s) ORDER BY operation_id,receipt_identity",
        (present_ops,),
    ) if present_ops else []
    reservations = _query_rows(
        dsn, "SELECT id,allocation_id,operation_id,amount,state,created_at FROM reservations "
        "WHERE operation_id=ANY(%s) ORDER BY operation_id,id", (present_ops,),
    ) if present_ops else []
    episodes = _query_rows(
        dsn, "SELECT operation_id,genome,task,status,tokens,seconds,trajectory FROM rsi_episodes "
        "WHERE operation_id=ANY(%s) ORDER BY operation_id", (present_ops,),
    ) if present_ops else []
    verdicts = _query_rows(
        dsn, "SELECT episode,evaluator_version,operation_id,solution,status,passed,detail "
        "FROM rsi_verdicts WHERE episode=ANY(%s) OR operation_id=ANY(%s) ORDER BY episode,evaluator_version",
        (present_ops, present_ops),
    ) if present_ops else []
    allocation_ids = {state["charter"]["allocations"][key]["id"] for key in ("tokens", "cpu")}
    allocation_ids.update(row["allocation_id"] for row in operations
                          if row.get("allocation_id"))
    allocation_ids.update(row["allocation_id"] for row in reservations
                          if row.get("allocation_id"))
    allocations = _query_rows(
        dsn, "SELECT id,parent_id,domain,authorized,consumed,reserved,owner_scope FROM allocations "
        "WHERE id=ANY(%s) ORDER BY id", (sorted(allocation_ids),),
    )
    artifact_digests = {protocol_digest}
    artifact_digests.update(item["task_id"] for item in state["charter"]["opportunities"])
    artifact_digests.update(item["genome_id"] for item in state["charter"]["opportunities"])
    for epoch in epochs:
        artifact_digests.update(epoch["tasks"])
    for assignment in assignments:
        artifact_digests.update((assignment["data"]["parent"], assignment["data"]["candidate"]))
    for round_ in protocol["rounds"]:
        artifact_digests.update((round_["parent"], round_["candidate"]))
    for item in episodes:
        artifact_digests.add(item["trajectory"])
    for item in verdicts:
        artifact_digests.add(item["solution"])
    artifact_bytes, artifact_metadata = {}, []
    for digest in sorted(artifact_digests):
        if not digest:
            continue
        with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT digest,manifest,format,version,scope,availability,access_label "
                        "FROM artifact_versions WHERE digest=%s", (digest,))
            metadata = cur.fetchone()
        path = Path(artifacts_root) / digest
        if metadata is not None:
            artifact_metadata.append(dict(metadata))
        if path.is_file():
            raw = path.read_bytes()
            artifact_bytes[digest] = raw.hex()
    package = {
        "schema": _EXPORT_SCHEMA,
        "campaign_id": campaign_id,
        "agenda": agenda_export["agenda"],
        "decisions": decisions,
        "protocol_digest": protocol_digest,
        "gate_decisions": gate_decisions,
        "regression_baselines": baselines,
        "gate_epochs": epochs,
        "gate_runs": gate_runs,
        "anchor_exposures": anchor_exposures,
        "investigations": investigations,
        "operations": operations,
        "receipts": receipts,
        "reservations": reservations,
        "allocations": allocations,
        "episodes": episodes,
        "verdicts": verdicts,
        "artifact_metadata": artifact_metadata,
        "artifact_bytes": artifact_bytes,
    }
    return _plain(package)


def _clean_receipt(operation_id, operations, receipts, unresolved, problems):
    operation = operations.get(operation_id)
    found = receipts.get(operation_id, [])
    if operation is None:
        problems.append(f"required operation is missing: {operation_id}")
        return None
    if (not operation.get("settled")
            or operation.get("dispatch_state") not in {"observed", "reconciled"}
            or operation.get("reconcile_state") in {"conflict", "unresolved"}):
        unresolved.append(operation_id)
        return None
    if len(found) != 1:
        problems.append(f"settled operation has no unique receipt: {operation_id}")
        return None
    if found[0].get("outcome") not in {"success", "failure"}:
        unresolved.append(operation_id)
        return None
    receipt = found[0]
    if payload_digest(receipt.get("content", {})) != receipt.get("content_digest"):
        return None
    return receipt


def _receipt_test_result(receipt):
    if receipt is None:
        return None
    content = receipt.get("content")
    if (not isinstance(content, dict) or content.get("parse") != "typed-json"
            or content.get("truncated") is not False
            or content.get("_verdict") not in {"success", "failure"}):
        return None
    data = content.get("data", {})
    if not isinstance(data, dict) or data.get("timed_out") is not False:
        return None
    worker = data.get("worker", {})
    report = worker.get("data", {}) if isinstance(worker, dict) else {}
    counts = [report.get(key) for key in ("tests", "failures", "errors", "skipped")]
    if (not isinstance(worker, dict) or worker.get("status") not in {"ok", "error"}
            or any(type(value) is not int or value < 0 for value in counts)
            or counts[0] <= 0 or counts[0] - counts[3] <= 0):
        return None
    passed = worker["status"] == "ok" and counts[1:] == [0, 0, 0]
    if content["_verdict"] != ("success" if passed else "failure"):
        return None
    return {"status": "passed" if passed else "failed", "passed": passed}


def _artifact_package(digest, artifact_bytes, metadata, problems):
    raw_hex = artifact_bytes.get(digest)
    if not isinstance(raw_hex, str):
        problems.append(f"required artifact bytes are missing: {digest}")
        return None, {}
    try:
        raw = bytes.fromhex(raw_hex)
        package = json.loads(raw)
        files = {path: bytes.fromhex(value) for path, value in package["files"].items()}
        manifest, scope = package["manifest"], package["scope"]
        if hashlib.sha256(raw).hexdigest() != digest:
            problems.append(f"artifact digest mismatch: {digest}")
        if artifacts.package_bytes(manifest, files, scope) != raw:
            problems.append(f"artifact package encoding mismatch: {digest}")
        meta = metadata.get(digest)
        if meta is None:
            problems.append(f"required artifact metadata is missing: {digest}")
        elif (meta.get("digest") != digest or meta.get("scope") != scope
              or meta.get("manifest") != manifest):
            problems.append(f"artifact manifest mismatch: {digest}")
        entries = manifest.get("files", []) if isinstance(manifest, dict) else []
        expected_paths = {item.get("path") for item in entries if item.get("kind", "file") != "dir"}
        if expected_paths != set(files):
            problems.append(f"artifact file coverage mismatch: {digest}")
        for entry in entries:
            path = entry.get("path")
            if path in files and (len(files[path]) != entry.get("size")
                                  or hashlib.sha256(files[path]).hexdigest() != entry.get("digest")):
                problems.append(f"artifact file digest mismatch: {digest}:{path}")
        return package, files
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        problems.append(f"artifact package is invalid: {digest}")
        return None, {}


def _task_content_identity(package, files):
    manifest = package.get("manifest", {}) if package else {}
    if manifest.get("kind") != task.SCOPE:
        return None
    groups = {}
    for kind in ("workspace", "verifier", "reference"):
        prefix = kind + "/"
        groups[kind] = {path[len(prefix):]: raw.hex() for path, raw in files.items()
                        if path.startswith(prefix)}
    return gate._digest({"instruction": manifest.get("instruction"), **groups})


def _derived_result(episode_id, evaluator, operations, receipts, episodes,
                    verdicts, unresolved, problems):
    _clean_receipt(episode_id, operations, receipts, unresolved, problems)
    verifier_id = verifier.operation_id_for(episode_id, evaluator)
    receipt = _clean_receipt(verifier_id, operations, receipts, unresolved, problems)
    known = _receipt_test_result(receipt)
    episode = episodes.get(episode_id)
    verdict = verdicts.get((episode_id, evaluator))
    if episode is None:
        problems.append(f"required episode is missing: {episode_id}")
        known = None
    elif episode.get("status") != "completed":
        unresolved.append(episode_id)
        known = None
    if receipt is not None and known is None:
        unresolved.append(verifier_id)
    if (verdict is None or verdict.get("operation_id") != verifier_id
            or verdict.get("detail") != (receipt or {}).get("content")):
        known = None
    if known is not None and (verdict.get("status") != known["status"]
                              or verdict.get("passed") is not known["passed"]):
        known = None
    return known, verifier_id


def _expected_gate_operation(gate_id, phase, digest, subject):
    return "rsi-gate-" + gate._digest(
        {"gate": gate_id, "phase": phase, "task": digest, "genome": subject})


def _check_baseline(gate_id, parent, baseline, operations, receipts, episodes,
                    verdicts, unresolved, problems):
    if not isinstance(baseline, dict) or not isinstance(baseline.get("checks"), list):
        problems.append(f"historical regression baseline is missing: {gate_id}")
        return None
    solved = set()
    for check in baseline["checks"]:
        episode_id, evaluator = check.get("episode"), check.get("evaluator_version")
        valid_ids = isinstance(episode_id, str) and isinstance(evaluator, str)
        derived, verifier_id = _derived_result(
            episode_id, evaluator, operations, receipts, episodes, verdicts,
            unresolved, problems,
        ) if valid_ids else (None, None)
        episode = episodes.get(episode_id)
        verdict = verdicts.get((episode_id, evaluator))
        if (not valid_ids or check.get("genome") != parent
                or not isinstance(check.get("task"), str)
                or verifier_id != check.get("verifier") or episode is None
                or episode.get("genome") != parent or episode.get("task") != check.get("task")
                or episode.get("trajectory") != check.get("trajectory")
                or verdict is None or verdict.get("solution") != check.get("solution")
                or derived is None or derived["passed"] is not True
                or check.get("passed") is not True or check.get("status") != "passed"):
            problems.append(f"historical regression evidence is inconsistent: {gate_id}")
        else:
            solved.add(check["task"])
    task_ids = sorted(solved)
    if baseline.get("task_ids") != task_ids:
        problems.append(f"historical regression task set changed: {gate_id}")
    return task_ids


def _phase_outcomes(report, phase, expected, epoch, assignment, operations,
                    receipts, episodes, verdicts, unresolved, problems):
    phases = report.get("phases")
    if not isinstance(phases, dict):
        problems.append(f"gate phase table is invalid: {assignment['gate_id']}")
        return None
    rows = phases.get(phase)
    if not isinstance(rows, list):
        problems.append(f"gate phase is missing: {assignment['gate_id']}:{phase}")
        rows = []
    observed = [(row.get("task"), row.get("genome")) for row in rows
                if isinstance(row, dict)]
    if observed != expected:
        problems.append(f"gate phase coverage differs: {assignment['gate_id']}:{phase}")
    outcomes = {}
    for digest, subject in expected:
        episode_id = _expected_gate_operation(assignment["gate_id"], phase, digest, subject)
        evaluator = epoch["tasks"][digest]["evaluator"]
        derived, verifier_id = _derived_result(
            episode_id, evaluator, operations, receipts, episodes, verdicts,
            unresolved, problems,
        )
        episode = episodes.get(episode_id)
        if (episode is None or episode.get("genome") != subject
                or episode.get("task") != digest or episode.get("status") != "completed"):
            problems.append(f"gate episode identity differs: {episode_id}")
        row = next((item for item in rows if isinstance(item, dict)
                    and item.get("task") == digest and item.get("genome") == subject), None)
        verdict = verdicts.get((episode_id, evaluator))
        if row is None:
            problems.append(f"gate phase evidence row is missing: {episode_id}")
        elif (row.get("episode") != episode_id or row.get("verdict") != verifier_id
              or derived is None or row.get("status") != derived["status"]
              or row.get("passed") is not derived["passed"]):
            problems.append(f"gate phase verdict differs from pristine receipt: {episode_id}")
        if (verdict is None or verdict.get("operation_id") != verifier_id
                or verdict.get("episode") != episode_id
                or verdict.get("evaluator_version") != evaluator):
            problems.append(f"gate verifier record is missing: {episode_id}")
        if derived is not None:
            outcomes[(digest, subject)] = derived["passed"]
    return outcomes if len(outcomes) == len(expected) else None


def _alpha_matches_exposure(alpha, gate_id, exposures):
    groups = {}
    for item in exposures:
        groups.setdefault(item.get("gate"), []).append(item)
    target = groups.get(gate_id, [])
    if not target:
        return False
    try:
        times = {datetime.fromisoformat(item["created_at"]) for item in target}
        if len(times) != 1:
            return False
        created = next(iter(times))
        gate_times = {}
        for other, rows in groups.items():
            parsed = {datetime.fromisoformat(item["created_at"]) for item in rows}
            if len(parsed) != 1:
                return False
            gate_times[other] = next(iter(parsed))
    except (KeyError, TypeError, ValueError):
        return False
    before = sum(value < created for other, value in gate_times.items() if other != gate_id)
    tied = sum(value == created for value in gate_times.values())
    return any(math.isclose(float(alpha), 0.05 / (index * (index + 1)),
                            rel_tol=0, abs_tol=1e-15)
               for index in range(before + 1, before + tied + 1))


def recompute(bundle):
    """Derive comparison outcomes from an export, without a database or route."""
    problems, unresolved = [], []
    try:
        data, _ = _canonical(bundle)
    except SettlementError as exc:
        return {"status": "tampered", "comparison_gain": False, "problems": [str(exc)]}
    if not isinstance(data, dict) or data.get("schema") != _EXPORT_SCHEMA:
        return {"status": "tampered", "comparison_gain": False,
                "problems": ["unsupported export schema"]}
    agenda_data = data.get("agenda", {})
    campaign_id = data.get("campaign_id")
    charter = agenda_data.get("charter", {})
    protocol_digest = data.get("protocol_digest")
    if (campaign_id != agenda_data.get("agenda_id")
            or charter.get("assessment_protocol") != protocol_digest):
        problems.append("campaign or protocol identity drift")

    artifact_bytes = data.get("artifact_bytes", {})
    metadata = {row.get("digest"): row for row in data.get("artifact_metadata", [])}
    packages, package_files = {}, {}
    for digest in artifact_bytes:
        packages[digest], package_files[digest] = _artifact_package(
            digest, artifact_bytes, metadata, problems)
    protocol = None
    package = packages.get(protocol_digest)
    try:
        if package is None or package.get("scope") != "rsi-assessment-protocol":
            raise ValueError("missing protocol package")
        protocol_raw = package_files[protocol_digest]["protocol.json"]
        protocol, canonical = _parse_protocol(json.loads(protocol_raw), charter["max_turns"])
        if canonical != protocol_raw:
            raise ValueError("noncanonical protocol")
    except (ValueError, KeyError, TypeError, SettlementError, json.JSONDecodeError):
        problems.append("protocol artifact identity mismatch")
        protocol = None

    assignments = [row for row in data.get("decisions", [])
                   if row.get("kind") == "p10.assessment.assignment"]
    rounds = {item.get("id"): item for item in (protocol or {}).get("rounds", [])}
    assignments_by_round = {}
    for row in assignments:
        item = row.get("data", {})
        round_id = item.get("round_id")
        round_ = rounds.get(round_id)
        if (row.get("id") != (_assignment_id(campaign_id, round_id)
                              if isinstance(round_id, str) else "")
                or item.get("agenda_id") != campaign_id
                or item.get("gate_id") != (_gate_id(campaign_id, round_id)
                                           if isinstance(round_id, str) else "")
                or item.get("protocol_digest") != protocol_digest
                or round_ is None
                or any(item.get(key) != round_.get(key)
                       for key in ("after_turn", "epoch", "parent", "candidate", "model", "route_identity"))):
            problems.append(f"assessment assignment identity drift: {round_id}")
        if round_id in assignments_by_round:
            problems.append(f"duplicate assessment assignment: {round_id}")
        assignments_by_round[round_id] = item

    decision_rows = data.get("gate_decisions", [])
    decisions = {row.get("id"): row for row in decision_rows}
    epochs = {row.get("digest"): row for row in data.get("gate_epochs", [])}
    run_rows = data.get("gate_runs", [])
    runs = {row.get("id"): row for row in run_rows}
    baseline_rows = data.get("regression_baselines", [])
    baselines = {row.get("subject"): row.get("data", {}) for row in baseline_rows}
    if len(decisions) != len(decision_rows) or len(runs) != len(run_rows) or len(baselines) != len(baseline_rows):
        problems.append("duplicate gate evidence identity")
    operations_list = data.get("operations", [])
    operations = {row.get("id"): row for row in operations_list}
    receipt_rows = {}
    for row in data.get("receipts", []):
        receipt_rows.setdefault(row.get("operation_id"), []).append(row)
    episodes_list = data.get("episodes", [])
    episode_rows = {row.get("operation_id"): row for row in episodes_list}
    verdicts_list = data.get("verdicts", [])
    verdict_rows = {(row.get("episode"), row.get("evaluator_version")): row
                    for row in verdicts_list}
    if (len(operations) != len(operations_list) or len(episode_rows) != len(episodes_list)
            or len(verdict_rows) != len(verdicts_list)):
        problems.append("duplicate operation, episode or verdict identity")

    for operation_id in operations:
        _clean_receipt(operation_id, operations, receipt_rows, unresolved, problems)
    for operation_id, found in receipt_rows.items():
        if len(found) == 1 and payload_digest(found[0].get("content", {})) != found[0].get("content_digest"):
            problems.append(f"operation receipt digest is invalid: {operation_id}")
    for history in data.get("investigations", []):
        for effect in history.get("unresolved_effects", []):
            _clean_receipt(effect.get("id"), operations, receipt_rows,
                           unresolved, problems)

    for row in episodes_list:
        operation_id = row.get("operation_id")
        if row.get("status") != "completed" and isinstance(operation_id, str):
            unresolved.append(operation_id)
    for row in verdicts_list:
        if (row.get("status") not in {"passed", "failed"}
                or type(row.get("passed")) is not bool):
            operation_id = row.get("operation_id")
            if isinstance(operation_id, str):
                unresolved.append(operation_id)

    for digest, epoch in epochs.items():
        identity = {key: epoch.get(key) for key in ("tasks", "budget", "policy", "execution")}
        if gate._digest(identity) != digest or epoch.get("policy") != gate.POLICY:
            problems.append(f"gate epoch identity drift: {digest}")
        for task_digest, spec in (epoch.get("tasks") or {}).items():
            task_package = packages.get(task_digest)
            manifest = task_package.get("manifest", {}) if task_package else {}
            if (task_package is None or task_package.get("scope") != task.SCOPE
                    or manifest.get("split") != spec.get("split")
                    or manifest.get("evaluator_version") != spec.get("evaluator")):
                problems.append(f"gate task identity drift: {task_digest}")

    required_artifacts = {protocol_digest}
    required_artifacts.update(item.get("task_id") for item in charter.get("opportunities", []))
    required_artifacts.update(item.get("genome_id") for item in charter.get("opportunities", []))
    for epoch in epochs.values():
        required_artifacts.update((epoch.get("tasks") or {}).keys())
    for round_ in (protocol or {}).get("rounds", []):
        required_artifacts.update((round_.get("parent"), round_.get("candidate")))
        if round_.get("epoch") not in epochs:
            problems.append(f"protocol gate epoch is missing: {round_.get('epoch')}")
    for item in assignments_by_round.values():
        required_artifacts.update((item.get("parent"), item.get("candidate")))
    for row in episodes_list:
        required_artifacts.add(row.get("trajectory"))
    for row in verdicts_list:
        required_artifacts.add(row.get("solution"))
    required_artifacts.discard(None)
    for digest in required_artifacts:
        if digest not in packages:
            problems.append(f"required artifact bytes are missing: {digest}")
    task_identities = {
        digest: _task_content_identity(packages.get(digest), package_files.get(digest, {}))
        for digest in required_artifacts
    }
    exposures = data.get("anchor_exposures", [])
    exposures_by_gate = {}
    for item in exposures:
        exposures_by_gate.setdefault(item.get("gate"), []).append(item)

    derived_dispositions = {}
    for round_id, assignment in assignments_by_round.items():
        gate_id = assignment.get("gate_id")
        final_id = "gate:" + str(gate_id)
        decision = decisions.get(final_id)
        if decision is None:
            continue
        report = decision.get("data", {})
        epoch = epochs.get(assignment.get("epoch"))
        run = runs.get(gate_id)
        if (decision.get("kind") != "gate" or decision.get("subject") != assignment.get("candidate")
                or any(report.get(key) != assignment.get(key)
                       for key in ("epoch", "parent", "candidate", "route_identity"))):
            problems.append(f"final gate identity drift: {gate_id}")
        if run is None:
            problems.append(f"final gate has no run record: {gate_id}")
        elif any(run.get(key) != assignment.get(key) for key in ("epoch", "parent", "candidate")):
            problems.append(f"gate run identity drift: {gate_id}")
        if report.get("disposition") == "incomplete":
            problems.append(f"incomplete gate was archived: {gate_id}")
            continue
        if epoch is None:
            continue
        specs = epoch.get("tasks", {})
        val_tasks = sorted(d for d, spec in specs.items() if spec.get("split") == "val")
        anchor_tasks = sorted(d for d, spec in specs.items() if spec.get("split") == "anchor")
        declarations = report.get("execution", [])
        refuses_containment = (epoch.get("execution") == "contained" and any(
            item.get("containment") is not True or item.get("network") != "none"
            for item in declarations if isinstance(item, dict)))
        if report.get("disposition") == "blocked" and refuses_containment and not report.get("phases"):
            if exposures_by_gate.get(gate_id):
                problems.append(f"blocked gate has anchor exposure: {gate_id}")
            derived_dispositions[gate_id] = "blocked"
            continue
        val_expected = [(d, genome_id) for d in val_tasks
                        for genome_id in (assignment["parent"], assignment["candidate"])]
        val = _phase_outcomes(report, "val", val_expected, epoch, assignment, operations,
                              receipt_rows, episode_rows, verdict_rows, unresolved, problems)
        expected_phases = {"val"}
        expected_disposition = None
        if val is not None:
            old_score = sum(val[(d, assignment["parent"])] for d in val_tasks)
            new_score = sum(val[(d, assignment["candidate"])] for d in val_tasks)
            if new_score < old_score:
                expected_disposition = "quarantine"
                if gate_id in baselines or report.get("regression_baseline"):
                    problems.append(f"validation quarantine has unexpected regression baseline: {gate_id}")
            else:
                baseline = baselines.get(gate_id)
                solved = _check_baseline(gate_id, assignment["parent"], baseline, operations,
                                         receipt_rows, episode_rows, verdict_rows, unresolved, problems)
                if solved is not None:
                    if report.get("regression_baseline") != baseline.get("checks"):
                        problems.append(f"gate regression baseline differs: {gate_id}")
                    expected_phases.add("regression")
                    regression_expected = [(d, assignment["candidate"]) for d in solved]
                    regression = _phase_outcomes(
                        report, "regression", regression_expected, epoch, assignment,
                        operations, receipt_rows, episode_rows, verdict_rows, unresolved, problems)
                    if regression is not None and not all(regression.values()):
                        expected_disposition = "quarantine"
                    elif regression is not None:
                        reserved = exposures_by_gate.get(gate_id, [])
                        expected_ids = {task_identities.get(d) for d in anchor_tasks}
                        actual_ids = {item.get("identity") for item in reserved}
                        exact_exposure = (None not in expected_ids and actual_ids == expected_ids
                                          and {item.get("task") for item in reserved} == set(anchor_tasks))
                        if not exact_exposure:
                            collisions = [item for item in exposures
                                          if item.get("identity") in expected_ids
                                          and item.get("gate") != gate_id]
                            if collisions and not reserved:
                                expected_disposition = "blocked"
                            else:
                                problems.append(f"anchor exposure evidence differs: {gate_id}")
                        else:
                            expected_phases.add("anchor")
                            anchor_expected = [(d, genome_id) for d in anchor_tasks
                                               for genome_id in (assignment["parent"], assignment["candidate"])]
                            anchor = _phase_outcomes(
                                report, "anchor", anchor_expected, epoch, assignment,
                                operations, receipt_rows, episode_rows, verdict_rows,
                                unresolved, problems)
                            comparison = report.get("anchor_comparison", {})
                            alpha = comparison.get("alpha") if isinstance(comparison, dict) else None
                            if (type(alpha) not in (int, float) or not 0 < alpha < 1
                                    or not _alpha_matches_exposure(alpha, gate_id, exposures)):
                                problems.append(f"anchor alpha is unsupported by exposure history: {gate_id}")
                                anchor = None
                            if anchor is not None:
                                old = tuple(anchor[(d, assignment["parent"])] for d in anchor_tasks)
                                new = tuple(anchor[(d, assignment["candidate"])] for d in anchor_tasks)
                                reconstructed = gate.paired_verdict(old, new, float(alpha))
                                if comparison != reconstructed:
                                    problems.append(f"paired anchor verdict differs from receipt outcomes: {gate_id}")
                                accepted = "promote" if epoch.get("execution") == "contained" else "experimental_gain"
                                expected_disposition = accepted if reconstructed["promote"] else "quarantine"
        if expected_disposition is None and report.get("disposition") == "blocked":
            declarations = report.get("execution", [])
            refuses_containment = (epoch.get("execution") == "contained" and any(
                item.get("containment") is not True or item.get("network") != "none"
                for item in declarations if isinstance(item, dict)))
            if refuses_containment and not report.get("phases"):
                expected_disposition = "blocked"
                expected_phases = set()
        if expected_disposition is not None:
            derived_dispositions[gate_id] = expected_disposition
            if report.get("disposition") != expected_disposition:
                problems.append(f"gate disposition differs from derived evidence: {gate_id}")
            if set(report.get("phases", {})) != expected_phases:
                problems.append(f"gate phase set differs from derived progression: {gate_id}")
            if "anchor" not in expected_phases and exposures_by_gate.get(gate_id):
                problems.append(f"gate reserved anchors before its comparison phase: {gate_id}")

    assigned_gates = {item.get("gate_id") for item in assignments_by_round.values()}
    for gate_id in runs:
        if gate_id not in assigned_gates:
            problems.append(f"unassigned gate run: {gate_id}")
    for decision_id in decisions:
        gate_id = decision_id.removeprefix("gate:")
        if gate_id not in assigned_gates:
            problems.append(f"unassigned gate decision: {gate_id}")
    historical_operations = {
        operation_id
        for baseline in baseline_rows
        for check in (baseline.get("data", {}).get("checks", []) or [])
        for operation_id in (check.get("episode"), check.get("verifier"))
        if isinstance(operation_id, str)
    }
    resource_units = _resource_totals(
        data.get("allocations", []), data.get("reservations", []), operations,
        charter, campaign_id, historical_operations, problems,
    )
    complete = (not problems and not unresolved and set(assignments_by_round) == set(rounds)
                and all("gate:" + item["gate_id"] in decisions
                        for item in assignments_by_round.values()))
    comparison_gain = bool(complete and any(value in {"promote", "experimental_gain"}
                                            for value in derived_dispositions.values()))
    return {"status": "consistent" if complete else "incomplete" if not problems else "tampered",
            "comparison_gain": comparison_gain, "learning_gain": False,
            "limitations": ["offline evidence cannot authenticate provider, wall time or compute attestations",
                            "comparison outcomes do not establish transfer or improved learning",
                            "resource units include exported historical regression support, not only campaign spend"],
            "problems": problems, "unresolved_operations": sorted(set(unresolved)),
            "resource_units": resource_units}


def _resource_totals(allocations, reservations, operations, charter, campaign_id,
                     historical_operations, problems):
    if not isinstance(allocations, list) or not isinstance(reservations, list):
        problems.append("resource allocation or reservation evidence is missing")
        return None
    first_problem = len(problems)
    allocation_rows = {}
    for row in allocations:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) \
                or row["id"] in allocation_rows:
            problems.append("allocation evidence identity is invalid or duplicated")
            continue
        allocation_rows[row["id"]] = row
    reservation_rows = {}
    for row in reservations:
        operation_id = row.get("operation_id") if isinstance(row, dict) else None
        if not isinstance(operation_id, str):
            problems.append("reservation evidence has no operation identity")
            continue
        reservation_rows.setdefault(operation_id, []).append(row)
    if len(reservation_rows) != len(reservations):
        problems.append("reservation evidence has a duplicate operation identity")

    totals = {"tokens": {"reserved": 0, "settled": 0, "uncertain": 0, "released": 0},
              "cpu": {"reserved": 0, "settled": 0, "uncertain": 0, "released": 0}}
    roots = charter.get("allocations", {}) if isinstance(charter, dict) else {}
    root_ids = {}
    for domain in ("tokens", "cpu"):
        root = roots.get(domain) if isinstance(roots, dict) else None
        root_ids[domain] = root.get("id") if isinstance(root, dict) else None
    allowed_scopes = {""}
    if isinstance(campaign_id, str):
        allowed_scopes.add(campaign_id)
        allowed_scopes.add("rsi-agenda:" + campaign_id)
    for domain, allocation_id in root_ids.items():
        allocation = allocation_rows.get(allocation_id) if isinstance(allocation_id, str) else None
        owner_scope = (allocation.get("owner_scope") or "") if allocation else None
        root = roots.get(domain) if isinstance(roots, dict) else None
        units = root.get("units") if isinstance(root, dict) else None
        if (not isinstance(allocation_id, str) or allocation is None
                or allocation.get("domain") != domain or allocation.get("parent_id") is not None
                or owner_scope not in allowed_scopes or type(units) is not int
                or type(allocation.get("authorized")) is not int
                or allocation["authorized"] < units):
            problems.append(f"campaign {domain} allocation root evidence is missing or invalid")

    for operation_id, operation in operations.items():
        linked = reservation_rows.get(operation_id, [])
        reservation_id = operation.get("reservation_id")
        expected_reservation_id = "res-" + operation_id if isinstance(operation_id, str) else None
        if (len(linked) != 1 or reservation_id != expected_reservation_id
                or linked[0].get("id") != reservation_id):
            problems.append(f"operation has no unique required reservation: {operation_id}")
            continue
        reservation = linked[0]
        allocation_id = operation.get("allocation_id")
        if reservation.get("allocation_id") != allocation_id:
            problems.append(f"operation reservation allocation differs: {operation_id}")
            continue
        allocation = allocation_rows.get(allocation_id) if isinstance(allocation_id, str) else None
        if allocation is None or allocation.get("parent_id") is not None:
            problems.append(f"operation allocation root is missing or invalid: {operation_id}")
            continue

        envelope = operation.get("payload")
        effect = envelope.get("effect") if isinstance(envelope, dict) else None
        effect_payload = envelope.get("payload") if isinstance(envelope, dict) else None
        try:
            prepared = {key: value for key, value in envelope.items()
                        if not key.startswith("_")} if isinstance(envelope, dict) else None
            if prepared is None or payload_digest(prepared) != operation.get("payload_digest"):
                problems.append(f"operation payload digest differs from effect evidence: {operation_id}")
            expected_domain = {broker.AGENT_RUN: "tokens", broker.SANDBOX_EXEC: "cpu"}.get(effect)
            retries = envelope.get("retries", 0)
            if (expected_domain is None or not isinstance(effect_payload, dict)
                    or isinstance(retries, bool) or not isinstance(retries, int) or retries < 0):
                raise ValueError("unsupported operation effect")
            expected_amount, _ = broker.exposure_schedule(effect, effect_payload, retries)
        except (KeyError, TypeError, ValueError):
            problems.append(f"operation resource effect is invalid: {operation_id}")
            continue
        if allocation.get("domain") != expected_domain:
            problems.append(f"operation allocation domain differs from effect: {operation_id}")
        if (type(allocation.get("authorized")) is not int
                or allocation["authorized"] < expected_amount):
            problems.append(f"operation allocation does not authorize its reservation: {operation_id}")
        if (operation_id not in historical_operations
                and allocation_id != root_ids.get(expected_domain)):
            problems.append(f"operation allocation differs from campaign root: {operation_id}")
        amount = reservation.get("amount")
        if type(amount) is not int or amount != expected_amount:
            problems.append(f"operation reservation amount differs from effect: {operation_id}")
        state = reservation.get("state")
        known_settlement = (operation.get("settled") is True
                            and operation.get("dispatch_state") in ("observed", "reconciled")
                            and operation.get("reconcile_state") not in ("conflict", "unresolved"))
        released = (state == "released" and operation.get("cancel_state") == "confirmed"
                    and operation.get("dispatch_state") in ("cancelled", "reconciled")
                    and operation.get("reconcile_state") == "reconciled")
        if ((known_settlement and state != "settled")
                or (not known_settlement and state not in ("reserved", "uncertain") and not released)):
            problems.append(f"operation reservation state differs from settlement: {operation_id}")
        if isinstance(state, str) and state in totals[expected_domain]:
            totals[expected_domain][state] += amount if type(amount) is int else 0

    if any(operation_id not in operations for operation_id in reservation_rows):
        problems.append("reservation evidence has no matching operation")
    return None if len(problems) != first_problem else totals


def _read_route(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    required = {"SETTLEMENT_GATEWAY_ENDPOINT", "SETTLEMENT_GATEWAY_MODEL", "SETTLEMENT_GATEWAY_KEY"}
    if required - values.keys():
        raise SettlementError("route file is missing gateway endpoint, model or key")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "run", "inspect", "suspend", "resume",
                                             "stop", "export", "recompute"))
    parser.add_argument("--dsn")
    parser.add_argument("--id")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--charter", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--route-file", type=Path)
    parser.add_argument("--codex")
    parser.add_argument("--max-wakes", type=int, default=8)
    parser.add_argument("--wall-seconds", type=float, default=300.0)
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args(argv)
    if args.command == "recompute":
        if args.bundle is None:
            parser.error("recompute requires --bundle")
        result = recompute(json.loads(args.bundle.read_text(encoding="utf-8")))
    else:
        if not args.dsn or not args.id:
            parser.error("this command requires --dsn and --id")
        root = args.root
        if root is None:
            parser.error("this command requires --root")
        roots = {"staging_root": root / "stage", "artifacts_root": root / "art"}
        if args.command == "start":
            if args.charter is None or args.protocol is None:
                parser.error("start requires --charter and --protocol")
            result = start(args.dsn, campaign_id=args.id,
                           charter=json.loads(args.charter.read_text(encoding="utf-8")),
                           protocol=json.loads(args.protocol.read_text(encoding="utf-8")), **roots)
        elif args.command == "run":
            if args.route_file is None or not args.codex:
                parser.error("run requires --route-file and --codex")
            route = _read_route(args.route_file)
            provider = Provider(route["SETTLEMENT_GATEWAY_ENDPOINT"],
                                route["SETTLEMENT_GATEWAY_MODEL"],
                                route["SETTLEMENT_GATEWAY_KEY"])
            agent = CodexLauncher(root / "runs", codex_cmd=[args.codex], provider=provider,
                                  allowed_overrides=genome.HARNESS_KEYS)
            checker = LocalLauncher(root / "verifiers")
            result = run(args.dsn, agent, checker, args.id, **roots,
                         max_wakes=args.max_wakes, wall_seconds=args.wall_seconds)
        elif args.command == "inspect":
            result = inspect(args.dsn, args.id)
        elif args.command in {"suspend", "resume", "stop"}:
            if args.expected_revision is None:
                parser.error(f"{args.command} requires --expected-revision")
            result = {"suspend": suspend, "resume": resume, "stop": stop}[args.command](
                args.dsn, args.id, args.expected_revision)
        elif args.command == "export":
            result = export(args.dsn, args.id, artifacts_root=roots["artifacts_root"])
        else:
            parser.error("unsupported command")
    encoded = json.dumps(_plain(result), sort_keys=True, separators=(",", ":"))
    if args.command == "export" and args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
