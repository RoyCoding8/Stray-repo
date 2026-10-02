"""Lane L: learning acquisition for coordination-procedure/1 (EC02 design 6-7).

Experience packets are built from REAL development episodes on W dev tasks
run through the R controller. Construction is broker-routed (real receipts)
with a hard four-call ceiling. The stage gate is parse/stage/check/select
with a none path. Frozen packages flow through the capability registry.

LIVE-GRANT NOTE: no live model calls exist in this environment (no
TEAM01_LIVE_API_KEY; unauthenticated inference is rejected). Construction
is routed through the broker against the FakeGatewayAdapter and every such
run is labeled DOUBLED. The 4 live construction calls + G2 acquisition
await the grant; see preflight_live() and acquire().
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from settlement import broker, capabilities, db, store, team
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import FakeGatewayAdapter
from settlement.representation import canonical_bytes, sha_hex

from . import freeze as freeze_mod
from . import oracle
from . import packet
from . import packet
from . import preflight
from .controller import (
    EpisodeConfig,
    build_experience_packet,
    list_probe_observations,
    list_step_receipts,
    load_frozen_package,
    publish_package_version,
    run_episode,
    seed_episode,
    stage_package,
)
from .policy_exec import STEP_RECEIPT_KIND

PACKET_VERSION = "coord02-experience/1"
BUDGET_VERSION = "coord02-construction-budget/1"
REQUEST_VERSION = "coord02-construction-request/1"
SELECTOR_VERSION = "coord02-dev-select/1"
DEV_PROTOCOL = "coord02-dev-v1"

MAX_LINEAGES = 2
MAX_CONSTRUCTION_CALLS = preflight.CONSTRUCTION_CALLS

CONSTRUCTION_CONTENT_BUDGET_BYTES = 128 * 1024
CONSTRUCTION_MAX_OUTPUT_TOKENS = 65536
CONSTRUCTION_REASONING_EFFORT = "low"

CONSTRUCTION_MODEL = "doubled-fake-gateway"
LIVE_MODEL = "configured-live-model"


def live_model() -> str:
    return os.environ.get("TEAM01_LIVE_MODEL", LIVE_MODEL)


def live_reasoning_effort() -> str:
    effort = os.environ.get("EC02_REASONING_EFFORT",
                            CONSTRUCTION_REASONING_EFFORT)
    if effort not in ("low", "medium", "high"):
        raise ValueError("EC02_REASONING_EFFORT must be low|medium|high")
    return effort
CONSTRUCTION_LABEL = "DOUBLED"
LIVE_LABEL = "LIVE"
DOUBLED_NOTE = ("DOUBLED: fake-gateway stand-in; no live grant in this "
                "environment (no TEAM01_LIVE_API_KEY)")

DEV_SELECTION_TASKS = ("c02-t01", "c02-t06", "c02-t11",
                       "c02-t16", "c02-t21", "c02-t26")

ORDERING = ("valid-execution", "solved-tasks", "model-tokens",
            "sandbox-ops", "canonical-bytes")


class ConstructionBudgetExhausted(SettlementError):
    def __init__(self, detail: str = "") -> None:
        super().__init__("construction budget exhausted: four calls maximum"
                         + (": " + detail if detail else ""))


class ConstructionRequestTooLarge(SettlementError):
    def __init__(self, detail: str) -> None:
        super().__init__("construction request exceeds content budget: "
                         f"{detail}")


class EvidenceDBProtected(SettlementError):
    def __init__(self, detail: str) -> None:
        super().__init__("destructive setup refused on evidence DB: "
                         f"{detail}")


_DOUBLE_MODEL_HINTS = ("doubl", "recording", "simulat", "fake")


def _is_live_gateway(gateway: Any | None) -> bool:
    if gateway is None or isinstance(gateway, FakeGatewayAdapter):
        return False
    if str(getattr(gateway, "label", "") or ""):
        return False
    model = str(getattr(gateway, "model", "") or "")
    if model and any(h in model.lower() for h in _DOUBLE_MODEL_HINTS):
        return False
    return True


def _grant_version(dsn: str) -> int | None:
    try:
        return int(store.get_control(dsn)["authority_version"])
    except Exception:
        return None


def provenance(gateway: Any | None = None) -> dict:
    live_grant = bool(preflight_live()["live_grant"])
    live = gateway is not None \
        and not isinstance(gateway, FakeGatewayAdapter) and live_grant
    if live:
        return {"label": LIVE_LABEL, "doubled": False, "live": True,
                "model": live_model()}
    return {"label": CONSTRUCTION_LABEL, "doubled": True, "live": False,
            "model": CONSTRUCTION_MODEL}


def _cmd(payload: Any = None) -> Command:
    return Command(request_id=f"coord02-L-{uuid.uuid4().hex}",
                   payload=payload or {})


def preflight_live() -> dict:
    key = os.environ.get("TEAM01_LIVE_API_KEY", "")
    if key:
        return {"live_grant": True, "reason": ""}
    return {"live_grant": False,
            "reason": "no TEAM01_LIVE_API_KEY: 4 live construction calls + "
                      "G2 acquisition blocked; doubled path only"}


def _protected_markers() -> tuple[str, ...]:
    return ("protected", "reference patch", "oracle.py", "checker.py",
            "protected_cases", "expected output")


def _scan_protected(value: Any, hits: list) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _scan_protected(key, hits)
            _scan_protected(item, hits)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _scan_protected(item, hits)
    elif isinstance(value, str):
        lowered = value.lower()
        for marker in _protected_markers():
            if marker in lowered:
                hits.append(marker)


def assert_no_protected_feedback(value: Any, where: str = "repair") -> None:
    hits: list = []
    _scan_protected(value, hits)
    if hits:
        raise SettlementError(
            f"{where} carries protected-feedback markers {sorted(set(hits))}")


def _count_operations(dsn: str, like: str) -> int:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE %s",
                        (like,))
            count = int(cur.fetchone()[0])
            conn.commit()
            return count


def _episode_costs(dsn: str, *, run_id: str, task_id: str) -> dict:
    observations = list_probe_observations(dsn, run_id, task_id)
    return {"model_calls": 0, "model_input_tokens": 0,
            "model_output_tokens": 0,
            "source_invocations": len(observations),
            "sandbox_operations": _count_operations(dsn, f"coord:{run_id}:%"),
            "sandbox_cpu_ms": None, "sandbox_wall_ms": None,
            "elapsed_ms": None, "liabilities": [],
            "unknown": ["sandbox_cpu_ms", "sandbox_wall_ms", "elapsed_ms"]}


def _executed_operations(dsn: str, *, run_id: str, task_id: str) -> list[dict]:
    out: list[dict] = []
    for receipt in list_step_receipts(dsn, run_id, task_id):
        out.append({"kind": STEP_RECEIPT_KIND,
                    "operation_id": receipt.get("_operation_id", ""),
                    "decision_id": receipt.get("decision_id", ""),
                    "action": receipt.get("action", ""),
                    "transport": receipt.get("transport", ""),
                    "refusal": receipt.get("protocol_refusal", {})})
    for obs in list_probe_observations(dsn, run_id, task_id):
        out.append({"kind": "coord-probe",
                    "interface": obs.get("interface", ""),
                    "timed_out": bool(obs.get("timed_out", False)),
                    "error": obs.get("error")})
    return out


def _actual_artifacts(dsn: str, investigation_id: str) -> dict:
    try:
        state = team.team_state(dsn, investigation_id)
    except Exception:
        return {"plans": [], "submissions": [], "joins": []}
    return {
        "plans": [{"plan_id": p.get("plan_id"), "shape": p.get("shape"),
                   "revision": p.get("revision")}
                  for p in state.get("plans", [])],
        "submissions": [{"plan_id": s.get("plan_id"),
                         "node_id": s.get("node_id"),
                         "plan_revision": s.get("plan_revision"),
                         "output_digest": s.get("output_digest")}
                        for s in state.get("submissions", [])],
        "joins": [{"plan_id": j.get("plan_id"),
                   "plan_revision": j.get("plan_revision"),
                   "passed": j.get("passed")}
                  for j in state.get("joins", [])]}


def experience_packet(dsn: str, *, run_id: str, task_id: str,
                      investigation_id: str,
                      task_snapshot: dict | None = None,
                      interface_contract: dict | None = None) -> dict:
    base = build_experience_packet(dsn, run_id=run_id, task_id=task_id,
                                   investigation_id=investigation_id)
    decisions = list(base.get("decisions", []))
    observations = list(base.get("probe_observations", []))
    joins = list(base.get("joins", []))
    plans = list(base.get("plans", []))
    return {
        "packet_version": PACKET_VERSION,
        "run_id": run_id, "task_id": task_id,
        "investigation_id": investigation_id,
        "versioned_inputs": {
            "task_snapshot": dict(task_snapshot or {}),
            "interface_contract": dict(interface_contract or {}),
            "snapshot_digest": packet.snapshot_digest_of(
                task_snapshot or {})},
        "failed_joins": [j for j in joins if not j.get("passed", True)],
        "revisions": sorted({p.get("revision") for p in plans
                             if p.get("revision") is not None}),
        "decisions": decisions,
        "probe_observations": observations,
        "observations": observations,
        "plans": list(base.get("plans", [])),
        "submissions": list(base.get("submissions", [])),
        "joins": list(base.get("joins", [])),
        "executed_operations": _executed_operations(
            dsn, run_id=run_id, task_id=task_id),
        "actual_artifacts": _actual_artifacts(dsn, investigation_id),
        "failures": [d for d in decisions
                     if d.get("protocol_refusal") or d.get("transport")],
        "cost": _episode_costs(dsn, run_id=run_id, task_id=task_id)}


def construction_budget(*,
                        max_output_tokens: int =
                        CONSTRUCTION_MAX_OUTPUT_TOKENS,
                        reasoning_effort: str =
                        CONSTRUCTION_REASONING_EFFORT,
                        deadline_ms: int = 300_000,
                        timeout_ms: int = 60_000,
                        live_calls_authorized: int =
                        MAX_CONSTRUCTION_CALLS) -> dict:
    if not 0 < int(live_calls_authorized) <= MAX_CONSTRUCTION_CALLS:
        raise ValueError("live_calls_authorized must be within the "
                         "%d-call construction ceiling"
                         % MAX_CONSTRUCTION_CALLS)
    prov = provenance()
    return {"budget_version": BUDGET_VERSION, "model": prov["model"],
            "max_output_tokens": int(max_output_tokens),
            "reasoning_effort": reasoning_effort,
            "deadline_ms": int(deadline_ms), "timeout_ms": int(timeout_ms),
            "finite": True, "label": prov["label"],
            "doubled": prov["doubled"],
            "live_calls_authorized": int(live_calls_authorized),
            "live_calls_used": 0}


def construction_request(episodes: Any, budget: dict, *,
                         lineage: int, attempt: str,
                         prior_failure: dict | None = None) -> dict:
    if attempt not in ("init", "repair"):
        raise SettlementError(f"unknown construction attempt {attempt!r}")
    if attempt == "repair":
        if prior_failure is None:
            raise SettlementError("repair needs the concrete prior failure")
        assert_no_protected_feedback(prior_failure, "repair")
        failure: dict | None = dict(prior_failure)
        failure["lineage"] = int(lineage)
    else:
        failure = None
    prov = provenance()
    try:
        made = packet.construction_packet(
            episodes, budget, lineage=lineage, attempt=attempt,
            prior_failure=failure,
            content_budget_bytes=CONSTRUCTION_CONTENT_BUDGET_BYTES)
    except SettlementError as exc:
        if "exceeds content budget" in str(exc):
            raise ConstructionRequestTooLarge(str(exc))
        raise
    made["request_version"] = REQUEST_VERSION
    made["label"] = prov["label"]
    made["doubled"] = prov["doubled"]
    ordered = {"request_version": made.pop("request_version")}
    ordered.update(made)
    prior_failure_out = ordered.pop("prior_failure")
    packet_digest_out = ordered.pop("packet_digest")
    label_out = ordered.pop("label")
    doubled_out = ordered.pop("doubled")
    ordered["label"] = label_out
    ordered["doubled"] = doubled_out
    ordered["prior_failure"] = prior_failure_out
    ordered["packet_digest"] = packet_digest_out
    return ordered


def render_construction_prompt(request: dict) -> str:
    return packet.render_construction_prompt(request)


def _construction_text(dsn: str, operation_id: str) -> tuple[str, dict]:
    from psycopg.rows import dict_row
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content, outcome FROM receipts"
                        " WHERE operation_id = %s ORDER BY receipt_identity",
                        (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    for row in rows:
        content = row.get("content") or {}
        if isinstance(content.get("text"), str):
            return content["text"], dict(content.get("usage") or {})
    return "", {"input_tokens": 0, "output_tokens": 0}


TERMINAL_OPERATION_STATES = ("observed", "reconciled", "cancelled")


def _operation_ids(dsn: str, prefix: str) -> list[str]:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operations WHERE id LIKE %s"
                        " ORDER BY id", (f"{prefix}%",))
            rows = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT request_id FROM command_journal WHERE"
                        " request_id LIKE %s AND result_code = 'invalid_input'"
                        " ORDER BY request_id", (f"{prefix}-invalid-%",))
            rows += [r[0] for r in cur.fetchall()]
            conn.commit()
            return rows


def _parse_operation_id(prefix: str, operation_id: str) -> dict | None:
    stem = operation_id[len(prefix):] if operation_id.startswith(prefix) \
        else operation_id
    parts = stem.strip("-").split("-")
    if len(parts) != 4 or parts[0] != "l":
        return None
    try:
        int(parts[3])
        return {"lineage": int(parts[1]), "attempt": parts[2]}
    except ValueError:
        return None


@dataclass
class ConstructionLedger:
    dsn: str
    allocation_id: str
    attempt_prefix: str = "coord02-L-construct"
    calls: list[dict] = field(default_factory=list)
    refused: int = 0
    authorized_calls: int = MAX_CONSTRUCTION_CALLS

    def __post_init__(self) -> None:
        if not 0 < int(self.authorized_calls) <= MAX_CONSTRUCTION_CALLS:
            raise ValueError("authorized_calls must be within the "
                             "%d-call construction ceiling"
                             % MAX_CONSTRUCTION_CALLS)
        _acquisition_step(
            self.dsn, f"coord02:L-construction-{self.allocation_id}:identity",
            {"attempt_prefix": self.attempt_prefix}, lambda: {})
        self._hydrate()

    def _hydrate(self) -> None:
        seen = {c.get("operation_id") for c in self.calls}
        for operation_id in _operation_ids(self.dsn, self.attempt_prefix):
            if operation_id in seen:
                continue
            if "-invalid-" in operation_id:
                self.calls.append({"operation_id": operation_id,
                                   "consumed": True, "valid": False,
                                   "lineage": 0, "attempt": "invalid"})
                continue
            self.calls.append(self._record_of(operation_id))

    def _record_of(self, operation_id: str) -> dict:
        row = broker.read_operation(self.dsn, operation_id) or {}
        inner = ((row.get("payload") or {}).get("payload")) or {}
        parsed = _parse_operation_id(self.attempt_prefix, operation_id) \
            or {"lineage": 0, "attempt": "unknown"}
        text, usage = _construction_text(self.dsn, operation_id)
        return {"lineage": parsed["lineage"], "attempt": parsed["attempt"],
                "operation_id": operation_id,
                "dispatch_state": row.get("dispatch_state", "unknown"),
                "text": text, "usage": usage,
                "label": CONSTRUCTION_LABEL
                if inner.get("model", "") == CONSTRUCTION_MODEL
                else LIVE_LABEL,
                "doubled": inner.get("model", "") == CONSTRUCTION_MODEL,
                "live": inner.get("model", "") != CONSTRUCTION_MODEL,
                "budget": {"model": inner.get("model", ""),
                           "max_output_tokens": inner.get(
                               "max_output_tokens", 0),
                           "reasoning_effort": inner.get(
                               "reasoning_effort")}}

    def remaining(self) -> int:
        return self.authorized_calls - self.calls_used()

    def calls_used(self) -> int:
        return len(_operation_ids(self.dsn, self.attempt_prefix))

    def unresolved_effects(self) -> list[str]:
        out = []
        for record in self.calls:
            operation_id = record.get("operation_id", "")
            if "-invalid-" in operation_id:
                continue
            row = broker.read_operation(self.dsn, operation_id) or {}
            if row.get("dispatch_state") not in TERMINAL_OPERATION_STATES:
                out.append(operation_id)
        return out

    def _reconcile_pending(self, gateway: Any) -> list[str]:
        pending = self.unresolved_effects()
        if pending and _is_live_gateway(gateway):
            preflight.require_live(
                panels=("development",),
                construction_calls=self.authorized_calls)
        still = []
        for operation_id in pending:
            status = broker.dispatch_operation(
                self.dsn, operation_id, launchers={}, gateway=gateway,
                grant_version=_grant_version(self.dsn))
            if status.dispatch_state not in TERMINAL_OPERATION_STATES:
                still.append(operation_id)
        self._hydrate()
        return still

    def _consume_invalid(self, operation_id: str, detail: str) -> None:
        result = store.transact(
            self.dsn, Command(request_id=operation_id, payload={}),
            lambda cur, control: (ResultCode.INVALID_INPUT, detail,
                                  {"operation_id": operation_id}, [], []))
        if result.code not in (ResultCode.INVALID_INPUT,
                               ResultCode.ALREADY_APPLIED):
            raise SettlementError(
                f"invalid construction request not recorded: {result.detail}")

    def _guard_lineage(self, lineage: int, attempt: str) -> None:
        if not 1 <= int(lineage) <= MAX_LINEAGES:
            raise SettlementError(f"lineage {lineage} outside 1..2")
        if attempt not in ("init", "repair"):
            raise SettlementError(
                f"unknown construction attempt {attempt!r}")
        prior = [c for c in self.calls
                 if c["lineage"] == int(lineage) and c.get("valid", True)]
        if attempt == "init" and prior:
            raise SettlementError(f"lineage {lineage} init already used")
        if attempt == "repair":
            if len(prior) != 1 or prior[0]["attempt"] != "init":
                raise SettlementError(
                    f"lineage {lineage} repair needs exactly one prior init")

    def _serialized(self, gateway: Any, request: dict, *,
                    replay: bool = False) -> dict:
        lineage = int(request.get("lineage", 0))
        attempt = str(request.get("attempt", ""))
        with db.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(hashtext(%s))",
                            (self.attempt_prefix,))
                conn.commit()
            try:
                still = self._reconcile_pending(gateway)
                if still:
                    self.refused += 1
                    raise ConstructionBudgetExhausted(
                        "unresolved effects hold construction capacity: %s"
                        % ",".join(sorted(still)))
                self._hydrate()
                if replay:
                    prior = next((c for c in self.calls
                                  if c["lineage"] == lineage
                                  and c["attempt"] == attempt), None)
                    if prior is not None:
                        return self._record_of(prior["operation_id"])
                prov = provenance(gateway)
                if _is_live_gateway(gateway):
                    preflight.require_live(
                        panels=("development",),
                        construction_calls=self.authorized_calls)
                if self.calls_used() >= self.authorized_calls:
                    self.refused += 1
                    raise ConstructionBudgetExhausted()
                seq = self.calls_used() + 1
                try:
                    self._guard_lineage(lineage, attempt)
                except SettlementError as exc:
                    self._consume_invalid(
                        f"{self.attempt_prefix}-invalid-{seq}", str(exc))
                    self._hydrate()
                    raise
                budget = request.get("budget", {}) or {}
                operation_id = (f"{self.attempt_prefix}-l-{lineage}"
                                f"-{attempt}-{seq}")
                ensured = broker.ensure_operation(
                    self.dsn, operation_id=operation_id,
                    effect=broker.MODEL_INFERENCE,
                    payload={"model": str(prov["model"]),
                             "messages": [{"role": "user",
                                           "content":
                                               render_construction_prompt(
                                                   request)}],
                             "max_output_tokens": int(budget.get(
                                 "max_output_tokens",
                                 CONSTRUCTION_MAX_OUTPUT_TOKENS)),
                             "deadline_ms": int(budget.get("deadline_ms",
                                                           300_000)),
                             "reasoning_effort": str(budget.get(
                                 "reasoning_effort",
                                 CONSTRUCTION_REASONING_EFFORT))},
                    allocation_id=self.allocation_id, attempt_id=None)
                if ensured.code not in (ResultCode.APPLIED,
                                        ResultCode.ALREADY_APPLIED):
                    raise SettlementError(
                        "construction call not admitted: %s"
                        % ensured.detail)
            finally:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(hashtext(%s))",
                                (self.attempt_prefix,))
                    conn.commit()
        status = broker.dispatch_operation(
            self.dsn, operation_id, launchers={}, gateway=gateway,
            grant_version=_grant_version(self.dsn))
        text, usage = _construction_text(self.dsn, operation_id)
        record = {"lineage": lineage, "attempt": attempt,
                  "operation_id": operation_id,
                  "dispatch_state": status.dispatch_state,
                  "text": text, "usage": usage,
                  "label": prov["label"], "doubled": prov["doubled"],
                  "live": prov["live"],
                  "request_digest": sha_hex(canonical_bytes(request)),
                  "budget": dict(budget)}
        self.calls.append(record)
        return record

    def request_call(self, request: dict, *,
                     gateway: Any | None = None,
                     replay: bool = False) -> dict:
        return self._serialized(gateway or FakeGatewayAdapter(),
                                dict(request), replay=replay)

    def repair_call(self, episodes: Any, budget: dict, *, lineage: int,
                    prior_failure: dict, gateway: Any | None = None,
                    replay: bool = False) -> dict:
        return self.request_call(
            construction_request(episodes, budget, lineage=lineage,
                                 attempt="repair",
                                 prior_failure=prior_failure),
            gateway=gateway, replay=replay)

    def accounting(self) -> dict:
        live_used = sum(1 for c in self.calls if c.get("live"))
        labels = {c.get("label") for c in self.calls if c.get("label")}
        return {"calls_used": self.calls_used(),
                "calls_refused": self.refused,
                "ceiling": self.authorized_calls,
                "study_ceiling": MAX_CONSTRUCTION_CALLS,
                "live_calls_used": live_used,
                "live_calls_authorized": self.authorized_calls,
                "label": next(iter(labels), CONSTRUCTION_LABEL),
                "lineages": sorted({c["lineage"] for c in self.calls
                                    if c.get("valid", True)
                                    and c.get("lineage")})}


def construction_allocation_units(budget: dict) -> int:
    authorized = int(budget.get("live_calls_authorized",
                                MAX_CONSTRUCTION_CALLS))
    return authorized * (
        CONSTRUCTION_CONTENT_BUDGET_BYTES // 4
        + int(budget.get("max_output_tokens",
                         CONSTRUCTION_MAX_OUTPUT_TOKENS)))


def seed_construction_campaign(dsn: str, campaign: str,
                               budget: dict) -> dict:
    return seed_episode(dsn, f"L-construct-{campaign}", {"m": "1"},
                        authorized=construction_allocation_units(budget))


DESIGNATION_TABLE = "coord02_db_designation"


def _designation(dsn: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (DESIGNATION_TABLE,))
            if cur.fetchone()[0] is None:
                conn.commit()
                return None
            cur.execute(f"SELECT kind FROM {DESIGNATION_TABLE}")
            kinds = [row[0] for row in cur.fetchall()]
            if "evidence" in kinds:
                cur.execute(f"SELECT kind, purpose FROM {DESIGNATION_TABLE}"
                            " WHERE kind = 'evidence'"
                            " ORDER BY created_at DESC LIMIT 1")
            else:
                cur.execute(f"SELECT kind, purpose FROM {DESIGNATION_TABLE}"
                            " ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            conn.commit()
            if row is None:
                return None
            return {"kind": row[0], "purpose": row[1]}


def designate_db(dsn: str, *, kind: str, purpose: str) -> dict:
    if kind not in ("disposable", "evidence"):
        raise SettlementError(f"unknown designation {kind!r}")
    if not purpose:
        raise SettlementError("designation needs a stated purpose")
    current = _designation(dsn)
    if current is not None and current["kind"] == "evidence" \
            and kind == "disposable":
        raise EvidenceDBProtected(
            f"refusing to relabel evidence DB disposable "
            f"(designated evidence: {current['purpose']})")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE IF NOT EXISTS {DESIGNATION_TABLE}"
                        " (kind TEXT NOT NULL, purpose TEXT NOT NULL,"
                        " created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            cur.execute(f"INSERT INTO {DESIGNATION_TABLE} (kind, purpose)"
                        " VALUES (%s, %s)", (kind, purpose))
            conn.commit()
    return {"kind": kind, "purpose": purpose}


def prepare_disposable_db(dsn: str, migrations: Any) -> dict:
    designation = _designation(dsn)
    if designation is None or designation["kind"] != "disposable":
        raise EvidenceDBProtected(
            "no disposable-purpose designation in this database;"
            " designate first" if designation is None
            else f"designated {designation['kind']}:"
                 f" {designation['purpose']}")
    db.apply_migrations(dsn, migrations)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            tables = [row[0] for row in cur.fetchall()]
            for table in tables:
                if table == DESIGNATION_TABLE:
                    continue
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()
    return {"truncated": sorted(t for t in tables
                                if t != DESIGNATION_TABLE)}


def keep_response(record: dict) -> dict:
    text = record.get("text", "") or ""
    usage = dict(record.get("usage") or {})
    base = {"usage": usage, "kept": True,
            "label": record.get("label", CONSTRUCTION_LABEL),
            "doubled": record.get("doubled", True),
            "live": record.get("live", False),
            "operation_id": record.get("operation_id", "")}
    if not text.strip():
        return {"usable": False, "reason": "empty-response",
                "entry_bytes": b"", "response_bytes": b"", **base}
    entry, problem = packet.parse_construction_entry(text)
    if problem:
        return {"usable": False, "reason": problem,
                "entry_bytes": b"",
                "response_bytes": text.encode("utf-8"), **base}
    return {"usable": True, "reason": "",
            "entry_bytes": entry.encode("utf-8"),
            "response_bytes": text.encode("utf-8"), **base}


def parse_candidate(entry_bytes: bytes) -> dict:
    if not entry_bytes:
        return {"ok": False, "reason": "empty-response"}
    try:
        compile(entry_bytes.decode("utf-8"), "<candidate>", "exec")
    except (ValueError, UnicodeDecodeError, SyntaxError) as exc:
        return {"ok": False, "reason": f"parse-failure: {exc}"}
    return {"ok": True, "reason": ""}


def stage_candidate(staging_root: Any, *, entry_bytes: bytes,
                    description: str, requires: dict,
                    label: str = CONSTRUCTION_LABEL) -> dict:
    receipt = stage_package(
        staging_root, entry_bytes=entry_bytes,
        description=f"[{label}] {description}".encode("utf-8"),
        requires=dict(requires))
    receipt["construction_label"] = label
    receipt["entry_bytes"] = bytes(entry_bytes)
    return receipt


def check_candidate(dsn: str, artifacts_root: Any, *, receipt: dict,
                    launcher: Any, allocation_id: str,
                    version_id: str, requires: dict) -> dict:
    try:
        staged = publish_package_version(
            dsn, artifacts_root, receipt, launcher, allocation_id,
            version_id=version_id, requires=dict(requires))
    except SettlementError as exc:
        return {"ok": False, "reason": str(exc), "version_id": version_id}
    if staged.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return {"ok": False, "reason": staged.detail,
                "version_id": version_id}
    try:
        loaded = load_frozen_package(dsn, artifacts_root, version_id)
    except SettlementError as exc:
        return {"ok": False, "reason": str(exc), "version_id": version_id}
    entry = bytes(loaded.get("entry_bytes", b""))
    if sha_hex(entry) != sha_hex(bytes(receipt.get("entry_bytes", entry))):
        return {"ok": False, "reason": "digest-mismatch",
                "version_id": version_id}
    return {"ok": True, "reason": "", "version_id": version_id,
            "package_digest": loaded["package_digest"]}


def stage_gate(dsn: str, staging_root: Any, artifacts_root: Any, *,
               entry_bytes: bytes, requires: dict, version_id: str,
               launcher: Any, allocation_id: str,
               description: str = "coord02-L candidate") -> dict:
    parsed = parse_candidate(entry_bytes)
    if not parsed["ok"]:
        return {"stage": "parse", "ok": False, "reason": parsed["reason"]}
    try:
        receipt = stage_candidate(staging_root, entry_bytes=entry_bytes,
                                  description=description, requires=requires)
    except SettlementError as exc:
        return {"stage": "stage", "ok": False, "reason": str(exc)}
    checked = check_candidate(dsn, artifacts_root, receipt=receipt,
                              launcher=launcher, allocation_id=allocation_id,
                              version_id=version_id, requires=requires)
    if not checked["ok"]:
        return {"stage": "check", "ok": False, "reason": checked["reason"]}
    return {"stage": "select", "ok": True, "reason": "",
            "version_id": version_id,
            "package_digest": checked["package_digest"], "receipt": receipt}


def snapshot_files(task_id: str) -> dict:
    payload = oracle.build_solver_payload(task_id)
    return {k: v for k, v in payload["files"].items()
            if isinstance(v, str) and (k == "spec.json"
                                      or k == "convention.json"
                                      or k.startswith("src/"))}


def _snapshot_path(name: str) -> str:
    if "/" in name or name in ("convention.json", "spec.json",
                               "public.json", "spec.md"):
        return name
    return "src/" + name


def valid_tree_files(task_id: str) -> dict:
    snap = snapshot_files(task_id)
    valid = dict(snap)
    for name, body in oracle.overlay_files(task_id, "valid").items():
        path = _snapshot_path(name)
        if path in valid:
            valid[path] = body
    return valid


def valid_tree_outputs(task_id: str, owned: list) -> dict:
    valid = valid_tree_files(task_id)
    return {p: valid[p] for p in owned if p in valid}


def dev_constructor(task_id: str, *, solved: bool = True) -> Callable:
    def _build(node: str, child: dict, rendered: dict,
               operation_id: str | None = None,
               attempt_id: str | None = None) -> dict | None:
        return None
    return _build


def _dev_interface_contract(task_id: str, payload: dict) -> dict:
    return {"task_id": task_id,
            "public_cases": len(payload.get("public", [])),
            "worker_files": oracle.worker_files(task_id),
            "new_paths": []}


def _public_check_source(task_id: str) -> str:
    return "\n".join([
        "import json",
        "import os",
        "import sys",
        "import tempfile",
        "asm = sys.argv[1]",
        "cases = __PUBLIC__",
        "sys.path.insert(0, os.path.join(asm, 'src'))",
        "import app",
        "failures = []",
        "for case in cases:",
        "    with tempfile.TemporaryDirectory() as tmp:",
        "        req = os.path.join(tmp, 'req.json')",
        "        resp = os.path.join(tmp, 'resp.json')",
        "        open(req, 'w').write(json.dumps(case['input']))",
        "        try:",
        "            app.main(['app', req, resp])",
        "            got = json.loads(open(resp).read())",
        "        except Exception as exc:",
        "            failures.append({'input': case['input'],",
        "                             'error': str(exc)})",
        "            continue",
        "        if got != case['expected']:",
        "            failures.append({'input': case['input'], 'got': got,",
        "                             'expected': case['expected']})",
        "if failures:",
        "    print(json.dumps({'status': 'error',",
        "                      'data': {'failures': failures}}))",
        "else:",
        "    print(json.dumps({'status': 'ok', 'data': {}}))",
        ""]).replace("__PUBLIC__", json.dumps(oracle.public_cases(task_id)))


def _dev_join_rules(task_id: str) -> dict:
    return {"join": "conjunctive", "integration_owner": "w1",
            "check_entry": "check.py",
            "checks": {"check.py": _public_check_source(task_id)}}


def _requires_for(task_id: str, snapshot: dict) -> dict:
    out = {}
    for path in oracle.worker_files(task_id):
        if path in snapshot and isinstance(snapshot[path], str):
            out["role-" + Path(path).stem] = {
                "digest": hashlib.sha256(
                    snapshot[path].encode()).hexdigest(),
                "abi": "py-module", "version": "1"}
    return out


def _dev_bindings(requires: dict, snapshot: dict) -> list:
    bindings = []
    for role in sorted(requires):
        stem = role[len("role-"):] if role.startswith("role-") else role
        match = next((p for p in sorted(snapshot)
                      if p == f"src/{stem}.py" or p.endswith(f"/{stem}.py")
                      or Path(p).stem == stem), None)
        if match is None:
            match = sorted(snapshot)[0]
        bindings.append({"name": role, "path": match,
                         "abi": "py-module", "version": "1"})
    return bindings


def _dev_source_interfaces(task_id: str) -> dict:
    payload = oracle.build_solver_payload(task_id)
    snap = json.dumps({"task_id": task_id,
                       "public": payload["public"][:1],
                       "files": sorted(payload["files"])})
    script = "\n".join([
        "import json",
        "import sys",
        "SNAP = __SNAP__",
        "req = json.load(open(sys.argv[1]))",
        "json.dump({'snapshot': SNAP, 'echo': req.get('input', {})},",
        "            open(sys.argv[2], 'w'))",
        ""]).replace("__SNAP__", snap)
    return {"observe-broken": script.encode("utf-8")}


def _acquire_probe_plan_entry() -> bytes:
    return ("\n".join([
        "import json",
        "import sys",
        "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
        "    raise SystemExit(0)",
        "req = json.load(open(sys.argv[1]))",
        "phase = req.get('phase', '')",
        "if phase == 'pre-plan':",
        "    proposal = {'action': 'probe', 'invocations': [",
        "        {'interface': 'observe-broken', 'input': {'path': ''}}]}",
        "else:",
        "    proposal = {'action': 'stop',",
        "                'reason': 'acquisition probe only'}",
        "resp = {'profile': req['profile'],",
        "        'profile_version': req['profile_version'],",
        "        'decision_id': req['decision_id'],",
        "        'package_digest': req['package_digest'],",
        "        'source_digest': req['source_digest'],",
        "        'plan_revision': req['plan_revision'],",
        "        'phase': req['phase'], 'proposal': proposal,",
        "        'state': {'acquired': True}}",
        "json.dump(resp, open(sys.argv[2], 'w'))",
        ""]) + "\n").encode("utf-8")


def _run_dev_episode(dsn: str, tag: str, task_id: str, snapshot: dict,
                     payload: dict, launcher_factory: Callable,
                     constructor: Callable,
                     entry: bytes | None = None) -> dict:
    seed = seed_episode(dsn, tag, snapshot)
    entry = entry if entry is not None else _acquire_probe_plan_entry()
    requires = _requires_for(task_id, snapshot)
    package = {"version_id": f"coord02-L-{tag}",
               "package_digest": sha_hex(entry),
               "entry_bytes": entry, "requires": requires}
    cfg = EpisodeConfig(
        run_id=f"run-{tag}", task_id=task_id,
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=_dev_interface_contract(task_id, payload),
        join_rules=_dev_join_rules(task_id),
        bindings=_dev_bindings(requires, snapshot),
        source_interfaces=_dev_source_interfaces(task_id),
        package=package, snapshot_digest=seed["snapshot_digest"])
    outcome = run_episode(dsn, cfg, launcher_factory(tag), constructor)
    return {"run_id": cfg.run_id, "task_id": cfg.task_id,
            "investigation_id": cfg.investigation_id,
            "interface_contract": dict(cfg.interface_contract),
            "outcome": outcome}


def _acquisition_step(dsn: str, identity: str, payload: dict,
                      run: Callable) -> dict:
    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            (identity,)).fetchone()
    data = row[0] if row is not None else run()
    result = store.transact(
        dsn, Command(request_id=identity, payload=payload),
        lambda cur, control: (ResultCode.APPLIED, "", data, [], []))
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"acquisition step refused: {result.detail}")
    return result.data


def acquire_episodes(dsn: str, scratch: Path, *, task_ids: list[str],
                     launcher_factory: Callable,
                     constructor: Callable | None = None,
                     campaign_root: str | None = None) -> list[dict]:
    episodes = []
    root = campaign_root or uuid.uuid4().hex
    for pos, task_id in enumerate(task_ids):
        tag = f"L-acquire-{root}-{task_id}-{pos}"
        payload = oracle.build_solver_payload(task_id)
        snapshot = snapshot_files(task_id)
        made = _acquisition_step(
            dsn, f"coord02:{tag}:episode", {"snapshot": snapshot},
            lambda: _run_dev_episode(dsn, tag, task_id, snapshot, payload,
                                     launcher_factory, constructor))
        packet = experience_packet(
            dsn, run_id=made["run_id"], task_id=made["task_id"],
            investigation_id=made["investigation_id"],
            task_snapshot=snapshot,
            interface_contract=made["interface_contract"])
        episodes.append({"task_id": task_id, "episode": made,
                         "packet": packet})
    return episodes


def _profile_check(dsn: str, *, entry_bytes: bytes, requires: dict,
                   launcher_factory: Callable, identity: str | None = None) -> dict:
    parsed = parse_candidate(entry_bytes)
    if not parsed["ok"]:
        return {"ok": False, "reason": parsed["reason"]}
    with tempfile.TemporaryDirectory(
            prefix="coord02-validate-profile-") as tmp:
        root = Path(tmp)
        identity = identity or uuid.uuid4().hex
        seed = seed_episode(dsn, f"validate-profile-{identity}", {"m": "1"})
        launcher = launcher_factory(f"validate-profile-{identity}")["local-process"]
        gated = stage_gate(
            dsn, root / "staging", root / "artifacts",
            entry_bytes=entry_bytes, requires=dict(requires),
            version_id=f"coord02-validate-{identity}",
            launcher=launcher, allocation_id=seed["allocation_id"],
            description="coord02 development-profile check")
    if not gated["ok"]:
        return {"ok": False, "reason": gated["reason"]}
    return {"ok": True, "reason": ""}


def _candidate_admitted(outcome: dict) -> bool:
    if outcome.get("status") in ("s-fallback-success", "s-fallback-failed"):
        return False
    return outcome.get("plan_id") is not None


def validate_on_development(dsn: str, *, entry_bytes: bytes,
                            requires: dict, task_ids: list[str],
                            launcher_factory: Callable,
                            constructor: Callable | None = None,
                            constructor_factory: Callable | None = None,
                            costs: dict | None = None,
                            validation_root: str | None = None) -> dict:
    root = validation_root if validation_root is not None else uuid.uuid4().hex
    if not isinstance(root, str) or not root.strip():
        raise ValueError("validation_root must be a nonempty string")
    identity = f"coord02:L-validate-{root}"
    _acquisition_step(
        dsn, f"{identity}:request",
        {"entry_digest": sha_hex(entry_bytes), "requires": requires,
         "task_ids": list(task_ids), "costs": dict(costs or {})}, lambda: {})
    parsed = parse_candidate(entry_bytes)
    profile = _acquisition_step(
        dsn, f"{identity}:profile", {"entry_digest": sha_hex(entry_bytes)},
        lambda: _profile_check(dsn, entry_bytes=entry_bytes, requires=requires,
                               launcher_factory=launcher_factory, identity=identity))
    solved: list[str] = []
    fallbacks: list[str] = []
    admitted: list[str] = []
    failures: list = []
    executed: list[str] = []
    run_ids: list[str] = []
    for pos, task_id in enumerate(task_ids):
        tag = f"L-validate-{root}-{task_id}-{pos}"
        payload = oracle.build_solver_payload(task_id)
        snapshot = snapshot_files(task_id)
        build = constructor_factory(task_id) \
            if constructor_factory is not None else constructor
        made = _acquisition_step(
            dsn, f"coord02:{tag}:episode", {"snapshot": snapshot},
            lambda: _run_dev_episode(dsn, tag, task_id, snapshot, payload,
                                     launcher_factory, build, entry=entry_bytes))
        outcome = made["outcome"]
        executed.append(task_id)
        run_ids.append(made["run_id"])
        if _candidate_admitted(outcome):
            admitted.append(task_id)
        if outcome["status"] == "success":
            solved.append(task_id)
        elif outcome["status"] == "s-fallback-success":
            fallbacks.append(task_id)
        else:
            failures.append({"task_id": task_id,
                             "status": outcome["status"],
                             "reason": outcome.get("reason", "")})
    measured = sum(_count_operations(dsn, f"coord:{r}:%") for r in run_ids)
    costs = dict(costs or {})
    valid = bool(parsed["ok"] and profile["ok"] and admitted)
    return {"parse_ok": bool(parsed["ok"]),
            "parse_reason": parsed["reason"],
            "profile_ok": bool(profile["ok"]),
            "profile_reason": profile["reason"],
            "execution_admitted": bool(admitted),
            "admitted_tasks": sorted(admitted),
            "admitted_count": len(admitted),
            "valid_execution": valid,
            "solved_tasks": sorted(solved),
            "solved_count": len(solved),
            "fallback_tasks": sorted(fallbacks),
            "fallback_count": len(fallbacks),
            "failures": failures, "executed": executed,
            "model_tokens": int(costs.get("model_tokens", 0)),
            "sandbox_operations": int(
                costs.get("sandbox_operations", measured)),
            "canonical_bytes": len(entry_bytes)}


def _ordering_key(result: dict) -> tuple:
    validation = result.get("validation", {})
    return (0 if validation.get("valid_execution") else 1,
            -int(validation.get("solved_count", 0)),
            int(validation.get("model_tokens", 0)),
            int(validation.get("sandbox_operations", 0)),
            int(validation.get("canonical_bytes", 0)),
            int(result.get("lineage", 0)))


def select_candidate(dev_results: list[dict]) -> dict:
    ranked = sorted(dev_results, key=_ordering_key)
    best = ranked[0] if ranked else None
    ranking = [r["lineage"] for r in ranked]
    if best is None or not best["validation"]["valid_execution"]:
        return {"selection": "none", "selector": SELECTOR_VERSION,
                "ordering": list(ORDERING), "ranking": ranking,
                "reason": "neither candidate executable under the contract"}
    return {"selection": best["lineage"], "selector": SELECTOR_VERSION,
            "ordering": list(ORDERING), "ranking": ranking,
            "reason": "preregistered development ordering"}


def exposure_manifest(lineage: int, exposure: list) -> dict:
    return {"lineage": int(lineage),
            "development_access": "same-policy",
            "prior_lineage_results": [
                e.get("lineage") if isinstance(e, dict) else None
                for e in exposure],
            "recorded": True}


def validation_stages(rec: dict) -> list:
    if isinstance(rec.get("repair_kept"), dict) \
            and rec["repair_kept"].get("usable"):
        return ["init", "repair"]
    return ["init"]


def construct_lineages(episodes: list[dict], budget: dict, *,
                        ledger: ConstructionLedger,
                        gateway: Any | None = None,
                        launcher_factory: Callable) -> list[dict]:
    gateway = gateway or FakeGatewayAdapter()
    lineages: list[dict] = []
    for lineage in (1, 2):
        prior = [copy.deepcopy(r) for r in lineages]
        init = ledger.request_call(
            construction_request(episodes, budget, lineage=lineage,
                                 attempt="init"), gateway=gateway, replay=True)
        kept = keep_response(init)
        parsed = parse_candidate(kept["entry_bytes"])
        profile = _acquisition_step(
            ledger.dsn, f"{init['operation_id']}:profile",
            {"entry_digest": sha_hex(kept["entry_bytes"])},
            lambda: _profile_check(
                ledger.dsn, entry_bytes=kept["entry_bytes"], requires={},
                identity=init["operation_id"],
                launcher_factory=launcher_factory)) \
            if kept["usable"] and parsed["ok"] else None
        rec: dict = {"lineage": lineage, "init": init,
                     "kept": kept, "parsed": parsed,
                     "profile": profile,
                     "repair": None, "repair_kept": None,
                     "repair_parsed": None, "repair_profile": None,
                     "rejections": [],
                     "exposure_manifest": exposure_manifest(lineage, prior)}
        if not kept["usable"]:
            rec["rejections"].append({"stage": "keep",
                                      "reason": kept["reason"],
                                      "operation_id": init["operation_id"]})
        elif not parsed["ok"]:
            rec["rejections"].append({"stage": "parse",
                                      "reason": parsed["reason"],
                                      "operation_id": init["operation_id"]})
        elif profile is not None and not profile["ok"]:
            rec["rejections"].append({"stage": "profile",
                                      "reason": profile["reason"],
                                      "operation_id": init["operation_id"]})
        if not kept["usable"] or not parsed["ok"] \
                or (profile is not None and not profile["ok"]):
            if profile is not None and not profile["ok"]:
                failure = {"kind": "profile",
                           "reason": profile["reason"],
                           "operation_id": init["operation_id"],
                           "lineage": lineage, "stage": "profile"}
            else:
                failure = {"kind": "parse" if kept["usable"] else "empty",
                           "reason": parsed.get("reason")
                           or kept.get("reason"),
                           "operation_id": init["operation_id"],
                           "lineage": lineage,
                           "stage": "parse" if kept["usable"] else "keep"}
            rec["repair_failure"] = failure
            rec["repair"] = ledger.repair_call(
                episodes, budget, lineage=lineage, prior_failure=failure,
                gateway=gateway, replay=True)
            rec["repair_kept"] = keep_response(rec["repair"])
            rec["repair_parsed"] = parse_candidate(
                rec["repair_kept"]["entry_bytes"])
            if not rec["repair_kept"]["usable"]:
                rec["rejections"].append({
                    "stage": "repair-keep",
                    "reason": rec["repair_kept"]["reason"],
                    "operation_id": rec["repair"]["operation_id"]})
            elif not rec["repair_parsed"]["ok"]:
                rec["rejections"].append({
                    "stage": "repair-parse",
                    "reason": rec["repair_parsed"]["reason"],
                    "operation_id": rec["repair"]["operation_id"]})
            else:
                rec["repair_profile"] = _acquisition_step(
                    ledger.dsn, f"{rec['repair']['operation_id']}:profile",
                    {"entry_digest": sha_hex(rec["repair_kept"]["entry_bytes"])},
                    lambda: _profile_check(
                        ledger.dsn,
                        entry_bytes=rec["repair_kept"]["entry_bytes"],
                        identity=rec["repair"]["operation_id"],
                        requires={}, launcher_factory=launcher_factory))
                if not rec["repair_profile"]["ok"]:
                    rec["rejections"].append({
                        "stage": "repair-profile",
                        "reason": rec["repair_profile"]["reason"],
                        "operation_id": rec["repair"]["operation_id"]})
        lineages.append(rec)
    return lineages


def acquire(dsn: str, scratch: Path, *, task_ids: list[str],
            launcher_factory: Callable,
            constructor: Callable | None = None,
            construction_gateway: Any | None = None,
            budget: dict | None = None,
            attempt_prefix: str | None = None,
            campaign_root: str | None = None) -> dict:
    if not isinstance(campaign_root, str) or not campaign_root.strip():
        raise ValueError("campaign_root must be a nonempty string")
    budget = dict(budget) if budget is not None \
        else construction_budget()
    root = campaign_root
    prefix = attempt_prefix or f"coord02-L-construct-{root}"
    _acquisition_step(
        dsn, f"coord02:L-acquire-{root}:campaign",
        {"task_ids": list(task_ids), "budget": budget, "attempt_prefix": prefix},
        lambda: {})
    episodes = acquire_episodes(
        dsn, scratch, task_ids=list(task_ids), campaign_root=root,
        launcher_factory=launcher_factory, constructor=constructor)
    packet = _merged_packet(episodes)
    seed = seed_construction_campaign(dsn, root, budget)
    ledger = ConstructionLedger(dsn, seed["allocation_id"],
                                attempt_prefix=prefix,
                                authorized_calls=int(budget.get(
                                    "live_calls_authorized",
                                    MAX_CONSTRUCTION_CALLS)))
    lineages = construct_lineages(
        episodes, budget, ledger=ledger,
        gateway=construction_gateway or FakeGatewayAdapter(),
        launcher_factory=launcher_factory)
    return {"episodes": episodes, "packet": packet, "lineages": lineages,
            "ledger": ledger, "budget": budget,
            "accounting": ledger.accounting(), "campaign_root": root}


def _merged_packet(episodes: list[dict]) -> dict:
    if not episodes:
        return {"packet_version": PACKET_VERSION,
                "probe_observations": [], "decisions": [],
                "observations": [], "failures": [],
                "executed_operations": [], "plans": [],
                "submissions": [], "joins": []}
    merged: dict = copy.deepcopy(episodes[0]["packet"])
    for extra in episodes[1:]:
        packet = extra["packet"]
        for key in ("decisions", "probe_observations", "observations",
                    "failures", "executed_operations", "plans",
                    "submissions", "joins"):
            merged[key] = list(merged.get(key, [])) + list(
                packet.get(key, []))
    return merged


def freeze_selection(freeze_id: str, baselines: dict, *,
                     source_sha: str, selection: dict,
                     dev_results: list[dict], lineages: list[dict],
                     accounting: dict,
                     model: dict | None = None,
                     config: dict | None = None) -> dict:
    chosen = selection.get("selection")
    if chosen == "none":
        package_field: dict = {
            "kind": "none",
            "reason": selection.get(
                "reason", "no executable candidate"),
            "selector": SELECTOR_VERSION}
    else:
        winner = next(r for r in dev_results if r["lineage"] == chosen)
        lineage_rec = next(r for r in lineages if r["lineage"] == chosen)
        package_field = {
            "kind": "coordination-procedure/1",
            "version_id": winner.get("version_id", ""),
            "package_digest": sha_hex(winner.get("entry_bytes", b"")),
            "selector": SELECTOR_VERSION,
            "ordering": list(ORDERING),
            "development": {
                "protocol": DEV_PROTOCOL,
                "tasks": list(DEV_SELECTION_TASKS),
                "solved": winner.get("validation", {}).get(
                    "solved_tasks", []),
                "fallbacks": winner.get("validation", {}).get(
                    "fallback_tasks", [])},
            "exposure_manifest": dict(
                lineage_rec.get("exposure_manifest", {})),
            "construction": dict(accounting)}
    return freeze_mod.build_freeze(
        freeze_id, source_sha=source_sha, package=package_field,
        baselines=dict(baselines),
        model=dict(model) if model is not None else {
            "label": CONSTRUCTION_LABEL, "status": DOUBLED_NOTE,
            "live_calls_used": 0,
            "live_calls_authorized": MAX_CONSTRUCTION_CALLS},
        config=dict(config) if config is not None else {
            "budgets": dict(freeze_mod.CEILINGS),
            "rules": dict(freeze_mod.RULES)})


def publish_retained(dsn: str, artifacts_root: Any, *, receipt: dict,
                     launcher: Any, allocation_id: str, version_id: str,
                     requires: dict, applicability: dict,
                     evidence_refs: list, scope: dict,
                     dependencies: list, budget: dict) -> Any:
    from settlement import artifacts as _artifacts
    staged = publish_package_version(
        dsn, artifacts_root, receipt, launcher, allocation_id,
        version_id=version_id, requires=dict(requires))
    if staged.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return staged
    row = capabilities.get_version(dsn, version_id) or {}
    digest = str(row.get("artifact_digest") or "")
    verified = bool(
        digest and _artifacts.artifact_available(
            dsn, artifacts_root, digest))
    if not verified:
        raise SettlementError("retained bytes do not verify")
    hooks = {"applicability": dict(applicability),
             "evidence_refs": list(evidence_refs), "scope": dict(scope),
             "dependencies": [digest] if digest else list(dependencies),
             "budget": dict(budget)}
    staged.data = {**dict(staged.data), "hooks": hooks}
    return staged


def revoke_binding_eligibility(dsn: str, *, version_id: str,
                               reason: str) -> dict:
    done = capabilities.quarantine(
        dsn, _cmd(), version_id,
        f"demonstrated incompatibility: {reason}")
    return {"quarantine": done.code.value, "detail": done.detail}


def scoped_loss_evidence(observation: dict) -> dict:
    return {"scope": "binding",
            "binding": observation.get("binding", ""),
            "loss": observation.get("loss", ""),
            "global_quarantine": False}
