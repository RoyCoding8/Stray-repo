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

from . import (agenda_policy, capability, genome, investigate, investigation,
               memory, search, task, verifier)

_MAX_OPTIONS = 64
_MAX_TURNS = 100
_POLICY_INTERFACE = "exploration-policy/1"


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
    policy = charter["policy"]
    if isinstance(policy, str):
        if policy not in {"seed/1", "adaptive/1"}:
            raise SettlementError("policy must be seed/1, adaptive/1, or an exploration policy")
    elif (not isinstance(policy, dict)
          or set(policy) != {"genome", "name", "interface", "timeout_ms", "max_output_bytes"}
          or any(not isinstance(policy.get(key), str) or not policy[key].strip()
                 for key in ("genome", "name", "interface"))
          or policy.get("interface") != _POLICY_INTERFACE):
        raise SettlementError("native policy needs genome, name, exploration-policy/1, and bounds")
    else:
        _positive(policy.get("timeout_ms"), "policy.timeout_ms", capability.MAX_TIMEOUT_MS)
        _positive(policy.get("max_output_bytes"), "policy.max_output_bytes",
                  capability.MAX_OUTPUT_BYTES)
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


def _load_policy(dsn, artifacts_root, charter, *, allow_missing=False):
    policy = charter["policy"]
    if isinstance(policy, str):
        return None
    try:
        organism = genome.load(dsn, artifacts_root, policy["genome"])
    except (SettlementError, OSError):
        if allow_missing:
            return None
        raise
    method = next((item for item in capability.catalogue(organism)
                   if item.name == policy["name"] and item.interface == policy["interface"]), None)
    if method is None:
        if allow_missing:
            return None
        raise SettlementError("native policy does not name its genome's exact interface")
    limits = method.descriptor["limits"]
    if (policy["timeout_ms"] > limits["timeout_ms"]
            or policy["max_output_bytes"] > limits["max_output_bytes"]):
        raise SettlementError("native policy bounds exceed the method's declared limits")
    return organism


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
    if isinstance(charter["policy"], dict):
        genomes.add(charter["policy"]["genome"])
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
    _load_policy(dsn, artifacts_root, charter)

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
        if datetime.now(UTC) >= datetime.fromisoformat(current["charter"]["deadline"]):
            raise StaleRevision("agenda deadline passed before choice admission")
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


