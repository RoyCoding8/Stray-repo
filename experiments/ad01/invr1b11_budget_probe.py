"""B11 — the served output budget of one free route, measured not assumed.

The cap sheet `reports/cap-sheets/b-live-cap.md` freezes every lane-B study at
`max_output_tokens: 2048` and records that the budget itself is UNRESOLVED: the
archived probe `reports/evidence/w1-e1-boolean-r3/route-probe.json` read a 502
that tracks the requested OUTPUT BUDGET rather than the prompt. Every campaign
then runs at 2048, so B12, B13 and B16 all inherit a number this lane measures.
Establishing it costs dispatches, which is why B11 is the first bounded item on
the sheet and why the sheet is written before the first effect.

## The design, and why it spends its sends on the question

The ladder is the cap sheet's own: one rung at 16, 64, 256, 1024, 2048 and
4096 output tokens (`b-live-cap.md`, the `B11` row of the dispatch caps). The
prompt is held FIXED at the archived campaign prompt — the exact string
`live.render_output_prompt(session.output_model_input(), [], 1)` from
`experiments/ad01/w1_e1_campaign_r3.py:_build_session("qual", 11)`, which
reproduces at 982 characters, the length the archived probe recorded. One
variable moves: `max_output_tokens`. A budget ladder against a moving prompt
would measure the product of the two, and the archived record is precisely a
case of that ambiguity. The prompt is pinned by digest so a reader can check
the same string was sent at every rung.

Six rungs, one send each, zero retries, which is the cap sheet's basis and not
this module's choice: a retry at a fixed budget re-measures the same rung and
answers nothing.

## Every send is a durable broker operation

Each rung is a `ModelRequest` handed to `_DurableBrokerOutput`, the same object
every other live path in `scripts/invl02_live.py` sends through and the shape
lane A1 gave the preflight and lane A7 gave the probe. That object calls
`broker.ensure_operation` then `broker.dispatch_operation` under a study-bound
allocation, so each send leaves an operation row, a reservation carrying
exposure, and one decided receipt. A send with no store is a model call that
leaves no row, no receipt and no exposure, which is the defect milestone A
exists to close, so the DSN and the allocation are both required and a
half-given pair is refused before the wire.

`LiveGuard` stays the outer object for the reason A7 gives: the route check and
the per-attempt evidence ledger are observations of one send, and what the
guard no longer owns is the send's admission. Its ceiling is read from the store
on every check, so the number that stops a seventh send is `COUNT(*) FROM
operations`, not an integer this process kept beside the broker's.

Automatic retries are set to `0` on the guard. `MAX_RETRIES` is 3 and a 502 is
retryable, so the default would spend up to four physical sends per rung and
silently break the six-send ceiling this lane is authorised against. The
campaign's own per-request bound is `deadline_ms: 300000` and
`reasoning_effort: low`, carried from the archived contrast cap sheet, and
`reasoning_effort` is left unset because the chat surface refuses a request
carrying one, so the receipt records no effort rather than a control the wire
never applied.

## Free routing only, and the refusal is the authority

The adapter is built with `expected_route` set to the frozen route and its
default `route_mode="free"`. `_free_signal` is the one derivation of "is this
route free" and both halves of the route contract call it; a request that would
route paid is refused pre-send rather than retried on another model. There is
no paid fallback anywhere in this module: there is no second model id to fall
back to, so a non-free route is a refusal and the ladder stops.

## Honest usage, and an honest stop

`billed` and `charge_units` are unknown on this route by measurement, not by
assumption — the route reports its price as `usage.cost`, which `_decode_usage`
deliberately does not read. `_usage_snapshot` writes `"unknown"` for a field the
body does not carry and this module never rewrites one to zero. A rung that
times out or is refused is recorded as the distinct thing it was, and the
stopping rule is the cap sheet's: a 502 or a timeout at the LOWEST rung is a
route fact no later study can spend its way out of, so the ladder stops there
and the remaining rungs are recorded as not-measured rather than spent.

A changed budget is a NEW freeze. Nothing measured here is comparable to
anything run at a different budget, and this module asserts no comparability.

## Where it runs

The frozen route is `http://localhost:4000/v1`, a Windows loopback listener, and
the durable store is a PostgreSQL socket inside WSL. The two are on different
hosts, so the durable path runs in one Windows process that reaches both: the
router on `127.0.0.1:4000` and the store on `127.0.0.1:5432` through the
`wslrelay` forwarder. `_wsl_password` reads the disposable role's password
inside the shell and returns a DSN; the password is never printed, logged or
written, and no key value is written anywhere in this module.
"""

