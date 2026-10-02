from __future__ import annotations

import os
from pathlib import Path

import psycopg


def resolve_dsn(explicit: str | None = None) -> str:
    dsn = explicit or os.environ.get("SETTLEMENT_DSN", "")
    if not dsn:
        raise RuntimeError("SETTLEMENT_DSN is not configured")
    return dsn


def connect(dsn: str, **kwargs):
    kwargs.setdefault("autocommit", False)
    return psycopg.connect(dsn, **kwargs)


READ_CONNECT_TIMEOUT_S = 10
READ_STATEMENT_TIMEOUT = "60s"


def read_connect(dsn: str):
    return connect(dsn, connect_timeout=READ_CONNECT_TIMEOUT_S,
                   options=f"-c statement_timeout={READ_STATEMENT_TIMEOUT}")


def apply_migrations(dsn: str, migrations_dir: str | Path) -> list[str]:
    files = sorted(Path(migrations_dir).glob("*.sql"))
    applied: list[str] = []
    with connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations"
                " (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            for path in files:
                cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (path.name,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text())
                cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
                applied.append(path.name)
    return applied
