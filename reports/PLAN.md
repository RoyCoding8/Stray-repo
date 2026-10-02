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
worktrees under `/tmp/asv2-r03-*` removed after the integrated suite
passed (456 passed); lane DBs `settlement_r03{data,sup,eval,flow,int}`
dropped. Final R03 tip `be1730d`, pushed.

## DEVELOPMENT-01 episode (coordinator branch `codex/implementation-development-01`, base `be1730d`, design `7c3d380` merged as `c4ec6f7`)

Live model access is absent (no `SETTLEMENT_GATEWAY_ENDPOINT`/key/grant in
the environment), so the live run is blocked; the slice finishes
implementation plus deterministic checks and reports the runnable live
command. Seed count bounds (≤2 explanations, ≤1 probe, ≤2 candidates) are
enforced in durable episode state, not by convention.

| ID | DEV IDs | Owner branch / worktree | Owned paths | Test DB | Depends on |
|---|---|---|---|---|---|
| D-EP | DEV-01/02/03/04/09-part | `codex/dev01-episode` / `/tmp/asv2-dev01-ep` | `src/settlement/development.py` (new), `src/settlement/experiment.py`, `tests/test_dev01_episode.py` | `settlement_dev01ep` | merged (`5b7918f`), integrated |
| D-CMP | DEV-05/06/07/08/10/09-part | `codex/dev01-compare` / `/tmp/asv2-dev01-cmp` | `tests/test_dev01_compare.py`, `experiments/dev01_tasks.py` (new fixtures), episode-compare docs input | `settlement_dev01cmp` | merged (`9d0d6f4`), integrated |
| D-OPS | DEV-11/12 | `codex/dev01-ops` / `/tmp/asv2-dev01-ops` | `experiments/run_dev_episode.py` (new), operator view regions, `tests/test_dev01_ops.py` | `settlement_dev01ops` | merged (`3498cbf`), integrated |

Integration (`f3318f8`): the entry bypassed the durable lifecycle (phase
labels over `run_abcs`) — rewired through observe→bind with the bound
candidate injected via `synthesize`/`fixer_version` (C invokes the exact
bound bytes); `development.check` rewritten as apply-then-grade (direct
grading could never pass procedure-shaped candidates);
`propose_hidden_answer` idempotent on identical answers (repeat runs no
longer crash). Deterministic end-to-end proven on scratch DBs including
a same-DB repeat; bound episode ids refuse re-run on identity.

Rules: D-EP is the sole owner of `experiment.py` and `development.py`;
D-CMP/D-OPS consume `run_abcs`/episode APIs read-only and route change
requests through the coordinator. No lane edits `broker.py`, launchers,
`store.py`, or `reviews/probes/` without coordinator approval. All
inference through `_infer_via_broker` (gateway adapter live,
`double=` fixture deterministic); generated bytes never execute in the
trusted host process. Temp worktrees `/tmp/asv2-dev01-*` removed after
integration; lane DBs dropped with them.

## DEVELOPMENT-02 episode (coordinator branch `codex/implementation-development-02`, base `0816ebf` = design packet merged on `e1b95a6`)

Assignment `WORKER-DEVELOPMENT-02-PROMPT.md`. Four characterization probes
(`reviews/probes/test_development_01_readiness.py`, 4 passed = 4 gaps
reproduced) drive D02-001..004; design contracts in
`docs/design/MEMORY-AND-CONTEXT.md` (§11: CTX-01..10; §§3-9: packet
obligations). No live gateway in this environment (no
`SETTLEMENT_GATEWAY_ENDPOINT`/KEY/`SETTLEMENT_GRANT_UNITS`): deterministic
slice only; the live finite-panel run stays a stated gate with a runnable
command. No new vector DB, memory framework, ontology, deletion policy,
agenda engine, or second workflow engine.

