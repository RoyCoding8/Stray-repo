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

## Persistent investigations

`rsi.investigate.create` pins a development objective, genome, task, allocations
and maximum number of worker actions. `step` performs one action and pristine
check. A failed check leaves a named question open and retains the solution
snapshot. The next action receives that observation and those solution bytes in
a separate workspace. `run` continues within the pinned limit. A passing check
completes the objective; exhausting the limit leaves it unresolved.

The public CLI is `python -m rsi.investigate`. Its commands are `create`, `inspect`,
`step`, `suspend`, `resume` and `export`. Every command takes `--dsn`, `--id` and
`--root`. `create` also takes published `--genome` and `--task` digests, existing
`--token-allocation` and `--cpu-allocation`, and finite `--max-steps`,
`--timeout-ms` and `--token-ceiling` bounds. Worker commands use external
`--route-file` and `--codex` paths, as in the experiment below.
Use `--catalog-template` when the installed Codex catalogue lacks the launcher's
default template. This selects bundled tool metadata; it does not change the
gateway model named in the route file.

`resume` reuses the admitted operation identity before making another decision.
Suspension blocks new decisions and preserves already-admitted effects; it is not
process cancellation. `export` includes the decision and observation history and
unresolved operations. The task instrument accepts development tasks only, keeping
sealed tests and references out of continuation context. The existing archive
loop now uses this owner for development tasks with a one-action limit; its
frozen budgets and sealed comparison policy retain their existing meaning.

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
