"""AG01-EXP independent checker: rebuild totals from traces, reject violations.

Reads preserved trace files plus the frozen manifest, recomputes cost unions
(operation identities unioned, shared ancestors counted once), liabilities
and waiting measures, and re-runs the grader over scored observations. Any
altered, missing or duplicate record is reported with a reason and yields a
nonzero exit. Reports the resource vector; no universal score is invented.

Cost semantics (v2 substrate): every reservation row is either settled, in
which case its amount unioned by operation must equal the consumed total, or
unsettled, in which case it must be attributed by a pending-liability entry
carrying the operation and a reason, and its amount must equal the reserved
total. Unattributed outstanding exposure is a violation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = {"manifest_sha256", "traj_id", "world_id", "family", "variant",
            "arm", "tie", "policy_version", "backend", "rng_seed",
            "end_reason", "ticks", "observations", "products",
            "pending_drained", "ledger", "totals", "grade", "complete"}

COST_SUFFIXES = ((":explore", "explore_spent"), (":eval", "eval_spent"),
                 (":recovery", "recovery_spent"))


def _union_spent(ledger: dict, alloc_suffix: str,
                 liabilities: list) -> tuple[int, int, list]:
    liable = {entry.get("operation_id") for entry in liabilities
              if entry.get("operation_id")}
    seen_settled: dict = {}
    unsettled = 0
    reasons = []
    for res in ledger.get("reservations", []):
        if not str(res.get("allocation_id", "")).endswith(alloc_suffix):
            continue
        op = res.get("operation_id")
        if res.get("state") == "settled":
            if op in seen_settled and seen_settled[op] != res["amount"]:
                reasons.append(f"duplicate-op-conflict {op}")
            seen_settled[op] = res["amount"]
        else:
            unsettled += int(res.get("amount", 0))
            if op not in liable:
                reasons.append(f"unattributed-exposure {res.get('id')}")
    return sum(seen_settled.values()), unsettled, reasons


def check_trace(trace: dict, manifest_doc: dict, manifest_hash: str,
                world: dict | None, budgets: dict) -> list:
    reasons = []
    missing = REQUIRED - set(trace)
    if missing:
        return [f"missing-fields {sorted(missing)}"]
    if trace["manifest_sha256"] != manifest_hash:
        reasons.append("manifest-hash-mismatch")
    if world is None:
        reasons.append(f"unknown-world {trace['world_id']}")
        return reasons
    if trace["world_id"] != world["world_id"]:
        reasons.append("world-identity-mismatch")
    if not str(trace["traj_id"]).startswith(
            trace["world_id"]) or not str(trace["traj_id"]).endswith(
            f"_{trace['arm'].lower()}_t{trace['tie']}"):
        reasons.append(f"traj-identity-mismatch {trace['traj_id']}")
    expected_policy = (manifest_doc.get("policy_versions") or {}).get(trace["arm"])
    if expected_policy is not None and trace["policy_version"] != expected_policy:
        reasons.append(f"policy-version-mismatch {trace['policy_version']}"
                       f" != {expected_policy}")
    if trace.get("complete") is not True:
        reasons.append("incomplete-trajectory")
    ticks = [t["tick"] for t in trace["ticks"]]
    if ticks != list(range(len(ticks))):
        reasons.append("tick-gap-or-disorder")
    if len(ticks) > world["ticks"]:
        reasons.append("horizon-exceeded")
    ledger = trace["ledger"]
    dec_charges = sorted(res.get("operation_id") for res in ledger.get("reservations", [])
                         if ":dec:" in str(res.get("operation_id", "")))
    tick_dec_ops = [t.get("dec_op") for t in trace["ticks"]]
    if any(not op for op in tick_dec_ops):
        reasons.append("missing-decision-charge")
    elif sorted(tick_dec_ops) != dec_charges:
        reasons.append("decision-charge-mismatch "
                       f"ticks={len(tick_dec_ops)} charges={len(dec_charges)}")
    for name, want in (("sources", "source-drift"), ("files", "file-drift")):
        if name in manifest_doc and name in trace \
                and trace[name] != manifest_doc[name]:
            reasons.append(f"{want} {name}")
    if trace["arm"] not in ("R", "Q") or trace["tie"] not in (0, 1):
        reasons.append("bad-arm-or-tie")
    op_ids = [o["id"] for o in ledger.get("ops", [])]
    if len(set(op_ids)) != len(op_ids):
        reasons.append("duplicate-op-records")
    receipt_ops = {r["operation_id"] for r in ledger.get("receipts", [])}
    for op in ledger.get("ops", []):
        if op["id"] not in receipt_ops:
            reasons.append(f"effect-without-receipt {op['id']}")
    for receipt in ledger.get("receipts", []):
        if receipt["operation_id"] not in set(op_ids):
            reasons.append(f"receipt-without-effect {receipt['receipt']}")
    if int(ledger.get("conflicts", 0)) > 0:
        reasons.append("conflicting-evidence")
    liabilities = list(trace["totals"]["liabilities"])
    for liability in liabilities:
        if not liability.get("operation_id") or not liability.get("reason"):
            reasons.append("liability-unattributed")
    unsettled_ops = {res.get("operation_id") for res in ledger.get("reservations", [])
                     if res.get("state") != "settled"}
    for liability in liabilities:
        if liability.get("operation_id") not in unsettled_ops:
            reasons.append(f"liability-without-exposure {liability.get('operation_id')}")
    totals = dict(trace["totals"])
    by_id = {a["id"]: a for a in ledger.get("allocations", [])}
    for suffix, key in COST_SUFFIXES:
        rows = [a for aid, a in by_id.items() if aid.endswith(suffix)]
        if not rows:
            reasons.append(f"missing-allocation {suffix}")
            continue
        settled, open_amount, sub = _union_spent(ledger, suffix, liabilities)
        reasons.extend(sub)
        if settled != int(totals.get(key, -1)):
            reasons.append(f"cost-total-altered {suffix} ledger={settled}")
        consumed = sum(int(a["consumed"]) for a in rows)
        reserved = sum(int(a["reserved"]) for a in rows)
        if consumed != settled:
            reasons.append(f"cost-consumed-mismatch {suffix}")
        if reserved != open_amount:
            reasons.append(f"cost-reserved-mismatch {suffix} ledger={open_amount}")
        for row in rows:
            if int(row["consumed"]) + int(row["reserved"]) > int(row["authorized"]):
                reasons.append(f"allocation-over-authorized {row['id']}")
    if totals.get("eval_spent") != len(world["tasks"]):
        reasons.append("eval-cost-mismatch")
    if totals.get("recovery_spent", 0) > budgets["recovery_cap"]:
        reasons.append("recovery-cap-exceeded")
    for outcome in ledger.get("outcomes", []):
        if int(outcome.get("epoch", 0)) > int(world["ticks"]):
            reasons.append(f"outcome-beyond-horizon {outcome.get('receipt')}")
            break
    for drained in trace["pending_drained"]:
        state = next((r["state"] for r in ledger.get("reservations", [])
                      if r.get("operation_id") == drained.get("source_attempt")), None)
        if state != "settled":
            reasons.append(f"drained-unsettled {drained.get('receipt')}")
    idle = sum(1 for t in trace["ticks"] if t["decision"]["action"] == "idle")
    if idle != totals.get("idle_ticks"):
        reasons.append("idle-count-mismatch")
    caps = {s["option_key"]: s["cap"] for s in world.get("seeds", [])}
    for option_id, spent in (trace.get("option_spend") or {}).items():
        if option_id in caps and spent > caps[option_id]:
            reasons.append(f"option-cap-exceeded {option_id} {spent}>{caps[option_id]}")
    if totals.get("feasible_waiting", 0) > totals.get("idle_ticks", 0):
        reasons.append("waiting-exceeds-idle")
    try:
        from . import grader
        fresh = grader.grade(trace["observations"], trace["products"], world)
    except ImportError as exc:
        reasons.append(f"grader-refused {exc}")
        return reasons
    if fresh["correct"] != trace["grade"]["correct"]:
        reasons.append(f"grade-mismatch trace={trace['grade']['correct']}"
                       f" fresh={fresh['correct']}")
    if fresh["total"] != len(world["tasks"]):
        reasons.append("grade-task-count-mismatch")
    return reasons


def pair_key(trace: dict) -> tuple:
    return (trace["world_id"], trace["tie"])


def expected_pairs(manifest: dict) -> set:
    pairs = set()
    for world in manifest["worlds"]:
        for arm in ("R", "Q"):
            for tie in (0, 1):
                pairs.add((world["world_id"], arm, tie))
    return pairs


def check_dir(trace_dir: str | Path, manifest: dict, manifest_hash: str,
              budgets: dict, worlds_extra: dict | None = None,
              expect_full: bool = False) -> dict:
    worlds = {w["world_id"]: w for w in manifest["worlds"]}
    worlds.update(worlds_extra or {})
    traces, non_traces = [], []
    for path in sorted(Path(trace_dir).glob("*.json")):
        doc = json.loads(path.read_text())
        if isinstance(doc, dict) and doc.get("traj_id") and doc.get("world_id"):
            traces.append(doc)
        else:
            non_traces.append(path.name)
    violations = {}
    seen_ids: dict = {}
    for trace in traces:
        world = worlds.get(trace.get("world_id", ""))
        bad = check_trace(trace, manifest, manifest_hash, world, budgets)
        traj_id = trace.get("traj_id", "?")
        if traj_id in seen_ids:
            bad = list(bad) + ["duplicate-trajectory"]
        else:
            seen_ids[traj_id] = True
        if bad:
            violations[traj_id] = bad
    seen = {(t.get("world_id"), t.get("arm"), t.get("tie")) for t in traces
            if t.get("traj_id") not in violations}
    if expect_full:
        for missing in sorted(expected_pairs(manifest) - seen):
            violations[f"pair-{missing[0]}-{missing[1].lower()}-t{missing[2]}"] = [
                "incomplete-pair"]
    pairs: dict = {}
    for trace in traces:
        if trace.get("traj_id") in violations:
            continue
        pairs.setdefault(pair_key(trace), {})[trace["arm"]] = trace
    rows = []
    for (world_id, tie), arms in sorted(pairs.items()):
        if set(arms) != {"R", "Q"}:
            violations[f"pair-{world_id}-t{tie}"] = ["incomplete-pair"]
            continue
        rows.append({
            "world": world_id, "tie": tie,
            "correct_r": arms["R"]["grade"]["correct"],
            "correct_q": arms["Q"]["grade"]["correct"],
            "explore_r": arms["R"]["totals"]["explore_spent"],
            "explore_q": arms["Q"]["totals"]["explore_spent"],
            "eval": arms["R"]["totals"]["eval_spent"],
            "recovery_r": arms["R"]["totals"]["recovery_spent"],
            "recovery_q": arms["Q"]["totals"]["recovery_spent"],
            "waiting_r": arms["R"]["totals"]["idle_ticks"],
            "waiting_q": arms["Q"]["totals"]["idle_ticks"],
            "feasible_wait_r": arms["R"]["totals"]["feasible_waiting"],
            "feasible_wait_q": arms["Q"]["totals"]["feasible_waiting"],
            "liabilities_r": arms["R"]["totals"]["liabilities"],
            "liabilities_q": arms["Q"]["totals"]["liabilities"]})
    families: dict = {}
    for row in rows:
        fam = next(w["family"] for w in manifest["worlds"] if w["world_id"] == row["world"])
        agg = families.setdefault(fam, {"correct_r": 0, "correct_q": 0,
                                        "explore_r": 0, "explore_q": 0, "pairs": 0})
        agg["correct_r"] += row["correct_r"]
        agg["correct_q"] += row["correct_q"]
        agg["explore_r"] += row["explore_r"]
        agg["explore_q"] += row["explore_q"]
        agg["pairs"] += 1
    return {"traces": len(traces), "pairs": rows, "families": families,
            "violations": violations, "non_trace_files": sorted(non_traces),
            "ok": not violations}


def main(argv: list | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: checker <trace-dir> [--manifest PATH] [--subset]", file=sys.stderr)
        return 2
    trace_dir = args[0]
    manifest_path = Path(args[args.index("--manifest") + 1]) if "--manifest" in args \
        else Path(__file__).parent / "manifest.json"
    manifest = json.loads(Path(manifest_path).read_text())
    from .manifest import HASH_PATH
    manifest_hash = HASH_PATH.read_text().strip() if HASH_PATH.exists() \
        else manifest.get("manifest_sha256", "")
    report = check_dir(trace_dir, manifest, manifest_hash, manifest["budgets"],
                       expect_full="--subset" not in args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
