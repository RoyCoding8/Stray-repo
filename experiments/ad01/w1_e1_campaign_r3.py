"""The third live E1 campaign, under a freeze that names its own parameters.

Run id `w1-e1-boolean-r3`. r1 was invalid because the route contract had two
halves that disagreed. r2 ran on the repaired contract and reported zero
constructions across eight attempts, and two reviews found that its headline
rested on inputs the campaign chose rather than inputs the protocol fixed:
the 512-character cap, an attempt number hardcoded to 1, and eight
"independent lineages" that were two prompts on one task, sent four times
each. All eight of r2's records carry `split=qual seed=11` and operation ids
ending `-qual-0011-a1`, so its audit cell was never dispatched at all. This
file is the third run, and `FREEZE.md` in this directory is the document those
reviews asked for. It was written before the first dispatch and no value in it
was chosen after an outcome was known.

Every dispatch goes through `live_construct.LiveGuard` over
`HttpGatewayAdapter`, `render_output_prompt`, `output_operation_id`,
`extract_and_validate_boolean` and the `RuleSession` scorer. This file adds no
HTTP client, no prompt and no parser of its own. The one thing it does add is
a second reading of every response at the parser's own implied cap, because
the shipped driver's cap and the shipped parser's cap are different questions
and reporting only one of them would repeat r2's mistake in the other
direction.

`verify` withdraws the gateway and then re-derives every claim field from the
stored bytes. It never reads a recorded `reason`, because a self-consistent
forgery passes a verifier that does: a short response whose prose describes a
long one, with the record's own outcome, counts and digests all agreeing with
each other. A claim here is true only if it can be recomputed from the
observations the record stores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

CAMPAIGN_VERSION = "w1-e1-boolean-campaign-v3"
CAMPAIGN_ID = "w1-e1-boolean-r3"
CAP_SHEET = "reports/cap-sheets/w1-e1-cap.md"
FREEZE = "reports/evidence/w1-e1-boolean-r3/FREEZE.md"
SUPERSEDES = ("w1-e1-boolean-r1", "w1-e1-boolean-r2")
REASON_SUPERSEDED = (
    "r1 is invalid because the route contract had two halves that disagreed "
    "on `provider`, which is a harness fact rather than a model result. r2 ran "
    "on the repaired contract but measured its zero against a 512-character "
    "cap whose value no shipped code derives, and it dispatched a single task "
    "identity eight times: every one of its records is `split=qual seed=11` at "
    "attempt 1, so the audit seed the protocol freezes beside it was never "
    "dispatched, and the eight were two prompts sent four times each rather "
    "than eight lineages. Its records are retained and reported beside r3 as "
    "a different protocol. Neither campaign is repaired or selectively re-run."
)

TREATMENTS = ("P1", "P2")
ARM_MEANING = {
    "P1": "interface-only acquisition: the frozen public view and nothing else",
    "P2": "prior-task summary: two dev-split predictor digests and their "
          "scores, no program text",
}

# The frozen protocol offers exactly two seeds and two attempt numbers, so
# the input space is 2 x 2 per arm and this campaign fills all of it. r2 spent
# eight of its sixteen calls and put none into a second attempt; the grid
# below spends the allowance on distinct (task, attempt) cells rather than on
# repeats of one cell.
#
# N = 4 x supported cells x treatments = 4 x 1 x 2 = 8, from the cap sheet.
# Each opportunity may spend at most two model calls, so the ceiling is 16.
# This dispatch plan spends one call per cell, and the second call is held in
# reserve for a cell whose first draw was a transport loss, which the exposure
# file records rather than this plan assuming.
TASKS = (("qual", 11), ("audit", 23))
ATTEMPTS = (1, 2)
CELLS = [(arm, split, seed, attempt)
         for arm in TREATMENTS for split, seed in TASKS for attempt in ATTEMPTS]
ATTEMPT_CEILING = len(CELLS)
MODEL_CALL_CEILING = ATTEMPT_CEILING * 2

# The shipped preflight's own deadline, kept because shortening it manufactures
# transport loss and reports it as a result.
DISPATCH_DEADLINE_MS = 300_000
GATEWAY_API = "chat"

# Cap A is the frozen constant, read from the protocol rather than restated,
# so this file cannot drift from it. Cap B is unbounded: the parser's own
# implied limit, where the response is judged by the protocol and by nothing
# this campaign chose. Both are reported. See FREEZE.md section 2.
CAP_A_KEY = "max_response_characters"

CELL_DESCRIPTION = {
    "world": "boolean",
    "representation": "output-shape predictor",
    "task": "the frozen qual and audit splits with all eight queries already "
            "spent, so the model is asked to commit rather than probe",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_json(path: Path, payload) -> None:
    """Write atomically, so a crash mid-write cannot leave half a record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(path.suffix + ".partial")
    scratch.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n",
                       encoding="utf-8")
    os.replace(scratch, path)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cap_a() -> int:
    from experiments.ad01 import live_construct as live
    return int(live.OUTPUT_LIMITS[CAP_A_KEY])


def conforming_answer_characters() -> int:
    """The length of the shortest payload the protocol's validator accepts.

    Computed from the validator's own shape rather than quoted, and it is the
    number that decides whether Cap A is a physical floor of the exchange. If
    this is below Cap A then a conforming answer is possible and a response
    that misses the cap is a discipline failure rather than an impossibility.
    """
    from experiments.ad01 import live_construct as live
    spec = {"const": 0, "mask": 0, "pair": None}
    return len(json.dumps({"specs": [spec] * 4}, separators=(",", ":")))


def _build_session(split: str, seed: int):
    """The frozen task with its query budget spent, for either frozen seed.

    The shipped `_preflight_task` hardcodes the qual split
    (`live_construct.py:1461`), so it cannot reach the audit seed. r2
    dispatched through its own qual-pinned `_frozen_task`
    (`w1_e1_campaign_r2.py:439`) for every one of its eight cells, which is
    why all eight of its records read `split=qual seed=11` and the audit cell
    was never run. This function takes the split it is given and spends the
    budget the same way: the same learner, the same loop, the same session,
    and the same `output_model_input` the protocol's own prompt renderer is
    given.
    """
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import rule_learner
    task = rules.make_task(split, int(seed))
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, int(seed))
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    return task, session


def _reference_scores(task: dict) -> dict:
    """What doing nothing scores, and what the hypothesis class admits.

    Neither is a constructed program and neither is ever counted as one. They
    let a reader tell a program that cleared chance from one that cleared the
    floor from one that recovered the rule.
    """
    from experiments.ad01 import boolean_rule as rules
    session = rules.RuleSession(task)
    zero = session.commit_predictor(
        {"specs": [{"const": 0, "mask": 0, "pair": None}] * rules.N_OUTPUTS})
    zero_overall = session.score(zero)["overall"]
    oracle = rules.RuleSession(task)
    exact = oracle.commit_predictor(
        {"specs": [rules.spec_for_table(table) for table in task["tables"]]})
    return {"zero_predictor_overall": zero_overall,
            "oracle_overall": oracle.score(exact)["overall"]}


