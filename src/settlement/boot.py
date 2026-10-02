from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from .common import ResultCode
from .config import Settings
from .gateway import (
    FakeGatewayAdapter,
    GatewayAdapter,
    GatewayError,
    GatewayErrorKind,
    GatewayStatus,
    ModelRequest,
    ModelResponse,
)

INSPECT_OPS = ("inspect", "mechanical-recovery")
SIMULATED_OP = "simulated-demonstration"
MODEL_OP = "model-inference"


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    configured: bool
    reachable: bool
    authenticated: bool
    exercised: bool
    detail: str = ""


@dataclass(frozen=True)
class BootReport:
    ok: bool
    entries: tuple[DependencyStatus, ...]
    available_operations: tuple[str, ...]
    models_available: bool
    summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


def _status(
    name: str, configured: bool, reachable: bool, authenticated: bool, exercised: bool, detail: str = ""
) -> DependencyStatus:
    return DependencyStatus(name, configured, reachable, authenticated, exercised, detail)


def check_database(dsn: str) -> DependencyStatus:
    if not dsn:
        return _status("database", False, False, False, False, "SETTLEMENT_DSN is not configured")
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as exc:
        return _status("database", True, False, False, False, f"database unreachable: {exc}")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM schema_migrations")
                pending = cur.fetchone()[0]
    except Exception as exc:
        return _status(
            "database", True, True, True, False, f"migration state not readable: {exc}"
        )
    return _status(
        "database", True, True, True, True, f"connected; {pending} migrations recorded"
    )


def check_artifacts(artifact_root: str, staging_root: str) -> DependencyStatus:
    if not artifact_root or not staging_root:
        return _status("artifacts", False, False, False, False, "artifact roots are not configured")
    if not (os.path.isdir(artifact_root) and os.path.isdir(staging_root)):
        return _status(
            "artifacts", True, False, False, False, "artifact roots are missing or not directories"
        )
    probe = os.path.join(staging_root, ".boot_probe")
    try:
        with open(probe, "w") as handle:
            handle.write("boot")
        with open(probe) as handle:
            exercised = handle.read() == "boot"
        os.unlink(probe)
    except OSError as exc:
        return _status("artifacts", True, True, True, False, f"staging round-trip failed: {exc}")
    if not exercised:
        return _status("artifacts", True, True, True, False, "staging round-trip mismatch")
    if not os.access(artifact_root, os.W_OK):
        return _status("artifacts", True, True, True, False, "artifact root is not writable")
    return _status("artifacts", True, True, True, True, "roots present; staging round-trip ok")


def check_sandbox(profile: str) -> DependencyStatus:
    from . import exec_profile

    if profile not in (exec_profile.GVISOR, exec_profile.LOCAL_PROCESS, exec_profile.SIMULATED):
        return _status("sandbox", False, False, False, False, f"unknown profile: {profile}")
    if profile == exec_profile.SIMULATED:
        return _status("sandbox", True, True, True, True, "simulated profile needs no runtime")
    if profile == exec_profile.GVISOR:
        probe = exec_profile.probe_gvisor()
        return _status(
            "sandbox", True, probe.available, probe.available, probe.available,
            f"[{profile}] {probe.reason}",
        )
    try:
        result = exec_profile.run_local_process(["/bin/true"], timeout_ms=5_000)
        alive = result.returncode == 0
    except Exception as exc:
        return _status("sandbox", True, False, False, False, f"local spawn failed: {exc}")
    return _status(
        "sandbox",
        True,
        alive,
        alive,
        alive,
        "local-process spawn ok (explicitly NOT containment)"
        if alive
        else "local-process spawn failed",
    )


