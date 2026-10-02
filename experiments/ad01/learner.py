"""Model-backed AD01 learner at the gateway seam.

The learner receives the accumulated packet (charter, visible
opportunities, prior observations with failures, retained members,
remaining budgets) and returns one section-3 action through broker
model inference. Recording doubles serve the same seam in order.
"""

from __future__ import annotations

import json
from typing import Any

from . import packet as _packet


class LearnerRefused(Exception):
    pass


LEARNER_INSTRUCTION = (
    "Reply with ONLY one JSON object and no other text: no prose, "
    "no explanation, no code fences. next_action.kind must always be "
    "present: diagnostic, development, or stop. next_action.diagnostic "
    "must be exactly software or graph. basis_references must be "
    "observation_id strings copied from the observations list exactly, "
    "character for character, never truncated, abbreviated, invented, or "
    "section names like charter or remaining. requested_resources must "
    "be an object mapping a resource name to a nonnegative integer "
    "amount, e.g. {\"queries\": 3}. When curriculum_item is not null, "
    "next_action.task_id must equal curriculum_item. When "
    "curriculum_item is null, next_action.task_id must be one of "
    "visible_opportunities.")


def _extract_json(text: str) -> dict | None:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        lines = lines[1:] if len(lines) > 1 else []
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


class RecordingGatewayAdapter:
    label = "AD01-RECORDING-GATEWAY"

    def __init__(self, scripts: list):
        from settlement.gateway import Usage
        self._scripts = [dict(s) for s in scripts]
        self._fallback_usage = Usage(input_tokens=5, output_tokens=5)
        self.calls: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def _script(self):
        if len(self.calls) <= len(self._scripts):
            return self._scripts[len(self.calls) - 1]
        return self._scripts[-1]

    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        self.calls.append(request)
        script = self._script()
        usage = script.get("usage", None)
        if usage is None:
            usage = self._fallback_usage
        elif isinstance(usage, dict):
            usage = Usage(**usage)
        return ModelResponse(request.operation_id, script.get("text", ""),
                             dict(script.get("meta", {})), usage, "stop")

    def cancel(self, operation_id):
        return False


def learner_request(charter: dict, visible: list, experience: dict,
                    retained: list, remaining: dict,
                    curriculum: str | None,
                    prior_failure: dict | None = None) -> dict:
    packet = _packet.decision_packet(
        charter=charter, visible=visible, experience=experience,
        retained=retained, remaining=remaining, curriculum=curriculum,
        boundary=None)
    if prior_failure is not None:
        packet["prior_failure"] = _packet._strip_value(
            dict(prior_failure))
    return packet


def visible_prompt(charter: dict, visible: list, experience: dict,
                   retained: list, remaining: dict,
                   curriculum: str | None,
                   prior_failure: dict | None = None) -> str:
    from . import packet as _pkt
    cleaned_obs = [o for o in (experience or {}).get("observations", [])
                   if not _pkt._is_sealed_observation(o)]
    cleaned_exp = dict(experience or {}, observations=cleaned_obs)
    packet = _pkt.decision_packet(
        charter=charter, visible=visible, experience=cleaned_exp,
        retained=retained, remaining=remaining, curriculum=curriculum,
        boundary=None)
    if prior_failure is not None:
        packet["prior_failure"] = _pkt._strip_value(dict(prior_failure))
    return LEARNER_INSTRUCTION + "\n" + json.dumps(packet, sort_keys=True)


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def record_exposure(dsn: str, batch_id: str, exposed_to: str) -> dict:
    if not batch_id or not exposed_to:
        raise ValueError("exposure needs batch and consumer")
    with _read_conn(dsn) as conn:
        conn.execute(
            "INSERT INTO s09_assessment_exposure"
            " (batch_id, exposed_to, retired_at)"
            " VALUES (%s, %s, now())"
            " ON CONFLICT (batch_id, exposed_to)"
            " DO UPDATE SET retired_at = COALESCE("
            " s09_assessment_exposure.retired_at, now())",
            (batch_id, exposed_to))
        conn.commit()
    return {"batch_id": batch_id, "exposed_to": exposed_to,
            "retired": True}


def is_retired(dsn: str, batch_id: str) -> bool:
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT 1 FROM s09_assessment_exposure"
            " WHERE batch_id = %s AND retired_at IS NOT NULL",
            (batch_id,)).fetchone()
        conn.commit()
        return row is not None


def require_unretired(dsn: str, batch_id: str, consumer: str) -> None:
    if is_retired(dsn, batch_id):
        raise LearnerRefused(
            "assessment batch %r retired for descendant %r"
            % (batch_id, consumer))