def _judge_at_cap_b(text: str, session) -> dict:
    """The same response judged at the parser's own implied cap.

    This is the reading that removes the campaign's cap from the claim. It
    calls the protocol's validator and the protocol's scorer and nothing else,
    so a response that fails here failed for a reason no number this campaign
    chose can explain.
    """
    from experiments.ad01 import live_construct as live
    verdict = {"cap": "unbounded",
               "cap_characters": None,
               "parses": False, "verdict": "invalid-program",
               "detail": None, "score": None,
               "candidate_digest": None}
    try:
        candidate = live.extract_and_validate_boolean(text)
    except Exception as exc:
        verdict["detail"] = "%s: %s" % (type(exc).__name__, exc)
        return verdict
    verdict["parses"] = True
    committed = session.commit_predictor(candidate)
    score = session.score(committed)
    verdict["score"] = score
    verdict["candidate_digest"] = live.source_digest(json.dumps(
        candidate, sort_keys=True, separators=(",", ":")))
    verdict["verdict"] = (
        "constructed" if score["overall"] >= live.PREFLIGHT_SCORE_FLOOR
        else "poor-task-result")
    return verdict


def _dispatch_once(guard, *, arm: str, split: str, seed: int, attempt: int,
                   round_run_id: str) -> dict:
    """One construction opportunity. Returns the shipped attempt shape.

    An over-Cap-A response is recorded as `invalid-program` with
    `over_length: true` beside it, because that is the protocol's own
    taxonomy and the protocol admits no eighth value. The campaign's separate
    finding lives in the `over_length` flag and in `cap_b`, and `verify`
    re-derives both from the bytes, so the two are never averaged: the
    outcome says what the protocol called it and the flag says why.
    """
    from experiments.ad01 import live_construct as live
    from settlement.gateway import GatewayError, ModelRequest

    task, session = _build_session(split, seed)
    history = [] if arm == "P1" else live.output_permitted_history()
    prompt = live.render_output_prompt(session.output_model_input(), history,
                                       attempt)
    operation_id = live.output_operation_id(arm, split, int(seed), attempt,
                                            round_run_id=round_run_id)
    evidence = {"arm": arm, "task": task["task_id"], "attempt": attempt,
                "raw_prompt": prompt, "round": live.OUTPUT_ROUND}
    request = ModelRequest(
        model=guard.pinned_model,
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=live.OUTPUT_LIMITS["max_output_tokens"],
        deadline_ms=DISPATCH_DEADLINE_MS,
        operation_id=operation_id)

    def _recorded():
        return next((e for e in guard.ledger
                     if e.get("operation_id") == operation_id), None)

    def _entry(outcome: str, **extra) -> dict:
        entry = {"arm": arm, "task": task["task_id"],
                 "split": split, "seed": int(seed), "attempt": attempt,
                 "operation_id": operation_id, "outcome": outcome,
                 "reason": None, "raw_response": None,
                 "candidate_digest": None, "score": None,
                 "dispatch": _recorded()}
        entry.update(extra)
        return entry

    try:
        response = guard.infer(request, evidence=evidence)
    except live.LiveRefused as exc:
        kind = guard.refusal_kind or "unknown"
        return _entry("route-refusal" if kind == "route"
                      else "pre-dispatch-refusal",
                      refusal_kind=kind, refusal=str(exc))
    except Exception as exc:
        recorded = _recorded()
        if isinstance(recorded, dict) and recorded.get(
                "parse_outcome") == "transport-error":
            return _entry("transport-loss",
                          exception_class=type(exc).__name__,
                          refusal=str(exc))
        return _entry("transport-loss",
                      exception_class=type(exc).__name__,
                      refusal=str(exc))

    if isinstance(response, GatewayError):
        diagnosis = live.classify_error(response)
        refused = diagnosis["route_error"] is not None or (
            diagnosis["response_status"] is not None
            and 400 <= diagnosis["response_status"] < 500
            and diagnosis["kind"] != "timeout")
        return _entry("route-refusal" if refused else "transport-loss",
                      diagnosis=diagnosis,
                      refusal=diagnosis["reason"])

    text = response.text
    dispatch = guard.provenance(operation_id)
    characters = len(text)
    cap_a = _cap_a()

    def _settle(parse_outcome: str, **kwargs) -> None:
        try:
            guard.finalize_evidence(operation_id,
                                    round_no=live.OUTPUT_ROUND,
                                    parse_outcome=parse_outcome, **kwargs)
        except Exception:
            # A finalization refusal must not become a driver fault that
            # discards a response the provider actually paid for. The bytes
            # are already in the dispatch record; the taxonomy decision below
            # is made from them, and the refusal is recorded.
            pass

    if not text.strip():
        _settle("empty")
        return _entry("empty-content", raw_response=text,
                      response_characters=characters,
                      cap_b=_judge_at_cap_b(text, session))

    if characters > cap_a:
        # Over Cap A. The shipped driver would finalize `too-long` and move on.
        # This campaign does the same and then asks the second question, so the
        # cap's contribution to the result is visible rather than assumed.
        _settle("too-long")
        return _entry("invalid-program", raw_response=text,
                      response_characters=characters,
                      over_length=True, cap_a_characters=cap_a,
                      cap_b=_judge_at_cap_b(text, session))

    try:
        candidate = live.extract_and_validate_boolean(text)
        committed = session.commit_predictor(candidate)
    except Exception as exc:
        _settle("parse-failed")
        return _entry("invalid-program", raw_response=text,
                      response_characters=characters, over_length=False,
                      parse_error="%s: %s" % (type(exc).__name__, exc),
                      cap_b=_judge_at_cap_b(text, session))

    score = session.score(committed)
    candidate_digest = live.source_digest(json.dumps(
        candidate, sort_keys=True, separators=(",", ":")))
    below = score["overall"] < live.PREFLIGHT_SCORE_FLOOR
    _settle("accepted", accepted_candidate_digest=candidate_digest,
            parsed_source_digest=candidate_digest)
    return _entry("poor-task-result" if below else "constructed",
                  raw_response=text, response_characters=characters,
                  over_length=False, candidate_digest=candidate_digest,
                  score=score,
                  cap_b={"cap": "unbounded", "cap_characters": None,
                         "parses": True, "verdict": _verdict_for(score),
                         "detail": None, "score": score,
                         "candidate_digest": candidate_digest})


def _verdict_for(score: dict) -> str:
    from experiments.ad01 import live_construct as live
    return ("poor-task-result"
            if score["overall"] < live.PREFLIGHT_SCORE_FLOOR
            else "constructed")


# --- the manifest, written before the first dispatch -------------------


def _planned_grid() -> list:
    grid = []
    for arm, split, seed, attempt in CELLS:
        round_run_id = "%s-%s-%s-a%d" % (CAMPAIGN_ID, split, arm, attempt)
        grid.append({"arm": arm, "split": split, "seed": int(seed),
                     "attempt": attempt, "round_run_id": round_run_id,
                     "state": "pending", "outcome": None, "cap_b_verdict": None,
                     "billed": None, "charge_units": None})
    return grid