def _ensure_p01_state(dsn, agent, opportunity, flight, charter, loaded,
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
    return state


def _target_was_observed(dsn, investigation_id, decision_id, attempt_id, operation_id):
    history = investigation.export(dsn, investigation_id)
    if history is None:
        return False
    decision = next((item for item in history["decisions"] if item["id"] == decision_id), None)
    if (decision is None or decision["kind"] != "worker"
            or decision["data"].get("attempt_id") != attempt_id
            or decision["data"].get("operation_id") != operation_id):
        return False
    return any(item["decision_id"] == decision_id
               and item["content"].get("episode") == operation_id
               for item in history["observations"])


def _ensure_p01(dsn, agent, checker, opportunity, flight, charter, loaded,
                staging_root, artifacts_root):
    state = _ensure_p01_state(dsn, agent, opportunity, flight, charter, loaded,
                              staging_root, artifacts_root)
    start = flight.get("start")
    if start is not None:
        target_revision = int(start["target_revision"])
        decision_id, attempt_id, operation_id = (start[key] for key in
                                                 ("decision_id", "attempt_id", "operation_id"))
        pending = state.get("pending_decision")
        if pending is not None:
            if ((pending["id"], pending["attempt_id"], pending["operation_id"])
                    != (decision_id, attempt_id, operation_id)
                    or pending.get("visible_input") != start["visible_input"]):
                raise StaleRevision("pending P01 input differs from the policy-pinned start")
        elif not _target_was_observed(dsn, flight["investigation_id"],
                                      decision_id, attempt_id, operation_id):
            prepared = investigate.prepare_context(
                dsn, flight["investigation_id"], target_revision=target_revision,
                artifacts_root=artifacts_root)
            if (prepared.get("visible_input") != start["visible_input"]
                    or (prepared.get("decision_id"), prepared.get("attempt_id"),
                        prepared.get("operation_id")) != (decision_id, attempt_id, operation_id)):
                raise StaleRevision("prepared P01 input changed after policy admission")
            investigate._require(investigation.decide(dsn, Command(
                request_id="p01-decide:" + decision_id.removeprefix("p01-decision-"),
                expected_revision=target_revision,
                payload={"investigation_id": flight["investigation_id"],
                         "decision_id": decision_id,
                         "attempt_id": attempt_id,
                         "operation_id": operation_id,
                         "action": {"kind": "worker",
                                    "explanation": "Attempt the open obligation using checked feedback.",
                                    "intended_observation": investigate.QUESTION},
                         "visible_input": start["visible_input"]})))
        return investigate.step(dsn, agent, checker, flight["investigation_id"],
                                staging_root=staging_root, artifacts_root=artifacts_root,
                                target_revision=target_revision)
    return investigate.step(dsn, agent, checker, inv_id, staging_root=staging_root,
                            artifacts_root=artifacts_root,
                            target_revision=flight["target_revision"])


def _finish(dsn, agent, checker, agenda_id, state, loaded, staging_root, artifacts_root,
            *, flight):
    if flight.get("kind") == "policy":
        return _finish_policy(dsn, agent, checker, agenda_id, state, loaded,
                              staging_root, artifacts_root, flight=flight)
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


def _opportunity_options(dsn, agenda_id, state, loaded, agent, artifacts_root, *,
                         free_tokens, free_cpu):
    charter = state["charter"]
    current_grant = int(store.get_control(dsn)["authority_version"]) == charter["grant_version"]
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
            triggered = _checked_failed_lesson_use(
                dsn, agenda_id, item, charter, loaded, artifacts_root)
            if not triggered:
                eligible, reason = False, "no checked failed later use of the referenced learner-visible lesson"
        options.append({"id": item["id"], "eligible": eligible, "priority": item["priority"],
                        "kind": kind, "triggered": triggered,
                        "last_selected": _last_selected(dsn, agenda_id, item["id"]),
                        "reason": reason, "investigation_id": inv_id,
                        "target_revision": p01["revision"] if p01 else 0})
    return options


def _select_and_run(dsn, agent, checker, agenda_id, state, snapshot, loaded,
                    staging_root, artifacts_root):
    charter = state["charter"]
    deadline = datetime.fromisoformat(charter["deadline"])
    if state["turns"] >= charter["max_turns"] or datetime.now(UTC) >= deadline:
        return _stop(dsn, agenda_id, state, snapshot, "hard turn/deadline cap")
    token_root, cpu_root = (charter["allocations"]["tokens"]["id"],
                            charter["allocations"]["cpu"]["id"])
    free_tokens, free_cpu = store.allocation_free(dsn, token_root), store.allocation_free(dsn, cpu_root)
    # Fixed policies keep their existing resource and ranking path. Native policies
    # use the same eligibility projection with their own CPU admission included.
    options = _opportunity_options(
        dsn, agenda_id, state, loaded, agent, artifacts_root,
        free_tokens=free_tokens, free_cpu=free_cpu)
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


def _allocation_state(dsn, allocation_id):
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT a.authorized,a.reserved,a.consumed,"
                    "COALESCE(sum(child.authorized),0) AS children "
                    "FROM allocations a LEFT JOIN allocations child ON child.parent_id=a.id "
                    "WHERE a.id=%s GROUP BY a.id",
                    (allocation_id,))
        row = cur.fetchone()
    if row is None:
        raise SettlementError("agenda allocation root is missing")
    result = {key: int(row[key]) for key in ("authorized", "reserved", "consumed")}
    result["free"] = result["authorized"] - result["reserved"] - result["consumed"] - int(row["children"])
    return result


def _policy_admissions(dsn, agenda_id):
    with db.read_connect(dsn) as conn:
        row = conn.execute("SELECT count(*) FROM rsi_decisions"
                           " WHERE subject=%s AND kind='p05.policy_admission'",
                           (agenda_id,)).fetchone()
    return int(row[0])


def _method_worker_request(item, visible, method):
    fields = ("objective", "objective_revision", "state_revision",
              "open_questions", "artifact_refs", "previous_observation")
    continuation = {**{field: visible[field] for field in fields},
                    "context_packet": visible["context_packet"]}
    return {"interface": method["interface"], "value": method["value"],
            "files": {path: raw.decode("utf-8") for path, raw in item.workspace.items()},
            "context": {"continuation": continuation, "task_digest": item.digest}}


def _prepare_start(dsn, agent, checker, agenda_id, charter, option, loaded,
                   staging_root, artifacts_root):
    item = next(entry for entry in charter["opportunities"] if entry["id"] == option["id"])
    state = _ensure_p01_state(
        dsn, agent, item, option, charter, loaded, staging_root, artifacts_root)
    if (state["revision"] != option["target_revision"] or state["status"] != "ready"
            or state["pending_decision"] is not None):
        return None, "P01 start changed while the option was being prepared"
    prepared = investigate.prepare_context(
        dsn, option["investigation_id"], target_revision=option["target_revision"],
        artifacts_root=artifacts_root)
    if "visible_input" not in prepared:
        refusal = prepared.get("context_outcome") or prepared.get("capability_outcome")
        return None, str((refusal or {}).get("reason") or "P01 could not prepare a visible input")[:512]
    organism = loaded[option["id"]][1]
    config = state["config"]
    method = prepared["visible_input"].get("capability")
    runtime = {"execution_version": ""}
    if method is not None:
        request = _method_worker_request(loaded[option["id"]][0], prepared["visible_input"],
                                         config["method"])
        plan = capability.plan_invocation(
            checker, organism, config["method"]["name"], request,
            timeout_ms=config["timeout_ms"])
        runtime = {"execution_version": plan.execution_version, **dict(plan.runtime)}
    return {
        "investigation_id": option["investigation_id"],
        "target_revision": option["target_revision"],
        "decision_id": prepared["decision_id"],
        "attempt_id": prepared["attempt_id"],
        "operation_id": prepared["operation_id"],
        "visible_input": prepared["visible_input"],
        "task": loaded[option["id"]][0].digest,
        "genome": organism.digest,
        "model": config.get("model") or "",
        "method": method,
        "runtime": runtime,
        "evaluator_version": loaded[option["id"]][0].evaluator_version,
        "limits": {key: config[key] for key in
                   ("timeout_ms", "token_ceiling", "max_steps",
                    "token_allocation", "cpu_allocation")},
    }, None


