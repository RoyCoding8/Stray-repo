"""S1 operator interface (UI-1..5, BOOT-4 narrowing): FastAPI over durable records.

Every GET renders from committed rows and never mutates domain state, so the
UI stays fully usable with the model gateway down: a banner reports models
unavailable while inspection and mechanical recovery stay enabled. Commands
are versioned and idempotent; generated content is rendered as inert escaped
text; there is no trusted shell endpoint and no credential is ever displayed.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from psycopg.rows import dict_row
from starlette.middleware.base import BaseHTTPMiddleware

from . import broker, steward, store
from .common import Command, CommandResult, ConflictPayload, ResultCode, SettlementError

HERE = Path(__file__).resolve().parent.parent.parent


OUTCOME_UNKNOWN_NOTE = ("external outcome unknown: cancellation stops new work only;"
                        " uncertain charges are retained and late receipts are still admitted"
                        " through reconciliation")


def operator_token(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    configured = os.environ.get("OPERATOR_TOKEN", "")
    if configured:
        return configured
    import secrets

    generated = secrets.token_hex(16)
    print(f"settlement-operator: generated one-process OPERATOR_TOKEN={generated}"
          " (set OPERATOR_TOKEN to fix it)", flush=True)
    return generated


def _rows(dsn: str, sql: str, args: tuple = ()) -> list[dict]:
    with store.db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, args)
            rows = [{k: (dict(v) if isinstance(v, dict) else v) for k, v in dict(r).items()}
                    for r in cur.fetchall()]
            conn.commit()
            return rows


EPISODE_SUFFIXES = ("-dev", "-panel-B", "-panel-C", "-transfer-B", "-transfer-C")


def overview_data(dsn: str) -> dict[str, Any]:
    with store.db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(*) AS n FROM attempts")
            total = int(cur.fetchone()["n"])
            cur.execute("SELECT id, investigation_id, lifecycle FROM attempts ORDER BY updated_at DESC, id LIMIT 50")
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, dispatch_state, reconcile_state FROM operations"
                        " WHERE dispatch_state NOT IN ('observed', 'reconciled', 'closed') ORDER BY id LIMIT 50")
            unresolved = [dict(r) for r in cur.fetchall()]
    return {"attempt_total": total, "attempts": attempts, "unresolved_operations": unresolved,
            "budgets": steward.read_budgets(dsn)}


def investigation_data(dsn: str, iid: str) -> dict[str, Any] | None:
    inv = _rows(dsn, "SELECT * FROM investigations WHERE id = %s", (iid,))
    if not inv:
        return None
    return {"investigation": inv[0],
            "attempts": _rows(dsn, "SELECT * FROM attempts WHERE investigation_id = %s ORDER BY id LIMIT 200", (iid,)),
            "operations": _rows(dsn, "SELECT o.* FROM operations o JOIN attempts a ON a.id = o.attempt_id"
                                " WHERE a.investigation_id = %s ORDER BY o.id LIMIT 500", (iid,))}


def genomes_data(dsn: str) -> list[dict]:
    return _rows(dsn, "SELECT digest, parent, harness, origin, created_at FROM rsi_genomes"
                     " ORDER BY created_at DESC, digest LIMIT 100")


def episodes_data(dsn: str) -> list[dict]:
    # Keep anchor content out of the operator page and any scraped evidence bundle.
    return _rows(dsn, "SELECT e.operation_id, e.genome, e.task, e.status, e.tokens, e.seconds,"
                     " t.name, t.split, v.status AS verdict FROM rsi_episodes e"
                     " LEFT JOIN rsi_tasks t ON t.digest = e.task"
                     " LEFT JOIN rsi_verdicts v ON v.episode = e.operation_id"
                     " AND v.evaluator_version = t.evaluator_version"
                     " ORDER BY e.created_at DESC, e.operation_id LIMIT 100")


def operation_data(dsn: str, op_id: str) -> dict[str, Any] | None:
    row = broker.read_operation(dsn, op_id)
    if row is None:
        return None
    intents = [i for i in store.scan_outbox(dsn, 200)
               if i["workflow_identity"] == f"dispatch:{op_id}" and not i["delivered"]]
    return {"operation": row, "pending_effects": intents,
            "next_decision": broker._next_for(row)}


class _Auth(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static/") or request.url.path == "/login":
            return await call_next(request)
        if request.headers.get("x-operator-token") not in (self.token,) \
                and request.cookies.get("operator_token") != self.token:
            if request.headers.get("accept", "").find("text/html") >= 0:
                return HTMLResponse(
                    '<html><body><a href="/login">operator login required</a></body></html>',
                    status_code=401)
            return JSONResponse({"detail": "operator authentication required"}, status_code=401)
        return await call_next(request)


_COMMANDS = ("admit", "pause", "resume", "cancel", "amend-allocation", "inspect")


def run_command(dsn: str, action: str, form: dict[str, Any],
                launchers: dict[str, Any] | None = None,
                gateway: Any | None = None) -> dict[str, Any]:
    request_id = str(form.get("request_id") or
                     f"ui-{action}-{os.urandom(4).hex()}")
    expected = form.get("expected_revision")
    cmd = Command(request_id=request_id,
                  expected_revision=int(expected) if expected not in (None, "") else None,
                  payload={k: v for k, v in form.items()
                           if k not in ("request_id", "expected_revision") and v != ""})
    try:
        if action == "admit":
            result = steward.admit_commitment(dsn, cmd)
        elif action == "pause":
            result = store.suspend_attempt(dsn, cmd)
        elif action == "resume":
            result = store.resume_attempt(dsn, cmd)
        elif action == "cancel":
            result = broker.request_cancel(dsn, cmd.payload.get("operation_id", ""),
                                           launchers or {}, gateway)
        elif action == "amend-allocation":
            result = steward.amend_allocation(dsn, cmd)
        elif action == "inspect":
            row = broker.read_operation(dsn, cmd.payload.get("operation_id", ""))
            if row is None:
                result = CommandResult(code=ResultCode.INVALID_INPUT, request_id=request_id,
                                       detail="unknown operation", data={})
            else:
                result = CommandResult(code=ResultCode.APPLIED, request_id=request_id,
                                       detail=broker._next_for(row), data=row)
        else:
            result = CommandResult(code=ResultCode.INVALID_INPUT, request_id=request_id,
                                   detail=f"unknown command {action}", data={})
    except ConflictPayload as exc:
        return {"action": action, "outcome": "refused", "code": "conflict-payload",
                "detail": str(exc), "request_id": request_id}
    outcome = "refused" if result.code in (
        ResultCode.STALE_REVISION, ResultCode.UNAUTHORIZED, ResultCode.INSUFFICIENT_RESOURCES,
        ResultCode.INCOMPATIBLE_VERSION, ResultCode.MISSING_EVIDENCE,
        ResultCode.INVALID_INPUT, ResultCode.UNAVAILABLE_DEPENDENCY) else "accepted"
    note = OUTCOME_UNKNOWN_NOTE if action == "cancel" and outcome == "accepted" else ""
    return {"action": action, "outcome": outcome, "code": result.code.value,
            "detail": result.detail, "data": result.data, "request_id": request_id, "note": note}


def create_app(dsn: str, gateway: Any | None = None, token: str | None = None,
               launchers: dict[str, Any] | None = None) -> FastAPI:
    key = operator_token(token)
    app = FastAPI(title="settlement-operator")
    app.add_middleware(_Auth, token=key)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    env = Environment(loader=FileSystemLoader(str(HERE / "templates")),
                      autoescape=select_autoescape(["html", "xml"]))
    state = {"dsn": dsn, "gateway": gateway, "launchers": launchers or {}}

    def _render(name: str, context: dict, status: int = 200,
                poll_url: str = "/") -> HTMLResponse:
        context = dict(context, gateway_down=gateway is None, poll_url=poll_url)
        return HTMLResponse(env.get_template(name).render(**context), status_code=status)

    @app.get("/", response_class=HTMLResponse)
    def overview():
        return _render("overview.html", {"view": overview_data(state["dsn"])}, poll_url="/")

    @app.get("/investigations/{iid}", response_class=HTMLResponse)
    def investigation(iid: str):
        data = investigation_data(state["dsn"], iid)
        if data is None:
            return _render("error.html", {"message": f"unknown investigation {iid}"}, status=404)
        return _render("investigation.html", {"view": data, "iid": iid},
                       poll_url=f"/investigations/{iid}")

    @app.get("/genomes", response_class=HTMLResponse)
    def genomes():
        return _render("records.html", {"title": "genome lineage", "rows": genomes_data(dsn)}, poll_url="/genomes")

    @app.get("/episodes", response_class=HTMLResponse)
    def episodes():
        return _render("records.html", {"title": "episodes and verdicts", "rows": episodes_data(dsn)}, poll_url="/episodes")

    @app.get("/operations/{op_id}", response_class=HTMLResponse)
    def inspect_operation(op_id: str):
        data = operation_data(state["dsn"], op_id)
        if data is None:
            return _render("error.html", {"message": f"unknown operation {op_id}"}, status=404)
        return _render("operation.html", {"view": data, "op_id": op_id},
                       poll_url=f"/operations/{op_id}")

    @app.get("/login", response_class=HTMLResponse)
    def login_form():
        return HTMLResponse(
            "<html><body><h1>operator login</h1>"
            '<form method="post" action="/login">'
            '<input type="password" name="token" autocomplete="off"/>'
            '<button type="submit">sign in</button></form></body></html>')

    @app.post("/login")
    async def login(request: Request):
        from fastapi.responses import RedirectResponse

        raw = (await request.body()).decode("utf-8", "replace")
        submitted = dict(parse_qsl(raw, keep_blank_values=True)).get("token", "")
        if not secrets.compare_digest(submitted, key):
            return HTMLResponse("<html><body>wrong token</body></html>", status_code=403)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("operator_token", key, httponly=True, samesite="lax", path="/")
        return response

    @app.post("/commands/{action}", response_class=HTMLResponse)
    async def command(action: str, request: Request):
        raw = (await request.body()).decode("utf-8", "replace")
        form = dict(parse_qsl(raw, keep_blank_values=True))
        if action not in _COMMANDS:
            return _render("result.html",
                           {"result": {"action": action, "outcome": "refused",
                                       "code": "invalid_input", "detail": "unknown command",
                                       "request_id": "", "note": "", "data": {}}},
                           status=400)
        return _render("result.html",
                       {"result": run_command(state["dsn"], action, form, state["launchers"],
                                                  state["gateway"])})

    return app


def main() -> None:
    import uvicorn

    dsn = os.environ.get("SETTLEMENT_DSN", "")
    if not dsn:
        raise RuntimeError("SETTLEMENT_DSN is not configured")
    uvicorn.run(create_app(dsn), host="127.0.0.1", port=8101)
