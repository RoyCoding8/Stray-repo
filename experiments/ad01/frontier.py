"""M2 durable frontier of admissible investigation work.

The study freezes mission plus environments. It never dictates the next
investigation. The executable program chooses its own next work from this
frontier through its STEP bytes, inside explicit authority. The frontier,
observations, pending effects, outcomes and obligations persist in one
JSON store so an investigation survives a restart. Storage exists only
for restart survival.

Replay reveals a recorded outcome only where the stored identity matches
exactly. Each recorded replay charges one query. Anything unseen returns
unsupported. Prediction is a separate
evidence class and never counts as a replay result. Readiness is
event-driven through ready_events. This module starts no loops, timers
or schedulers.
"""

from __future__ import annotations

import hashlib
import json
import os

FRONTIER_VERSION = "invl02-frontier-v2"
NAMESPACE = "invl02_m2"

OPERATE = "operate"
IMPROVE = "improve"
PURPOSES = (OPERATE, IMPROVE)

OPERATE_KINDS = (
    "investigate",
    "probe",
    "construct",
    "reuse",
    "revise",
    "wait",
    "stop",
)

PACKAGE_ORIGINS = ("authored-control", "acquired")
EVIDENCE_VERSION = "invl02-evidence-v2"
EVIDENCE_KINDS = (
    "gateway-dispatch",
    "child-execution",
    "e0-run",
    "e12-run",
    "e3-run",
    "m4-observation",
)
EVIDENCE_OUTCOMES = ("success", "failure", "unknown", "unresolved")
PARSE_OUTCOMES = (
    "pending", "accepted", "parse-failed", "route-refused",
    "transport-error", "too-long", "empty",
)
SOURCE_ANCHOR_VERSION = "invl02-source-anchor-v1"
RESOURCE_KEYS = frozenset(("queries", "steps"))

INSTRUMENTS = ("boolean-rule-v1", "deliberation")


class Refused(Exception):
    pass


def canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


EVIDENCE_RESPONSE_FIELDS = (
    "requested_model", "returned_model", "endpoint", "provider", "tier",
    "requested_output_cap", "response_digest", "prompt_digest", "raw_prompt",
    "raw_response", "stop_reason", "usage", "billed", "charge_units",
    "route_error", "cost_blocked", "response_received", "response_status",
    "exception_class", "exception_reason", "diagnosis",
)
EVIDENCE_USAGE_COUNT_FIELDS = (
    "input_tokens", "output_tokens", "charge_units", "charge_scale",
)
EVIDENCE_USAGE_BOOL_FIELDS = ("provider_enforced_ceiling", "billed")


PACKAGE_MANIFEST_FIELDS = (
    "origin", "source_kind", "op_source", "imp_source", "parent_digest",
    "version", "control_id", "authority_request", "obligations", "channel",
    "provenance",
)


def package_manifest(package: dict) -> dict:
    if not isinstance(package, dict):
        raise Refused("package manifest must be an object")
    try:
        return {key: package[key] for key in PACKAGE_MANIFEST_FIELDS}
    except KeyError as exc:
        raise Refused("package manifest misses %s" % exc.args[0]) from exc


def package_digest(op_source_or_package, imp_source=None, parent_digest=None,
                   version=None, control_id=None, provenance_digest=None,
                   *, origin="authored-control", source_kind="fixed-menu",
                   authority_request=None) -> str:
    if isinstance(op_source_or_package, dict):
        manifest = package_manifest(op_source_or_package)
    else:
        manifest = {
            "origin": origin,
            "source_kind": source_kind,
            "op_source": op_source_or_package,
            "imp_source": imp_source,
            "parent_digest": parent_digest,
            "version": version,
            "control_id": control_id,
            "authority_request": dict(authority_request or {
                "queries": 16, "steps": 12}),
            "obligations": ["re-test probe divergence on new seeds"],
            "channel": "invl02-improve-v1",
            "provenance": (None if provenance_digest is None else
                           {"digest": provenance_digest}),
        }
    return _digest_text(canonical(manifest))


def source_digest(source: str) -> str:
    return _digest_text(source)


def _evidence_identity_digest(record: dict) -> str:
    keys = (
        "version", "kind", "operation_id", "attempt", "outcome", "arm",
        "task_id", "receipt_identity",
        "source_digest", "artifact_digest", "input_digest", "result_digest",
        "package_digest", "parent_digest", "round",
        "dispatch_evidence_digest", "raw_payload_digest", "route_digest",
    )
    identity = {key: record.get(key) for key in keys}
    for key in EVIDENCE_RESPONSE_FIELDS:
        identity[key] = record.get(key)
    for key in ("driver_digest", "operation_payload_digest",
                "parse_outcome", "accepted_candidate_digest"):
        if key in record:
            identity[key] = record[key]
    return _digest_text(canonical(identity))


def make_evidence_record(kind: str, operation_id: str, outcome: str, *,
                         attempt: int | None = None,
                         receipt_identity: str | None = None,
                         arm: str | None = None,
                         task_id: str | None = None,
                         source_digest: str | None = None,
                         artifact_digest: str | None = None,
                         input_digest: str | None = None,
                         result_digest: str | None = None,
                         package_digest: str | None = None,
                         parent_digest: str | None = None,
                         round_no: int | None = None,
                         dispatch_evidence_digest: str | None = None,
                         driver_digest: str | None = None,
                         operation_payload_digest: str | None = None,
                         parse_outcome: str | None = None,
                         accepted_candidate_digest: str | None = None,
                         details: dict | None = None) -> dict:
    if kind not in EVIDENCE_KINDS or outcome not in EVIDENCE_OUTCOMES:
        raise Refused("evidence kind or outcome is unknown")
    if not isinstance(operation_id, str) or not operation_id:
        raise Refused("evidence needs an operation identity")
    details = dict(details or {})
    raw_payload = details.get("raw_payload")
    if isinstance(raw_payload, dict):
        if driver_digest is None:
            driver_digest = raw_payload.get("driver_digest")
        if operation_payload_digest is None:
            operation_payload = raw_payload.get("operation_payload")
            if isinstance(operation_payload, dict):
                operation_payload_digest = _digest_text(canonical(
                    operation_payload))
    raw_payload_digest = _digest_text(canonical(raw_payload))
    route_digest = _digest_text(canonical(details.get("route")))
    identity = {
        "version": EVIDENCE_VERSION,
        "kind": kind,
        "operation_id": operation_id,
        "attempt": attempt,
        "outcome": outcome,
        "arm": arm,
        "task_id": task_id,
        "source_digest": source_digest,
        "artifact_digest": artifact_digest,
        "input_digest": input_digest,
        "result_digest": result_digest,
        "package_digest": package_digest,
        "parent_digest": parent_digest,
        "round": round_no,
        "dispatch_evidence_digest": dispatch_evidence_digest,
        "driver_digest": driver_digest,
        "operation_payload_digest": operation_payload_digest,
        "raw_payload_digest": raw_payload_digest,
        "route_digest": route_digest,
    }
    if (dispatch_evidence_digest is not None
            or parse_outcome is not None
            or accepted_candidate_digest is not None):
        identity["parse_outcome"] = parse_outcome
        identity["accepted_candidate_digest"] = accepted_candidate_digest
    receipt = receipt_identity or "evidence:%s" % _digest_text(canonical(identity))
    identity["receipt_identity"] = receipt
    evidence_digest = _evidence_identity_digest(identity)
    return {
        **identity,
        "evidence_digest": evidence_digest,
        "raw_payload_digest": raw_payload_digest,
        "details": details,
    }


def _valid_usage_value(value, *, boolean: bool) -> bool:
    if value == "unknown":
        return True
    return type(value) is bool if boolean else _is_count(value)


def _validate_usage_snapshot(usage, *, label: str) -> None:
    if not isinstance(usage, dict):
        raise Refused("evidence %s usage is malformed" % label)
    for key in EVIDENCE_USAGE_COUNT_FIELDS:
        if key in usage and not _valid_usage_value(
                usage[key], boolean=False):
            raise Refused("evidence %s usage %s is malformed" % (label, key))
    for key in EVIDENCE_USAGE_BOOL_FIELDS:
        if key in usage and not _valid_usage_value(usage[key], boolean=True):
            raise Refused("evidence %s usage %s is malformed" % (label, key))


def _validate_gateway_usage(record: dict) -> None:
    for key in ("charge_units", "billed"):
        if key in record and not _valid_usage_value(
                record[key], boolean=key == "billed"):
            raise Refused("evidence gateway %s is malformed" % key)
    if "usage" in record:
        usage = record["usage"]
        _validate_usage_snapshot(usage, label="gateway")
        for key in ("charge_units", "billed"):
            if key in record and usage.get(key) != record[key]:
                raise Refused(
                    "dispatch evidence gateway %s does not match usage" % key)
    details = record.get("details")
    if isinstance(details, dict) and "usage" in details:
        detail_usage = details["usage"]
        _validate_usage_snapshot(detail_usage, label="gateway details")
        if "usage" in record:
            for key in ("charge_units", "billed"):
                if (key in record and key in record["usage"]
                        and record["usage"][key] != detail_usage.get(key)):
                    raise Refused(
                        "dispatch evidence gateway %s does not match details usage"
                        % key)


