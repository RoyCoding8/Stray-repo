# Agent Society

An experimental infrastructure for autonomous investigation, executable capability acquisition and transfer. The system should learn how to investigate and improve its methods; it should not stop at storing advice in prompts.

| Read this | For |
|---|---|
| [Current inventory](reports/PROJECT-INVENTORY.md) | What exists, current evidence, stages and the Git/workspace map |
| [Worker prompt](WORKER-PROMPT.md) | The current complete assignment and acceptance conditions |
| [Project ledger](reports/PROJECT-LEDGER.md) | Verified state, open work and next decisions |
| [Roadmap](docs/design/REFINEMENT-ROADMAP.md) | Philosophy through final implementation |
| [Implementation workflow](IMPLEMENTATION-WORKFLOW.md) | Parallel ownership, integration, verification and cleanup |
| [Design index](docs/design/README.md) | Architecture and mechanism specifications |
| [Latest transfer assessment](reviews/STAGE-09-TRANSFER-ASSESSMENT.md) | Material findings behind the current assignment |
| [History index](docs/HISTORY.md) | Retired prompts and diaries, recoverable from Git |

Stage 9 remains active. Fifteen capability areas have code, with seven foundation and eight cognitive areas. The latest narrow studies do not establish useful general learning or complete the expanded comparison. See the inventory and ledger for their evidence boundaries.

The current implementation snapshot is on `codex/implementation-development-01`, despite its older name. The remote default still points at `codex/architecture-handoff`; explicitly select the implementation branch when starting from a fresh clone.

## Development

Use Python 3.12 or newer and the repository environment (`uv sync --extra test`). Database-backed checks require explicit disposable PostgreSQL configuration; use the relevant test's documented DSN variables.

Some candidate-execution checks depend on the Linux resource/execution profile. A Windows import failure is not evidence against Linux qualification, and disabling execution limits is not a valid portability fix.

Keep gateway configuration and credentials outside Git. Discover and verify the current route rather than copying endpoints or model assumptions from old reports.
