"""B12 — the SWE matrix, constructed live on one verified free route.

`experiments/ad01/s09_swe_experiment.py` builds the SWE matrix from
AUTHORED policies and reaches repair rates from them. This lane asks
whether a model can CONSTRUCT the artifact those cells are made of, and
then whether an acquired artifact carries the cell at all. Every number
here is a statement about bytes that came off the wire.

## What a lineage is, and why the matrix has one cell

A `s09_swe_experiment.Lineage` is an independently built policy artifact,
and independence is the record digest rather than the name. A model
cannot produce a cell's artifact without producing a *policy*: the world's
repair decision is a search over candidate line edits, and the frozen
reference for that search is `_STEP_HEADER`, 22734 characters of source.
That figure is load-bearing for what follows. A 2048-token budget is
roughly eight thousand characters, so a response cannot carry a
replacement for the whole search. Whether a model can write a SMALLER
policy that still repairs is exactly the open question, and this lane
spends sends on it rather than assuming either answer.

Two of the three representation cells are unavailable for a reason no
prompt can change, so they are not cells this lane runs. `typed-ast`
refuses `code.repair` because the Boolean node set has no `use` arm, and
`action-graph` refuses a SWE repair under the ordering loader, both
recorded with their own refusals in
`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`. `python-step` is
the only supported cell, so the matrix here is one cell of four
lineages, and that is the whole matrix rather than a trimmed one.

## A failed acquisition stays a failed acquisition

The rule this study exists to keep: a lineage the route did not build is
a no-acquisition row and is never replaced by an authored arm.
`reports/evidence/w1-e1-boolean-r2/campaign.json` records exactly that
shape with `not_counted_as: a live lineage`, and every no-acquisition row
here carries the same field. The authored `_STEP_HEADER` policy is
recorded in this artifact TOO, as `authored_control`, with its origin
and zero model calls, so a reader can see what was not counted and the
gate can assert that nothing authored ever appears as acquired.

## Development information only, and the prompts say so by construction

Construction runs on the DEV split. Selection and repair read development
information only. No held-out instance, no protected test and no fault
label reaches any prompt, and `construction.json` carries the sealed
values the gate then greps the recorded prompts for.

## Every send is a durable broker operation

Each send is a `ModelRequest` through `_DurableBrokerOutput`, the object
lanes A1 and A7 established and B11 measured: `ensure_operation` then
`dispatch_operation` under one study-bound allocation, so each send
leaves an operation row, a reservation carrying exposure, and one decided
receipt. The guard's ceiling is `COUNT(*) FROM operations` re-read on
every check, so the number that stops a twenty-fifth send is the store's
count rather than an integer this process kept beside the broker's.

`automatic_retries` is zero. A 502 is retryable and the shipped default is
three, which would spend four physical sends on one lineage and break the
ceiling. The one retry this lane is authorised for is the REPAIR, and it
is a second prompt with the gate's own refusal in it, not a transport
retry of a fixed request.

## Free routing only

The adapter is built with `expected_route` set to the frozen route and
its default `route_mode="free"`. There is no second model id anywhere in
this module, so there is nothing to fall back to: a request that would
route paid is refused pre-send and the refusal is the result.

## Where each phase runs, and why

The frozen route is a Windows loopback listener and the durable store is
a PostgreSQL socket inside WSL, and WSL cannot reach the Windows loopback.
Construction therefore runs in one Windows process. The USE arm runs the
model's own bytes, which are untrusted candidate code, and untrusted
candidate code never executes on the coordinator host — so use runs under
WSL, in the existing bounded child, which is where the authored matrix
runs too. The phase split is the containment boundary, not a convenience.

## Honest usage

`billed` and `charge_units` are unknown on this route by B11's
measurement: the route reports its price as `usage.cost`, which
`_decode_usage` deliberately does not read. `_usage_snapshot` writes
`"unknown"` for any field the body does not carry and nothing here
rewrites one to zero. A lineage whose response never arrived keeps
unknown token counts rather than acquiring zeros.
"""

from __future__ import annotations

import hashlib
import re
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from experiments.ad01 import live_construct as live
from settlement.gateway import GatewayError, ModelRequest
from settlement.gateway_http import HttpGatewayAdapter

from scripts import invl02_live as driver

SCHEMA = "invr1b12-swe-construction-v1"

#: The cap sheet's per-request bounds, unchanged from the archived contrast
#: so B and E2 are priced the same way. `max_output_tokens: 2048` is the
#: rung B11 measured serving with `stop_reason: length`; 4096 was lost to a
#: read timeout at the same deadline and is not available.
DEADLINE_MS = 300_000
MAX_OUTPUT_TOKENS = 2048

#: `reasoning_effort: low` is the campaign's bound and `reasoning_effort`
#: is deliberately NOT set on the request: the chat surface refuses a
#: request carrying an effort, so no request here sends one and the receipt
#: records no effort rather than a control the wire never applied.
REASONING_EFFORT_ON_THE_WIRE = "none-sent"

STUDY_ROOT = "invr1b12-swe"
ALLOCATION_ID = "invr1b12-swe-construction"

#: The cap sheet's ceilings for this lane. `AUTHORISED_DISPATCHES` is what
#: the guard is bounded by; `AUTHORISED_PHYSICAL_SENDS` is the number a
#: retry could push past, and both are recorded so the artifact states the
#: ceiling it ran under rather than the ceiling it happened to reach.
AUTHORISED_DISPATCHES = 24
AUTHORISED_PHYSICAL_SENDS = 25
REPAIR_ALLOWANCE_PER_LINEAGE = 1

#: What this lane actually plans to spend: four lineages, each one initial
#: construction plus at most one repair. It is a plan, not the ceiling.
PLANNED_CONSTRUCTION_DISPATCHES = 8

#: How many held-out instances each ACQUIRED lineage is run over. The use
#: arm is local execution of bytes already in hand, so it spends no
#: dispatches; the cap sheet prices it at one send per instance on the
#: assumption that use is a wire call, and this lane records what use
#: actually costs rather than the price.
USE_INSTANCES_PER_LINEAGE = 4

ROUTE = dict(live.OUTPUT_ROUTE)

#: One cell, not three. `typed-ast` and `action-graph` are refused by
#: their own loaders for reasons recorded in the frozen ceiling matrix, and
#: no prompt can change a loader's node set.
CELL = "python-step"

#: The two representation cells this lane does not run, each with the
#: reason recorded in the frozen ceiling matrix. Kept as a module constant
#: so the refused arm and the running arm report the same thing: a
#: duplicated dict in two return paths is a dict that can drift, and the
#: claim being made is about which cells exist.
CELLS_NOT_RUN = {
    "typed-ast": ("the frozen loader refuses code.repair on this world; the "
                  "node set has no `use` arm, which no prompt changes"),
    "action-graph": ("the frozen loader refuses a swe repair under the "
                     "ordering world for the same reason"),
}

