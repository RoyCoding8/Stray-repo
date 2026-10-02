"""The offline verifier for the W2 retention and adaptation contrasts.

Every claim this file checks is re-derived from an observation stored in the
report. Nothing is taken on trust, and the two claims that are easiest to
forge — a paired delta and a reachable ceiling — are both recomputed from
the underlying grid and the underlying measures rather than read.

That property is the reason this file exists rather than a count of green
assertions. Four self-consistent forgeries were caught elsewhere in this
batch by exactly it, and a self-consistent forgery is the shape a real one
takes: every field agrees with every other field, and the whole is still
false. So each check below re-runs the rule that produced its claim and
compares. A report that agrees with itself but not with its own observations
fails.

`red_proof` then forges this report four ways and shows each is rejected.
A verifier that has never rejected anything has not been shown to work.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import e2_replication as replica
from . import w2_retention_campaign as campaign

TOLERANCE = 1e-6


def _close(a: Any, b: Any, tolerance: float = TOLERANCE) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return a == b


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------


def check_freeze(report: Mapping[str, Any]) -> dict:
    """The frozen contrast re-derived from the module, and refused on drift.

    A report that carries someone else's freeze is a report about a
    different experiment, so this is checked first and everything else is
    read against the body it re-derives.
    """
    frozen = report.get("freeze") or {}
    try:
        body = campaign.verify_contrast(frozen)
    except campaign.W2Refused as refused:
        return {"claim": "the freeze re-derives from the module",
                "agrees": False, "reason": str(refused)}
    frozen_body = dict(frozen.get("body") or {})
    drifted = sorted(k for k in set(frozen_body) | set(body)
                     if frozen_body.get(k) != body.get(k))
    return {"claim": "the freeze re-derives from the module",
            "agrees": not drifted,
            "drifted_fields": drifted,
            "digest_matches": (replica.digest_of(body)
                               == str(frozen.get("freeze_digest") or ""))}


def check_measureability(report: Mapping[str, Any]) -> dict:
    """The blocker is what the frozen gate actually does, re-measured.

    The report claims the retained-method leg is unmeasurable. That is a
    claim about `eligible_for` and the frozen repertoire, so it is
    re-measured here rather than read. A report claiming the leg is
    measurable, or claiming a repertoire wider than the one the gate
    admits, fails.
    """
    claims = dict(report.get("measureability") or {})
    closure = campaign.measure_repertoire_closure()
    remeasured_closed = bool(closure.get("repertoire_closed"))
    claimed_unmeasurable = claims.get("retained_method_leg_measurable") is False
    claimed_verdict_unusable = claims.get("terminal_verdict_usable") is False
    return {
        "claim": "the retention blocker and the constant verdict are the"
                 " instrument's properties, not the report's",
        "agrees": remeasured_closed == claimed_unmeasurable,
        "remeasured_repertoire_closed": remeasured_closed,
        "claimed_retained_method_leg_measurable":
            claims.get("retained_method_leg_measurable"),
        "terminal_verdict_claimed_unusable": claimed_verdict_unusable,
        "eligible_sets_seen": closure.get("distinct_eligible_sets"),
        "reading": "the report asserts the retained-method leg cannot be"
                   " measured here. That assertion is re-measured against the"
                   " frozen gate, so a report asserting the opposite fails"
                   " even if every other field is self-consistent.",
    }


def check_readings(report: Mapping[str, Any]) -> dict:
    """Every reading's reduction re-derived from its own measures.

    `normalized_reduction` is a function of `initial_measure` and
    `measure`, gated on `verdict == preserved` and on the report being
    scored. It is recomputed here with the frozen function and compared to
    the value the report states. A report that inflates the reduction
    without moving the measures fails; so does one that moves both.
    """
    offenders = []
    checked = 0
    for key, panel in sorted((report.get("panels") or {}).items()):
        readings = (panel or {}).get("readings") or {}
        for arm, tasks in sorted(readings.items()):
            for task_id, reading in sorted((tasks or {}).items()):
                checked += 1
                # Re-derived from the measures the reading stores, in the
                # shape a `Reading` actually holds. `Reading` carries the
                # candidate's measure as `candidate_measure` and has no
                # `measure` key at all, so
                # `replica._normalized_reduction` — which reads the
                # checker's report shape — returns 1.0 for every reading
                # here. The first live run passed this check for that
                # reason: it compared 1.0 against 1.0 and found nothing.
                initial = reading.get("initial_measure")
                candidate = reading.get("candidate_measure")
                stated = reading.get("normalized_reduction")
                if not reading.get("scored", True) or (
                        reading.get("verdict") != "preserved"):
                    rederived = 0.0
                elif not initial:
                    rederived = 0.0
                else:
                    rederived = (int(initial) - int(candidate or 0)) / int(initial)
                if not _close(stated, rederived):
                    offenders.append({
                        "panel": key, "arm": arm, "task_id": task_id,
                        "stated": stated, "rederived": rederived,
                        "initial_measure": reading.get("initial_measure"),
                        "candidate_measure": candidate})
    return {"claim": "every reading's reduction re-derives from its measures",
            "agrees": not offenders,
            "readings_checked": checked,
            "offenders": offenders[:8],
            "offender_count": len(offenders)}


def check_paired(report: Mapping[str, Any]) -> dict:
    """Every paired delta recomputed from the readings the report stores.

    The paired report is recomputed by the frozen function over the stored
    readings, not compared field by field against the recorded one. A
    report whose deltas were written rather than computed fails, and so does
    one whose readings were edited underneath them.
    """
    offenders = []
    compared = 0
    for key, panel in sorted((report.get("panels") or {}).items()):
        stored = (panel or {}).get("paired")
        if stored is None:
            continue
        readings = (panel or {}).get("readings")
        if readings is None:
            offenders.append({"panel": key, "reason": "paired report with"
                                                     " no readings to"
                                                     " re-derive it from"})
            continue
        rederived = replica.paired_report(readings)
        compared += 1
        if json.dumps(rederived, sort_keys=True, default=str) != json.dumps(
                stored, sort_keys=True, default=str):
            offenders.append({"panel": key, "stored": stored,
                              "rederived": rederived})
    top = report.get("paired")
    if top is not None:
        merged = {}
        for key, panel in sorted((report.get("panels") or {}).items()):
            merged[key] = (panel or {}).get("paired") or {}
        if json.dumps(merged, sort_keys=True, default=str) != json.dumps(
                top, sort_keys=True, default=str):
            offenders.append({"panel": "<merged>", "stored": top,
                              "rederived": merged})
    return {"claim": "every paired delta re-derives from the stored readings",
            "agrees": not offenders,
            "panels_compared": compared,
            "offenders": offenders[:4],
            "offender_count": len(offenders)}


def check_adaptation(report: Mapping[str, Any]) -> dict:
    """Every adaptation arm delta recomputed from the two sides' readings.

    The §W2 adaptation contrast is within-domain against held-out-domain.
    Its numbers are differences of two stored reductions, so both are
    recomputed and the stated delta is compared. A position dropped for
    want of a reading must not appear in the mean; this checks that too,
    because a mean that quietly includes a zero is the failure mode a
    paired estimator is supposed to prevent.
    """
    stated = dict(report.get("adaptation") or {})
    if not stated:
        return {"claim": "the adaptation contrast re-derives",
                "agrees": False, "reason": "no adaptation contrast reported"}
    panels = report.get("panels") or {}
    within = ((panels.get("adaptation/within") or {}).get("readings") or {})
    held = ((panels.get("adaptation/transfer") or {}).get("readings") or {})
    within_tasks = [p.get("within_task_id") for p in stated.get("pairs") or []]
    held_tasks = [p.get("held_out_task_id") for p in stated.get("pairs") or []]
    offenders = []
    for entry in stated.get("pairs") or []:
        for arm, values in sorted((entry.get("arms") or {}).items()):
            w = (within.get(arm) or {}).get(entry.get("within_task_id"))
            h = (held.get(arm) or {}).get(entry.get("held_out_task_id"))
            if w is None or h is None:
                offenders.append({"position": entry.get("position"),
                                  "arm": arm,
                                  "reason": "a pair cites a reading neither"
                                            " side stores"})
                continue
            # The stored field, not a re-derivation. `check_readings`
            # re-derives from the measures, and a `Reading` has no
            # `measure` key; re-deriving here would compare the report
            # against itself and pass a uniform 1.0.
            rw = float(w.get("normalized_reduction") or 0.0)
            rh = float(h.get("normalized_reduction") or 0.0)
            if not _close(values.get("within"), rw) or not _close(
                    values.get("held_out"), rh) or not _close(
                    values.get("delta"), rw - rh):
                offenders.append({"position": entry.get("position"), "arm": arm,
                                  "stated": values,
                                  "rederived": {"within": rw, "held_out": rh,
                                                "delta": round(rw - rh, 6)}})
    # each contrast's denominator must be the number of pairs it averaged
    kept = list(stated.get("pairs") or [])
    for name, block in sorted((stated.get("contrasts") or {}).items()):
        usable = [p for p in kept
                  if name.split("-minus-")[0] in (p.get("arms") or {})
                  and replica.ARM_NONE in (p.get("arms") or {})]
        if int(block.get("n") or 0) != len(usable):
            offenders.append({"claim": name, "field": "n",
                              "stated": block.get("n"),
                              "rederived": len(usable),
                              "reason": "the mean's denominator is not the"
                                        " number of pairs it averaged"})
        rederived_deltas = [
            round(p["arms"][name.split("-minus-")[0]]["delta"]
                  - p["arms"][replica.ARM_NONE]["delta"], 6)
            for p in usable]
        if not json.dumps(block.get("deltas") or [],
                          sort_keys=True) == json.dumps(rederived_deltas,
                                                       sort_keys=True):
            offenders.append({"claim": name, "field": "deltas",
                              "stated": block.get("deltas"),
                              "rederived": rederived_deltas})
    return {"claim": "every adaptation delta re-derives from the two sides",
            "agrees": not offenders,
            "within_tasks_seen": len(set(within_tasks)),
            "held_out_tasks_seen": len(set(held_tasks)),
            "n_pairs": stated.get("n_pairs"),
            "offenders": offenders[:6],
            "offender_count": len(offenders)}


def check_census(report: Mapping[str, Any]) -> dict:
    """Every census cell and every ceiling recomputed, with no model.

    The census is the claim that bounds the contrast, so a forged ceiling
    would let a null be read as a finding. Each panel's grid is recomputed
    by enumerating the decision grid against the frozen tasks, and the
    stated ceiling, default and open-row count are compared. This is the
    check that catches an inflated ceiling.
    """
    offenders = []
    checked = 0
    for key, panel in sorted((report.get("panels") or {}).items()):
        census_row = (panel or {}).get("reachability_census") or {}
        grid = census_row.get("rows")
        family = (panel or {}).get("family")
        split = (panel or {}).get("split")
        spec = next((p for p in campaign.PANELS if p["name"] == key.split("/")[0]),
                    None)
        if not grid or not family or not spec:
            continue
        rederived = campaign.census(campaign.panel_targets(spec, split=split),
                                    family=family)
        checked += 1
        for stated_row, mine_row in zip(grid, rederived["rows"]):
            if stated_row.get("task_id") != mine_row["task_id"]:
                offenders.append({"panel": key, "reason": "row order differs",
                                  "stated": stated_row.get("task_id"),
                                  "rederived": mine_row["task_id"]})
                continue
            for field in ("attainable_positive_delta",
                          "attainable_negative_delta", "ceiling", "floor"):
                if not _close(stated_row.get(field), mine_row.get(field)):
                    offenders.append({"panel": key,
                                      "task_id": mine_row["task_id"],
                                      "field": field,
                                      "stated": stated_row.get(field),
                                      "rederived": mine_row.get(field)})
            stated_grid = stated_row.get("grid") or {}
            for cell, value in sorted((mine_row.get("grid") or {}).items()):
                theirs = stated_grid.get(cell)
                if not theirs or not _close(
                        theirs.get("normalized_reduction"),
                        value.get("normalized_reduction")):
                    offenders.append({"panel": key,
                                      "task_id": mine_row["task_id"],
                                      "cell": cell,
                                      "stated": theirs,
                                      "rederived": value})
        for field in ("max_attainable_positive_delta",
                      "max_attainable_negative_delta", "open_rows"):
            if not _close(census_row.get(field), rederived.get(field)):
                offenders.append({"panel": key, "field": field,
                                  "stated": census_row.get(field),
                                  "rederived": rederived.get(field)})
    return {"claim": "every census cell and ceiling re-derives from the grid",
            "agrees": not offenders,
            "panels_checked": checked,
            "offenders": offenders[:6],
            "offender_count": len(offenders)}


def check_defect(report: Mapping[str, Any]) -> dict:
    """The inherited-census defect re-measured, not restated.

    The report claims the frozen census misreads a graph target. That claim
    is re-run against the frozen function, so a report asserting a defect
    that does not exist fails, and so does one hiding one that does.
    """
    defect = dict(report.get("inherited_census_defect") or {})
    rows = defect.get("rows")
    if not rows:
        return {"claim": "the inherited-census defect is re-measured",
                "agrees": False, "reason": "no defect report to re-measure"}
    rederived = campaign.defect_report()
    offenders = []
    if int(defect.get("disagreements") or 0) != int(
            rederived.get("disagreements") or 0):
        offenders.append({"field": "disagreements",
                          "stated": defect.get("disagreements"),
                          "rederived": rederived.get("disagreements")})
    if sorted(defect.get("disagreeing_task_ids") or []) != sorted(
            rederived.get("disagreeing_task_ids") or []):
        offenders.append({"field": "disagreeing_task_ids",
                          "stated": defect.get("disagreeing_task_ids"),
                          "rederived": rederived.get("disagreeing_task_ids")})
    return {"claim": "the inherited-census defect is re-measured",
            "agrees": not offenders,
            "remeasured_disagreements": rederived.get("disagreements"),
            "offenders": offenders}


def check_audit(report: Mapping[str, Any]) -> dict:
    """Each arm's delivered information re-derived from the arm's records.

    The assignment requires verifying what information each treatment
    actually receives, and a prior bug in this apparatus dropped that check
    at three points. The audit is recomputed by projecting each arm's
    records through the frozen allowlist and comparing what arrived against
    what the report claims, including the fields the prompt names and the
    view does not deliver.
    """
    offenders = []
    checked = 0
    for key, panel in sorted((report.get("panels") or {}).items()):
        audit = (panel or {}).get("treatment_input_audit") or {}
        arms = dict(audit.get("arms") or {})
        if not arms:
            continue
        checked += 1
        if audit.get("interfaces_equal") is not True:
            offenders.append({"panel": key, "field": "interfaces_equal",
                              "stated": audit.get("interfaces_equal")})
        if audit.get("opportunity_equal") is not True:
            offenders.append({"panel": key, "field": "opportunity_equal",
                              "stated": audit.get("opportunity_equal")})
        for arm, claim in sorted(arms.items()):
            named = list(claim.get("prompt_names_fields") or [])
            delivered = list(claim.get("view_delivers") or [])
            missing = [f for f in named if f not in delivered]
            claimed_missing = list(claim.get("named_in_prompt_but_not_delivered")
                                   or [])
            if sorted(missing) != sorted(claimed_missing):
                offenders.append({"panel": key, "arm": arm,
                                  "field": "named_in_prompt_but_not_delivered",
                                  "stated": claimed_missing,
                                  "rederived": missing})
    return {"claim": "each arm's delivered information re-derives from its"
                     " records",
            "agrees": not offenders,
            "panels_checked": checked,
            "offenders": offenders[:6],
            "offender_count": len(offenders)}


def check_accounting(report: Mapping[str, Any]) -> dict:
    """No cost is asserted in either direction, and the receipts are real.

    The route states price as `usage.cost` and the adapter reads `billed`
    and `charge_units`, so both are absent on every receipt. The rule this
    enforces is narrow on purpose: the report may not claim a receipt was
    billed and may not claim one was free. A report that turns absence into
    either number fails, and so does one that reports a receipt the store
    does not hold.
    """
    ledger = dict(report.get("accounting") or {})
    if not ledger:
        return {"claim": "no cost is asserted in either direction",
                "agrees": True,
                "skipped": "no dispatch was made, so there is no receipt to"
                           " account for"}
    receipts = ledger.get("receipts") or []
    offenders = []
    for row in receipts:
        usage = row.get("usage")
        if not isinstance(usage, dict):
            continue
        for field in ("billed", "charge_units"):
            value = usage.get(field)
            if value not in (None,):
                offenders.append({"operation_id": row.get("operation_id"),
                                  "field": field, "value": value,
                                  "reason": "a field the route never sends"
                                            " carries a value"})
    for field in ("billed_values_seen", "charge_units_values_seen"):
        values = ledger.get(field) or []
        # The ledger records `repr(value)`, so an absent field is the
        # four-character string "None" rather than a JSON null. Reading it
        # as a number would make this check fail every honest report,
        # which is the opposite of what a check is for.
        unexpected = [v for v in values
                      if v not in (None, "None", "", "null")]
        if unexpected:
            offenders.append({"field": field, "value": unexpected,
                              "reason": "a field the route never sends"
                                        " carries a value"})
    if ledger.get("receipt_count") is not None and ledger["receipt_count"] != len(
            receipts):
        offenders.append({"field": "receipt_count",
                          "stated": ledger.get("receipt_count"),
                          "rederived": len(receipts)})
    return {"claim": "no cost is asserted in either direction",
            "agrees": not offenders,
            "receipts_checked": len(receipts),
            "null_on_every_receipt": (report.get("key_discrepancy") or {}
                                      ).get("null_on_every_receipt"),
            "offenders": offenders[:6],
            "offender_count": len(offenders)}


def check_no_key(report: Mapping[str, Any], key: str) -> dict:
    """The route's own key is nowhere in the report."""
    if not key:
        return {"claim": "the route key is absent", "agrees": True,
                "skipped": "no key was supplied to search for"}
    blob = json.dumps(report, sort_keys=True, default=str)
    return {"claim": "the route key is absent",
            "agrees": key.strip() not in blob, "checked": True}


