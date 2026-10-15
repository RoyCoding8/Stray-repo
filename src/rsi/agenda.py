"""Bounded P05 portfolio runtime.

Charter shape: ``{grant_version, objective, allocations:{tokens:{id,units},
cpu:{id,units}}, policy, max_turns, deadline, opportunities:[{id, task_id,
genome_id, investigation_id?, objective, question, priority,
resource_ceilings:{tokens,cpu}, timeout_ms, max_steps, expected_observation,
stop_condition, method_request?:{name,interface,value}, scope_probe?:
{source_opportunity_id,lesson_refs:[{claim_id,version}],changed_condition,
competing_explanations}}]}``. Task IDs are canonical Task.digest values. CPU ceilings
are broker allocation units; timeout_ms is a separate per-opportunity bound.

One immutable agenda row owns its finite catalogue, explicitly granted shared
token/CPU roots, turn cap, both source clocks, and at most one persisted flight.
P01 owns each investigation. Choices precede P01 calls; acknowledgements name
the exact decision, attempt, operation, checked outcome and settled receipts.
Only learner-visible sources count; timeouts and labels are not learning evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from psycopg.rows import dict_row
from psycopg.types.json import Json

from settlement import broker, db, store
from settlement.common import Command, ResultCode, SettlementError, StaleRevision

from . import agenda_policy, capability, genome, investigate, investigation, memory, task, verifier

_MAX_OPTIONS = 64
_MAX_TURNS = 100


def _json(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > 262_144:
            raise ValueError("charter exceeds 262144 bytes")
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SettlementError(f"charter must be bounded finite JSON: {exc}") from exc


def _positive(value, name, maximum=2**31 - 1):
    if type(value) is not int or not 0 < value <= maximum:
        raise SettlementError(f"{name} must be a positive integer <= {maximum}")
    return value


def _parse(charter):
    required = {"grant_version", "objective", "allocations", "policy", "max_turns",
                "deadline", "opportunities"}
    if not isinstance(charter, dict) or required - charter.keys():
        raise SettlementError("charter is missing required fields")
    if charter["policy"] not in {"seed/1", "adaptive/1"}:
        raise SettlementError("policy must be seed/1 or adaptive/1")
    if not isinstance(charter["objective"], str) or not charter["objective"].strip():
        raise SettlementError("objective must be non-empty")
    _positive(charter["grant_version"], "grant_version")
    _positive(charter["max_turns"], "max_turns", _MAX_TURNS)
    try:
        deadline = datetime.fromisoformat(charter["deadline"])
    except (AttributeError, ValueError) as exc:
        raise SettlementError("deadline must be an ISO-8601 UTC timestamp") from exc
    if deadline.tzinfo is None or deadline.utcoffset().total_seconds() != 0:
        raise SettlementError("deadline must be UTC")
    roots = charter["allocations"]
    if not isinstance(roots, dict) or set(roots) != {"tokens", "cpu"}:
        raise SettlementError("allocations must name token and CPU roots")
    for domain, root in roots.items():
        if not isinstance(root, dict) or not isinstance(root.get("id"), str) or not root["id"].strip():
            raise SettlementError(f"{domain} allocation needs an id")
        _positive(root.get("units"), f"{domain} allocation units")
    items = charter["opportunities"]
    if not isinstance(items, list) or not 0 < len(items) <= _MAX_OPTIONS:
        raise SettlementError(f"opportunities must contain 1..{_MAX_OPTIONS} entries")
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise SettlementError("each opportunity must be an object")
        for key in ("id", "task_id", "genome_id", "objective", "question",
                    "expected_observation", "stop_condition"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise SettlementError(f"opportunity {key} must be non-empty")
        if item["id"] in ids:
            raise SettlementError("opportunity ids must be unique")
        ids.add(item["id"])
        _positive(item.get("priority"), "priority")
        limits = item.get("resource_ceilings")
        if not isinstance(limits, dict) or set(limits) != {"tokens", "cpu"}:
            raise SettlementError("resource_ceilings must name token and CPU units")
        for domain, amount in limits.items():
            _positive(amount, f"resource_ceilings.{domain}")
        _positive(item.get("timeout_ms"), "timeout_ms", 300_000)
        _positive(item.get("max_steps"), "max_steps", _MAX_TURNS)
        method = item.get("method_request")
        if method is not None and (not isinstance(method, dict)
                or set(method) != {"name", "interface", "value"}
                or any(not isinstance(method.get(k), str) or not method[k].strip()
                       for k in ("name", "interface"))):
            raise SettlementError("method_request needs name, interface and value")
        probe = item.get("scope_probe")
        if probe is not None:
            if (not isinstance(probe, dict) or not isinstance(probe.get("source_opportunity_id"), str)
                    or not isinstance(probe.get("changed_condition"), str)
                    or not probe["changed_condition"].strip()
                    or not isinstance(probe.get("competing_explanations"), list)
                    or len(probe["competing_explanations"]) < 2):
                raise SettlementError("scope_probe needs source, changed condition and alternatives")
            refs = probe.get("lesson_refs")
            if not isinstance(refs, list) or not refs or any(
                    not isinstance(r, dict) or not isinstance(r.get("claim_id"), str)
                    or type(r.get("version")) is not int or r["version"] < 1 for r in refs):
                raise SettlementError("scope_probe needs exact lesson references")
    if any(i.get("scope_probe", {}).get("source_opportunity_id") not in ids
           for i in items if i.get("scope_probe") is not None):
        raise SettlementError("scope probe source must name a catalogue opportunity")
    return charter


def _kind(item):
    return ("scope-probe" if item.get("scope_probe") is not None else
            "instrument" if item.get("method_request") is not None else "investigation")


def _load_catalogue(dsn, artifacts_root, charter, *, allow_missing=False):
    result = {}
    for item in charter["opportunities"]:
        try:
            dev_task = task.load(dsn, artifacts_root, item["task_id"])
            organism = genome.load(dsn, artifacts_root, item["genome_id"])
        except (SettlementError, OSError):
            if not allow_missing:
                raise
            result[item["id"]] = None
            continue
        if dev_task.split != "dev":
            if not allow_missing:
                raise SettlementError("agenda accepts published development tasks only")
            result[item["id"]] = None
            continue
        method = item.get("method_request")
        if method is not None and not any(
                cap.name == method["name"] and cap.interface == method["interface"]
                for cap in capability.catalogue(organism)):
            if not allow_missing:
                raise SettlementError("method request does not name this genome's exact interface")
            result[item["id"]] = None
            continue
        result[item["id"]] = (dev_task, organism)
    for item in charter["opportunities"]:
        probe = item.get("scope_probe")
        if probe is not None:
            source_entry, target_entry = (result[probe["source_opportunity_id"]],
                                          result[item["id"]])
            if source_entry is None or target_entry is None:
                continue
            source, target = source_entry[0], target_entry[0]
            if source.instruction == target.instruction and dict(source.workspace) == dict(target.workspace):
                if not allow_missing:
                    raise SettlementError("scope probe must change actual task input")
                result[item["id"]] = None
    return result


def _authority(cur, agenda_id, charter):
    version = charter["grant_version"]
    cur.execute("SELECT authority_version FROM control WHERE id=1")
    control = cur.fetchone()
    cur.execute("SELECT authority_grant,envelopes FROM grants WHERE version=%s", (version,))
    grant = cur.fetchone()
    if control is None or int(control["authority_version"]) != version or grant is None:
        raise SettlementError("pinned agenda grant is not current")
    authority, envelope = dict(grant["authority_grant"] or {}), dict(grant["envelopes"] or {})
    tasks = {i["task_id"] for i in charter["opportunities"]}
    genomes = {i["genome_id"] for i in charter["opportunities"]}
    if (authority.get("kind") != "rsi-agenda" or authority.get("agenda_id") != agenda_id
            or not tasks <= set(authority.get("development_task_ids", []))
            or not genomes <= set(authority.get("genome_ids", []))
            or not {broker.AGENT_RUN, broker.SANDBOX_EXEC} <= set(authority.get("effects", []))
            or int(envelope.get("max_turns", 0)) < charter["max_turns"]):
        raise SettlementError("grant does not authorize this catalogue and turn cap")
    for domain in ("tokens", "cpu"):
        root = charter["allocations"][domain]
        if envelope.get(domain) != {"allocation_id": root["id"], "units": root["units"]}:
            raise SettlementError(f"grant {domain} envelope differs from charter root")
        cur.execute("SELECT domain,parent_id,authorized,owner_scope FROM allocations WHERE id=%s",
                    (root["id"],))
        allocation = cur.fetchone()
        if (allocation is None or allocation["domain"] != domain or allocation["parent_id"] is not None
                or int(allocation["authorized"]) < root["units"]
                or allocation["owner_scope"] not in ("", agenda_id, "rsi-agenda:" + agenda_id)):
            raise SettlementError(f"{domain} allocation is not an authorized root pool")


def create(dsn, *, agenda_id, charter, artifacts_root):
    if not isinstance(agenda_id, str) or not agenda_id.strip():
        raise SettlementError("agenda_id must be non-empty")
    charter, digest = _json(charter)
    charter = _parse(charter)
    _load_catalogue(dsn, artifacts_root, charter, allow_missing=True)

    def save(cur, control):
        cur.execute("SELECT charter_digest FROM rsi_agendas WHERE agenda_id=%s", (agenda_id,))
        row = cur.fetchone()
        if row is not None:
            if row["charter_digest"] != digest:
                raise SettlementError("agenda id already has another immutable charter")
            return ResultCode.ALREADY_APPLIED, "agenda already created", {"agenda_id": agenda_id}, [], []
        _authority(cur, agenda_id, charter)
        cur.execute("SELECT event_epoch FROM control WHERE id=1")
        event_epoch = cur.fetchone()["event_epoch"]
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1")
        memory_revision = cur.fetchone()["revision"]
        cur.execute("INSERT INTO rsi_agendas (agenda_id,charter,charter_digest,source_epoch,memory_revision)"
                    " VALUES (%s,%s,%s,%s,%s)",
                    (agenda_id, Json(charter), digest, event_epoch, memory_revision))
        data = {"agenda_id": agenda_id, "charter_digest": digest}
        return ResultCode.APPLIED, "agenda created", data, [("rsi.agenda.created", data)], []

    result = store.transact(dsn, Command(request_id="p05-create:" + agenda_id,
                                         payload={"agenda_id": agenda_id, "charter_digest": digest}), save)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return read(dsn, agenda_id)


def _row(dsn, agenda_id):
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s", (agenda_id,))
        row = cur.fetchone()
        return None if row is None else dict(row)


def read(dsn, agenda_id):
    row = _row(dsn, agenda_id)
    return None if row is None else {k: v for k, v in row.items()
                                     if k not in {"created_at", "updated_at"}}


def export(dsn, agenda_id):
    state = read(dsn, agenda_id)
    if state is None:
        return None
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id,kind,actor,data,created_at FROM rsi_decisions"
                    " WHERE subject=%s AND (kind LIKE 'p05.%%' OR kind LIKE 'p10.%%')"
                    " ORDER BY created_at,id", (agenda_id,))
        return {"agenda": state, "decisions": [dict(row) for row in cur.fetchall()]}


def _source_snapshot(dsn, state):
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SELECT event_epoch FROM control WHERE id=1")
        epoch = int(cur.fetchone()["event_epoch"])
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1")
        memory_revision = int(cur.fetchone()["revision"])
        cur.execute("SELECT epoch,kind,payload FROM domain_events"
                    " WHERE epoch>%s AND epoch<=%s ORDER BY epoch,ordinal",
                    (state["source_epoch"], epoch))
        events = [dict(row) for row in cur.fetchall()]
        conn.commit()
    return {"event_epoch": epoch, "memory_revision": memory_revision, "events": events}


def _choice_id(agenda_id, revision, kind):
    digest = hashlib.sha256(f"{agenda_id}:{revision}:{kind}".encode()).hexdigest()
    return f"p05-{kind}-{digest}"


def _record(cur, agenda_id, kind, revision, data):
    cur.execute("INSERT INTO rsi_decisions (id,kind,actor,subject,data)"
                " VALUES (%s,%s,'fixed',%s,%s)",
                (_choice_id(agenda_id, revision, kind), "p05." + kind,
                 agenda_id, Json(data)))


def _pending_assessment(cur, agenda_id):
    cur.execute(
        "SELECT assignment.id,assignment.kind,assignment.actor,assignment.subject,assignment.data"
        " FROM rsi_decisions AS assignment"
        " WHERE assignment.subject=%s AND assignment.kind='p10.assessment.assignment'"
        " AND NOT EXISTS (SELECT 1 FROM rsi_decisions AS final_gate"
        " WHERE final_gate.id=('gate:' || (assignment.data->>'gate_id'))"
        " AND final_gate.kind='gate')"
        " ORDER BY assignment.created_at,assignment.id LIMIT 1",
        (agenda_id,))
    row = cur.fetchone()
    return None if row is None else dict(row)


def _commit_choice(dsn, agenda_id, state, snapshot, choice):
    charter = state["charter"]
    identity = hashlib.sha256(
        f"{state['revision']}:{snapshot['event_epoch']}:{snapshot['memory_revision']}:{choice['id']}"
        .encode()).hexdigest()[:24]
    command = Command(
        request_id=f"p05-choose:{agenda_id}:{identity}",
        payload={"agenda_id": agenda_id, "revision": state["revision"],
                 "choice": choice["id"],
                 "snapshot": [snapshot["event_epoch"], snapshot["memory_revision"]]})

    def commit(cur, control):
        cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        if current is None or int(current["revision"]) != int(state["revision"]):
            raise StaleRevision("agenda changed during source snapshot")
        if current["status"] != "active":
            raise StaleRevision("agenda no longer admits development choices")
        if current["flight"] is not None:
            raise StaleRevision("another wake already pinned a flight")
        if _pending_assessment(cur, agenda_id) is not None:
            raise StaleRevision("an assessment assignment is pending")
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1 FOR UPDATE")
        memory_row = cur.fetchone()
        if (int(control["event_epoch"]) != snapshot["event_epoch"]
                or int(memory_row["revision"]) != snapshot["memory_revision"]):
            raise StaleRevision("source snapshot changed before choice")
        _authority(cur, agenda_id, charter)
        flight = {"opportunity_id": choice["id"],
                  "investigation_id": choice["investigation_id"],
                  "target_revision": choice["target_revision"],
                  "choice_id": _choice_id(agenda_id, int(state["revision"]), "choice"),
                  "source_snapshot": {"event_epoch": snapshot["event_epoch"],
                                      "memory_revision": snapshot["memory_revision"]}}
        data = {**choice, **flight, "turn": int(state["turns"]) + 1,
                "ranked": choice["ranked"], "policy": charter["policy"],
                "reason": choice["rank_reason"]}
        _record(cur, agenda_id, "choice", int(state["revision"]), data)
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,turns=turns+1,flight=%s,"
                    "source_epoch=%s,memory_revision=%s,updated_at=now() WHERE agenda_id=%s",
                    (Json(flight), snapshot["event_epoch"], snapshot["memory_revision"], agenda_id))
        return (ResultCode.APPLIED, "choice persisted", flight,
                [("rsi.agenda.choice", {"agenda_id": agenda_id,
                                         "opportunity_id": choice["id"]})], [])

    result = store.transact(dsn, command, commit)
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return result.data
    if result.code == ResultCode.STALE_REVISION:
        return None
    raise SettlementError(result.detail)


def _settled(effect):
    return bool(effect and effect.get("settled")
                and effect.get("dispatch_state") in {"observed", "reconciled"}
                and effect.get("reconcile_state") not in {"conflict", "unresolved"}
                and effect.get("receipts"))


def _attempt_effects(dsn, attempt_id):
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id,payload,settled,dispatch_state,reconcile_state FROM operations"
                    " WHERE attempt_id=%s ORDER BY id", (attempt_id,))
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["effect"] = dict(row["payload"] or {}).get("effect")
        row["receipts"] = store.operation_receipts(dsn, row["id"])
    return {row["id"]: row for row in rows}


def _ack_evidence(dsn, flight):
    history = investigation.export(dsn, flight["investigation_id"])
    if history is None:
        return None
    digest = hashlib.sha256(
        f"{flight['investigation_id']}:{flight['target_revision']}".encode()).hexdigest()
    decision_id = "p01-decision-" + digest
    decision = next((d for d in history["decisions"] if d["id"] == decision_id), None)
    if decision is None or decision["kind"] != "worker":
        return None
    data = decision["data"]
    attempt_id, operation_id = data.get("attempt_id"), data.get("operation_id")
    observation = next((o["content"] for o in history["observations"]
                        if o["decision_id"] == decision_id
                        and o["content"].get("episode") == operation_id), None)
    if (not isinstance(attempt_id, str) or not isinstance(operation_id, str)
            or observation is None or observation.get("status") not in {"passed", "failed"}
            or type(observation.get("passed")) is not bool):
        return None
    effects = _attempt_effects(dsn, attempt_id)
    worker, verifier = effects.get(operation_id), effects.get(observation.get("verdict"))
    if (not _settled(worker) or not _settled(verifier)
            or any(not _settled(effect) for effect in effects.values())
            or worker["effect"] not in {broker.AGENT_RUN, broker.SANDBOX_EXEC}
            or verifier["effect"] != broker.SANDBOX_EXEC
            or observation["status"] != ("passed" if observation["passed"] else "failed")):
        return None
    return {"decision_id": decision_id, "attempt_id": attempt_id,
            "operation_id": operation_id, "observation": observation,
            "receipts": {"worker": worker["receipts"], "verifier": verifier["receipts"]}}


def _refusal_evidence(dsn, flight):
    history = investigation.export(dsn, flight["investigation_id"])
    if history is None:
        return None
    digest = hashlib.sha256(
        f"{flight['investigation_id']}:{flight['target_revision']}".encode()).hexdigest()
    decision_id = "p01-decision-" + digest
    decision = next((d for d in history["decisions"] if d["id"] == decision_id), None)
    if decision is None or decision["kind"] != "worker":
        return None
    data = decision["data"]
    attempt_id, operation_id = data.get("attempt_id"), data.get("operation_id")
    observation = next((o["content"] for o in history["observations"]
                        if o["decision_id"] == decision_id
                        and o["content"].get("episode") == operation_id), None)
    if (not isinstance(attempt_id, str) or not isinstance(operation_id, str)
            or observation is None or observation.get("status") != "refused"
            or observation.get("passed") is not None or observation.get("verdict") is not None
            or observation.get("solution") is not None):
        return None
    refused = observation.get("refused_operation", operation_id)
    if refused == operation_id:
        with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id,attempt_id,settled,dispatch_state,reconcile_state,payload,reservation_id"
                        " FROM operations WHERE id=%s", (operation_id,))
            op = cur.fetchone()
            if op is not None:
                reason = investigation._never_sent_refusal(cur, dict(op), operation_id, attempt_id)
                if reason is None:
                    return None
            else:
                cur.execute("SELECT result_code,result_detail FROM command_journal WHERE request_id=%s",
                            ("broker-prep-" + operation_id,))
                refusal = cur.fetchone()
                cur.execute("SELECT 1 FROM operations WHERE attempt_id=%s LIMIT 1", (attempt_id,))
                if (refusal is None or refusal["result_code"] not in
                        investigation._DEFINITE_PREP_REFUSALS or cur.fetchone() is not None):
                    return None
                reason = str(refusal["result_detail"])
        return {"decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "refused_operation": refused,
                "reason": "P01 worker was definitively refused before dispatch: " + reason}

    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT t.evaluator_version FROM rsi_episodes e JOIN rsi_tasks t"
                    " ON t.digest=e.task WHERE e.operation_id=%s", (operation_id,))
        task_row = cur.fetchone()
        if task_row is None or refused != verifier.operation_id_for(
                operation_id, task_row["evaluator_version"]):
            return None
        cur.execute("SELECT 1 FROM operations WHERE id=%s", (refused,))
        if cur.fetchone() is not None:
            return None
        cur.execute("SELECT result_code,result_detail FROM command_journal WHERE request_id=%s",
                    ("broker-prep-" + refused,))
        refusal = cur.fetchone()
    effects = _attempt_effects(dsn, attempt_id)
    worker = effects.get(operation_id)
    if (refusal is None or refusal["result_code"] not in investigation._DEFINITE_PREP_REFUSALS
            or not _settled(worker) or worker["effect"] not in {broker.AGENT_RUN, broker.SANDBOX_EXEC}
            or any(not _settled(effect) for effect in effects.values())):
        return None
    return {"decision_id": decision_id, "attempt_id": attempt_id,
            "operation_id": operation_id, "refused_operation": refused,
            "reason": "P01 verifier was definitively refused before dispatch: "
                      + str(refusal["result_detail"])}


def _ack(dsn, agenda_id, flight, evidence):
    state = _row(dsn, agenda_id)
    for attempt in range(2):
        expected_revision = int(state["revision"])
        cmd = Command(request_id=f"p05-ack:{agenda_id}:{state['revision']}:{attempt}",
                      payload={"agenda_id": agenda_id, "revision": state["revision"],
                               "decision_id": evidence["decision_id"]})

        def commit(cur, control, expected_revision=expected_revision):
            cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
            current = cur.fetchone()
            if current is None:
                raise StaleRevision("agenda disappeared before acknowledgement")
            cur.execute("SELECT id,data FROM rsi_decisions WHERE subject=%s AND kind='p05.ack'"
                        " AND data->>'decision_id'=%s", (agenda_id, evidence["decision_id"]))
            prior = cur.fetchone()
            if prior is not None:
                return (ResultCode.ALREADY_APPLIED, "flight already acknowledged",
                        dict(prior["data"] or {}), [], [])
            if (int(current["revision"]) != expected_revision
                    or current["flight"] != flight):
                raise StaleRevision("agenda flight changed before acknowledgement")
            data = {**flight, **evidence}
            _record(cur, agenda_id, "ack", expected_revision, data)
            # Keep the pre-effect cursors. The next wake must examine the P01
            # outcome and P02 capture generated by this flight.
            cur.execute("UPDATE rsi_agendas SET revision=revision+1,flight=NULL,status="
                        "CASE WHEN status IN ('suspended','stopped') THEN status "
                        "WHEN turns >= %s THEN 'complete' ELSE 'active' END,"
                        "last_result=%s,updated_at=now() WHERE agenda_id=%s",
                        (current["charter"]["max_turns"],
                         Json({"status": "acknowledged", **data}), agenda_id))
            return (ResultCode.APPLIED, "flight acknowledged", data,
                    [("rsi.agenda.acknowledged", {"agenda_id": agenda_id,
                                                   "opportunity_id": flight["opportunity_id"]})], [])

        result = store.transact(dsn, cmd, commit)
        if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            return result.data
        if result.code != ResultCode.STALE_REVISION or attempt:
            raise SettlementError(result.detail)
        state = _row(dsn, agenda_id)
    return {}


def _inv_id(agenda_id, option_id):
    return "p05-inv-" + hashlib.sha256(f"{agenda_id}:{option_id}".encode()).hexdigest()[:32]


def _lesson_claim_ids(charter, opportunity_id):
    refs = {ref["claim_id"] for item in charter["opportunities"]
            if item["id"] == opportunity_id
            for ref in (item.get("scope_probe") or {}).get("lesson_refs", [])}
    refs.update(ref["claim_id"] for item in charter["opportunities"]
                if (item.get("scope_probe") or {}).get("source_opportunity_id") == opportunity_id
                for ref in item["scope_probe"]["lesson_refs"])
    return sorted(refs)


def _p01_incompatibility(config, opportunity, charter, agent):
    lessons = _lesson_claim_ids(charter, opportunity["id"])
    if (config.get("task") != opportunity["task_id"]
            or config.get("genome") != opportunity["genome_id"]
            or config.get("token_allocation") != charter["allocations"]["tokens"]["id"]
            or config.get("cpu_allocation") != charter["allocations"]["cpu"]["id"]
            or not set(lessons) <= set((config.get("context") or {}).get(
                "required_claim_ids", []))):
        return "P01 investigation differs from the pinned portfolio opportunity"
    method = opportunity.get("method_request")
    if config.get("method") != method:
        return "P01 method request differs from the pinned portfolio opportunity"
    if method is None and (agent is None or config.get("model") != agent.provider.model):
        return "P01 worker model differs from investigation configuration"
    if config["token_ceiling"] > opportunity["resource_ceilings"]["tokens"]:
        return "P01 token ceiling exceeds the opportunity ceiling"
    if config["timeout_ms"] > opportunity["timeout_ms"]:
        return "P01 timeout exceeds the opportunity ceiling"
    return None


def _ensure_p01(dsn, agent, checker, opportunity, flight, charter, loaded,
                staging_root, artifacts_root):
    inv_id = flight["investigation_id"]
    state = investigation.read(dsn, inv_id)
    lessons = _lesson_claim_ids(charter, opportunity["id"])
    if state is None:
        dev_task, organism = loaded[opportunity["id"]]
        investigate.create(
            dsn, agent, organism, investigation_id=inv_id, task=dev_task,
            token_allocation=charter["allocations"]["tokens"]["id"],
            cpu_allocation=charter["allocations"]["cpu"]["id"],
            max_steps=opportunity["max_steps"], timeout_ms=opportunity["timeout_ms"],
            token_ceiling=opportunity["resource_ceilings"]["tokens"],
            objective=opportunity["objective"], method=opportunity.get("method_request"),
            context={"required_claim_ids": lessons} if lessons else None,
            staging_root=staging_root, artifacts_root=artifacts_root)
        state = investigation.read(dsn, inv_id)
    incompatibility = _p01_incompatibility(state["config"], opportunity, charter, agent)
    if incompatibility is not None:
        raise SettlementError(incompatibility)
    return investigate.step(dsn, agent, checker, inv_id, staging_root=staging_root,
                            artifacts_root=artifacts_root,
                            target_revision=flight["target_revision"])


def _finish(dsn, agent, checker, agenda_id, state, loaded, staging_root, artifacts_root,
            *, flight):
    opportunity = next(i for i in state["charter"]["opportunities"]
                       if i["id"] == flight["opportunity_id"])
    if loaded.get(opportunity["id"]) is None:
        return {"status": "pending", "opportunity_id": opportunity["id"],
                "reason": "catalogue source is unavailable; pinned flight is retained"}
    result = _ensure_p01(dsn, agent, checker, opportunity, flight, state["charter"], loaded,
                         staging_root, artifacts_root)
    evidence = _ack_evidence(dsn, flight)
    if evidence is not None:
        _ack(dsn, agenda_id, flight, evidence)
        return {"status": "acknowledged", "opportunity_id": opportunity["id"],
                "investigation": result, "acknowledgement": evidence}
    refusal = _refusal_evidence(dsn, flight)
    if refusal is not None:
        return _defer_flight(dsn, agenda_id, flight)
    if result.get("context_outcome") or result.get("capability_outcome"):
        return {"status": "pending", "opportunity_id": opportunity["id"],
                "reason": result.get("context_outcome") or result.get("capability_outcome")}
    return {"status": "pending", "opportunity_id": opportunity["id"],
            "investigation": result}


def _defer_flight(dsn, agenda_id, flight):
    refusal = _refusal_evidence(dsn, flight)
    if refusal is None:
        return {"status": "pending", "opportunity_id": flight["opportunity_id"],
                "reason": "pinned flight has no definitive never-sent proof"}
    state = _row(dsn, agenda_id)
    data = {**flight, "reason": refusal["reason"]}
    command = Command(request_id=f"p05-deferral:{agenda_id}:{state['revision']}",
                      payload={"agenda_id": agenda_id, "revision": state["revision"], "data": data})

    def save(cur, control):
        cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        if int(current["revision"]) != int(state["revision"]) or current["flight"] != flight:
            raise StaleRevision("agenda flight changed before deferral")
        _record(cur, agenda_id, "deferral", int(state["revision"]), data)
        result = {"status": "deferred", **data}
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,flight=NULL,last_result=%s,"
                    "updated_at=now() WHERE agenda_id=%s", (Json(result), agenda_id))
        return (ResultCode.APPLIED, "flight deferred", result,
                [("rsi.agenda.deferred", {"agenda_id": agenda_id})], [])
    result = store.transact(dsn, command, save)
    return result.data if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED) else {
        "status": "stale", "reason": result.detail}


def _source_investigations(dsn, agenda_id, option_id, item):
    if item.get("investigation_id"):
        return [item["investigation_id"]]
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT data->>'investigation_id' AS id FROM rsi_decisions"
                    " WHERE subject=%s AND kind='p05.choice' AND data->>'opportunity_id'=%s"
                    " ORDER BY created_at,id", (agenda_id, option_id))
        return list(dict.fromkeys(row["id"] for row in cur.fetchall() if row["id"]))


def _checked_failed_lesson_use(dsn, agenda_id, item, charter, loaded, artifacts_root):
    probe = item.get("scope_probe")
    if probe is None:
        return False
    source = next(i for i in charter["opportunities"]
                  if i["id"] == probe["source_opportunity_id"])
    source_entry, probe_entry = loaded.get(source["id"]), loaded.get(item["id"])
    if source_entry is None or probe_entry is None:
        return False
    origin_task, probe_task = source_entry[0], probe_entry[0]
    if origin_task.instruction == probe_task.instruction and dict(origin_task.workspace) == dict(probe_task.workspace):
        return False
    expected = {(r["claim_id"], r["version"]) for r in probe["lesson_refs"]}
    for inv_id in _source_investigations(dsn, agenda_id, source["id"], source):
        history = investigation.export(dsn, inv_id)
        if history is None:
            continue
        for observation in history["observations"]:
            content = observation["content"]
            if content.get("status") != "failed" or content.get("passed") is not False:
                continue
            decision = next((d for d in history["decisions"]
                             if d["id"] == observation["decision_id"]), None)
            if decision is None or decision["kind"] != "worker":
                continue
            packet = dict((decision["data"].get("visible_input") or {}).get("context_packet") or {})
            memory_view = dict(packet.get("memory_view") or {})
            refs = {(c.get("claim_id"), c.get("version")) for c in memory_view.get("claims", [])
                    if isinstance(c, dict)}
            operation_id = decision["data"].get("operation_id")
            operation_evidence = _attempt_effects(dsn, decision["data"].get("attempt_id"))
            worker_evidence = operation_evidence.get(operation_id)
            verdict_evidence = operation_evidence.get(content.get("verdict"))
            if (expected <= refs and _settled(worker_evidence)
                    and worker_evidence["effect"] in {broker.AGENT_RUN, broker.SANDBOX_EXEC}
                    and _settled(verdict_evidence)
                    and verdict_evidence["effect"] == broker.SANDBOX_EXEC
                    and all(_settled(effect) for effect in operation_evidence.values())):
                source_state = investigation.read(dsn, inv_id)
                scope = source_state["config"].get("context", {}).get(
                    "scope", {"domain": "task"})
                visible = memory.query(
                    dsn, purpose="task: " + source_state["objective"],
                    investigation_id=inv_id, scope=scope,
                    claim_ids=sorted({claim_id for claim_id, _ in expected}),
                    artifacts_root=artifacts_root, limit=len(expected))
                current = {(claim["claim_id"], claim["version"])
                           for claim in visible["claims"] if claim["status"] == "supported"}
                if expected <= current and not visible["missing_information"]:
                    return True
    return False


def _last_selected(dsn, agenda_id, option_id):
    with db.read_connect(dsn) as conn:
        row = conn.execute("SELECT max((data->>'turn')::int) FROM rsi_decisions"
                           " WHERE subject=%s AND kind='p05.choice' AND data->>'opportunity_id'=%s",
                           (agenda_id, option_id)).fetchone()
        return row[0]


def _relevant(dsn, snapshot, agenda_id, charter):
    inv_ids = {inv_id for item in charter["opportunities"]
               for inv_id in _source_investigations(
                   dsn, agenda_id, item["id"], item)}
    for event in snapshot["events"]:
        payload = dict(event["payload"] or {})
        if event["kind"] == "rsi.investigation.observed" and payload.get("investigation_id") in inv_ids:
            return True
        if (event["kind"] == "rsi.decision" and payload.get("kind") == "capability-retention"
                and dict(payload.get("data") or {}).get("status") == "retained"
                and any(payload.get("subject") == item["genome_id"]
                        and dict(payload.get("data") or {}).get("name")
                        == (item.get("method_request") or {}).get("name")
                        and dict(payload.get("data") or {}).get("interface")
                        == (item.get("method_request") or {}).get("interface")
                        for item in charter["opportunities"])):
            return True
    return False


def _relevant_memory_change(dsn, charter, prior_revision):
    claim_ids = sorted({ref["claim_id"] for item in charter["opportunities"]
                        for ref in (item.get("scope_probe") or {}).get("lesson_refs", [])})
    if not claim_ids:
        return False
    with db.read_connect(dsn) as conn:
        row = conn.execute("SELECT 1 FROM rsi_memory_claim_versions"
                           " WHERE claim_id=ANY(%s) AND revision>%s LIMIT 1",
                           (claim_ids, prior_revision)).fetchone()
        return row is not None


def _advance(dsn, agenda_id, state, snapshot):
    cmd = Command(request_id=f"p05-advance:{agenda_id}:{state['revision']}:{snapshot['event_epoch']}:{snapshot['memory_revision']}",
                  payload={"agenda_id": agenda_id})

    def save(cur, control):
        cur.execute("SELECT revision FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1 FOR UPDATE")
        mem = cur.fetchone()
        if (int(current["revision"]) != int(state["revision"])
                or int(control["event_epoch"]) != snapshot["event_epoch"]
                or int(mem["revision"]) != snapshot["memory_revision"]):
            raise StaleRevision("source snapshot changed before cursor advance")
        cur.execute("UPDATE rsi_agendas SET source_epoch=%s,memory_revision=%s,updated_at=now()"
                    " WHERE agenda_id=%s", (snapshot["event_epoch"], snapshot["memory_revision"], agenda_id))
        return ResultCode.APPLIED, "source cursors advanced", {"status": "unchanged"}, [], []
    return store.transact(dsn, cmd, save)


def _defer(dsn, agenda_id, state, snapshot, ranked):
    data = {"ranked": ranked, "reason": "no eligible opportunity",
            "event_epoch": snapshot["event_epoch"], "memory_revision": snapshot["memory_revision"]}
    previous = state.get("last_result") or {}
    if previous.get("status") == "deferred" and previous.get("ranked") == ranked:
        if (state["source_epoch"] != snapshot["event_epoch"]
                or state["memory_revision"] != snapshot["memory_revision"]):
            _advance(dsn, agenda_id, state, snapshot)
        return {"status": "deferred", **data}
    cmd = Command(request_id=f"p05-defer:{agenda_id}:{state['revision']}:{snapshot['event_epoch']}:{snapshot['memory_revision']}",
                  payload={"agenda_id": agenda_id, "revision": state["revision"], "data": data})

    def save(cur, control):
        cur.execute("SELECT revision FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1 FOR UPDATE")
        mem = cur.fetchone()
        if (int(current["revision"]) != int(state["revision"])
                or int(control["event_epoch"]) != snapshot["event_epoch"]
                or int(mem["revision"]) != snapshot["memory_revision"]):
            raise StaleRevision("source snapshot changed before deferral")
        _record(cur, agenda_id, "deferral", int(state["revision"]), data)
        result = {"status": "deferred", **data}
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,source_epoch=%s,memory_revision=%s,"
                    "last_result=%s,updated_at=now() WHERE agenda_id=%s",
                    (snapshot["event_epoch"], snapshot["memory_revision"], Json(result), agenda_id))
        return (ResultCode.APPLIED, "agenda deferred", result,
                [("rsi.agenda.deferred", {"agenda_id": agenda_id})], [])
    result = store.transact(dsn, cmd, save)
    return result.data if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED) else {
        "status": "stale", "reason": result.detail}


def _stop(dsn, agenda_id, state, snapshot, reason):
    cmd = Command(request_id=f"p05-stop:{agenda_id}:{state['revision']}",
                  payload={"agenda_id": agenda_id, "revision": state["revision"], "reason": reason})

    def stop(cur, control):
        cur.execute("SELECT revision FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        if current is None or int(current["revision"]) != int(state["revision"]):
            raise StaleRevision("agenda changed before cap stop")
        data = {"reason": reason, "ranked": []}
        _record(cur, agenda_id, "deferral", int(state["revision"]), data)
        result = {"status": "stopped", **data}
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,status='stopped',source_epoch=%s,"
                    "memory_revision=%s,last_result=%s,updated_at=now() WHERE agenda_id=%s",
                    (snapshot["event_epoch"], snapshot["memory_revision"], Json(result), agenda_id))
        return (ResultCode.APPLIED, "agenda cap reached", result,
                [("rsi.agenda.stopped", {"agenda_id": agenda_id})], [])
    result = store.transact(dsn, cmd, stop)
    return result.data if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED) else {
        "status": "stale", "reason": result.detail}


def _select_and_run(dsn, agent, checker, agenda_id, state, snapshot, loaded,
                    staging_root, artifacts_root):
    charter = state["charter"]
    deadline = datetime.fromisoformat(charter["deadline"])
    if state["turns"] >= charter["max_turns"] or datetime.now(UTC) >= deadline:
        return _stop(dsn, agenda_id, state, snapshot, "hard turn/deadline cap")
    current_grant = int(store.get_control(dsn)["authority_version"]) == charter["grant_version"]
    token_root, cpu_root = (charter["allocations"]["tokens"]["id"],
                            charter["allocations"]["cpu"]["id"])
    free_tokens, free_cpu = store.allocation_free(dsn, token_root), store.allocation_free(dsn, cpu_root)
    options = []
    for item in charter["opportunities"]:
        kind = _kind(item)
        inv_id = item.get("investigation_id") or _inv_id(agenda_id, item["id"])
        p01 = investigation.read(dsn, inv_id)
        history = investigation.export(dsn, inv_id) if p01 is not None else None
        spent = sum(d["kind"] == "worker" for d in history["decisions"]) if history else 0
        incompatibility = (_p01_incompatibility(p01["config"], item, charter, agent)
                           if p01 is not None else None)
        source_available = loaded.get(item["id"]) is not None
        ready = (p01 is None or (p01["status"] == "ready"
                 and p01["pending_decision"] is None and spent < item["max_steps"]))
        eligible = current_grant and source_available and incompatibility is None and ready
        reason = ("eligible" if eligible else "agenda grant is no longer current"
                  if not current_grant else "catalogue source is unavailable"
                  if not source_available else incompatibility if incompatibility is not None
                  else "investigation is not ready")
        token_units = (p01["config"]["token_ceiling"] if p01 is not None else
                       item["resource_ceilings"]["tokens"])
        cpu_units = broker.exposure_schedule(broker.SANDBOX_EXEC, {"timeout_ms": 30_000})[0]
        if item.get("method_request") is not None:
            native_timeout = (p01["config"]["timeout_ms"] if p01 is not None else
                              item["timeout_ms"])
            cpu_units += broker.exposure_schedule(
                broker.SANDBOX_EXEC, {"timeout_ms": native_timeout})[0]
        if token_units > free_tokens:
            eligible, reason = False, "shared token root has insufficient free units"
        if cpu_units > item["resource_ceilings"]["cpu"] or cpu_units > free_cpu:
            eligible, reason = False, "shared CPU root cannot cover native verifier exposure"
        triggered = False
        if kind == "instrument" and source_available:
            method = item["method_request"]
            availability = capability.eligibility(
                dsn, genome=loaded[item["id"]][1], name=method["name"],
                interface=method["interface"], task_id=item["task_id"],
                value=method["value"], artifacts_root=artifacts_root)
            triggered = availability["status"] == "selected"
            if not triggered:
                eligible = False
                reason = availability["reason"]
                if "retention" in reason:
                    reason = "no checked retention for the exact genome method interface: " + reason
        elif kind == "scope-probe":
            triggered = _checked_failed_lesson_use(dsn, agenda_id, item, charter, loaded, artifacts_root)
            if not triggered:
                eligible, reason = False, "no checked failed later use of the referenced learner-visible lesson"
        options.append({"id": item["id"], "eligible": eligible, "priority": item["priority"],
                        "kind": kind, "triggered": triggered,
                        "last_selected": _last_selected(dsn, agenda_id, item["id"]),
                        "reason": reason, "investigation_id": inv_id,
                        "target_revision": p01["revision"] if p01 else 0})
    ranked = agenda_policy.rank(options, charter["policy"])
    selected = next((option for option in ranked if option["eligible"]), None)
    if selected is None:
        return _defer(dsn, agenda_id, state, snapshot, ranked)
    choice = {**selected, "ranked": ranked}
    flight = _commit_choice(dsn, agenda_id, state, snapshot, choice)
    if flight is None:
        current = _row(dsn, agenda_id)
        if current is not None and current["flight"] is not None:
            return _finish(dsn, agent, checker, agenda_id, current, loaded,
                           staging_root, artifacts_root, flight=current["flight"])
        return {"status": "stale", "reason": "source snapshot changed"}
    return _finish(dsn, agent, checker, agenda_id, _row(dsn, agenda_id), loaded,
                   staging_root, artifacts_root, flight=flight)


def _wake(dsn, agent, checker, agenda_id, *, staging_root, artifacts_root):
    state = _row(dsn, agenda_id)
    if state is None:
        raise SettlementError("unknown agenda " + agenda_id)
    if state["status"] != "active":
        return {"status": state["status"], "revision": state["revision"], "turns": state["turns"]}
    charter = _parse(state["charter"])
    loaded = _load_catalogue(dsn, artifacts_root, charter, allow_missing=True)
    if state["flight"] is not None:
        return _finish(dsn, agent, checker, agenda_id, state, loaded, staging_root,
                       artifacts_root, flight=state["flight"])
    snapshot = _source_snapshot(dsn, state)
    memory_changed = (snapshot["memory_revision"] != state["memory_revision"]
                      and _relevant_memory_change(dsn, charter, state["memory_revision"]))
    cached_deferral = (state.get("last_result") or {}).get("status") == "deferred"
    changed = (not state["last_result"] or cached_deferral or memory_changed
               or (snapshot["event_epoch"] != state["source_epoch"]
                   and _relevant(dsn, snapshot, agenda_id, charter)))
    if not changed:
        if snapshot["event_epoch"] != state["source_epoch"]:
            _advance(dsn, agenda_id, state, snapshot)
        return dict(state["last_result"] or {"status": "unchanged"})
    return _select_and_run(dsn, agent, checker, agenda_id, state, snapshot, loaded,
                           staging_root, artifacts_root)


def wake(dsn, agent, checker, agenda_id, *, staging_root, artifacts_root):
    state = _row(dsn, agenda_id)
    if state is not None and "assessment_protocol" in state["charter"]:
        raise SettlementError("campaign-owned agendas must use the campaign consumer")
    return _wake(dsn, agent, checker, agenda_id, staging_root=staging_root,
                 artifacts_root=artifacts_root)


def control(dsn, agenda_id, expected_revision, action):
    if not isinstance(agenda_id, str) or not agenda_id.strip():
        raise SettlementError("agenda_id must be non-empty")
    if type(expected_revision) is not int or expected_revision < 0:
        raise SettlementError("expected_revision must be a nonnegative integer")
    if not isinstance(action, str) or action not in {"suspend", "resume", "stop"}:
        raise SettlementError("action must be suspend, resume or stop")

    identity = hashlib.sha256(json.dumps(
        [agenda_id, expected_revision, action], separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    decision_id = "p10-control-" + identity
    request_id = "p10-control:" + identity
    command = Command(
        request_id=request_id,
        payload={"agenda_id": agenda_id, "expected_revision": expected_revision,
                 "action": action})

    def apply(cur, control_state):
        cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        if current is None:
            raise SettlementError("unknown agenda " + agenda_id)
        if int(current["revision"]) != expected_revision:
            raise StaleRevision("agenda revision changed before lifecycle control")
        status = current["status"]
        if action == "suspend":
            if status not in {"active", "complete"}:
                raise SettlementError("only active or complete agendas can be suspended")
            next_status = "suspended"
        elif action == "resume":
            if status != "suspended":
                raise SettlementError("only suspended agendas can be resumed")
            next_status = "active"
        else:
            next_status = "stopped"
            if status == "stopped":
                data = {"action": action, "status": status,
                        "revision": expected_revision}
                return ResultCode.ALREADY_APPLIED, "agenda already stopped", data, [], []

        data = {"action": action, "from_status": status, "status": next_status,
                "expected_revision": expected_revision,
                "revision": expected_revision + 1}
        decision = {"id": decision_id, "kind": "p10.lifecycle.control",
                    "actor": "fixed", "subject": agenda_id, "data": data}
        cur.execute("INSERT INTO rsi_decisions (id,kind,actor,subject,data)"
                    " VALUES (%s,%s,'fixed',%s,%s)",
                    (decision_id, "p10.lifecycle.control", agenda_id, Json(data)))
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,status=%s,updated_at=now()"
                    " WHERE agenda_id=%s",
                    (next_status, agenda_id))
        return (ResultCode.APPLIED, "agenda lifecycle controlled", data,
                [("rsi.decision", decision),
                 ("rsi.agenda.controlled", {"agenda_id": agenda_id, **data})], [])

    result = store.transact(dsn, command, apply)
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return result.data
    if result.code == ResultCode.STALE_REVISION:
        raise StaleRevision(result.detail)
    raise SettlementError(result.detail)