Coordinator-pinned packet seam (M-CTX implements, M-EP consumes; stable
before either lane's consumer/producer code merges):

- `context.build_packet(dsn, cmd, *, decision) -> CommandResult`, new
  migration `0008_context_packets.sql` (M-CTX owns migration numbering).
- `decision = {"decision_kind": "diagnose"|"construct"|"resume",
  "purpose", "required_inputs", "allowed_actions", "access", "budget":
  {"input_chars", "output_reserve"}, "current_versions",
  "investigation_id", "episode_id"}`.
- Result data: `{"packet_id", "outcome": "ready"|"needs_information"|
  "stale", "rendered", "rendered_digest", "mandatory_content",
  "evidence_bundles", "gaps", "footprint", "omissions",
  "token_estimate": {"chars", "labeled": "chars-not-tokens"}}`.
- Binding table `packet_invocations(packet_id, operation_id,
  rendered_digest)`; packet identity + rendered digest recorded in the
  episode row and gateway receipt by M-EP. Non-`ready` outcome stages or
  narrows the decision; it never silently drops a required input.

| ID | D02/CTX IDs | Owner branch / worktree | Owned paths | Test DB | Depends on |
|---|---|---|---|---|---|
| M-EP | D02-001..004; CTX-08, CTX-10 | `codex/dev02-episode` / `/tmp/asv2-dev02-ep` | `experiments/run_dev_episode.py`, `src/settlement/development.py`, `src/settlement/experiment.py` (release path only), `tests/test_dev02_episode.py` (new), challenge fixtures | `settlement_dev02ep` | packet seam above; M-CTX implements `build_packet` |
| M-CTX | CTX-01..07, CTX-09 | `codex/dev02-context` / `/tmp/asv2-dev02-ctx` | `src/settlement/context.py`, `migrations/0008_context_packets.sql` (new), `tests/test_ctx*.py`, operator packet regions in `src/settlement/api.py::overview_data` | `settlement_dev02ctx` | packet seam above; consumes episode/evidence/artifact stores read-only |

D02 dispositions (coordinator assessment from probe evidence + source):
D02-001 confirmed (constructor prompt carries unresolved refs; batch runs
after); D02-002 confirmed (closure returns rejected bytes with fallback
stem); D02-003 confirmed (admit freezes empty protocol; policy recorded
post-construction); D02-004 confirmed (`_maybe_release` routes/pins only;
"use" labeled from metadata). None rebutted; live-model conditioning is
externally blocked (no gateway) and stays a stated gate.

Rules: M-EP is the sole owner of `development.py`, `experiment.py` and
`run_dev_episode.py`; M-CTX is the sole owner of `context.py` and
migration 0008. Neither lane edits the other's files, `broker.py`,
launchers, `store.py`, `reviews/probes/`, locks, or `reports/PLAN.md`
without coordinator approval.

M-EP reclaim record: the M-EP specialist terminated after the reading
phase with an empty tree (no venv, DB, edits or commits; verified before
takeover). The coordinator implemented the M-EP slice directly on
`codex/implementation-development-02` (`8648d8e`) against the already-merged
M-CTX seam — no fake lane history, no parallel-edit conflict. Lane branch
`codex/dev02-episode` left at `b7d7c85` and removed with the temp
worktrees. Workstream report `reports/workstreams/dev02-ep.md` records the
reclaimed implementation as coordinator-completed work.

## DEVELOPMENT-02-LIVE completion (coordinator branch
`codex/implementation-development-02`, base `a1d2525` + assessment packet
`0c1c869`; autonomous agenda design explicitly out of scope)

Assessment `reviews/DEVELOPMENT-02-ASSESSMENT.md`: D02-002 closed,
freeze ordering accepted, 509 deterministic tests useful-not-sufficient.
All five D2A findings verified against source; none rebutted. No live
gateway in this environment (env-only discovery; endpoint/key/grant/model
all unset; no configured local gateway) — the live episode and provider
smoke stay exact-blocker records with runnable commands.