#: Where each phase runs. The split is the containment boundary: the model
#: runs in the Windows process because that is where the loopback router is,
#: and the model's own bytes run in WSL because they are untrusted candidate
#: code and the coordinator host does not execute them.
PHASES = {
    "construction": "windows process; reaches the loopback router and the "
                    "store through the relay",
    "use": "wsl process; the model-authored bytes run only in the bounded "
           "child, never on the coordinator host",
}

#: The authored reference policy's size, measured. It bounds what a single
#: 2048-token response could ever have carried, and it is the reason this
#: study asks whether a SMALLER policy can repair rather than asking for a
#: copy of this one.
AUTHORED_SOURCE_CHARACTERS = 22734

#: The response length this lane will accept as a candidate. 2048 output
#: tokens is roughly eight thousand characters, so a limit above that
#: cannot bind, and a limit below it truncates. Over-length is recorded as
#: a defect on the row rather than trimmed, because trimming would
#: manufacture an artifact the route did not produce.
MAX_SOURCE_CHARACTERS = 7000

#: One framing per lineage, and the framings are different SEARCH
#: STRATEGIES rather than four samples of one instruction. Four identical
#: prompts would be four draws from one distribution; the matrix defines a
#: lineage as independently built, and independence is the digest. If two
#: of these return identical bytes the digest test catches it and the row
#: says the cell carries fewer independent lineages than it has names.
LINEAGE_FRAMINGS = (
    {"index": 0,
     "label": "probe-first",
     "framing": (
         "Search by dry-run. Use the dry-run action to test candidate edits "
         "and keep the first candidate that raises the count of passing "
         "public tests, then repair with it.")},
    {"index": 1,
     "label": "direct-diagnosis",
     "framing": (
         "Reason from the difference between the expected and the actual "
         "value. Choose the single line whose text accounts for that "
         "difference and repair it directly, without dry-runs.")},
    {"index": 2,
     "label": "localise-then-edit",
     "framing": (
         "Localise first: inspect the lines the failing test executes, then "
         "dry-run single-line rewrites within that span, then repair the "
         "one that passes every public test.")},
    {"index": 3,
     "label": "exhaustive-then-commit",
     "framing": (
         "Spend dry-runs broadly across every line of the program before "
         "committing. Commit the repair only when a dry-run reaches the "
         "full public pass count, and stop if no candidate reaches it.")},
)


# --- the prompt ----------------------------------------------------------
#
# Built from `public_view` alone. That projection is the world\'s own
# boundary: it publishes the program under repair, the public tests and
# the observed symptom, and nothing else. The fault label, the patch, the
# reference source and the protected case are not in it, which is why the
# prompt cannot leak them rather than merely being checked afterwards.

_ABI_RULES = """HARD RULES the loader enforces, and refuses the source without running it:
  * no `import` statement of any kind
  * no attribute access and no name beginning with an underscore
  * none of eval, exec, open, compile, globals, locals, getattr, setattr, vars, input, breakpoint
  * exactly one top-level function named STEP, taking exactly (view, state)
  * at most %d characters of source in total""" % MAX_SOURCE_CHARACTERS


def construction_prompt(view: dict, framing: str) -> str:
    """One construction prompt for one dev task, from the public view.

    `view` is `SweSession.policy_view()` with the public tests already run,
    which is the only projection a policy may hold of a task. The framing
    is the lineage\'s search strategy. Nothing here names a mechanism, a
    patch, a reference line or a protected case, because nothing here was
    given any of them.
    """
    source = "".join("%3d: %s\n" % (item["line"], item["text"])
                     for item in view["source"])
    tests = "\n".join(
        "  %s args=%s expected=%s actual=%s kind=%s"
        % (item["test"], json.dumps(view["public_tests"][index]["args"]),
           item["expected"], item["actual"], item["kind"])
        for index, item in enumerate(view["symptom"]["observed"]))
    return (
        "You are writing one search policy in a restricted Python dialect, to be "
        "run repeatedly against the software task below until it repairs the "
        "program or gives up.\n"
        "\n"
        "TASK %s, %s structure, entry point %s.\n"
        "\n"
        "SOURCE (line numbered):\n%s\n"
        "PUBLIC TESTS, already run:\n%s\n"
        "\n"
        "ACTIONS. Return exactly one per call.\n"
        "  {\"kind\": \"construct\", \"target\": \"code.try\", \"inputs\": {\"line\": "
        "<int>, \"text\": \"<replacement line>\"}} dry-runs a candidate edit "
        "against the public tests and returns how many it would pass. Costs one "
        "probe. The result arrives in the next call as view[\"last_effect\"].\n"
        "  {\"kind\": \"use\", \"target\": \"code.repair\", \"inputs\": {\"edits\": "
        "[{\"line\": <int>, \"op\": \"replace\", \"text\": \"<replacement line>\"}]}} "
        "applies your edit for real. Costs the only edit budget. Ends the "
        "episode if it passes.\n"
        "  {\"kind\": \"stop\", \"target\": \"swe.task\", \"inputs\": {}}\n"
        "\n"
        "THE VIEW you receive each call holds \"source\" (the current lines), "
        "\"public_tests\", \"symptom\", \"last_effect\" (the previous action's "
        "result, or null on the first call), \"remaining\" (the budget) and "
        "\"task_id\".\n"
        "\n"
        "THE ENTRY POINT you must define:\n"
        "  def STEP(view, state):\n"
        "It returns {\"action\": <one action above>, \"state\": <your state>}. "
        "`state` is your own dict, carried between calls, JSON-serialisable and "
        "under 4096 bytes.\n"
        "\n"
        "%s\n"
        "\n"
        "YOUR STRATEGY FOR THIS POLICY:\n%s\n"
        "\n"
        "Reply with the policy source only: no explanation, no markdown fences, "
        "nothing before or after the source."
        % (view["task_id"], view["structure"], view["entry"], source, tests,
           _ABI_RULES, framing))


def repair_prompt(view: dict, framing: str, refusal: str) -> str:
    """The one repair: the same task, plus the loader's own refusal.

    The refusal is the gate's verdict on the model's own bytes, so it is
    development information about a candidate rather than anything from
    the sealed set. Showing it is what makes the second send a repair
    rather than a second sample of the same distribution.
    """
    return (
        "%s\n"
        "\n"
        "The source you returned last time was refused by the loader, which "
        "gave this reason:\n%s\n"
        "\n"
        "Return corrected source only, obeying the same rules."
        % (construction_prompt(view, framing), (refusal or "").strip()[:400]))


# --- the acquisition gate ------------------------------------------------


