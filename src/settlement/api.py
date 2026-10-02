"""S1 operator interface (UI-1..5, BOOT-4 narrowing): FastAPI over durable records.

Every GET renders from committed rows and never mutates domain state, so the
UI stays fully usable with the model gateway down: a banner reports models
unavailable while inspection and mechanical recovery stay enabled. Commands
are versioned and idempotent; generated content is rendered as inert escaped
text; there is no trusted shell endpoint and no credential is ever displayed.
"""

from __future__ import annotations

import html
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

from . import agenda, broker, steward, store
from .common import Command, CommandResult, ConflictPayload, ResultCode

HERE = Path(__file__).resolve().parent.parent.parent
T5_PROBES = ("trials", "trial_assignments", "trial_results", "candidates", "releases",
             "quarantine", "capability_versions", "capability_releases")
T4_TABLES = ("artifact_versions", "claims", "derivations", "observations", "context_views",
             "continuation_docs")
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


def table_present(dsn: str, name: str) -> bool:
    with store.db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.tables"
                        " WHERE table_schema = 'public' AND table_name = %s", (name,))
            found = cur.fetchone() is not None
            conn.commit()
            return found


def t5_state(dsn: str) -> dict[str, Any]:
    present = [t for t in T5_PROBES if table_present(dsn, t)]
    return {"installed": bool(present), "tables": present}


def _rows(dsn: str, sql: str, args: tuple = ()) -> list[dict]:
    with store.db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, args)
            rows = [{k: (dict(v) if isinstance(v, dict) else v) for k, v in dict(r).items()}
                    for r in cur.fetchall()]
            conn.commit()
            return rows


def overview_data(dsn: str) -> dict[str, Any]:
    snap = agenda.agenda_snapshot(dsn)
    nexts = {a["id"]: agenda.next_decision_for(dsn, a["id"]) for a in snap["attempts"]}
    control = store.get_control(dsn)
    return {"obligations": snap["obligations"], "attempts": snap["attempts"],
            "unresolved_operations": snap["unresolved_operations"], "capacity": snap["capacity"],
            "due": snap["due"], "next_decisions": nexts,
            "authority_version": control.get("authority_version"),
            "evidence_epoch": control.get("evidence_epoch")}


def investigation_data(dsn: str, iid: str) -> dict[str, Any] | None:
    inv = _rows(dsn, "SELECT * FROM investigations WHERE id = %s", (iid,))
    if not inv:
        return None
    attempts = _rows(dsn, "SELECT * FROM attempts WHERE investigation_id = %s ORDER BY id", (iid,))
    ops = _rows(dsn, "SELECT o.* FROM operations o JOIN attempts a ON a.id = o.attempt_id"
                     " WHERE a.investigation_id = %s ORDER BY o.id", (iid,))
    obs = _rows(dsn, "SELECT ob.* FROM attempt_observations ob JOIN attempts a ON a.id = ob.attempt_id"
                     " WHERE a.investigation_id = %s ORDER BY ob.id", (iid,))
    revs = _rows(dsn, "SELECT * FROM investigation_revisions WHERE investigation_id = %s"
                      " ORDER BY revision", (iid,))
    waits = {a["id"]: agenda.next_decision_for(dsn, a["id"]) for a in attempts}
    data: dict[str, Any] = {"investigation": inv[0], "attempts": attempts, "operations": ops,
                            "observations": obs, "revisions": revs, "wait_reasons": waits,
                            "diagram": dependency_svg(inv[0], attempts, ops)}
    if table_present(dsn, "evidence_relations"):
        data["relations"] = _rows(dsn, "SELECT * FROM evidence_relations ORDER BY id LIMIT 100")
    if table_present(dsn, "derivations"):
        data["derivations"] = _rows(dsn, "SELECT * FROM derivations ORDER BY id LIMIT 100")
    return data


def dependency_svg(inv: dict, attempts: list[dict], ops: list[dict]) -> str:
    nodes = [f'<rect x="10" y="10" width="180" height="34" rx="4"/>'
             f'<text x="20" y="32">{html.escape(str(inv.get("id", "")))}</text>']
    by_attempt: dict[str, list[dict]] = {}
    for op in ops:
        by_attempt.setdefault(str(op.get("attempt_id") or ""), []).append(op)
    y = 70
    edges = []
    for att in attempts:
        aid = html.escape(str(att["id"]))
        nodes.append(f'<rect x="250" y="{y}" width="220" height="34" rx="4"/>'
                     f'<text x="260" y="{y + 22}">{aid} [{html.escape(str(att["lifecycle"]))}]</text>')
        edges.append(f'<line x1="190" y1="27" x2="250" y2="{y + 17}"/>')
        for op in by_attempt.get(str(att["id"]), []):
            oid = html.escape(str(op["id"]))
            nodes.append(f'<rect x="520" y="{y}" width="240" height="34" rx="4"/>'
                         f'<text x="530" y="{y + 22}">{oid} [{html.escape(str(op["dispatch_state"]))}]</text>')
            edges.append(f'<line x1="470" y1="{y + 17}" x2="520" y2="{y + 17}"/>')
            y += 44
        y += 44
    height = max(y + 10, 120)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="780" height="{height}" role="img">'
            + "".join(edges) + "".join(nodes) + "</svg>")