Coordinator-pinned seams (stable packet decision shapes; no interface
change except where named):

- Trigger refs may carry `claim_id` (`context._referenced_claims` already
  resolves them). L-EP writes collected claim ids into episode trigger
  refs durably (UPDATE + event); no other writer touches trigger refs.
- `bind_packet_invocation(dsn, cmd, packet_id, operation_id,
  artifacts_root=None)` signature frozen. L-CTX strengthens internals
  (model-op input read, input digest column via migration 0009, replay
  refusal); callers unchanged.
- Use disposition crosses the fresh process as an explicit JSON document
  (`run_use.py --disposition-json`): `{released: {family: version_id},
  router_policies: {...}, trial: bool}`. Absent/unreleased/wrong-scope →
  incumbent with recorded reason; trial invocations labeled `trial`, never
  ordinary use.

| ID | D2A IDs | Owner branch / worktree | Owned paths | Test DB | Depends on |
|---|---|---|---|---|---|
| L-EP | D2A-001..003, cost union, live preflights | `codex/d02live-episode` / `/tmp/asv2-d02live-ep` | `src/settlement/development.py`, `src/settlement/experiment.py` (use path + cost plumbing only; invocation semantics frozen), `experiments/run_dev_episode.py`, `experiments/run_use.py`, `tests/test_d02live_episode.py` (new) | `settlement_d2liveep` | trigger-ref claim convention; disposition JSON schema above |
| L-CTX | D2A-004..005 | `codex/d02live-context` / `/tmp/asv2-d02live-ctx` | `src/settlement/context.py`, `migrations/0009_packet_input_binding.sql` (new), `tests/test_d02live_context.py` (new) | `settlement_d2livectx` | bind signature frozen; migration numbering |

Rules: L-EP owns `development.py`, `run_dev_episode.py`, `run_use.py` and
the use/cost parts of `experiment.py`; L-CTX owns `context.py` and
migration 0009. Neither lane edits the other's files, `broker.py`,
launchers, `store.py`, `reviews/probes/`, `reports/PLAN.md`, locks, or
`docs/design/AUTONOMOUS-AGENDA.md` without coordinator approval. Both
prove paths through real PostgreSQL + real subprocesses with explicit
doubles only at model inference seams. Acceptance probes
(`reviews/probes/test_development_02_acceptance.py`) are characterization
evidence, not contracts: migrate each fixed property to a real-DB
regression and record correspondence; never invert a probe to make a
number green. Temp worktrees `/tmp/asv2-d02live-*` removed after
integration; lane DBs `settlement_d2live{ep,ctx,int}` dropped with them. Both lanes prove paths through real
PostgreSQL + real subprocesses with explicit doubles only at
model/runtime seams; generated bytes never execute in the trusted host
process. Migrate the 4 probes to intended contracts or replace with
stronger real-DB regressions and record correspondence. Temp worktrees
`/tmp/asv2-dev02-*` removed after integration; lane DBs
`settlement_dev02{ep,ctx,int}` dropped with them.

## ENGINEERING-REVIEW audit (assignment `WORKER-ENGINEERING-REVIEW.md`, coordinator branch `codex/implementation-development-02`, lane base `9ee00a6`)

Evidence branch `origin/codex/development-02-live-evidence` merged fast-forward (`9ee00a6`); carries the live-campaign assessment (`reviews/DEVELOPMENT-02-LIVE-EVIDENCE.md`), grader/accounting controls (`reviews/probes/test_live_evidence_controls.py`), the live-evidence prompt (obligations EVID-01/02/PROV carried forward, scope caps superseded) and agenda design drafts (not implemented by this audit).

Coordinator index: `reports/ENGINEERING-REVIEW.md` (lanes, region partitions, coverage matrix, findings ledger). Shared-contract and shared-file ownership rules from prior cycles apply, plus the experiment.py/development.py region partitions in the index. Migration numbering is coordinator-owned; lanes file requests. Integration order: ENG-PROV + ENG-INV-* → ENG-ACCT → ENG-SOLV; one merge at a time with affected checks rerun; final journey + failure-mode passes and full suite on the integrated tip.