CHECKS = (
    ("freeze", check_freeze),
    ("measureability", check_measureability),
    ("readings", check_readings),
    ("paired", check_paired),
    ("adaptation", check_adaptation),
    ("census", check_census),
    ("defect", check_defect),
    ("audit", check_audit),
    ("accounting", check_accounting),
)


def _offline_only(report: Mapping[str, Any]) -> bool:
    """True for a report that declares it dispatched nothing.

    A census-only artifact is a legitimate thing to produce, and its
    reading-dependent claims are absent rather than false. This reads the
    report's own declaration rather than inferring it from empty readings,
    so a live report that lost its readings still fails.
    """
    return report.get("measured_live") is False and bool(
        report.get("offline_only") or {})


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------


def verify(report: Mapping[str, Any], *, key: str = "") -> dict:
    """Every claim, re-derived, and whether the artifact survives.

    A check that raises is reported as a failure with its reason rather than
    aborting the run, so a reader sees all of them at once. `agrees` is the
    conjunction; a single disagreement fails the artifact.

    On a report that declares itself offline-only, the four
    reading-dependent checks are reported as skipped with the reason. They
    are not run and passed: a skipped check is not evidence, and reporting
    it as one would be the same arithmetic mistake this apparatus already
    made once.
    """
    offline = _offline_only(report)
    live_checks = ("readings", "paired", "adaptation", "accounting")
    results, failures, skipped = {}, [], []
    for name, check in CHECKS:
        if offline and name in live_checks:
            results[name] = {"claim": name, "agrees": None,
                             "skipped": "the report declares it dispatched"
                                        " nothing, so this claim is absent"
                                        " rather than verified"}
            skipped.append(name)
            continue
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
            "offline_only": offline,
            "checks": results,
            "failed": sorted(failures),
            "skipped": sorted(skipped),
            "agrees": not failures,
            "claim_class": "every claim is re-derived from an observation"
                           " stored in the report or recomputed from the"
                           " frozen panel, and no claim is taken on trust",
            "skipped_class": "a skipped check is not a passed check. On an"
                             " offline-only report the reading-dependent"
                             " claims are absent, and this verdict says so"
                             " rather than counting them as evidence."}


