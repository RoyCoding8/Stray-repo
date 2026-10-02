# M5 cap sheet Investigation Learning 02

Status: superseded by reports/cap-sheets/invl02-live-grant.md. The human authorized live Nemotron testing on 2026-09-23 and retired the historical call limit. The placeholder command below is withdrawn. It never ran.

Withdrawn placeholder. It used flags the entry point does not accept and a configuration file that does not exist.

Real pilot syntax observed from scripts/s09_pilot.py main. Freeze with freeze --out DIR. Run with run --dsn DSN --out DIR with optional --mode doubles or live and optional --model ID. Live refuses without S09_M5_LIVE_GRANT and requires explicit --model. Gateway comes from SETTLEMENT_GATEWAY_ENDPOINT and SETTLEMENT_GATEWAY_KEY through Settings.

Live command shape actually supported:
set -a plus source of the environment file outside Git plus set plus S09_STUDY_CALLS_ALREADY_SPENT equals 0. Then PYTHONPATH dot plus experiments uv run python scripts/s09_pilot.py run --dsn postgres template with DB name --out evidence dir --mode live --model request identifier.
Then: PYTHONPATH dot plus experiments uv run python scripts/s09_verify.py bundle dir.

The new investigation driver command lands here after its first real run. No new live allocation beyond the recorded grant. Routing constraints and stop rule from the live grant apply.
