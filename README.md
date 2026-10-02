# Agent Society

An experimental infrastructure for autonomous investigation, executable capability acquisition and transfer. The system should learn how to investigate and improve its methods; it should not stop at storing advice in prompts.

| Read this | For |
|---|---|
| [Worker prompt](WORKER-PROMPT.md) | The current complete assignment and acceptance conditions |
| [Project ledger](reports/PROJECT-LEDGER.md) | Verified state, open work and next decisions |
| [Roadmap](docs/design/REFINEMENT-ROADMAP.md) | Philosophy through final implementation |
| [Implementation workflow](IMPLEMENTATION-WORKFLOW.md) | Parallel ownership, integration, verification and cleanup |
| [Design index](docs/design/README.md) | Architecture and mechanism specifications |
| [Latest transfer assessment](reviews/STAGE-09-TRANSFER-ASSESSMENT.md) | Material findings behind the current assignment |
| [History index](docs/HISTORY.md) | Retired prompts and diaries, recoverable from Git |

Stage 9 remains active. The latest reviewed delivery contains useful instruments and a small live reducer experiment with worse results than its control. It does not complete the expanded representation, experience, transfer and learner-revision comparison. See the ledger for evidence boundaries.

## Development

Use Python 3.12 or newer and the repository environment (`uv sync --extra test`). Database-backed checks require explicit disposable PostgreSQL configuration; use the relevant test's documented DSN variables.

Some candidate-execution checks depend on the Linux resource/execution profile. A Windows import failure is not evidence against Linux qualification, and disabling execution limits is not a valid portability fix.

Keep gateway configuration and credentials outside Git. Discover and verify the current route rather than copying endpoints or model assumptions from old reports.
