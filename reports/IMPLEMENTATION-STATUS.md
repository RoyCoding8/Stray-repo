# Implementation status (S0-S3)

Base commit: `be7956d`. Integration branch: `codex/implementation-s0-s3`.

## Slices

- S0: pending (T1).
- S1: pending (T2, T3, T6).
- S2: pending (T4).
- S3: pending (T5).

## Entry points

- Package: `src/settlement/` (`common`, `gateway`, `db`, `config` settled).
- Setup: `uv sync` (once `uv.lock` exists), per-task database
  `postgresql://ubuntu@/settlement_<task>?host=/var/run/postgresql`.
- Run/test: `SETTLEMENT_TEST_DSN=<dsn> uv run pytest`.

## Environment limitations

- PostgreSQL 16 locally (deployment target PG18, see D-001).
- No Docker/`runsc` on this host: gVisor profile reports incompatible (see D-002).
- No live inference endpoint yet: gateway checks past discovery/auth/inference
  separation only with fake adapter; live gate unverified.
