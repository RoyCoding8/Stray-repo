"""Agency-boundary data surface (AD01 §8 AD-08).

Human-set fields (objective, environment, capabilities, limits, rules,
interventions) and system-chosen fields (opportunities, diagnostics,
candidates, reuse) live in structurally distinct namespaces with explicit
provenance tags. This module owns the schema; T-ADTR drives population
through the trajectory entry.
"""

from __future__ import annotations

AGENCY_SCHEMA = {
    "human_set": ("objective", "freeze_id", "freeze_digest",
                  "seed_capabilities", "allocation_caps",
                  "benefit_rule_digest", "stop_conditions",
                  "interventions"),
    "system_chosen": ("selected_opportunity", "competing_explanation",
                      "diagnostic", "candidate_lineage", "abandoned",
                      "reuse_decision", "next_allocation"),
}


def make_envelope(charter: dict, trajectory: dict) -> dict:
    human, chosen = (set(AGENCY_SCHEMA["human_set"]),
                     set(AGENCY_SCHEMA["system_chosen"]))
    if set(charter) - human:
        raise ValueError("charter-holds-system-or-unknown-fields %s"
                         % sorted(set(charter) - human))
    if set(trajectory) - chosen:
        raise ValueError("trajectory-holds-human-or-unknown-fields %s"
                         % sorted(set(trajectory) - chosen))
    if set(charter) & set(trajectory):
        raise ValueError("shared-keys-across-namespaces")
    envelope = {
        "charter": {key: {"value": charter[key], "set_by": "human"}
                    for key in charter},
        "trajectory": {key: {"value": trajectory[key], "set_by": "system"}
                       for key in trajectory},
    }
    envelope["charter"].setdefault("interventions",
                                   {"value": [], "set_by": "human"})
    return envelope


def record_intervention(envelope: dict, kind: str, reason: str) -> dict:
    if kind not in ("stop", "amend"):
        raise ValueError("unknown-intervention %r" % kind)
    if not reason:
        raise ValueError("intervention-requires-reason")
    updated = {"charter": dict(envelope["charter"]),
               "trajectory": dict(envelope["trajectory"])}
    log = list(updated["charter"]["interventions"]["value"])
    log.append({"kind": kind, "reason": reason, "set_by": "human"})
    updated["charter"]["interventions"] = {"value": log,
                                           "set_by": "human"}
    return updated
