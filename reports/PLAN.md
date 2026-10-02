# S0-S3 implementation plan

Base: `be7956d` (`origin/codex/architecture-handoff`).
Integration branch: `codex/implementation-s0-s3` (coordinator only).

Shared contracts (coordinator-owned, settled before split):
`src/settlement/common.py` (command/result envelope, error vocabulary),
`src/settlement/gateway.py` (adapter ABC, typed errors, fake adapter for tests),
`src/settlement/db.py` (DSN, connection, migration runner),
`src/settlement/config.py` (typed settings, no secrets),
`tests/conftest.py` (per-task isolated database fixture),
`pyproject.toml` + `uv.lock` (dependency pins).

Test-resource isolation: one PostgreSQL database per task
(`settlement_t0env`, `settlement_t1state`, ...), own venv per worktree,
own scratch roots via pytest `tmp_path`. Worktrees live beside the checkout
as `../Agent-Society-v2-<task-id>`. Git worktrees separate checkouts only;
databases, ports and runtime state are isolated per task as listed.

## Tasks

| ID | Slice | Req IDs | Owner branch / worktree | Owned paths | Depends on | Checks (real infra marked *) | Status |
|---|---|---|---|---|---|---|---|
| T0 | baseline | — | integration / main checkout | pyproject, uv.lock, common, gateway ABC, db, config, conftest, reports/PLAN | — | `uv lock --check`, import smoke | done |
| T1 | S0 env/gateway/profile | BOOT-1..4, IF-5gw, S0 gate | `codex/task-s0-env` / `../Agent-Society-v2-s0-env` | `src/settlement/gateway_http.py`, `exec_profile.py`, `boot.py`, `scripts/manifest.py`, `tests/test_s0_*.py` | T0 | unit + discovery/auth/inference checks separated; `runsc` probe reports explicit incompatible on this host; manifest script prints versions | merged (`451457b` + review fixes T1-R01..R03 in `b5b5b0c`) |
| T2 | S1 durable state | TX-1..6, IF-1/2/5, EFF-1/2/4, BOOT-5, §4 tables, §15 races | `codex/task-s1-state` / `../Agent-Society-v2-s1-state` | `migrations/`, `src/settlement/store.py`, `tests/test_tx_*.py`, `tests/test_state_*.py` | T0 | pytest on real Postgres*; reservation race, duplicate command/receipt, stale ownership, outbox crash repair, event-cursor gap | merged (`6403cb9` + review extension below) |
| T3 | S1 broker/exec | EFF-1..9, RUN-1..4, AGENDA-4, §15 broker cases | `codex/task-s1-broker` / `../Agent-Society-v2-s1-broker` | `src/settlement/broker.py`, `launchers/`, `run.py`, `tests/test_broker_*.py`, `tests/test_run_*.py` | T2 merged | real-PG* fault injection at every effect boundary; runsc path gated by probe, never silent fallback | pending |
| T4 | S2 artifacts/evidence | ART-1..4, IF-3, RUN-2/5, §4 claims/derivations | `codex/task-s2-evidence` / `../Agent-Society-v2-s2-evidence` | `src/settlement/artifacts.py`, `evidence.py`, `context.py`, `tests/test_s2_*.py` | T2 merged | real-PG* + real filesystem*; retraction race, missing-bytes detection, fresh-worker resume with pending effects | merged (`dbda101` + review fixes T4-R01/R02/R03/R04/R09/R10/R11/R12/R13/R14; note: the "92 passed" in the T4 report was the whole-suite count, S2 files hold 21 tests) |
| T5 | S3 learning/trials | LEARN-1..9, IF-4/6/7, §11 A/B/C | `codex/task-s3-learning` / `../Agent-Society-v2-s3-learning` | `src/settlement/capabilities.py`, `trials.py`, `evaluation.py`, `experiment.py`, fixtures, `tests/test_s3_*.py` | T2+T3 merged | frozen protocol, matched resources, fresh-worker invocation of retained method; simulated arms labeled simulated | pending |
| T6 | operator/agenda | UI-1..5, IF-1 steward, AGENDA-1..5 | `codex/task-s1-operator` / `../Agent-Society-v2-s1-operator` | `src/settlement/steward.py`, `agenda.py`, `api.py`, `templates/`, `tests/test_ui_*.py` | T2 merged (API shape), T3/T5 for views | UI usable with gateway down; idempotent commands; generated content inert | pending |
| T7 | validation/recovery | REC-1..4, §15 full map, §16 report split | `codex/task-s0-validate` / `../Agent-Society-v2-s0-validate` | `tests/test_adv_*.py`, `scripts/checkpoint.py`, `reports/VERIFICATION.md` (coordinator merges) | after T3+T4 merged | Hypothesis state machines on real PG*; restore into fenced env; live-gateway gates marked unverified until endpoint exists | pending |

Rules: specialists commit + push only their own branch, write
`reports/workstreams/<task-id>.md`, never edit another task's paths or
`reports/PLAN.md`, `pyproject.toml`, `uv.lock`, `src/settlement/common.py`,
`src/settlement/gateway.py`, `src/settlement/db.py`, `src/settlement/config.py`.
Contract change requests go in the task report; the coordinator decides.
Coordinator integrates one task at a time in dependency order with normal
merges and reruns affected checks.

Review extensions on the integration branch (coordinator-owned, with finding IDs):
- T1-R01..R03 (`b5b5b0c`): defensive usage decode, `cancel_status` unknown, gvisor dispatch reason.
- T2-R01 (`actual_cost` on settle/admit_receipt + `tests/test_settle_actual.py`): settle consumes
  measured cost and releases the unused remainder (I2); unknown outcomes still retain full exposure.
- T2-R02 (`get_control` ensures the control row; `allocation_status` read helper for broker/UI).
- T2-R03 (recorded, not fixed): the `allocations` CHECK covers `consumed + reserved <= authorized`
  but not subdivided children; child capacity is enforced by the serialized Python check under the
  control lock. A DB-level backstop for children is deferred.
- T2-R04 (for T6): no transition bumps an existing attempt's ownership generation; lease
  expiry/revocation policy must add its own transition (new migration, coordinator-approved).

Migration sequencing: T4 owns `migrations/0002_*.sql` (artifacts, claims, derivations, context),
T5 owns `migrations/0003_*.sql` (capabilities, trials, releases). Each task touches only its tables.

Waves: (1) T1 + T2 in parallel — done, both merged. (2) T3 + T4 in parallel after T2 merges.
(3) T5 + T6 in parallel after T3 merges. (4) T7 validation, A/B/C run,
final reports and review request.
