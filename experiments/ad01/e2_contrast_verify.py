"""Offline re-derivation of every claim the E2 contrast campaign makes.

`reports/evidence/invr1e2contrast/report.json` is a set of strings. A reader
cannot tell a measured reduction from an authored one, so this module reads
the report and re-derives each claim from the observations stored beside it,
using the campaign's own reducer and the campaign's own checker. A claim that
does not re-derive is a forgery that verified clean, which is the failure
`live_construct.preflight_decision` was written to stop.

The observation/claim split is the same one. An **observation** is a thing
that happened: the reducer's graded report on a named task at a named budget,
recomputable from the panel. A **claim** is a statement about the
observations: the paired deltas, the reachability ceiling, the size matching,
the uniformity verdict. `observations` are re-derived; `claims` are checked
against the re-derived value and reported with both.

Run: `python3 -m experiments.ad01.e2_contrast_verify reports/evidence/.../report.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import e2_contrast_campaign as campaign
from . import e2_replication as replica
from . import learner
from . import worlds


class VerifierRefused(Exception):
    """A report whose claims this verifier cannot re-derive."""


# ---------------------------------------------------------------------------
# observations, re-derived from the panel
# ---------------------------------------------------------------------------


def _panel_task_ids() -> set:
    ids = set()
    for world in worlds.world_membership(worlds.FROZEN_DIR).values():
        for families in world.values():
            for tasks in families.values():
                ids.update(str(t) for t in tasks)
    return ids


# ---------------------------------------------------------------------------
# claims, checked against the observations
# ---------------------------------------------------------------------------


def check_freeze(report: Mapping[str, Any]) -> dict:
    frozen = dict(report.get("freeze") or {})
    body = campaign.verify_contrast(frozen)
    return {"claim": "the freeze addresses the panel it ran on",
            "re_derived_digest": replica.digest_of(body),
            "recorded_digest": str(frozen.get("freeze_digest") or ""),
            "agrees": replica.digest_of(body) == frozen.get("freeze_digest"),
            "note": "the freeze is checked against the module and the panel,"
                    " so an edited body is refused here as it is at run time"}


def check_evidence(report: Mapping[str, Any]) -> dict:
    """Every record the arms carried, recomputed from the panel.

    The arms are rebuilt through the campaign's own `build_arms`, not by
    re-measuring the source and filler pools directly. The run's control arm
    is the measured filler records re-fitted to the relevant arm's exact
    character count, and that padding is part of the arm the policy was
    shown. A verifier that rebuilt the control from the raw pool would
    compare a different arm against the one the run used, and would
    disagree with a correct run.

    The rebuild is the observation. The profile is the claim about it, and
    the profile is recomputed from the rebuilt records rather than read back
    from the report.
    """
    body = campaign.verify_contrast(dict(report.get("freeze") or {}))
    target = worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])
    arms = campaign.build_arms(
        target, source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"],
        visible=learner.visible_opportunities(body["cohort_world"]))
    budgets = {replica.ARM_RELEVANT: body["evidence_max_queries"],
               replica.ARM_IRRELEVANT: body["control_max_queries"]}
    rederived = {
        name: campaign.graded_outcome_profile(
            list((arms.get(name) or {}).get("observations") or []))
        for name in (replica.ARM_RELEVANT, replica.ARM_IRRELEVANT)}
    claimed = dict(report.get("graded_outcome_profiles") or {})
    return {
        "claim": "each arm's records carry a varied graded outcome",
        "re_derived": rederived,
        "claimed": {name: claimed.get(name) for name in rederived},
        "agrees": all(rederived[name] == claimed.get(name)
                       for name in rederived),
        "per_arm_varied": {name: not rederived[name]["uniform"]
                           for name in rederived},
        "verdict_is_constant_everywhere": all(
            rederived[name]["verdict_is_constant"] for name in rederived),
        "evidence_budgets": budgets,
    }


def check_size_matching(report: Mapping[str, Any]) -> dict:
    """Equal characters and equal record counts, recomputed."""
    body = campaign.verify_contrast(dict(report.get("freeze") or {}))
    target = worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])
    arms = campaign.build_arms(
        target, source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"],
        visible=learner.visible_opportunities(body["cohort_world"]))
    rederived = campaign.require_size_matched(arms)
    claimed = dict(report.get("size_matching") or {})
    return {"claim": "the two arms carrying experience are size matched",
            "re_derived": rederived, "claimed": claimed,
            "agrees": all(
                rederived.get(arm) == claimed.get(arm)
                for arm in (replica.ARM_RELEVANT, replica.ARM_IRRELEVANT))}


def check_reachability(report: Mapping[str, Any]) -> dict:
    """The ceiling and the default, recomputed with no model and no dispatch."""
    body = campaign.verify_contrast(dict(report.get("freeze") or {}))
    rederived = campaign.reachability_census(
        body["target_task_ids"],
        method_ids=sorted({pair[0] for pair in campaign.DECISION_GRID}),
        budgets=sorted({pair[1] for pair in campaign.DECISION_GRID}))
    claimed = dict(report.get("reachability_census") or {})
    return {
        "claim": "the benefit metric can only move off the default",
        "re_derived_max_positive": rederived["max_attainable_positive_delta"],
        "claimed_max_positive": claimed.get("max_attainable_positive_delta"),
        "re_derived_max_negative": rederived["max_attainable_negative_delta"],
        "claimed_max_negative": claimed.get("max_attainable_negative_delta"),
        "agrees": (rederived["max_attainable_positive_delta"]
                   == claimed.get("max_attainable_positive_delta")
                   and rederived["max_attainable_negative_delta"]
                   == claimed.get("max_attainable_negative_delta")),
        "ceiling_is_default_on_every_target": all(
            r["attainable_positive_delta"] == 0.0
            for r in rederived["rows"]),
    }


def check_paired(report: Mapping[str, Any]) -> dict:
    """The paired deltas, recomputed from the stored observations.

    Three levels, and the third is the one that catches a forgery.

    The `normalized_reduction` a reading carries is re-derived from the
    checker's own fields beside it, `initial_measure`, `candidate_measure`
    and `verdict`, through `s09_e2_scored.normalized_reduction`. A reading
    whose stated reduction does not follow from the measures the same reading
    stores is a forgery, and it is reported as one.

    The paired deltas are then recomputed from the re-derived reductions
    rather than from the report's stated ones, and put through the frozen
    estimator. A report that records a delta its own observations do not
    produce fails.
    """
    readings = dict(report.get("readings") or {})
    rederived_readings = {}
    disagreements = []
    for arm, tasks in readings.items():
        for task_id, row in sorted((tasks or {}).items()):
            rederived_readings.setdefault(arm, {})[task_id] = {
                **row,
                replica.NORMALIZED_REDUCTION: _rederive_reduction(row)}
            if (row.get(replica.NORMALIZED_REDUCTION)
                    != _rederive_reduction(row)):
                disagreements.append("%s/%s: states %r, its own measures give %r"
                                     % (arm, task_id,
                                        row.get(replica.NORMALIZED_REDUCTION),
                                        _rederive_reduction(row)))
    rederived = replica.paired_report(rederived_readings)
    claimed = dict(report.get("paired") or {})
    rows = {}
    for name, body in rederived.items():
        other = dict(claimed.get(name) or {})
        rows[name] = {
            "re_derived_deltas": body.get("deltas"),
            "claimed_deltas": other.get("deltas"),
            "re_derived_delta": (body.get("paired") or {}).get("delta"),
            "claimed_delta": (other.get("paired") or {}).get("delta"),
            "agrees": (body.get("deltas") == other.get("deltas")
                       and (body.get("paired") or {}).get("delta")
                       == (other.get("paired") or {}).get("delta")),
            "n": (body.get("paired") or {}).get("n"),
        }
    return {
        "claim": "the paired deltas follow from the stored readings, and each"
                 " reading's reduction follows from the measures it stores",
        "contrasts": rows,
        "agrees": all(r["agrees"] for r in rows.values()) and not disagreements,
        "reduction_disagreements": disagreements,
        "estimator": replica.ESTIMATOR,
    }


def _rederive_reduction(row: Mapping[str, Any]) -> float:
    """The reduction the checker's own fields on this row give.

    `Reading.as_report` is the adapter between a Reading and a checker's
    report, and it is built here from the same four fields the adapter reads,
    so the rule is applied once and not restated.
    """
    from . import s09_e2_scored as scored

    return float(scored.normalized_reduction({
        "scored": bool(row.get("scored", True)),
        "verdict": str(row.get("verdict") or ""),
        "measure": row.get("candidate_measure") or 0,
        "initial_measure": row.get("initial_measure") or 0,
        "reason": str(row.get("reason") or "")}))


def check_accounting(report: Mapping[str, Any]) -> dict:
    """Exposure and billing, recomputed from the stored receipts.

    The receipts are the observation; the counts and the billing verdict are
    claims about them. So the counts are recomputed from the receipt rows and
    compared, rather than read back from the fields the report states.

    The billing verdict is checked the other way round: the report must not
    claim a price the receipts do not carry. `billed` and `charge_units` are
    absent from every `usage` the provider returned on this route, so a
    report that reported either as a number would be wrong, and one that
    reported `usage.cost` as a cost would be reading a field the adapter does
    not read into the one it does.
    """
    claimed = dict(report.get("accounting") or {})
    receipts = list(claimed.get("receipts") or [])
    classes: dict = {}
    for row in receipts:
        key = str(row.get("response_class") or "") or str(row.get("outcome") or "")
        classes[key] = classes.get(key, 0) + 1
    usage_keys = sorted({str(k) for row in receipts
                         for k in (row.get("usage") or {})})
    billed_present = [repr((row.get("usage") or {}).get("billed"))
                      for row in receipts if isinstance(row.get("usage"), dict)]
    charge_present = [repr((row.get("usage") or {}).get("charge_units"))
                      for row in receipts if isinstance(row.get("usage"), dict)]
    return {
        "claim": "exposure is counted in dispatches and estimated units, and"
                 " no cost is asserted from a field the adapter does not read",
        "re_derived": {
            "receipt_count": len(receipts),
            "outcome_counts": classes,
            "usage_keys_seen": usage_keys,
            "billed_values": sorted({repr(v) for v in billed_present}) or ["<absent>"],
            "charge_units_values": sorted(set(charge_present)) or ["<absent>"],
        },
        "claimed": {
            "receipt_count": claimed.get("receipt_count"),
            "outcome_counts": claimed.get("outcome_counts"),
            "usage_keys_seen": claimed.get("usage_keys_seen"),
            "billed": claimed.get("billed"),
            "charge_units": claimed.get("charge_units"),
        },
        "agrees": (len(receipts) == claimed.get("receipt_count")
                   and classes == claimed.get("outcome_counts")
                   and usage_keys == claimed.get("usage_keys_seen")),
        # A receipt's usage is the adapter's normalised `Usage`, so a field
        # the provider never sent is present and null. The check is that
        # neither billing field carries a value, and that the report does not
        # present the route's own `usage.cost` as one the store holds.
        "no_price_claimed": (all(v in ("None", "") for v in billed_present)
                             and all(v in ("None", "") for v in charge_present)),
        "cost_not_read_as_a_price": (
            "usage.cost" in str(claimed.get("discrepancy") or "")),
        "receipt_usage_is_adapter_normalised": all(
            set((row.get("usage") or {})) >= {"billed", "charge_units",
                                              "input_tokens", "output_tokens",
                                              "charge_scale"}
            for row in receipts if isinstance(row.get("usage"), dict)),
    }


def check_no_key(report: Mapping[str, Any], key: str) -> dict:
    """The gateway key is absent from the artifact, as a substring check."""
    if not key:
        return {"claim": "no key to check", "agrees": True, "checked": False}
    blob = json.dumps(report, sort_keys=True, default=str)
    return {"claim": "the artifact carries no gateway key",
            "agrees": key.strip() not in blob, "checked": True}


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------

CHECKS = (
    ("freeze", check_freeze),
    ("evidence", check_evidence),
    ("size_matching", check_size_matching),
    ("reachability", check_reachability),
    ("paired", check_paired),
    ("accounting", check_accounting),
)


def verify(report: Mapping[str, Any], *, key: str = "") -> dict:
    """Every claim, re-derived, and whether the artifact survives.

    A check that raises is reported as a failure with its reason rather than
    aborting the run, so a reader sees all of them at once. `agrees` is the
    conjunction; a single disagreement fails the artifact.
    """
    results, failures = {}, []
    for name, check in CHECKS:
        try:
            result = check(report)
        except Exception as exc:
            result = {"claim": name, "agrees": False,
                      "error": "%s: %s" % (type(exc).__name__, exc)}
        results[name] = result
        if not result.get("agrees"):
            failures.append(name)
    results["no_key"] = check_no_key(report, key)
    if not results["no_key"].get("agrees"):
        failures.append("no_key")
    return {"namespace": report.get("namespace"),
            "campaign_kind": report.get("campaign_kind"),
            "checks": results,
            "failed": sorted(failures),
            "agrees": not failures,
            "claim_class": "every claim is re-derived from an observation"
                           " stored in the report, and no claim is taken on"
                           " trust"}


def red_proof(report: Mapping[str, Any]) -> dict:
    """Forge the report three ways and show the verifier catches each.

    A verifier that has never rejected anything has not been shown to work.
    Each forgery is a self-consistent one: the fabricated value is internally
    coherent and differs from the truth in exactly one claim, which is the
    shape a real forgery takes.

    One: a paired delta the report's own observations do not produce.
    Two: a delta inflated *together with* the reduction that produced it, so
    the report is self-consistent and the checker still fails. This is the
    forgery E1 verified clean, and it is why the reduction is re-derived from
    the measures rather than read.
    Three: an evidence profile claiming a uniform arm the panel does not have.
    Four: a reachability ceiling above what any decision reaches.
    """
    import copy

    out = {}
    readings = dict(report.get("readings") or {})

    forged = copy.deepcopy(report)
    target_contrast = next(iter(forged.get("paired") or {}), None)
    if target_contrast and readings.get(replica.ARM_RELEVANT):
        task_id = sorted(readings[replica.ARM_RELEVANT])[0]
        row = dict(readings[replica.ARM_RELEVANT][task_id])
        row["normalized_reduction"] = float(row.get("normalized_reduction") or 0.0) + 0.5
        forged["readings"] = {**readings,
                              replica.ARM_RELEVANT: {**readings[replica.ARM_RELEVANT],
                                                     task_id: row}}
        out["inflated_reduction"] = _run(forged)

    forged = copy.deepcopy(report)
    treatment = dict(forged.get("readings") or {}).get(replica.ARM_RELEVANT) or {}
    if treatment:
        task_id = sorted(treatment)[0]
        row = dict(treatment[task_id])
        # Shrink the candidate so the stated reduction is internally
        # consistent with it, and move the delta to match. A reader checking
        # only that the report agrees with itself finds nothing wrong.
        initial = int(row.get("initial_measure") or 0)
        inflated = min(0.99, float(row.get("normalized_reduction") or 0.0) + 0.4)
        row["candidate_measure"] = max(0, int(round(initial * (1 - inflated))))
        row["normalized_reduction"] = inflated
        forged["readings"] = {**readings,
                              replica.ARM_RELEVANT: {**treatment, task_id: row}}
        forged["paired"] = replica.paired_report(forged["readings"])
        out["self_consistent_inflation"] = _run(forged)

    forged = copy.deepcopy(report)
    if forged.get("graded_outcome_profiles"):
        forged["graded_outcome_profiles"] = {
            name: {**dict(value or {}), "uniform": True,
                   "delivered_uniform": True, "delivered_grades": 1}
            for name, value in forged["graded_outcome_profiles"].items()}
        out["claimed_uniform_arm"] = _run(forged)

    forged = copy.deepcopy(report)
    if forged.get("reachability_census"):
        forged["reachability_census"] = {
            **forged["reachability_census"],
            "max_attainable_positive_delta": 0.5}
        out["inflated_ceiling"] = _run(forged)
    return out


def _run(forged: Mapping[str, Any]) -> dict:
    try:
        outcome = verify(forged)
    except Exception as exc:
        return {"agrees": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {"agrees": outcome["agrees"], "failed": outcome["failed"]}


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="re-derive every claim in an E2 contrast report")
    parser.add_argument("report", help="path to report.json")
    parser.add_argument("--red-proof", action="store_true",
                        help="forge the report and show the verifier refuses")
    args = parser.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    key = ""
    import os

    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    outcome = verify(report, key=key)
    payload = {"verification": outcome}
    if args.red_proof:
        payload["red_proof"] = red_proof(report)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0 if outcome["agrees"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
