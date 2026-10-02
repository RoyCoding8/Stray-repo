# Brief: public entry and toolchain (surveyor ses_f437b5fe0ffetGZYOrFJ5m9GKM)

## Entry points

- `src/settlement/broker.py`: `dispatch_operation(dsn, operation_id, ...)`, `dispatch_pending(...)`, `attempt_workflow(...)`.
- `src/settlement/team.py`: `dispatch_child(...)`.
- `src/settlement/development.py`: `collect_experience(...)`.
- `src/settlement/experiment.py`: `run_abcs(...)`, `run_subsequent_use(...)`.

## Callers

`capabilities.py`, `experiment.py`, `development.py`, `representation.py`, `team.py` call `broker.dispatch_operation` directly.
`scripts/scheduler.py` calls `broker.dispatch_pending` in a retry loop.
`scripts/agenda01.py` calls `broker.dispatch_operation` from the operator CLI.
Tests call `dispatch_operation` and `DBOS.start_workflow(broker.attempt_workflow, ...)` directly.

## Repo setup

Python `>= 3.12`. Lock file `uv.lock`. Runner pytest with `testpaths = ["tests"]`.
Exact test command: `SETTLEMENT_TEST_DSN=<dsn> uv run --frozen pytest`. Tests skip without `SETTLEMENT_TEST_DSN`.
Suite: 142 `test_*.py` files plus `conftest.py`. Fixtures truncate Postgres tables, require live DSN.
Config example: `config/.env.example` with DSN, gateway endpoint, key env name, artifact roots.

## Toolchain

System Python 3.12.3. `uv` 0.12.9. Postgres accepting connections, server 16.15.
No system `pytest` or `psycopg` outside the locked venv.

## Structural observation

Three drivers converge the same work with no single owner: `broker.heartbeat`/`broker.recover`, `agenda.repair_scan` with `collect_wakeups`, `scripts/scheduler.run_once`.
A reader must trace all three to know who moved an operation. This is the duplicated orchestration lane B must replace.