from __future__ import annotations

import hashlib
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

import experiments.ad01.w1_e1_campaign_r3 as archived_campaign
from scripts import invl02_live as driver

SCHEMA = "invr1b11-budget-probe-v1"

#: The cap sheet's ladder, verbatim: one rung each at 16, 64, 256, 1024, 2048
#: and 4096 output tokens on the campaign prompt
#: (`reports/cap-sheets/b-live-cap.md`, the `B11` row of the dispatch caps).
#: Zero retries, so six rungs is six physical sends and the ceiling holds.
BUDGET_LADDER = (16, 64, 256, 1024, 2048, 4096)

#: The per-request bounds the cap sheet carries from the archived contrast, so
#: B and the archived E2 contrast are priced the same way.
DEADLINE_MS = 300_000

#: `reasoning_effort: low` is the campaign's bound, and `reasoning_effort` is
#: deliberately NOT set on the request: the chat surface refuses a request
#: carrying an effort, so no request in these campaigns sends one and the
#: receipt records no effort rather than a control the wire never applied.
REASONING_EFFORT_ON_THE_WIRE = "none-sent"

#: The study this ladder is charged to. A new root, because a changed budget
#: is a new freeze and must not be pooled with anything run at another one.
STUDY_ROOT = "invr1b11-budget"
ALLOCATION_ID = "invr1b11-budget-ladder"

#: The authorised ceiling, from the cap sheet's `B11` row. Read here so the
#: driver's own stopping rule and the report's are the same number.
AUTHORISED_SENDS = 6

ROUTE = dict(live.OUTPUT_ROUTE)

#: The units the broker charges one model request at, from
#: `exposure_schedule(MODEL_INFERENCE, ...)`. Recorded per rung so the ladder's
#: cost is derived from the store's own arithmetic rather than asserted.
def _units_for(prompt_characters: int, max_output_tokens: int) -> int:
    return prompt_characters // 4 + 1 + max_output_tokens


def campaign_prompt() -> str:
    """The archived campaign prompt, byte for byte.

    The archived probe built it as
    `live.render_output_prompt(session.output_model_input(), [], 1)` over
    `_build_session("qual", 11)`. Reproducing it offline gives 982 characters,
    which is the length `reports/evidence/w1-e1-boolean-r3/route-probe.json`
    recorded, so the string the archived 502 was measured against is the string
    this ladder varies one variable of.
    """
    _, session = archived_campaign._build_session("qual", 11)
    return live.render_output_prompt(session.output_model_input(), [], 1)


def _operation_id(rung: int) -> str:
    """One identity per rung, and no identity is reused.

    A second dispatch of one operation id finds a settled operation and returns
    the settled text without reaching the gateway, so identity is what stops a
    repeated send. Each rung is its own identity because each rung is its own
    measurement; a shared id would make rung 2 a replay of rung 1 and answer
    nothing.
    """
    return "invr1b11-budget-%d" % rung


def _usage_snapshot(usage) -> dict:
    """The shipped snapshot: unknown stays unknown.

    `_usage_snapshot` writes `"unknown"` for any field the response does not
    carry, which on this route is `charge_units` and `billed` — the route
    reports its price as `usage.cost`, which the adapter deliberately does not
    read. Nothing here rewrites a value, so an unmeasured field is not a
    measured zero.
    """
    return live._usage_snapshot(usage)


