"""Derived corrections for the Team 01 live2 campaign (lane D closure).

Reads the committed raw bundle only and publishes separate linked derived
views; raw episode records are never modified. Covers the delivery-closure
repairs: refusal counted as zero success with receipt-derived usage, the
refusal / unavailable-evidence / unsettled-effect three-way distinction,
the calibration-vs-probe count correction, operation-identity-union
campaign totals, and the advisory-text labeling of coordination-template/2.

Offline: no gateway, no database, no model calls.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

import sys

sys.path.insert(0, str(ROOT))

from experiments.team01 import checker  # noqa: E402

REFUSED_CELL = "live2-S-team01-t06-r2"
CORRECTION_FILES = ("derived-correction-live2.json", "derived-totals-live2.json")


def load_bundle(evidence: Path) -> dict:
    records = {}
    for path in sorted((evidence / "episodes").glob("*.json")):
        record = json.loads(path.read_bytes())
        records[record["episode_id"]] = record
    recon = json.loads((evidence / "reconciliation-live2.json").read_bytes())
    build = json.loads((evidence / "builds" / "build-1.json").read_bytes())
    frozen = json.loads((evidence / "template-frozen-live2.json").read_bytes())
    verdict = json.loads((evidence / "verdict-live2.json").read_bytes())
    return {"records": records, "recon": recon, "build": build,
            "frozen": frozen, "verdict": verdict}


def recon_by_id(recon: dict) -> dict:
    return {d["episode_id"]: d for d in recon["detail"]}


def classify_cell(episode_id: str, record: dict | None,
                  detail: dict | None) -> dict:
    if record is None or detail is None:
        return {"episode_id": episode_id, "outcome_state": "missing-record",
                "evidence_state": "unavailable-evidence",
                "effect_state": "unsettled-effect",
                "accounting_agreement": False, "solved": None,
                "usage_record": None,
                "usage_receipts": (detail or {}).get("usage_receipts"),
                "usage_corrected": (detail or {}).get("usage_receipts")}
    if detail.get("missing_receipts"):
        evidence = "unavailable-evidence"
    else:
        evidence = "available"
    outcome = record.get("outcome")
    if outcome == "success":
        solved: bool | None = True
    elif outcome in ("failure", "refused"):
        solved = False
    else:
        solved = None
    receipts = detail.get("usage_receipts") or {}
    accounted = detail.get("usage_ok", False)
    alloc_ok = detail.get("balance", -1) >= 0 \
        and detail.get("alloc_ok", False)
    if detail.get("missing_receipts") or not alloc_ok:
        effect = "unsettled-effect"
    else:
        effect = "settled"
    return {"episode_id": episode_id, "outcome_state": outcome,
            "evidence_state": evidence, "effect_state": effect,
            "accounting_agreement": bool(accounted), "solved": solved,
            "usage_record": record.get("usage"),
            "usage_receipts": receipts, "usage_corrected": receipts}


def corrected_rule_input(records: dict, by_id: dict) -> dict:
    adjusted = {}
    for episode_id, record in records.items():
        key = (record.get("panel"), record.get("arm"),
               record.get("task_id"), record.get("repeat"))
        view = copy.deepcopy(record)
        if record.get("outcome") == "refused":
            view["outcome"] = "failure"
            tokens = (by_id.get(episode_id) or {}).get("usage_receipts") or {}
            view["usage"] = {"in": tokens.get("in", 0),
                             "out": tokens.get("out", 0)}
            costs = view.get("costs") or {}
            costs["model_tokens"] = {"in": tokens.get("in", 0),
                                     "out": tokens.get("out", 0)}
            view["costs"] = costs
        adjusted[key] = view
    return adjusted


def recompute_panels(bundle: dict) -> dict:
    records = bundle["records"]
    by_id = recon_by_id(bundle["recon"])
    cells = {cid: classify_cell(cid, records.get(cid), by_id.get(cid))
             for cid in sorted(set(records) | set(by_id))}
    adjusted = corrected_rule_input(records, by_id)
    controls = dict(bundle["verdict"].get("controls") or {})
    out = {"cells": cells,
           "eval": checker.finite_panel_rule(adjusted, controls, "eval"),
           "transfer": checker.finite_panel_rule(adjusted, controls,
                                                 "transfer")}
    out["refusal_note"] = (
        "live2-S-team01-t06-r2 refused with no submittable artifact; "
        "counted as zero success (solved=false) with receipt-derived "
        "usage 890 in / 563 out. Raw record outcome stays 'refused'.")
    out["template_label"] = template_label(bundle["frozen"])
    return out


def template_label(frozen: dict) -> dict:
    directive = frozen.get("directive") or ""
    return {
        "version": frozen.get("version"),
        "digest": frozen.get("digest"),
        "directive_chars": len(directive),
        "semantic_role": "advisory text",
        "applies_when": {
            "text": frozen.get("applies_when"),
            "enforced": False,
            "enforcement_site": None,
        },
        "note": ("Model-generated directive text appended to planner and "
                 "constructor prompts; no executable composition with "
                 "parameter bindings, no enforced applicability check. "
                 "Executable coordination-template acquisition remains open."),
    }


def episode_op_ids(records: dict) -> set:
    seen = set()
    for record in records.values():
        for op in (record.get("constructor_ops") or []):
            if op.get("op_id"):
                seen.add(op["op_id"])
        for op in (record.get("tool_ops") or []):
            if op.get("op_id"):
                seen.add(op["op_id"])
        for receipt in (record.get("receipts") or []):
            seen.add(receipt)
    return seen


def compute_totals(bundle: dict) -> dict:
    records = bundle["records"]
    groups: dict = {}
    for record in records.values():
        probe = record.get("probe")
        if record.get("panel") == "dev":
            group = "calibration" if probe is None else "probe-%s" % probe
        else:
            group = record.get("panel")
        entry = groups.setdefault(group, {"episodes": [], "success": 0,
                                          "failure": 0, "refused": 0})
        entry["episodes"].append(record["episode_id"])
        entry[record.get("outcome")] = entry.get(record.get("outcome"),
                                                 0) + 1
    for entry in groups.values():
        entry["episodes"].sort()
        entry["count"] = len(entry["episodes"])
    ep_model = sum(r.get("model_calls", 0) for r in records.values())
    ep_tool = sum(r.get("tool_calls", 0) for r in records.values())
    ep_in = sum((r.get("usage") or {}).get("in", 0)
                for r in records.values())
    ep_out = sum((r.get("usage") or {}).get("out", 0)
                 for r in records.values())
    episode_only = {"episodes": len(records), "model_calls": ep_model,
                    "tool_calls": ep_tool, "usage_in": ep_in,
                    "usage_out": ep_out}
    build = bundle["build"]
    construction = {
        "op_id": build.get("op_id"),
        "model_calls": 1,
        "tool_calls": 0,
        "usage_in": (build.get("usage") or {}).get("in", 0),
        "usage_out": (build.get("usage") or {}).get("out", 0),
        "receipts": build.get("receipts") or [],
    }
    overlap = episode_op_ids(records) & set(construction["receipts"])
    whole = {"episodes": len(records), "construction_ops": 1,
             "model_calls": ep_model + construction["model_calls"],
             "tool_calls": ep_tool + construction["tool_calls"],
             "usage_in": ep_in + construction["usage_in"],
             "usage_out": ep_out + construction["usage_out"],
             "op_identity_overlap": sorted(overlap)}
    recon = bundle["recon"]
    ledger_match = (episode_only["model_calls"] == recon["model_calls"]
                    and episode_only["tool_calls"] == recon["tool_calls"]
                    and episode_only["usage_in"] == recon["usage_in"]
                    and episode_only["usage_out"] == recon["usage_out"])
    return {
        "groups": groups,
        "calibration_correction": {
            "reported": "10 success, 2 failure (t09 S+T join-rejected)",
            "stored": ("9 success, 3 failure: t09 S+T pass protected 6/6 "
                       "but join-rejected; t09 P fails protected 0/6 and "
                       "join-rejected"),
        },
        "episode_only": episode_only,
        "construction": construction,
        "whole_campaign": whole,
        "ledger_crosscheck": ledger_match,
        "unavailable": ("No pre-ledger campaign-chargeable calls are "
                        "recorded in the committed bundle; in-episode "
                        "retries are inside episode usage. Anything earlier "
                        "is unavailable, not estimated."),
    }


def write_derived(evidence: Path) -> list:
    bundle = load_bundle(evidence)
    correction = recompute_panels(bundle)
    totals = compute_totals(bundle)
    correction["links"] = {
        "raw_episodes": "episodes/",
        "reconciliation": "reconciliation-live2.json",
        "historical_verdict": "verdict-live2.json",
        "companion": "derived-totals-live2.json",
    }
    totals["links"] = {
        "raw_episodes": "episodes/",
        "ledger": "campaign-ledger-live2.json",
        "reconciliation": "reconciliation-live2.json",
        "construction": "builds/build-1.json",
        "companion": "derived-correction-live2.json",
    }
    paths = []
    for name, payload in (("derived-correction-live2.json", correction),
                          ("derived-totals-live2.json", totals)):
        path = evidence / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        paths.append(path)
    return paths


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)
    for path in write_derived(Path(args.evidence)):
        print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
