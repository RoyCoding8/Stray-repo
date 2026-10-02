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
| T3 | S1 broker/exec | EFF-1..9, RUN-1..4, AGENDA-4, §15 broker cases | `codex/task-s1-broker` / `../Agent-Society-v2-s1-broker` | `src/settlement/broker.py`, `launchers/`, `run.py`, `tests/test_broker_*.py`, `tests/test_run_*.py` | T2 merged | real-PG* fault injection at every effect boundary; runsc path gated by probe, never silent fallback | merged (`e127799` + review fixes T3-R01/R02/R04/R06/R07/R08; `note_worker_stopped` stays broker-owned via the public transact envelope; schedulers must call `heartbeat(..., repair_due=True)` periodically or `retry-later` never fires) |
| T4 | S2 artifacts/evidence | ART-1..4, IF-3, RUN-2/5, §4 claims/derivations | `codex/task-s2-evidence` / `../Agent-Society-v2-s2-evidence` | `src/settlement/artifacts.py`, `evidence.py`, `context.py`, `tests/test_s2_*.py` | T2 merged | real-PG* + real filesystem*; retraction race, missing-bytes detection, fresh-worker resume with pending effects | merged (`dbda101` + review fixes T4-R01/R02/R03/R04/R09/R10/R11/R12/R13/R14; note: the "92 passed" in the T4 report was the whole-suite count, S2 files hold 21 tests) |
| T5 | S3 learning/trials | LEARN-1..9, IF-4/6/7, §11 A/B/C | `codex/task-s3-learning` / `../Agent-Society-v2-s3-learning` | `src/settlement/capabilities.py`, `trials.py`, `evaluation.py`, `experiment.py`, fixtures, `tests/test_s3_*.py` | T2+T3 merged | frozen protocol, matched resources, fresh-worker invocation of retained method; simulated arms labeled simulated | merged (`5f44470` + integration fixes T5-R01..R06; T6 absence-simulation tests made monkeypatch-robust) |
| T6 | operator/agenda | UI-1..5, IF-1 steward, AGENDA-1..5 | `codex/task-s1-operator` / `../Agent-Society-v2-s1-operator` | `src/settlement/steward.py`, `agenda.py`, `api.py`, `templates/`, `tests/test_ui_*.py` | T2 merged (API shape), T3/T5 for views | UI usable with gateway down; idempotent commands; generated content inert | merged (`c40c0aa` + review fixes T6-R01/R02/R03/R04/R05/R06; trial/release views still pending T5 wiring) |
| T7 | validation/recovery | REC-1..4, §15 full map, §16 report split | `codex/task-s0-validate` / `../Agent-Society-v2-s0-validate` | `tests/test_adv_*.py`, `scripts/checkpoint.py`, `reports/VERIFICATION.md` (coordinator merges) | after T3+T4 merged | Hypothesis state machines on real PG*; restore into fenced env; live-gateway gates marked unverified until endpoint exists | merged (`dc102ea` + integration fixes T7-F01/T7-F02/T7-F03 below) |

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

## REVIEW-01 fix cycle (base `381346a`, review branch merged as history)