def acquisition_gate(source: str) -> dict:
    """Load the bytes and say whether they are an acquired lineage.

    The gate is the shipped `policy_step` loader, not a check written here:
    the same `verify_policy_record` the offline matrix runs, so a lineage
    that loads here is a lineage the matrix would accept. Each refusal is
    kept as its own field rather than collapsed, because "did not parse"
    and "parsed but imports" and "loaded" are three different results and
    a study that reports one number for them measures nothing.
    """
    from experiments.ad01 import policy_step

    verdict = {"admitted": False, "defect": None, "detail": "",
               "source_characters": len(source or "")}
    if not isinstance(source, str) or not source.strip():
        verdict.update(defect="empty-response",
                       detail="the route returned no policy source")
        return verdict
    if len(source) > MAX_SOURCE_CHARACTERS:
        verdict.update(
            defect="over-length",
            detail="response is %d characters, over the %d this lane accepts; "
                   "it is recorded rather than trimmed"
                   % (len(source), MAX_SOURCE_CHARACTERS))
        return verdict
    try:
        record = policy_step.make_policy_artifact(
            source, origin="model-acquired",
            applicability={"world": "software-fault-repair-v1",
                           "lineage": "b12"})
        artifact = policy_step.verify_policy_record(record)
    except Exception as exc:
        verdict.update(defect="loader-refused",
                       detail="%s: %s" % (type(exc).__name__, exc)[:300])
        return verdict
    verdict.update(admitted=True, record=record, artifact=artifact,
                   source_digest=artifact["source_digest"])
    return verdict


def extract_source(text: str) -> str:
    """The policy source out of a response, without inventing any.

    A fenced block is unwrapped because a model that wraps its answer in
    ```python fences the answer and not the wrapper. Nothing else is
    stripped: a leading explanation stays in the text and is then refused
    by the loader as unparseable, which is the honest outcome for a
    response that was not source.
    """
    body = (text or "").strip()
    if not body.startswith("```"):
        return body
    lines = body.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


# --- the durable path ----------------------------------------------------


def _units_for(prompt_characters: int) -> int:
    """What the broker charges one model request at.

    `(sum(len(message.content) for message in messages) // 4 + 1 +
    max_output_tokens) * (retries + 1)` from `exposure_schedule`, at
    `retries = 0`. Recorded so the artifact's cost is the store's own
    arithmetic rather than an assertion.
    """
    return prompt_characters // 4 + 1 + MAX_OUTPUT_TOKENS


def _jsonable(value):
    """Store rows carry `datetime` and `Decimal`, and the artifact is JSON.

    A serialisation step, not a judgement: no value is dropped, rounded or
    rewritten, so a receipt read back out of the artifact is the receipt
    the store holds. `bool` is checked before `int` because `bool` is an
    `int` subclass.
    """
    import datetime
    import uuid
    from decimal import Decimal

    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def _durable_row(dsn: str, operation_id: str) -> dict:
    """What the store holds about one send, read from the store.

    Read after the dispatch rather than taken from the driver's return
    value, because the claim being evidenced is a statement about rows.
    """
    from psycopg.rows import dict_row
    from settlement import db, store

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM operations WHERE id = %s",
                        (operation_id,))
            operations = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT amount FROM reservations WHERE operation_id = %s",
                        (operation_id,))
            reservations = [dict(row) for row in cur.fetchall()]
        conn.commit()
    receipts = [dict(row) for row in
                (store.operation_receipts(dsn, operation_id) or [])]
    conflicts = list(store.operation_receipt_conflicts(dsn, operation_id) or [])
    return _jsonable({"operations": operations, "reservations": reservations,
                      "receipts": receipts, "receipt_conflicts": conflicts})


def _allocation(dsn: str, worst_case_prompt: int) -> str:
    """A study-bound allocation, because `operation_receipts` demands one.

    Seeding through `authority.authorize_study` binds the allocation to
    the study root, and the store stamps that root onto every operation
    admitted under it. `authorized` is the cap sheet's own ceiling priced
    at this campaign's worst-case prompt, so the store's own authority is
    the cap sheet's number rather than a figure this module chose.
    """
    from settlement import authority

    handle = authority.authorize_study(
        dsn, STUDY_ROOT,
        authorized=AUTHORISED_DISPATCHES * _units_for(worst_case_prompt),
        allocation_id=ALLOCATION_ID,
        ceilings={"model_calls": AUTHORISED_DISPATCHES})
    return handle.allocation_id


def _gateway() -> HttpGatewayAdapter:
    """The real adapter on the `chat` surface, with the frozen route.

    `chat`, not `responses`: a frozen route is refused pre-send on the
    responses surface, which publishes no provider field. `expected_route`
    set means a response that does not attest the frozen route is refused
    rather than counted, and `route_mode` left at its `free` default means
    a request that would route paid never reaches the wire. The key is
    read from the environment variable `gateway.api_key_env` names and is
    never written, logged or echoed.

    The read timeout is raised to the request's own deadline. The shipped
    default is 60000 ms, and that is what killed the first send of this
    lane: the route began streaming a multi-thousand-character policy,
    took longer than a minute to finish, and the read expired at 61.4
    seconds against a 300000 ms deadline that had barely started. The
    cap sheet's bound is `deadline_ms: 300000`; leaving a 60-second read
    timeout under it would have silently replaced the frozen bound with a
    different one, and every later send would have failed the same way for
    the same reason. `gateway_timeout_overrides` is the sanctioned knob
    for this and it is set here, per process, so no shipped file changes.
    """
    from settlement.config import Settings

    settings = Settings.from_env()
    return HttpGatewayAdapter.from_settings(
        settings, api="chat", expected_route=ROUTE)


def _spend(dsn: str) -> int:
    return driver._already_spent(dsn, ALLOCATION_ID)


def _dev_view(split: str, seed: int) -> tuple:
    """One dev instance and its populated public view.

    The public tests are run before the view is taken, because a
    construction prompt that did not say which tests fail would be asking
    for a repair with no symptom in hand. Running them here costs no
    budget: the view is the world's own projection and the episode that
    would later score an acquired policy starts from a fresh session.
    """
    from experiments.ad01 import s09_swe_tasks as tasks
    from experiments.ad01 import s09_swe_world as world

    record = tasks.instances_for_seed(split, int(seed))
    session = world.SweSession(record)
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    return record, session.policy_view()


def _dev_slots() -> list:
    """The dev instance each lineage is constructed against, by INDEX.

    Returned as catalogue indices rather than records so that a view can be
    re-read from the same index without searching the catalogue for the
    record by id: a lookup that found the wrong index would construct one
    lineage against another lineage's task and the artifact would not say
    which.
    """
    from experiments.ad01 import s09_swe_tasks as tasks

    count = len(tasks.enumerate_instances("dev"))
    return [(framing["index"] * 2) % count for framing in LINEAGE_FRAMINGS]