def validate_evidence_record(record: dict, *, kind: str | None = None,
                            outcome: str | None = None) -> dict:
    if not isinstance(record, dict):
        raise Refused("evidence record must be an object")
    required = {
        "version", "kind", "operation_id", "attempt", "outcome", "arm",
        "task_id",
        "source_digest", "artifact_digest", "input_digest", "result_digest",
        "package_digest", "parent_digest", "round",
        "dispatch_evidence_digest", "evidence_digest", "receipt_identity",
        "raw_payload_digest", "route_digest", "details",
    }
    if required - set(record):
        raise Refused("evidence record is incomplete")
    if record.get("version") != EVIDENCE_VERSION:
        raise Refused("evidence record uses an unknown version")
    if record.get("kind") not in EVIDENCE_KINDS or (
            kind is not None and record.get("kind") != kind):
        raise Refused("evidence record kind mismatch")
    if record.get("outcome") not in EVIDENCE_OUTCOMES or (
            outcome is not None and record.get("outcome") != outcome):
        raise Refused("evidence record outcome mismatch")
    if not isinstance(record.get("operation_id"), str) or not record[
            "operation_id"]:
        raise Refused("evidence record operation identity mismatch")
    if not isinstance(record.get("receipt_identity"), str) or not record[
            "receipt_identity"]:
        raise Refused("evidence record receipt identity mismatch")
    for key in ("arm", "task_id"):
        value = record.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            raise Refused("evidence record %s is malformed" % key)
    for key in ("source_digest", "artifact_digest", "input_digest",
                "result_digest", "package_digest", "parent_digest",
                "dispatch_evidence_digest", "driver_digest",
                "operation_payload_digest", "route_digest",
                "accepted_candidate_digest"):
        value = record.get(key)
        if value is not None and (not isinstance(value, str)
                                  or len(value) != 64
                                  or any(character not in "0123456789abcdef"
                                         for character in value)):
            raise Refused("evidence record %s is malformed" % key)
    if ("parse_outcome" in record and record.get("parse_outcome") is not None
            and record.get("parse_outcome") not in PARSE_OUTCOMES):
        raise Refused("evidence record parse outcome is malformed")
    if record.get("dispatch_evidence_digest") is not None and not {
            "parse_outcome", "accepted_candidate_digest"} <= set(record):
        raise Refused("evidence finalization identity is incomplete")
    if record.get("attempt") is not None and (
            type(record.get("attempt")) is not int
            or record.get("attempt") < 1):
        raise Refused("evidence record attempt is malformed")
    if record.get("round") is not None and (
            type(record.get("round")) is not int
            or record.get("round") < 0):
        raise Refused("evidence record round is malformed")
    details = record.get("details")
    if not isinstance(details, dict):
        raise Refused("evidence record details are malformed")
    if record.get("kind") == "gateway-dispatch":
        _validate_gateway_usage(record)
    if details.get("route") is not None and not isinstance(
            details.get("route"), dict):
        raise Refused("evidence record route is malformed")
    if record.get("raw_payload_digest") != _digest_text(canonical(
            details.get("raw_payload"))):
        raise Refused("evidence record raw payload digest mismatch")
    if record.get("route_digest") != _digest_text(canonical(
            details.get("route"))):
        raise Refused("evidence record route digest mismatch")
    if record.get("evidence_digest") != _evidence_identity_digest(record):
        raise Refused("evidence record identity digest mismatch")
    return record


def environment_digest(environments: list) -> str:
    return _digest_text(canonical(list(environments)))


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def _resource_delta(requested: dict, *, require_charge: bool = False) -> dict:
    if (not isinstance(requested, dict)
            or set(requested) - RESOURCE_KEYS
            or any(not _is_count(value) for value in requested.values())):
        raise Refused("requested resources are malformed")
    projection = {key: int(requested[key]) for key in sorted(requested)}
    if require_charge and (not projection or not any(projection.values())):
        raise Refused("charged resource projection must be nonzero")
    return projection


def _effect_resources(effect: dict) -> dict:
    charged = effect.get("charged_resources")
    if charged is None:
        if effect.get("charged") is True:
            raise Refused("charged resource projection is missing")
        return {}
    return _resource_delta(
        charged, require_charge=effect.get("charged") is True)


ROUND_RESULT_FIELDS = ("round", "candidate", "log", "observations", "receipts")
REVISION_IDENTITY_FIELDS = (
    "package_digest", "parent_digest", "imp_digest", "response_digest",
    "provenance_digest", "acquisition_evidence_digest", "acquisition_round",
    "origin", "source_kind", "arm", "round", "accepted", "retained", "active",
)


def round_result_digest(result: dict) -> str:
    return _digest_text(canonical({key: result.get(key)
                                   for key in ROUND_RESULT_FIELDS}))


def validate_package(package: dict, *, grant: dict) -> dict:
    if not isinstance(package, dict):
        raise Refused("revision candidate is not an object")
    for key in ("control_id", "origin", "source_kind", "op_source", "imp_source",
                "op_digest", "imp_digest", "package_digest",
                "parent_digest", "version", "authority_request",
                "obligations", "channel", "provenance", "provenance_digest"):
        if key not in package:
            raise Refused("revision candidate misses %s" % key)
    if package["origin"] not in PACKAGE_ORIGINS:
        raise Refused("unknown package origin %r" % (
            package.get("origin"),))
    if not isinstance(package["control_id"], str) or not package["control_id"]:
        raise Refused("revision candidate has no control identity")
    if not isinstance(package["source_kind"], str) or not package["source_kind"]:
        raise Refused("revision candidate has no source kind")
    if (not isinstance(package["obligations"], list)
            or any(not isinstance(item, str) or not item
                   for item in package["obligations"])):
        raise Refused("revision candidate obligations are malformed")
    if not isinstance(package["channel"], str) or not package["channel"]:
        raise Refused("revision candidate has no channel")
    if package["origin"] == "authored-control":
        if package["source_kind"] != "fixed-menu":
            raise Refused("authored-control requires fixed-menu source kind")
        if package["provenance"] is not None or package["provenance_digest"] is not None:
            raise Refused("authored-control cannot carry model provenance")
    elif package["origin"] == "acquired":
        if package["source_kind"] != "model-response":
            raise Refused("acquired package requires model-response source kind")
        if not isinstance(package["provenance"], dict):
            raise Refused("acquired package requires provenance")
    for key in ("op_source", "imp_source"):
        if not isinstance(package[key], str) or not package[key].strip():
            raise Refused("revision candidate holds no %s bytes" % key)
    if package["op_digest"] != source_digest(package["op_source"]):
        raise Refused("operational bytes do not match their digest")
    if package["imp_digest"] != source_digest(package["imp_source"]):
        raise Refused("improvement bytes do not match their digest")
    provenance = package["provenance"]
    expected_provenance_digest = (
        None if provenance is None else _digest_text(canonical(provenance)))
    if package["provenance_digest"] != expected_provenance_digest:
        raise Refused("package provenance does not match its digest")
    if type(package["version"]) is not int or package["version"] < 0:
        raise Refused("revision version is not a nonnegative integer")
    if package["version"] == 0:
        if package["parent_digest"] is not None:
            raise Refused("initial package cannot have a parent")
    elif not isinstance(package["parent_digest"], str) or len(package[
            "parent_digest"]) != 64:
        raise Refused("revision parent identity is malformed")
    request = package["authority_request"]
    if not isinstance(request, dict) or set(request) != {"queries", "steps"}:
        raise Refused("revision authority request is malformed")
    for key in ("queries", "steps"):
        if not _is_count(request.get(key)):
            raise Refused("revision authority request is malformed")
        if request[key] > int(grant.get(key, 0)):
            raise Refused("revision expands authority beyond the grant")
    if package["package_digest"] != package_digest(package):
        raise Refused("package manifest does not match its digest")
    return package


def validate_acquisition_evidence(package: dict, original: dict,
                                    finalization: dict) -> dict:
    if not isinstance(package, dict) or package.get("origin") != "acquired":
        raise Refused("acquisition evidence requires an acquired package")
    if package.get("source_kind") != "model-response":
        raise Refused("acquisition evidence requires model-response source")
    try:
        original = validate_evidence_record(
            original, kind="gateway-dispatch", outcome="success")
        finalization = validate_evidence_record(
            finalization, kind="gateway-dispatch", outcome="success")
    except Refused as exc:
        raise Refused("invalid dispatch evidence: %s" % exc) from exc
    provenance = package.get("provenance")
    required = {"version", "kind", "operation_id", "prompt_digest",
                "response_digest", "parsed_source_digest",
                "dispatch_evidence_digest"}
    if not isinstance(provenance, dict) or set(provenance) != required:
        raise Refused("acquisition evidence has incomplete provenance")
    if (provenance.get("version") != EVIDENCE_VERSION
            or provenance.get("kind") != "gateway-dispatch"
            or not isinstance(provenance.get("operation_id"), str)
            or not provenance["operation_id"]):
        raise Refused("acquisition evidence has malformed provenance")
    if original.get("dispatch_evidence_digest") is not None:
        raise Refused("original dispatch evidence is not an original record")
    if original.get("evidence_digest") != provenance.get(
            "dispatch_evidence_digest"):
        raise Refused("acquisition evidence references a different dispatch")
    if finalization.get("dispatch_evidence_digest") != original.get(
            "evidence_digest"):
        raise Refused("finalization does not link original dispatch evidence")
    if any(finalization.get(key) != original.get(key) for key in (
            "operation_id", "input_digest", "result_digest", "task_id",
            "attempt", "arm", "route_digest")):
        raise Refused("dispatch evidence lineage does not match operation")
    if any(finalization.get(key) != original.get(key)
           for key in EVIDENCE_RESPONSE_FIELDS):
        raise Refused("dispatch evidence response identity does not match")
    if finalization.get("details") != original.get("details"):
        raise Refused("dispatch evidence details do not match")
    if (not original.get("task_id") or not original.get("arm")
            or original.get("attempt") is None):
        raise Refused("original dispatch has incomplete treatment identity")
    if finalization.get("arm") != original.get("arm"):
        raise Refused("finalization treatment identity does not match dispatch")
    if finalization.get("round") is None or type(
            finalization.get("round")) is not int or finalization[
                "round"] < 0:
        raise Refused("finalization lineage has no valid round")
    if (original.get("round") is not None
            and finalization.get("round") != original.get("round")):
        raise Refused("finalization round does not match dispatch")
    raw_payload = original.get("details", {}).get("raw_payload")
    if not isinstance(raw_payload, dict):
        raise Refused("dispatch evidence has no raw model response")
    raw_prompt = raw_payload.get("raw_prompt")
    raw_response = raw_payload.get("raw_response")
    if not isinstance(raw_prompt, str) or not isinstance(raw_response, str):
        raise Refused("dispatch evidence raw bytes are incomplete")
    if (_digest_text(raw_prompt) != original.get("input_digest")
            or _digest_text(raw_response) != original.get("result_digest")):
        raise Refused("dispatch evidence raw byte digest mismatch")
    if finalization.get("details", {}).get("raw_payload") != raw_payload:
        raise Refused("finalization raw response does not match dispatch")
    body = raw_response.strip()
    if body.startswith("```"):
        lines = body.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise Refused("raw model response is not valid JSON") from exc
    source = parsed.get("entry") if isinstance(parsed, dict) else None
    if not isinstance(parsed, dict) or set(parsed) != {"entry"}:
        raise Refused("raw model response has a non-strict payload")
    if not isinstance(source, str) or not source.strip():
        raise Refused("raw model response has no executable source")
    try:
        from . import method_exec
        method_exec.verify_step_source(source, "STEP")
    except Exception as exc:
        raise Refused("raw model response source is not a STEP package") from exc
    source_digest_value = _digest_text(source)
    expected = {
        "operation_id": provenance.get("operation_id"),
        "prompt_digest": provenance.get("prompt_digest"),
        "response_digest": provenance.get("response_digest"),
        "parsed_source_digest": provenance.get("parsed_source_digest"),
        "dispatch_evidence_digest": original.get("evidence_digest"),
    }
    actual = {
        "operation_id": original.get("operation_id"),
        "prompt_digest": original.get("input_digest"),
        "response_digest": original.get("result_digest"),
        "parsed_source_digest": source_digest_value,
        "dispatch_evidence_digest": original.get("evidence_digest"),
    }
    if expected != actual or package.get("response_digest") != actual[
            "response_digest"] or package.get("response_source_digest") != \
            source_digest_value:
        raise Refused("dispatch evidence does not match package lineage")
    if (finalization.get("parse_outcome") != "accepted"
            or finalization.get("source_digest") != source_digest_value
            or finalization.get("artifact_digest") != package.get(
                "package_digest")
            or finalization.get("package_digest") != package.get(
                "package_digest")
            or finalization.get("accepted_candidate_digest") != package.get(
                "package_digest")
            or finalization.get("parent_digest") != package.get(
                "parent_digest")):
        raise Refused("dispatch evidence does not bind package identity")
    return {"original": original, "finalization": finalization}