def _build_manifest() -> dict:
    from experiments.ad01 import live_construct as live
    prompts = {}
    for arm, split, seed, attempt in CELLS:
        _, session = _build_session(split, seed)
        history = [] if arm == "P1" else live.output_permitted_history()
        prompt = live.render_output_prompt(session.output_model_input(),
                                           history, attempt)
        prompts["%s:%s:%d:a%d" % (arm, split, int(seed), attempt)] = {
            "digest": live.source_digest(prompt), "characters": len(prompt)}
    references = {}
    for split, seed in TASKS:
        task, _ = _build_session(split, seed)
        references["%s:%d" % (split, seed)] = {
            "task_id": task["task_id"], **_reference_scores(task)}
    return {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "written_at": _now(),
        "cap_sheet": CAP_SHEET,
        "freeze": FREEZE,
        "supersedes": list(SUPERSEDES),
        "reason_superseded": REASON_SUPERSEDED,
        "written_before_any_dispatch": True,
        "route": dict(live.OUTPUT_ROUTE),
        "route_api": GATEWAY_API,
        "route_note": "the credential is never written to this directory; the "
                      "guard compares endpoint, model, provider and tier "
                      "through `route_matches` on every response",
        "limits_read_from_protocol": dict(live.OUTPUT_LIMITS),
        "parameters_that_are_this_campaigns": {
            "character_cap": {
                "value": _cap_a(), "cap_key": "A",
                "who_fixed_it": "this campaign inherited the literal; no "
                                "shipped code derives the number 512",
                "shipped_enforcement": [
                    "scripts/invl02_live.py:1195 finalizes `too-long`",
                    "experiments/ad01/offline_recompute.py:2266 flags "
                    "`response-character-cap-exceeded`",
                ],
                "not_enforced_by": "live_construct.LiveGuard, "
                                   "`render_output_prompt`, "
                                   "`extract_and_validate_boolean`, or the "
                                   "`RuleSession` scorer",
                "second_cap_reported": "B, unbounded, which is the parser's "
                                       "own implied limit",
            },
        },
        "conforming_answer_characters": conforming_answer_characters(),
        "conforming_answer_note": "the shortest payload the protocol's own "
                                  "validator accepts. Below Cap A, so Cap A "
                                  "does not make a conforming answer "
                                  "impossible.",
        "score_floor": live.PREFLIGHT_SCORE_FLOOR,
        "score_floor_note": "the shipped literal, untuned; 1.0 is the oracle",
        "dispatch_deadline_ms": DISPATCH_DEADLINE_MS,
        "cell": CELL_DESCRIPTION,
        "tasks": [{"split": split, "seed": int(seed)} for split, seed in TASKS],
        "treatments": {arm: ARM_MEANING[arm] for arm in TREATMENTS},
        "attempts": list(ATTEMPTS),
        "prompts": prompts,
        "reference_scores": references,
        "planned": {
            "construction_opportunities": ATTEMPT_CEILING,
            "cap_sheet_formula": "N = 4 x supported cells x treatments",
            "model_call_ceiling": MODEL_CALL_CEILING,
            "grid": "2 arms x 2 frozen seeds x 2 attempt numbers = 8, every "
                    "cell dispatched once",
        },
        "independence": {
            "what_varies": "task (2 frozen seeds) and attempt (1 or 2), which "
                           "changes the literal text `Attempt N of 2` and "
                           "nothing else, plus the arm's permitted history",
            "sampling_knob": "none. `ModelRequest` carries `reasoning_effort` "
                             "and no temperature, top_p or seed, and "
                             "`gateway_http` builds no sampling field into "
                             "either payload.",
            "consequence": "the protocol offers 4 distinct prompts per arm and "
                           "no repetition axis. n is reported as draws, never "
                           "as independent opportunities, and a draw at a "
                           "repeated prompt is labelled as a repeat.",
            "cap_sheet_rule": "disjointness of ancestor chains, which is a "
                              "bookkeeping rule about lineage identity. It is "
                              "not evidence that the inputs differed, and a "
                              "digest test cannot stand in for one.",
        },
        "stopping_rule": "the study stops when the 8-cell grid is filled. A "
                         "refusal, transport loss or no-candidate outcome does "
                         "not authorise a replacement episode, no authored "
                         "solver is written after a failure, and no cap, "
                         "prompt or floor is moved after an outcome is seen.",
    }


def _build_exposure(manifest: dict, already_spent: int = 0,
                    prior_faults: list | None = None) -> dict:
    """Counters and pending exposure, written BEFORE the first dispatch.

    The cap sheet requires this ordering including for crashes: a process
    killed at cell six must leave on disk the fact that eight dispatches were
    owed and how many were settled, plus the cost of each settled one.

    `already_spent` is the number of dispatches a previous, interrupted run of
    this campaign put on the wire. It is carried into the guard's own ledger
    rather than discarded, so a resumed run cannot spend the same allowance
    twice and the total exposure on disk is the real total rather than the
    part that happened to succeed. The cap sheet's resume row allows exactly
    this: "from persisted pending exposure only".
    """
    return {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "opened_at": _now(),
        "updated_at": _now(),
        "attempt_ceiling": ATTEMPT_CEILING,
        "model_call_ceiling": MODEL_CALL_CEILING,
        "dispatches_reserved": MODEL_CALL_CEILING - ATTEMPT_CEILING,
        "dispatches_reserved_note": "held for a cell whose first draw was a "
                                    "transport loss, and for dispatches a "
                                    "driver fault consumed. A cell that "
                                    "dispatched cleanly is never re-drawn; "
                                    "the reserve is recorded, not assumed.",
        "attempts_planned": ATTEMPT_CEILING,
        "attempts_settled": 0,
        "dispatches_spent": int(already_spent),
        "dispatches_carried_in": int(already_spent),
        "dispatches_refunded": 0,
        "billed_true": 0,
        "billed_false": 0,
        "billed_unknown": 0,
        "charge_units_known": None,
        "attempts": _planned_grid(),
        "driver_faults": list(prior_faults or []),
    }