def _policy_prefix(dsn, agenda_id):
    history = export(dsn, agenda_id)
    prefix = []
    for decision in history["decisions"]:
        data = dict(decision.get("data") or {})
        if decision["kind"] == "p05.choice":
            prefix.append({"kind": "choice", "opportunity_id": data.get("opportunity_id"),
                           "turn": data.get("turn")})
        elif decision["kind"] == "p05.ack":
            observation = dict(data.get("observation") or {})
            prefix.append({"kind": "observation", "opportunity_id": data.get("opportunity_id"),
                           "status": observation.get("status"),
                           "passed": observation.get("passed")})
    return prefix


def _prepared_policy_frame(dsn, agent, checker, agenda_id, state, loaded,
                           staging_root, artifacts_root, *, free_tokens, free_cpu,
                           policy_cpu, admissions_remaining):
    charter = state["charter"]
    options = _opportunity_options(
        dsn, agenda_id, state, loaded, agent, artifacts_root,
        free_tokens=free_tokens, free_cpu=free_cpu)
    starts = {}
    for option in options:
        if not option["eligible"]:
            continue
        try:
            start, refusal = _prepare_start(
                dsn, agent, checker, agenda_id, charter, option, loaded,
                staging_root, artifacts_root)
        except (SettlementError, OSError, UnicodeError) as exc:
            start, refusal = None, str(exc)[:512]
        if refusal is not None:
            option["eligible"], option["reason"] = False, refusal
            continue
        starts[option["id"]] = start
    menu = []
    for option in options:
        item = next(entry for entry in charter["opportunities"] if entry["id"] == option["id"])
        start = starts.get(option["id"])
        row = {"opportunity_id": option["id"],
               "objective": item["objective"], "question": item["question"],
               "priority": option["priority"], "kind": option["kind"],
               "triggered": option["triggered"], "last_selected": option["last_selected"],
               "eligible": bool(start), "reason": option["reason"],
               "task": item["task_id"], "genome": item["genome_id"],
               "expected_observation": item["expected_observation"],
               "stop_condition": item["stop_condition"],
               "resource_ceilings": item["resource_ceilings"],
               "target_revision": option["target_revision"]}
        if start is not None:
            row["prepared_input_digest"] = hashlib.sha256(json.dumps(
                start["visible_input"], sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        menu.append(row)
    visible = {"objective": charter["objective"], "menu": menu,
               "prefix": _policy_prefix(dsn, agenda_id),
               "limits": {"turns_remaining": max(0, charter["max_turns"] - state["turns"]),
                          "policy_calls_remaining": admissions_remaining,
                          "tokens_remaining": free_tokens,
                          "cpu_remaining": free_cpu,
                          "policy_cpu_units": policy_cpu,
                          "deadline": charter["deadline"]}}
    return visible, starts


def _policy_identity(policy, organism, method, plan):
    return {"genome": organism.digest, "name": policy["name"],
            "interface": policy["interface"], "method_digest": method.digest,
            "timeout_ms": policy["timeout_ms"],
            "max_output_bytes": policy["max_output_bytes"],
            "execution_version": plan.execution_version,
            "runtime": dict(plan.runtime)}


def _policy_request(visible):
    return {"interface": _POLICY_INTERFACE, "value": visible, "files": {}, "context": {}}


def _lock_allocation(cur, allocation_id):
    cur.execute("SELECT authorized,reserved,consumed FROM allocations WHERE id=%s FOR UPDATE",
                (allocation_id,))
    row = cur.fetchone()
    if row is None:
        raise StaleRevision("agenda allocation root disappeared")
    result = {key: int(row[key]) for key in ("authorized", "reserved", "consumed")}
    cur.execute("SELECT COALESCE(sum(authorized),0) AS children FROM allocations WHERE parent_id=%s",
                (allocation_id,))
    children = int(cur.fetchone()["children"])
    result["free"] = result["authorized"] - result["reserved"] - result["consumed"] - children
    return result


def _commit_policy_flight(dsn, agenda_id, state, snapshot, frame_digest,
                          policy_identity, plan, resource_before, admissions_before):
    charter = state["charter"]
    revision = int(state["revision"])
    identity = hashlib.sha256(
        f"{agenda_id}:{revision}:{frame_digest}:{policy_identity['method_digest']}".encode()).hexdigest()
    operation_id = "p05-policy-" + identity[:32]
    flight = {"kind": "policy", "policy": policy_identity,
              "policy_request_digest": plan.input_digest,
              "operation_id": operation_id, "frame_digest": frame_digest,
              "policy_cpu_units": broker.exposure_schedule(
                  broker.SANDBOX_EXEC, {"timeout_ms": charter["policy"]["timeout_ms"]})[0],
              "agenda_revision": revision + 1,
              "grant_version": charter["grant_version"],
              "deadline": charter["deadline"],
              "admissions_before": admissions_before,
              "source_snapshot": {"event_epoch": snapshot["event_epoch"],
                                  "memory_revision": snapshot["memory_revision"]},
              "resource_before": resource_before}
    command = Command(
        request_id=f"p05-policy-admit:{agenda_id}:{revision}:{frame_digest}",
        payload={"agenda_id": agenda_id, "revision": revision,
                 "frame_digest": frame_digest, "operation_id": operation_id})

    def commit(cur, control):
        cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
        current = cur.fetchone()
        if current is None or int(current["revision"]) != revision:
            raise StaleRevision("agenda changed before policy admission")
        if current["status"] != "active" or current["flight"] is not None:
            raise StaleRevision("agenda no longer admits a policy flight")
        if (int(current["revision"]) + 1 != flight["agenda_revision"]
                or control["event_epoch"] != snapshot["event_epoch"]):
            raise StaleRevision("policy source snapshot changed before admission")
        if datetime.now(UTC) >= datetime.fromisoformat(charter["deadline"]):
            raise StaleRevision("agenda deadline passed before policy admission")
        if _pending_assessment(cur, agenda_id) is not None:
            raise StaleRevision("an assessment assignment is pending")
        cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1 FOR UPDATE")
        memory_row = cur.fetchone()
        if int(memory_row["revision"]) != snapshot["memory_revision"]:
            raise StaleRevision("policy memory snapshot changed before admission")
        _authority(cur, agenda_id, charter)
        cur.execute("SELECT count(*) AS admissions FROM rsi_decisions WHERE subject=%s"
                    " AND kind='p05.policy_admission'", (agenda_id,))
        admissions = int(cur.fetchone()["admissions"])
        if admissions >= charter["max_turns"]:
            raise StaleRevision("native policy admission limit is exhausted")
        for domain in ("tokens", "cpu"):
            root_id = charter["allocations"][domain]["id"]
            if _lock_allocation(cur, root_id) != resource_before[domain]:
                raise StaleRevision(f"shared {domain} root changed before policy admission")
        data = {"policy": policy_identity, "frame_digest": frame_digest,
                "operation_id": operation_id,
                "policy_request_digest": plan.input_digest,
                "source_snapshot": flight["source_snapshot"],
                "resource_before": resource_before,
                "admission": admissions + 1}
        _record(cur, agenda_id, "policy_admission", revision, data)
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,flight=%s,source_epoch=%s,"
                    "memory_revision=%s,updated_at=now() WHERE agenda_id=%s",
                    (Json(flight), snapshot["event_epoch"], snapshot["memory_revision"], agenda_id))
        return (ResultCode.APPLIED, "native policy flight persisted", flight,
                [("rsi.agenda.policy.admitted", {"agenda_id": agenda_id,
                                                  "operation_id": operation_id,
                                                  "frame_digest": frame_digest})], [])

    result = store.transact(dsn, command, commit)
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return result.data
    if result.code == ResultCode.STALE_REVISION:
        return None
    raise SettlementError(result.detail)


def _policy_operation(dsn, flight, cpu_allocation):
    operation = broker.read_operation(dsn, flight["operation_id"])
    if operation is None:
        return {"status": "absent"}
    payload = dict(operation.get("payload") or {})
    if (payload.get("effect") != broker.SANDBOX_EXEC
            or operation.get("allocation_id") != cpu_allocation
            or operation.get("execution_version") != flight["policy"]["execution_version"]):
        return {"status": "unknown", "operation": operation}
    if (not operation.get("settled")
            or operation.get("dispatch_state") not in {"observed", "reconciled"}
            or operation.get("reconcile_state") in {"conflict", "unresolved"}):
        return {"status": "pending", "operation": operation}
    receipts = store.operation_receipts(dsn, flight["operation_id"])
    if len(receipts) != 1 or not operation.get("reservation_id"):
        return {"status": "pending", "operation": operation}
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT allocation_id,amount,state FROM reservations WHERE id=%s",
                    (operation["reservation_id"],))
        reservation = cur.fetchone()
    if (reservation is None or reservation["allocation_id"] != cpu_allocation
            or reservation["state"] != "settled"):
        return {"status": "pending", "operation": operation}
    amount = int(reservation["amount"])
    cost = payload.get("_receipt_actual_cost")
    if cost is None:
        cost = amount
    if (amount != flight["policy_cpu_units"] or type(cost) is not int
            or cost < 0 or cost > amount):
        return {"status": "unknown", "operation": operation}
    return {"status": "settled", "operation": operation,
            "reservation_id": operation["reservation_id"],
            "reservation_amount": amount, "cpu_units": cost,
            "receipts": receipts}