def check_gateway(
    adapter: GatewayAdapter | None, endpoint: str, exercise: bool
) -> DependencyStatus:
    if adapter is None:
        return _status("gateway", bool(endpoint), False, False, False, "no gateway adapter wired")
    if isinstance(adapter, FakeGatewayAdapter):
        return _status(
            "gateway", True, True, False, False, "simulated adapter: live inference unavailable"
        )
    route = getattr(adapter, "route_contract", None)
    preflight = getattr(adapter, "preflight_route", None)
    if route is not None and callable(preflight):
        try:
            preflight_result = preflight(route)
        except Exception as exc:
            return _status("gateway", True, False, False, False,
                           f"model catalog preflight failed: {exc}")
        if isinstance(preflight_result, GatewayError):
            transport_failure = preflight_result.kind in (
                GatewayErrorKind.TRANSPORT, GatewayErrorKind.TIMEOUT
            )
            return _status(
                "gateway", True, not transport_failure, not transport_failure, False,
                f"model catalog refused: {preflight_result.message}",
            )
        if not exercise:
            return _status(
                "gateway", True, True, True, False,
                "model catalog validated; live inference not exercised",
            )
        operation_id = "boot-inference-probe"
        try:
            response = adapter.infer(ModelRequest(
                model=preflight_result["requested_model"],
                messages=({"role": "user", "content": "Reply with boot-ok."},),
                max_output_tokens=4,
                deadline_ms=30_000,
                operation_id=operation_id,
            ))
        except Exception as exc:
            return _status("gateway", True, True, True, False,
                           f"inference probe failed: {type(exc).__name__}: {exc}"[:500])
        if isinstance(response, ModelResponse) and response.operation_id == operation_id \
                and response.text.strip():
            return _status("gateway", True, True, True, True,
                           "model catalog and inference probe passed")
        detail = (response.message if isinstance(response, GatewayError)
                  else "invalid probe response")
        return _status("gateway", True, True, True, False, f"inference probe refused: {detail}")
    discovery = adapter.check_discovery()
    if isinstance(discovery, GatewayError):
        return _status("gateway", bool(endpoint), False, False, False, discovery.message)
    if discovery != GatewayStatus.REACHABLE:
        return _status("gateway", bool(endpoint), False, False, False,
                       f"gateway discovery status: {discovery}")
    auth = adapter.check_auth()
    if isinstance(auth, GatewayError):
        return _status("gateway", True, True, False, False, auth.message)
    if auth != GatewayStatus.AUTHENTICATED:
        return _status("gateway", True, True, False, False, f"gateway auth status: {auth}")
    return _status(
        "gateway", True, True, True, False,
        "authenticated; frozen model route and models body not validated",
    )


def check_interpreters() -> DependencyStatus:
    version = sys.version_info
    supported = (version.major, version.minor) >= (3, 12)
    if not supported:
        return _status(
            "interpreters", True, False, False, False,
            f"python {version.major}.{version.minor} below required 3.12",
        )
    try:
        proc = subprocess.run(
            [sys.executable, "--version"], capture_output=True, text=True, timeout=15
        )
        exercised = proc.returncode == 0
        detail = (proc.stdout or proc.stderr).strip()
    except (subprocess.SubprocessError, OSError) as exc:
        return _status("interpreters", True, True, True, False, f"interpreter spawn failed: {exc}")
    return _status(
        "interpreters", True, True, True, exercised,
        f"trusted interpreter {detail}" if exercised else "interpreter --version failed",
    )


def validate(
    settings: Settings,
    gateway_adapter: GatewayAdapter | None = None,
    admitted_profile: str = "gvisor",
    exercise_gateway: bool = False,
) -> BootReport:
    adapter = gateway_adapter
    if adapter is None and settings.gateway.endpoint:
        from .gateway_http import HttpGatewayAdapter

        adapter = HttpGatewayAdapter.from_settings(settings)
    entries = (
        check_database(settings.dsn),
        check_artifacts(settings.artifact_root, settings.staging_root),
        check_sandbox(admitted_profile),
        check_gateway(adapter, settings.gateway.endpoint, exercise_gateway),
        check_interpreters(),
    )
    by_name = {entry.name: entry for entry in entries}
    gateway = by_name["gateway"]
    gateway_ok = gateway.authenticated and (not exercise_gateway or gateway.exercised)
    models_available = gateway.exercised
    sandbox_ok = by_name["sandbox"].reachable
    ops = list(INSPECT_OPS)
    if models_available:
        ops.append(MODEL_OP)
    if sandbox_ok:
        ops.append(f"sandbox-exec:{admitted_profile}")
    ops.append(SIMULATED_OP)
    ok = all(
        [
            by_name["database"].exercised,
            by_name["artifacts"].exercised,
            by_name["interpreters"].reachable,
            sandbox_ok,
            gateway_ok,
        ]
    )
    code = ResultCode.APPLIED if ok else ResultCode.UNAVAILABLE_DEPENDENCY
    summary = f"boot {code.value}: " + ", ".join(
        f"{entry.name}={'ok' if entry.exercised else 'ready' if entry.reachable else 'limited'}"
        for entry in entries
    )
    return BootReport(
        ok=ok,
        entries=entries,
        available_operations=tuple(ops),
        models_available=models_available,
        summary=summary,
    )