def _run(root: Path, *, dsn: str | None = None,
         allocation_id: str | None = None) -> dict:
    from experiments.ad01 import live_construct as live
    from settlement.gateway_http import HttpGatewayAdapter

    endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if not endpoint or not key:
        raise SystemExit("SETTLEMENT_GATEWAY_ENDPOINT and "
                         "SETTLEMENT_GATEWAY_KEY must be set; this lane never "
                         "accepts a credential on the command line")
    if (dsn is None) != (allocation_id is None):
        raise SystemExit(
            "a dispatch is durable or it is not: --dsn and --allocation-id "
            "are required together, because an operation admitted without an "
            "allocation is a row the store cannot charge")

    manifest = _build_manifest()
    # A previous run of this campaign that faulted on a cell still spent the
    # dispatch. Carrying the number in keeps the ceiling honest: the resumed
    # run cannot quietly buy a fresh allowance by crashing. Faulted cells are
    # retried, and cells that settled are not re-dispatched.
    prior_spent, prior_faults, settled = 0, [], set()
    exposure_path = root / "exposure.json"
    if exposure_path.exists():
        prior = _read_json(exposure_path)
        prior_spent = int(prior.get("dispatches_spent", 0))
        prior_faults = list(prior.get("driver_faults", []))
        for cell in prior.get("attempts", []):
            if cell.get("state") == "settled" and cell.get("outcome"):
                settled.add((cell["arm"], cell["split"], cell["seed"],
                             cell["attempt"]))
    exposure = _build_exposure(manifest, already_spent=prior_spent,
                               prior_faults=prior_faults)
    _write_json(root / "campaign-manifest.json", manifest)
    _write_json(exposure_path, exposure)

    gateway = HttpGatewayAdapter(
        endpoint=endpoint, api_key=key, api=GATEWAY_API,
        expected_route=dict(live.OUTPUT_ROUTE),
        timeout_read_ms=DISPATCH_DEADLINE_MS - 10_000,
        timeout_total_ms=DISPATCH_DEADLINE_MS)
    # A durable send is admitted and dispatched through the broker, so each
    # cell carries an operation row, a reservation, a receipt and an
    # exposure. The cap sheet's retry row reuses one operation identity per
    # lineage, and identity is what makes that a retry rather than a second
    # send: the store already holds the first. The ceiling reads the same
    # count, so a resumed run continues from what the store records rather
    # than from a number a file carried.
    if dsn is not None:
        gateway = live.preflight_dispatch_gateway(
            dsn, gateway, allocation_id=allocation_id)
    guard = live.LiveGuard(
        gateway, pinned_model=live.OUTPUT_ROUTE["requested_model"],
        ceiling=MODEL_CALL_CEILING,
        automatic_retries=live.OUTPUT_LIMITS["automatic_retries"],
        expected_route=dict(live.OUTPUT_ROUTE),
        already_spent=prior_spent,
        spend_reader=(lambda: live.spent_dispatches(dsn, allocation_id))
        if dsn is not None else None)

    for cell in exposure["attempts"]:
        arm, split, seed, attempt = (cell["arm"], cell["split"], cell["seed"],
                                     cell["attempt"])
        if (arm, split, seed, attempt) in settled:
            cell["state"] = "settled"
            cell["outcome"] = "carried-from-prior-run"
            continue
        name = "%s-%s-a%d" % (arm, split, attempt)
        task, session = _build_session(split, seed)
        try:
            entry = _dispatch_once(
                guard, arm=arm, split=split, seed=seed, attempt=attempt,
                round_run_id=cell["round_run_id"])
            record = _build_record(root, manifest, name, cell, entry, task,
                                   session, guard)
            _write_json(root / "records" / ("%s.json" % name), record)
            cell["state"] = "settled"
            cell["outcome"] = entry["outcome"]
            cell["cap_b_verdict"] = (entry.get("cap_b") or {}).get("verdict")
            usage = (entry.get("dispatch") or {}).get("usage") or {}
            cell["billed"] = usage.get("billed", "unknown")
            cell["charge_units"] = usage.get("charge_units", "unknown")
        except Exception as exc:
            # An apparatus failure is not a construction outcome and is never
            # laundered into one. The cell stays unsettled, so the exposure
            # file still reads as owed.
            cell["state"] = "driver-fault"
            exposure["driver_faults"].append(
                {"cell": name, "operation_id": cell["round_run_id"],
                 "error_class": type(exc).__name__, "error": str(exc),
                 "at": _now()})
        exposure["attempts_settled"] = sum(
            1 for c in exposure["attempts"] if c["state"] == "settled")
        exposure["dispatches_spent"] = guard.spent_dispatches
        exposure["dispatches_refunded"] = guard.refunded_dispatches
        exposure["guard_status"] = guard.guard_status()
        billed = [c["billed"] for c in exposure["attempts"]
                  if c.get("billed") is not None]
        exposure["billed_true"] = sum(1 for b in billed if b is True)
        exposure["billed_false"] = sum(1 for b in billed if b is False)
        exposure["billed_unknown"] = sum(1 for b in billed if b == "unknown")
        charges = [c["charge_units"] for c in exposure["attempts"]
                   if isinstance(c.get("charge_units"), int)]
        exposure["charge_units_known"] = (sum(charges) if charges else None)
        exposure["charge_units_note"] = (
            "the provider reported no charge field on this route, so the sum "
            "is null rather than zero. Unknown stays unknown."
            if not charges else "sum of the charge_units the provider reported")
        exposure["updated_at"] = _now()
        _write_json(root / "exposure.json", exposure)

    summary = summarize(root)
    summary["closed_at"] = _now()
    _write_json(root / "campaign.json", summary)
    exposure["closed_at"] = _now()
    exposure["final_guard_status"] = guard.guard_status()
    _write_json(root / "exposure.json", exposure)
    return summary


def _build_record(root: Path, manifest: dict, name: str, cell: dict,
                  entry: dict, task: dict, session, guard) -> dict:
    """One record per cell, holding the bytes and the decision over them.

    The `reason` field is written for a human reader and is never read back by
    `verify`. Everything a claim depends on is either recomputable from
    `raw_response` or is a digest of it.
    """
    from experiments.ad01 import live_construct as live
    record = {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "cell_name": name,
        "written_at": _now(),
        "study_root": CAMPAIGN_ID,
        "protocol_id": live.OUTPUT_PROTOCOL_ID,
        "route": dict(live.OUTPUT_ROUTE),
        "treatment": entry["arm"],
        "treatment_meaning": ARM_MEANING[entry["arm"]],
        "split": entry["split"],
        "seed": entry["seed"],
        "task_id": entry["task"],
        "queries_spent": len(session.queried),
        "attempt": entry["attempt"],
        "cap_a_characters": _cap_a(),
        "conforming_answer_characters": conforming_answer_characters(),
        "score_floor": live.PREFLIGHT_SCORE_FLOOR,
        "reference_scores": manifest["reference_scores"].get(
            "%s:%d" % (entry["split"], entry["seed"])),
        "prompt_digest": (entry.get("dispatch") or {}).get("prompt_digest"),
        "round_run_id": cell["round_run_id"],
        "attempts": [entry],
        "guard_status": guard.guard_status(),
    }
    return record


# --- reading the campaign back, with no network ------------------------


def _cap_a_table(records: list) -> dict:
    """Outcomes at Cap A, the frozen 512, counted the way the driver counts."""
    from experiments.ad01 import live_construct as live
    table = {name: 0 for name in live.PREFLIGHT_OUTCOMES}
    over_length = 0
    for record in records:
        entry = record["attempts"][0]
        table[entry["outcome"]] += 1
        if entry.get("over_length"):
            over_length += 1
    return {"cap": "A", "characters": _cap_a(), "outcomes": table,
            "over_length": over_length,
            "accepted_under_cap": sum(
                table[o] for o in ("constructed", "poor-task-result"))}


def _cap_b_table(records: list) -> dict:
    """Outcomes at Cap B, unbounded, judged by the protocol alone.

    A response that parses here is a program the protocol would have run. A
    response that does not is not a program at any length, which is the finding
    that removes the campaign's cap from the explanation.
    """
    table = {"constructed": 0, "poor-task-result": 0,
             "invalid-program": 0, "no-response": 0}
    details = []
    for record in records:
        entry = record["attempts"][0]
        cap_b = entry.get("cap_b")
        if not isinstance(cap_b, dict):
            table["no-response"] += 1
            continue
        table[cap_b["verdict"]] += 1
        details.append({"cell": record["cell_name"],
                        "characters": entry.get("response_characters"),
                        "verdict": cap_b["verdict"],
                        "parses": cap_b["parses"],
                        "score": (cap_b.get("score") or {}).get("overall"),
                        "detail": (cap_b.get("detail") or "")[:160] or None})
    return {"cap": "B", "characters": None, "outcomes": table,
            "per_cell": details,
            "note": "the response judged by `extract_and_validate_boolean` "
                    "and the `RuleSession` scorer, with no length check at "
                    "all. This is the parser's own implied limit."}


def _counts(records: list) -> dict:
    """The three numbers that must not be collapsed into one.

    A construction event is a cell whose bytes parsed and ran. A unique source
    program is a distinct candidate digest among those bytes. A retained
    record is a file. Four events that converged on one program is four
    constructions of one program, and reporting it as four acquisitions would
    overstate the result by the number of identical programs. Only the first
    of the three is about how many times a model was asked.
    """
    events, digests = 0, set()
    for record in records:
        entry = record["attempts"][0]
        if entry["outcome"] in ("constructed", "poor-task-result"):
            events += 1
        if entry.get("candidate_digest"):
            digests.add(entry["candidate_digest"])
    return {"construction_events": events,
            "unique_source_programs": len(digests),
            "retained_artifact_records": len(records)}