| ID | Findings | Owner branch / worktree | Owned paths | Test DB | Status |
|---|---|---|---|---|---|
| R1a | R01-001/002 (sole store/broker owner, first) | `codex/review01-r01-admit` / `../Agent-Society-v2-r01-admit` | `store.py`, `broker.py` dispatch/admission only | `settlement_r01admit` | pending (R1 oversized attempt failed clean; split into sequential slices) |
| R1b | R01-003/004 + R01-S02 (after R1a, same branch) | `codex/review01-r01-admit` / `../Agent-Society-v2-r01-admit` | fulfillment, launcher fencing, `steward.py` lease | `settlement_r01admit` | done `1369711`, 21 new pass; existing-test fallout migrated by R1c, NOT merged |
| R1c1 | heal R01-003/004 fallout (same admit branch) | `codex/review01-r01-admit` / `../Agent-Society-v2-r01-admit` | migrated tests, explicit redispatch, generation-aware launcher claim | `settlement_r01admit` | done `406e9ed`, full branch suite green |
| R1c2 | R01-006/013 + R01-014 store side (same admit branch) | `codex/review01-r01-admit` / `../Agent-Society-v2-r01-admit` | `scripts/checkpoint.py`, `scripts/restore.py`, wf continuation | `settlement_r01admit` | done `7856b2a` + follow-up `5334d13`; admit slice MERGED (`6adfd4f`) |
| R2 | R01-005 | `codex/review01-r01-runsc` / `../Agent-Society-v2-r01-runsc` | `src/settlement/launcher_runsc.py`, `exec_profile.py`, `tests/test_*runsc*.py`, `tests/test_*gvisor*.py` | `settlement_r01runsc` | pending |
| R3 | R01-007 | `codex/review01-r01-evidence` / `../Agent-Society-v2-r01-evidence` | `src/settlement/evidence.py`, `tests/test_*evidence*.py`, `tests/test_s2_*.py` (`db.py` changes via coordinator request only) | `settlement_r01evidence` | pending |
| R4a | R01-008 (grader isolation) | `codex/review01-r01-evalexp` / `../Agent-Society-v2-r01-evalexp` | `experiments/run_tests.py`, `experiment.py` grade region only | `settlement_r01evalexp` | pending (R4 oversized attempt failed clean; split) |
| R4b | R01-009/010 (release binding, parallel-safe: disjoint files) | `codex/review01-r01-eval-b` / `../Agent-Society-v2-r01-eval-b` | `trials.py`, `evaluation.py`, `capabilities.py` | `settlement_r01evalb` | pending |
| R4c | R01-011/012 (experiment rebuild, on merged base) | `codex/review01-r01-eval-c` / `../Agent-Society-v2-r01-eval-c` | `experiment.py` run path, `experiments/run_live_abc.py` | `settlement_r01evalc` | done `e587df2`, MERGED (fast-forward) |
| R5 | R01-014 gateway side + R01-015 + R01-S01 | `codex/review01-r01-deadline-ui` / `../Agent-Society-v2-r01-deadline-ui` | `src/settlement/gateway_http.py`, `api.py`, `agenda.py`, `templates/`, `tests/test_ui_*.py`, `tests/test_s0_gateway*.py` | `settlement_r01deadline` | pending |

Authorship note: on user instruction, all 56 commits in
`origin/codex/architecture-handoff..HEAD` were rewritten author/committer-wide
to `ubuntu <ubuntu-968db71cad01@noreply.local>` with identical trees and
force-pushed once (`093e757` → `4884d24`). SHAs cited in older workstream
reports predate the rewrite; messages are unchanged. Task branches
`codex/review01-*` were already `Ubuntu`-authored and untouched.

Rules: fix specialists commit + push only their own `codex/review01-*`
branch, `git add` only files they created/edited (never `git add -A`),
write `reports/workstreams/<task-id>.md`, and record any needed
`common.py`/`gateway.py`/`db.py`/`config.py` change as a contract request
in the task report instead of editing it. Coordinator integrates with
explicit merges in R1 → R3 → R4 → R2 → R5 order (shared-transition owner
first) and reruns affected checks after each merge.

## REVIEW-02 fix cycle (base `6197865`: `2455e93` + review-02 handoff content)

Review histories are unrelated (implementation rewritten at human request);
the handoff (`reviews/REVIEW-02.md`, `reviews/probes/test_review_02.py`,
`WORKER-REVIEW-02-PROMPT.md` at review tip `3268620`) was integrated
content-only, without joining obsolete pre-rewrite ancestry.

Coordinator-set cross-cutting contracts (settled before split, all workers
must implement against these, no unilateral redefinition):

- C1 billing: `Usage` gains `billed: bool = False`, set True only when the
  provider response carries an explicit priced charge. Broker passes
  `actual_cost = usage.charge_units if usage.billed else None`; store
  `_settle_amount` is unchanged (`None` consumes the full reservation:
  unknown billing retains conservative exposure). Receipt usage dicts carry
  the billed flag for audit. Fake/simulated adapters report billed=False,
  so tests asserting zero cost after fake sends encode the old bug and must
  be migrated to conservative exposure (or use explicit billed Usage where
  a priced path is under test).