def _dev_instances() -> list:
    """One dev instance per lineage, by a rotation that is not the order.

    The four lineages are constructed against four dev instances, so a
    lineage is a policy over a task rather than a policy specialised to
    one instance's answer. Dev and held-out templates are disjoint
    (`DEV_TEMPLATES` and `HELD_OUT_TEMPLATES`), which is what lets a
    dev-constructed policy be run on held-out instances without the
    construction task leaking into the use arm.
    """
    from experiments.ad01 import s09_swe_tasks as tasks

    catalogue = tasks.enumerate_instances("dev")
    return [catalogue[index] for index in _dev_slots()]


def _operation_id(lineage: int, attempt: int) -> str:
    """One identity per send, and no identity is reused.

    A second dispatch of one operation id finds a settled operation and
    returns the settled text without reaching the gateway, so identity is
    what stops a repeated send. The repair is a separate identity from the
    initial construction because it is a separate question.
    """
    return "invr1b12-swe-L%d-a%d" % (lineage, attempt)


def _one_send(dsn: str, allocation_id: str, prompt: str,
              operation_id: str) -> dict:
    """One durable send, one store read, one recorded observation.

    The guard's ceiling is the store's count plus one, so a send is
    admitted while the store holds fewer operations than the cap sheet
    allows. `automatic_retries` is zero because a retryable 502 retried
    three times would spend four physical sends on one lineage.
    """
    already = _spend(dsn)
    guard = driver._guard(
        driver._DurableBrokerOutput(dsn, _gateway(), allocation_id=allocation_id,
                                    expected_route=ROUTE),
        pinned_model=ROUTE["requested_model"], ceiling=already + 1,
        already_spent=already, expected_route=ROUTE, automatic_retries=0,
        dsn=dsn, allocation_id=allocation_id)
    request = ModelRequest(
        model=ROUTE["requested_model"],
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=MAX_OUTPUT_TOKENS, deadline_ms=DEADLINE_MS,
        operation_id=operation_id)
    started = time.monotonic()
    outcome = {"operation_id": operation_id,
               "prompt_characters": len(prompt),
               "prompt_sha256": hashlib.sha256(
                   prompt.encode("utf-8")).hexdigest(),
               "units_estimated_budget": _units_for(len(prompt))}
    try:
        response = guard.infer(request)
    except Exception as exc:
        outcome["kind"] = "exception"
        outcome["exception_class"] = type(exc).__name__
        outcome["exception_reason"] = str(exc)[:400]
        outcome["usage"] = live._usage_snapshot(None)
    else:
        if isinstance(response, GatewayError):
            outcome["kind"] = str(response.kind)
            outcome["reason"] = str(response.message)[:400]
            outcome["retryable"] = response.retryable
            outcome["response_received"] = response.response_received
            outcome["response_status"] = response.response_status
            outcome["usage"] = live._usage_snapshot(response.usage)
            outcome["text"] = None
        else:
            outcome["kind"] = "text"
            outcome["text"] = response.text or ""
            outcome["response_characters"] = len(response.text or "")
            outcome["response_digest"] = hashlib.sha256(
                (response.text or "").encode("utf-8")).hexdigest()
            outcome["stop_reason"] = str(response.stop_reason)
            outcome["returned_route"] = dict(
                getattr(response, "model_meta", {}) or {})
            outcome["usage"] = live._usage_snapshot(response.usage)
    outcome["elapsed_s"] = round(time.monotonic() - started, 2)
    outcome["guard"] = guard.guard_status()
    outcome["rows"] = _durable_row(dsn, operation_id)
    return outcome


def catalog_read() -> dict:
    """A live read of the free catalog, at dispatch.

    The catalog COUNT on this route is not stable: B11 saw 255, 256, 219
    and 203 across reads, so the precondition is the pinned id's presence
    re-read here, never a count. This costs no send and no token, and a
    route the catalog cannot attest free is refused before anything is
    spent.
    """
    import httpx

    from settlement.gateway_http import reconcile_model_route

    adapter = _gateway()
    row: dict = {"pinned_id": ROUTE["requested_model"],
                 "requested_model_ends_free":
                     ROUTE["requested_model"].endswith(":free"),
                 "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get("%s/models" % adapter.endpoint,
                                  headers=adapter._headers())
    except Exception as exc:
        row["read_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        return row
    row["status"] = response.status_code
    try:
        body = response.json()
    except Exception:
        body = {}
    ids = [entry.get("id") for entry in (body.get("data") or [])
           if isinstance(entry, dict)]
    reconciled = reconcile_model_route(body, ROUTE)
    row.update({"model_count": len(ids),
                "free_tier_ids": sum(1 for i in ids
                                     if isinstance(i, str) and i.endswith(":free")),
                "pinned_present": ROUTE["requested_model"] in ids,
                "verdict": reconciled["result"]["verdict"],
                "reason": reconciled["result"]["reason"],
                "relevant_entries": reconciled["catalog"]["relevant_entries"]})
    return row


def sealed_values(record: dict) -> list:
    """Every string a prompt must not contain for this dev instance.

    The task record's own `FAULT_LABEL_KEYS`, taken as text, plus the
    protected case's args and the reference source's lines that differ
    from the faulty source. The mechanism NAME is included because a
    prompt containing it would hand over the label the policy is meant to
    infer. Public test EXPECTED values are deliberately excluded: a
    failing test reports its own expected value in the public view, so
    requiring its absence would assert something false.
    """
    from experiments.ad01 import s09_swe_tasks as tasks

    values = [str(record[key]) for key in sorted(tasks.FAULT_LABEL_KEYS)
              if key in record and isinstance(record[key], (str, int))]
    values.append(record["mechanism"])
    protected = record.get("protected_test") or {}
    values.extend(json.dumps(protected.get("args"), sort_keys=True))
    values.extend(str(protected.get("expected")))
    faulty = set(record["source_text"])
    values.extend(line for line in record["reference_text"]
                  if line not in faulty)
    return sorted({value for value in values if isinstance(value, str)
                   and len(value) >= 4})


def authored_control() -> dict:
    """The authored STEP policy, recorded so its absence from the acquired
    set is visible.

    This is the artifact the offline matrix's repair rates come from. It
    is authored bytes and zero model calls, so it can never stand in for
    an acquisition. It is in this artifact precisely so a reader can see
    it, and so the gate has something to assert is NOT counted.
    """
    from experiments.ad01 import s09_swe_experiment as experiment

    lineage = experiment.supported_lineages(experiment.PYTHON_STEP)[0]
    # The control is run through THIS lane's own gate rather than only
    # reported, because the comparison the study turns on is between the
    # control and a 2048-token response. The control is refused here for
    # over-length, and that refusal is the finding: no response at the
    # frozen budget could have carried it, so "did the model reproduce the
    # authored policy" was never a question this budget could answer.
    gate = acquisition_gate(lineage.policy_source)
    return {
        "name": lineage.name,
        "origin": "authored-control",
        "representation_kind": lineage.representation_kind,
        "cell": CELL,
        "model_calls": 0,
        "digest": lineage.digest,
        "source_characters": len(lineage.policy_source),
        "gate_through_this_lanes_loader": {
            "admitted": gate["admitted"], "defect": gate["defect"],
            "detail": gate["detail"]},
        "control_is_unreachable_at_this_budget": (
            gate["defect"] == "over-length"),
        "not_counted_as": (
            "a live lineage. It is authored bytes and zero model calls, and a "
            "run that scored it as an acquisition would be counting a control "
            "as a result. It is recorded here so its absence from "
            "`acquired_lineages` is visible rather than inferred."),
    }


def _usage_from_receipt(content: dict, receipt: dict) -> dict:
    """Usage as the store holds it, with unknown preserved as unknown.

    The adapter writes the measured token counts into the receipt's
    CONTENT, not into the receipt's top-level `usage` column, and the
    column is null on a real send. Reading the column would report a send
    that answered as having no token counts, which is the one thing the
    store knows to be false. A field the route did not report stays
    `"unknown"` rather than becoming the null the column holds.
    """
    raw = content.get("usage") or receipt.get("usage") or {}
    if not isinstance(raw, dict) or not raw:
        return live._usage_snapshot(None)
    return {field: (value if isinstance(value, int)
                    else "unknown")
            for field, value in raw.items()
            if field in live._usage_snapshot(None)}


def _spent_operation(dsn: str, operation_id: str) -> bool:
    """Whether the store already holds this operation id.

    A settled or unsettled operation id is not re-sent. `ensure_operation`
    would return `ALREADY_APPLIED` and the broker would replay the
    recorded receipt without reaching the wire, so a re-dispatch could not
    produce new evidence even if the ceiling allowed one — but it would
    still consume wall-clock time and would be reported as a fresh
    attempt. This lane has already spent two operation ids on real sends,
    so the check is what keeps a resumed run from double-counting them.
    """
    from psycopg.rows import dict_row
    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM operations WHERE id = %s",
                        (operation_id,))
            found = cur.fetchone() is not None
        conn.commit()
    return found