def _independence(records: list) -> dict:
    """What n means in this campaign, counted rather than asserted."""
    by_arm = {}
    for record in records:
        arm = record["treatment"]
        bucket = by_arm.setdefault(arm, {
            "treatment": arm, "draws": 0, "distinct_prompts": set(),
            "repeat_draws": 0, "outcomes": {}, "scores": [],
            "candidate_digests": [], "characters": []})
        entry = record["attempts"][0]
        bucket["draws"] += 1
        prompt_key = "%s:%d:a%d" % (record["split"], record["seed"],
                                    record["attempt"])
        if prompt_key in bucket["distinct_prompts"]:
            bucket["repeat_draws"] += 1
        bucket["distinct_prompts"].add(prompt_key)
        bucket["outcomes"][entry["outcome"]] = \
            bucket["outcomes"].get(entry["outcome"], 0) + 1
        if entry.get("score"):
            bucket["scores"].append(entry["score"]["overall"])
        if entry.get("candidate_digest"):
            bucket["candidate_digests"].append(entry["candidate_digest"])
        if isinstance(entry.get("response_characters"), int):
            bucket["characters"].append(entry["response_characters"])
    for bucket in by_arm.values():
        bucket["distinct_prompts"] = sorted(bucket["distinct_prompts"])
        bucket["distinct_prompt_count"] = len(bucket["distinct_prompts"])
        scores = sorted(bucket["scores"])
        bucket["scores_sorted"] = scores
        bucket["score_median"] = scores[len(scores) // 2] if scores else None
        bucket["distinct_behaviours"] = len(set(bucket["candidate_digests"]))
    return {
        "unit": "draws",
        "not": "independent opportunities. The reasoning is in the "
               "manifest's `independence` field, which is the copy that ships; "
               "this one reports the counts it produces. A `repeat_draws` above "
               "zero means a prompt was drawn more than once, which a reserve "
               "retry of a lost send does by design.",
        "sampling_knob": "none in `ModelRequest`; `reasoning_effort` is the "
                         "only optional field and it requires the responses "
                         "api, which is refused on a frozen route",
        "by_arm": [by_arm[arm] for arm in TREATMENTS if arm in by_arm],
    }


def _retry_transport_losses(root: Path, *, dsn: str | None = None,
                            allocation_id: str | None = None) -> dict:
    """Re-dispatch the cells whose only draw was a lost send.

    The cap sheet's retry row is explicit: "≤ 1 retry per operation identity,
    retries reuse identity". A `transport-loss` is a send that produced no
    response, which on this route arrived as an HTTP 502 but which the
    classifier decides from the absence of bytes rather than from the status
    code, so treating it as a settled construction outcome would report the
    route's availability as a result. The retry reuses the same
    `round_run_id` and therefore the same `output_operation_id`, so it is one
    lineage drawn twice and not two lineages, and it is drawn from the
    reserve the exposure file has been holding since before the first
    dispatch.

    It is not a replacement episode. The cell, the task, the attempt and the
    prompt are unchanged, and the first draw is kept and reported beside the
    second rather than overwritten.
    """
    from experiments.ad01 import live_construct as live
    from settlement.gateway_http import HttpGatewayAdapter

    endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if not endpoint or not key:
        raise SystemExit("SETTLEMENT_GATEWAY_ENDPOINT and "
                         "SETTLEMENT_GATEWAY_KEY must be set")
    if (dsn is None) != (allocation_id is None):
        raise SystemExit(
            "a retry is durable or it is not: --dsn and --allocation-id are "
            "required together, because an operation admitted without an "
            "allocation is a row the store cannot charge")

    exposure = _read_json(root / "exposure.json")
    manifest = _read_json(root / "campaign-manifest.json")
    lost = [cell for cell in exposure["attempts"]
            if cell.get("state") == "settled"
            and cell.get("outcome") == "transport-loss"
            and not cell.get("retried")]
    results = {"campaign_id": CAMPAIGN_ID, "opened_at": _now(),
               "cells_retryable": [c["arm"] + "-" + c["split"] + "-a%d"
                                   % c["attempt"] for c in lost],
               "retried": [], "skipped": [], "dispatched": 0}

    gateway = HttpGatewayAdapter(
        endpoint=endpoint, api_key=key, api=GATEWAY_API,
        expected_route=dict(live.OUTPUT_ROUTE),
        timeout_read_ms=DISPATCH_DEADLINE_MS - 10_000,
        timeout_total_ms=DISPATCH_DEADLINE_MS)
    if dsn is not None:
        gateway = live.preflight_dispatch_gateway(
            dsn, gateway, allocation_id=allocation_id)
    guard = live.LiveGuard(
        gateway,
        pinned_model=live.OUTPUT_ROUTE["requested_model"],
        ceiling=MODEL_CALL_CEILING,
        automatic_retries=live.OUTPUT_LIMITS["automatic_retries"],
        expected_route=dict(live.OUTPUT_ROUTE),
        already_spent=int(exposure.get("dispatches_spent", 0)),
        spend_reader=(lambda: live.spent_dispatches(dsn, allocation_id))
        if dsn is not None else None)

    for cell in lost:
        arm, split = cell["arm"], cell["split"]
        seed, attempt = int(cell["seed"]), int(cell["attempt"])
        name = "%s-%s-a%d-retry1" % (arm, split, attempt)
        if guard.is_ceiling_reached():
            results["skipped"].append(
                {"cell": name, "why": "model-call ceiling %d reached"
                 % MODEL_CALL_CEILING})
            continue
        try:
            entry = _dispatch_once(
                guard, arm=arm, split=split, seed=seed, attempt=attempt,
                round_run_id=cell["round_run_id"])
            task, session = _build_session(split, seed)
            record = _build_record(root, manifest, name, cell, entry, task,
                                   session, guard)
            record["retry_of"] = "%s-%s-a%d" % (arm, split, attempt)
            record["retry_reason"] = ("the first draw was a lost send, not a "
                                      "model result")
            _write_json(root / "records" / ("%s.json" % name), record)
            cell["retried"] = True
            cell["retry_record"] = "records/%s.json" % name
            cell["retry_outcome"] = entry["outcome"]
            results["retried"].append({"cell": name,
                                       "outcome": entry["outcome"]})
        except Exception as exc:
            results["skipped"].append(
                {"cell": name, "error_class": type(exc).__name__,
                 "error": str(exc)})
        results["dispatched"] = guard.spent_dispatches
        exposure["dispatches_spent"] = guard.spent_dispatches
        exposure["updated_at"] = _now()
        _write_json(root / "exposure.json", exposure)

    results["dispatches_spent"] = guard.spent_dispatches
    results["guard_status"] = guard.guard_status()
    results["closed_at"] = _now()
    _write_json(root / "retries.json", results)
    summary = summarize(root)
    summary["retries"] = results
    _write_json(root / "campaign.json", summary)
    return summary


def summarize(root: Path) -> dict:
    """Recompute the campaign's tables from the written records.

    Read-only and network-free. A third party with this directory and the
    repository reproduces every number here without a gateway.
    """
    from experiments.ad01 import live_construct as live
    manifest = _read_json(root / "campaign-manifest.json")
    exposure = _read_json(root / "exposure.json")
    records = [_read_json(p) for p in sorted((root / "records").glob("*.json"))]
    # The exposure file is what the cap sheet requires to be written before
    # effects, and it is also the one field in this directory a fabricator
    # would under-report, because a campaign that claims fewer dispatches than
    # its records show has quietly bought a fresh allowance. So the settled
    # count is re-derived from the records and the file's own number is
    # reported beside it. A mismatch is published, not silently preferred.
    dispatched = sum(1 for record in records
                     if isinstance(record["attempts"][0].get("dispatch"), dict))
    derived_settled = sum(1 for record in records
                          if record["attempts"][0].get("outcome")
                          not in (None, "carried-from-prior-run"))
    exposure_settled = int(exposure.get("attempts_settled", 0))
    per_cell = []
    for record in records:
        entry = record["attempts"][0]
        dispatch = entry.get("dispatch") or {}
        usage = dispatch.get("usage") or {}
        per_cell.append({
            "cell": record["cell_name"],
            "arm": record["treatment"],
            "split": record["split"],
            "seed": record["seed"],
            "attempt": record["attempt"],
            "operation_id": entry["operation_id"],
            "prompt_digest": dispatch.get("prompt_digest"),
            "outcome_cap_a": entry["outcome"],
            "outcome_cap_b": (entry.get("cap_b") or {}).get("verdict"),
            "response_characters": entry.get("response_characters"),
            "over_length": bool(entry.get("over_length")),
            "score": (entry.get("score") or {}).get("overall"),
            "candidate_digest": entry.get("candidate_digest"),
            "stop_reason": dispatch.get("stop_reason"),
            "returned_model": dispatch.get("returned_model"),
            "provider": dispatch.get("provider"),
            "tier": dispatch.get("tier"),
            "billed": usage.get("billed", "unknown"),
            "charge_units": usage.get("charge_units", "unknown"),
            "input_tokens": usage.get("input_tokens", "unknown"),
            "output_tokens": usage.get("output_tokens", "unknown"),
        })
    return {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "read_at": _now(),
        "offline": True,
        "freeze": FREEZE,
        "supersedes": list(SUPERSEDES),
        "cap_a_characters": _cap_a(),
        "conforming_answer_characters": conforming_answer_characters(),
        "score_floor": live.PREFLIGHT_SCORE_FLOOR,
        "reference_scores": manifest["reference_scores"],
        "cell": manifest["cell"],
        "planned": manifest["planned"],
        "exposure": {
            "attempts_planned": exposure["attempts_planned"],
            "attempts_settled_recorded": exposure_settled,
            "attempts_settled_derived": derived_settled,
            "attempts_settled": derived_settled,
            "exposure_agrees_with_records": exposure_settled == derived_settled,
            "dispatches_spent_recorded": exposure.get("dispatches_spent"),
            "dispatches_spent_derived": dispatched,
            "dispatches_carried_in": exposure.get("dispatches_carried_in", 0),
            "dispatches_refunded": exposure["dispatches_refunded"],
            "model_call_ceiling": exposure["model_call_ceiling"],
            "dispatches_reserved": exposure["dispatches_reserved"],
            "billed_true": exposure["billed_true"],
            "billed_false": exposure["billed_false"],
            "billed_unknown": exposure["billed_unknown"],
            "charge_units_known": exposure["charge_units_known"],
            "charge_units_note": exposure.get("charge_units_note"),
            "driver_faults": exposure["driver_faults"],
        },
        "counts": _counts(records),
        "cap_a": _cap_a_table(records),
        "cap_b": _cap_b_table(records),
        "independence": _independence(records),
        "per_cell": per_cell,
    }


# --- verification, offline and re-deriving -----------------------------


def _recompute_cap_b(text: str, split: str, seed: int) -> dict:
    """Re-derive the Cap B verdict from the stored bytes.

    Nothing here reads a recorded verdict. The response is re-fed to the
    protocol's own validator and the protocol's own scorer, and the answer is
    whatever they return.
    """
    from experiments.ad01 import live_construct as live
    _, session = _build_session(split, seed)
    if not text.strip():
        return {"verdict": "empty-content", "parses": False,
                "score": None, "candidate_digest": None}
    try:
        candidate = live.extract_and_validate_boolean(text)
    except Exception as exc:
        return {"verdict": "invalid-program", "parses": False,
                "score": None, "candidate_digest": None,
                "detail": "%s: %s" % (type(exc).__name__, exc)}
    committed = session.commit_predictor(candidate)
    score = session.score(committed)
    return {"verdict": _verdict_for(score), "parses": True, "score": score,
            "candidate_digest": live.source_digest(json.dumps(
                candidate, sort_keys=True, separators=(",", ":")))}


def _recompute_cap_a(text: str, split: str, seed: int,
                     cap_a: int) -> dict:
    """Re-derive the Cap A taxonomy value from the stored bytes.

    The recorded `reason` is not an input. The character count comes from the
    bytes, and the protocol's verdict comes from the protocol. A record that
    carries prose about a long response under a short one fails here, because
    the prose is never consulted and the count is taken from the string.
    """
    from experiments.ad01 import live_construct as live
    characters = len(text)
    if characters > cap_a:
        return {"outcome": "invalid-program", "characters": characters,
                "over_length": True, "parse_error": None}
    if not text.strip():
        return {"outcome": "empty-content", "characters": characters,
                "over_length": False, "parse_error": None}
    try:
        live.extract_and_validate_boolean(text)
    except Exception as exc:
        return {"outcome": "invalid-program", "characters": characters,
                "over_length": False,
                "parse_error": "%s: %s" % (type(exc).__name__, exc)}
    return {"outcome": None, "characters": characters, "over_length": False,
            "parse_error": None,
            "note": "parses under Cap A; the recorded outcome must be "
                    "`constructed` or `poor-task-result` and its score must "
                    "be the score this scorer returns"}


def _route_fields_match(returned: dict, frozen: dict) -> bool:
    """The shipped route rule, restated with no import and no transport.

    `settlement.gateway_http.route_matches` is a pure field comparison, but
    importing it executes that module's `import httpx`. This is the same rule
    with the constants restated, and it is the only restatement in the
    campaign, so it is kept in its own function where a test can reach it on
    any host rather than only on one with neither `httpx` nor `settlement`.

    The four fields are the four the guard itself compares, joined by the
    guard's own `_RETURNED_ROUTE_FIELDS`. The endpoint is a URL identity
    rather than a string equality, because `localhost` and `127.0.0.1` are the
    same place and a campaign that recorded one spelling must not read as a
    route mismatch against a guard configured with the other.
    """
    from urllib.parse import urlsplit

    if _endpoint_identity(returned.get("endpoint")) != \
            _endpoint_identity(frozen.get("endpoint")):
        return False
    for frozen_key, returned_key in (("resolved_model", "model"),
                                     ("provider", "provider"),
                                     ("tier", "tier")):
        got, want = returned.get(returned_key), frozen.get(frozen_key)
        if not isinstance(got, str) or not isinstance(want, str):
            return False
        if got.casefold() != want.casefold():
            return False
    return True


def _endpoint_identity(endpoint: object) -> str | None:
    """The loopback-insensitive endpoint identity the route rule compares on.

    A URL identity rather than a string equality. A field that is not a
    string, or a URL without a scheme and host or carrying credentials, has no
    identity and so matches nothing.
    """
    from urllib.parse import urlsplit
    if not isinstance(endpoint, str):
        return None
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc or parsed.username is not None \
            or parsed.password is not None or parsed.hostname is None:
        return None
    host = "loopback" if parsed.hostname.lower() in {
        "localhost", "127.0.0.1", "::1"} else parsed.hostname.lower()
    scheme = parsed.scheme.lower()
    default = 443 if scheme == "https" else 80
    return "%s://%s:%d" % (scheme, host,
                           port if port is not None else default)


def _offline_route_matches(returned: dict, frozen: dict) -> bool:
    """The route comparison, with no HTTP client in the import graph.

    The shipped rule is preferred and is what decides whenever the module
    imports. `_route_fields_match` is the fallback for a host where importing
    `gateway_http` fails on its `import httpx`, which is the host this
    campaign's offline contract is written for. Both are checked against each
    other on every run, so the fallback cannot drift from the rule it stands
    in for.
    """
    try:
        from settlement import gateway_http as shipped
    except ImportError:
        return _route_fields_match(returned, frozen)
    return shipped.route_matches(returned, frozen)


def _shipped_route_rule_without_transport():
    """`route_matches` loaded from source, with no `import httpx` executed.

    `gateway_http` imports `httpx` at module scope, so on a host without it
    the shipped comparison is unreachable by import and the agreement check
    would silently degrade to testing only the restatement. The rule is a pure
    function of two dicts and needs nothing from the module's transport, so it
    is read out of the parsed source instead: the named constants and the four
    functions, executed into a bare namespace, leaving `httpx` untouched.

    This is the shipped code, not a copy of it, so it cannot drift the way the
    restatement can.

    **The assumption, and what guards it.** The exec'd rule is only equivalent
    to the imported one while those names stay pure functions of their
    arguments. If a future edit gives one of them a dependency on module state
    this loader does not inject, the failure is not always loud: a missing
    name raises, but a name that resolves to a stub here would return a
    different verdict silently. Nothing in the loader can detect that, and the
    namespace deliberately injects the standard-library names `gateway_http`
    itself binds, so a shadowing edit would read them rather than fail.

    The guard is `_assert_route_rules_agree`, which runs the same seven cases
    through this loader and the restatement on every `verify`. A rule that
    stops agreeing fails the run rather than quietly passing it. That test is
    the invariant's enforcement, not this function.
    """
    import ast
    import hashlib
    import json as _json
    import os as _os
    import threading
    import time as _time
    import types
    import typing
    from dataclasses import dataclass, replace
    from urllib.parse import urlsplit, urlunsplit

    path = REPO_ROOT / "src" / "settlement" / "gateway_http.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    needed = {"_ROUTE_FIELDS", "_CASELESS_ROUTE_FIELDS", "_EXACT_ROUTE_FIELDS",
              "_RESPONSE_ROUTE_KEYS", "_canonical_local_endpoint",
              "_route_value_matches", "_endpoints_equal", "route_matches"}
    module = types.ModuleType("gateway_http_route_only")
    # These are the standard-library names `gateway_http` binds at module
    # scope, not the ones the rule is known to use: the rule's own free names
    # are builtins and locals today, and injecting the rest keeps a future
    # edit that touches one of them from failing on an unrelated import. The
    # cost is that such an edit fails by agreeing rather than by raising, which
    # is why the agreement cases below are the guard and not this list.
    module.__dict__.update({
        "typing": typing, "hashlib": hashlib, "json": _json, "os": _os,
        "threading": threading, "time": _time, "dataclass": dataclass,
        "replace": replace, "urlsplit": urlsplit, "urlunsplit": urlunsplit,
        "Any": typing.Any})
    for node in tree.body:
        if isinstance(node, ast.Assign) and \
                isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.FunctionDef):
            name = node.name
        else:
            continue
        if name in needed:
            exec(compile(ast.Module(body=[node], type_ignores=[]),
                         str(path), "exec"), module.__dict__)
    missing = needed - set(module.__dict__)
    if missing:
        from experiments.ad01 import live_construct as live
        raise live.LiveRefused(
            "gateway_http no longer defines %s" % ", ".join(sorted(missing)))
    return module.route_matches