def _policy_result(invocation, starts):
    if invocation.status != "completed":
        return None, "native policy invocation " + invocation.status
    if invocation.files:
        return None, "native policy must return no files"
    value = invocation.value
    if not isinstance(value, dict) or not isinstance(value.get("action"), str):
        return None, "native policy output must be a choose or stop object"
    if value["action"] == "choose":
        if set(value) != {"action", "opportunity_id"}:
            return None, "native policy choice has an invalid shape"
        opportunity_id = value.get("opportunity_id")
        if not isinstance(opportunity_id, str) or opportunity_id not in starts:
            return None, "native policy chose an ineligible opportunity"
        return {"action": "choose", "opportunity_id": opportunity_id}, None
    if value["action"] == "stop":
        reason = value.get("reason")
        if (set(value) != {"action", "reason"} or not isinstance(reason, str)
                or not reason.strip() or len(reason.encode("utf-8")) > 1024):
            return None, "native policy stop reason must be bounded and nonempty"
        return {"action": "stop", "reason": reason}, None
    return None, "native policy action must be choose or stop"


def _check_policy_resources(dsn, charter, flight, evidence):
    before = flight["resource_before"]
    after = {domain: _allocation_state(dsn, charter["allocations"][domain]["id"])
             for domain in ("tokens", "cpu")}
    expected_cpu = dict(before["cpu"])
    expected_cpu["consumed"] += evidence["cpu_units"]
    expected_cpu["free"] -= evidence["cpu_units"]
    if after["cpu"] != expected_cpu or after["tokens"] != before["tokens"]:
        return None
    return after