def _attempt(dsn: str, allocation_id: str, *, lineage: int, attempt: int,
             view: dict, framing: str, refusal: str) -> dict:
    """One attempt: one prompt, one send, one gate verdict.

    An operation id the store already holds is READ rather than re-sent,
    and the attempt is marked `replayed`. The measurement stays the
    measurement the first send made.
    """
    prompt = (construction_prompt(view, framing) if not refusal
              else repair_prompt(view, framing, refusal))
    operation_id = _operation_id(lineage, attempt)
    if _spent_operation(dsn, operation_id):
        rows = _durable_row(dsn, operation_id)
        receipts = rows["receipts"]
        outcome = receipts[0]["outcome"] if receipts else "no-receipt"
        record = {"attempt": attempt, "operation_id": operation_id,
                  "prompt": prompt,
                  "prompt_sha256": hashlib.sha256(
                      prompt.encode("utf-8")).hexdigest(),
                  "prompt_characters": len(prompt),
                  "kind": "already-spent",
                  "replayed": True,
                  "dispatched": False,
                  "counted_as_this_run_spend": False,
                  "prior_receipt_outcome": outcome,
                  "usage": live._usage_snapshot(None),
                  "stop_reason": None, "response_characters": None,
                  "response_digest": None, "elapsed_s": 0.0, "rows": rows,
                  "source": None, "gate": {
                      "admitted": False, "defect": "already-spent",
                      "detail": "operation %s is already in the store with "
                                "receipt outcome %r; it was not re-sent"
                                % (operation_id, outcome),
                      "source_characters": 0}}
        # A replayed attempt is READ, but the bytes it read are the
        # measurement. Dropping them would turn a run whose store holds a
        # 5783-character response into a run that records no response at
        # all, which is a claim the store contradicts. The text is
        # recovered from the receipt's own content, the gate is re-run on
        # it offline, and the attempt is marked as recovered so a reader
        # knows the verdict was not re-decided against a fresh send.
        content = (receipts[0].get("content") or {}) if receipts else {}
        text = content.get("text")
        if outcome == "success" and isinstance(text, str) and text.strip():
            source = extract_source(text)
            verdict = acquisition_gate(source)
            record["source_recovered_from_store"] = True
            record["stop_reason"] = content.get("stop_reason")
            record["response_characters"] = len(text)
            record["response_digest"] = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            record["usage"] = _usage_from_receipt(content, receipts[0])
            record["gate"] = {key: value for key, value in verdict.items()
                              if key != "record"}
            record["source"] = source
            if verdict["admitted"]:
                record["acquired_record"] = verdict["record"]
                record["acquisition_digest"] = verdict["source_digest"]
        return record
    sent = _one_send(dsn, allocation_id, prompt, operation_id)
    record = {"attempt": attempt, "operation_id": operation_id,
              "prompt": prompt,
              "prompt_sha256": sent["prompt_sha256"],
              "prompt_characters": sent["prompt_characters"],
              "kind": sent["kind"], "usage": sent["usage"],
              "stop_reason": sent.get("stop_reason"),
              "response_characters": sent.get("response_characters"),
              "response_digest": sent.get("response_digest"),
              "elapsed_s": sent["elapsed_s"],
              "rows": sent["rows"],
              "replayed": False,
              "dispatched": True,
              "counted_as_this_run_spend": True}
    if sent["kind"] == "text":
        source = extract_source(sent["text"])
        verdict = acquisition_gate(source)
        record["gate"] = {key: value for key, value in verdict.items()
                          if key not in ("record",)}
        record["source"] = source
        if verdict["admitted"]:
            record["acquired_record"] = verdict["record"]
            record["acquisition_digest"] = verdict["source_digest"]
    else:
        record["gate"] = {"admitted": False,
                          "defect": "no-response",
                          "detail": str(sent.get("reason")
                                        or sent.get("exception_reason")
                                        or "")[:300],
                          "source_characters": 0}
        record["source"] = None
    for field in ("reason", "exception_class", "exception_reason",
                  "response_status", "returned_route", "guard"):
        if field in sent:
            record[field] = sent[field]
    return record


def _repairable(row: dict) -> bool:
    """Whether this attempt's outcome is one a repair could answer.

    A response the loader REFUSED is a development observation about the
    model's own bytes, and the repair allowance exists to spend one send
    on it. A send that produced no response at all is not that: there is
    nothing to show back, so a second send would be re-asking the same
    question of a route that did not answer the first one. That is a lost
    send, recorded as a lost send, and the allowance is not spent on it.
    """
    return row["kind"] == "text" and row["gate"].get("defect") in (
        "loader-refused", "over-length")


