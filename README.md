# Agent Society

An autonomous system that improves agents and their improver, keeping changes
only when evidence supports them. `src/settlement` owns budgets, execution,
receipts and artifacts. `src/rsi` versions the genome that Codex CLI reads,
runs recorded episodes, and verifies solutions against a frozen task bank.
The genome archive records fixed parent selection and attributed decisions.
A meta-agent proposes child genomes from development evidence using editable
meta instructions. A frozen gate checks validation, solved-task regressions
and fresh anchor outcomes at a matched model and execution budget. Cooperative
benchmark gains remain experimental; trusted promotion requires containment.

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

## Bounded improvement experiments

Create a genome directory with `AGENTS.md` and `meta/IMPROVE.md`. Use a
qualified bank report whose task packages already exist in the same database
and artifact root. Keep the route file and credentials outside Git.

```powershell
$env:PYTHONPATH = 'src'
& .venv/Scripts/python.exe -m rsi.experiment `
  --dsn 'dbname=rsi_t5 host=127.0.0.1 port=55432 user=postgres' `
  --root D:/AI/tools/rsi-t5 --seed D:/AI/tools/rsi-t9-seed `
  --bank-report D:/AI/tools/rsi-t5/bank-report.json `
  --route-file D:/AI/tools/model-route.env `
  --codex C:/Users/roysh/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe `
  --run-id experiment-01 --generations 2 --tokens 150000 --timeout-ms 300000 `
  --dev proverb --val transpose `
  --anchor affine-cipher bottle-song bowling list-ops poker tree-building `
  --migrations migrations
```

The loop records fixed parent selection, AI proposals and fixed gate decisions.
Its JSON report includes failed attempts, unknown outcomes and a stopping reason.
A repeated run ID returns the recorded result; changed parameters require a
new ID. A run stops after spending its anchor exposure. New comparisons require
fresh anchor content; a new epoch alone cannot authorize reuse.

These native runs are cooperative benchmarks. Stronger sandboxing is deferred;
process and resource limits remain active. Benchmark acceptance records
`experimental_gain`. Trusted mode requires proved execution containment and
blocks these launchers. The [live report](reports/evidence/rsi-t9/report.json)
records three dev timeouts and one improver timeout, with no child or gain.

`rsi.synthesis.run` proposes a new task from completed dev failures, pins its
output, and runs its reference and stub in fresh verifier processes. Only a
passing reference and failing stub permit publication to the dev registry.
Held-out content duplicates are rejected. AI proposal and fixed qualification
have separate decision records. Qualification checks executable behavior;
it does not prove the AI-written specification or tests are correct. A future
epoch can select qualified tasks without modifying a frozen evaluator.