def _revalidate_policy(dsn, agent, checker, agenda_id, state, charter, loaded,
                       staging_root, artifacts_root, flight, frame, evidence):
    snapshot = _source_snapshot(dsn, state)
    if snapshot["memory_revision"] != flight["source_snapshot"]["memory_revision"]:
        return None, "memory changed while the native policy ran"
    resources = _check_policy_resources(dsn, charter, flight, evidence)
    if resources is None:
        return None, "shared agenda resources changed beyond the settled policy operation"
    admissions_remaining = max(0, charter["max_turns"] - flight["admissions_before"])
    # Reuse the pre-admission option budget; the root check accounts for the
    # policy's own reservation settlement and rejects any other resource change.
    limits = frame["visible"]["limits"]
    visible, starts = _prepared_policy_frame(
        dsn, agent, checker, agenda_id, state, loaded, staging_root, artifacts_root,
        free_tokens=limits["tokens_remaining"],
        free_cpu=limits["cpu_remaining"], policy_cpu=flight["policy_cpu_units"],
        admissions_remaining=admissions_remaining)
    if visible != frame["visible"] or starts != frame["starts"]:
        return None, "prepared opportunity menu or P01 input changed while the native policy ran"
    fresh = _source_snapshot(dsn, state)
    if (fresh["event_epoch"] != snapshot["event_epoch"]
            or fresh["memory_revision"] != snapshot["memory_revision"]):
        return None, "source frontier changed during native policy revalidation"
    if datetime.now(UTC) >= datetime.fromisoformat(charter["deadline"]):
        return None, "agenda deadline passed while the native policy ran"
    return {"snapshot": fresh, "resources": resources, "starts": starts}, None


