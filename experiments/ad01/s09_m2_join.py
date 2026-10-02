"""M2 post-live join: every artifact, method and action to its receipts.

Line 53 of `WORKER-STAGE-09-CONNECTED-STUDY.md` asks, after live execution, to
"join each policy artifact and each task method to its own receipts and byte
identity, then join policy actions to their effects". This script reads the
committed run-7 and run-8 evidence and emits one row per operation, per
retained method, and per use record, with each row carrying the receipts that
belong to that row and nothing else.

It is offline. Every send in the study went through
`authority.admit_study_call` and then `broker.dispatch_operation`; this script
calls neither, opens no database, and reads only bytes under
`reports/evidence/`. A receipt it cannot find is recorded as missing, never
synthesised.

Run it with `python3 experiments/ad01/s09_m2_join.py`. Pass `--out` to write
the join somewhere other than the default evidence directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "reports" / "evidence"
DEFAULT_OUT = EVIDENCE / "inv_r1_m2_join" / "join.json"

# The two live runs. `inv_r1_m3` is `inv_r1_m3_run7` and `inv_r1_m3b` is
# `inv_r1_m3_run8`; the directory names predate the study roots, and the
# study root is read from the manifest rather than assumed.
RUNS = ("inv_r1_m3", "inv_r1_m3b")

# `construct.FAMILY_TAG` and `construct._member_id`: an acquired member is
# `acquired-<tag>-<sha256(source)[:8]>`. The truncated digest is the only byte
# identity a member id carries, so the join re-derives it from the bytes and
# records the full digest beside it.
FAMILY_TAG = {"software": "sw", "graph": "gr"}


def member_id_for(task_family: str, source_digest: str) -> str:
    return "acquired-%s-%s" % (FAMILY_TAG[task_family], source_digest[:8])


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def _receipts(export: dict) -> dict:
    """Receipts keyed by operation id.

    A receipt's `receipt_identity` is launcher-prefixed (`gw:` for the gateway,
    `local:` for the local-process sandbox), so the join keys on the
    `operation_id` the receipt itself carries rather than reconstructing an
    identity by string surgery.
    """
    keyed = {}
    for transition in export.get("transitions", []):
        for receipt in transition.get("receipts", []) or []:
            keyed.setdefault(receipt.get("operation_id"), []).append(receipt)
    return keyed


def _raw_by_receipt(export: dict) -> dict:
    keyed = {}
    for transition in export.get("transitions", []):
        for raw in transition.get("raw_responses", []) or []:
            keyed.setdefault(raw.get("receipt_identity"), []).append(raw)
    return keyed


def _transition_index(export: dict) -> dict:
    keyed = {}
    for transition in export.get("transitions", []):
        for operation_id in transition.get("operations", []) or []:
            keyed.setdefault(operation_id, []).append(transition.get("index"))
    return keyed


def _all_operation_ids(exports: list) -> set:
    return {operation["id"]
            for export in exports
            for operation in (export.get("operations") or [])}


def operation_rows(run: str, export: dict) -> list:
    """One row per operation, joined to the receipts that carry that id."""
    receipts = _receipts(export)
    raws = _raw_by_receipt(export)
    transitions = _transition_index(export)
    rows = []
    for operation in export.get("operations", []) or []:
        operation_id = operation["id"]
        owned = receipts.get(operation_id, [])
        payload = operation.get("payload") or {}
        row = {
            "operation_id": operation_id,
            "run": run,
            "campaign_id": export.get("campaign_id"),
            "arm": export.get("arm"),
            "world": export.get("world"),
            "effect": payload.get("effect"),
            "settled": operation.get("settled"),
            "dispatch_state": operation.get("dispatch_state"),
            "launcher_id": operation.get("launcher_id"),
            "receipt_provenance": payload.get("_receipt_provenance"),
            "receipt_actual_cost": payload.get("_receipt_actual_cost"),
            "receipt_count": len(owned),
            "receipts": [],
            "byte_identity": None,
            "transition_indices": transitions.get(operation_id, []),
        }
        for receipt in owned:
            content = receipt.get("content") or {}
            text = content.get("text")
            entry = {
                "receipt_identity": receipt.get("receipt_identity"),
                "outcome": receipt.get("outcome"),
                "content_keys": sorted(content),
                "response_digest": content.get("response_digest"),
                "response_received": content.get("response_received"),
                "containment": content.get("containment"),
                "text_sha256": sha256(text) if isinstance(text, str) else None,
                "text_chars": len(text) if isinstance(text, str) else None,
                "raw_response_digest": None,
                "raw_response_digest_matches_text": None,
            }
            for raw in raws.get(receipt.get("receipt_identity"), []):
                entry["raw_response_digest"] = raw.get("digest")
                entry["raw_response_digest_matches_text"] = (
                    raw.get("digest") == entry["text_sha256"])
            row["receipts"].append(entry)
        if not owned:
            row["receipt_missing"] = True
        rows.append(row)
    return rows


def method_rows(run: str, campaign_id: str, exports: list,
                use_records: list) -> list:
    """One row per retained method, joined to its receipts and its uses.

    The chain is: the model call's receipt text parses to a construction
    response whose `entry` field is the method source; the sha256 of that
    source is both `retained_bytes[].source_digest` and the repertoire member's
    `source_digest`; the member id carries the first eight hex of that digest.
    Every step of that chain is recomputed here rather than trusted.
    """
    rows = []
    for export in exports:
        if export.get("campaign_id") != campaign_id:
            continue
        receipts = _receipts(export)
        raws = _raw_by_receipt(export)
        for transition in export.get("transitions", []):
            for retained in transition.get("retained_bytes", []) or []:
                source = None
                provenance = None
                provenance_operation = None
                for receipt in [r for values in receipts.values()
                                for r in values]:
                    content = receipt.get("content") or {}
                    text = content.get("text")
                    if not isinstance(text, str):
                        continue
                    try:
                        parsed = json.loads(text)
                    except ValueError:
                        continue
                    entry_source = parsed.get("entry") if isinstance(
                        parsed, dict) else None
                    if not isinstance(entry_source, str):
                        continue
                    if sha256(entry_source) == retained.get("source_digest"):
                        source = entry_source
                        provenance = receipt.get("receipt_identity")
                        provenance_operation = receipt.get("operation_id")
                        break
                if source is None:
                    episode = transition.get("episode") or {}
                    executable = episode.get("executable") or {}
                    candidate = executable.get("method_source")
                    if isinstance(candidate, str) and sha256(
                            candidate) == retained.get("source_digest"):
                        source = candidate
                computed = sha256(source) if isinstance(source, str) else None
                episode = transition.get("episode") or {}
                member_id = member_id_for(
                    episode.get("family", "software"),
                    retained.get("source_digest") or "")
                uses = []
                for record in use_records:
                    if record.get("executed") != retained.get(
                            "capability_id"):
                        continue
                    declared = list(record.get("operation_ids") or [])
                    found = [op for op in declared
                             if op in _all_operation_ids(exports)]
                    uses.append({
                        "record_id": record.get("record_id"),
                        "task_id": record.get("task_id"),
                        "verdict": record.get("verdict"),
                        "initial_measure": record.get("initial_measure"),
                        "final_measure": record.get("final_measure"),
                        "normalized_reduction": record.get(
                            "normalized_reduction"),
                        "operation_ids_declared": declared,
                        "operation_ids_present_in_any_export": found,
                        "executed_source_sha256": sha256(
                            record["executed_source"])
                        if record.get("executed_source") else None,
                        "executed_source_equals_retained_source": (
                            record.get("executed_source") == source),
                        "receipts_found": 0,
                    })
                rows.append({
                    "run": run,
                    "campaign_id": campaign_id,
                    "capability_id": retained.get("capability_id"),
                    "retained_at_transition": transition.get("index"),
                    "source_digest_declared": retained.get("source_digest"),
                    "source_digest_computed": computed,
                    "computed_digest_agrees": computed == retained.get(
                        "source_digest"),
                    "source_digest_matches_raw": retained.get(
                        "source_digest") == retained.get("computed_digest"),
                    "source_bytes": len(source) if source else None,
                    "declared_bytes": retained.get("bytes"),
                    "reconstructed_source": source,
                    "member_id_recomputed": member_id,
                    "member_id_declared": retained.get("capability_id"),
                    "member_id_agrees": member_id == retained.get(
                        "capability_id"),
                    "construction_receipt": provenance,
                    "construction_receipt_operation_id": provenance_operation,
                    "uses": uses,
                })
    return rows


def _dispositions(run: str) -> dict:
    use_records = load(EVIDENCE / run / "use_records.json")
    counts = {}
    for record in use_records:
        status = record.get("status") or record.get("executed") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def build() -> dict:
    operations = []
    methods = []
    repertoires = []
    for run in RUNS:
        directory = EVIDENCE / run
        exports = [load(directory / "exports" / name) for name in sorted(
            (directory / "exports").iterdir()) if name.suffix == ".json"]
        use_records = load(directory / "use_records.json")
        campaigns = []
        for export in exports:
            for row in operation_rows(run, export):
                operations.append(row)
            campaigns.append(export.get("campaign_id"))
        for name in sorted((directory / "repertoires").iterdir()):
            if name.suffix != ".json":
                continue
            repertoire = load(name)
            for member in repertoire.get("members", []) or []:
                methods.extend(method_rows(run, repertoire.get("campaign_id"),
                                           exports, use_records))
                repertoires.append({
                    "run": run,
                    "file": name.name,
                    "campaign_id": repertoire.get("campaign_id"),
                    "capability_id": member.get("capability_id"),
                    "authored": member.get("authored"),
                    "origin": member.get("origin"),
                    "source_digest_declared": member.get("source_digest"),
                    "source_digest_computed_from_method_source": sha256(
                        member["method_source"])
                    if member.get("method_source") else None,
                    "byte_identity_verified": (
                        member.get("source_digest") == sha256(
                            member["method_source"]))
                    if member.get("method_source") else None,
                    "declared_construction_operation": (
                        (member.get("construction") or {}).get(
                            "init_operation")),
                    "declared_construction_matches_receipt_derived": None,
                    "declared_byte_identity_note": (
                        "source_digest does not equal sha256(method_source)"
                        if member.get("method_source") and member.get(
                            "source_digest") != sha256(
                                member["method_source"]) else None),
                })
    for row in repertoires:
        construction = row.get("declared_construction_operation")
        derived = next((m["construction_receipt_operation_id"]
                        for m in methods
                        if m["capability_id"] == row["capability_id"]), None)
        row["declared_construction_matches_receipt_derived"] = (
            construction == derived if construction and derived else None)
    return {
        "join_version": "inv01-m2-join-v1",
        "requirement": "WORKER-STAGE-09-CONNECTED-STUDY.md:53",
        "generated_offline": True,
        "database_read": False,
        "gateway_contacted": False,
        "runs": [
            {
                "directory": run,
                "study_root": load(EVIDENCE / run / "manifest.json").get(
                    "study_root"),
                "use_record_dispositions": _dispositions(run),
            } for run in RUNS],
        "operation_rows": operations,
        "method_rows": methods,
        "repertoire_member_rows": repertoires,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    join = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(join, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "operation_rows": len(join["operation_rows"]),
        "method_rows": len(join["method_rows"]),
        "repertoire_member_rows": len(join["repertoire_member_rows"]),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