def capabilities_data(dsn: str) -> dict[str, Any]:
    data: dict[str, Any] = {"t5": t5_state(dsn), "artifacts": [], "derivations": []}
    if table_present(dsn, "artifact_versions"):
        data["artifacts"] = _rows(dsn, "SELECT digest, manifest, format, version, size,"
                                       " availability FROM artifact_versions ORDER BY digest LIMIT 100")
    if table_present(dsn, "derivations"):
        data["derivations"] = _rows(dsn, "SELECT * FROM derivations ORDER BY id LIMIT 100")
    return data


def trials_data(dsn: str) -> dict[str, Any]:
    state = t5_state(dsn)
    return {"t5": state, "rows": [], "pending": not state["installed"]}


def learning_data(dsn: str) -> dict[str, Any]:
    state = t5_state(dsn)
    hypotheses = _rows(dsn, "SELECT * FROM derivations ORDER BY id LIMIT 100") \
        if table_present(dsn, "derivations") else []
    return {"t5": state, "pending": not state["installed"], "hypotheses": hypotheses,
            "comparisons": []}


def evidence_data(dsn: str) -> dict[str, Any]:
    data: dict[str, Any] = {"claims": [], "observations": [], "t4": False}
    if table_present(dsn, "claims"):
        data["t4"] = True
        data["claims"] = _rows(dsn, "SELECT * FROM claims ORDER BY id LIMIT 100")
        data["observations"] = _rows(dsn, "SELECT * FROM observations ORDER BY receipt_id LIMIT 100")
    return data


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


_COMMANDS = ("admit", "pause", "resume", "cancel", "quarantine", "amend-allocation",
             "inspect", "repair")


def run_command(dsn: str, action: str, form: dict[str, Any],
                launchers: dict[str, Any] | None = None) -> dict[str, Any]:
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
                                           launchers or {})
        elif action == "quarantine":
            result = steward.quarantine_subject(dsn, cmd)
        elif action == "amend-allocation":
            result = steward.amend_allocation(dsn, cmd)
        elif action == "repair":
            report = agenda.repair_scan(dsn, launchers or {})
            result = CommandResult(code=ResultCode.APPLIED, request_id=request_id,
                                   detail=report.next_decision,
                                   data={"repaired": report.repaired,
                                         "dispatched": report.dispatched,
                                         "deferred_model": report.deferred_model})
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

    def _render(name: str, context: dict, status: int = 200) -> HTMLResponse:
        context = dict(context, gateway_down=gateway is None)
        return HTMLResponse(env.get_template(name).render(**context), status_code=status)

    @app.get("/", response_class=HTMLResponse)
    def overview():
        return _render("overview.html", {"view": overview_data(state["dsn"])})

    @app.get("/investigations/{iid}", response_class=HTMLResponse)
    def investigation(iid: str):
        data = investigation_data(state["dsn"], iid)
        if data is None:
            return _render("error.html", {"message": f"unknown investigation {iid}"}, status=404)
        return _render("investigation.html", {"view": data, "iid": iid})

    @app.get("/capabilities", response_class=HTMLResponse)
    def capabilities():
        return _render("capabilities.html", {"view": capabilities_data(state["dsn"])})

    @app.get("/trials", response_class=HTMLResponse)
    def trials():
        return _render("trials.html", {"view": trials_data(state["dsn"])})

    @app.get("/learning", response_class=HTMLResponse)
    def learning():
        return _render("learning.html", {"view": learning_data(state["dsn"])})

    @app.get("/evidence", response_class=HTMLResponse)
    def evidence():
        return _render("evidence.html", {"view": evidence_data(state["dsn"])})

    @app.get("/operations/{op_id}", response_class=HTMLResponse)
    def inspect_operation(op_id: str):
        data = operation_data(state["dsn"], op_id)
        if data is None:
            return _render("error.html", {"message": f"unknown operation {op_id}"}, status=404)
        return _render("operation.html", {"view": data, "op_id": op_id})

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
                       {"result": run_command(state["dsn"], action, form, state["launchers"])})

    return app


def main() -> None:
    import uvicorn

    dsn = os.environ.get("SETTLEMENT_DSN", "")
    if not dsn:
        raise RuntimeError("SETTLEMENT_DSN is not configured")
    uvicorn.run(create_app(dsn), host="127.0.0.1", port=8101)