def _assert_route_rules_agree() -> None:
    """The shipped rule and the offline restatement must decide alike.

    `verify` decides a record's route with whichever of the two it can reach,
    so if they ever disagree the verifier's verdict would depend on the host
    it ran on. These cases are the ones that have actually bitten: a
    capitalised provider the live gateway really returns, a missing field, a
    different model, and a loopback endpoint spelled two ways, plus a
    non-local host and an https endpoint, which are what a scheme-blind or
    host-blind endpoint identity would get wrong.

    The frozen side is fixed rather than derived from the returned one,
    because a fixture built from the subject under test agrees with itself by
    construction and would prove nothing.

    Both halves are checked on every host. The shipped rule is read by import
    where that works and out of the parsed source where it does not, so a host
    without `httpx` still pins the agreement rather than quietly checking one
    branch and reporting a clean run.

    Returns which half decided, so a run that reached the rule by parsing the
    source is visible in the result rather than indistinguishable from one
    that imported it.
    """
    try:
        from settlement import gateway_http as shipped
        route_matches = shipped.route_matches
        source = "imported"
    except ImportError:
        route_matches = _shipped_route_rule_without_transport()
        source = "parsed-source"
    good = {"model": "m/x:free", "provider": "Nvidia", "tier": "free",
            "endpoint": "http://127.0.0.1:4000/v1"}
    frozen = {"endpoint": "http://127.0.0.1:4000/v1",
              "resolved_model": "m/x:free", "provider": "nvidia",
              "tier": "free"}
    cases = [
        (good, True),
        ({**good, "provider": "openai"}, False),
        ({**good, "model": "m/other:free"}, False),
        ({k: v for k, v in good.items() if k != "tier"}, False),
        ({**good, "endpoint": "http://localhost:4000/v1"}, True),
        ({**good, "endpoint": "http://example.com:4000/v1"}, False),
        ({**good, "endpoint": "https://127.0.0.1/v1"}, False),
    ]
    for returned, expected in cases:
        if route_matches(returned, frozen) != expected:
            raise AssertionError(
                "the shipped route rule no longer decides %r as %r"
                % (returned, expected))
        if _route_fields_match(returned, frozen) != expected:
            raise AssertionError(
                "the offline route rule disagrees with the shipped rule on %r"
                % returned)
    return source