def _jsonable(value):
    """Store rows carry `datetime` and `UUID`, and the artifact has to be JSON.

    A row read from PostgreSQL is not yet a record a reader can reopen, so the
    two types the store hands back become their canonical text here and nothing
    else is touched. This is a serialisation step and not a judgement: no value
    is dropped, rounded or rewritten, so a receipt read back from the artifact
    is the receipt the store holds. `bool` is checked before `int` because
    `bool` is an `int` subclass and would otherwise become 0 or 1.
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
    """What the store holds about one rung, read from the store.

    Read after the dispatch rather than taken from the driver's return value,
    because the claim being evidenced is a statement about rows. `_jsonable`
    is applied here rather than at the write, so the store read stays a store
    read and the artifact still carries every field the row had.
    """
    from psycopg.rows import dict_row
    from settlement import db, store

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM operations WHERE id = %s", (operation_id,))
            operations = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT amount FROM reservations WHERE operation_id = %s",
                        (operation_id,))
            reservations = [dict(row) for row in cur.fetchall()]
        conn.commit()
    receipts = [dict(row) for row in (store.operation_receipts(dsn, operation_id) or [])]
    conflicts = list(store.operation_receipt_conflicts(dsn, operation_id) or [])
    return _jsonable({"operations": operations, "reservations": reservations,
                      "receipts": receipts, "receipt_conflicts": conflicts})


def _allocation(dsn: str) -> str:
    """A study-bound allocation, because `operation_receipts` demands one.

    Seeding through `authority.authorize_study` binds the allocation to the
    study root, and the store then stamps that root onto every operation
    admitted under it. A bare `seed_allocation` would leave the receipt read
    refusing an operation the dispatch had just settled.
    """
    from settlement import authority

    handle = authority.authorize_study(
        dsn, STUDY_ROOT,
        authorized=AUTHORISED_SENDS * _units_for(len(campaign_prompt()), 2048),
        allocation_id=ALLOCATION_ID,
        ceilings={"model_calls": AUTHORISED_SENDS})
    return handle.allocation_id


def _gateway() -> HttpGatewayAdapter:
    """The real adapter on the `chat` surface, with the frozen route.

    `chat`, not `responses`: a frozen route is refused pre-send on the
    responses surface, which publishes no provider field, and this adapter
    pins one. `expected_route` set means a response that does not attest the
    frozen route is refused rather than counted, and `route_mode` left at its
    `free` default means a request that would route paid never reaches the
    wire. The key is read from the environment variable the gateway config
    names and is never written, logged or echoed.
    """
    from settlement.config import Settings

    settings = Settings.from_env()
    return HttpGatewayAdapter.from_settings(
        settings, api="chat", expected_route=ROUTE)


def _spend(dsn: str) -> int:
    return driver._already_spent(dsn, ALLOCATION_ID)


def _one_rung(dsn: str, allocation_id: str, prompt: str, rung: int) -> dict:
    """One rung: one durable send, one store read, one recorded observation.

    The guard's ceiling is the store's count plus one, so a rung is admitted
    while the store holds fewer operations than it allows, and the store is
    re-read on every check rather than trusted from a seed. `automatic_retries`
    is zero because a retryable 502 retried three times would spend four
    physical sends on one rung and break the ceiling this lane is authorised
    against.
    """
    operation_id = _operation_id(rung)
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
        max_output_tokens=rung, deadline_ms=DEADLINE_MS,
        operation_id=operation_id)
    started = time.monotonic()
    outcome = {"max_output_tokens": rung, "operation_id": operation_id}
    try:
        response = guard.infer(request)
    except Exception as exc:
        outcome["kind"] = "exception"
        outcome["exception_class"] = type(exc).__name__
        outcome["exception_reason"] = str(exc)[:400]
    else:
        if isinstance(response, GatewayError):
            outcome["kind"] = str(response.kind)
            outcome["reason"] = str(response.message)[:400]
            outcome["retryable"] = response.retryable
            outcome["response_received"] = response.response_received
            outcome["response_status"] = response.response_status
            outcome["usage"] = _usage_snapshot(response.usage)
        else:
            outcome["kind"] = "text"
            outcome["text_characters"] = len(response.text or "")
            outcome["response_digest"] = hashlib.sha256(
                (response.text or "").encode("utf-8")).hexdigest()
            outcome["stop_reason"] = str(response.stop_reason)
            outcome["returned_route"] = dict(getattr(response, "model_meta", {}) or {})
            outcome["usage"] = _usage_snapshot(response.usage)
    outcome["elapsed_s"] = round(time.monotonic() - started, 2)
    outcome["guard"] = guard.guard_status()
    outcome["rows"] = _durable_row(dsn, operation_id)
    return outcome


def _catalog(dsn: str) -> dict:
    """A live read of the free catalog, through the sanctioned preflight.

    `preflight_route` is the same entry point the campaign preflight uses: it
    reads `GET /models` and hands the body to `validate_model_route`, which is
    the catalog half of the route contract and calls `_free_signal` on the
    entry. So a route the catalog cannot attest free is refused here, before a
    token is spent, rather than discovered on the wire. The model count and the
    free-id count are read from the same response the validator judged, so the
    presence claim and the verdict are one observation.
    """
    import httpx

    from settlement.gateway_http import reconcile_model_route

    adapter = _gateway()
    row: dict = {"pinned_id": ROUTE["requested_model"],
                 "requested_model_ends_free": ROUTE["requested_model"].endswith(":free")}
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(f"{adapter.endpoint}/models",
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
    row.update({
        "model_count": len(ids),
        "free_tier_ids": sum(1 for i in ids
                             if isinstance(i, str) and i.endswith(":free")),
        "pinned_present": ROUTE["requested_model"] in ids,
        "verdict": reconciled["result"]["verdict"],
        "reason": reconciled["result"]["reason"],
        "relevant_entries": reconciled["catalog"]["relevant_entries"],
    })
    return row


def ladder(dsn: str) -> dict:
    """The whole ladder, and the stopping rule that may end it early.

    The cap sheet's stopping condition is binding: a 502 or a timeout at the
    LOWEST rung is a route fact no later study can spend its way out of, so the
    ladder stops there and every higher rung is recorded as not measured. A
    stop is not an obstacle to route around; it is the result.
    """
    prompt = campaign_prompt()
    allocation_id = _allocation(dsn)
    rungs: list[dict] = []
    stopped_at = None
    reason = None
    for index, rung in enumerate(BUDGET_LADDER):
        if _spend(dsn) >= AUTHORISED_SENDS:
            stopped_at = rung
            reason = "the authorised send ceiling was reached"
            break
        observed = _one_rung(dsn, allocation_id, prompt, rung)
        rungs.append(observed)
        if index == 0 and _is_route_failure(observed):
            stopped_at = rung
            reason = ("the lowest rung failed at the route, which no later "
                      "rung and no later study can spend its way out of")
            break
    return {
        "schema": SCHEMA,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "study_root": STUDY_ROOT,
        "allocation_id": allocation_id,
        "route": dict(ROUTE),
        "tier": ROUTE["tier"],
        "provider": ROUTE["provider"],
        "prompt_characters": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_source": ("live.render_output_prompt(session.output_model_input(), "
                          "[], 1) over experiments.ad01.w1_e1_campaign_r3."
                          "_build_session('qual', 11)"),
        "deadline_ms": DEADLINE_MS,
        "reasoning_effort": REASONING_EFFORT_ON_THE_WIRE,
        "max_response_characters": live.OUTPUT_LIMITS["max_response_characters"],
        "ladder": list(BUDGET_LADDER),
        "authorised_sends": AUTHORISED_SENDS,
        "retries_per_rung": 0,
        "sends_used": _spend(dsn),
        "stopped_at_budget": stopped_at,
        "stop_reason": reason,
        "units_per_rung": {str(rung): _units_for(len(prompt), rung)
                           for rung in BUDGET_LADDER},
        "catalog": _catalog(dsn),
        "rungs": rungs,
    }


def _is_route_failure(observed: dict) -> bool:
    """Whether one rung died at the route rather than at the model.

    A 502, a timeout and a transport error are the same class here: the request
    never became an answer. A 200 is not a route failure. `protocol` is
    deliberately NOT here, because a protocol refusal is the free gate or the
    route contract working, and a later rung at the same budget would be
    refused identically — so it is recorded, not treated as a route death.
    """
    kind = str(observed.get("kind", ""))
    if kind == "text":
        return False
    receipts = observed.get("rows", {}).get("receipts") or []
    if any(row.get("outcome") == "success" for row in receipts):
        return False
    if kind in ("exception", "transport", "timeout", "rate_limit"):
        return True
    if observed.get("response_status") in (500, 502, 503, 504):
        return True
    return "timed out" in str(observed.get("exception_reason", "")) or \
        "timed out" in str(observed.get("reason", ""))


def _wsl_password() -> str:
    """The disposable role's password, read inside the shell and not printed.

    The store lives in a PostgreSQL socket inside WSL while the route lives on
    the Windows loopback, so the durable path runs in one Windows process and
    needs the role password. It is read from a mode-600 file into a DSN that
    is held in memory only; no credential value is written to any file, printed
    or logged by this module.
    """
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "-u", "ubuntu", "--", "bash", "-c",
         "cat /tmp/.b11pw"],
        capture_output=True, text=True)
    return result.stdout.strip()


def dsn() -> str:
    """The DSN for the lane's disposable store, held in memory only."""
    return "postgresql://b11probe:%s@127.0.0.1:5432/invl02_b11" % _wsl_password()


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    out = Path(args[args.index("--out") + 1] if "--out" in args
               else "reports/evidence/invr1b11-budget")
    # The two live-path gates, then the store. The grant check is the human
    # authority the cap sheet rests on and the model is the pinned id; neither
    # is a credential, and both are already in the environment.
    driver._require_grant()
    if os.environ.get("INVL02_LIVE_MODEL") != ROUTE["requested_model"]:
        raise ValueError("the pinned live model is not the B11 route model")
    result = ladder(dsn())
    out.mkdir(parents=True, exist_ok=True)
    (out / "budget-probe.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    print("b11 sends_used=%d/%d stopped_at=%s" % (
        result["sends_used"], AUTHORISED_SENDS, result["stopped_at_budget"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
