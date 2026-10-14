from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

POLICIES = ("structured/1", "raw-history/1", "adaptive/1")
CONDITIONS = ("complete", "misleading", "source-removed")
MATRIX = tuple((policy, condition) for policy in POLICIES for condition in CONDITIONS)
LIVE_ALIAS = "openrouter/openrouter/free"
TASK_INSTRUCTION = (
    "Implement maximum(xs). Determine the empty-list convention from prior checked "
    "maximum experience and reflect it in the implementation."
)
LESSON = (
    "sorted(xs)[-1] computes a maximum for nonempty lists but fails on empty lists. "
    "The checked empty-input task specifies a zero default."
)
MISLEADING_LESSON = (
    "The checked empty-input task means an empty list should raise IndexError; "
    "keep sorted(xs)[-1] as the maximum rule."
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _cell_id(policy: str, condition: str) -> str:
    return f"p03-context03-{policy.replace('/', '-')}-{condition}"


def _manifest_matrix(manifest: dict) -> tuple[tuple[str, str], ...]:
    raw = manifest.get("matrix")
    if not isinstance(raw, list):
        raise ValueError("manifest has no ordered matrix")  # noqa: TRY004
    cells = []
    for item in raw:
        if isinstance(item, list) and len(item) == 2:
            policy, condition = item
        elif isinstance(item, dict):
            policy, condition = item.get("policy"), item.get("condition")
        else:
            raise ValueError("manifest matrix entry is malformed")
        if (not isinstance(policy, str) or not isinstance(condition, str)
                or (policy, condition) not in MATRIX):
            raise ValueError("manifest contains an unpermitted policy or condition")
        cells.append((policy, condition))
    if tuple(cells) != MATRIX:
        raise ValueError("manifest must contain the complete ordered nine-cell matrix")
    return tuple(cells)


def _verify_packet(record: dict, packet: dict) -> None:
    packet_digest = packet.get("digest")
    body = {key: value for key, value in packet.items() if key != "digest"}
    if not isinstance(packet_digest, str) or _digest(_canonical(body)) != packet_digest:
        raise ValueError(f"{record['cell_id']}: context packet digest mismatch")
    request = packet.get("request") or {}
    if request.get("policy") != record["policy"]:
        raise ValueError(f"{record['cell_id']}: packet policy differs from frozen cell")
    corpus = record.get("corpus")
    if not isinstance(corpus, dict):
        raise ValueError(f"{record['cell_id']}: authored corpus is missing")  # noqa: TRY004
    corpus_body = {key: value for key, value in corpus.items() if key != "digest"}
    if corpus.get("digest") != _digest(_canonical(corpus_body)):
        raise ValueError(f"{record['cell_id']}: authored corpus digest mismatch")
    expected_lesson = MISLEADING_LESSON if record["condition"] == "misleading" else LESSON
    if (corpus.get("claim_text") != expected_lesson
            or corpus.get("claim_status") != "challenged"
            or corpus.get("task_instruction") != TASK_INSTRUCTION
            or corpus.get("claim_version") != 2
            or corpus.get("required_observation_id") != corpus.get("opposition_id")):
        raise ValueError(f"{record['cell_id']}: cell does not contain its frozen challenged lesson")
    if request.get("required_observation_ids") != [corpus.get("required_observation_id")]:
        raise ValueError(f"{record['cell_id']}: packet request lost its named required source")
    counts = packet.get("counts")
    view = packet.get("memory_view")
    if not isinstance(counts, dict) or not isinstance(view, dict):
        raise ValueError(f"{record['cell_id']}: packet counts or memory view are missing")  # noqa: TRY004
    continuation = {**request.get("continuation", {}), "context_packet": packet}
    if counts.get("packet_bytes") != len(_canonical(continuation)):
        raise ValueError(f"{record['cell_id']}: packet byte count does not match its continuation")
    if (counts.get("claims") != len(view.get("claims", []))
            or counts.get("observations") != len(view.get("observations", []))):
        raise ValueError(f"{record['cell_id']}: packet source counts are inconsistent")
    excerpt_bytes = sum(len(item.get("text", "").encode("utf-8"))
                        for item in packet.get("excerpts", [])
                        if isinstance(item, dict) and isinstance(item.get("text"), str))
    if counts.get("excerpt_bytes") != excerpt_bytes:
        raise ValueError(f"{record['cell_id']}: packet excerpt byte count is inconsistent")
    budget = request.get("budget", {})
    if (counts.get("packet_bytes", 0) > budget.get("packet_bytes", 0)
            or counts.get("scanned_bytes", 0) > budget.get("scan_bytes", 0)
            or counts.get("excerpt_bytes", 0) > budget.get("excerpt_bytes", 0)
            or counts.get("actions", 0) > budget.get("actions", 0)):
        raise ValueError(f"{record['cell_id']}: packet exceeds its frozen construction budget")


def _decision_input(record: dict) -> dict | None:
    decisions = record.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError(f"{record['cell_id']}: decisions are missing")  # noqa: TRY004
    worker = [item for item in decisions if item.get("kind") == "worker"]
    if len(worker) > 1:
        raise ValueError(f"{record['cell_id']}: cell used more than one worker decision")
    if not worker:
        return None
    visible = worker[0].get("data", {}).get("visible_input")
    if not isinstance(visible, dict):
        raise ValueError(f"{record['cell_id']}: worker decision has no visible input")  # noqa: TRY004
    return visible


def _verify_last_observation(record: dict) -> None:
    observation = (record.get("state") or {}).get("last_observation")
    attempts = record.get("attempt_observations")
    if observation is None:
        if attempts != []:
            raise ValueError(f"{record['cell_id']}: state omitted its recorded attempt observation")
        return
    if not isinstance(observation, dict):
        raise ValueError(f"{record['cell_id']}: last observation is malformed")  # noqa: TRY004
    if not isinstance(attempts, list):
        raise ValueError(f"{record['cell_id']}: attempt observations are missing")  # noqa: TRY004
    matching = [item for item in attempts
                if isinstance(item, dict) and item.get("content") == observation]
    if len(matching) != 1:
        raise ValueError(f"{record['cell_id']}: last observation differs from its attempt observation")
    attempt = matching[0]
    decisions = record.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError(f"{record['cell_id']}: decisions are missing")  # noqa: TRY004
    decision_matches = [item for item in decisions
                        if isinstance(item, dict) and item.get("id") == attempt.get("decision_id")
                        and item.get("kind") == "worker"]
    if len(decision_matches) != 1:
        raise ValueError(f"{record['cell_id']}: last observation has no unique worker decision")
    worker_operation = (decision_matches[0].get("data") or {}).get("operation_id")
    if not isinstance(worker_operation, str) or observation.get("episode") != worker_operation:
        raise ValueError(f"{record['cell_id']}: last observation episode differs from its worker decision")
    verdict = observation.get("verdict")
    if type(observation.get("passed")) is bool and verdict is None:
        raise ValueError(f"{record['cell_id']}: graded observation has no verifier operation")
    if verdict is not None:
        operations = record.get("operations")
        if (not isinstance(verdict, str) or not isinstance(operations, list)
                or re.fullmatch(r"rsi-verify-[0-9a-f]{64}", verdict) is None
                or sum(isinstance(item, dict) and item.get("id") == verdict
                       for item in operations) != 1
                or verdict == worker_operation):
            raise ValueError(f"{record['cell_id']}: last observation verdict has no verifier operation")


def _selected_sources(packet: dict) -> dict:
    view = packet.get("memory_view") or {}
    observations = [{
        "observation_id": item.get("observation_id"),
        "artifacts": item.get("artifacts", []),
        "task_instruction": item.get("content", {}).get("task_instruction"),
        "passed": item.get("content", {}).get("passed"),
    } for item in view.get("observations", [])]
    claims = [{
        "claim_id": item.get("claim_id"), "version": item.get("version"),
        "status": item.get("status"), "text": item.get("text"),
        "support": item.get("support", []), "opposition": item.get("opposition", []),
    } for item in view.get("claims", [])]
    return {"claims": claims, "observations": observations}


def _verify_invocation(record: dict, visible: dict, packet: dict) -> None:
    invocation = record.get("invocation")
    if not isinstance(invocation, dict):
        raise ValueError(f"{record['cell_id']}: worker decision has no invocation export")  # noqa: TRY004
    instruction = invocation.get("instruction")
    if not isinstance(instruction, str):
        raise ValueError(f"{record['cell_id']}: rendered instruction is missing")  # noqa: TRY004
    raw = instruction.encode("utf-8")
    if (invocation.get("instruction_bytes") != len(raw)
            or invocation.get("instruction_sha256") != _digest(raw)):
        raise ValueError(f"{record['cell_id']}: rendered instruction digest mismatch")
    match = re.search(r"^Continuation \(JSON\):\n(.*?)(?:\n\nInput digest:|\Z)",
                      instruction, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"{record['cell_id']}: rendered instruction omits its continuation")
    continuation = json.loads(match.group(1))
    if continuation != visible or continuation.get("context_packet") != packet:
        raise ValueError(f"{record['cell_id']}: broker instruction is disconnected from decision packet")
    continuation_digest = _digest(_canonical(continuation))
    if (invocation.get("continuation") != continuation
            or invocation.get("continuation_sha256") != continuation_digest
            or invocation.get("packet_sha256") != packet.get("digest")
            or invocation.get("connected") is not True):
        raise ValueError(f"{record['cell_id']}: invocation digest chain is disconnected")
    input_digest = re.search(r"^Input digest: ([0-9a-f]{64})$", instruction, re.MULTILINE)
    if not input_digest or invocation.get("input_digest") != input_digest.group(1):
        raise ValueError(f"{record['cell_id']}: worker input digest is missing or changed")
    manifest = record.get("input_manifest")
    if not isinstance(manifest, list):
        raise ValueError(f"{record['cell_id']}: staged input manifest is missing")  # noqa: TRY004
    expected_manifest = hashlib.sha256(_canonical(manifest)).hexdigest()
    if expected_manifest != input_digest.group(1):
        raise ValueError(f"{record['cell_id']}: staged input digest is disconnected")
    operations = record.get("operations", [])
    operation_ids = {item.get("id") for item in operations}
    if invocation.get("operation_id") not in operation_ids:
        raise ValueError(f"{record['cell_id']}: invocation operation is absent from accounting export")
    operation = next(item for item in operations
                     if item.get("id") == invocation.get("operation_id"))
    if (invocation.get("payload_digest") != operation.get("payload_digest")
            or invocation.get("receipts") != operation.get("receipts")):
        raise ValueError(f"{record['cell_id']}: invocation receipt accounting is disconnected")
    child_inputs = record.get("child_inputs", [])
    if record.get("mode") == "fixture":
        if len(child_inputs) != 1:
            raise ValueError(f"{record['cell_id']}: fixture child input count is not one")
        child = child_inputs[0]
        if (child.get("context_packet") != packet or child.get("continuation") != continuation
                or child.get("prompt") != instruction):
            raise ValueError(f"{record['cell_id']}: actual fixture child received disconnected context")


def _operation_usage(operation: dict) -> dict:
    operation_id = operation.get("id")
    unknown = {"operation_id": operation_id, "tokens": None, "status": "unknown"}
    receipts = operation.get("receipts")
    if not isinstance(receipts, list) or operation.get("settled") is not True:
        return unknown
    if not receipts:
        return unknown
    total = 0
    identities = set()
    for receipt in receipts:
        if (not isinstance(receipt, dict) or receipt.get("operation_id") != operation_id
                or not isinstance(receipt.get("receipt_identity"), str)
                or not receipt["receipt_identity"]
                or receipt["receipt_identity"] in identities):
            return unknown
        identities.add(receipt["receipt_identity"])
        tokens = receipt.get("tokens")
        if (not isinstance(tokens, dict)
                or type(tokens.get("input_tokens")) is not int
                or type(tokens.get("output_tokens")) is not int
                or min(tokens["input_tokens"], tokens["output_tokens"]) < 0):
            return unknown
        total += tokens["input_tokens"] + tokens["output_tokens"]
    return {"operation_id": operation_id, "tokens": total, "status": "measured"}


def _aggregate_worker_usage(operations: list[dict], worker_id: str | None) -> dict:
    if worker_id is None:
        return {"recorded_tokens": 0, "known_token_subtotal": 0,
                "unknown_usage_operations": [], "unknown_usage_operation_count": 0,
                "worker_usage": {"operation_id": None, "tokens": 0,
                                 "status": "not_dispatched"}}
    worker_operation = next((item for item in operations if item.get("id") == worker_id), None)
    usage = (_operation_usage(worker_operation) if worker_operation is not None else
             {"operation_id": worker_id, "tokens": None, "status": "unknown"})
    unknown = [worker_id] if usage["status"] == "unknown" else []
    subtotal = usage["tokens"] if not unknown else 0
    return {"recorded_tokens": usage["tokens"], "known_token_subtotal": subtotal,
            "unknown_usage_operations": unknown,
            "unknown_usage_operation_count": len(unknown), "worker_usage": usage}


def recompute(manifest: dict, records: list[dict]) -> dict:
    _manifest_matrix(manifest)
    by_cell = {}
    database_ids = set()
    driver_digests = set()
    source_digest_sets = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("cell export is not an object")  # noqa: TRY004
        policy, condition = record.get("policy"), record.get("condition")
        cell_id = record.get("cell_id")
        if (policy, condition) not in MATRIX or cell_id != _cell_id(policy, condition):
            raise ValueError("cell export is outside the frozen matrix")
        if cell_id in by_cell:
            raise ValueError(f"duplicate cell export: {cell_id}")
        by_cell[cell_id] = record
        if not isinstance(record.get("database_id"), str) or record["database_id"] in database_ids:
            raise ValueError("each cell must identify a distinct fresh database")
        database_ids.add(record["database_id"])
    expected_ids = {_cell_id(policy, condition) for policy, condition in MATRIX}
    if set(by_cell) != expected_ids:
        missing = sorted(expected_ids - set(by_cell))
        extra = sorted(set(by_cell) - expected_ids)
        raise ValueError(f"matrix exports are incomplete (missing={missing}, extra={extra})")

    expected_alias = manifest.get("model_alias")
    if not isinstance(expected_alias, str):
        raise ValueError("manifest has no frozen model alias")  # noqa: TRY004
    modes = {record.get("mode") for record in by_cell.values()}
    if len(modes) != 1:
        raise ValueError("cells mix fixture and live modes")
    mode = next(iter(modes))
    if mode == "live" and expected_alias != LIVE_ALIAS:
        raise ValueError("live manifest does not name the permitted free alias")
    source_pins = manifest.get("source_sha256")
    if mode == "live" and (not isinstance(source_pins, dict) or not source_pins):
        raise ValueError("live manifest requires prospective source pins")
    if "source_sha256" in manifest and (not isinstance(source_pins, dict) or not source_pins):
        raise ValueError("manifest prospective source pins are malformed")
    if any(record.get("model_alias") != expected_alias for record in by_cell.values()):
        raise ValueError("cell model alias differs from the frozen manifest")

    candidate_digests = {record.get("candidate_task_digest") for record in by_cell.values()}
    genome_digests = {record.get("genome_digest") for record in by_cell.values()}
    if len(candidate_digests) != 1 or len(genome_digests) != 1:
        raise ValueError("cells do not share the frozen task and genome")

    for cell_id, record in by_cell.items():
        freeze = record.get("freeze")
        if not isinstance(freeze, dict) or freeze.get("cell_id") != cell_id:
            raise ValueError(f"{cell_id}: cell freeze is missing or mismatched")
        if record.get("freeze_sha256") != _digest(_canonical(freeze)):
            raise ValueError(f"{cell_id}: frozen configuration digest mismatch")
        if freeze.get("matrix") != [list(pair) for pair in MATRIX]:
            raise ValueError(f"{cell_id}: per-cell freeze changed the ordered matrix")
        source_digests = freeze.get("source_sha256")
        if not isinstance(source_digests, dict) or not source_digests:
            raise ValueError(f"{cell_id}: source digests are missing")
        if source_pins is not None:
            for path, digest in source_digests.items():
                if source_pins.get(path) != digest:
                    raise ValueError(f"{cell_id}: runtime source differs from prospective source pin")
            driver_pin = source_pins.get("experiments/context03/driver.py")
            if not isinstance(driver_pin, str) or freeze.get("driver_sha256") != driver_pin:
                raise ValueError(f"{cell_id}: driver differs from prospective source pin")
        if freeze.get("policy") != record["policy"] or freeze.get("condition") != record["condition"]:
            raise ValueError(f"{cell_id}: freeze identity differs from the cell")
        if freeze.get("model_alias") != expected_alias:
            raise ValueError(f"{cell_id}: model alias differs from the frozen campaign")
        driver_digests.add(freeze.get("driver_sha256"))
        source_digest_sets.add(_digest(_canonical(source_digests)))
        packet = record.get("context_packet")
        if not isinstance(packet, dict):
            raise ValueError(f"{cell_id}: context packet is missing")  # noqa: TRY004
        _verify_packet(record, packet)
        request = packet["request"]
        if (request.get("scope") != freeze.get("memory", {}).get("scope")
                or request.get("limit") != freeze.get("memory", {}).get("limit")
                or request.get("budget") != freeze.get("context_packet_budget")
                or request.get("continuation", {}).get("objective") != TASK_INSTRUCTION):
            raise ValueError(f"{cell_id}: packet differs from the frozen task scope or budget")
        if record.get("selected_sources") != _selected_sources(packet):
            raise ValueError(f"{cell_id}: exported source references differ from the packet")
        visible = _decision_input(record)
        _verify_last_observation(record)
        condition = record["condition"]
        if condition == "source-removed":
            required_id = record["corpus"]["required_observation_id"]
            names_required_source = any(
                item.get("kind") == "observation" and item.get("id") == required_id
                for item in packet.get("needs", []) if isinstance(item, dict))
            if (packet.get("status") != "needs_information" or visible is not None
                    or record.get("operations") or record.get("child_inputs")
                    or record.get("invocation") is not None
                    or (record.get("state") or {}).get("status") != "ready"
                    or not names_required_source):
                raise ValueError(f"{cell_id}: source removal dispatched or lost its cached packet")
            outcome = record.get("step_outcome", {}).get("context_outcome", {})
            if outcome.get("packet") != packet or outcome.get("status") != "needs_information":
                raise ValueError(f"{cell_id}: source-removal receipt is disconnected from cached packet")
        else:
            if packet.get("status") != "ready" or visible is None:
                raise ValueError(f"{cell_id}: completed condition lacks a ready worker decision")
            if visible.get("context_packet") != packet:
                raise ValueError(f"{cell_id}: decision continuation dropped its context packet")
            _verify_invocation(record, visible, packet)

    if len(driver_digests) != 1 or len(source_digest_sets) != 1:
        raise ValueError("cells do not share the frozen driver and source digests")

    for condition in CONDITIONS:
        peers = [by_cell[_cell_id(policy, condition)] for policy in POLICIES]
        corpora = [item.get("corpus", {}).get("digest") for item in peers]
        revisions = [item.get("corpus", {}).get("prior_memory_revision") for item in peers]
        if len(set(corpora)) != 1 or len(set(revisions)) != 1:
            raise ValueError(f"{condition}: policy cells do not share the frozen corpus revision")

    measured = []
    for policy, condition in MATRIX:
        record = by_cell[_cell_id(policy, condition)]
        state = record.get("state", {})
        observation = state.get("last_observation") or {}
        passed = observation.get("passed")
        packet = record["context_packet"]
        counts = packet.get("counts") or {}
        operations = record.get("operations", [])
        all_receipts = [receipt for op in operations for receipt in op.get("receipts", [])]
        invocation = record.get("invocation")
        usage = _aggregate_worker_usage(
            operations, invocation.get("operation_id") if invocation else None)
        measured.append({
            "cell_id": record["cell_id"], "policy": policy, "condition": condition,
            "build_status": packet.get("status"), "passed": passed,
            "worker_dispatched": record.get("invocation") is not None,
            **usage,
            "receipt_count": len(all_receipts), "step_elapsed_ms": record.get("step_elapsed_ms"),
            "build_counts": {key: counts.get(key) for key in
                             ("claims", "observations", "scanned_bytes", "excerpt_bytes",
                              "actions", "packet_bytes")},
            "instruction_bytes": (record.get("invocation") or {}).get("instruction_bytes"),
        })
    dispatched = [item for item in measured if item["worker_dispatched"]]
    completed = [item for item in dispatched if item["passed"] is not None]
    quality = (sum(item["passed"] is True for item in completed) / len(completed)
               if completed else None)
    baseline = by_cell[_cell_id("structured/1", "complete")]
    baseline_pass = (baseline["context_packet"].get("status") == "ready"
                     and (baseline.get("state", {}).get("last_observation") or {}).get("passed") is True
                     and (baseline.get("invocation") or {}).get("connected") is True)
    return {
        "schema": "p03-context-recompute/1", "mode": mode, "model_alias": expected_alias,
        "matrix_cells": len(measured), "dispatched_workers": len(dispatched),
        "verified_quality_rate": quality, "structured_complete_baseline_pass": baseline_pass,
        "source_removal_refusals": sum(item["build_status"] == "needs_information"
                                        for item in measured if item["condition"] == "source-removed"),
        "recorded_token_total": (sum(item["recorded_tokens"] for item in measured)
                                 if all(item["recorded_tokens"] is not None for item in measured)
                                 else None),
        "known_token_subtotal": sum(item["known_token_subtotal"] for item in measured),
        "unknown_usage_operations": [operation_id for item in measured
                                     for operation_id in item["unknown_usage_operations"]],
        "unknown_usage_operation_count": sum(
            item["unknown_usage_operation_count"] for item in measured),
        "cells": measured,
        "claim_limit": "recorded outcomes and worker token usage; per-operation costs remain attributed in receipts, and response authenticity is not proven",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute the frozen P03 matched comparison offline.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--record", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = [json.loads(path.read_text(encoding="utf-8")) for path in args.record]
    result = recompute(manifest, records)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