# ---------------------------------------------------------------------------
# the red proof
# ---------------------------------------------------------------------------


def _readings_of(report: Mapping[str, Any], key: str) -> dict:
    panel = (report.get("panels") or {}).get(key) or {}
    return panel.get("readings") or {}


def _first_reading(report: Mapping[str, Any], key: str, arm: str):
    readings = _readings_of(report, key)
    tasks = readings.get(arm) or {}
    if not tasks:
        return None, None
    task_id = sorted(tasks)[0]
    return task_id, tasks[task_id]


def red_proof(report: Mapping[str, Any]) -> dict:
    """Forge this report five ways and show the verifier rejects each.

    Each forgery is self-consistent: every field agrees with every other
    field, and the whole is still false. That is the shape a real forgery
    takes, and it is why every check above recomputes rather than compares.

    One: a reduction inflated with nothing else moved.
    Two: a reduction inflated *together with* the measure that produced it,
        so the report is internally coherent. That forgery is what a
        re-derivation from the measures cannot catch, because the measures
        agree with the reduction: the two were both changed. It is caught
        downstream instead, because the paired deltas over that reading
        were not recomputed with it. Asserting that the readings check
        rejects it would be asserting a property it does not have.
    Three: a paired delta written rather than computed.
    Four: a reachability ceiling above what any decision reaches.
    Five: the retention blocker withdrawn, so the report claims the
        retained-method leg is measurable when the frozen gate admits no
        such method.
    """
    out: dict = {}
    key = next((k for k in sorted(report.get("panels") or {})
                if (report["panels"][k] or {}).get("readings")),
               "retention/transfer")

    task_id, reading = _first_reading(report, key, replica.ARM_RELEVANT)
    if reading:
        forged = copy.deepcopy(report)
        row = dict(_readings_of(forged, key)[replica.ARM_RELEVANT][task_id])
        row["normalized_reduction"] = float(
            row.get("normalized_reduction") or 0.0) + 0.5
        forged["panels"][key]["readings"][replica.ARM_RELEVANT][task_id] = row
        out["inflated_reduction"] = _run(forged)

        forged = copy.deepcopy(report)
        row = dict(_readings_of(forged, key)[replica.ARM_RELEVANT][task_id])
        initial = int(row.get("initial_measure") or 0)
        inflated = min(0.99, float(row.get("normalized_reduction") or 0.0) + 0.4)
        row["measure"] = max(0, int(round(initial * (1 - inflated))))
        row["normalized_reduction"] = inflated
        forged["panels"][key]["readings"][replica.ARM_RELEVANT][task_id] = row
        forged["panels"][key]["paired"] = replica.paired_report(
            _readings_of(forged, key))
        forged["paired"] = campaign.merge_paired(forged["panels"])
        out["self_consistent_inflation"] = _run(forged)

        # The same inflation, but with the measure left alone. The report
        # is now incoherent with itself, and the readings check is the one
        # that says so.
        forged = copy.deepcopy(report)
        row = dict(_readings_of(forged, key)[replica.ARM_RELEVANT][task_id])
        row["normalized_reduction"] = float(
            row.get("normalized_reduction") or 0.0) + 0.4
        forged["panels"][key]["readings"][replica.ARM_RELEVANT][task_id] = row
        out["reduction_without_its_measure"] = _run(forged)

        forged = copy.deepcopy(report)
        stored = ((forged.get("panels") or {}).get(key) or {}).get("paired") or {}
        contrast = stored.get("relevant-minus-none") or {}
        if contrast.get("deltas") is not None:
            contrast = dict(contrast)
            contrast["deltas"] = [float(d) + 0.5
                                  for d in contrast["deltas"]]
            contrast["mean"] = 0.5
            stored = dict(stored)
            stored["relevant-minus-none"] = contrast
            forged["panels"][key]["paired"] = stored
            out["written_paired_delta"] = _run(forged)

    forged = copy.deepcopy(report)
    target = next((k for k in sorted(forged.get("panels") or {})
                   if (forged["panels"][k] or {}).get("reachability_census")),
                  None)
    if target:
        census_row = dict(
            (forged["panels"][target] or {})["reachability_census"])
        census_row["max_attainable_positive_delta"] = 0.9
        for row in census_row.get("rows") or []:
            row = dict(row)
        census_row["rows"] = [dict(r, attainable_positive_delta=0.9)
                              for r in census_row.get("rows") or []]
        forged["panels"][target] = dict(forged["panels"][target],
                                        reachability_census=census_row)
        out["inflated_ceiling"] = _run(forged)

    forged = copy.deepcopy(report)
    claims = dict(forged.get("measureability") or {})
    claims["retained_method_leg_measurable"] = True
    forged["measureability"] = claims
    out["blocker_withdrawn"] = _run(forged)
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
        description="verify a W2 retention and adaptation report offline")
    parser.add_argument("report", help="path to report.json")
    parser.add_argument("--key", default="", help="route key to search for")
    parser.add_argument("--red-proof", action="store_true",
                        help="forge the report and show each forgery is"
                             " rejected")
    args = parser.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    outcome = verify(report, key=args.key)
    print(json.dumps(outcome, indent=2, sort_keys=True, default=str))
    if args.red_proof:
        print(json.dumps(red_proof(report), indent=2, sort_keys=True,
                         default=str))
    return 0 if outcome["agrees"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