- C2 generations: `ModelRequest` gains `dispatch_generation: int = 0`
  (coordinator-owned `gateway.py` edit, already committed in the base).
  `BrokerOp` generation stamping is W-A owned; launchers must refuse stale
  generations without producing external effects (W-B implements runsc
  side against W-A's field, read-only).
- C3 migrations: W-A owns `migrations/0004_*` (recovery/barrier), W-C owns
  `migrations/0005_*` (evaluation binding). No other task touches
  `migrations/`.
- C4 review probes in `reviews/probes/test_review_02.py` are
  revision-specific evidence: 8 defect tests MUST fail after repair, the
  import-time forgery test MUST keep passing. Add positive regressions for
  each corrected contract; never weaken a probe to green.

| ID | Findings | Owner branch / worktree | Owned paths | Test DBs | Depends on |
|---|---|---|---|---|---|
| W-A | R02-001/002/003/004/005 + store-side R02-011/012 | `codex/r02-authority` / `/tmp/asv2-r02-r02-authority` | `store.py`, `broker.py`, `run.py`, `scripts/checkpoint.py`, `scripts/restore.py`, `migrations/0004_*`, owned tests | `settlement_r02auth` (+`_restore`,`_wf`) | C1–C4 |
| W-B | R02-006 + gateway-side R02-011/012 | `codex/r02-exec` / `/tmp/asv2-r02-r02-exec` | `exec_profile.py`, `launcher_runsc.py`, `gateway_http.py`, owned tests | `settlement_r02exec` | C1–C4, C2 read-only |
| W-C | R02-008/009 | `codex/r02-evalbind` / `/tmp/asv2-r02-r02-evalbind` | `evaluation.py`, `capabilities.py`, `trials.py`, `migrations/0005_*`, owned tests | `settlement_r02eval` | C1–C4 |
| W-D | R02-007/010 + CLI-side R02-011 | `codex/r02-explearn` / `/tmp/asv2-r02-r02-explearn` | `experiment.py`, `experiments/`, `launcher_local.py`, owned tests | `settlement_r02exp` | C1–C4 |

Rules: fix specialists commit only their own branch, `git add` only files
they created/edited (never `git add -A`), write
`reports/workstreams/r02-<name>.md`, never edit another task's paths,
`reports/PLAN.md`, shared contracts, or coordinator reports. No
`launcher_local.py` edits by W-B; no `broker.py`/`store.py` edits by
W-B/W-C/W-D; no `gateway_http.py` edits by W-A/W-C/W-D. Integration order:
W-A → W-C → W-D → W-B (authority core first), one merge at a time with
affected checks rerun. Temp worktrees under `/tmp/asv2-r02-*` are removed
after integration.

REVIEW-02 completion record: all R02 lanes merged into
`codex/implementation-s0-s3` (`72cfa11`); full suite 418 passed
(`reports/VERIFICATION.md`, R02 section). Temp worktrees removed.

## REVIEW-03 fix cycle (base `20017f2`, review branch merged as history)

Reviewed source `72cfa11`; review tip `83d8f0a`
(`origin/codex/review-s0-s3-03`). All 12 specification findings confirmed
against production entry points; no rebuttals. Shared-file regions were
partitioned per lane (broker: exposure/SUP, Protocol/EVAL, workflow/FLOW;
launcher_runsc: fence-retention/SUP, staging-ctor/EVAL; store: integrity/DATA,
barrier/FLOW); the probe file was partitioned by test function.

| ID | Findings | Owner branch / worktree | Owned paths | Test DB | Status |
|---|---|---|---|---|---|
| W-DATA | R03-010/011/012 (deadlines, artifact bytes, overcharge) | `codex/r03-data` / `/tmp/asv2-r03-r03-data` | `store.py` integrity regions, `evidence.py`, owned tests | `settlement_r03data` | merged (`9134c7b`) |
| W-SUP | R03-001/002 (generation fence, supervision) | `codex/r03-sup` / `/tmp/asv2-r03-r03-sup` | `launcher_runsc.py` fence/retention, `exec_profile.py`, broker exposure, owned tests | `settlement_t1broker` | merged (`4de32e7` + `7b7e5dc`) |
| W-EVAL | R03-003/004/005/006 (staging, binding, experiment) | `codex/r03-eval` / `/tmp/asv2-r03-r03-eval` | `experiment.py`, `evaluation.py`, `capabilities.py`, `launcher_local.py`, `experiments/run_live_abc.py`, owned tests | `settlement_r03eval` | merged (`27afd88`) |
| W-FLOW | R03-007/008/009 (backup, wakeup, retry) | `codex/r03-flow` / `/tmp/asv2-r03-r03-flow` | `scripts/checkpoint.py`, `scripts/restore.py`, `run.py` workflow, owned tests | `settlement_r03flow` | merged (`56aeaa2`) |

Integration: DATA → SUP → EVAL → FLOW with explicit merges on
`codex/implementation-s0-s3` (one store.py import conflict, unioned after
verifying both sides; one integration-only probe failure from an
over-broad import removal, import restored). Integration fixes committed
as `42caa1e` (probe retirements, image-local python default). Temp
worktrees under `/tmp/asv2-r03-*` are removed after the integrated suite
passes; lane DBs `settlement_r03{data,sup,eval,flow,int}` are dropped
with them.
