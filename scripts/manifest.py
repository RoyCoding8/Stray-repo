from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def locked_packages(lock_path: Path | None = None) -> dict[str, str]:
    path = lock_path or ROOT / "uv.lock"
    with open(path, "rb") as handle:
        lock = tomllib.load(handle)
    return {entry["name"]: entry["version"] for entry in lock.get("package", [])}


def postgres_version(dsn: str = "") -> str:
    target = dsn or os.environ.get("SETTLEMENT_DSN", "")
    if not target:
        return "unknown (SETTLEMENT_DSN is not configured)"
    try:
        import psycopg

        with psycopg.connect(target, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW server_version")
                row = cur.fetchone()
    except Exception as exc:
        return f"unknown ({exc})"
    return str(row[0]) if row else "unknown"


def sandbox_state() -> dict[str, Any]:
    from settlement import exec_profile

    probe = exec_profile.probe_gvisor()
    return {
        "runsc_present": shutil.which("runsc") is not None,
        "docker_present": shutil.which("docker") is not None,
        "gvisor_available": probe.available,
        "gvisor_reason": probe.reason,
    }


def build_manifest() -> dict[str, Any]:
    from settlement.config import Settings
    from settlement.gateway_http import CONTRACT

    settings = Settings.from_env()
    resources = settings.resources
    return {
        "python": platform.python_version(),
        "packages": locked_packages(),
        "postgres": postgres_version(),
        "sandbox": sandbox_state(),
        "kernel": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "limits": {
            "max_concurrent_attempts": resources.max_concurrent_attempts,
            "max_concurrent_operations": resources.max_concurrent_operations,
            "attempt_deadline_ms": resources.attempt_deadline_ms,
            "operation_deadline_ms": resources.operation_deadline_ms,
            "scratch_bytes": resources.scratch_bytes,
            "output_bytes": resources.output_bytes,
            "gateway_endpoint_configured": bool(settings.gateway.endpoint),
            "gateway_timeout_connect_ms": settings.gateway.timeout_connect_ms,
            "gateway_timeout_read_ms": settings.gateway.timeout_read_ms,
            "gateway_timeout_total_ms": settings.gateway.timeout_total_ms,
        },
        "gateway_contract": CONTRACT,
    }


def main() -> None:
    print(json.dumps(build_manifest(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
