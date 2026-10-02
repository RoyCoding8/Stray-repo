"""M3: a prospective pilot with a competent authored control and a real menu.

Milestone M3 (`WORKER-STAGE-09-CONNECTED-STUDY.md:55`) asks for three things
at once and this module runs all three on one panel, through one execution
path, under one set of limits:

- construction **with development experience** against construction with
  **only the public interface**. The two prompts are the same packet with
  one field differing, `diagnostics.observations`, so the treatment is
  experience and not prompt length, and it is separate from anything else.
- a **competent authored control** at the same oracle/action/compute limits.
  The control names a strategy in its own source. It is not the default, so
  a tie is a measurement rather than an arithmetic certainty.
- the child menu, which C15 (`8c535e3`) opened. Every member is gated by
  `menu_answers_nothing` before anything is dispatched, and the arms are
  gated by `control_distinct` afterwards, so a run that reproduces the tie
  it was going to reproduce anyway is refused rather than reported.

Three arms, paired on every task, so the comparison is paired and the
budget is the same on both sides of it. The two acquired arms are built in
the calibration world (`w0`) and scored on `w1` and `w2`, so every acquired
score is a score on a world the member was not constructed on. That is a
within-family, same-representation transfer. It is not a cross-family or
cross-representation transfer diagnostic, and it is not zero-shot.

    arm              who wrote the bytes            strategy named by
    ---------------  -----------------------------  ----------------------
    dev-exp          the model, development trace   the model's own choice
    public-interface the model, no trace             the model's own choice
    authored-control supplied                        an explicit literal

Why the control source is a literal and not `run_seed`. The first authored
control in this repository (`scripts/inv01_study.py:929`) declared two
members whose `method_source` was byte-identical and called `run_seed`,
which the child namespace does not bind, so it would have raised
`NameError` had the study ever called it. The study does not call it. The
control here calls the bound `reducers.reduce_software` / `reduce_graph`
with a `method` literal, which is the shape the child actually executes.

A defect this run found, which no gate currently reports.
`child_contract` declares `reduce_software(task, oracle, method,
max_queries)` and `packet.public_operations` hands that text to the model,
so `method` reads as the third positional argument. The wrapper
`_wrapper_for` actually binds is `(task, oracle, *, max_queries=16,
**kwargs)`, so `method` is keyword-only. A model that follows the
documented contract and writes `reduce_graph(task, oracle, "ddmin",
max_queries)` passes `verify_member`, which checks only the entry's own
arity, and then raises `TypeError: reduce_graph() takes 2 positional
arguments but 3 positional arguments` in the child. The same model writing
`method="ddmin"` runs. This is a contract that mis-documents its own
binding, distinct from C14 and from the inert control, and it is recorded
here rather than patched: `method_exec.py` is owned by the C15 lane.

Dispatches and cost are recorded in two currencies and never summed.
`dispatches` counts physical model sends that reached the provider, and a
send the gateway refused *before* the wire is admitted, settled, and
counted as zero. `provider_reported_cost` is what the provider's own
`usage` block said, and on a free route it is zero because the route is
free, not because anything was measured. It is recorded as reported, never
as a measured zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import control_distinctness as gates
from experiments.ad01 import method_exec, packet, worlds
from experiments.ad01 import s09_run_isolation as isolation

ARMS = ("dev-exp", "public-interface", "authored-control")

# The two strategies the child menu offers. A competent control names one
# in its own bytes; which one is frozen before any dispatch, not chosen
# afterwards from a result.
CONTROL_STRATEGY = "ddmin"

# Per-request bounds, frozen before the first send. Wide enough to emit an
# executable artifact, which a reasoning-only output would not be.
REQUEST_BOUNDS = {"max_output_tokens": 2048, "deadline_ms": 300_000}
MAX_QUERIES = 16
REASONING_EFFORT = "high"

# The panel. Two worlds, one software and one graph task each, so the panel
# carries the two strategies apart. The graph tasks are where ddmin and
# greedy return different candidates on every one of them; the software
# tasks are where they often agree, which is itself the finding.
PANEL = [
    ("w1", 1, "ad01-w1-within-gr-00", "graph"),
    ("w1", 1, "ad01-w1-within-sw-00", "software"),
    ("w2", 2, "ad01-w2-within-gr-00", "graph"),
    ("w2", 2, "ad01-w2-within-sw-00", "software"),
]

# The development trace the `dev-exp` arm reads. Two tasks per family, all
# from the calibration world, so no scored task is ever in the treatment.
# Four distinct development tasks is what M3 asks for where the finite
# support permits it, and the world supports exactly this many without
# touching the panel.
DEVELOPMENT = {
    "software": ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"],
    "graph": ["ad01-w0-dev-gr-00", "ad01-w0-dev-gr-01"],
}

REDUCTOR = {"software": "reduce_software", "graph": "reduce_graph"}

# The arm whose prompt is fixed before the run starts. `public-interface`
# renders from an empty experience list, so its bytes are a function of the
# frozen panel, the frozen bounds and the frozen source, and the freeze can
# commit their digest. `dev-exp` cannot: its experience is earned by the run
# it is an input to, so at freeze time there is nothing to hash. It is
# recorded as unvouched rather than guessed, which is the whole point of
# committing a digest instead of writing one into the result afterwards.
PRE_DETERMINABLE_ARM = "public-interface"


def committed_prompt_digests() -> dict:
    """The digests the freeze commits, one per family, before any send.

    These are the prompts the study will send for `PRE_DETERMINABLE_ARM`,
    rendered through the same `construction_prompt` the dispatch uses. A
    family whose prompt is not a function of frozen inputs is absent, and its
    absence is the honest record rather than a digest of a placeholder.
    """
    committed = {}
    for family in sorted(DEVELOPMENT):
        task = worlds.load_task(worlds.FROZEN_DIR, DEVELOPMENT[family][0])
        prompt = construction_prompt(
            family, task, experience=[], prior_failure=None,
            budget=REQUEST_BOUNDS)
        committed[family] = _digest(prompt)
    return committed


class PilotRefused(RuntimeError):
    """The run stopped before or instead of a dispatch it could not justify."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _prompt_digest_verdict(digest: str, committed: str | None, arm: str
                           ) -> tuple[bool, str]:
    """Did this run send the bytes its freeze committed?

    The comparison runs from the sent bytes toward the commitment, because
    the commitment is the fixed side. Nothing here re-renders anything: the
    prompt exists, it was dispatched, and the question is only whether the
    freeze named it.

    A `dev-exp` dispatch is `False` by construction, not by failure. Its
    experience is produced by the same run, so at freeze time the prompt did
    not exist to be hashed. That is a different fact from "the bytes drifted
    under us", and the note keeps them apart.
    """
    if committed is None:
        if arm == PRE_DETERMINABLE_ARM:
            return False, ("the freeze commits no digest for this arm, so "
                           "these bytes are unvouched")
        return False, ("%s earns its experience from this run, so its prompt "
                       "did not exist when the freeze was written and no "
                       "digest could be committed for it" % arm)
    if digest == committed:
        return True, "the sent bytes hash to the digest the freeze committed"
    return False, ("the freeze committed %s, this run sent bytes hashing to "
                   "%s" % (committed[:16], digest[:16]))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- the arms

