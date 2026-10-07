# Project ledger

One page: current state, next work and known gaps. Keep it one page. History
lives in Git: the diary this replaced and every study, script and experiment
are at tag `archive/pre-subtraction-2026-10`.

## State (2026-10-07)

The repository is the `settlement` package: a durable execution substrate
for an autonomous agent. It has no agent loop yet.

| Area | Modules |
|---|---|
| Durable store | `db`, `store` (SERIALIZABLE transitions, command journal, outbox), `checkpoint`, `restore` |
| Effects | `broker` (prepare → dispatch → observe → reconcile; a crash never re-sends a settled effect), `run` (composition interpreter) |
| Bounded execution | `launcher_local`, `launcher_runsc`, `exec_profile`, `child_limits`, `winjob` (Windows Job Objects), `attestation` |
| Models | `gateway` (adapter interface plus a fake), `gateway_http` (OpenAI-style chat completions), `config` |
| Knowledge | `artifacts` (content-addressed packages), `capabilities` (versioned methods, releases, quarantine), `evidence`, `context` |
| Budgets and studies | `steward`, `trials`, `evaluation`, `authority`, `loop`, `agenda`, `agenda_policy` |
| Operator | `api` (FastAPI inspection UI), `boot` (dependency checks) |

The last row of study-shaped modules is entangled with `api`. P2 replaces
them and then deletes them.

Verification:
- Kept suite on Windows with PostgreSQL 18: 569 passed, 19 skipped
  (POSIX-only mechanisms and the symlink privilege), 0 failed.
- CI run 37669366485: every job green on Ubuntu, macOS, Windows, both DB
  shards and heavy archived; about 4 minutes.

## Next

Follow `tmp/PLANS.md` locally, or the summary here:

1. **P2 kernel.** One SQL-owned mission runtime: goal → model decision →
   admitted bounded action → receipt → next step. Commands `run`, `resume`
   and `show`. Done when a scripted-model mission survives a process kill
   without repeating a settled effect.
2. **P3 real model.** Needs a model route chosen by the user.
3. **P4 skill reuse.** Measured against a no-memory baseline on held-out
   tasks.
4. **P5 product.** UI, installation and docs.

## Known gaps

- There is no agent loop and no user-facing entry point (P2).
- Windows children get memory, CPU and kill-tree bounds through Job Objects,
  but no filesystem or network containment.
- 21 migrations still create tables for retired studies (`s09_*`, `team_*`,
  `agenda_*`, `inv_r1_study_runs`). Drop them in the P2 schema work.
- `reports/` and the `evidence*` directories hold frozen evidence from
  retired studies. They are not used by code or tests.