def _finish_policy(dsn, agent, checker, agenda_id, state, loaded,
                   staging_root, artifacts_root, *, flight):
    charter = state["charter"]
    policy = charter["policy"]
    organism = _load_policy(dsn, artifacts_root, charter, allow_missing=True)
    if organism is None:
        return {"status": "pending", "reason": "pinned policy source is unavailable"}
    try:
        frame = search.load_frame(dsn, flight["frame_digest"], artifacts_root=artifacts_root)
        method = next(item for item in capability.catalogue(organism)
                      if item.name == policy["name"] and item.interface == policy["interface"])
        request = _policy_request(frame["visible"])
        plan = capability.plan_invocation(
            checker, organism, policy["name"], request,
            timeout_ms=policy["timeout_ms"], max_output_bytes=policy["max_output_bytes"])
    except (SettlementError, OSError, StopIteration) as exc:
        return {"status": "pending", "reason": "pinned policy plan is unavailable: " + str(exc)[:256]}
    identity = _policy_identity(policy, organism, method, plan)
    if (identity != flight["policy"] or plan.input_digest != flight["policy_request_digest"]
            or frame["source"].get("agenda_id") != agenda_id
            or frame["source"].get("agenda_revision") + 1 != flight["agenda_revision"]):
        return {"status": "pending", "reason": "pinned policy invocation identity no longer matches"}
    cpu_id = charter["allocations"]["cpu"]["id"]
    try:
        invocation = capability.invoke(
            dsn, checker, organism, policy["name"], request,
            operation_id=flight["operation_id"], allocation_id=cpu_id, attempt_id=None,
            staging_root=staging_root, artifacts_root=artifacts_root,
            timeout_ms=policy["timeout_ms"], max_output_bytes=policy["max_output_bytes"])
    except SettlementError as exc:
        evidence = _policy_operation(dsn, flight, cpu_id)
        if evidence["status"] == "absent":
            snapshot = _source_snapshot(dsn, state)
            return _close_policy_flight(
                dsn, agenda_id, state, flight, snapshot,
                {"kind": "policy_refusal", "operation_admitted": False,
                 "reason": "native policy admission refused: " + str(exc)[:256]},
                status="deferred", resources=None)
        return {"status": "pending", "reason": "native policy operation remains unresolved"}
    evidence = _policy_operation(dsn, flight, cpu_id)
    if evidence["status"] != "settled":
        return {"status": "pending", "reason": "native policy operation has no definitive settlement"}
    decision, refusal = _policy_result(invocation, frame["starts"])
    check, invalidation = _revalidate_policy(
        dsn, agent, checker, agenda_id, state, charter, loaded,
        staging_root, artifacts_root, flight, frame, evidence)
    if check is None:
        expired = datetime.now(UTC) >= datetime.fromisoformat(charter["deadline"])
        return _close_policy_flight(
            dsn, agenda_id, state, flight, _source_snapshot(dsn, state),
            {"kind": "policy_refusal", "reason": invalidation},
            status="stopped" if expired else "deferred", resources=None)
    snapshot, resources = check["snapshot"], check["resources"]
    policy_result = {"status": "completed", "value": invocation.value,
                     "output_digest": invocation.output_digest,
                     "operation_id": flight["operation_id"]}
    if refusal is not None:
        return _close_policy_flight(
            dsn, agenda_id, state, flight, snapshot,
            {"kind": "policy_refusal", "reason": refusal,
             "policy_result": policy_result},
            status="deferred", resources=resources)
    if decision["action"] == "stop":
        return _close_policy_flight(
            dsn, agenda_id, state, flight, snapshot,
            {"kind": "policy_stop", "reason": decision["reason"],
             "policy_result": policy_result},
            status="stopped", resources=resources)
    opportunity_id = decision["opportunity_id"]
    return _commit_policy_choice(
        dsn, agent, checker, agenda_id, state, loaded, staging_root, artifacts_root,
        flight, frame, opportunity_id, snapshot, resources, policy_result)


def _lock_policy_transition(cur, control, agenda_id, revision, flight, snapshot,
                            resources, *, require_authority, allow_expired):
    cur.execute("SELECT * FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE", (agenda_id,))
    current = cur.fetchone()
    if (current is None or int(current["revision"]) != revision
            or current["flight"] != flight or current["status"] != "active"):
        raise StaleRevision("native policy flight changed before transition")
    if current["charter"]["deadline"] != flight["deadline"]:
        raise StaleRevision("native policy deadline changed")
    expired = datetime.now(UTC) >= datetime.fromisoformat(flight["deadline"])
    if expired and not allow_expired:
        raise StaleRevision("agenda deadline passed before policy transition")
    if control["event_epoch"] != snapshot["event_epoch"]:
        raise StaleRevision("agenda event frontier changed before policy transition")
    cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1 FOR UPDATE")
    memory_row = cur.fetchone()
    if int(memory_row["revision"]) != snapshot["memory_revision"]:
        raise StaleRevision("memory changed before policy transition")
    if require_authority:
        _authority(cur, agenda_id, current["charter"])
    if resources is not None:
        for domain in ("tokens", "cpu"):
            if (_lock_allocation(cur, current["charter"]["allocations"][domain]["id"])
                    != resources[domain]):
                raise StaleRevision(f"shared {domain} root changed before policy transition")
    return current