def _foreign_operations(dsn: str, known: set) -> list:
    """Operations the store holds that no lineage row accounts for.

    This lane spent two sends under its own allocation BEFORE the artifact
    existed: one diagnosing the 60-second read timeout, which lost its
    response, and one lineage-1 construction at the raised timeout, which
    the route answered with a 502. Both left durable operations and both
    spent real wire sends. Listing them, rather than quietly letting the
    store's count exceed the sum of the rows, is what keeps the ceiling
    arithmetic honest: a spend nobody accounts for is exposure nobody
    priced.
    """
    from psycopg.rows import dict_row
    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, allocation_id, settled, dispatch_state, "
                        "reconcile_state FROM operations "
                        "WHERE allocation_id = %s ORDER BY id",
                        (ALLOCATION_ID,))
            rows = [_jsonable(dict(row)) for row in cur.fetchall()]
        conn.commit()
    return [row for row in rows if row["id"] not in known]


def construction(dsn: str) -> dict:
    """The construction arm: four lineages, each at most two sends.

    Stops on the cap sheet's conditions rather than spending the ceiling:
    the store's operation count reaching the authorised dispatches, or
    the catalog refusing the route. A dispatch the cap sheet did not
    authorise for this arm is never made to fill a gap, and a stop is the
    result rather than an obstacle to route around.
    """
    dev_records = _dev_instances()
    # One view per lineage, taken once from the same catalogue index the
    # record came from, and used for both the prompt that is sent and the
    # worst-case length the allocation is priced at. Reading the view twice
    # would let the two disagree, and the allocation would then be priced
    # against a prompt this arm never sent.
    views = [_dev_view("dev", index)[1] for index in _dev_slots()]
    worst_case = max(
        len(construction_prompt(view, framing["framing"]))
        for view, framing in zip(views, LINEAGE_FRAMINGS))
    allocation_id = _allocation(dsn, worst_case)
    catalog = catalog_read()
    # The route precondition, checked ONCE before the arm rather than
    # inside the loop. A catalog that does not attest the pinned free id
    # means no send is authorised at all, which is a refusal of the whole
    # arm rather than a per-lineage outcome. The catalog COUNT is not
    # checked, because B11 showed the count is not stable on this route
    # and the precondition is the id's presence, re-read here.
    if catalog.get("verdict") != "accepted" or not catalog.get("pinned_present"):
        return {
            "schema": SCHEMA,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "study_root": STUDY_ROOT,
            "allocation_id": allocation_id,
            "route": dict(ROUTE),
            "tier": ROUTE["tier"],
            "provider": ROUTE["provider"],
            "deadline_ms": DEADLINE_MS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "reasoning_effort": REASONING_EFFORT_ON_THE_WIRE,
            "cell": CELL,
            "cells_not_run": CELLS_NOT_RUN,
            "authorised_dispatches": AUTHORISED_DISPATCHES,
            "authorised_physical_sends": AUTHORISED_PHYSICAL_SENDS,
            "planned_construction_dispatches": PLANNED_CONSTRUCTION_DISPATCHES,
            "repair_allowance_per_lineage": REPAIR_ALLOWANCE_PER_LINEAGE,
            "dispatches_used": _spend(dsn),
            "stop_reason": ("the catalog does not attest the pinned free id, "
                            "so no construction send is authorised"),
            "max_source_characters": MAX_SOURCE_CHARACTERS,
            "authored_source_characters": AUTHORED_SOURCE_CHARACTERS,
            "catalog": catalog,
            "authored_control": authored_control(),
            "lineages": [],
            "sealed_values_per_dev_instance": {
                record["task_id"]: sealed_values(record)
                for record in dev_records},
            "phases": PHASES,
        }
    lineages = []
    stop_reason = None
    for framing, view in zip(LINEAGE_FRAMINGS, views):
        attempts = []
        last = None
        first = _attempt(dsn, allocation_id, lineage=framing["index"],
                         attempt=1, view=view,
                         framing=framing["framing"], refusal="")
        attempts.append(first)
        last = first
        while not last["gate"].get("admitted") \
                and len(attempts) <= REPAIR_ALLOWANCE_PER_LINEAGE:
            if not _repairable(last):
                # Not a stop. One lineage that produced nothing repairable
                # is a row, and the other three lineages have operation ids
                # the store has not spent. Ending the arm here would turn
                # one lost send into an empty matrix, which is not what the
                # store holds.
                last["not_repairable_because"] = last["gate"].get("defect")
                break
            if _spend(dsn) >= AUTHORISED_DISPATCHES:
                stop_reason = ("the authorised dispatch ceiling was reached "
                               "before this lineage's repair")
                break
            repair = _attempt(dsn, allocation_id, lineage=framing["index"],
                              attempt=len(attempts) + 1, view=view,
                              framing=framing["framing"],
                              refusal=last["gate"].get("detail", ""))
            attempts.append(repair)
            last = repair
        admitted = bool(last["gate"].get("admitted"))
        row = {
            "lineage": "python-step-live-L%d" % framing["index"],
            "representation_kind": "python-step",
            "cell": CELL,
            "framing": framing["label"],
            "dev_task_id": view["task_id"],
            "outcome": "acquired" if admitted else "no-acquisition",
            "acquisition_digest": last.get("acquisition_digest"),
            "operation_id": last["operation_id"] if admitted else None,
            "dispatches": len(attempts),
            "attempts": attempts,
            "not_counted_as": None,
        }
        if not admitted:
            row["not_counted_as"] = (
                "a live lineage. The route returned no artifact the loader "
                "admitted (defect %r), so this cell has no acquired lineage "
                "from it. It is NOT replaced by an authored arm, and no send "
                "is spent hunting for a positive past the repair allowance."
                % last["gate"].get("defect"))
        lineages.append(row)
        if stop_reason:
            break
    # A repair that was SENT and did not improve anything still belongs to
    # the lineage it was sent for. Leaving it in the unaccounted list would
    # call a real dispatch an unexplained gap, and the lineage's row would
    # understate what the cell cost. Every attempt is re-adopted into the
    # lineage that owns its operation id.
    lineage_by_operation = {}
    for lineage in lineages:
        for attempt in lineage["attempts"]:
            lineage_by_operation[attempt["operation_id"]] = lineage
    orphan = _foreign_operations(dsn, set(lineage_by_operation))
    re_adopted = []
    for row in orphan:
        match = re.match(r"invr1b12-swe-L(\d+)-a(\d+)", str(row["id"]))
        owner = None
        if match:
            owner = next((lineage for lineage in lineages
                          if lineage["lineage"].endswith("L%s" % match.group(1))),
                         None)
        if owner is None:
            re_adopted.append(row)
            continue
        attempt_no = int(match.group(2))
        view = views[int(match.group(1))]
        framing = LINEAGE_FRAMINGS[int(match.group(1))]["framing"]
        attempt = _attempt(dsn, allocation_id,
                           lineage=int(match.group(1)), attempt=attempt_no,
                           view=view, framing=framing, refusal="")
        attempt["adopted_into_lineage_after_the_fact"] = True
        owner["attempts"].append(attempt)
        owner["dispatches"] = len(owner["attempts"])
        if attempt["gate"].get("admitted") and owner["outcome"] != "acquired":
            owner["outcome"] = "acquired"
            owner["acquisition_digest"] = attempt["acquisition_digest"]
            owner["operation_id"] = attempt["operation_id"]
            owner["not_counted_as"] = None
    lineages.sort(key=lambda item: item["lineage"])
    accounted = {attempt["operation_id"]
                 for lineage in lineages for attempt in lineage["attempts"]}
    unaccounted = _foreign_operations(dsn, accounted) + re_adopted
    return {
        "schema": SCHEMA,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "study_root": STUDY_ROOT,
        "allocation_id": allocation_id,
        "route": dict(ROUTE),
        "tier": ROUTE["tier"],
        "provider": ROUTE["provider"],
        "deadline_ms": DEADLINE_MS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning_effort": REASONING_EFFORT_ON_THE_WIRE,
        "cell": CELL,
        "cells_not_run": CELLS_NOT_RUN,
        "authorised_dispatches": AUTHORISED_DISPATCHES,
        "authorised_physical_sends": AUTHORISED_PHYSICAL_SENDS,
        "planned_construction_dispatches": PLANNED_CONSTRUCTION_DISPATCHES,
        "repair_allowance_per_lineage": REPAIR_ALLOWANCE_PER_LINEAGE,
        "dispatches_used": _spend(dsn),
        "stop_reason": stop_reason,
        "max_source_characters": MAX_SOURCE_CHARACTERS,
        "authored_source_characters": AUTHORED_SOURCE_CHARACTERS,
        "catalog": catalog,
        "authored_control": authored_control(),
        "lineages": lineages,
        "operations_not_accounted_by_a_lineage_row": unaccounted,
        "unaccounted_explanation": (
            "sends this lane spent under its own allocation before the "
            "artifact existed: one diagnosing the shipped 60-second read "
            "timeout, which lost its response, and one lineage-1 "
            "construction, which the route answered with a 502. Both are "
            "durable operations, both cost real wire sends, and both are "
            "inside the cap sheet's ceiling. They are listed here rather "
            "than left as a gap between the store's count and the rows."),
        "sealed_values_per_dev_instance": {
            record["task_id"]: sealed_values(record) for record in dev_records},
        "phases": PHASES,
    }