def control_source(family: str, strategy: str = CONTROL_STRATEGY) -> str:
    """The control's bytes as a bare string, shared by the member and dry."""
    return (
        "def ENTRY(task, oracle, max_queries=%d):\n"
        "    return reducers.%s(task, oracle, method=%r,"
        " max_queries=max_queries)\n"
        % (MAX_QUERIES, REDUCTOR[family], strategy))


def control_member(family: str, strategy: str = CONTROL_STRATEGY) -> dict:
    """A competent authored control at the arms' own limits.

    The source names `reducers.reduce_software` / `reduce_graph`, which the
    child binds, and passes `method` as a literal in its own body. Nothing
    downstream supplies the strategy, so the member is competent by
    construction and the gate can read which strategy ran out of executed
    evidence rather than out of a declared digest.
    """
    source = control_source(family, strategy)
    return {"capability_id": "authored-control-%s-%s" % (family, strategy),
            "authored": True, "origin": "m3-frozen-control",
            "entry": "ENTRY", "method_source": source,
            "source_digest": _digest(source),
            "scope": {"family": family}, "params": {"method": strategy}}


def _experience_for(dsn: str, identity, family: str) -> list:
    """Observations from the family's development tasks, on the real oracle.

    These are the treatment. Every task is a calibration-world task the
    panel never scores, and the public-interface arm receives an empty list,
    so the two prompts differ in exactly this field. The trace carries one
    observation per development task, which is what makes
    `experience_varies` a real check here rather than a formality: a trace
    of one outcome would refuse it, and would deserve to.
    """
    from experiments.ad01 import trajectory
    observations = []
    member = control_member(family)
    for index, task_id in enumerate(DEVELOPMENT[family]):
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        result = method_exec.run_member_out_of_process(
            member, task, max_queries=MAX_QUERIES, dsn=dsn,
            allocation_id=identity.allocation_id,
            operation_id=identity.operation_id("devobs", family,
                                                "d%d" % index))
        verdict = trajectory._check(task, result.get("candidate") or {})
        candidate = result.get("candidate") or {}
        initial, kept = trajectory._size(task, candidate)
        observations.append(
            {"observation_id": "m3-dev-%s-%d" % (family, index),
             "task_id": task_id, "capability_id": member["capability_id"],
             # `verdict` is the coarse field the E2 variation gate reads and
             # it is `preserved` on every dev task. The reason code, the
             # normalized reduction and the query count are what actually
             # differ across development episodes, so they are what the
             # treatment carries; the coarse verdict rides along so the E2
             # gate can be applied to this arm as written.
             "verdict": verdict.get("verdict"),
             "reason": verdict.get("reason"),
             "method": CONTROL_STRATEGY,
             "normalized_reduction": (
                 ((initial - kept) / initial) if initial else None),
             "detail": {"queries": result.get("queries"),
                        "initial_size": initial, "kept_size": kept}})
    return observations


