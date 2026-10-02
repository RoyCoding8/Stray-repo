"""Lane A baseline gap inventory and replay reconciliation (offline, stdlib only).

Fails nonzero while any known evidence gap is neither exported nor recorded
as an explicit limitation with per-obligation dispositions. Passes only when
every gap is dispositioned and a fresh replay of committed evidence matches
the totals stated in reports/workstreams/inv-a.md.

Reads committed evidence and reports. Writes nothing. No DB or provider use.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C4 = ROOT / "evidence-ad01/c4-live"
LIVE = ROOT / "evidence-live"
INV_A = ROOT / "reports/workstreams/inv-a.md"
EC02 = ROOT / "reports/EC02-CLOSURE.md"
AD01 = ROOT / "reports/AUTONOMOUS-DEVELOPMENT-01.md"
C3_MERGED = ROOT / "evidence-ad01/c3-trajectories-merged"

failures: list[str] = []
passes: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    (passes if ok else failures).append("%s: %s" % (name, detail))


def limitation_recorded(*markers: str) -> bool:
    if not INV_A.exists():
        return False
    text = re.sub(r"\s+", " ", INV_A.read_text())
    return all(m in text for m in markers)


def replay_c4() -> dict:
    pairs = sorted([f for f in C4.glob("*.json")
                    if f.name.startswith("trace-") or f.name.startswith("resume-")])
    logs = sorted([f for f in C4.glob("*.log")
                   if f.name.startswith("trace-") or f.name.startswith("resume-")])
    readable, stubs, worlds, retained_total, use_phases = [], [], set(), 0, 0
    unknown_tokens = 0
    for f in pairs:
        raw = f.read_bytes()
        if not raw.strip():
            stubs.append(f.name)
            continue
        data = json.loads(raw.decode())
        readable.append(f.name)
        worlds.add(data.get("world"))
        retained_total += int(data["accounting"]["mechanism"]["retained"])
        if data["accounting"]["use"]["model_calls"] or data["accounting"]["use"]["sandbox_ops"]:
            use_phases += 1
        if data["accounting"]["total"]["tokens"] is None:
            unknown_tokens += 1
    return {"json": len(pairs), "log": len(logs), "readable": len(readable),
            "stubs": stubs, "worlds": sorted(worlds),
            "retained": retained_total, "use_phases": use_phases,
            "unknown_tokens": unknown_tokens}


def replay_c3_use() -> int:
    total = 0
    for f in sorted(C3_MERGED.glob("use-*.json")):
        total += len(json.loads(f.read_text()))
    return total


def replay_c2() -> dict:
    acq = json.loads((LIVE / "c2-acquisition8.json").read_text())
    rep = json.loads((LIVE / "c2-acquisition8-repair.json").read_text())
    reasons = {}
    for r in acq["results"]:
        reasons[str(r["lineage"])] = sorted({f["reason"] for f in r["validation"]["failures"]})
    return {"selection": acq["selection"]["selection"],
            "init_calls": acq["accounting"]["calls_used"],
            "total_calls": rep["accounting"]["calls_used"],
            "reasons": reasons,
            "repair_reason": rep["repair_reason"]}


def main() -> int:
    c4 = replay_c4()
    check("C4-pair-count", c4["json"] == 11 and c4["log"] == 11,
          "evidence holds %d JSON + %d log (%d readable, stubs %s)" % (
              c4["json"], c4["log"], c4["readable"], c4["stubs"]))
    check("C4-single-world-no-retention", c4["worlds"] == [0] and c4["retained"] == 0
          and c4["use_phases"] == 0,
          "worlds=%s retained=%d use_phases=%d unknown_tokens=%d/9" % (
              c4["worlds"], c4["retained"], c4["use_phases"], c4["unknown_tokens"]))
    use_total = replay_c3_use()
    check("C3-use-corpus", use_total == 72, "merged use records=%d" % use_total)
    c2 = replay_c2()
    check("C2-no-selection", c2["selection"] == "none" and c2["total_calls"] == 4,
          "selection=%s calls=%d lineage_reasons=%s" % (
              c2["selection"], c2["total_calls"], c2["reasons"]))
    check("C2-lineages-differ", len(set(map(str, c2["reasons"].values()))) == 2,
          "lineage 1 vs 2 failure reasons differ")

    raw_c2 = sorted(LIVE.glob("c2-*-raw-responses.json"))
    raw_c4 = sorted(C4.glob("*-raw-responses.json"))
    check("G1-raw-model-text", bool(raw_c2 and raw_c4)
          or limitation_recorded("G1", "raw model text"),
          "raw exports c2=%d c4=%d" % (len(raw_c2), len(raw_c4)))

    receipt = list(LIVE.glob("c2-*-receipts.json")) + list(C4.glob("*-receipts.json"))
    check("G2-receipt-linkage", bool(receipt)
          or limitation_recorded("G2", "receipt"),
          "receipt exports=%d" % len(receipt))

    ledgers = [(ROOT / "reports/workstreams/inv-a-c2-ledger.json").exists(),
               (ROOT / "reports/workstreams/inv-a-c4-ledger.json").exists()]
    check("G3-effective-config", all(ledgers)
          and limitation_recorded("G3", "effective configuration"),
          "ledgers=%s" % ledgers)
    check("G4-db-identity", all(ledgers)
          and limitation_recorded("G4", "database identity"),
          "per-attempt DB identity distinguished in ledgers=%s" % ledgers)

    ad01_text = AD01.read_text() if AD01.exists() else ""
    check("G5-c4-eleven-not-twelve", "11 JSON/log pairs" in ad01_text
          and limitation_recorded("G5", "live12"),
          "AD01 report states 11 pairs and records missing live12")
    check("G6-c3-callback-scope", "_recording_learner" in ad01_text
          and "outside-menu" in ad01_text
          and limitation_recorded("G6", "callback"),
          "AD01 report qualifies C3 as callback-learner construction/use")
    ec02_text = EC02.read_text() if EC02.exists() else ""
    check("G7-c2-lineage-specific", "plan carries only action+shape+children" in ec02_text
          and "acquisition probe only" in ec02_text
          and "lineage 2" in ec02_text.lower()
          and limitation_recorded("G7", "lineage"),
          "EC02 report carries lineage-specific failure descriptions")
    check("G8-grant-reconciliation", limitation_recorded("G8", "granted root")
          and limitation_recorded("unknown liabilities"),
          "baseline reconciles granted root and unknown liabilities")

    inv_text = INV_A.read_text() if INV_A.exists() else ""
    for label, needle in [("report-11-pairs", "11 JSON/log pairs"),
                          ("report-72-use", "72"),
                          ("report-selection-none", "selection none"),
                          ("report-4-calls", "4/4")]:
        check(label, needle in inv_text, "inv-a.md states %s" % needle)

    print("lane A baseline gate: %d pass, %d fail" % (len(passes), len(failures)))
    for line in passes:
        print("  ok: %s" % line)
    for line in failures:
        print("  GAP: %s" % line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