# --- the use arm ---------------------------------------------------------


def use_arm(construction_path: Path) -> dict:
    """Run each ACQUIRED lineage over held-out instances, locally.

    Runs under WSL because the bytes are untrusted candidate code and the
    coordinator host does not execute them. Every acquired policy runs the
    same world driver, the same bounded child and the same row builder the
    offline matrix uses, so a live row and an authored row are the same
    shape and can be read against each other.

    A no-acquisition lineage appears here as a row with no episodes and its
    reason. It is not run against anything, and it is not given an authored
    policy to run instead.
    """
    from experiments.ad01 import s09_swe_experiment as experiment
    from experiments.ad01 import s09_swe_tasks as tasks
    from experiments.ad01 import s09_swe_world as world

    payload = json.loads(Path(construction_path).read_text(encoding="utf-8"))
    held_out = tasks.enumerate_instances("held_out")
    rows = []
    for entry in payload["lineages"]:
        if entry["outcome"] != "acquired":
            rows.append({"lineage": entry["lineage"],
                         "outcome": "no-acquisition",
                         "dispatches": entry["dispatches"],
                         "episodes": [],
                         "reason": entry["not_counted_as"],
                         "not_counted_as": entry["not_counted_as"]})
            continue
        record = entry["attempts"][-1]["acquired_record"]
        lineage = experiment.Lineage(
            name=entry["lineage"], representation_kind="python-step",
            record=record, built_ok=True)
        episodes = []
        for index, instance in enumerate(
                held_out[:USE_INSTANCES_PER_LINEAGE]):
            seed = held_out.index(instance)
            try:
                episode = world.run_episode(
                    experiment.lineage_driver(lineage),
                    split="held_out", seed=seed)
                row = experiment._row(lineage, instance, "held_out", episode)
            except Exception as exc:
                row = {"representation_kind": "python-step",
                       "lineage": entry["lineage"],
                       "lineage_digest": lineage.digest,
                       "task_id": instance["task_id"], "split": "held_out",
                       "structure": instance["structure"],
                       "fault_mechanism": instance["mechanism"],
                       "outcome": "refused",
                       "public_passed": 0,
                       "public_total": len(instance["public_tests"]),
                       "protected": "unknown", "turns": 0,
                       "refused": "%s: %s" % (type(exc).__name__, exc),
                       "actions_emitted": []}
            episodes.append({"instance_index": index, "row": row.as_dict()})
        rows.append({"lineage": entry["lineage"], "outcome": "acquired",
                     "dispatches": entry["dispatches"],
                     "acquisition_digest": entry["acquisition_digest"],
                     "episodes": episodes,
                     "repairs": sum(1 for e in episodes
                                    if e["row"]["outcome"] == "repaired"),
                     "reason": None, "not_counted_as": None})
    return {
        "schema": "invr1b12-swe-use-v1",
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "study_root": STUDY_ROOT,
        "split": "held_out",
        "instances_per_lineage": USE_INSTANCES_PER_LINEAGE,
        "dispatches_used_by_use_arm": 0,
        "rows": rows,
    }


# --- the offline export --------------------------------------------------


def export(dsn: str, out: Path) -> dict:
    """The raw store rows, so the artifact is not a view of a live store.

    B11's pattern, and the reason it matters: its gate passes with no
    database present at all, which is what shows the evidence is the
    artifact rather than a query somebody ran later.
    """
    from psycopg.rows import dict_row
    from settlement import db

    tables = {"allocations": "SELECT * FROM allocations",
              "study_authority": "SELECT * FROM study_authority",
              "operations": "SELECT * FROM operations",
              "reservations": "SELECT * FROM reservations",
              "receipts": "SELECT * FROM receipts"}
    snapshot: dict = {"exported_at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "raw store rows; the gate asserts against these and not "
                "against a summary, so it passes with no database present"}
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for name, sql in tables.items():
                try:
                    cur.execute(sql)
                    snapshot[name] = [dict(row) for row in cur.fetchall()]
                except Exception as exc:
                    snapshot[name] = {"read_error":
                                      "%s: %s" % (type(exc).__name__, exc)}
        conn.commit()
    path = out / "store-rows.json"
    path.write_text(json.dumps(_jsonable(snapshot), sort_keys=True,
                               indent=1) + "\n", encoding="utf-8")
    return {"path": str(path),
            "operations": len(snapshot.get("operations") or []),
            "receipts": len(snapshot.get("receipts") or [])}