| ID | Obligation | Owner branch / worktree | Owned paths | Test DB | Depends on |
|---|---|---|---|---|---|
| ENG-ACCT | EVID-02 unbilled-settlement reporting | `codex/eng-acct` / `/tmp/asv2-eng-acct` | experiment.py accounting regions, owned tests | `settlement_engacct` | region partition in index |
| ENG-SOLV | EVID-01 solver output contract + live baseline smoke | `codex/eng-solv` / `/tmp/asv2-eng-solv` | experiment.py arm/collection/use regions, development.py collect region, owned tests/fixtures | `settlement_engsolv` | contract approved by coordinator before implementation |
| ENG-PROV | effective-config + source fingerprint in records | `codex/eng-prov` / `/tmp/asv2-eng-prov` | entry record regions, owned tests | `settlement_engprov` | — |
| ENG-INV-A | state/recovery/ops sweep | `codex/eng-inva` / `/tmp/asv2-eng-inva` | store.py, run.py, scripts/*, migrations 0001/0004/0006, owned tests | `settlement_enginva` | — |
| ENG-INV-B | dispatch/containment/gateway sweep | `codex/eng-invb` / `/tmp/asv2-eng-invb` | broker.py, gateway_http.py, boot.py, exec_profile.py, launcher_*.py, owned tests | `settlement_enginvb` | — |
| ENG-INV-C | evidence/learning/operator/packaging sweep | `codex/eng-invc` / `/tmp/asv2-eng-invc` | artifacts/evidence/context/capabilities/trials/evaluation/steward/agenda/api.py, experiments/*, other migrations, owned tests | `settlement_enginvc` | — |

Rules: lanes commit + push only their own branch, `git add` only files they created/edited, write `reports/workstreams/eng-<name>.md`, never edit another lane's paths, shared contracts, coordinator reports, or `docs/design/*`. Private Git identity stays; no credentials or remote URLs in reports. Live work only where the lane brief authorizes it (ENG-SOLV smoke: one designated task, seeded allocation ≤2M units on its own DB, disposable local profile, full evidence preserved). Temp worktrees `/tmp/asv2-eng-*` removed by the coordinator after integration; lane DBs dropped with them.

## AGENDA-01 (assignment `WORKER-AGENDA-01.md`, coordinator branch `codex/implementation-agenda-01`, design base `c69f8cb`, runtime base `913bda7`)

Contract baseline (coordinator-owned, committed before split; decisions AG01-D01..D08 in `reports/DECISIONS.md`):

- Migration `0010_agenda01.sql` owns: `agenda_options` (option_id PK, allocation_root, current_revision, disposition open/dormant/answered/retired, disposition_version), `agenda_option_revisions` (immutable (option_id, revision), request_id UNIQUE, body JSONB, digest), `agenda_disposition_events` (append-only (option_id, version) UNIQUE), `agenda_attempt_links` (option/revision/attempt/operation binding + effect_identity UNIQUE), `agenda_decisions` (trajectory, cursor_tick, policy_version UNIQUE; selection + reasons), `agenda_cursors` (trajectory PK; tick, rotation), `agenda_wake_log` ((option_id, event_identity) UNIQUE). Owner: AG01-STATE. No `open/dormant/...` in `investigations.disposition`.
- Commands (all `store.transact`, idempotent request_id; ConflictPayload on changed-payload reuse): `propose_option` (request_id `ag01-propose-<stable-key>-r<rev>`; StaleRevision on stale expected_revision), `select_and_admit` (advisory selection + atomic recheck + exposure reserve in ONE transact via transaction-local helpers; never nest public transact under the control lock), `record_outcome` (attempt link + durable receipt/evidence + epoch check), `submit_continuation` / `set_dormant` / `answer_option` / `retire_option` (expected_disposition_version), `process_wake` (typed match + wake_log dedup). Read-only `explain_eligibility`. Owner: AG01-STATE.
- Identities: option request key `ag01:<scope>:<question-key>:<probe-key>` canonical JSON, digest `common.payload_digest`; intended-effect identity = (allocation_root, option_id, evidence/dep versions, probe, intended decision, replication_slot|none); replication slots `repl:<protocol>:<k>-of-<N>` frozen in the continuation record. Cost ops `ag01:<traj>:dec:<tick>` (1 unit) and `ag01:<traj>:probe:<tick>` (2/4/8) via existing reserve/settle; decision cost charged even when idle. Owners: STATE (durable), EXP (manifest values).
- Evidence input shape: observation `{prop, scope, dep, dep_version, value true|false|unknown, source_attempt, receipt, epoch}`; opposition + unknown preserved; future-epoch/tampered/missing support refused. Grammar version `AG01-OBS/1`; policy versions `AG01-R/1`, `AG01-Q/1`; parser + rotation + safety shared, Q adds only qualification routes Q1 (decision-change), Q2 (discriminating probe), Q3 (frozen replication remainder). Policies never import grader/latent modules (import gate test). Owner: AG01-POLICY.
- Experiment boundaries: 32 worlds (8 families x 4 variants) x 2 opposite tie orders x R/Q = 128 trajectories; 24 ticks; 64 exploration units; 8 end-use tasks; per-trajectory isolated DB `agenda01_w<WW>v<V>_<r|q>_t<0|1>`; eval allowance 8/trajectory + protected recovery cap 16, both unavailable to exploration; evidence cut at tick 24; manifest `experiments/agenda01/manifest.json` + sha256 referenced by every trace; checker `experiments/agenda01/checker.py` reconstructs totals/costs/liabilities and rejects altered/missing/duplicate records. Owner: AG01-EXP.
- Operator/demo: extend `agenda_snapshot` with eligibility reasons, continuation basis, wake condition, costs, outstanding liability (STATE); one CLI `scripts/agenda01.py` propose->admit->observe->continue/decline->dormant->wake->resume with useful-continuation AND justified-refusal paths (DEMO). No new management service or dashboard framework.

| ID | Obligation | Owner branch / worktree | Owned paths | Test DBs | Depends on |
|---|---|---|---|---|---|
| AG01-STATE | Durable options/dispositions/versions/attempt links, atomic funding, recovery; AG01-01..04,07,09 | `codex/ag01-state` / `/tmp/asv2-ag01-state` | `migrations/0010_*`, `src/settlement/agenda.py`, additive `_agenda01_*` helpers in `store.py`, `tests/test_ag01_state.py` | `agenda01_state` | contract baseline |
| AG01-POLICY | Shared rotation, R/Q, qualification, typed wake matcher, cursor; AG01-05..08 | `codex/ag01-policy` / `/tmp/asv2-ag01-policy` | `src/settlement/agenda_policy.py` (new), `tests/test_ag01_policy.py` | `agenda01_policy` | baseline; reads STATE commands, never edits them |
| AG01-EXP | World fixtures, grader, manifest, runner (durable path), checker, adverse tests; AG01-10..11 | `codex/ag01-exp` / `/tmp/asv2-ag01-exp` | `experiments/agenda01/`, `tests/test_ag01_experiment.py` | `agenda01_exp` + trajectory DBs | baseline; integrates STATE+POLICY after coordinator merge |
| AG01-DEMO | CLI path + operator read surface demo; AG01-12 | `codex/ag01-demo` / `/tmp/asv2-ag01-demo` | `scripts/agenda01.py`, `tests/test_ag01_demo.py`, demo evidence | `agenda01_demo` | baseline; integrates after STATE merge |

Rules: lanes commit + push only their own branch, `git add` only owned paths, write `reports/workstreams/ag01-<name>.md`, never edit another lane's paths, shared contracts, coordinator reports, or `docs/design/*`. Contract change requests go in the lane report; the coordinator decides. Real PostgreSQL 16 for all durable tests (`SETTLEMENT_TEST_DSN` host-param form); deterministic adapter doubles for world observations, labeled. No model calls, no live gateway, no production capability release. Integration order: STATE -> POLICY -> EXP -> DEMO; one merge at a time with affected checks rerun; reviewer pass on integrated contracts + experimental fairness in a fresh context before freeze; freeze manifest, run 128, full suite, `reports/AGENDA-01.md`, push. Temp worktrees `/tmp/asv2-ag01-*` removed by the coordinator after integration; lane DBs dropped with them.

### Execution record (coordinator, merged to `fdc354a` + docs)

- Merges: POLICY `27b9f0d` + DEMO `24a447b` + STATE (`0010`, `5e7cd6b`);
  EXP runner rewritten onto agenda commands (net -311 lines, `c7209b5`).
- Integration repairs `c8b24dc`: checkpoint migration list + overview
  projection folded to one connection (`executes <= 18`, `connects <= 6`).
- Freeze `090a4991` crashed 4/128 (w11 productless probe) → fix + regression
  test `e0a60ea`, refreeze `a52f3ed7` `fdc354a`, full 128 rerun: 128/128
  complete, checker clean. Verdict: all 64 pairs tied, Q not merited.
- Verification: full suite 653 green; report `reports/AGENDA-01.md`; traces
  `experiments/agenda01/results/`; review requested in `reviews/REQUEST.md`.

### Correction dispositions (assessment `3078018`, all six CONFIRMED, none rebutted)

- AGR1-01 CONFIRMED (live PG `/tmp/ag01_verify_agr1.py`): admit creates no
  investigation/attempt/operation; decisions store `AG01-CMD-1` with no
  policy/digest; proposals mint root authority. Fix: trusted setup seeds
  grant/allocation/investigation; admission acquires real attempts and
  prepares real operations via transaction-local store helpers; no
  self-authorized roots.
- AGR1-02 CONFIRMED (live PG): fabricated receipts accepted; same-ID
  changed-content silently `already_applied`; `receipts` untouched. Fix:
  sim launcher admits through `broker.admit_launcher_receipt`; record_outcome
  resolves and binds receipt bytes/attempt/operation/epoch, refuses
  conflicts and stale versions.
- AGR1-03 CONFIRMED (probe rerun + code): fence applies Q-logic to both
  arms; Q1 qualifies an unrelated citation with manufactured after-strings;
  slot strings bypass protocol checks. Fix: one `qualify_continuation`,
  mechanical fence shared, policy identity bound, Q-only extra; Q1 requires
  residual-matching citation plus differing declared consequences; slots
  checked against durable frozen protocol and counts; R-vs-Q end-to-end proof.
- AGR1-04 CONFIRMED (trace arithmetic): launches track seeds, 15-22 idle
  ticks, tie orders inert, Q-losing control ties. Fix: separate diagnostic
  controls proving treatment exposure, then a reviewed v2 panel; original
  panel preserved as inactive-treatment evidence.
- AGR1-05 CONFIRMED (probe rerun): empty dir, incomplete/false-version/
  missing-eval/missing-dec-op traces all accepted. Fix: exact panel
  membership, identity/version/cost/effect/liability/horizon reconciliation,
  verified freeze with source digests, explicit subset mode, committed replay
  entry point.
- AGR1-06 CONFIRMED (code + grep): all drive state process-local, no resume
  entry, uncommitted driver, `/tmp` hardcodes in fresh-process tests. Fix:
  durable trajectory state, committed replay driver, kill-and-resume proof
  against uninterrupted control, path cleanup.

### Correction outcome (v2 panel, see `reports/AGENDA-01.md`)

- Diagnostics: dev02 both arms 2/2 with m1 admitted usefully; dev03 R
  admits m1 while Q records `unqualified-continuation` and never links m1
  (1/1 both, R +2 spend); dev02 truncated at 1 tick forfeits p1.
- Panel: freeze `d5e2d79` ran 124/128 (w10 future-epoch receipts from
  drive-tick due dates) → refreeze `3b137cf` (cursor-epoch time anchor) →
  collation refreeze `c8b9acc` → 128/128 complete, strict acceptance green
  (64 pairs, 0 violations), manifest v2 `99e9d5f6`, Q `AG01-Q-2`.
- Result: grades tie 284–284 in all 64 pairs; Q spends 16 fewer exploration
  units (family 1 only); 8 per-tick decisions differ; 4 w11 trajectories
  carry one attributed dud liability each. Verdict under the stated merit
  rule: no accuracy gain, tie clause met on resources — Q merits a broader
  trial on cost grounds (authored simulation, not a learning claim).

### Correction-assessment dispositions (assessment `55df063`, three-gate prompt)

- Family totals: three-gate prompt line 21 CONFIRMED in one cell — v2
  `f2 (36, 36)` against traces/checker `f2 (32, 32)`; fixed in the v2
  section only (v1 appendix stays byte-frozen). All other families,
  the 32-row pair table, and the 64-row checker JSON (0 mismatches
  vs traces) verified (`/tmp/famcheck.py`, `/tmp/tblcheck.py`,
  `/tmp/fullcheck.py`). Report sums now 284–284.
- `8 of 3072` CONFIRMED as 8 action-level (probe-vs-idle) diffs over
  3072 trace-ticks: family-1 a2 followup, both ties (`/tmp/actdiff.py`).
- Receipt linkage: no `receipts/ag01_receipts.jsonl` exists anywhere in
  the tree; receipts live in the `receipts` table and are embedded per
  trace in `ledger`. Substance verified over embedded ledgers:
  614 ops (matches the assessment's 614), 626 receipts, 626 outcomes,
  0 orphan outcomes, 0 receipts without operations (`/tmp/substance2.py`).
- AGR2-01/02/03 CONFIRMED as specified in
  `reviews/AGENDA-01-CORRECTION-ASSESSMENT.md`; the probe's six findings
  convert to maintained regressions below. No rebuttals.

## COGNITIVE-BATCH-01 (assignment `WORKER-COGNITIVE-BATCH-01.md`, coordinator
branch `codex/implementation-cognitive-batch-01`, base `051811f` + design
packet `origin/codex/representation-design-01` merged as `22c88a8`)

Live model access is absent (no `SETTLEMENT_GATEWAY_ENDPOINT`/key/grant in
the environment): Lane D finishes the deterministic authored-fixture path
plus the bounded live campaign as an exact-blocker record with a runnable
command. Both finite experiments keep their own complete checked evidence.

Shared contracts (coordinator-owned, settled before lane split; decisions
CB01-D01.. in `reports/DECISIONS.md`):

- J1 package/profile: representation packages reuse the immutable artifact
  envelope (`artifacts.stage_package`/`publish_package` with manifest
  files/entry/verify_args) + `capability_versions` (version/artifact
  digest/dependencies/protocol). New invocation profile
  `representation-01`, ABI `python <entry> <request.json> <response.json>`,
  actions encode/start/advance/decode with bounded JSON schemas chosen
  once by Lane C. Existing repair `development.METHOD_ABI` and
  `experiment._invoke_method` are preserved untouched; the entry is never
  inferred from file order. Owner: Lane C (schema), all lanes consume.
- J2 source oracle: source tasks are data files; checkers are separately
  implemented trusted binaries with an independent reference
  cross-check (graph BFS-coloring vs exhaustive 2-coloring ≤5 vertices,
  triangles vs explicit triples, interpreter vs separate transition
  table). Witness identities: software `(task, observation-id,
  value-disagreement)`, graphs `(task, validity ∧ triangle-free ∧
  non-bipartite)`. Feedback vocabulary `preserved | not_preserved |
  invalid | unknown` + checked measure + bounded reason. Owner: Lane B.
- J3 evidence records: every arm-task record carries composition
  (core/adapter digests), invocation receipts, oracle queries, costs and
  disposition; split/manifest/checker mirror the agenda freeze discipline
  (content-verified manifest, strict checker rejects missing/duplicate/
  unbound records, CLI replays from committed inputs). Owner: Lane D,
  reuses Lane A freeze mechanics read-only.
- J4 construction lineage: acquisition episodes persist parent experience
  refs, candidate lineage (≤2 versions/arm/stage), component identities
  and trial disposition through existing development/capability records;
  no duplicate event log or second registry. Owner: Lane D.
- J5 budgets: per benefit task ≤16 witness queries, ≤64 component
  invocations, ≤120s elapsed, ≤2s per invocation, ≤64KiB per
  request/response/persisted state; campaign ≤12 model calls (≤16384 in/
  ≤8192 out tokens each), equal per-arm opportunity. Owner: Lane D
  enforces, Lane C measures.

| ID | Obligation | Owner branch / worktree | Owned paths | Test DBs | Depends on |
|---|---|---|---|---|---|
| A-agenda | AGR2-01/02/03 short gates + corrected preserved panel | coordinator, this branch (no split; shared driver/time owner) | `experiments/agenda01/`, `src/settlement/agenda.py` (charge order), `migrations/0013_*`, `tests/test_ag01_*.py`, `reports/AGENDA-01.md` | `agenda01_exp` + trajectory DBs | J-contracts read-only |
| B-source | RPR-01 instruments/fixtures/checkers/reducers/splits | `codex/cb01-source` / `/tmp/asv2-cb01-source` | `experiments/representation/` instruments + fixtures, owned tests | `settlement_cb01src` | J1/J2 |
| C-exec | RPR-02/05/07 profile/runner/state/linkage/view | `codex/cb01-exec` / `/tmp/asv2-cb01-exec` | `src/settlement/representation.py` (new), profile runner, owned tests | `settlement_cb01exec` | J1/J5 |
| D-acquire | RPR-03/04/06/08 contexts/lineage/freeze/A-B-C/evidence/report | `codex/cb01-acquire` / `/tmp/asv2-cb01-acquire` | acquisition + experiment + checker + `reports/REPRESENTATION-01.md` (via coordinator) | `settlement_cb01acq` | J3/J4/J5; fixtures from B/C |

Rules: lanes commit + push only their own branch, `git add` only owned
files, write `reports/workstreams/cb01-<name>.md`, never edit another
lane's paths, shared contracts, coordinator reports, or `docs/design/*`.
Shared store/broker/gateway/artifact/capability/migration/test/UI changes
go through one coordinator-designated owner; dependents wait for that
commit. Integration order: B + C in parallel, then D on the merged base;
A runs independently (shared driver/time semantics under the coordinator).
Resource-heavy panels run sequentially. Temp worktrees `/tmp/asv2-cb01-*`
removed after integration; lane DBs dropped with them.

Outcome: all four lanes delivered scope-clean on owned paths and merged
with explicit merges (`e644ff5` B, `b8fff7f` C, `c25c39d` D); coordinator
re-ran every lane test file on the merged source (B 46, C 39, D 28
passed) plus the DB-free replay/freeze checks before publishing
`reports/REPRESENTATION-01.md` (`1e5bf53`). Lane C's workstream report
ends without a verification section; the coordinator's merged-source
rerun (39 passed) stands as its evidence. Contract readings confirmed:
graph witness identity is task plus three-way conjunction, equal-measure
acceptance is the byte-identical incumbent only (B and D concur).