def validate_proposal(proposal: dict) -> dict:
    if not isinstance(proposal, dict):
        raise LearnerRefused("learner response is not an object")
    action = proposal.get("next_action")
    if not isinstance(action, dict) or action.get("kind") not in (
            "diagnostic", "development", "use_method", "stop"):
        raise LearnerRefused("unknown action kind")
    if action["kind"] == "use_method" and not isinstance(action.get("method_id"), str):
        raise LearnerRefused("use_method needs a method_id")
    if action["kind"] != "stop" and not isinstance(action.get("task_id"), str):
        raise LearnerRefused("action needs a task_id")
    if "max_queries" in action and (
            type(action["max_queries"]) is not int or action["max_queries"] < 0):
        raise LearnerRefused("max_queries must be a nonnegative integer")
    if "diagnostic" in action and action["diagnostic"] not in (
            "software", "graph", "diagnostic_resolves"):
        raise LearnerRefused("unknown diagnostic")
    resources = proposal.get("requested_resources", {})
    if not isinstance(resources, dict) or any(
            not isinstance(k, str) or type(v) is not int or v < 0
            for k, v in resources.items()):
        raise LearnerRefused("requested_resources must contain nonnegative integers")
    refs = proposal.get("basis_references", [])
    if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs):
        raise LearnerRefused("basis_references must be a list of strings")
    return proposal


def _learner_op_id(cid: str, seq: int, attempt: int = 0) -> str:
    base = "ad01-%s-learner-%d" % (cid, seq)
    return base if not attempt else "%s-c%d" % (base, attempt)


def _settled_text(dsn: str, operation_id: str) -> str | None:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s"
                        " AND receipt_identity = %s AND outcome = 'success'",
                        (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        return None
    return str(dict(row.get("content") or {}).get("text", ""))


def model_propose(dsn: str, *, cid: str, seq: int, gateway: Any,
                  model: str, charter: dict, visible: list,
                  experience: dict, retained: list, remaining: dict,
                  curriculum: str | None, allocation_id: str,
                  prior_failure: dict | None = None,
                  attempt: int = 0) -> dict:
    from settlement import broker
    from settlement.common import ResultCode
    from .trajectory import reasoning_effort
    operation_id = _learner_op_id(cid, seq, attempt)
    settled = _settled_text(dsn, operation_id)
    if settled is None:
        prompt = visible_prompt(
            charter, visible, experience, retained, remaining,
            curriculum, prior_failure)
        ensured = broker.ensure_operation(
            dsn, operation_id=operation_id,
            effect=broker.MODEL_INFERENCE,
            payload={"model": model,
                     "messages": [{"role": "user", "content": prompt}],
                     "max_output_tokens": 2048, "deadline_ms": 300_000,
                     "reasoning_effort": reasoning_effort()},
            allocation_id=allocation_id)
        if ensured.code not in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED):
            raise LearnerRefused("learner call not admitted: %s"
                                 % ensured.detail)
        broker.dispatch_operation(dsn, operation_id, launchers={},
                                  gateway=gateway)
        settled = _settled_text(dsn, operation_id)
        if settled is None:
            raise LearnerRefused(
                "learner call %s left no settled response" % operation_id)
    proposal = _extract_json(settled)
    if proposal is None:
        raise LearnerRefused("learner response is not JSON")
    return validate_proposal(proposal)


def visible_opportunities(world: int) -> list:
    from . import worlds
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    return sorted(
        t for d in membership[str(world)].get("dev", {}).values()
        for t in d)


def curriculum_item(world: int, arm: str, seq: int) -> str | None:
    if arm != "R":
        return None
    from . import rotation
    schedule = rotation.r_schedule(world)
    if seq >= len(schedule):
        return None
    return schedule[seq]["task_id"]


def propose_from_model(dsn: str, *, cid: str, gateway: Any, model: str,
                       charter: dict, world: int, arm: str,
                       allocation_id: str):
    def _propose(experience: dict, asked: dict) -> dict:
        seq = experience["boundary"]["seq"]
        return model_propose(
            dsn, cid=cid, seq=seq, gateway=gateway, model=model,
            charter=charter, visible=visible_opportunities(world),
            experience=experience,
            retained=list(experience.get("retained", [])),
            remaining=dict(experience.get("remaining", {})),
            curriculum=curriculum_item(world, arm, seq),
            allocation_id=allocation_id,
            prior_failure=experience.get("prior_failure"),
            attempt=int(experience.get("correction_attempt") or 0))

    return _propose