def _close_policy_flight(dsn, agenda_id, state, flight, snapshot, decision,
                         *, status, resources):
    revision = int(state["revision"])
    result_status = "stopped" if status == "stopped" else "deferred"
    decision = {**decision, "operation_admitted": decision.get("operation_admitted", True)}
    data = {**flight, **decision, "source_snapshot_after_policy": {
        "event_epoch": snapshot["event_epoch"],
        "memory_revision": snapshot["memory_revision"]}}
    cmd = Command(request_id=f"p05-{decision['kind']}:{agenda_id}:{revision}",
                  payload={"agenda_id": agenda_id, "revision": revision,
                           "operation_id": flight["operation_id"], "decision": decision})

    def close(cur, control):
        _lock_policy_transition(
            cur, control, agenda_id, revision, flight, snapshot, resources,
            require_authority=False, allow_expired=status == "stopped")
        _record(cur, agenda_id, decision["kind"], revision, data)
        result = {"status": result_status, **decision, "frame_digest": flight["frame_digest"]}
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,status=%s,flight=NULL,"
                    "source_epoch=%s,memory_revision=%s,last_result=%s,updated_at=now() "
                    "WHERE agenda_id=%s",
                    ("stopped" if status == "stopped" else "active",
                     snapshot["event_epoch"], snapshot["memory_revision"], Json(result), agenda_id))
        return (ResultCode.APPLIED, "native policy flight closed", result,
                [("rsi.agenda.policy." + ("stopped" if status == "stopped" else "refused"),
                  {"agenda_id": agenda_id, "operation_id": flight["operation_id"]})], [])

    result = store.transact(dsn, cmd, close)
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return result.data
    if result.code == ResultCode.STALE_REVISION:
        return {"status": "stale", "reason": result.detail}
    raise SettlementError(result.detail)


def _commit_policy_choice(dsn, agent, checker, agenda_id, state, loaded,
                          staging_root, artifacts_root, flight, frame,
                          opportunity_id, snapshot, resources, policy_result):
    revision = int(state["revision"])
    start = frame["starts"][opportunity_id]
    choice_id = _choice_id(agenda_id, revision, "choice")
    choice_flight = {**flight, "kind": "work", "opportunity_id": opportunity_id,
                     "operation_admitted": True,
                     "investigation_id": start["investigation_id"],
                     "target_revision": start["target_revision"],
                     "choice_id": choice_id, "start": start,
                     "source_snapshot": {"event_epoch": snapshot["event_epoch"],
                                         "memory_revision": snapshot["memory_revision"]},
                     "resource_after_policy": resources,
                     "policy_result": policy_result}
    data = {"opportunity_id": opportunity_id, "investigation_id": start["investigation_id"],
            "target_revision": start["target_revision"], "choice_id": choice_id,
            "turn": int(state["turns"]) + 1, "policy": flight["policy"],
            "frame_digest": flight["frame_digest"], "operation_id": flight["operation_id"],
            "operation_admitted": True, "policy_result": policy_result,
            "menu": frame["visible"]["menu"],
            "source_snapshot": choice_flight["source_snapshot"]}
    cmd = Command(request_id=f"p05-policy-choice:{agenda_id}:{revision}:{choice_id}",
                  payload={"agenda_id": agenda_id, "revision": revision,
                           "choice_id": choice_id, "opportunity_id": opportunity_id})

    def commit(cur, control):
        current = _lock_policy_transition(
            cur, control, agenda_id, revision, flight, snapshot, resources,
            require_authority=True, allow_expired=False)
        if _pending_assessment(cur, agenda_id) is not None:
            raise StaleRevision("an assessment assignment is pending")
        cur.execute("SELECT revision,status,pending_decision_id FROM rsi_investigations "
                    "WHERE investigation_id=%s FOR UPDATE", (start["investigation_id"],))
        p01 = cur.fetchone()
        if (p01 is None or int(p01["revision"]) != int(start["target_revision"])
                or p01["status"] != "ready" or p01["pending_decision_id"] is not None):
            raise StaleRevision("selected P01 start changed before policy choice")
        _record(cur, agenda_id, "choice", revision, data)
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,turns=turns+1,flight=%s,"
                    "source_epoch=%s,memory_revision=%s,updated_at=now() WHERE agenda_id=%s",
                    (Json(choice_flight), snapshot["event_epoch"], snapshot["memory_revision"], agenda_id))
        return (ResultCode.APPLIED, "native policy choice advanced to P01 work", choice_flight,
                [("rsi.agenda.choice", {"agenda_id": agenda_id,
                                          "opportunity_id": opportunity_id})], [])

    result = store.transact(dsn, cmd, commit)
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return _finish(dsn, agent, checker, agenda_id, _row(dsn, agenda_id), loaded,
                       staging_root, artifacts_root, flight=result.data)
    if result.code == ResultCode.STALE_REVISION:
        if "deadline passed" in result.detail:
            current = _row(dsn, agenda_id)
            return _close_policy_flight(
                dsn, agenda_id, current, flight, _source_snapshot(dsn, current),
                {"kind": "policy_refusal", "reason": result.detail},
                status="stopped", resources=None)
        return {"status": "stale", "reason": result.detail}
    if result.code in (ResultCode.INVALID_INPUT, ResultCode.UNAUTHORIZED):
        current = _row(dsn, agenda_id)
        return _close_policy_flight(
            dsn, agenda_id, current, flight, _source_snapshot(dsn, current),
            {"kind": "policy_refusal", "reason": "agenda grant no longer authorizes P01 admission"},
            status="stopped", resources=None)
    raise SettlementError(result.detail)