def _validate_child_receipt(receipt: dict, record: dict,
                            evidence_records: list) -> None:
    evidence = validate_evidence_record(
        receipt, kind="child-execution", outcome="success")
    expected = {
        "arm": record.get("arm"),
        "source_digest": record.get("imp_digest"),
        "artifact_digest": record.get("package_digest"),
        "package_digest": record.get("package_digest"),
        "parent_digest": record.get("parent_digest"),
        "round": record.get("round"),
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise Refused("child receipt lineage does not match revision")
    if not evidence.get("task_id"):
        raise Refused("child receipt has no task lineage")
    post_restart = record.get("post_restart")
    if not isinstance(post_restart, dict) or not post_restart.get(
            "executed"):
        raise Refused("accepted revision has no post-restart child receipt")
    operation_ids = post_restart.get("operation_ids")
    if (not isinstance(operation_ids, list) or not operation_ids
            or len(set(operation_ids)) != len(operation_ids)
            or any(not isinstance(item, str) or not item
                   for item in operation_ids)):
        raise Refused("post-restart operation identity is malformed")
    if operation_ids != [evidence["operation_id"]]:
        raise Refused("child receipt does not cite the durable operation")
    if post_restart.get("executable_digest") != record.get("imp_digest"):
        raise Refused("post-restart executable digest does not match revision")
    if (post_restart.get("task_id") != evidence.get("task_id")
            or post_restart.get("round") != evidence.get("round")):
        raise Refused("post-restart child lineage does not match receipt")
    raw_payload = evidence.get("details", {}).get("raw_payload")
    if not isinstance(raw_payload, dict):
        raise Refused("child receipt raw payload is missing")
    source_bytes = raw_payload.get("source_bytes")
    serialized_input = raw_payload.get("serialized_input")
    driver_digest = raw_payload.get("driver_digest")
    operation_payload = raw_payload.get("operation_payload")
    if (not isinstance(source_bytes, str)
            or _digest_text(source_bytes) != evidence.get("source_digest")
            or not isinstance(serialized_input, str)
            or _digest_text(serialized_input) != evidence.get("input_digest")
            or driver_digest != evidence.get("driver_digest")
            or not isinstance(operation_payload, dict)
            or _digest_text(canonical(operation_payload)) != evidence.get(
                "operation_payload_digest")):
        raise Refused("child receipt source, driver, or input bytes are unbound")
    launcher = raw_payload.get("launcher_receipt")
    if not isinstance(launcher, dict) or launcher.get("outcome") != "success":
        raise Refused("child receipt durable result is not successful")
    if launcher.get("receipt_identity") is not None and launcher.get(
            "receipt_identity") != evidence.get("receipt_identity"):
        raise Refused("child receipt durable identity mismatch")
    if launcher.get("operation_id") is not None and launcher.get(
            "operation_id") != evidence.get("operation_id"):
        raise Refused("child receipt durable operation mismatch")
    worker = (launcher.get("data") or {}).get("worker")
    worker_data = worker.get("data") if isinstance(worker, dict) else None
    if not isinstance(worker_data, dict):
        raise Refused("child receipt durable result bytes are missing")
    action = raw_payload.get("action")
    state = raw_payload.get("state")
    if action != worker_data.get("action") or state != worker_data.get("state"):
        raise Refused("child receipt raw payload does not match durable result")
    result = {"action": action, "state": state}
    if evidence.get("result_digest") != _digest_text(canonical(result)):
        raise Refused("child receipt result digest does not match raw payload")
    durable = [item for item in evidence_records
               if item.get("evidence_digest") == evidence["evidence_digest"]
               and item.get("receipt_identity") == evidence[
                   "receipt_identity"]]
    if len(durable) != 1 or canonical(durable[0]) != canonical(evidence):
        raise Refused("child receipt is not the recorded durable operation")


def _validate_effect_identity(identity) -> dict:
    if not isinstance(identity, dict) or not identity:
        raise Refused("effect needs an operation or receipt identity")
    if set(identity) - {"operation_id", "receipt_identity"}:
        raise Refused("effect identity has unknown fields")
    if any(not isinstance(value, str) or not value
           for value in identity.values()):
        raise Refused("effect identity is malformed")
    return dict(identity)


def _effect_identity_matches(effect: dict, observation: dict) -> None:
    expected = effect.get("expected_identity")
    try:
        expected = _validate_effect_identity(expected)
    except Refused as exc:
        raise Refused("pending effect has no expected identity") from exc
    for key, value in expected.items():
        if observation.get(key) != value:
            label = ("operation identity" if key == "operation_id"
                     else "receipt identity")
            raise Refused("effect %s mismatch" % label)


def validate_operate_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise Refused("operate action must be an object")
    kind = action.get("kind")
    if kind not in OPERATE_KINDS:
        raise Refused("unknown operate action kind %r" % (kind,))
    inputs = action.get("inputs")
    if not isinstance(inputs, dict):
        raise Refused("operate action inputs must be an object")
    if kind == "investigate" and not isinstance(
            inputs.get("opportunity_id"), str):
        raise Refused("investigate needs an opportunity_id")
    if kind == "probe" and (
            not isinstance(inputs.get("opportunity_id"), str)
            or not inputs["opportunity_id"]
            or not isinstance(inputs.get("x"), int)
            or not 0 <= inputs["x"] < 16):
        raise Refused("probe needs an opportunity_id and x in 0..15")
    _resource_delta(action.get("requested_resources"))
    return action


def validate_view(view: dict) -> dict:
    if not isinstance(view, dict):
        raise Refused("STEP view must be an object")
    if view.get("purpose") not in PURPOSES:
        raise Refused("STEP view names no operate/improve purpose")
    for key in ("mission", "frontier", "experience", "obligations",
                "authority_remaining", "instruments", "environments",
                "environment_digest", "target_digest",
                "contract_versions"):
        if key not in view:
            raise Refused("STEP view misses %s" % key)
    if view["purpose"] == IMPROVE and "frozen_source" not in view:
        raise Refused("improve view holds no frozen source")
    if view["purpose"] == OPERATE and "frozen_source" in view:
        raise Refused("operate view must not carry program source")
    return view


def _check_opportunity(opportunity: dict) -> dict:
    if not isinstance(opportunity, dict):
        raise Refused("opportunity must be an object")
    for key in ("opportunity_id", "mission_link", "question",
                "intervention", "resources"):
        if key not in opportunity:
            raise Refused("opportunity misses %s" % key)
    intervention = opportunity["intervention"]
    if not isinstance(intervention, dict) or intervention.get(
            "instrument") not in INSTRUMENTS:
        raise Refused("opportunity names an inadmissible instrument")
    _resource_delta(opportunity["resources"], require_charge=True)
    if not isinstance(opportunity["opportunity_id"], str) or not \
            opportunity["opportunity_id"]:
        raise Refused("opportunity needs an id")
    return opportunity


def _blank_doc(namespace: str, mission: dict, authority: dict) -> dict:
    return {
        "namespace": namespace,
        "frontier_version": FRONTIER_VERSION,
        "mission": dict(mission),
        "mission_projection": canonical(dict(mission)),
        "environments": list(mission["environments"]),
        "environment_digest": environment_digest(
            mission["environments"]),
        "grant": {"queries": int(authority["queries"]),
                  "steps": int(authority["steps"])},
        "used": {"queries": 0, "steps": 0},
        "opportunities": {},
        "observations": [],
        "outcomes": {},
        "outcomes_projection": canonical({}),
        "predictions": [],
        "obligations": [],
        "pending_effects": [],
        "active_package": None,
        "lineage": [],
        "accepted_revisions": [],
        "retained": {"evidence_ids": [], "obligations": []},
        "retained_projection": canonical({
            "evidence_ids": [], "obligations": []}),
        "evidence": [],
        "evidence_projection": [],
        "private_state": {},
        "staged_candidate": None,
        "round_results": [],
        "round_journal": [],
        "treatment_arms": {"acquired": []},
    }


class FrontierStore:
    def __init__(self, path) -> None:
        self.path = str(path)
        try:
            with open(self.path, encoding="utf-8") as handle:
                doc = json.load(handle)
        except (OSError, ValueError) as exc:
            raise Refused("store %s is unreadable" % self.path) from exc
        if not isinstance(doc, dict) or doc.get("namespace") != \
                NAMESPACE:
            raise Refused("store %s is outside namespace %s" % (
                self.path, NAMESPACE))
        if doc.get("frontier_version") != FRONTIER_VERSION:
            raise Refused("store %s uses an unknown frontier version"
                          % self.path)
        self._doc = doc
        self._validate_document()
        self._validate_active_package()

    @property
    def authority(self) -> dict:
        grant = dict(self._doc["grant"])
        used = dict(self._doc["used"])
        return {"queries_total": grant["queries"],
                "steps_total": grant["steps"],
                "queries_used": used["queries"],
                "steps_used": used["steps"],
                "queries_remaining": grant["queries"] - used["queries"],
                "steps_remaining": grant["steps"] - used["steps"]}

    @property
    def observations(self) -> list:
        return [dict(o) for o in self._doc["observations"]]

    @property
    def evidence(self) -> list:
        return [dict(record) for record in self._doc["evidence"]]

    @property
    def retained(self) -> dict:
        return {"evidence_ids": list(
            self._doc["retained"]["evidence_ids"]),
            "obligations": list(
                self._doc["retained"]["obligations"])}

    @property
    def private_state(self) -> dict:
        return dict(self._doc["private_state"])

    @private_state.setter
    def private_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise Refused("private state must be an object")
        self._doc["private_state"] = dict(state)
        self.save()

    @property
    def active_package(self):
        package = self._doc["active_package"]
        return dict(package) if package is not None else None

    @property
    def active_digest(self):
        package = self._doc["active_package"]
        return package["package_digest"] if package else None

    @property
    def environment_digest(self) -> str:
        return self._doc["environment_digest"]

    @property
    def pending_effects(self) -> list:
        return [dict(e) for e in self._doc["pending_effects"]
                if e["status"] == "pending"]

    @property
    def settled_effects(self) -> list:
        return [dict(e) for e in self._doc["pending_effects"]
                if e["status"] == "settled"]

    @property
    def treatment_arms(self) -> dict:
        return {"acquired": [dict(c) for c in
                             self._doc["treatment_arms"]["acquired"]]}

    @property
    def accepted_revisions(self) -> list:
        return [dict(record) for record in
                self._doc.get("accepted_revisions", [])]

    def _source_anchor_path(self, operation_id: str) -> str:
        key = _digest_text(operation_id)[:24]
        return self.path + ".source-anchor-" + key + ".json"

    def _source_anchor_value(self, original: dict) -> dict:
        details = original.get("details", {})
        payload = details.get("raw_payload")
        if not isinstance(details, dict) or (
                details.get("route") is not None
                and not isinstance(details.get("route"), dict)):
            raise Refused("acquisition source anchor route is malformed")
        if not isinstance(payload, dict):
            raise Refused("acquisition source anchor has no raw bytes")
        raw_prompt = payload.get("raw_prompt")
        raw_response = payload.get("raw_response")
        if not isinstance(raw_prompt, str) or not isinstance(raw_response, str):
            raise Refused("acquisition source anchor has incomplete raw bytes")
        return {
            "version": SOURCE_ANCHOR_VERSION,
            "operation_id": original.get("operation_id"),
            "evidence_digest": original.get("evidence_digest"),
            "prompt_digest": _digest_text(raw_prompt),
            "response_digest": _digest_text(raw_response),
            "route": dict(details.get("route") or {}),
            "raw_prompt": raw_prompt,
            "raw_response": raw_response,
        }

    def _write_source_anchor(self, original: dict) -> None:
        value = self._source_anchor_value(original)
        path = self._source_anchor_path(value["operation_id"])
        encoded = canonical(value) + "\n"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                if handle.read() != encoded:
                    raise Refused("acquisition source anchor conflicts with evidence")
            return
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(encoded)
        try:
            os.link(temporary, path)
        except FileExistsError:
            with open(path, encoding="utf-8") as handle:
                if handle.read() != encoded:
                    raise Refused("acquisition source anchor conflicts with evidence")
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _validate_source_anchor(self, original: dict) -> dict:
        path = self._source_anchor_path(original.get("operation_id"))
        try:
            with open(path, encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, ValueError, TypeError) as exc:
            raise Refused("acquisition source anchor is missing or unreadable") from exc
        expected = self._source_anchor_value(original)
        if canonical(value) != canonical(expected):
            raise Refused(
                "acquisition source anchor no longer matches dispatch evidence")
        return value

    def _durable_acquisition(self, package: dict,
                             finalization: dict | None = None) -> dict | None:
        if package["origin"] != "acquired":
            return None
        provenance = package.get("provenance")
        if not isinstance(provenance, dict):
            raise Refused("acquired package requires acquisition evidence")
        evidence_digest = provenance.get("dispatch_evidence_digest")
        originals = [
            record for record in self._doc["evidence"]
            if record.get("evidence_digest") == evidence_digest
            and record.get("dispatch_evidence_digest") is None]
        if len(originals) != 1:
            raise Refused("acquisition evidence original dispatch is missing:"
                          " dispatch provenance is unavailable")
        self._validate_source_anchor(originals[0])
        finalizations = [
            record for record in self._doc["evidence"]
            if record.get("dispatch_evidence_digest") == evidence_digest
            and record.get("package_digest") == package.get(
                "package_digest")]
        if finalization is None:
            if len(finalizations) != 1:
                raise Refused("acquired package requires acquisition evidence")
            finalization = finalizations[0]
        try:
            stored_finalization = validate_evidence_record(
                finalization, kind="gateway-dispatch", outcome="success")
        except Refused as exc:
            raise Refused("acquisition evidence finalization is invalid") \
                from exc
        if len(finalizations) != 1 or canonical(
                finalizations[0]) != canonical(stored_finalization):
            raise Refused("acquisition evidence finalization is not durable")
        try:
            validate_acquisition_evidence(
                package, originals[0], stored_finalization)
        except Refused as exc:
            raise Refused("acquisition evidence does not bind package") \
                from exc
        return stored_finalization

    def _revision_record(self, package: dict, *, arm: str | None,
                         round_no: int | None,
                         acquisition_evidence_digest: str | None = None,
                         acquisition_round: int | None = None) -> dict:
        return {
            "package_digest": package["package_digest"],
            "parent_digest": package.get("parent_digest"),
            "imp_digest": package["imp_digest"],
            "response_digest": package.get("response_digest"),
            "provenance_digest": package.get("provenance_digest"),
            "acquisition_evidence_digest": acquisition_evidence_digest,
            "acquisition_round": acquisition_round,
            "origin": package.get("origin"),
            "source_kind": package.get("source_kind"),
            "arm": arm,
            "round": (int(package.get("version", 0))
                      if round_no is None else int(round_no)),
            "accepted": True,
            "retained": package.get("origin") == "acquired",
            "active": True,
            "post_restart": {"executed": False, "operation_ids": [],
                             "executable_digest": None},
            "receipt": None,
        }

    def _validate_document(self) -> None:
        doc = self._doc
        if {"rounds", "improvement_log"} & set(doc):
            raise Refused("removed round projection is present")
        mission = doc.get("mission")
        if (not isinstance(mission, dict)
                or not isinstance(mission.get("objective"), str)
                or not mission["objective"].strip()
                or not isinstance(mission.get("environments"), list)
                or not mission["environments"]):
            raise Refused("mission projection is invalid")
        if doc.get("mission_projection") != canonical(mission):
            raise Refused("mission projection changed")
        environments = doc.get("environments")
        if environments != mission["environments"]:
            raise Refused("mission environment projection changed")
        if doc.get("environment_digest") != environment_digest(environments):
            raise Refused("mission environment digest changed")
        grant = doc.get("grant")
        used = doc.get("used")
        if (not isinstance(grant, dict) or set(grant) != {"queries", "steps"}
                or any(not _is_count(grant.get(key)) for key in grant)
                or not isinstance(used, dict) or set(used) != {"queries", "steps"}
                or any(not _is_count(used.get(key)) for key in used)
                or any(used[key] > grant[key] for key in grant)):
            raise Refused("authority projection is invalid")
        opportunities = doc.get("opportunities")
        if not isinstance(opportunities, dict):
            raise Refused("opportunity projection is invalid")
        for opportunity_id, opportunity in opportunities.items():
            if not isinstance(opportunity_id, str) or not isinstance(
                    opportunity, dict) or opportunity.get(
                        "opportunity_id") != opportunity_id:
                raise Refused("opportunity projection is invalid")
            _check_opportunity(opportunity)
            if opportunity.get("status") not in {
                    "admissible", "accepted", "settled", "done"}:
                raise Refused("opportunity status is invalid")
        observations = doc.get("observations")
        pending_effects = doc.get("pending_effects")
        if not isinstance(observations, list) or not isinstance(
                pending_effects, list):
            raise Refused("observation or effect projection is invalid")
        observation_ids = set()
        effects = {effect.get("effect_id"): effect
                   for effect in pending_effects if isinstance(effect, dict)}
        for observation in observations:
            if not isinstance(observation, dict):
                raise Refused("observation projection is invalid")
            observation_id = observation.get("observation_id")
            if (not isinstance(observation_id, str) or not observation_id
                    or observation_id in observation_ids):
                raise Refused("observation identity projection is invalid")
            observation_ids.add(observation_id)
            effect_id = observation.get("effect_id")
            if effect_id is not None and effect_id not in effects:
                raise Refused("observation effect projection is invalid")
        self._validate_lineage()
        self._validate_effect_projection()
        self._validate_retained_projection()
        self._validate_evidence_projection()
        self._validate_outcome_projection()
        obligations = doc.get("obligations")
        if (not isinstance(obligations, list)
                or any(not isinstance(item, str) or not item
                       for item in obligations)
                or len(set(obligations)) != len(obligations)):
            raise Refused("obligation projection is invalid")
        predictions = doc.get("predictions")
        if (not isinstance(predictions, list)
                or any(not isinstance(item, dict)
                       or not isinstance(item.get("key"), dict)
                       or not isinstance(item.get("hypothesis"), dict)
                       for item in predictions)):
            raise Refused("prediction projection is invalid")
        private_state = doc.get("private_state")
        if not isinstance(private_state, dict):
            raise Refused("private state projection is invalid")
        self._validate_round_journal()
        self._validate_round_results()
        self._validate_accepted_revisions()
        treatment_arms = doc.get("treatment_arms")
        if (not isinstance(treatment_arms, dict)
                or not isinstance(treatment_arms.get("acquired"), list)):
            raise Refused("treatment arm projection is invalid")
        treatment_digests = set()
        for package in treatment_arms["acquired"]:
            validate_package(package, grant=grant)
            if package.get("origin") != "acquired":
                raise Refused("treatment arm contains a non-acquired package")
            if package["package_digest"] in treatment_digests:
                raise Refused("treatment arm identity is duplicated")
            treatment_digests.add(package["package_digest"])
        staged = doc.get("staged_candidate")
        if staged is not None:
            validate_package(staged, grant=grant)

    def _validate_effect_projection(self) -> None:
        effects = self._doc.get("pending_effects")
        if not isinstance(effects, list):
            raise Refused("effect projection is invalid")
        ids = set()
        attached = {}
        for observation in self._doc["observations"]:
            effect_id = observation.get("effect_id")
            if effect_id is not None:
                attached.setdefault(effect_id, []).append(observation)
        if any(len(items) > 1 for items in attached.values()):
            raise Refused("observation per effect identity is duplicated")
        lineage_digests = {
            record["package_digest"] for record in self._doc["lineage"]
        }
        for effect in effects:
            if not isinstance(effect, dict):
                raise Refused("effect projection is invalid")
            effect_id = effect.get("effect_id")
            if (not isinstance(effect_id, str) or not effect_id
                    or effect_id in ids):
                raise Refused("effect identity projection is invalid")
            ids.add(effect_id)
            if effect.get("opportunity_id") not in self._doc.get(
                    "opportunities", {}):
                raise Refused("effect opportunity projection is invalid")
            if effect.get("program_digest") not in lineage_digests:
                raise Refused("effect program projection is invalid")
            if effect.get("status") not in {"pending", "settled"}:
                raise Refused("effect status projection is invalid")
            opportunity = self._doc["opportunities"].get(
                effect["opportunity_id"])
            expected_status = ("accepted" if effect["status"] == "pending"
                               else "done")
            if opportunity.get("status") != expected_status:
                raise Refused("effect opportunity status projection is invalid")
            if effect.get("charged") is not True:
                raise Refused("effect has no durable charge")
            _effect_resources(effect)
            _validate_effect_identity(effect.get("expected_identity"))
            observation_id = effect.get("observation_id")
            effect_observations = attached.get(effect_id, [])
            if effect.get("status") == "pending":
                if observation_id is not None or len(effect_observations) > 1:
                    raise Refused("pending effect has a settlement projection")
                continue
            if (len(effect_observations) != 1
                    or observation_id != effect_observations[0].get(
                        "observation_id")):
                raise Refused("settled effect observation projection is invalid")
            observation = effect_observations[0]
            _effect_identity_matches(effect, observation)

    def _validate_retained_projection(self) -> None:
        retained = self._doc.get("retained")
        if (not isinstance(retained, dict)
                or set(retained) != {"evidence_ids", "obligations"}
                or not isinstance(retained["evidence_ids"], list)
                or not isinstance(retained["obligations"], list)
                or any(not isinstance(item, str) or not item
                       for item in retained["evidence_ids"])
                or any(not isinstance(item, str) or not item
                       for item in retained["obligations"])
                or len(set(retained["evidence_ids"])) != len(
                    retained["evidence_ids"])
                or len(set(retained["obligations"])) != len(
                    retained["obligations"])):
            raise Refused("retained projection is invalid")
        if self._doc.get("retained_projection") != canonical(retained):
            raise Refused("retained projection changed")
        observation_ids = {item.get("observation_id") for item in
                           self._doc.get("observations", [])}
        if any(item not in observation_ids
               for item in retained["evidence_ids"]):
            raise Refused("retained evidence projection is invalid")
        active = self._doc.get("active_package")
        if (isinstance(active, dict) and active.get("version", 0) > 0
                and retained["obligations"] != list(
                    active.get("obligations") or [])):
            raise Refused("retained obligation projection is invalid")

    def _validate_evidence_projection(self) -> None:
        evidence = self._doc.get("evidence")
        projection = self._doc.get("evidence_projection")
        if not isinstance(evidence, list) or not isinstance(projection, list):
            raise Refused("evidence projection is invalid")
        seen_receipts = set()
        seen_digests = set()
        for record in evidence:
            if not isinstance(record, dict):
                raise Refused("evidence record must be an object")
            if not isinstance(record.get("details"), dict):
                raise Refused("evidence record details are malformed")
            if (record.get("kind") == "gateway-dispatch"
                    and record.get("outcome") == "success"
                    and record.get("dispatch_evidence_digest") is None):
                self._validate_source_anchor(record)
            validate_evidence_record(record)
            receipt = record["receipt_identity"]
            digest = record["evidence_digest"]
            if receipt in seen_receipts or digest in seen_digests:
                raise Refused("evidence identity projection is invalid")
            seen_receipts.add(receipt)
            seen_digests.add(digest)
        expected = [{"evidence_digest": item["evidence_digest"],
                     "receipt_identity": item["receipt_identity"]}
                    for item in evidence]
        if projection != expected:
            raise Refused(
                "finalization evidence projection changed; dispatch provenance"
                " is not durable")

    def _validate_outcome_projection(self) -> None:
        outcomes = self._doc.get("outcomes")
        if not isinstance(outcomes, dict):
            raise Refused("outcome projection is invalid")
        for key, outcome in outcomes.items():
            try:
                canonical_key = canonical(json.loads(key))
            except (TypeError, ValueError) as exc:
                raise Refused("outcome identity projection is invalid") from exc
            if not isinstance(key, str) or key != canonical_key:
                raise Refused("outcome identity projection is invalid")
            if not isinstance(outcome, dict):
                raise Refused("outcome projection is invalid")
        if self._doc.get("outcomes_projection") != canonical(outcomes):
            raise Refused("outcome projection changed")

    def _validate_round_results(self) -> None:
        results = self._doc.get("round_results")
        if not isinstance(results, list):
            raise Refused("round result projection is invalid")
        seen = set()
        for result in results:
            if (not isinstance(result, dict)
                    or type(result.get("round")) is not int
                    or result["round"] < 1
                    or result["round"] in seen):
                raise Refused("round result identity is invalid")
            digest = result.get("result_digest")
            if (not isinstance(digest, str) or len(digest) != 64
                    or digest != round_result_digest(result)):
                raise Refused("round result identity is invalid")
            if (not isinstance(result.get("log"), list)
                    or not isinstance(result.get("observations"), list)
                    or not isinstance(result.get("receipts"), list)):
                raise Refused("round result projection is invalid")
            seen.add(result["round"])
            validate_package(result.get("candidate"), grant=self._doc["grant"])
            for receipt in result.get("receipts", []):
                validate_evidence_record(receipt, kind="child-execution",
                                         outcome="success")

    def _validate_accepted_revisions(self) -> None:
        records = self._doc.get("accepted_revisions")
        if not isinstance(records, list):
            raise Refused("accepted revision projection is invalid")
        lineage = self._doc.get("lineage")
        if not isinstance(lineage, list):
            raise Refused("accepted revision lineage is invalid")
        packages = {}
        for record in lineage:
            if not isinstance(record, dict) or not isinstance(
                    record.get("package"), dict):
                raise Refused("accepted revision lineage is invalid")
            package = record["package"]
            digest = package.get("package_digest")
            if not isinstance(digest, str) or not digest or digest in packages:
                raise Refused("accepted revision lineage is invalid")
            packages[digest] = package
        digests = set()
        evidence = self._doc.get("evidence", [])
        for record in records:
            if not isinstance(record, dict):
                raise Refused("accepted revision projection is invalid")
            digest = record.get("package_digest")
            if (not isinstance(digest, str) or not digest
                    or digest in digests):
                raise Refused(
                    "acquisition evidence or accepted revision identity is invalid")
            package = packages.get(digest)
            if package is None:
                raise Refused(
                    "acquisition evidence or accepted revision identity is invalid")
            validate_package(package, grant=self._doc["grant"])
            finalization = (self._durable_acquisition(package)
                            if package.get("origin") == "acquired" else None)
            if package.get("origin") != "acquired" and (
                    record.get("acquisition_evidence_digest") is not None
                    or record.get("acquisition_round") is not None):
                raise Refused("authored package carries acquisition lineage")
            if package.get("origin") == "acquired" and (
                    finalization is None
                    or record.get("acquisition_evidence_digest")
                    != finalization.get("evidence_digest")
                    or record.get("acquisition_round")
                    != finalization.get("round")):
                raise Refused("acquisition finalization lineage changed")
            if (type(record.get("round")) is not int
                    or record["round"] < 0
                    or (record.get("acquisition_round") is not None
                        and (type(record.get("acquisition_round")) is not int
                             or record["acquisition_round"] < 0))):
                raise Refused("accepted revision identity is invalid")
            expected = self._revision_record(
                package, arm=record.get("arm"), round_no=record.get("round"),
                acquisition_evidence_digest=record.get(
                    "acquisition_evidence_digest"),
                acquisition_round=record.get("acquisition_round"))
            if any(record.get(key) != expected.get(key)
                   for key in REVISION_IDENTITY_FIELDS):
                if package.get("origin") == "acquired":
                    raise Refused(
                        "acquisition evidence or accepted revision lineage"
                        " is invalid")
                raise Refused("accepted revision lineage is invalid")
            digests.add(digest)
            post_restart = record.get("post_restart")
            if not isinstance(post_restart, dict):
                raise Refused("accepted revision post-restart state is missing")
            receipt = record.get("receipt")
            if post_restart.get("executed"):
                _validate_child_receipt(receipt, record, evidence)
            elif (post_restart.get("operation_ids") != []
                  or post_restart.get("executable_digest") is not None
                  or receipt is not None
                  or record.get("usable_result") is True):
                raise Refused("accepted revision has an unrecorded receipt")
            if receipt is not None:
                if not isinstance(receipt, dict):
                    raise Refused("accepted revision receipt is malformed")
                matches = [item for item in evidence
                           if isinstance(item, dict)
                           and item.get("evidence_digest") == receipt.get(
                               "evidence_digest")]
                if len(matches) != 1 or canonical(matches[0]) != canonical(
                        receipt):
                    raise Refused("accepted revision receipt is not durable")

    def _validate_lineage(self) -> None:
        records = self._doc.get("lineage")
        if not isinstance(records, list):
            raise Refused("lineage projection is invalid")
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise Refused("lineage projection is invalid")
            package = record.get("package")
            validate_package(package, grant=self._doc["grant"])
            if (record.get("version") != index
                    or record.get("package_digest") != package.get(
                        "package_digest")
                    or record.get("parent_digest") != package.get(
                        "parent_digest")):
                raise Refused("lineage projection is invalid")

    def _validate_active_package(self) -> dict | None:
        active = self._doc.get("active_package")
        if active is None:
            return None
        try:
            bound = validate_package(active, grant=self._doc["grant"])
        except Refused as exc:
            raise Refused("active package is invalid: %s" % exc) from exc
        records = self._doc.get("lineage") or []
        if not records:
            raise Refused("active package has no retained candidate")
        previous = None
        finalizations = {}
        for index, record in enumerate(records):
            if not isinstance(record, dict) or not isinstance(
                    record.get("package"), dict):
                raise Refused("retained candidate is invalid")
            try:
                package = validate_package(
                    record["package"], grant=self._doc["grant"])
            except Refused as exc:
                raise Refused("retained candidate is invalid: %s" % exc) \
                    from exc
            if (record.get("version") != index
                    or record.get("package_digest") != package[
                        "package_digest"]
                    or record.get("parent_digest") != package[
                        "parent_digest"]
                    or package["version"] != index):
                raise Refused("retained candidate lineage is invalid")
            if previous is None:
                if package["parent_digest"] is not None:
                    raise Refused("initial retained candidate has a parent")
            else:
                if package["parent_digest"] != previous["package_digest"]:
                    raise Refused("retained candidate parent lineage changed")
                if (package["op_source"] != previous["op_source"]
                        or package["op_digest"] != previous["op_digest"]):
                    raise Refused("retained candidate operational lineage changed")
            if package["origin"] == "acquired":
                finalization = self._durable_acquisition(package)
                finalizations[index] = finalization
                if record.get("acquisition_evidence_digest") != finalization[
                        "evidence_digest"]:
                    raise Refused("acquisition finalization lineage changed")
                retained = [item for item in self._doc[
                    "treatment_arms"]["acquired"]
                    if item.get("package_digest") == package[
                        "package_digest"]]
                if len(retained) != 1 or canonical(
                        retained[0]) != canonical(package):
                    raise Refused("acquired package is not retained")
            elif record.get("acquisition_evidence_digest") is not None:
                raise Refused("authored package carries acquisition lineage")
            previous = package
        if canonical(bound) != canonical(previous):
            raise Refused("active package differs from retained candidate")
        if previous["version"] > 0 or previous["origin"] == "acquired":
            finalization = finalizations.get(len(records) - 1)
            expected_arm = (None if previous["version"] == 0
                            else (finalization or {}).get("arm"))
            expected = self._revision_record(
                previous, arm=expected_arm, round_no=None,
                acquisition_evidence_digest=(
                    None if finalization is None else finalization[
                        "evidence_digest"]),
                acquisition_round=(
                    None if finalization is None else finalization[
                        "round"]))
            matches = [
                record for record in self._doc.get("accepted_revisions", [])
                if record.get("package_digest") == previous[
                    "package_digest"]]
            ignored = {"post_restart", "receipt"}
            if len(matches) != 1 or any(
                    matches[0].get(key) != value
                    for key, value in expected.items()
                    if key not in ignored):
                raise Refused("active accepted revision lineage changed")
        for record in self._doc.get("accepted_revisions", []):
            post_restart = record.get("post_restart")
            if not isinstance(post_restart, dict):
                raise Refused("accepted revision post-restart state is missing")
            if post_restart.get("executed"):
                _validate_child_receipt(
                    record.get("receipt"), record, self._doc["evidence"])
            elif (post_restart.get("operation_ids") != []
                  or post_restart.get("executable_digest") is not None
                  or record.get("receipt") is not None
                  or record.get("usable_result") is True):
                raise Refused("accepted revision has an unrecorded receipt")
        return bound

    def _check_evidence_identity(self, evidence: dict) -> dict | None:
        same_receipt = [item for item in self._doc["evidence"]
                        if item.get("receipt_identity") == evidence[
                            "receipt_identity"]]
        same_digest = [item for item in self._doc["evidence"]
                       if item.get("evidence_digest") == evidence[
                           "evidence_digest"]]
        matches = {item.get("evidence_digest"): item
                   for item in same_receipt + same_digest}
        if not matches:
            return None
        existing = next(iter(matches.values()))
        if len(matches) != 1 or canonical(existing) != canonical(evidence):
            raise Refused("evidence identity is already recorded or conflicting")
        return dict(existing)

    def _append_evidence(self, evidence: dict) -> dict:
        existing = self._check_evidence_identity(evidence)
        if existing is not None:
            return existing
        if (evidence.get("kind") == "gateway-dispatch"
                and evidence.get("outcome") == "success"
                and evidence.get("dispatch_evidence_digest") is None):
            self._write_source_anchor(evidence)
        self._doc["evidence"].append(dict(evidence))
        self._doc["evidence_projection"].append({
            "evidence_digest": evidence["evidence_digest"],
            "receipt_identity": evidence["receipt_identity"]})
        return dict(evidence)

    def record_evidence(self, record: dict) -> dict:
        evidence = validate_evidence_record(record)
        existing = self._check_evidence_identity(evidence)
        if existing is not None:
            return existing
        self._append_evidence(evidence)
        self.save()
        return dict(evidence)

    def record_revision_receipt(self, package_digest: str,
                                receipt: dict) -> dict:
        evidence = validate_evidence_record(
            receipt, kind="child-execution", outcome="success")
        matches = [record for record in self._doc["accepted_revisions"]
                   if record.get("package_digest") == package_digest]
        if len(matches) != 1:
            raise Refused("accepted revision is missing or ambiguous")
        record = matches[0]
        existing_receipt = record.get("receipt")
        replacing_local = (
            isinstance(existing_receipt, dict)
            and str(existing_receipt.get("receipt_identity", "")).startswith(
                "local:")
            and canonical(existing_receipt) != canonical(evidence))
        if replacing_local and str(evidence.get(
                "receipt_identity", "")).startswith("local:"):
            raise Refused("local post-restart receipt cannot replace a receipt")
        if existing_receipt is not None and not replacing_local:
            if canonical(existing_receipt) != canonical(evidence):
                raise Refused("accepted revision already has a different receipt")
            self._check_evidence_identity(evidence)
            return dict(record)
        journal = [entry for entry in self._doc["round_journal"]
                   if isinstance(entry, dict)
                   and entry.get("receipt", {}).get("operation_id") ==
                   evidence.get("operation_id")
                   and entry.get("round") == record.get("round")]
        if len(journal) != 1:
            raise Refused("post-restart receipt is not linked to its round")
        candidate = dict(record)
        candidate["post_restart"] = {
            "executed": True,
            "operation_ids": [evidence["operation_id"]],
            "executable_digest": record.get("imp_digest"),
            "task_id": evidence.get("task_id"),
            "round": evidence.get("round"),
        }
        candidate["usable_result"] = True
        candidate["receipt"] = dict(evidence)
        _validate_child_receipt(
            evidence, candidate,
            [item for item in self._doc["evidence"]
             if not replacing_local or item.get("evidence_digest") !=
             existing_receipt.get("evidence_digest")] + [dict(evidence)])
        if replacing_local:
            self._doc["evidence"] = [
                item for item in self._doc["evidence"]
                if item.get("evidence_digest") != existing_receipt.get(
                    "evidence_digest")]
            self._doc["evidence_projection"] = [
                item for item in self._doc["evidence_projection"]
                if item.get("evidence_digest") != existing_receipt.get(
                    "evidence_digest")]
        self._check_evidence_identity(evidence)
        self._append_evidence(evidence)
        record.clear()
        record.update(candidate)
        self.save()
        return dict(record)

    def retain_acquisition(self, package: dict, finalization: dict) -> dict:
        bound = validate_package(package, grant=self._doc["grant"])
        evidence = validate_evidence_record(
            finalization, kind="gateway-dispatch", outcome="success")
        provenance = bound.get("provenance")
        if not isinstance(provenance, dict):
            raise Refused("acquired package requires acquisition evidence")
        originals = [item for item in self._doc["evidence"]
                     if item.get("evidence_digest") == provenance.get(
                         "dispatch_evidence_digest")
                     and item.get("dispatch_evidence_digest") is None]
        if len(originals) != 1:
            raise Refused("original dispatch evidence is missing")
        validate_acquisition_evidence(bound, originals[0], evidence)
        existing_finalization = self._check_evidence_identity(evidence)
        retained = [item for item in self._doc["treatment_arms"]["acquired"]
                    if item.get("package_digest") == bound["package_digest"]]
        if len(retained) > 1 or (
                retained and canonical(retained[0]) != canonical(bound)):
            raise Refused("acquired package retention conflicts")
        if existing_finalization is None:
            self._append_evidence(evidence)
        if not retained:
            self._doc["treatment_arms"]["acquired"].append(dict(bound))
        if existing_finalization is None or not retained:
            self.save()
        return {"package_digest": bound["package_digest"],
                "control_id": bound["control_id"]}

    def _validate_round_journal(self) -> None:
        journal = self._doc.get("round_journal")
        if not isinstance(journal, list):
            raise Refused("round journal projection is invalid")
        seen = set()
        for entry in journal:
            if not isinstance(entry, dict):
                raise Refused("round journal entry is malformed")
            round_no = entry.get("round")
            step = entry.get("step")
            if (type(round_no) is not int or round_no < 1
                    or type(step) is not int or step < 0
                    or (round_no, step) in seen):
                raise Refused("round journal identity is malformed")
            seen.add((round_no, step))
            if (not isinstance(entry.get("action"), dict)
                    or not isinstance(entry.get("state"), dict)
                    or not isinstance(entry.get("receipt"), dict)
                    or not entry["receipt"].get("receipt_identity")
                    or not isinstance(entry.get("executed_digest"), str)
                    or not entry["executed_digest"]):
                raise Refused("round journal receipt is incomplete")
            validate_evidence_record(
                entry["receipt"], kind="child-execution", outcome="success")
            if not isinstance(entry.get("charged"), bool):
                raise Refused("round journal charge state is malformed")
            _effect_resources(entry)
            if not entry["charged"] and entry.get("charged_resources", {}):
                raise Refused("uncharged round journal has a charge")
            if "candidate" in entry and not isinstance(
                    entry["candidate"], dict):
                raise Refused("round journal candidate is malformed")

    def _round_entry(self, round_no: int, step: int) -> dict | None:
        return next((entry for entry in self._doc["round_journal"]
                     if entry.get("round") == int(round_no)
                     and entry.get("step") == int(step)), None)

    def round_command(self, round_no: int, step: int) -> dict | None:
        entry = self._round_entry(round_no, step)
        return dict(entry) if entry is not None else None

    def record_round_command(self, round_no: int, step: int, *,
                            action: dict, state: dict, receipt: dict,
                            executed_digest: str) -> dict:
        if not isinstance(action, dict) or not isinstance(state, dict):
            raise Refused("round command result is malformed")
        if not isinstance(receipt, dict) or not receipt.get(
                "receipt_identity"):
            raise Refused("round command receipt is incomplete")
        validate_evidence_record(
            receipt, kind="child-execution", outcome="success")
        entry = {
            "round": int(round_no), "step": int(step), "action": dict(action),
            "state": dict(state), "receipt": dict(receipt),
            "executed_digest": str(executed_digest),
            "charged": False,
        }
        existing = self._round_entry(round_no, step)
        if existing is not None:
            stable = {key: existing.get(key) for key in (
                "round", "step", "action", "state", "receipt",
                "executed_digest")}
            if canonical(stable) != canonical(entry):
                raise Refused("round command conflicts with durable journal")
            return dict(existing)
        self._doc["round_journal"].append(entry)
        self.save()
        return dict(entry)

    def spend_round_command(self, round_no: int, step: int,
                            requested: dict) -> dict:
        entry = self._round_entry(round_no, step)
        if entry is None:
            raise Refused("round command is not durably received")
        if entry.get("charged"):
            return self.authority
        requested = _resource_delta(requested, require_charge=True)
        self._check_spend(requested)
        for key in ("queries", "steps"):
            self._doc["used"][key] += requested.get(key, 0)
        entry["charged"] = True
        entry["charged_resources"] = dict(requested)
        self.save()
        return self.authority

    def stage_round_candidate(self, round_no: int, step: int,
                              candidate: dict) -> dict:
        entry = self._round_entry(round_no, step)
        if entry is None or entry.get("action", {}).get("kind") != "construct":
            raise Refused("round construct command is not durable")
        if entry.get("candidate") is not None and canonical(
                entry["candidate"]) != canonical(candidate):
            raise Refused("round candidate conflicts with durable journal")
        self._doc["staged_candidate"] = dict(candidate)
        entry["candidate"] = dict(candidate)
        self.save()
        return dict(candidate)

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(canonical(self._doc) + "\n")
        os.replace(tmp, self.path)

    def propose(self, opportunity: dict) -> dict:
        admitted = _check_opportunity(opportunity)
        oid = admitted["opportunity_id"]
        if oid in self._doc["opportunities"]:
            raise Refused("opportunity %r already exists" % oid)
        record = {**admitted, "status": "admissible"}
        self._doc["opportunities"][oid] = record
        self.save()
        return dict(record)

    def admissible(self) -> list:
        listed = [dict(o) for o in
                  self._doc["opportunities"].values()
                  if o["status"] == "admissible"]
        return sorted(listed, key=lambda o: (
            o["resources"]["queries"] + o["resources"]["steps"],
            o["opportunity_id"]))

    def step_view(self, purpose: str, package: dict) -> dict:
        if purpose not in PURPOSES:
            raise Refused("unknown STEP purpose %r" % (purpose,))
        if not isinstance(package, dict) or not package.get(
                "package_digest"):
            raise Refused("STEP view needs the active package digest")
        remaining = {"queries": self.authority["queries_remaining"],
                     "steps": self.authority["steps_remaining"]}
        view = {
            "purpose": purpose,
            "mission": self._doc["mission"]["objective"],
            "frontier": [
                {"opportunity_id": o["opportunity_id"],
                 "task": o["intervention"]["target"],
                 "question": o["question"],
                 "cost": dict(o["resources"])}
                for o in self.admissible()
            ],
            "experience": [
                {"observation_id": o.get("observation_id"),
                 "task": o.get("task"),
                 "verdict": o.get("verdict"),
                 "detail": o.get("detail")}
                for o in self._doc["observations"]
            ],
            "obligations": list(self._doc["obligations"]),
            "retained": self.retained,
            "authority_remaining": remaining,
            "instruments": list(INSTRUMENTS),
            "environments": list(self._doc["environments"]),
            "environment_digest": self._doc["environment_digest"],
            "target_digest": package["package_digest"],
            "contract_versions": self._contracts(),
        }
        if purpose == IMPROVE:
            view["frozen_source"] = {
                "op_source": package["op_source"],
                "imp_source": package["imp_source"],
                "op_digest": package["op_digest"],
                "imp_digest": package["imp_digest"],
            }
            view["improvement_budget"] = {
                "queries": min(4, remaining["queries"]),
                "steps": min(4, remaining["steps"]),
            }
        return validate_view(view)

    def _contracts(self) -> dict:
        from . import method_exec
        from . import packet
        from . import policy_step
        return {
            "frontier": FRONTIER_VERSION,
            "packet": packet.PACKET_VERSION,
            "policy_step": policy_step.POLICY_STEP_VERSION,
            "child": method_exec.CHILD_CONTRACT_VERSION,
        }

    def _check_spend(self, requested: dict) -> None:
        if not isinstance(requested, dict) or any(
                not _is_count(v) for v in requested.values()):
            raise Refused("requested resources are malformed")
        remaining = {"queries": self.authority["queries_remaining"],
                     "steps": self.authority["steps_remaining"]}
        for key in ("queries", "steps"):
            if int(requested.get(key, 0)) > remaining[key]:
                raise Refused("%s budget exhausted" % key)

    def check_spend(self, requested: dict) -> None:
        self._check_spend(requested)

    def spend(self, requested: dict) -> dict:
        self._check_spend(requested)
        for key in ("queries", "steps"):
            self._doc["used"][key] += int(requested.get(key, 0))
        self.save()
        return {"queries_remaining": self.authority[
            "queries_remaining"],
            "steps_remaining": self.authority["steps_remaining"]}

    def _matching_admission(self, opportunity_id: str,
                            program_digest: str,
                            identity: dict) -> list:
        return [effect for effect in self._doc["pending_effects"]
                if effect.get("opportunity_id") == opportunity_id
                and effect.get("program_digest") == program_digest
                and effect.get("expected_identity") == identity]

    def admit_and_spend(self, opportunity_id: str, program_digest: str,
                        requested: dict, *,
                        effect_identity: dict | None = None) -> dict:
        requested = _resource_delta(requested, require_charge=True)
        active_package = self._validate_active_package()
        if active_package is None:
            raise Refused("effect needs a bound program")
        if not program_digest or program_digest != active_package[
                "package_digest"]:
            raise Refused("effect program is not the active program")
        if effect_identity is None:
            candidates = [effect for effect in self._doc["pending_effects"]
                          if effect.get("opportunity_id") == opportunity_id
                          and effect.get("program_digest") == program_digest]
        else:
            identity = _validate_effect_identity(effect_identity)
            candidates = self._matching_admission(
                opportunity_id, program_digest, identity)
        if len(candidates) > 1:
            raise Refused("effect identity is ambiguous")
        if candidates:
            effect = candidates[0]
            identity = effect["expected_identity"]
            charged = _effect_resources(effect)
            if effect.get("charged"):
                if charged != requested:
                    raise Refused("effect charge conflicts with replay")
                return dict(effect)
            if effect.get("status") != "pending":
                raise Refused("settled effect has no durable charge")
            self._check_spend(requested)
        else:
            record = self._doc["opportunities"].get(opportunity_id)
            if record is None or record["status"] != "admissible":
                raise Refused("opportunity %r is not admissible" % (
                    opportunity_id,))
            self._check_spend(requested)
            effect_id = "eff-%s-%d" % (
                opportunity_id, len(self._doc["pending_effects"]))
            identity = _validate_effect_identity(
                effect_identity if effect_identity is not None else
                {"operation_id": "local:%s" % effect_id})
            effect = {
                "effect_id": effect_id,
                "opportunity_id": opportunity_id,
                "program_digest": program_digest,
                "status": "pending",
                "charged": False,
                "charged_resources": {},
                "expected_identity": identity,
            }
            record["status"] = "accepted"
            self._doc["pending_effects"].append(effect)
        for key in ("queries", "steps"):
            self._doc["used"][key] += requested.get(key, 0)
        effect["charged"] = True
        effect["charged_resources"] = dict(requested)
        self.save()
        return dict(effect)

    def accept(self, opportunity_id: str, program_digest: str, *,
               effect_identity: dict | None = None) -> dict:
        record = self._doc["opportunities"].get(opportunity_id)
        if record is None or record["status"] not in {
                "admissible", "accepted", "settled", "done"}:
            raise Refused("opportunity %r is not admissible" % (
                opportunity_id,))
        if self.active_digest is None:
            raise Refused("effect needs a bound program")
        if program_digest != self.active_digest:
            raise Refused("effect program is not the active program")
        return self.admit_and_spend(
            opportunity_id, program_digest, record["resources"],
            effect_identity=effect_identity)

    def _prepare_observation(self, observation: dict,
                             effect: dict | None = None) -> tuple:
        if not isinstance(observation, dict) or not observation.get(
                "observation_id"):
            raise Refused("observation needs an observation_id")
        record = dict(observation)
        effect_id = record.get("effect_id")
        if effect is None and effect_id is not None:
            effect = next((item for item in self._doc["pending_effects"]
                           if item["effect_id"] == effect_id), None)
        if effect_id is not None and effect is not None and \
                effect_id != effect["effect_id"]:
            raise Refused("observation effect identity is not attributable")
        if effect_id is not None:
            if effect is None or effect["status"] not in {
                    "pending", "settled"}:
                raise Refused("observation effect identity is not pending")
            if not any(isinstance(record.get(key), str) and record[key]
                       for key in ("operation_id", "receipt_identity")):
                raise Refused("effect observation needs attribution")
            for key in ("opportunity_id", "task"):
                if key in record and record[key] != effect["opportunity_id"]:
                    raise Refused("observation target does not match effect")
            _effect_identity_matches(effect, record)
        else:
            identity = record.get("opportunity_id", record.get("task"))
            matches = [item for item in self.pending_effects
                       if item["opportunity_id"] == identity]
            if len(matches) > 1:
                raise Refused("observation effect identity is ambiguous")
            if len(matches) == 1:
                effect = matches[0]
                for key in ("opportunity_id", "task"):
                    if key in record and record[key] != effect[
                            "opportunity_id"]:
                        raise Refused(
                            "observation target does not match effect")
                record["effect_id"] = effect["effect_id"]
                expected = _validate_effect_identity(effect["expected_identity"])
                local_identity = expected == {
                    "operation_id": "local:%s" % effect["effect_id"]}
                if (not local_identity and not any(
                        isinstance(record.get(key), str) and record[key]
                        for key in ("operation_id", "receipt_identity"))):
                    raise Refused("effect observation needs attribution")
                if local_identity and "operation_id" not in record:
                    record["operation_id"] = expected["operation_id"]
                _effect_identity_matches(effect, record)
        if any(item.get("observation_id") == record.get("observation_id")
               and item is not record for item in self._doc["observations"]):
            raise Refused("observation identity is already recorded")
        if record.get("effect_id") is not None and any(
                item.get("effect_id") == record.get("effect_id")
                and item.get("observation_id") != record["observation_id"]
                for item in self._doc["observations"]):
            raise Refused("observation per effect identity is already recorded")
        return effect, record

    def observe(self, observation: dict) -> dict:
        existing = next((item for item in self._doc["observations"]
                         if item.get("observation_id") == observation.get(
                             "observation_id")), None)
        if existing is not None:
            if canonical(existing) == canonical(observation):
                return dict(existing)
            raise Refused("observation identity is already recorded or conflicting")
        effect, record = self._prepare_observation(observation)
        self._doc["observations"].append(record)
        self.save()
        return dict(record)

    def complete_effect(self, effect_id: str, observation: dict, *,
                        action_key: dict | None = None,
                        outcome: dict | None = None) -> dict:
        effect = next((item for item in self._doc["pending_effects"]
                       if item["effect_id"] == effect_id), None)
        if effect is None:
            raise Refused("effect %r is not pending" % (effect_id,))
        if effect.get("charged") is not True:
            raise Refused("effect has no durable charge")
        existing = next((item for item in self._doc["observations"]
                         if item.get("effect_id") == effect_id), None)
        if existing is not None:
            if canonical(existing) != canonical(observation):
                raise Refused("effect already has another observation")
            if effect["status"] == "settled":
                return dict(effect)
            if effect["status"] != "pending":
                raise Refused("effect observation exists without settlement")
            outcome_key = None if action_key is None else canonical(action_key)
            if outcome_key is not None and outcome_key in self._doc["outcomes"]:
                if canonical(self._doc["outcomes"][outcome_key]) != canonical(outcome):
                    raise Refused("action outcome identity is already recorded")
            if outcome_key is not None:
                self._doc["outcomes"][outcome_key] = dict(outcome)
                self._doc["outcomes_projection"] = canonical(
                    self._doc["outcomes"])
            effect["status"] = "settled"
            effect["observation_id"] = existing["observation_id"]
            opportunity = self._doc["opportunities"].get(effect["opportunity_id"])
            if opportunity is not None:
                opportunity["status"] = "done"
            self.save()
            return dict(effect)
        _effect, record = self._prepare_observation(observation, effect)
        outcome_key = None if action_key is None else canonical(action_key)
        if outcome_key is not None and outcome_key in self._doc["outcomes"]:
            if canonical(self._doc["outcomes"][outcome_key]) != canonical(outcome):
                raise Refused("action outcome identity is already recorded")
        if effect["status"] == "settled":
            raise Refused("effect is already settled by another observation")
        if effect["status"] != "pending":
            raise Refused("effect %r is not pending" % (effect_id,))
        self._doc["observations"].append(record)
        if outcome_key is not None:
            self._doc["outcomes"][outcome_key] = dict(outcome)
            self._doc["outcomes_projection"] = canonical(
                self._doc["outcomes"])
        effect["status"] = "settled"
        effect["observation_id"] = record["observation_id"]
        opportunity = self._doc["opportunities"].get(effect["opportunity_id"])
        if opportunity is not None:
            opportunity["status"] = "done"
        self.save()
        return dict(effect)

    def settle(self, effect_id: str, observation: dict) -> dict:
        effect = next((e for e in self._doc["pending_effects"]
                       if e["effect_id"] == effect_id), None)
        if effect is None:
            raise Refused("effect %r is not pending" % (effect_id,))
        if effect.get("charged") is not True:
            raise Refused("effect has no durable charge")
        if not isinstance(observation, dict):
            raise Refused("effect settlement needs an observation")
        stored = next((o for o in self._doc["observations"]
                       if o.get("observation_id") == observation.get(
                           "observation_id")), None)
        if stored is None:
            raise Refused("effect settlement observation is not durable")
        if stored.get("effect_id") != effect_id:
            raise Refused("effect settlement observation effect identity is not attributable")
        if not any(isinstance(stored.get(key), str) and stored[key]
                   for key in ("operation_id", "receipt_identity")):
            raise Refused("effect settlement observation is not attributable")
        _effect_identity_matches(effect, stored)
        if effect["status"] == "settled":
            if effect.get("observation_id") == stored["observation_id"]:
                return dict(effect)
            raise Refused("effect is already settled by another observation")
        if effect["status"] != "pending":
            raise Refused("effect %r is not pending" % (effect_id,))
        effect["status"] = "settled"
        effect["observation_id"] = stored["observation_id"]
        record = self._doc["opportunities"].get(
            effect["opportunity_id"])
        if record is not None:
            record["status"] = "done"
        self.save()
        return dict(effect)

    def record_outcome(self, action_key: dict, outcome: dict) -> None:
        if not isinstance(action_key, dict) or not isinstance(outcome, dict):
            raise Refused("action outcome identity and result must be objects")
        key = canonical(action_key)
        if key in self._doc["outcomes"]:
            if canonical(self._doc["outcomes"][key]) == canonical(outcome):
                return
            raise Refused("action outcome identity is already recorded")
        self._doc["outcomes"][key] = dict(outcome)
        self._doc["outcomes_projection"] = canonical(self._doc["outcomes"])
        self.save()

    def replay(self, action_key: dict) -> dict:
        if not isinstance(action_key, dict):
            return {"class": "unsupported",
                    "reason": "identity or input mismatch: action key"
                              " is not an object"}
        try:
            outcome = self._doc["outcomes"].get(canonical(action_key))
        except TypeError:
            return {"class": "unsupported",
                    "reason": "identity or input mismatch: action key"
                              " is not comparable"}
        if outcome is None:
            return {"class": "unsupported",
                    "reason": "no compatible recorded outcome"}
        self.spend({"queries": 1})
        return {"class": "recorded-replay", "outcome": dict(outcome),
                "reason": "cached-serve: exact identity and input match",
                "queries_charged": 1}

    def predict(self, action_key: dict, hypothesis: dict) -> dict:
        entry = {"key": dict(action_key), "hypothesis": dict(
            hypothesis)}
        self._doc["predictions"].append(entry)
        self.save()
        return {"class": "prediction", "hypothesis": dict(hypothesis)}

    def ready_events(self) -> list:
        events = [{"type": "opportunity-available",
                   "opportunity_id": o["opportunity_id"]}
                  for o in self.admissible()]
        events.extend({"type": "effect-pending",
                       "effect_id": e["effect_id"]}
                      for e in self.pending_effects)
        return events

    def is_quiescent(self) -> bool:
        return len(self.pending_effects) == 0

    def bind_active(self, package: dict, *,
                    acquisition_evidence: dict | None = None) -> dict:
        bound = validate_package(package, grant=self._doc["grant"])
        if self._doc["active_package"] is not None:
            raise Refused("an active program already exists; adopt a"
                          " revision instead")
        if bound["version"] != 0 or bound["parent_digest"] is not None:
            raise Refused("initial package must be version zero")
        finalization = self._durable_acquisition(
            bound, acquisition_evidence)
        acquisition_digest = (None if finalization is None else
                              finalization["evidence_digest"])
        self._doc["active_package"] = dict(bound)
        self._doc["lineage"].append(
            {"version": 0, "package_digest": bound["package_digest"],
             "parent_digest": None, "acquisition_evidence_digest":
             acquisition_digest, "package": dict(bound)})
        self._doc["private_state"] = {}
        self._doc["retained"] = {"evidence_ids": [], "obligations": []}
        self._doc["retained_projection"] = canonical(self._doc["retained"])
        if bound["origin"] == "acquired":
            self._doc["treatment_arms"]["acquired"].append(dict(bound))
            self._doc["accepted_revisions"].append(
                self._revision_record(
                    bound, arm=None, round_no=None,
                    acquisition_evidence_digest=acquisition_digest,
                    acquisition_round=(
                        None if finalization is None else finalization[
                            "round"])))
        self.save()
        return dict(bound)

    def adopt_revision(self, candidate: dict, *, arm: str | None = None,
                       round_no: int | None = None,
                       acquisition_evidence: dict | None = None) -> dict:
        active = self._validate_active_package()
        if active is None:
            raise Refused("no active program to revise")
        if not self.is_quiescent():
            raise Refused("adoption needs a quiescent boundary")
        bound = validate_package(candidate, grant=self._doc["grant"])
        if bound["package_digest"] == active["package_digest"]:
            if bound.get("origin") == "acquired":
                self._durable_acquisition(bound, acquisition_evidence)
            return dict(bound)
        if bound["parent_digest"] != active["package_digest"]:
            raise Refused("revision parent is not the active program")
        if bound["version"] != active["version"] + 1:
            raise Refused("revision version does not follow its parent")
        if (bound["op_source"] != active["op_source"]
                or bound["op_digest"] != active["op_digest"]):
            raise Refused("revision operational source does not match the"
                          " active package")
        finalization = self._durable_acquisition(
            bound, acquisition_evidence)
        acquisition_digest = (None if finalization is None else
                              finalization["evidence_digest"])
        self._doc["active_package"] = dict(bound)
        self._doc["lineage"].append(
            {"version": len(self._doc["lineage"]),
             "package_digest": bound["package_digest"],
             "parent_digest": bound["parent_digest"],
             "acquisition_evidence_digest": acquisition_digest,
             "package": dict(bound)})
        self._doc["private_state"] = {}
        self._doc["retained"] = {
            "evidence_ids": [o.get("observation_id")
                             for o in self._doc["observations"]
                             if o.get("observation_id")],
            "obligations": list(bound.get("obligations") or []),
        }
        self._doc["retained_projection"] = canonical(self._doc["retained"])
        if bound.get("origin") == "acquired" and \
                bound["package_digest"] not in {
                    c["package_digest"] for c in
                    self._doc["treatment_arms"]["acquired"]}:
            self._doc["treatment_arms"]["acquired"].append(dict(bound))
        self._doc["accepted_revisions"].append(
            self._revision_record(
                bound, arm=arm, round_no=round_no,
                acquisition_evidence_digest=acquisition_digest,
                acquisition_round=(
                    None if finalization is None else finalization[
                        "round"])))
        self._doc["staged_candidate"] = None
        self.save()
        return dict(bound)


def create_store(path, *, namespace: str, mission: dict,
                 authority: dict) -> FrontierStore:
    if namespace != NAMESPACE:
        raise Refused("lane stores live in namespace %s" % NAMESPACE)
    if not isinstance(mission, dict) or not mission.get("objective") \
            or not isinstance(mission.get("environments"), list) \
            or not mission["environments"]:
        raise Refused("mission needs an objective plus frozen"
                      " environments")
    if not isinstance(authority, dict) or not _is_count(
            authority.get("queries")) or not _is_count(
            authority.get("steps")):
        raise Refused("authority needs nonnegative query/step totals")
    store = FrontierStore.__new__(FrontierStore)
    store.path = str(path)
    store._doc = _blank_doc(namespace, mission, authority)
    store.save()
    return store