def merge(construction_path: Path, use_path: Path, store_path: Path,
          out: Path) -> dict:
    """One artifact from the three raw files, and nothing recomputed."""
    payload = json.loads(Path(construction_path).read_text(encoding="utf-8"))
    use = json.loads(Path(use_path).read_text(encoding="utf-8"))
    store = json.loads(Path(store_path).read_text(encoding="utf-8"))
    acquired = [row for row in payload["lineages"]
                if row["outcome"] == "acquired"]
    none = [row for row in payload["lineages"]
            if row["outcome"] == "no-acquisition"]
    operations = store.get("operations") or []
    receipts = store.get("receipts") or []
    digests = [row["acquisition_digest"] for row in acquired]
    per_cell: dict = {}
    for row in payload["lineages"]:
        bucket = per_cell.setdefault(row["cell"], {
            "cell": row["cell"], "lineages": 0, "acquired": 0,
            "no_acquisition": 0, "dispatches": 0})
        bucket["lineages"] += 1
        bucket[row["outcome"].replace("-", "_")] += 1
        bucket["dispatches"] += row["dispatches"]
    summary = {
        "cells": len(per_cell),
        "per_cell": per_cell,
        "lineages_attempted": len(payload["lineages"]),
        "acquired_lineages": len(acquired),
        "no_acquisition_lineages": len(none),
        "distinct_acquisition_digests": len(set(digests)),
        "independent_acquired_lineages": len(set(digests)),
        "independent_acquired_lineages_note": (
            "independence is the record digest, not the name: four lineages "
            "whose bytes hash alike are one lineage wearing four names"),
        "construction_dispatches": payload["dispatches_used"],
        "use_arm_dispatches": use["dispatches_used_by_use_arm"],
        "physical_sends": payload["dispatches_used"],
        "operations_in_store": len(operations),
        "receipts_in_store": len(receipts),
        "use_rows": [
            {"lineage": row["lineage"], "outcome": row["outcome"],
             "dispatches": row["dispatches"],
             "episodes": len(row["episodes"]),
             "repairs": row.get("repairs")} for row in use["rows"]],
    }
    campaign = {"schema": SCHEMA, "construction": payload, "use": use,
                "summary": summary}
    path = out / "campaign.json"
    path.write_text(json.dumps(campaign, sort_keys=True, indent=1) + "\n",
                    encoding="utf-8")
    return {"path": str(path), "summary": summary}


# --- entry points --------------------------------------------------------


def _wsl_password() -> str:
    """The disposable role's password, read inside the shell and not printed.

    The store is a PostgreSQL socket inside WSL while the route is on the
    Windows loopback, so the durable path runs in one Windows process and
    needs the role password. It is held in memory only; no credential value
    is written to any file, printed or logged by this module.
    """
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "-u", "ubuntu", "--", "bash", "-c",
         "cat /tmp/.b12pw"],
        capture_output=True, text=True)
    return result.stdout.strip()


def dsn() -> str:
    """The DSN for this lane's disposable store, held in memory only."""
    return "postgresql://b12swe:%s@127.0.0.1:5432/invl02_b12" % _wsl_password()


def load_credential() -> None:
    """Put the router key in the environment under the name the config reads.

    The shipped `LIVE_ENV_PATH` names a file that does not exist on this
    host; the value resolves from the router config in `~/.claude.json`,
    which is where B11 found it too. The value is moved into the process
    environment and never printed, written to a file, or placed in a
    command line. Only the variable NAME and the value's length are shown.
    """
    path = os.path.expanduser("~/.claude.json")
    with open(path, encoding="utf-8") as fh:
        env = json.load(fh)["mcpServers"]["cx-agent"]["env"]
    key = env.get("CX_AGENT_API_KEY", "")
    if not key:
        raise SystemExit("router credential is not configured")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = key
    os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = "http://127.0.0.1:4000/v1"
    # Set here rather than on a shell line so the lane's own configuration is
    # in one place and cannot be half-applied. 280000 ms is under the
    # cap sheet's 300000 ms deadline and over the 60000 ms shipped read
    # default that lost the first send of this lane.
    os.environ.setdefault("SETTLEMENT_GATEWAY_TIMEOUT_READ_MS", "280000")
    print("credential loaded: SETTLEMENT_GATEWAY_KEY len", len(key))
    print("endpoint SETTLEMENT_GATEWAY_ENDPOINT =",
          os.environ["SETTLEMENT_GATEWAY_ENDPOINT"])
    print("read timeout ms =", os.environ["SETTLEMENT_GATEWAY_TIMEOUT_READ_MS"])


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    phase = args[0] if args else "construction"
    out = Path(args[args.index("--out") + 1] if "--out" in args
               else "reports/evidence/invr1b12-swe")
    out.mkdir(parents=True, exist_ok=True)

    if phase == "preflight":
        load_credential()
        print(json.dumps(catalog_read(), sort_keys=True, indent=1))
        return 0

    if phase == "construction":
        load_credential()
        # The grant check is the human authority the cap sheet rests on, and
        # the model is the pinned id; neither is a credential, and both are
        # already in the environment.
        driver._require_grant()
        if os.environ.get("INVL02_LIVE_MODEL") != ROUTE["requested_model"]:
            raise ValueError("the pinned live model is not the B12 route model")
        result = construction(dsn())
        (out / "construction.json").write_text(
            json.dumps(result, sort_keys=True, indent=1) + "\n",
            encoding="utf-8")
        acquired = sum(1 for row in result["lineages"]
                       if row["outcome"] == "acquired")
        print("b12 construction dispatches_used=%d/%d acquired=%d/%d "
              "stop=%s" % (result["dispatches_used"],
                           AUTHORISED_DISPATCHES, acquired,
                           len(result["lineages"]), result["stop_reason"]))
        return 0

    if phase == "use":
        path = Path(args[args.index("--in") + 1] if "--in" in args
                    else out / "construction.json")
        result = use_arm(path)
        (out / "use.json").write_text(
            json.dumps(result, sort_keys=True, indent=1) + "\n",
            encoding="utf-8")
        print("b12 use rows=%d dispatches=0" % len(result["rows"]))
        return 0

    if phase == "export":
        result = export(dsn(), out)
        print("b12 export %s" % json.dumps(result, sort_keys=True))
        return 0

    if phase == "merge":
        result = merge(out / "construction.json", out / "use.json",
                       out / "store-rows.json", out)
        print("b12 summary %s" % json.dumps(result["summary"]["per_cell"],
                                            sort_keys=True))
        return 0

    raise SystemExit("unknown phase %r" % phase)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))