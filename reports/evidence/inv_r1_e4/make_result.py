"""E4's result artifact, and the rule that decides what it is allowed to say.

    .venv/bin/python reports/evidence/inv_r1_e4/make_result.py

The previous file in this directory, `make_evidence.py`, measured headroom
and never produced a result. This one reads a campaign that actually ran and
writes the verdict beside the numbers it came from.

The rule that matters is the last function here. A result artifact that
claims a model did something no model did is worse than no artifact, so the
claim is not written from the campaign's own summary: it is re-derived here
from the dispatches, and an artifact whose live claim does not survive that
check is not written at all. The acquittal is recorded as a cell that could
not run, beside the cells that did, rather than as an absence.

Three verdicts are kept apart, because each answers a different question and
one of them can be true while another is false:

  qualification   did the machinery tell a real change from no change?
  acquisition     did a live model return an eligible revision?
  benefit         did that revision improve the descendants?

This run qualifies the apparatus and fails to acquire. Those are compatible
and the artifact says so in those words.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as run

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE / "run" / "campaign.json"
RESULT = HERE / "result.json"

ACQUIRED = run.ACQUIRED
QUALIFIED = channel.QUALIFIED
UNQUALIFIED = channel.UNQUALIFIED
NO_ELIGIBLE = run.INELIGIBLE_REPORTED
BENEFIT = "benefit"
NO_BENEFIT = "no-benefit"


class ResultRefused(Exception):
    """The campaign does not support the artifact about to be written."""


def live_claim(evidence: dict) -> dict:
    """Re-derive the live-acquisition claim from the dispatches alone.

    Not a re-reading of the campaign's own verdict. A verdict is a claim
    about the dispatches, and a claim about a claim is what let a previous
    round record `recorded-double` and pass its verifier. So this walks the
    dispatches and asks three questions of each one directly: did a route
    answer it, did a model name itself on it, and do the bytes it returned
    carry a digest? A dispatch with any of the three missing is not
    evidence that a model was reached, whatever the campaign said.
    """
    dispatches = evidence.get("dispatches") or []
    attributed = []
    for dispatch in dispatches:
        route = dispatch.get("route") or {}
        complete = all(
            isinstance(route.get(field), str) and route[field]
            for field in ("endpoint", "resolved_model", "provider", "tier"))
        attributed.append({
            "operation_id": dispatch.get("operation_id"),
            "reached_a_route": complete,
            "model": dispatch.get("model"),
            "acquisition": dispatch.get("acquisition"),
            "eligible": bool(dispatch.get("eligible")),
            "eligibility": dispatch.get("eligibility"),
            "response_digest": dispatch.get("source_digest"),
            "output_tokens": (dispatch.get("usage") or {}).get(
                "output_tokens"),
        })
    eligible = [entry for entry in attributed
                if entry["acquisition"] == ACQUIRED
                and entry["eligible"] and entry["reached_a_route"]
                and entry["response_digest"]
                and isinstance(entry["model"], str) and entry["model"]]
    claimed = [entry for entry in attributed if entry["eligible"]]
    unverifiable = [entry for entry in claimed if entry not in eligible]
    return {
        "dispatches": len(dispatches),
        "reached_a_route": sum(1 for entry in attributed
                                if entry["reached_a_route"]),
        "returned_executable_bytes": sum(
            1 for entry in attributed
            if entry["acquisition"] == ACQUIRED),
        "eligible": len(eligible),
        "claimed_eligible_but_unattributable": len(unverifiable),
        "claim": ("live-acquired" if eligible
                  else run.INELIGIBLE_REPORTED),
        "per_dispatch": attributed,
    }


def cells(evidence: dict) -> list:
    """The four cells the handoff names, each with what actually happened.

    Reported as a list rather than as prose so a reader can see which cell
    is missing without reading a sentence to find out. The unrun cell says
    why in its own field rather than in a footnote to a cell that ran.
    """
    acquisition = evidence.get("acquisition") or {}
    claim = evidence.get("live_claim") or {}
    arms = evidence.get("arms") or {}
    acquired = arms.get("acquired") or {}
    qualification = evidence.get("qualification") or {}
    return [
        {
            "cell": "live-acquisition",
            "ran": claim.get("eligible", 0) > 0,
            "result": ("%d of %d dispatches returned executable STEP bytes;"
                       " %d were admitted as an eligible revision"
                       % (claim.get("returned_executable_bytes", 0),
                          claim.get("dispatches", 0), claim.get("eligible", 0))),
            "detail": ("every admitted reply named input 0, which is the"
                       " frozen reducer's own top-ranked input, so each was"
                       " refused as delegating to an unchanged fixed reducer"
                       if claim.get("eligible", 0) == 0 else None),
        },
        {
            "cell": "reviewer-authored-revision",
            "ran": bool((arms.get("known-effect") or {}).get("candidate_id")),
            "result": _arm_result(arms.get("known-effect")),
            "detail": "no model call; the reviewer wrote the bytes",
        },
        {
            "cell": "no-op-control",
            "ran": bool((arms.get("no-op") or {}).get("candidate_id")),
            "result": _arm_result(arms.get("no-op")),
            "detail": "no model call; selects the incumbent's own input",
        },
        {
            "cell": "disconnect-counterexample",
            "ran": bool((arms.get("disconnect") or {}).get(
                "refused_by_instrument")),
            "result": _arm_result(arms.get("disconnect")),
            "detail": ("no model call; the input is outside the instrument's"
                       " range and the round's own action validator refused"
                       " it, so no descendant was built"),
        },
    ]


def _arm_result(arm) -> str:
    if not arm:
        return "no arm was run"
    paired = arm.get("paired") or {}
    if not paired.get("measured"):
        return ("x=%s, no descendant was built, so nothing was measured"
                % arm.get("x_probed"))
    return ("x=%s against the incumbent's %s: delta %+.5f (se %.5f) over %d"
            " unseen tasks"
            % (paired.get("x_revised"), paired.get("x_incumbent"),
               paired["delta"], paired["paired_se"] or 0.0,
               paired.get("n_seeds", 0)))


def verdict(evidence: dict) -> dict:
    """The three verdicts, derived, with no cell able to supply another."""
    claim = evidence.get("live_claim") or {}
    qualification = evidence.get("qualification") or {}
    acquired = (evidence.get("arms") or {}).get("acquired") or {}
    paired = acquired.get("paired") or {}
    changed = acquired.get("changed") or {}
    if not qualification.get("qualified"):
        benefit, why = None, ("the apparatus is unqualified, so no run"
                              " outcome would mean anything")
    elif claim.get("eligible", 0) < 1:
        benefit, why = False, ("no eligible revision was acquired, so there"
                               " is no arm whose descendants could differ"
                               " from the incumbent's")
    elif not changed.get("changed_decision"):
        benefit, why = False, ("an eligible revision was acquired but it"
                               " selected the input the incumbent selects,"
                               " so it changed no decision")
    elif not paired.get("measured") or (paired.get("delta") or 0.0) <= 0.0:
        benefit, why = False, ("the revision changed the decision and the"
                               " descendants did not improve under the"
                               " frozen rule")
    else:
        benefit, why = True, ("a live-acquired, eligible revision changed"
                              " the decision and improved the descendants"
                              " under the frozen rule")
    return {
        "qualification": qualification.get("qualification"),
        "acquisition": claim.get("claim"),
        "benefit": benefit,
        "benefit_basis": why,
        "scope": ("one successful generation supports bounded meta-learning,"
                  " not unrestricted recursive self-improvement")
        if benefit else None,
    }


def build(evidence: dict) -> dict:
    claim = live_claim(evidence)
    if claim["claimed_eligible_but_unattributable"]:
        raise ResultRefused(
            "the campaign claims %d eligible dispatch(es) that carry no route,"
            " no model and no response digest, so the live acquisition cannot"
            " be written: the claim is not re-derivable from the dispatches"
            % claim["claimed_eligible_but_unattributable"])
    if claim["returned_executable_bytes"] and not claim["reached_a_route"]:
        raise ResultRefused(
            "a dispatch returned bytes without a route behind it, so the"
            " campaign cannot be written as a live acquisition")
    enriched = {**evidence, "live_claim": claim}
    verdicts = verdict(enriched)
    return {
        "experiment": "E4 one bounded executable learner revision",
        "run_version": run.RUN_VERSION,
        "channel_version": channel.CHANNEL_VERSION,
        "decision_under_study": channel.DECISION,
        "intervention_boundary": {
            "file": "experiments/ad01/improve_channel.py",
            "line": 172,
            "symbol": "DECISION",
            "bytes": run.REVISION_INTERFACE,
            "incumbent_line": "experiments/ad01/improve_channel.py:80",
        },
        "frozen": evidence.get("frozen"),
        "evaluator": channel.EVALUATOR_ID,
        "reproduce": {
            "campaign": "reports/evidence/inv_r1_e4/run/campaign.json",
            "builder": "reports/evidence/inv_r1_e4/make_result.py",
            "module": "experiments/ad01/learner_revision.py",
            "database": "none; the run is file-backed and offline",
            "note": ("the campaign spent live model calls and is not"
                     " repeatable without spending them again; this file is"
                     " derived from the campaign beside it and holds no"
                     " dispatch of its own"),
        },
        "prompt": evidence.get("prompt"),
        "route": evidence.get("route"),
        "model": evidence.get("model"),
        "cap_sheet": evidence.get("cap_sheet"),
        "authority_deviation": evidence.get("authority_deviation"),
        "cells": cells(enriched),
        "live_claim": claim,
        "acquisition": evidence.get("acquisition"),
        "acquisition_summary": evidence.get("acquisition_summary"),
        "incumbent": evidence.get("incumbent"),
        "cohort": {"split": evidence.get("split"),
                   "seeds": evidence.get("cohort"),
                   "n_seeds": evidence.get("n_seeds")},
        "arms": evidence.get("arms"),
        "ceiling": evidence.get("ceiling"),
        "evidence_ceiling": evidence.get("evidence_ceiling"),
        "qualification": evidence.get("qualification"),
        "verdicts": verdicts,
        "statement": _statement(verdicts, enriched),
    }


def _statement(verdicts: dict, evidence: dict) -> str:
    ceiling = evidence.get("ceiling") or {}
    wide = evidence.get("evidence_ceiling") or {}
    if verdicts["benefit"] is False and verdicts["acquisition"] == NO_ELIGIBLE:
        return (
            "The apparatus is qualified and no eligible revision was "
            "acquired, and those are separate findings. All three controls "
            "behaved as declared, so the machinery can tell a change from no "
            "change. Every live reply returned executable STEP bytes and was "
            "refused for naming the frozen reducer's own top-ranked input, so "
            "there is no acquired arm whose descendants could differ from the "
            "incumbent's and no benefit question was reached.\n\n"
            "The null is bounded on both sides. Within this decision the "
            "reachable range is %.5f, measured as a paired difference over "
            "%d unseen tasks, so even a perfect revision of this boundary "
            "would move a descendant by about that much. The wider evidence "
            "decision the frozen reducer actually makes is a different "
            "matter: the same evaluator puts it at %.4f against the "
            "incumbent's %.4f. The learner has large headroom, and this "
            "boundary cannot express it, because a descendant runs the "
            "authored menu's single input rather than the revision's choice. "
            "The blocker is the boundary, not the substrate and not the "
            "prompt."
            % (ceiling.get("delta") or 0.0, ceiling.get("n_seeds") or 0,
               wide.get("reducer_mean") or 0.0,
               wide.get("incumbent_mean") or 0.0))
    return "See the verdicts block; this statement is only written for the "\
           "acquisition-negative case and the case did not occur."


def main() -> int:
    if not CAMPAIGN.exists():
        sys.stderr.write("no campaign at %s; run the campaign first\n"
                         % (CAMPAIGN,))
        return 2
    evidence = json.loads(CAMPAIGN.read_text())
    result = build(evidence)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True,
                                 default=str) + "\n")
    sys.stdout.write(json.dumps(result["verdicts"], indent=2,
                                sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