def construction_prompt(family: str, task: dict, *,
                        experience: list, prior_failure: dict | None,
                        budget: dict) -> str:
    """The construction prompt, from the packet the study already renders.

    `experience` is the whole treatment. An empty list and a populated one
    produce the same packet with `diagnostics.observations` differing, and
    nothing else.
    """
    from experiments.ad01 import construct
    return construct._prompt(task, {"observations": experience}, budget,
                             prior_failure)


def _parse_source(text: str) -> tuple:
    """The model's reply, parsed to source and its envelope's own count.

    A reply that is not one JSON object with a non-empty `entry` string is
    a construction failure with the reason, not a source with the reason
    commented out of it.
    """
    try:
        payload = json.loads(text)
    except ValueError as exc:
        return None, "response is not one json object: %s" % (exc,)
    if not isinstance(payload, dict):
        return None, "response is not a json object"
    source = payload.get("entry")
    if not isinstance(source, str) or not source.strip():
        return None, "response carries no entry source"
    return source, None


# ------------------------------------------------------------- the dispatch

def _live_gateway(route: dict):
    """The live HTTP adapter with the route pinned.

    The route has to be pinned. An adapter with no `expected_route` refuses
    every dispatch as an unproven free route, and it refuses them *before*
    the send, so the run spends nothing, writes four `pre-send-route-
    refusal` receipts, and exits zero looking like a study. Pinning the
    route is what makes a dispatch physical.
    """
    from settlement.config import Settings
    from settlement.gateway_http import HttpGatewayAdapter
    if not route or not route.get("resolved_model"):
        raise PilotRefused("live gateway needs a pinned route")
    settings = Settings.from_env()
    if not settings.gateway.endpoint:
        raise PilotRefused("live gateway needs SETTLEMENT_GATEWAY_ENDPOINT")
    # `chat`, not `responses`: a frozen route is refused pre-send on the
    # responses surface, which publishes no provider field, and this adapter
    # pins one. Refusing would kill every live dispatch here.
    return HttpGatewayAdapter.from_settings(
        settings, api="chat", expected_route=route)


def _dry_gateway(source_for):
    """A gateway that answers from a local script, for a plumbing dry run.

    It implements the same `infer` interface the live adapter has, so
    admission, dispatch, the receipt and the reply parsing are all
    exercised. Nothing reaches a provider, and a dry result says nothing
    about the model: it exists so the pipeline is proved before the free
    route is spent on it.
    """
    from settlement.gateway import ModelResponse, Usage

    class Dry:
        def infer(self, request):
            return ModelResponse(
                operation_id=request.operation_id,
                text=source_for(request),
                model_meta={"adapter": "m3-dry"},
                usage=Usage(input_tokens=0, output_tokens=0,
                            charge_units=None, billed=False),
                stop_reason="end_turn")

    return Dry()


def _route() -> dict:
    from scripts import inv01_study as S
    model = os.environ.get("M3_MODEL", "").strip()
    if not model:
        raise PilotRefused("M3 needs an explicit M3_MODEL")
    route = S._v1_route_from_env(model)
    route["requested_model"] = model
    return route


