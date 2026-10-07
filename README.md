# Agent Society

Infrastructure for an autonomous agent that finds problems, builds and runs
executable capabilities, and keeps what works. Today the repository holds the
durable execution substrate (`src/settlement`). The agent loop is the next
phase.

| Read | For |
|---|---|
| [Project ledger](reports/PROJECT-LEDGER.md) | Current state, next work, known gaps |
| [Roadmap](docs/design/REFINEMENT-ROADMAP.md) | Philosophy |
| [Design index](docs/design/README.md) | Concepts and mechanisms |
| [CI](docs/CI.md) | Remotes and what CI checks |

Studies, scripts and experiments from earlier stages were removed from the
main line. They are preserved at tag `archive/pre-subtraction-2026-10`.
Recover a path with `git checkout archive/pre-subtraction-2026-10 -- <path>`.

## Development

Use Python 3.12 or newer and `uv sync --extra test`.

- Tests that need no database: `python -m pytest`.
- Database tests need a disposable PostgreSQL server. Set:
  - `SETTLEMENT_TEST_DSN` (an admin route, for example
    `dbname=postgres host=127.0.0.1 port=5432 user=postgres`)
  - `S09ISO_ADMIN_DSN` (the same route)
  - `S09ISO_TOKEN` (8 lowercase hex digits)
  - `SETTLEMENT_REQUIRE_TEST_DB=1`

  Each session creates its databases and drops them afterwards.
- `tests/_heavy_archived/` spawns many real children. Run it one file at a
  time.

Keep gateway configuration and credentials outside Git.
