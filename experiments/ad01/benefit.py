"""Frozen primary benefit rule, I vs R (AD01 §7, declarative).

I must show no validity-failure increase and no solved/valid loss in either
domain, strictly greater total normalized reduction on valid outputs, and
total model tokens, witness queries and sandbox operations each within
1.25x of R. Invalid/unknown outputs score zero reduction; any unknown
mandatory measurement makes the verdict unevaluable. Minimum valid size is
1; empty candidates can never verify preserved, so they score zero.
"""

from __future__ import annotations

import hashlib
import json

from .checker import ARMS, COST_KEYS, UNKNOWN

BENEFIT_RULE = {
    "freeze": "ad01",
    "per_domain": {
        "max_validity_failure_increase": 0,
        "min_solved_delta": 0,
    },
    "total": {
        "reduction": "strictly-greater",
    },
    "cost_ratio_limit": 1.25,
    "cost_keys": list(COST_KEYS),
    "unknown": "unevaluable",
    "invalid_unknown_reduction": 0.0,
    "min_valid_size": 1,
}

FAILURES = frozenset({"invalid", "unknown"})


def digest() -> str:
    raw = (json.dumps(BENEFIT_RULE, sort_keys=True) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


def _ratio(top: float, bottom: float) -> float:
    if bottom > 0:
        return top / bottom
    return 0.0 if top == 0 else float("inf")


def evaluate(records: list) -> dict:
    by_arm: dict = {}
    for arm in ARMS:
        by_arm[arm] = [r for r in records if r["arm"] == arm]
    for record in records:
        for key in COST_KEYS:
            if record["costs"][key] == UNKNOWN:
                return {"verdict": "unevaluable",
                        "reasons": ["unknown-cost %s" %
                                    record["record_id"]],
                        "per_domain": {}}
        for name in ("initial_measure", "final_measure"):
            if record[name] == UNKNOWN:
                return {"verdict": "unevaluable",
                        "reasons": ["unknown-measure %s" %
                                    record["record_id"]],
                        "per_domain": {}}
    per_domain: dict = {}
    reasons: list = []
    ok = True
    for domain in ("software", "graph"):
        rows = {arm: [r for r in by_arm[arm] if r["domain"] == domain]
                for arm in ARMS}
        failures = {arm: sum(1 for r in rows[arm]
                             if r["verdict"] in FAILURES) for arm in ARMS}
        solved = {arm: sum(1 for r in rows[arm]
                           if r["verdict"] == "preserved") for arm in ARMS}
        per_domain[domain] = {"failures": failures, "solved": solved}
        if failures["I"] - failures["R"] > 0:
            ok = False
            reasons.append("validity-regression %s" % domain)
        if solved["I"] - solved["R"] < 0:
            ok = False
            reasons.append("solved-loss %s" % domain)
    reduction = {arm: sum(r["normalized_reduction"] for r in by_arm[arm]
                          if r["verdict"] == "preserved") for arm in ARMS}
    costs = {arm: {key: sum(r["costs"][key] for r in by_arm[arm])
                   for key in COST_KEYS} for arm in ARMS}
    if not reduction["I"] > reduction["R"]:
        ok = False
        reasons.append("reduction-not-greater %s vs %s" %
                       (reduction["I"], reduction["R"]))
    for key in COST_KEYS:
        ratio = _ratio(costs["I"][key], costs["R"][key])
        if ratio > BENEFIT_RULE["cost_ratio_limit"]:
            ok = False
            reasons.append("cost-ratio %s %.3f" % (key, ratio))
    return {"verdict": "benefit" if ok else "no-benefit",
            "reasons": reasons, "per_domain": per_domain,
            "reduction": reduction, "costs": costs}