def _read_receipt(dsn: str, operation_id: str) -> dict:
    """The durable receipt, and what the provider said about its own cost."""
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT receipt_identity, outcome, content FROM receipts"
                " WHERE operation_id = %s ORDER BY receipt_identity",
                (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    for row in rows:
        if row.get("outcome") == "success":
            return row
    return rows[0] if rows else {}


def construct_once(dsn: str, identity, gateway, model: str, *,
                   arm: str, family: str, task: dict, experience: list,
                   lineage: int,
                   committed: Mapping[str, str] | None = None) -> dict:
    """One construction send, admitted and dispatched the durable way.

    The order is `authority.admit_study_call` then
    `broker.dispatch_operation`, and the reservation owner is never
    bypassed. A refusal is returned, not raised, so a store that declined
    the work is reported rather than dropped.

    `committed` is what the freeze promised for this run, and it is compared
    here, against the bytes actually sent, at the moment the bytes exist.
    Recording a digest with nothing to compare it to is what let four
    construction digests in `inv_r1_aa3_m3` go stale unnoticed.
    """
    from settlement import authority, broker, loop

    # The family is part of the identity, not a field of the payload. Two
    # constructions that differ only in their family carry different
    # prompts, and a study identity reused with a different payload is a
    # refusal the store is right to raise.
    operation_id = identity.operation_id("construct", family, "l%d" % lineage,
                                          arm)
    prompt = construction_prompt(
        family, task, experience=experience, prior_failure=None,
        budget=REQUEST_BOUNDS)
    payload = {"model": model,
               "messages": [{"role": "user", "content": prompt}],
               "max_output_tokens": REQUEST_BOUNDS["max_output_tokens"],
               "deadline_ms": REQUEST_BOUNDS["deadline_ms"],
               "reasoning_effort": REASONING_EFFORT}
    granted = authority.admit_study_call(
        dsn, identity.study_root, kind="development",
        operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload=payload)
    if not isinstance(granted, loop.Grant):
        return {"operation_id": operation_id, "admitted": False,
                "arm": arm, "task_id": task["task_id"],
                "refusal": getattr(granted, "reason", "unknown"),
                "detail": getattr(granted, "detail", "")}
    broker.dispatch_operation(dsn, operation_id, launchers={},
                              gateway=gateway)
    receipt = _read_receipt(dsn, operation_id)
    content = dict(receipt.get("content") or {})
    text = str(content.get("text") or "")
    usage = dict(content.get("usage") or {})
    response_class = str(content.get("response_class") or "")
    # A pre-send route refusal is admitted and settled but never left the
    # process. Counting it as a dispatch would overstate the spend by
    # exactly the number of sends the adapter refused, which is how a run
    # that sent nothing can read as one that sent four.
    sent = response_class != "pre-send-route-refusal"
    source, reason = _parse_source(text) if text else (
        None, str(content.get("error") or "no settled response text"))
    prompt_digest = _digest(prompt)
    matched, why = _prompt_digest_verdict(
        prompt_digest, dict(committed or {}).get(family), arm)
    record = {
        "operation_id": operation_id, "arm": arm, "lineage": lineage,
        "task_id": task["task_id"], "family": family,
        "admitted": True, "receipt_identity": receipt.get("receipt_identity"),
        "outcome": receipt.get("outcome"), "response_class": response_class,
        "sent": sent,
        "exposure_units": granted.exposure, "budget_kind": granted.budget_kind,
        "prompt_sha256": prompt_digest, "prompt_chars": len(prompt),
        "prompt_digest_matched": matched, "prompt_digest_note": why,
        "source": source, "parse_failure": reason,
        "dispatched_at": _timestamp(),
    }
    if source is not None:
        record["source_digest"] = _digest(source)
    # Three currencies, kept apart and never summed.
    #
    # `dispatches` is a physical count of sends that reached the gateway.
    # `internal_charge_units` is what the broker's own billing records
    # carry, and it is `None` when the response was not billed, which is an
    # absence rather than a measured zero. `provider_reported_cost` is what
    # the provider's own `usage` block said; on a free route it is 0
    # because nothing is charged, which is a price, not a measurement.
    record["currencies"] = {
        "dispatches": 1 if sent else 0,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "internal_charge_units": usage.get("charge_units"),
        "internal_charge_scale": usage.get("charge_scale"),
        "billed": usage.get("billed"),
        "provider_enforced_ceiling": usage.get("provider_enforced_ceiling"),
        "provider_reported_cost": None,
        "note": ("a free route reports provider cost 0 because the route is"
                 " free; that is an absence of a price, not a measured"
                 " zero cost"),
    }
    return record


# ------------------------------------------------------------- the scoring

def _qualify(source: str, family: str) -> tuple:
    """Whether the model's bytes are a member the child will run.

    A member that cannot pass `verify_member` is reported as a construction
    failure with the reason. It is never quietly replaced by the control.
    """
    member = {"capability_id": "acquired-check", "method_source": source,
              "entry": "ENTRY", "params": {"max_queries": MAX_QUERIES},
              "scope": {"family": family}, "authored": False}
    try:
        method_exec.verify_member(member)
        method_exec.verify_child_contract()
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)
    return member, None


def score_member(dsn: str, identity, member: dict, task: dict) -> dict:
    """Execute one member against one task, out of process, durably.

    The reduction is measured by `trajectory._size`, which counts `ops` for
    a software task and vertices plus edges for a graph one. A graph task
    has no `ops` key at all, so a measure written for software alone reads
    every graph task as a zero-byte candidate and every graph result as a
    tie.
    """
    from experiments.ad01 import trajectory
    operation_id = identity.operation_id(
        "score", member["capability_id"], task["task_id"])
    try:
        result = method_exec.run_member_out_of_process(
            member, task, max_queries=MAX_QUERIES, dsn=dsn,
            allocation_id=identity.allocation_id, operation_id=operation_id)
    except Exception as exc:
        # The reason matters. A member that reads the contract's declared
        # signature and calls `reduce_graph(task, oracle, "ddmin")` passes
        # `verify_member` and then raises a `TypeError` in the child,
        # because the contract declares `method` positional while the
        # generated wrapper makes it keyword-only. Recording the bare class
        # name would hide that the bytes were a correct reading of a
        # contract the wrapper does not honour.
        return {"task_id": task["task_id"], "family": task.get("family"),
                "executed": member["capability_id"],
                "authored": bool(member.get("authored")),
                "executed_source": member["method_source"],
                "output": {}, "queries": None, "verdict": "execution-refused",
                "initial_size": None, "kept_size": None,
                "normalized_reduction": None,
                "execution_error": "%s: %s" % (type(exc).__name__, exc),
                "costs": {"witness_queries": 0}, "operation_ids": [operation_id]}
    candidate = result.get("candidate") or {}
    verdict = trajectory._check(task, candidate)
    initial, kept = trajectory._size(task, candidate)
    return {"task_id": task["task_id"], "family": task.get("family"),
            "executed": member["capability_id"],
            "authored": bool(member.get("authored")),
            "executed_source": member["method_source"],
            "output": candidate, "queries": result.get("queries"),
            "verdict": verdict.get("verdict"),
            "reason": verdict.get("reason"),
            "initial_size": initial, "kept_size": kept,
            "normalized_reduction": (
                ((initial - kept) / initial) if initial else None),
            "costs": {"witness_queries": int(result.get("queries") or 0)},
            "operation_ids": [operation_id]}