def _select_with_policy(dsn, agent, checker, agenda_id, state, snapshot, loaded,
                        policy_genome, staging_root, artifacts_root):
    charter = state["charter"]
    if (state["turns"] >= charter["max_turns"]
            or datetime.now(UTC) >= datetime.fromisoformat(charter["deadline"])):
        return _stop(dsn, agenda_id, state, snapshot, "hard turn/deadline cap")
    admissions = _policy_admissions(dsn, agenda_id)
    if admissions >= charter["max_turns"]:
        return _stop(dsn, agenda_id, state, snapshot, "native policy admission limit reached")
    if policy_genome is None:
        return _defer(dsn, agenda_id, state, snapshot,
                      [{"eligible": False, "reason": "native policy source is unavailable"}])
    policy = charter["policy"]
    method = next((item for item in capability.catalogue(policy_genome)
                   if item.name == policy["name"] and item.interface == policy["interface"]), None)
    if method is None:
        return _defer(dsn, agenda_id, state, snapshot,
                      [{"eligible": False, "reason": "native policy interface is unavailable"}])
    policy_cpu = broker.exposure_schedule(
        broker.SANDBOX_EXEC, {"timeout_ms": policy["timeout_ms"]})[0]
    token_id, cpu_id = (charter["allocations"]["tokens"]["id"],
                        charter["allocations"]["cpu"]["id"])
    resource_before = {"tokens": _allocation_state(dsn, token_id),
                       "cpu": _allocation_state(dsn, cpu_id)}
    if policy_cpu > resource_before["cpu"]["free"]:
        return _defer(dsn, agenda_id, state, snapshot,
                      [{"eligible": False, "reason": "shared CPU root cannot cover native policy exposure"}])
    admissions_remaining = charter["max_turns"] - admissions
    visible, starts = _prepared_policy_frame(
        dsn, agent, checker, agenda_id, state, loaded, staging_root, artifacts_root,
        free_tokens=resource_before["tokens"]["free"],
        free_cpu=resource_before["cpu"]["free"] - policy_cpu,
        policy_cpu=policy_cpu, admissions_remaining=admissions_remaining)
    if not starts:
        return _defer(dsn, agenda_id, state, snapshot, visible["menu"])
    prepared_snapshot = _source_snapshot(dsn, state)
    source = {"agenda_id": agenda_id, "agenda_revision": state["revision"],
              "event_epoch": prepared_snapshot["event_epoch"],
              "memory_revision": prepared_snapshot["memory_revision"],
              "policy_admissions": admissions}
    try:
        frame_digest = search.publish_frame(
            dsn, visible, starts, source,
            staging_root=staging_root, artifacts_root=artifacts_root)
        frame = search.load_frame(dsn, frame_digest, artifacts_root=artifacts_root)
    except (SettlementError, OSError) as exc:
        return _defer(dsn, agenda_id, state, snapshot,
                      [{"eligible": False, "reason": "prepared policy frame unavailable: " + str(exc)[:256]}])
    current_resources = {"tokens": _allocation_state(dsn, token_id),
                         "cpu": _allocation_state(dsn, cpu_id)}
    if current_resources != resource_before:
        return {"status": "stale", "reason": "shared agenda resources changed while the frame was published"}
    rechecked_visible, rechecked_starts = _prepared_policy_frame(
        dsn, agent, checker, agenda_id, state, loaded, staging_root, artifacts_root,
        free_tokens=current_resources["tokens"]["free"],
        free_cpu=current_resources["cpu"]["free"] - policy_cpu,
        policy_cpu=policy_cpu, admissions_remaining=admissions_remaining)
    current_snapshot = _source_snapshot(dsn, state)
    if (rechecked_visible != frame["visible"] or rechecked_starts != frame["starts"]
            or current_snapshot["memory_revision"] != prepared_snapshot["memory_revision"]):
        return {"status": "stale", "reason": "prepared inputs changed before policy admission"}
    try:
        plan = capability.plan_invocation(
            checker, policy_genome, policy["name"], _policy_request(frame["visible"]),
            timeout_ms=policy["timeout_ms"], max_output_bytes=policy["max_output_bytes"])
    except SettlementError as exc:
        return _defer(dsn, agenda_id, state, current_snapshot,
                      [{"eligible": False, "reason": "native policy plan refused: " + str(exc)[:256]}])
    identity = _policy_identity(policy, policy_genome, method, plan)
    flight = _commit_policy_flight(
        dsn, agenda_id, state, current_snapshot, frame_digest, identity, plan,
        current_resources, admissions)
    if flight is None:
        current = _row(dsn, agenda_id)
        if current is not None and current["flight"] is not None:
            return _finish(dsn, agent, checker, agenda_id, current, loaded,
                           staging_root, artifacts_root, flight=current["flight"])
        return {"status": "stale", "reason": "source snapshot changed before policy admission"}
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
    policy_genome = _load_policy(dsn, artifacts_root, charter, allow_missing=True)
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
    if isinstance(charter["policy"], dict):
        return _select_with_policy(
            dsn, agent, checker, agenda_id, state, snapshot, loaded,
            policy_genome, staging_root, artifacts_root)
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
