# Agent Society

An autonomous system that improves agents and their improver, keeping changes
only when evidence supports them. `src/settlement` owns budgets, execution,
receipts and artifacts. `src/rsi` versions the genome that Codex CLI reads,
runs recorded episodes, and verifies solutions against a frozen task bank.
The genome archive records fixed parent selection and attributed decisions.
Genome proposals and the acceptance gate are still to build.

| Read | For |
|---|---|
| [Project ledger](reports/PROJECT-LEDGER.md) | Current state, next work, known gaps |
| [Roadmap](docs/design/REFINEMENT-ROADMAP.md) | Philosophy |
| [Design index](docs/design/README.md) | Concepts and mechanisms |
| [CI](docs/CI.md) | Remotes and what CI checks |

Studies, scripts and experiments from earlier stages were removed from the
main line. The remaining study controllers, context/evidence layer and 49 study tables
are retired; the operator pages inspect RSI lineage, episodes and verdicts.
Historical migration files remain unchanged. They are preserved at tag `archive/pre-subtraction-2026-10`.
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

Import an Exercism Python practice bank and check its references and stubs
without model calls:

```powershell
$env:PYTHONPATH = 'src'
& .venv/Scripts/python.exe -m rsi.task_bank `
  --source D:/AI/tools/polyglot-benchmark/python/exercises/practice `
  --root D:/AI/tools/rsi-t5 `
  --dsn 'dbname=rsi_t5 host=127.0.0.1 port=55432 user=postgres' `
  --migrations migrations
```

Use an existing database for that command. The root must be outside agent
workspaces. `bank-report.json` records the frozen bank digest, deterministic
dev/val/anchor splits and sanity results. Task agents receive only the
instruction and solution slots; pristine tests and references stay with the
kernel. Anchor tasks, trajectories and solution snapshots carry the hidden
access label. A successful reference and a failing stub qualify each task.

Publish a `rsi.task.Task` before passing it to `rsi.episode.run_episode`.
After a completed episode, `rsi.verifier.verify_episode` runs a separately
admitted verifier operation and records its evaluator version and solution
snapshot in `rsi_verdicts`. Repeating verification returns the recorded result.
Timeouts and infrastructure errors have no passing/failing score. The local
verifier launcher bounds processes but does not confine filesystem/network
access; these benchmark checks do not certify hostile code.