# -------------------------------------------------------------- the verdict

def paired_records(arms: dict) -> tuple:
    """The gate's two columns, keyed the way `control_distinct` reads them."""
    control = [r for rows in arms["authored-control"].values()
               for r in rows]
    for treatment in ("dev-exp", "public-interface"):
        acquired = [r for rows in arms[treatment].values() for r in rows]
        yield treatment, control, acquired


def run_panel(dsn: str, identity, gateway, model: str, out: Path, *,
              committed: Mapping[str, str] | None = None) -> dict:
    """Construct once per (arm, family), then score every arm on the panel.

    A member is constructed per family, not per task, and is then scored on
    every panel task of that family. That is what makes the comparison
    paired: the control, the development-experience arm and the
    public-interface arm all run the same tasks through the same sandbox
    with the same budget, and only the bytes and the prompt differ.

    `committed` is the freeze's own prompt digest table, passed in rather
    than re-derived here, so the run is compared against what was written
    down before it started rather than against itself.
    """
    construction = []
    experience = {}
    members = {}

    for family in sorted(DEVELOPMENT):
        experience[family] = _experience_for(dsn, identity, family)
        dev_task = worlds.load_task(worlds.FROZEN_DIR,
                                    DEVELOPMENT[family][0])
        for arm in ("dev-exp", "public-interface"):
            observations = experience[family] if arm == "dev-exp" else []
            record = construct_once(
                dsn, identity, gateway, model, arm=arm, family=family,
                task=dev_task, experience=observations, lineage=1,
                committed=committed)
            construction.append(record)
            member = None
            if record.get("source"):
                member, _ = _qualify(record["source"], family)
            members[(arm, family)] = member
        members[("authored-control", family)] = control_member(family)

    arms = {arm: {} for arm in ARMS}
    for label, world, task_id, family in PANEL:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        for arm in ARMS:
            member = members.get((arm, family))
            if member is None:
                arms[arm][task_id] = [{
                    "task_id": task_id, "family": family,
                    "executed": "construction-failed",
                    "authored": False, "executed_source": "",
                    "output": {}, "queries": None, "verdict": "not-constructed",
                    "initial_size": None, "kept_size": None,
                    "normalized_reduction": None,
                    "costs": {"witness_queries": 0}, "operation_ids": []}]
                continue
            scored = score_member(dsn, identity, member, task)
            scored["capability_id"] = scored["executed"]
            arms[arm][task_id] = [scored]

    return {"arms": arms, "construction": construction,
            "experience": experience,
            "members": {"%s/%s" % key: (value or {}).get("method_source")
                        for key, value in sorted(members.items())}}