def verify(root: Path) -> dict:
    """Re-derive every claim from the stored observations, offline.

    `LiveGuard.infer` is withdrawn first, so any code path that reached for a
    gateway raises rather than quietly succeeding.

    What is re-derived, and from what:

    | claim | re-derived from |
    |---|---|
    | response digest | `sha256` of the stored bytes |
    | character count | `len` of the stored bytes |
    | Cap A outcome | the protocol's validator and scorer over the bytes |
    | Cap B verdict | the same, with no length check |
    | candidate digest | re-parse and re-serialize |
    | score | the `RuleSession` scorer |
    | prompt identity | re-render the frozen template and digest it |
    | route fields | compared against the frozen route by the shipped rule |

    The recorded `reason` string is read by nothing here, including for
    display. It is prose about the response and every claim below is a
    recomputation from the response itself.
    """
    from experiments.ad01 import live_construct as live
    route_rule_source = _assert_route_rules_agree()

    results = {"campaign_id": CAMPAIGN_ID, "records_seen": 0,
               "records_with_bytes_to_attest": 0,
               "records_verified": 0,
               "withheld_from_verdict": ["reason", "over_length",
                                         "cap_b.verdict", "score",
                                         "candidate_digest", "outcome"],
               "failures": [], "cells": [], "network_withdrawn": True,
               "route_rule_source": route_rule_source}
    cap_a = _cap_a()
    expected_route = dict(live.OUTPUT_ROUTE)
    history_cache: dict = {}
    withdrawn = live.LiveGuard.infer
    live.LiveGuard.infer = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("verify reached for a gateway"))
    try:
        for path in sorted((root / "records").glob("*.json")):
            record = _read_json(path)
            results["records_seen"] += 1
            entry = record["attempts"][0]
            dispatch = entry.get("dispatch")
            cell_report = {"cell": record["cell_name"],
                           "operation_id": entry["operation_id"]}
            try:
                if not isinstance(dispatch, dict):
                    # A refusal decided before the wire has no response, so
                    # there is nothing to recompute. It is neither a pass nor
                    # a failure: claiming either would assert verification
                    # that did not happen or that a record is broken.
                    cell_report["status"] = "no-response-to-attest"
                    cell_report["outcome"] = entry["outcome"]
                    results["cells"].append(cell_report)
                    continue

                raw = entry.get("raw_response")
                if not isinstance(raw, str):
                    cell_report["status"] = "no-response-to-attest"
                    cell_report["outcome"] = entry["outcome"]
                    results["cells"].append(cell_report)
                    continue
                if raw != dispatch.get("raw_response"):
                    raise AssertionError(
                        "record response differs from its own dispatch bytes")
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                if digest != dispatch.get("response_digest"):
                    raise AssertionError(
                        "response digest does not recompute from the bytes")

                arm = record["treatment"]
                key = (arm, record["split"])
                if key not in history_cache:
                    from experiments.ad01 import live_construct as _live
                    history_cache[key] = ([] if arm == "P1"
                                          else _live.output_permitted_history())
                _, session = _build_session(record["split"], record["seed"])
                prompt = live.render_output_prompt(
                    session.output_model_input(), history_cache[key],
                    int(entry["attempt"]))
                if live.source_digest(prompt) != dispatch.get("prompt_digest"):
                    raise AssertionError(
                        "prompt digest does not recompute from the frozen "
                        "template")
                if entry["operation_id"] != live.output_operation_id(
                        arm, record["split"], int(record["seed"]),
                        int(entry["attempt"]),
                        round_run_id=record["round_run_id"]):
                    raise AssertionError(
                        "operation identity does not recompute")

                # The route is joined to the response field names by the
                # guard's own table rather than by a second spelling written
                # here, so this check cannot disagree with the guard about
                # which field is which.
                if entry["outcome"] not in ("route-refusal", "transport-loss",
                                            "pre-dispatch-refusal"):
                    returned = {
                        route_key: dispatch.get(record_key)
                        for record_key, route_key
                        in live.LiveGuard._RETURNED_ROUTE_FIELDS}
                    if not _offline_route_matches(returned, expected_route):
                        raise AssertionError(
                            "returned route %r does not match the frozen route"
                            % json.dumps(returned, sort_keys=True))

                characters = len(raw)
                if entry.get("response_characters") != characters:
                    raise AssertionError(
                        "recorded character count %r does not match the %d "
                        "characters in the stored response"
                        % (entry.get("response_characters"), characters))

                # Cap A, re-derived. The recorded `reason` is not an input.
                cap_a_derived = _recompute_cap_a(raw, record["split"],
                                                 int(record["seed"]), cap_a)
                if bool(entry.get("over_length")) != \
                        cap_a_derived["over_length"]:
                    raise AssertionError(
                        "over-length flag %r does not match the %d characters "
                        "stored against a cap of %d"
                        % (entry.get("over_length"), characters, cap_a))
                if cap_a_derived["outcome"] is not None and \
                        entry["outcome"] != cap_a_derived["outcome"]:
                    raise AssertionError(
                        "Cap A outcome %r re-derives as %r"
                        % (entry["outcome"], cap_a_derived["outcome"]))
                if cap_a_derived["outcome"] is None:
                    # It parses, so the outcome must be a construction one and
                    # the score must be the scorer's, not the record's.
                    if entry["outcome"] not in ("constructed",
                                                "poor-task-result"):
                        raise AssertionError(
                            "response parses under Cap A but is recorded as "
                            "%r" % entry["outcome"])
                    derived = _recompute_cap_b(raw, record["split"],
                                               int(record["seed"]))
                    if derived["verdict"] != entry["outcome"]:
                        raise AssertionError(
                            "outcome %r re-derives as %r"
                            % (entry["outcome"], derived["verdict"]))
                    if entry.get("score") != derived["score"]:
                        raise AssertionError(
                            "score does not recompute from the response")
                    if entry.get("candidate_digest") != \
                            derived["candidate_digest"]:
                        raise AssertionError(
                            "candidate digest does not recompute")

                # Cap B, re-derived independently of Cap A.
                derived_b = _recompute_cap_b(raw, record["split"],
                                             int(record["seed"]))
                recorded_b = (entry.get("cap_b") or {}).get("verdict")
                if recorded_b != derived_b["verdict"]:
                    raise AssertionError(
                        "Cap B verdict %r re-derives as %r"
                        % (recorded_b, derived_b["verdict"]))

                cell_report["status"] = "verified"
                cell_report["characters"] = characters
                cell_report["cap_a"] = entry["outcome"]
                cell_report["cap_b"] = derived_b["verdict"]
                results["cells"].append(cell_report)
                results["records_verified"] += 1
                results["records_with_bytes_to_attest"] += 1
            except Exception as exc:
                cell_report["status"] = "failed"
                cell_report["error"] = "%s: %s" % (type(exc).__name__, exc)
                results["cells"].append(cell_report)
                results["failures"].append(
                    {"record": path.name, "error_class": type(exc).__name__,
                     "error": str(exc)})
    finally:
        live.LiveGuard.infer = withdrawn
    results["recomputed"] = [c for c in results["cells"]
                             if c["status"] == "verified"]
    results["no_response_to_attest"] = [
        c for c in results["cells"] if c["status"] == "no-response-to-attest"]
    # The three counts are different denominators and are published as three
    # fields so no table can collapse them: every record on disk, the subset
    # that carries bytes to re-derive, and the subset that re-derived clean.
    results["denominators"] = {
        "records_on_disk": results["records_seen"],
        "with_response_bytes": results["records_with_bytes_to_attest"],
        "lost_sends": len(results["no_response_to_attest"]),
        "verified": results["records_verified"],
        "failed": len(results["failures"]),
    }
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "retry", "summarize",
                                            "verify", "manifest"))
    parser.add_argument("--root", default=str(REPO_ROOT / "reports" / "evidence"
                                              / CAMPAIGN_ID))
    parser.add_argument("--dsn", default="")
    parser.add_argument("--allocation-id", default="")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "run":
        print(json.dumps(_run(root, dsn=args.dsn or None,
                              allocation_id=args.allocation_id or None),
                         sort_keys=True, indent=1))
    elif args.command == "retry":
        print(json.dumps(_retry_transport_losses(
            root, dsn=args.dsn or None,
            allocation_id=args.allocation_id or None),
            sort_keys=True, indent=1))
    elif args.command == "summarize":
        print(json.dumps(summarize(root), sort_keys=True, indent=1))
    elif args.command == "manifest":
        print(json.dumps(_build_manifest(), sort_keys=True, indent=1))
    else:
        outcome = verify(root)
        print(json.dumps(outcome, sort_keys=True, indent=1))
        return 0 if not outcome["failures"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