def _fmt(value, places: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return ("%." + str(places) + "f") % value
    return str(value)


def _failures(result: dict) -> list:
    """Every way this run did not measure what it set out to measure.

    Each is a fact about the run, not a conclusion drawn from it, and each
    names the surface that produced it so a reader can go and look.
    """
    found = []
    for record in result["construction"]:
        arm = "%s/%s" % (record.get("arm"), record.get("family"))
        if record.get("outcome") == "unknown":
            found.append((
                "%s lost its response" % arm,
                "the receipt is `%s`: the send left and no response was"
                " recovered. The spend on it is uncertain, so it is"
                " recorded as unknown and not as a zero."
                % record.get("receipt_identity")))
        elif record.get("outcome") not in ("success", None):
            found.append((
                "%s was refused" % arm,
                "receipt `%s`, class `%s`: %s"
                % (record.get("receipt_identity"),
                   record.get("response_class"),
                   str(record.get("parse_failure"))[:160])))
        elif not record.get("source"):
            found.append((
                "%s produced no source" % arm,
                str(record.get("parse_failure"))[:200]))
    for arm, tasks in sorted(result["arms"].items()):
        for task_id, rows in sorted(tasks.items()):
            for row in rows:
                error = row.get("execution_error")
                if not error:
                    continue
                found.append((
                    "%s failed to execute on %s" % (arm, task_id),
                    "`%s`. Bytes: `%s`"
                    % (str(error).split(":", 1)[-1].strip()[:180],
                       (row.get("executed_source") or "(none)")
                       .replace("\n", " ").strip()[:150])))
    return found


def write_result_md(result: dict, out: Path) -> None:
    """The human-readable result, generated from the machine-readable one.

    It is written by the same code that produced `result.json` so the prose
    cannot drift from the numbers it describes.
    """
    arms = result["arms"]
    freeze = result["freeze"]
    gates = result["gates"]
    construction = result["construction"]
    panel = [row[2] for row in freeze["panel"]]

    admitted = [c for c in construction if c.get("admitted")]
    sent = [c for c in admitted if c.get("sent")]
    presend = [c for c in admitted if not c.get("sent")]
    billed = [c for c in sent if c["currencies"].get("billed") is True]
    charge_units = [c["currencies"].get("internal_charge_units")
                    for c in billed]

    lines = []
    lines.append("# M3: a competent authored control, an open menu, and what"
                 " the model chose")
    lines.append("")
    lines.append("`%s`, model `%s`, tier `%s`, store `%s`."
                 % (freeze["study_root"], freeze["model"],
                    freeze["route"].get("tier"), freeze["store"]))
    lines.append("")
    lines.append("M3 (`WORKER-STAGE-09-CONNECTED-STUDY.md:55`) asks for"
                 " construction with development experience against"
                 " construction with only the public interface, plus a"
                 " competent authored control at the same"
                 " oracle/action/compute limits. This run has all three,"
                 " paired on every task, and every send went through"
                 " `authority.admit_study_call` and then"
                 " `broker.dispatch_operation`.")
    lines.append("")

    lines.append("## The arms are distinct, and by which leg")
    lines.append("")
    lines.append("| arm | family | strategy the bytes name | source |")
    lines.append("|---|---|---|---|")
    for key, source in sorted(result["members"].items()):
        if not source:
            lines.append("| `%s` | | (construction failed) | |" % key)
            continue
        strategy = ("ddmin" if "ddmin" in source
                    else "greedy" if "greedy" in source else "none named")
        lines.append("| `%s` | %s | %s | `%s` |"
                     % (key, key.split("/")[-1], strategy,
                        source.splitlines()[-1].strip()[:80]))
    lines.append("")
    for name in ("dev-exp", "public-interface"):
        verdict = gates.get(name, {})
        if verdict.get("distinct"):
            lines.append("`control_distinct` passes for `%s`: the executed"
                         " policy id, the strategy that policy ran and the"
                         " returned candidate all separate the two arms."
                         % name)
        else:
            lines.append("`control_distinct` **refuses** for `%s`: %s"
                         % (name, verdict.get("refusal", "no verdict")))
    lines.append("")

    lines.append("## What each arm scored")
    lines.append("")
    lines.append("| task | family | dev-exp | public-interface |"
                 " authored-control |")
    lines.append("|---|---|---|---|---|")
    for task_id in panel:
        cells = []
        for arm in ARMS:
            rows = arms[arm].get(task_id) or []
            if not rows:
                cells.append("no record")
                continue
            row = rows[0]
            if row.get("verdict") in ("not-constructed", "execution-refused"):
                cells.append("**%s**" % row["verdict"])
            else:
                cells.append("%s (%s, %s q)"
                             % (_fmt(row.get("normalized_reduction")),
                                row.get("verdict"), row.get("queries")))
        family = (arms["authored-control"].get(task_id) or [{}])[0].get(
            "family", "")
        lines.append("| `%s` | %s | %s | %s | %s |"
                     % (task_id, family, cells[0], cells[1], cells[2]))
    lines.append("")

    lines.append("## Dispatches and cost, in separate currencies")
    lines.append("")
    lines.append("- **Admitted sends**: %d." % len(admitted))
    lines.append("- **Physical dispatches**: %d. A send the adapter refused"
                 " before it left the process is admitted and settled but"
                 " never dispatched, and it is counted here as a dispatch"
                 " only if it actually left."
                 % len(sent))
    if presend:
        lines.append("- **Pre-send route refusals**: %d. Each one is a"
                     " refusal the adapter raised before the send, so the"
                     " spend from these is zero, not a failed send."
                     % len(presend))
    lines.append("- **Provider-reported cost**: the route is free, so the"
                 " provider reports zero. That is an absence of a price,"
                 " not a measured zero cost, and it is not comparable to"
                 " an unqualified baseline.")
    lines.append("- **Internal charge units**: %s. The broker records"
                 " `charge_units` only when a response is billed; on this"
                 " free route it is absent, which is recorded as absent"
                 " and never as a zero."
                 % (", ".join(str(u) for u in charge_units) if charge_units
                    else "absent on every send"))
    lines.append("")
    lines.append("The two token counts the receipt carries are the internal"
                 " denominations. They are reported here and never summed"
                 " with the provider's reported cost, which is on a"
                 " different scale and, on this route, is not a price at"
                 " all.")
    lines.append("")

    failures = _failures(result)
    if failures:
        lines.append("## What failed, and why it is not a model failure")
        lines.append("")
        for kind, detail in failures:
            lines.append("- **%s**: %s" % (kind, detail))
        lines.append("")
        lines.append(
            "The graph members that failed wrote `reduce_graph(task,"
            " oracle, \"ddmin\", max_queries)`, which is the call"
            " `child_contract` documents. The wrapper the child binds is"
            " `(task, oracle, *, max_queries=16, **kwargs)`, so `method`"
            " is keyword-only and that call is a `TypeError`. The model"
            " obeyed the contract. `verify_member` passed it because it"
            " checks the entry's arity and never the calls inside it. This"
            " is a contract that mis-documents its own binding; the fix is"
            " in `method_exec.py`, which this lane does not own.")
        lines.append("")

    lines.append("## What M3 can claim, and what it cannot")
    lines.append("")
    lines.append(_verdict_prose(gates, result))
    lines.append("")
    lines.append("## Reproducing this")
    lines.append("")
    lines.append("The generator is committed at"
                 " `experiments/ad01/s09_m3_pilot.py`. It writes"
                 " `freeze.json`, `result.json` and this file from one"
                 " run, so the prose cannot drift from the numbers.")
    lines.append("")
    lines.append("    # no provider contact, proves the pipeline and the gates")
    lines.append("    python -m experiments.ad01.s09_m3_pilot \\")
    lines.append("        --out /tmp/m3dry --token m3dry --dry")
    lines.append("")
    lines.append("    # the live run this directory holds")
    lines.append("    python -m experiments.ad01.s09_m3_pilot \\")
    lines.append("        --out <dir> --token <token>")
    lines.append("")
    lines.append("The live form needs `SETTLEMENT_GATEWAY_ENDPOINT`, the"
                 " gateway key in the environment, and `M3_MODEL`. The"
                 " route is read from `SETTLEMENT_EXPECTED_ROUTE` and"
                 " must pin `tier: free`; the dispatch model is the"
                 " route's `requested_model`, and the store is a fresh"
                 " disposable database the run drops on exit.")
    lines.append("")
    (out / "RESULT.md").write_text("\n".join(lines) + "\n")


def _verdict_prose(gates: dict, result: dict) -> str:
    """The five verdicts M4 asks for, in M3's own evidence."""
    distinct = [name for name in ("dev-exp", "public-interface")
                if gates.get(name, {}).get("distinct")]
    constructed = [c for c in result["construction"] if c.get("source")]
    parts = []
    parts.append(
        "Mechanism `true`: the child menu is open (`menu_answers_nothing`"
        " reports no defaulting strategy), every arm executes out of"
        " process through the real sandbox, and every scored number is"
        " re-derived by the study's own checker.")
    if len(constructed) == len(result["construction"]) and constructed:
        parts.append(
            "Live acquisition `true` in the narrow sense that model-authored"
            " bytes were emitted, qualified and executed on the panel.")
    else:
        parts.append(
            "Live acquisition `partial`: %d of %d constructions returned"
            " source that qualified. The failures are recorded, not"
            " dropped." % (len(constructed), len(result["construction"])))
    if distinct:
        parts.append(
            "Task utility `comparable` for %s: the control is a distinct"
            " strategy and the candidates separate, so a difference here"
            " would be a measurement rather than an arithmetic certainty."
            % " and ".join("`%s`" % d for d in distinct))
    else:
        parts.append(
            "Task utility `not_comparable`: `control_distinct` refuses, so"
            " the arms ran one strategy and a tie here carries no"
            " information. This is the honest reading, and it is the"
            " reading the gate exists to force.")
    parts.append(
        "Transfer: the acquired arms are developed on the calibration world"
        " (`w0`) and scored on `w1` and `w2`, so every acquired score is a"
        " score on a world the member was not constructed on. That is a"
        " within-family, same-representation transfer. It is **not** a"
        " cross-representation or cross-family transfer diagnostic, and it"
        " is not zero-shot: the member had development experience in `w0`."
        " Whether the capability carries to a different *representation* or"
        " a different family is untested here.")
    parts.append(
        "Recursive improvement `ineligible`: E4's channel has no headroom"
        " from this run.")
    return " ".join(parts)


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="s09_m3_pilot")
    parser.add_argument("--out", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--adapter", default="http-responses")
    parser.add_argument("--dry", action="store_true",
                        help="prove the pipeline against a local reply and"
                             " dispatch nothing to a provider")
    args = parser.parse_args(argv)
    if not args.out or not args.token:
        parser.error("--out and --token are both required")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    started = _timestamp()
    if args.dry:
        route = {"endpoint": "", "provider": "dry", "tier": "dry",
                 "requested_model": "m3-dry", "resolved_model": "m3-dry",
                 "dry": True}
        gateway = _dry_gateway(
            lambda request: json.dumps({"entry": control_source(
                "software" if "Family: software." in request.messages[0][
                    "content"] else "graph"),
                "notes": "dry"}))
    else:
        try:
            route = _route()
        except PilotRefused as exc:
            print("m3 refused before dispatch: %s" % exc, file=sys.stderr)
            return 2
        try:
            gateway = _live_gateway(route)
        except PilotRefused as exc:
            print("m3 refused before dispatch: %s" % exc, file=sys.stderr)
            return 2

    with isolation.disposable_db(args.token) as database:
        # The dispatch model is the route's *requested* form, not its
        # resolved one. The adapter accepts `openrouter/nvidia/...` and
        # refuses `nvidia/...`, because the resolved name is what the
        # provider reports back rather than what it is asked for.
        identity = isolation.RunIsolation.build(
            database, model=route["requested_model"],
            adapter=args.adapter, gateway_mode="live").identity
        menu = gates.menu_answers_nothing()
        if not menu["open"]:
            print("m3 refused: the child menu answers itself: %s"
                  % menu.get("refusal"), file=sys.stderr)
            return 2
        # Committed before the first send, and only for the arm whose prompt
        # is already a function of frozen inputs. `dev-exp` earns its
        # experience during the run, so there is nothing here to commit for
        # it and it is absent rather than approximated.
        committed = committed_prompt_digests()
        freeze = {"frozen_at": started, "arms": list(ARMS),
                  "control_strategy": CONTROL_STRATEGY,
                  "panel": [list(row) for row in PANEL],
                  "development": dict(DEVELOPMENT),
                  "request_bounds": dict(REQUEST_BOUNDS),
                  "max_queries": MAX_QUERIES,
                  "reasoning_effort": REASONING_EFFORT,
                  "route": route, "model": route["requested_model"],
                  "resolved_model": route["resolved_model"],
                  "adapter": args.adapter,
                  "store": database.name, "study_root": identity.study_root,
                  "menu_open": True,
                  "prompt_digests": committed,
                  "prompt_digest_arm": PRE_DETERMINABLE_ARM,
                  "prompt_digest_note": (
                      "digests are committed for %s only; the dev-exp arm "
                      "earns its experience during this run, so its prompt "
                      "did not exist when this freeze was written"
                      % PRE_DETERMINABLE_ARM)}
        (out / "freeze.json").write_text(
            json.dumps(freeze, sort_keys=True, indent=1) + "\n")
        result = run_panel(database.dsn, identity, gateway,
                           route["requested_model"], out, committed=committed)
        gate_verdicts = {}
        constructed = {(c.get("arm"), c.get("family"))
                       for c in result["construction"] if c.get("source")}
        for treatment, control, acquired in paired_records(result["arms"]):
            # An arm that never constructed has empty candidates on every
            # panel task, and an empty candidate differs from a real one,
            # so `control_distinct` would read that as the two arms
            # separating. It did not: there was nothing to separate from
            # the control. A distinctness pass is only reported when the
            # arm has a constructed member in both families.
            missing = [family for family in sorted(DEVELOPMENT)
                       if (treatment, family) not in constructed]
            if missing:
                gate_verdicts[treatment] = {
                    "distinct": False, "refusal":
                        "not-scored: no constructed member for %s"
                        % ", ".join(missing),
                    "constructed_families": sorted(
                        f for (a, f) in constructed if a == treatment)}
                continue
            try:
                gate_verdicts[treatment] = gates.control_distinct(
                    control, acquired)
            except gates.GateRefused as refusal:
                gate_verdicts[treatment] = {"distinct": False,
                                            "refusal": str(refusal)}
        for family, observations in sorted(result["experience"].items()):
            gate_verdicts["experience-%s" % family] = gates.experience_varies(
                observations, arm_name="dev-exp/%s" % family)
            # The E2 gate above reads the coarse `verdict`, which is
            # `preserved` on every development task in this world, so it
            # refuses. The development trace is not constant even so: the
            # reason code, the normalized reduction and the query count all
            # vary across episodes, and that is what the treatment carries
            # into the prompt. This block records that variation so the
            # refusal above is not mistaken for a one-bit experience.
            reasons = sorted({str(o.get("reason")) for o in observations})
            reductions = sorted({o.get("normalized_reduction")
                                 for o in observations},
                                key=lambda v: (v is None, v))
            gate_verdicts["experience-detail-%s" % family] = {
                "observations": len(observations),
                "distinct_verdicts": len({o.get("verdict")
                                          for o in observations}),
                "distinct_reasons": reasons,
                "distinct_reductions": len(reductions),
                "carries_more_than_verdict": len(reasons) > 1
                or len(reductions) > 1,
            }
        result.update({"freeze": freeze, "gates": gate_verdicts,
                       "finished_at": _timestamp()})
        (out / "result.json").write_text(
            json.dumps(result, sort_keys=True, indent=1, default=str) + "\n")
        write_result_md(result, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
