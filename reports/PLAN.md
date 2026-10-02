# Implementation plan

## Current batch — 2026-10-02, A–C closure

Integration: `codex/ab-closure-2026-10-02`, from `codex/agent-society` at `5349dab`.
This batch runs *after* the one-time consolidation, so the milestone-A–C
inventory below describes the pre-consolidation graph. It is kept because those
lanes' findings still constrain what may honestly be claimed. This batch starts
from the consolidated 20-commit history; nothing in this section has yet landed.

The named remaining work is the one the consolidation record states plainly: the
live JSON `FrontierStore` path is **not** migrated to the SQL investigation
owner, and Stage 10's connected mission is not demonstrated. The four
coordinator repairs in the ledger (mission admission, measured coverage, source
identity, executed-lineage reporting) each carry an explicit "what this does not
establish" column, and those four exclusions are the seed of this batch.

### Runtime factors, measured before any lane started

| Factor | Resolution | Evidence |
|---|---|---|
| WSL resource cap | **3GB / 3 processors**, verified applied, not merely written. One shared VM serves every lane, so this cap is the whole project's ceiling. | `nproc` → 3, `free -m` → 2908 MB total, read back after `wsl --shutdown` |
| Suite cost | The full suite is ~4 hours. A prior lane ran it four times concurrently and starved a 15.6GB host. Lanes run **only their owned files**. | `docs/RUNBOOK-ISOLATED-FULL-SUITE.md`; `reports/STAGE-09-COMPLETION-MATRIX.md` records the incident |
| RUNTIME | WSL2 Ubuntu, PostgreSQL 18.6 live on the socket, `/home/ubuntu/.venvs/as9/bin/python` (3.14.4), `PYTHONPATH=src`, run as `ubuntu` for peer auth. | `pg_isready` → accepting connections |
| Lane isolation | Each test run gets its own `S09ISO_TOKEN`; `tests/conftest_isolation.py` mints and drops `s09iso_<token>_<suffix>` databases. A missing admin DSN is a collection INTERNALERROR, not a test failure. | `docs/RUNBOOK-ISOLATED-FULL-SUITE.md` |

Two mistakes in the WSL cap are worth recording because the first one survived a
partial fix: `.wslconfig` is **silently ignored** under a UTF-8 BOM *and* under a
section named `[experimental]` instead of `[wsl2]`. WSL starts normally in both
cases. The cap is only real once `nproc` and `free -m` are read back.

### Lane graph — round 1, census (read-only, disjoint)

Six lanes dispatched concurrently. Five are Windows-side only; `x0-baseline` is
the sole WSL/PostgreSQL consumer for this round, so the shared VM is never
contended.

| Lane | Task | Ownership | Depends on | State |
|---|---|---|---|---|
| a0-state | 46 | `FrontierStore` private state, writers/readers, durability, per-fact single owner | — | running |
| a1-sqlowner | 47 | SQL investigation owner's tables, lifecycle, continuation identity, gaps | — | running |
| a2-callers | 48 | production call sites, reachability, safe migration order | — | running |
| b0-census | 49 | milestone B: established / negative / absent / closed-unrun, with denominators | — | running |
| c0-census | 50 | milestone C: same discipline, plus the freeze-path reachability verdict | — | running |
| x0-baseline | 51 | real clean baseline on PostgreSQL, per file, per run | — | running |

"Closed unrun" is kept distinct from "negative" throughout this batch. The two
have been conflated in earlier passes, and the difference decides whether a
result may be described as a measurement.

## Prior batch — 2026-10-01

Integration: `codex/stage09-consolidation-2026-10-01`, from `70223fb` via the
read-only milestone inventories at `f03db5b`. Base checkpoint is the
`codex/stage09-closure-checkpoint` work, not the remote default.

Read-only inventories, one per milestone, are
[inv-a](workstreams/inv-a.md), [inv-b](workstreams/inv-b.md) and
[inv-c](workstreams/inv-c.md). Each names owned paths, dependencies and a
named pytest gate per lane, so each lane has an explicit verification scope.
The coordinator still inspects source and evidence and reruns affected gates on
the merged tip. The 2026-10-02 review and remaining priorities are recorded in
[PROJECT-LEDGER](PROJECT-LEDGER.md#coordinator-review-2026-10-02).

### Runtime and route factors (both closed before any lane started)

| Factor | Resolution | Evidence |
|---|---|---|
| RUNTIME | WSL2 Ubuntu, real PostgreSQL 18 on the socket, `PYTHONPATH=src` into `/home/ubuntu/.venvs/as9` (Python 3.14.4). The editable install is unavailable offline, so the source root is on the path instead. Must run as `ubuntu` or peer auth fails. | 13 disposable databases minted and dropped per run; `tests/test_s09_run_isolation.py` 23 passed |
| Claim ledger | `/tmp/settlement-claims` was root-owned, so the `ubuntu` user could not append a claim and every out-of-process policy execution refused with `claim-not-durable`. Ownership corrected in the image. This is an environment defect, not a code defect. | `tests/test_s09_e2_scored.py` went from 22 failures to 30 passed |
| ROUTE | `GET /v1/models` on the loopback gateway returns 219 models, 32 free-tier, and the pinned `nvidia/nemotron-3-ultra-550b-a55b:free` is present unprefixed. Discovery only; no inference call, no effect, no spend. | Live catalog read 2026-10-01 |

One premise in the milestone-B inventory is stale and must not be chased.
Its B11 lane records the pinned model id as absent from a 256-model catalog.
Today's catalog has 219 entries and the id is present, so the "frozen model
absent from catalog" finding no longer describes the route. B11's remaining
question stands and is the real one: the recorded 502 tracks the requested
output budget rather than the prompt, so the served budget must be established
before any B dispatch. Establishing it is itself a dispatch, so the cap sheet
is written first.

Baseline before any lane: the two-token isolation test was red on the clean
base because it minted 8-hex-digit tokens, which `_checked_token` refuses as
belonging to the pytest sweep space. Fixed on the integration branch at
`898b10c` so every lane gate measures only its own change.

### Lane graph, as merged

Disjoint paths, one writer per worktree under `.worktrees/`, serial `--no-ff`
merge by the coordinator in the main checkout, gate before merge and re-run on
the merged tip.

**This table is the merged reality at `5b7f1ca`, not the pre-merge plan.** The
State column was rewritten after the independent acceptance pass found it
entirely pre-merge: it marked sixteen lanes unfinished, none merged, and
omitted the twenty-eight workstream reports that exist on the tree. `State` now
distinguishes *landed* from *never run*, which is the only distinction a reader
needs in order to decide what is outstanding.

| Lane | Milestone | Ownership | Depends on | State |
|---|---|---|---|---|
| a1-preflight | A1 | `live_construct.py`, `invl02_live.py`, campaign r2/r3, durable-preflight test | — | landed `450a988` |
| a2-nodsn | A2 | `method_exec.py`, `policy_step.py`, out-of-process call sites, no-dsn test | — | landed `fb563ce` |
| a3-action | A3 | `policy_action.py`, `policy_step.py`, `policy_assess.py`, `assessment_profile.py`, action-meaning test | — | landed `f836a16` |
| a4-owner | A4 | frontier decision/authority projection onto the trajectory path | a1, a2, a3 | landed `6caacbc` |
| a4b-lostupdate | A4 | frontier crash-loss premise, measured then repaired | a4 | landed `1252c4f` |
| a5-chain | A5 | chain test, reviewer counterexamples, reviewer source | a4 | landed `a4929f2` |
| a6-callers | A6 | the five no-authority callers, migrated to real authority | a2 | landed `94efa12` |
| a7-probe | A7 | the preflight probe as a durable broker operation | a1 | landed `992ad93` |
| a8-improveauth | A8 | real authority threaded through the invl02 improve channel | a6 | landed `5d3f4be` |
| b1-sweharness | B1 | SWE view contract, SWE AST graph view read, SWE view test | — | landed `f5f536d` |
| b1c-flip | B1c | B1's assertions corrected, the bound action that could never fill | b1 | landed `35ba5e9` |
| b2-graphchild | B2 | a graph arm reaches a world turn; a dead child is not an empty one | b1 | landed `051d702` |
| b3-repertoire | B3 | open the closed repertoire so retention becomes measurable | b8 | landed `794520f` |
| b4-score | B4 | `agenda_policy` `_score_constant_rules` scored on a mean | — | landed `2c187ae`; its freeze is **unmeasured**, see below |
| b8-panel | B8 | panel enumeration, panel-power test, census evidence dir | — | landed `5d8bb4e` |
| b9-driver | B9 | one named executor per world in the bounded graph driver | b2 | landed `160f8e4` |
| b10-cap | B10 | the B cap sheet, written from the complete matrix before any effect | b1, b3 | landed `933f487` |
| b11-probe | B11 | route re-probe establishing the served output budget | b10 | landed `e7d0e3f`, 6 of 6 sends used |
| b12-live | B12 | SWE matrix live construction, 4 lineages per supported cell | b11 | landed `7cc4df7`, **0 of 4 lineages acquired** |
| b13 | B13 | E2 contrast replication on the powered panel | b8 | landed `a4083df` then **reverted** `a6687d6`; superseded by b13b |
| b13b-replseed | B13 | the E2 method resolved per family, and a graph edge read as a pair | b13 | landed `75cab06` |
| b14-retention | B14 | retention and adaptation behind the opened repertoire | b3, b12 | landed `9cc7249`, **0 of 3 members measurable** |
| b18-view | B18 | the contract view already carried what the guard reads | c2 | landed `c8c58bf` |
| c1-mission | C1 | single durable mission entry, retiring the partial owners | a4 | landed `eeb9e68` |
| c2-freeze | C2 | freeze enforcement and independently written channel controls | c1 | landed `dd81e3e` |
| c3-fixture | C3 | the verdict-shape fixture repaired against the freeze guard | c2 | landed `3894f8c` |
| c4-construction | C4 | inheritable construction procedure, replacing the two-member menu | c2 | landed `a82baca` |
| c6-suspend | C6 | one resume owner, naming what it resumed | c1 | landed `58aaae7` |
| c7-twodomain | C7 | one mission crossing both task structures, naming the powered side | c2, c6 | landed `3138408` |
| p1-search | review | search pass 1, four findings over the merged tip | all A | landed `f919431` |
| p2-search | review | search pass 2, three findings over the merged tip | p1 | landed `32823e8` |
| x1-sigfix | repair | two merged-tip defects no single lane could see | p1 | landed `01030c7` |
| x2-subscript | repair | freeze widened to the subscript position | p2 | landed `794737f` |
| acceptance | review | independent acceptance pass over the merged tip | all | landed `8a207ab` |
| x3-freeze | repair | the freeze refuses a frozen write made through a mapping method, read off the parse's own binding contexts | review | landed |
| x4b-effectid | repair | the effect identity is read off the episode and checked against `operations WHERE settled` before it is written | review | landed |
| x5-amend | repair | concurrent amends of one protocol resolve to one successor under a held parent lock | review | landed |
| doc-apply | doc | the ledger, roadmap and matrix record what is true, including the overturned mechanism verdict | review | landed |
| x6b-scan | repair | `source_kind` says what it gates on, not what C4 deleted | c4 | landed |
| token-grammar | repair | the grammar reads its sources from the index, not from a walk of the checkout | c7 | landed |
| decoy-fix | repair | the decoy's justification is repaired rather than the control removed | c7 | landed |
| sib2-fix | repair | migrate the two tests that named the removed construction menu by label | c4 | landed |
| giveaway | doc | name what the prompt actually is: the skeleton is the interface, not a giveaway | c7 | landed |
| z2-retarget | repair | re-aim six guards whose subjects had been repaired; find nine unexplained reds the earlier audit had not seen | all | landed |
| b5-sealed-state | B5 | per-task policy state in sealed assessment | b1 | **never run.** No workstream report, no evidence directory, no test exists. WORKER-PROMPT.md §B asked for per-task policy state in sealed assessment; nothing in this batch delivers it and nothing claims to. |
| c4-live | C4 | bounded live revision attempt under its own freeze | c3, b11 | **never run.** No report, no evidence directory, no test. This is the milestone-C deliverable in WORKER-PROMPT.md §C, so it is recorded as outstanding rather than dropped. The mechanism that would have made it runnable exists (c4-construction landed an inheritable construction procedure); no eligible revision was attempted against it, so **no live revision and no revised descendant cohort exist**. |

The two never-run lanes are the whole of the outstanding implementation scope
this batch left behind. Neither is a live lane: no cap sheet authorizes either,
and neither consumed a dispatch.

**Two reds remain deliberately unresolved and are recorded, not open work.**
FA-04 asserts `hasattr(channel, "REACHABLE_EVIDENCE")`, which the correct
deletion of the fixed menu falsifies, and it can only be greened by restoring
the menu C4 deleted. FA-02 names
`reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`, a file that was
never committed and must not be fabricated to satisfy a gate. Z2-RETARGET's
audit found nine further unexplained reds across four files that no document
recorded; the ledger carries the count and the audit's own coverage gap.

**B4's freeze is not a lane failure and is not closed.** The single
`control_competence(40)` sweep was cancelled for resource reasons before it
returned, so `reports/evidence/invr1b4-mean-score/b4-crossover-mean.json` does
not exist. A cancelled measurement is not a null measurement: nothing about the
crossover is known in either direction
(`reports/workstreams/b4-score.md`; see also
[FA-04 note](STAGE-09-10-COMPLETION-MATRIX.md)). The four tests that read it
now assert the absence is the declared one instead of erroring on a file
nobody was able to write.

Review lanes R1–R3 and the final acceptance pass ran as a separate agent from
the author of each target, and all three landed. R1 on the a1/a2 authority
migration is folded into `a6-callers` and `a8-improveauth`; R2 on a3 action
meaning into `a3-action`; R3 on the mission entry into `c1-mission` and
`c6-suspend`.

Live lanes were frozen before any effect and gated on the written cap sheet. A
missing cap sheet was setup work, not a reason to re-ask for authorization, and
no live lane re-asked.

## Current closure checkpoint — 2026-09-30

Integration: `codex/stage09-closure-checkpoint`, from `0c581ef`.
Stage 9 remains active; this batch closes material seams and specifies the next
connected study. It does not claim a general prototype or learning advantage.

| Lane | Ownership | Dependency | Acceptance | State |
|---|---|---|---|---|
| AC | `learner_revision.py`, one new accounting test | Existing broker/grant contracts | Real PostgreSQL admission, attribution, replay, cap and lost-response checks | Merged through `5424c10`; coordinator observed 81 related checks passing |
| CY | `policy_step.py`, use region of `trajectory.py`, source-policy callers and regression tests | Existing trajectory and bounded executor | No host execution; fresh-process retained use; actual policy/method operation accounting on success and refusal | Merged through `07b58b9`; independent boundary review closed its material findings |
| ST | One fresh evidence diagnostic and its test; read-only boundary reviews | Frozen E4 semantics | Independent scoring, observation sensitivity, disjoint cohort and raw results | Merged through `71eb58f`; diagnostic run and independent recomputation observed |
| FX | Remaining control test helper only | CY's versioned policy view | Canonical view construction without weakening assertions or runtime checks | Merged through `0e991d2`; lane gate 6 passed; temporary worktree removed |
| Coordinator | Architecture synthesis, ledger, roadmap, worker prompt, serial integration | AC/CY/ST/FX | Inspect changes, rerun integrated checks, clean owned resources, snapshot remotely | Source acceptance at `cae712b`: 281 passed, zero failures/skips; all four temporary worktrees removed |

All three implementation/review delegates use Luna in isolated worktrees under
`.worktrees/`. Only the coordinator changes this task graph and canonical design.
Linux checks use the existing WSL Ubuntu runtime and disposable databases owned
by this batch; historical stores and evidence remain untouched.

## Historical S0–S3 implementation plan

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

## COMPLETION (assessment `origin/codex/cognitive-batch-01-assessment`,
prompt `WORKER-REPRESENTATION-01-COMPLETION.md`, base `f91654c`)

Agenda v3 accepted as scoped prototype; representation apparatus
accepted as progress; acquisition/held-out transfer incomplete.
Discipline: skill `git-worktree-discipline` (`.worktrees/<job>`,
`wt/<job>`, disjoint ownership, gate-before-merge, serial merge,
teardown). Main checkout is the orchestrator's; workers never touch it.

Phase 0 obligation map (caller/consumer traced, not name-matched):

| ID | Obligation | Implementation path | Owner | Acceptance observation | Evidence boundary |
|---|---|---|---|---|---|
| CBR-01 | Real acquisition orchestration | `acquire/live_campaign.py:40-83` (always refuses; `--grant` never reaches `preflight`) → real path: config precedence → grant admission → broker model op → response parse → candidate publish → staged invocation via `representation.run_task` → verdict; retention A/B/C; 2+2 calls/arm, caps; abstention explicit | wt/cbr01 | Configured run with deterministic constructor double reaches broker dispatch, persists returned bytes, executes them as selected candidate; always-refusing entry / ignored response / authored replacement fails the completion check | Deterministic doubles prove the path, never live acquisition; no model bytes in repo |
| CBR-02 | Held-out evaluation phase | `acquire/panel.py:20-31,109-113` (7 dev + 2 check, 0 held-out) → add 8 sw + 8 gr held-out benefit + 4 controls × A/B/C = 60 records; `RPR-ACQ/1` mechanics preserved frozen; graph exposure after core freeze; changed core = adaptation result | wt/cbr02 | Exact 60-record membership; selectors see development only; transfer leakage/changed-core relabeling challenged | Held-out never influences selection; no full-panel rerun of the losing fixture |
| CBR-03 | Full decision predicate | `experiment/checker.py:223-247` (`pilot_rule` = 4 quality clauses) vs frozen `verdict_rule` text (validity + quality + 1.25x resource + zero-denominator) → implement full conjunction + efficiency alternative + unknown/invalid/missing measurement handling + native costs + op unions | wt/cbr02 | Resource counterexample (1e6x elapsed) returns non-promising; quality-passing over-budget and unknown-measurement cases get no favorable result; existing negative stays negative | Reference recomputation independent of `pilot_rule` |
| RPR-01..08 | Prior apparatus preserved | Lane B/C/D paths unchanged except at CBR seams | coordinator | Full suite + replay/freeze checks stay green | v1/v2/agenda evidence untouched |
| EXT | Live campaign | Gateway/grant absent | external | Exact blocker + runnable command retained | Zero spend |

Windows path-spelling: normalize serialized relative paths at any
touched context/manifest seam (Owner 2); never re-freeze historical
bytes for portability. Owners: wt/cbr01 = acquisition/profile
consumption; wt/cbr02 = held-out manifest/checker/decision.
Coordinator owns shared APIs, migrations, integration, PLAN ledger.

Phase 1 dispositions (confirm/rebut with evidence, then finish together):

- CBR-01 CONFIRMED and closed (`d9d85ce`, merged `7f8d069`): the
  unconditional preflight block is replaced by configured acquisition
  (config precedence, durable-grant admission, broker-routed
  construction ops, strict response parsing, staging/publication,
  staged invocation of returned bytes, verdict recording, A/B/C
  retention). Gate `tests/test_rpr10_campaign.py` 11 passed in-worktree
  and on merged state. Second defect found in passing (durable control
  authority defaulted to 1) and fixed at the source with its own test.
- CBR-02 CONFIRMED and closed (`ee0e282`, merged `58bdeec`): 16
  held-out benefit tasks (Lane B evaluation fixtures) + 4 controls ×
  A/B/C = 60 arm-task records under separate freeze RPR-ACQ/2
  (`455c777a`); selectors from development only; graph exposure after
  core freeze. Gate `tests/test_rpr11_heldout.py` 14 passed in-worktree
  and on merged state; committed `evidence-heldout/` strict-clean
  (48 records).
- CBR-03 CONFIRMED and closed (same commit): `pilot_rule` is the full
  frozen conjunction (validity/control + quality + 1.25x resource
  bounds with zero-denominator handling) plus efficiency alternative,
  unknown/invalid/missing measurements blocking favorable claims,
  release eligibility separated. Gate: resource counterexample,
  over-budget quality-passer, unknown-measurement, and preserved
  negative all behave as required; reference recomputation independent.
- Phase 3 triage (coordinator repair `7f61be4`, all verified green):
  (a) RPR-ACQ/1 freeze bytes preserved as `manifest_acq1.*` with
  manifest selection in checker/freeze/replay — `evidence/` (27) and
  `evidence-heldout/` (48) both strict-clean; (b) transfer tests
  retargeted at held-out `gr-eva-00` with honest `evaluation` stage
  (also admitted to the `benefit` filter — the relabel initially
  emptied means/costs, caught by the gate); (c) rpr07 fresh-db failure
  claim REBUTTED — passes on merged state. Default replay check root
  stays `evidence/` (documented `--evidence-root`); cpu/exposure
  remain unmeasured in production records (blocking direction:
  unknown never certifies a win) — runner-owner follow-up, not a
  release claim.
- Phase 4 final acceptance (ACCEPT, qualified completion): fresh
  read-only reviewer at `8a4e3e2` re-derived every verdict number from
  committed bytes (freeze SHAs `455c777a`/`4674f918`, 38/31 input
  files, 60 held-out + 27 mechanics records, held-out means, costs,
  full pilot_rule recomputation → promising False, release none) —
  all MATCH. Gate files 34/34 on isolated DB `agenda01_accept`
  (shared-DB contention during review was environmental, not a
  product defect). One LOW robustness finding: `operator_view`
  rpr-check receipt lookup lacked the sibling's None-guard
  (AttributeError only if a receipt vanishes mid-read); fixed at the
  source (`fc56df6`) with a race-simulating regression test that
  fails on the old code. Live campaign stays implemented but
  externally unverified (no gateway/grant, zero spend) — the
  assignment's prescribed qualified outcome; no favorable capability
  claim is made.

End-to-end connection (WORKER-REPRESENTATION-01-END-TO-END.md, this
assignment): constructor output → retained behavior → frozen held-out
comparison → disposition → fresh-process use. Task/coverage list:

- E2E-1 carry forward: freeze the actual A/B/C retained artifact and
  selector identities, lineage, applicability, dependencies and
  budget policy after selection; evaluation consumes that record;
  explicit authored-fixture mode preserved, never silent.
  Owner wt/e2e-a. Gate `tests/test_rpr12_retention.py` +
  `tests/test_rpr10_campaign.py`.
- E2E-2 operational arms: A's lessons drive a declared method
  directive; B's procedure executes through a bounded checked path;
  C's retained composition runs; missing/rejected → recorded
  incumbent/fallback with honest cost. Owner wt/e2e-a (contracts +
  retention) for the constructor side.
- E2E-3 evaluate exact identities: 16 held-out + 4 controls × A/B/C
  bound to retained artifacts before execution; full rule from
  actual outputs/costs; same C core bytes or labeled adaptation.
  Owner wt/e2e-b. Gate `tests/test_rpr13_endtoend.py` +
  `tests/test_rpr11_heldout.py`.
- E2E-4 disposition to use: load retained result + trial/release
  status from durable state in a new process; selected use where
  authorized or persistent fallback; no forced positives, no
  eligibility bypass. Owner wt/e2e-b, incl. phase-naming public
  entry. Decisive check: behavioral (not cosmetic) sensitivity on a
  fixed diagnostic, disconnect-negative, no-candidate path.
  Independent reviewer follows digests on e2e_review DB after merge.
- E2E complete, ACCEPT (`9b96f8b`): wt/e2e-a froze `rpr-retention/1`
  + constructor contracts (`72c50f3`, gate 19); wt/e2e-b bound
  retained evaluation/disposition/use (`01233fa`, gate 20; first
  run lost to infra, finished from preserved worktree state);
  merged-tip revalidation 44 green on fresh DB; independent
  reviewer with own double confirmed digest-following (authored
  core in 0/48 arm-task + 0/4 use records), behavioral
  sensitivity (B gr-eva-00 ddmin 0.0/no_improvement vs greedy
  0.1/improved; cosmetic change flips nothing),
  disconnect-negative, no-candidate path, freeze preservation,
  fresh-process use. One INFO note ledgered (eval index quotes
  authored core digest as provenance label; suggest rename
  later). Live: implemented, externally unverified (no gateway).

Batch 02 (WORKER-COGNITIVE-BATCH-02.md, stage 8.6): Team 01
checked collaboration + retained coordination (TM-01-08), live
representation campaign + live team learning (LIVE-01-07).
Gateway live via repo adapter (endpoint .../v1, api responses,
model muse-spark-1.3-contributor-free; discovery REACHABLE, auth
AUTHENTICATED, real inference text+usage). Python for all lanes:
`/tmp/asv2-agenda01/.venv/bin/python` (no per-worktree venv).
Coordinator owns shared contracts + integration branch.

Shared contracts (frozen before dependent lanes; owner T-RUNTIME):
`team.py` workload ABI — `propose_team_plan`,
`submit_child`, `assemble_and_join`, `freeze_candidate`;
`team_plans` + `team_submissions(plan_revision,node_id,
input_digests,ownership_generation,output_digest,receipt_refs)`
tables; `team` packet kind (never the `construct` slot);
S/P/T arm vocabulary (never candidate/reference reuse, never the
TM-§5-incompatible verdict rules); budget mapping onto
allocations/reservations/`expenditure_ledger` with checker+cleanup
reserve; public entries `run_team_panel` + campaign entry, status
names highest phase completed (representation `experiment.py`
pattern). Evidence idioms: Command in / CommandResult out,
hex-sha256 digests, committed checker, CLI-addressable replay.

Lane map (one writer per checkout, isolated DBs):

- T-RUNTIME (TM-01-04 + shared schema): `src/settlement/team.py`
  (new), `run.py` (shape validation/compilation boundary only),
  `context.py` (`team` packet kind + sandbox-exec binding only),
  `store.py` (team tables), migrations. Gate:
  `tests/test_team_runtime.py` (shape refusal, real-policy plan,
  incompatible local-greens fail join, corrected combo passes,
  1-revision fence, same-DB resume after completed child).
- T-WORLD (TM-05 + oracle/control TM-08): `experiments/team01/`
  fixtures (4 families x dev/eval-x2/transfer) + manifest,
  evaluator registration, authored valid + plausible-invalid
  solutions (outside participant inputs). Gate:
  `tests/test_team_world.py` (freeze/membership/barrier/oracle
  independence). Independent against the ABI.
- T-EXPERIMENT (TM-06-08, after skeleton): public entry,
  S/P/T runner, template acquisition/selection/freeze,
  48-episode + 24-episode runners, team checker/replay +
  operator view, TM-§5 finite-panel rule implementation.
  Gate: `tests/test_team_experiment.py` (doubled mechanisms).
- R-LIVE (LIVE-01/02 representation; coordinator): existing
  `experiment.py:run_experiment` + configured HttpGatewayAdapter,
  DB `rpr_live`, finite grant v1. live1: 4/12 real responses
  (A lessons staged+verified), 8 transient gateway timeouts;
  live2 retry declared. No-candidate/fallback preserved.
- T-LIVE (LIVE-03-07; after integrated runtime/world/
  experiment gates): <=24 dev episodes, <=2 template builds,
  48 S/P/T + 24 transfer live episodes, continuity probe,
  cost reconciliation. Own campaign state/evidence, DB `t_live`.

LIVE rows: 01 real inference via broker path (adapter proven);
02 representation full path on live bytes; 03 live team
development + diagnostic/incompatible probes; 04 model-built
template (<=1, dev-evidence only); 05 frozen 48 + 24 panels;
06 fresh-process template use + episode restart after real
child; 07 reconciled ops/receipts/usage/settlement. Verdicts:
mechanism, team benefit, retained-coordination benefit
separately; representation live disposition separately.

## EC02 — Executable Coordination 02 (base `997ffa1`, branch `codex/implementation-executable-coordination-02`)

Design: `docs/design/EXECUTABLE-COORDINATION-02.md`. New study, new
artifacts/identity/freezes; Team 01 panels are historical (lane D only).

### Settled contract baseline (G0)

- Policy `step` transport: `python <entry> <request.json> <response.json>`
  through the broker sandbox-exec path. Request carries unique decision
  identity, package digest, source/observation digest, expected plan
  revision, phase and allowed-action set; response echoes identities and
  carries one proposal (`probe|plan|rework|stop|unsupported`) plus new
  bounded state (<=16 KiB). Strict parse per
  `src/settlement/representation.py` identity-echo/validate precedent;
  unknown actions and extra effect-bearing fields are errors.
- Causal order on the new path: policy step -> controller validates ->
  `team.propose_team_plan` admits concrete plan -> admitted child
  ownership -> model-generated child repair bytes -> `submit_child` ->
  `assemble_and_join` -> independent freeze/grade. Admission precedes
  child inference (reversal of the old solver order). Operation ids
  `step_op_id`-style `(freeze, panel, task, repeat, arm)`-keyed.
- Controller owns phase (derived from accepted state, never from
  procedure memory), allowed-action sets per phase, binding checks,
  allocation subdivision, revalidation on input/byte/support change,
  and restart-from-recorded-decisions. Procedure state `m_t` is
  untrusted and carries no authority.
- Retention/publication: `capabilities.publish_candidate` (digest-bound
  bytes, verified execution op with receipts, applicability/evidence/
  scope/dependencies/budget fields) + `artifacts.stage_package`
  manifest format. No new registry. Quarantine/release commands stay
  authoritative for blocking new uses.
- Critical-seam decision (DEC-EC02-01): reuse `representation.py`
  file-invocation/identity-echo helpers + `capabilities` retention +
  `team.py` admission, with one thin study controller in
  `experiments/coord02/`. No duplicate scheduler, plugin framework, or
  per-arm solver clones. Rejected alternative: a new `coordproc`
  runtime module reimplementing transport/admission.
- Shared trial/record schema, cost union (correctness; model in/out
  tokens + calls; source/tool invocations; all sandbox ops incl. policy
  exec and protected checks; CPU/wall; elapsed; abandoned work;
  liabilities; internal accounting; external billing unknown-not-zero),
  freeze contents (package bytes, deps, input contract, exposure
  manifest, model/config, selector, baselines) and checker interface
  are owned by lane E against this baseline; lanes request changes via
  coordinator. Provenance fields: source SHA, config, package digest,
  freeze id on every live record.
- Migrations owner: lane R (`migrations/0015_*` if the operation
  ledger needs new columns; reuse is preferred, new tables need
  coordinator approval).

### Cap sheet (design §11; coordinator-recorded before spending)

Dev 48 (24 S/F calibration, 12 candidate validation, 6 A validation,
6 controls/continuity) + construction 4 broker-routed calls (2
lineages x init+repair) + eval 96 + transfer 48 + interventions 12 =
<=204 live episodes + 4 construction calls. Per-episode ceilings: 12
model calls, 128k in / 48k out tokens, 20 source/tool invocations, 64
sandbox ops, 8 policy steps, 2 children, 1 probe batch (<=4 source
invocations), 1 rework round, 900 s. Gateway/grant preflight required
before any live spend.

### Lanes (one branch + worktree + test DB each; coordinator merges serially)

| Lane | Branch / worktree / DB | Owned paths | Depends on | Status |
|---|---|---|---|---|
| D historical delivery | `ec02-lane-D` / `/tmp/asv2-ec02/.worktrees/lane-D` / `ec02test_d` | `experiments/team01/acquire2.py`, `reconcile2.py`, `run_live2.py` recovery + corrected derived analysis + closure dispositions | none | MERGED `994991c` (lane tip `da9ddad`): derived corrections + closure tests green; acquire2/reconcile2 verdict UNRECOVERABLE, see F-EC02-D01 |
| R runtime | `ec02-lane-R` / `/tmp/asv2-ec02/.worktrees/lane-R` / `ec02test_r` | `experiments/coord02/controller.py`, policy-executor seam, `migrations/0015_*` (if needed), `tests/test_coord02_runtime.py` | G0 contract | MERGED `4a19366` (lane tip `0ae9d4b`): 15 tests green on real PG post-merge; no migration needed (ledger reuse); seams for L/W/E in `reports/workstreams/ec02-R.md` |
| W workload/checker | `ec02-lane-W` / `/tmp/asv2-ec02/.worktrees/lane-W` / `ec02test_w` | `experiments/coord02/corpus/`, oracle, freeze + offline checker, `tests/test_coord02_workload.py` | G0 contract | MERGED `7bd316b` (lane tip `8ee510f`, writer-failed-takeover): 17 workload tests green; combined R+W gate 32 passed on merged tree; add/add `__init__` conflict resolved by union re-export; F-EC02-W01 stale-oracle-pin fixed via single read |
| L learning | `ec02-lane-L` / `/tmp/asv2-ec02/.worktrees/lane-L` / `ec02test_l` | experience packet, construction/selection/none path, `tests/test_coord02_learning.py` | G0 + R/W interfaces | MERGED `e0b7378` (lane tip `76b011a`): REAL-episode acquisition, 4-call ceiling ledger (0 live/4 authorized, DOUBLED), strict gate, select/none, 9 tests green post-merge |
| E experiment/operator | `ec02-lane-E` / `/tmp/asv2-ec02/.worktrees/lane-E` / `ec02test_e` | four-arm entry, evidence/accounting, operator projection, `tests/test_coord02_experiment.py` | R/W/L interfaces | EARLY MERGED `25e2e3f` (lane tip `f0b74e9`): trial schema, cost union, freeze assembly, promising rule, preflight — 26 contract tests green post-merge; full four-arm entry after R/W/L |

Gates: G0 contract+delivery; G1 integrated mechanics (EC-01–10
behavior evidence, real PG + subprocesses); G2 live vertical +
acquisition (reviewed trace before panels); G3 frozen 96+48 (+12
interventions); G4 independent validation (4 passes) + delivery.
Skills substitution: no environment skills named by the design are
present; applying AGENTS/WORKFLOW principles directly, reported here.

### Fresh-chat recovery status (coordinator, post-`322c1e5` merge)

- Prior chat: fetched assessment branch, committed G0 baseline
  (`e9edbea`), created `ec02-lane-D` + worktrees `integ`/`lane-D`.
  Both worktrees clean at `e9edbea`; no writer processes running;
  lane-D worktree free for takeover without stand-down.
- Operation state observed: gateway `http://localhost:6446/v1` up with
  `muse-spark-1.3-contributor-free`; PostgreSQL up; historical DBs
  (`live2camp`, `live2test`, `ec02test_d`) intact; live2 evidence
  bundle committed under `experiments/team01/`.
- Assessment tip `322c1e5` merged additively (WORKER recovery
  clarification only); G0 baseline preserved, no work discarded.
- Old-writer spend: no new model/DB effects observed from the prior
  chat beyond the committed G0 file change; campaign accounting
  starts from the live2 ledger plus preflights recorded below.
- Next: spawn lanes D/R/W against this base; L after R/W interfaces;
  E against shared contracts early, full entry after R/W/L.
- DONE: lane D merged (`994991c`). Post-merge gate: closure tests
  10 passed; generator reproduce byte-identical; raw evidence bytes
  untouched; team solver+experiment 7 passed + 16 skipped (DSN-gated)
  without DSN, and 22 passed + 1 pre-existing failure with
  `SETTLEMENT_TEST_DSN` set (see F-EC02-D01).
- F-EC02-D01 (known pre-existing failure, diagnosed per
  diagnosing-bugs loop, NOT a regression): tight loop
  `SETTLEMENT_TEST_DSN=<dsn> .venv/bin/python -m pytest
  tests/test_team_solver.py::test_build_returns_none_on_empty_replies -q`
  goes red in <1s with `ImportError: cannot import name 'acquire2'`;
  differential old-vs-new (base `6d5f4f7` vs merged `994991c`)
  gives identical failure; `git log --all` proves the module never
  existed on any branch. No correct fix seam exists: fabricating
  the module would misrepresent historical provenance (forbidden by
  the closure assignment), and weakening/deleting the test would
  hide the open delivery obligation. Disposition: test kept as-is
  as the standing probe (goes green only on legitimate recovery);
  prevention lesson: executing workers must commit campaign modules
  before their environment is recycled.
- Integration acceptance includes a slop-reduction pass over each
  lane's new code before the gate is declared: one source of truth
  per behavior, delete-first, net-negative diff, lane's committed
  tests as the preservation oracle.
- LIVE GRANT BLOCKER (coordinator preflight): gateway reachable and
  model `muse-spark-1.3-contributor-free` listed, but inference
  requires a key and no campaign grant is present in this fresh chat
  (`TEAM01_LIVE_API_KEY` and `SETTLEMENT_GATEWAY_KEY` absent;
  unauthenticated `/v1/responses` returns `Invalid API key`). No
  other key will be spent as a substitute. Consequence: G2/G3 live
  acquisition and panels cannot run until the human provides the
  grant; all live-independent work (G0/G1, lane D, corpus, runtime,
  construction/selection code with doubles, harness with fake
  gateway) proceeds meanwhile. Runnable remaining command once the
  grant exists: `TEAM01_LIVE_API_KEY=<grant> <lane-E entry>` (exact
  entry path to be fixed by lane E).

### Completion correction (base `2fd203e`, review `d2d8924`)

Review disposition: useful fixture apparatus, incomplete live
implementation (ECR2-01–05). M0–M5 per
`WORKER-COORDINATION-02-COMPLETION-CORRECTION.md`.

| Lane | Branch / worktree / DB | Owned paths | Status |
|---|---|---|---|
| exec (ECR2-01/05) | `wt/ecr2-exec` / `.worktrees/exec` / `ec02test_exec` | `experiments/coord02/entry.py`, `tests/test_coord02_ecr201_205.py` | active |
| learn (ECR2-03/04) | `wt/ecr2-learn` / `.worktrees/learn` / `ec02test_learn` (+`ec02test_sentinel`) | `experiments/coord02/experience.py`, `tests/test_coord02_learning.py` | active |
| evid (ECR2-02/05) | `wt/ecr2-evid` / `.worktrees/evid` / `ec02test_evid` | `experiments/coord02/schemas_evidence.py`, `tests/test_coord02_ecr202.py` | queued |

Coordinator-owned: evidence inventory + 20/24 reconciliation
(done, in `evidence-live/NO-ACQUISITION.md`); serial merges +
post-merge gates; live campaign launch/resume; M2 battery; M3–M5.
Rule (standing): live-evidence DBs never equal a test default
(`ec02test_live` isolated after the `ec02test_l` TRUNCATE
incident).
- M0 DONE: review merged additively (`2fd203e` over `0b47dcf`);
  probes reproduce all five findings on the merged tip; surviving
  live records exported (`ec02test_live`: 16 receipt rows);
  count reconciled 24 admitted = 20 explained + 4 records-lost.
- Grant ledger: design 4 construction calls spent many times over
  across 6 uncoordinated rounds (durable campaign counter landed in
  learn lane ECR2-04); episode grant 0/204 spent; no live
  construction without an explicit grant (correction §3).
- M2 DONE (tip `63090c8` = merge of `bec33ff` on `wt/ecr2-m2`):
  `tests/test_coord02_m2_qualification.py` 12 passed on
  `ec02test_m2` (doubled gateway only); EC-01..10 + pressure +
  counterbalanced covered; red-first exposed a misplaced quote in
  `_POLICY_F_CONDITIONAL` input_bindings (one-line fix in
  `experiments/coord02/entry.py`; every F policy execution died with
  SyntaxError); report `reports/EC02-M2-QUALIFICATION.md` holds the
  per-EC table + red→green log + fresh-checkout commands.
  Post-merge full gate: 72 passed, 1 pre-existing failure
  (`test_entry_write_evidence_round_trip:531`, fails at base, lane-E
  scope). `ec02test_live` receipts still 16, untouched.
- M3 DONE (tip `a2ee2b0` = merge of `3a1ce83` on `wt/ecr2-m3`):
  `tests/test_coord02_m3_acquisition.py` 9 passed on `ec02test_m3`
  (doubled gateway only); nine tests: two dev tasks acquired, both
  lineages init+repair through the broker with durable ledger
  consumption, none-selection with explicit machine-readable reason,
  winner-linkage path proven with executable vs inert stand-ins,
  S-fallback attribution, budget consumption on invalid/empty, verbatim
  preflight refusal. Zero production lines changed. Report
  `reports/EC02-M3-ACQUISITION.md` holds per-claim table, verdict
  (`none` — neither candidate executable under the contract), blocked
  command, fresh-checkout commands. Post-merge gate: 21 passed
  (M3 9 + M2 12). Selection verdict: none. Preflight: admitted false
  (no endpoint/key/model/grant). Old no-acquisition verdict stands only
  on absent grant. `ec02test_live` receipts still 16, untouched.
- M4 DONE (tip `3c032bd` = merge of `182d62c` on `wt/ecr2-m4`):
  `tests/test_coord02_m4_frozen.py` 8 passed on `ec02test_m4`
  (doubled gateway only): none-selection freeze with digest chain,
  144/144 cells executed (96 eval + 48 transfer) with zero silent
  skips, 36/36 L slots on explicitly-attributed S-fallback
  (`none-selection:S-fallback`, zero records mention `learned`),
  same-DB resume (reconcile/skip/rerun + freeze-tamper detection),
  fresh-process transfer load + binding outcomes, 0/12 interventions
  (both honestly inactive — no retained execution to target),
  failure records with settled costs + receipts. All-144-failure
  outcome is genuine doubled behavior (production path wires
  `solved_child_factory` raw snapshots, not the solved fixture).
  Two genuine production fixes: L-slot records keep the scheduled
  arm (`entry.py`); checker panel-filter shadowing (`checker.py`).
  Report `reports/EC02-M4-FROZEN.md` holds per-claim table, exact
  cell accounting, harvest tallies, fresh-checkout commands.
  Post-merge gate: 20 passed (M4 8 + M2 12); learning 19 passed on
  lane code. `ec02test_live` receipts still 16, untouched.

## EC02-CLOSURE + AD01 (assignment `WORKER-EC02-CLOSURE-AND-AUTONOMOUS-DEVELOPMENT-01.md`, base `fa777d5`, branch `codex/implementation-executable-coordination-02`)

Assessment `reviews/EC02-COMPLETION-ASSESSMENT.md` (all six ECA confirmed
against source at `fe41fb6`, none rebutted; probes
`reviews/probes/ec02_completion_review.py` +
`ec02-completion-observed.json` preserved as historical evidence, never
to be edited green). Old M0–M5 labels are superseded; disposition below
distinguishes implemented helpers, apparatus-tested behavior, live
observations, blocked work and final delivery.

| Old label | Assessed status (not a completion claim) |
|---|---|
| M0 | Partial: 24-vs-20 count reconciled, 16 live receipts preserved; durable authority + destructive-test protection still caller-dependent (ECA-05) |
| M1 | Not complete: public entry builds `FakeGatewayAdapter`, child factories return unchanged snapshots, A proposals do not govern the controller, accounting helpers unwired (ECA-01/02) |
| M2 | Partial fixture coverage, not all EC-01–10 obligations (response-to-effect flow, interrupted execution, fresh-process use missing) |
| M3 | Live blocked in worker env; new `none` cases are doubled/author-controlled, not a new live campaign |
| M4 | Not the commissioned live comparison: 144 doubled fallback cells are apparatus checks; no-acquisition/fallback disposition was the design-prescribed outcome |
| M5 | Not complete: production reproduction, integrated reconstruction, architecture conclusions open |

Recovery (coordinator, this session): HEAD `fa777d5` == assessment tip
(zero diff, additive); no writer processes running; prior lane writers
stood down (worktrees `.worktrees/{evid,learn,m2,m3,m4}` clean, all
merged); PG16 up; lane DBs + `ec02test_live` (16 receipts) intact;
`.gitignore` restored to HEAD (prior-session `AGENTS.md`/`CLAUDE.md`
ignores were stale — `fa777d5` legitimately modifies `AGENTS.md`);
`tmp/` + root `CLAUDE.md` left untouched. Identity Nightjar,
additive commits, no push until final handback.

Live authority (coordinator env, names only): `SETTLEMENT_GATEWAY_ENDPOINT`,
`TEAM01_LIVE_API_KEY`/`SETTLEMENT_GATEWAY_KEY`, `TEAM01_LIVE_MODEL`,
`EC02_LIVE_GRANT_EPISODES`/`_CALLS`, `AD01_LIVE_GRANT_*` all unset.
Single human grant ask recorded below; deterministic work proceeds
regardless. Lane prompts carry no credential values, ever; lane DBs only,
never `ec02test_live`.

### Cap sheets (coordinator-recorded before spending; ceilings, not quotes)

EC02-closure caps (design §11): dev 48 + construction 4 (2 lineages x
init+repair) + eval 96 + transfer 48 + interventions 12 = ≤204 live
episodes + 4 construction calls. Spent: 0/204 episodes; construction
authority exhausted across 6 prior uncoordinated rounds (durable counter
landed in learn lane ECR2-04) — no live construction call without an
explicit new grant. Per-episode ceilings: 12 model calls, 128k in / 48k
out tokens, 20 source/tool invocations, 64 sandbox ops, 8 policy steps,
2 children, 1 probe batch (≤4), 1 rework round, 900 s.

AD01 caps (design §6, proposed maximums, not spending authority): 3
worlds x (I/R pair) = 6 trajectories; per trajectory 6 agenda boundaries,
≤3 dev episodes, ≤2 lineages / 4 construction calls incl. repair, ≤16
diagnostic queries, ≤60 model calls incl. final use; 12 protected use
tasks/world = 72 use records. Token/wall/source/sandbox aggregates set in
a committed cap sheet after dev-only calibration, before freezing.
Existing smaller grant/profile ceilings still bind.

### Call graph (actual public entry; ECA sites marked)

`main` (entry.py:644) → `preflight.require_live` → `gateway_factory`
(:640, always `FakeGatewayAdapter` — ECA-01) → `freeze_mod.build_freeze`
→ `run_panel` (:544, no gateway/model forwarded — ECA-01) → `run_cell`
(:450) → `seed_episode` (controller) → `arm_decision` (:254) →
`_interpret_with_model` (:217, A-only broker MODEL_INFERENCE op; proposal
never delivered into controller state — ECA-01) → `arm_child_factory`
(:297, FIXTURE-only → `solved_child_factory` (:321); `live_child_factory`
(:309) identical stand-in — ECA-01) → `run_episode` (controller) →
`restage_tree` (:580) → `stage_record` (:412, drops fallback marker on
staged trees — ECA-03) → `SE.build_trial_record` → `write_evidence`
(:597, per-op cost copy — ECA-02) → `checker.check_evidence`. Costs
`_cell_costs` (:364, constants — ECA-02); receipts `_cell_receipts`
(:381, run-ID substitute — ECA-02). Acquisition: `acquire`
(experience.py:1141, fresh UUID campaign per call — ECA-05) →
`acquire_episodes` → `ConstructionLedger` (:479, prefix-counted, pending
ignored — ECA-05) → `construct_lineages` → `validate_on_development`
(:1016, `valid_execution = solved or fallbacks` — ECA-06) →
`select_candidate` (:1067) → `freeze_selection` (:1183,
package_digest/entry_digest-or-none — ECA-04) → `publish_retained`.
Resume `SE.resume_plan` (:529, procedure+frozen digest compare —
ECA-04). Protection `designate_db` (:683, append-relabe­l) /
`prepare_disposable_db` (:699 — ECA-05).

Shared-file ownership (sole writers; change requests via coordinator):
`experiments/coord02/entry.py` → T-EXEC; `schemas_evidence.py` +
`experience.py` → T-STATE; `controller.py`, `checker.py`, `freeze.py`,
`oracle.py`, `preflight.py`, `schemas.py`, `policy_exec.py` →
coordinator-shared (no lane edits); `experiments/representation/` +
AD01 world/checker paths → T-ADEV; new `experiments/ad01/` →
T-ADTR; `reports/PLAN.md`, closure reports → coordinator only. New test
files per lane; no edits to existing `tests/test_coord02_*.py` without
coordinator approval; existing M2/M3/M4 batteries preserved as fixture
evidence, never weakened to bless reconnects.

Pinned cross-lane record contract (both sides implement, reviewer
falsifies): trial record carries `arm` = scheduled/requested arm,
`executed_treatment` ∈ {S,A,F,L-acquired,S-fallback}, `fallback_reason`
(null or `none-selection:S-fallback` etc.) persisted by `stage_record`
independent of grading outcome; resume skips iff
`procedure_digest == freeze.package.package_digest` with outcome present
(success via frozen_digest match, settled failure explicitly admitted);
`freeze_selection` writes one canonical `package_digest` (sha of entry
bytes; `none` kind carries reason, no digest); `designate_db` refuses to
relabel an existing evidence designation disposable (append-only history
kept, latest-evidence wins); `validate` reports parse/profile/execution
validity, task quality, fallback separately — `select_candidate` ranks by
the frozen ordering on quality given validity, never fallback-alone.

### Task graph

Machine capacity: 2 CPUs / 7 GB — at most 2 PG-heavy lanes concurrently;
long suites run serially with progress output. Isolation: temp worktrees
`.worktrees/<job>` (merged/discarded then deleted, never pushed),
branch `wt/<job>`, own disposable DB, own scratch; Nightjar identity;
`git add` only owned paths.

| ID | Req | Owner branch / worktree / DB | Owned paths | Depends on | Output + rejecting check |
|---|---|---|---|---|---|
| T-EXEC | ECA-01 (+ entry side of 02/03) | `wt/ec02-exec` / `.worktrees/exec` / `ec02test_exec` | `entry.py`, `tests/test_coord02_exec.py` (new) | pinned contract above | Real adapter/model propagation main→panel→cell; A proposal delivered into admitted controller state (`stop` stops, repair bytes determine submission); broker-routed child generation post-admission; frozen evidence-based F; L executes acquired bytes; `live_child_factory`-as-unchanged-input deleted. Reject: recording adapter with unexpected valid outputs changes submitted+graded bytes at the public entry; poisoned reference loaders change nothing; distinct A `stop`/`unsupported` diverge |
| T-STATE | ECA-02/04/05/06 (+ schema side of 03) | `wt/ec02-state` / `.worktrees/state` / `ec02test_state` (+`ec02test_sentinel2` guard probe) | `schemas_evidence.py`, `experience.py`, `tests/test_coord02_state.py` (new) | pinned contract above | Per-op canonical records → cell/phase/campaign union (unknown stays unknown, failures/liabilities/shared counted once; no constants, no per-op cost copy); stable campaign root with atomic admission + unresolved-effect hold (re-entry + concurrent final-slot proof); evidence-DB relabel refusal on isolated sentinel; validity/quality/fallback separated in validate+select. Reject: nonuniform multi-op/replay recomputation from durable rows; interrupt-after-probe/child/publication resumes same campaign with identities intact; fabricated digests run, unmodified records skip via the public resume entry |
| T-ADEV | AD01 §§4–7 | `wt/ad01-env` / `.worktrees/adev` / `ec02test_adev` | AD01 splits/checkers under `experiments/representation/` + `experiments/ad01_worlds/` (new), `tests/test_ad01_env.py` (new) | representation inventory (read-only) | New AD01 freeze + dev/use split (software trace-reduction + graph-counterexample domains), pressure controls, objective + independent checker; authored controls validate each opportunity incl. dependency-invalidated deletion, unproductive direction, cheap-suffices. Reject: checker reproduces membership + refuses altered/missing/duplicate records |
| T-ADTR | AD01 §§2–6,8 | `wt/ad01-traj` / `.worktrees/adtr` / `ec02test_adtr` | `experiments/ad01/` (new trajectory entry: agenda/packet/development/retention), `tests/test_ad01_traj.py` (new) | pinned contract + T-EXEC/T-STATE seams (develop against contract first, integrate after C1) | System-chosen investigation cycle on the public trajectory entry: model-proposed investigation from real experience → diagnostic → attributed observation → construct/check/reject → resume/use repertoire; I + R arms, frozen selection, full cost union. Reject: changed evidence changes the next decision (deterministic control); renamed bookkeeping identities do not; success AND no-candidate paths both execute |
| T-VERIF | C1 + §5 challenges 1–4 | `wt/ec02-verif` / `.worktrees/verif` / `ec02test_verif` | `tests/test_ec02ad_verif.py` (new), `reports/workstreams/verif.md` | merged C1 base (starts after T-EXEC+T-STATE merge) | Independent C1: real public path + recording adapter (unexpected valid outputs), positive + rejecting behavior, real op unions, final-slot admission, resume on real PG; then causal/state/learning/fresh-checkout challenges with own counterchecks. Not satisfied by helper-only tests |
| Q-SLOP x3+ | quality religion | coordinator, post-merge | each merged lane diff | lane merge | `/slop-reduction` pass per merged lane (≥3 total): one source of truth per behavior, delete-first, net-negative-or-justified; lane tests are the preservation oracle |
| Q-BUG x3+ | falsification | coordinator/reviewer | integrated tip | C1 merge; pre-C2; pre-handback | `/parallel-bugfix` swarms (≥3 total): competing-hypothesis agents on the integrated path chase buggy/flaky/incomplete behavior per ECA/AD gates |

Gates: C1 shared execution (T-VERIF on merged T-EXEC+T-STATE) → C2 live
EC02 closure (grant-gated; none-acquisition → explicit incumbent fallback,
no 144-cell learned rerun) → C3 AD01 qualification (T-ADEV+T-ADTR
integrated) → C4 AD01 live (separately granted: 1 trace + review, then 3
paired worlds / 72 records) → C5 handback (`reports/EC02-CLOSURE.md` +
`reports/AUTONOMOUS-DEVELOPMENT-01.md`, recomputed verdicts, receipt
reconciliation, provenance, fresh-checkout commands, ECA/AD dispositions,
bottleneck ranking ≤3). No gate skipped by redefinition; no test retired
without replacement evidence.

Live-ask (single, this batch): endpoint + key + model + EC02 episode grant
(C2: ≤204 live episodes + explicit construction-grant renewal — prior 4
spent) + AD01 separate allocation (C4: trajectory maximums above + 72 use
records + calibration charged/labeled). Sign, counts and blocked phase
asked once; implementation + C1/C3 deterministic qualification proceed
while waiting. No live spend on discovery alone; inference auth ≠ grant.

T-ADEV MERGED (`14f94b6` = merge of `6929023`): frozen ad01 3-world
freeze + content-hashed manifest, R rotation, seed repertoire, 5
pressure controls + evidence-path base, independent checker, benefit
rule, agency-boundary schema. Post-merge gate: 30/30 green on merged
tip. RPR fixtures byte-identical. T-EXEC MERGED (`d329dea` = merge of `96a528a`, coordinator-reclaimed
after 3 lane stalls): real adapter/model propagation, interpreted A
proposals on the decision chain, admitted child bytes,
`live_child_factory` deleted, F on probe evidence, L executes retained
bytes. Post-merge gate 20/20 (exec 8 + M2 12); lane regressions
learning+experiment 50, M4 8 green. Pending T-STATE integration:
`executed_treatment`/`fallback_reason` schema threading.
T-STATE MERGED (`55671ea` = merge of `7987aae`): canonical store-row
unions, unified resume digests, stable campaign root, validity split.
Coordinator amendment `38bb4b0` (ecr202 unknown-stays-unknown).
Coordinator integration repair `a77f6f9` (none-selection resume skip;
M4 resume_same_db adjudicated: new-contract gap, not environmental —
fabricated-record rejection preserved). Combined gate 45/45
(state 16 + M3 9 + M2 12 + exec 8) + ecr202 8/8 on merged tip. Full M4
re-run proving the repair. T-ADTR relaunched (transient 503, clean
tree, verified no orphaned work) and implementing slice-by-slice
(tracer + admit + diagnostic slices green with sensitivity proofs).
M4 amendments (uncommitted until battery proves on a quiet tip):
`second[skip]` 0→141 (old assertion encoded the flagged
contradiction); digest-cells evidence carries real receipts/ops;
schemas follow-up accepts the explicit none-marker on digest-less
freezes. Lesson: never commit under a running long fixture (two
self-inflicted repo_base staleness failures).
First /parallel-bugfix hunt (coordinator, direct probes): found and
closed a REAL hole — resume_plan skipped fabricated receipt-less
stubs on the default path (reconciled set was opt-in). `37a6f7a`
requires non-empty claimed identities for any skip; ecr202 + M4
evidence amended to the contract. M4 full battery proving on the
hardened tip now.
T-ADTR MERGED (`9b8394d` = merge of `bd18150`): public trajectory
entry, PG resume + fresh-process CLI proof, I/R arms, frozen use +
fallback, cost union, protected-use barrier. Post-merge gate 50/50
(traj 20 + env 30). All four lanes merged; C3 qualification complete
on deterministic doubles. Next: T-VERIF (C1 independent gate).
T-VERIF MERGED + RE-VERIFIED (`aed2887`): 28 green on repair tip,
D1/D2/D3 CLOSED, C1 unconditional pass. Post-merge gate 52/52
(verif 28 + exec 8 + state 16). Coordinator VERIF repairs committed
(dead repairs branch deleted; provenance threading; stage_record
provenance; M2 stub to contract).
C2 runbook (coordinator-owned, runs now that C1 passed; live authority
in coordinator memory only): DB `ec02test_c2live` (allocated empty);
grants `EC02_LIVE_GRANT_EPISODES` + `EC02_LIVE_GRANT_CALLS` declared in
the run environment (construction renewal explicit — prior 4 spent);
entry `python -m experiments.coord02.entry --panel development` for
acquisition first, then evaluation/transfer only if a valid candidate
is selected (none → explicit incumbent fallback, no 144-cell learned
rerun); preflight admitted-required before any spend.

Live-authority finding (coordinator preflight 2026-09-15, memory
`ec02-ad01-live-gateway-config`, coordinator use only): gateway discovery
200 with key auth; assigned model listed; one minimal inference probe
returned a real response with measured usage (15 in / 32 out tokens) —
inference IS authorized. `ec02test_live` receipts still 16, untouched.
C2/C4 proceed on lane-merged code once C1 passes; construction-grant
renewal for the 4-call ceiling is the remaining explicit authorization
(prior 4 spent across uncoordinated rounds).

## BEHAVIORAL COMPLETION (assignment `WORKER-EC02-AD01-BEHAVIORAL-COMPLETION.md`, review branch `origin/codex/ad01-completion-review` merged additively as `6fec14a`, base `23a3e68`)

Prior unconditional C1/C3 and EC02-closure labels NOT accepted (assessment
`reviews/EC02-AD01-COMPLETION-ASSESSMENT.md`, EAR-01..06). Useful components
kept: HTTP adapter propagation, A-proposal insertion, scheduled/executed/
fallback fields, validity separation, construction serialization/helpers,
evidence-DB designation protection, two-domain freezes + authored controls.

Recovery (coordinator, this session): tip `23a3e68` == reviewed base (merge
fast-forwarded to `6fec14a` with zero conflicts, no production changes);
prior writers stood down — all 10 retained worktrees clean at merged tips,
no agents running; PG16 up; `ec02test_live` receipts 16, untouched.

Cap reconciliation (§2 third bullet, recorded as discrepancy, not breach
admission): design ceiling is ≤48 dev episodes INCLUDING calibration and
validation; the committed fallback export holds 96 dev cells (12×4×2), and
`ec02test_c2live6` receipts show 26 gw receipts totaling 48,928 in /
41,812 out tokens (acquisition + validation + A-decision + fallback cells).
Live grant history supplied in-session was verbal (endpoint/key/model +
"204 episodes + 4 construction calls" with one recorded human renewal);
no redacted grant document exists in the repo. Single concrete allocation
request (C2 repair remainder + C4) goes to the human once; deterministic
work proceeds regardless.

Authority ledger (durable, from `ec02test_c2live6`): 2 live construction
ops (`coord02-L-construct-c2live6-l-{1,2}-init-{1,2}`), ZERO repair ops
(EAR-04 confirmed: profile-invalid repairs never ran); `results[].entry_bytes`
stripped from the committed export (EAR-04: candidate bytes + raw responses
not preserved); `selection: none` stands as a narrow observation, NOT a
closed study verdict.

### Interface/caller map (coordinator-pinned before split)

EC02 public path: `entry.main --panel P --model M` → `preflight.require_live`
→ `gateway_factory(doubled)` → `freeze.build_freeze` → `run_panel`
→ `run_cell(dsn, freeze, task, panel, repeat, arm, gateway, model)` →
`seed_episode` → `arm_decision` (S policy / F policy / A model-interpreted /
L retained|none) → admission (`team.propose_team_plan` precedent; policy
`step` via broker sandbox-exec precedent in G0) → SHARED child path NEW:
render permitted task/source/contract/observation inputs → ONE broker
`MODEL_INFERENCE` dispatch on the configured child model → parse + stage
ACTUAL response bytes → `submit_child` → `assemble_and_join` → permitted
public feedback → `join` → `stage_record` (arm + executed_treatment +
fallback_reason) → `write_evidence` (store-derived op union) →
`checker.check_evidence`. S keeps iterative diagnostics/self-review; A reads
`selected_source_text` = actual retained bytes (not the task snapshot); F
runs the frozen conditional on probe evidence; L invokes the exact retained
bytes. Stop/refusal dispatches zero dependent work. NO free-form `repairs`
policy field, NO hash-comment stamp channel (both deleted, not bypassed).

Operation identity: `(freeze, panel, task, repeat, arm, attempt)`-keyed op
ids; cell cost = union over that cell's settled op rows; receipt = settled
`gw:<op>` rows; shared/replayed counted once; unknown stays unknown
(no zero-fill); liabilities preserved; run-ID substitutes deleted.

Resume: `run_panel --resume` loads the SAME freeze + campaign root,
reconciles saved campaign, validates claimed ops against settled op rows
(empty/unreconciled claim refuses), continues pending with stable
identities (no fresh UUID per cell on resume).

Acquisition: seed campaign root ONCE (no fresh-UUID default) →
development episodes under the root → init construct (2 lineages) →
`validate_on_development` (parse/profile/execution validity SEPARATE from
task quality) → ELIGIBLE repair with the concrete failure (parseable but
profile/execution-invalid reaches `repair_call`; missing repair = no row,
NOT re-labeled init) → revalidate → `select_candidate` (frozen ordering,
valid-but-low-quality ≠ malformed) → freeze/retain or none+reason.
Export preserves raw responses, accepted bytes, checks, usage/receipt
lineage per attempt.

AD01 public path: `ad01-traj run|resume` → `materialize_Xt` (charter,
opportunities, prior diagnostics incl. failures, repertoire, pending,
remaining) → context-packet learner request → `admit_investigation`
(validates, commits identity BEFORE dispatch) → dispatcher executes the
ACCEPTED target (not the task-loop item); `stop` dispatches zero episodes.
I selects the opportunity from the visible set; R takes the frozen
curriculum item, same learner/constructor/evaluator after. Inspection work
consumes boundaries WITHOUT construction capacity; 6 boundaries ≠ 6 dev
episodes (independent counters). Construction: broker MODEL_INFERENCE via
the representation profile → model-produced source OUTSIDE the seed menu →
check → immutable artifact/version → `freeze_repertoire` → fresh-process
`run_use` loads EXACT retained bytes (never seed-menu lookup by name).
Persist decision+pending BEFORE dispatch; resume reconstructs X_t incl.
repertoire. Caps per trajectory: 6 boundaries, ≤3 dev episodes, ≤2
lineages/4 construction calls, ≤16 diagnostic queries, ≤60 model calls
incl. use (+ aggregate token/wall/source/sandbox ceilings in the cap
sheet). `claimed_ops` invention deleted; `ensure_campaign` 1000-unit
insert replaced by the durable grant mechanism.

### Acceptance matrix (each row: claim → rejecting check on the PUBLIC path)

| # | Claim | Rejecting check |
|---|---|---|
| A1 | Child bytes are model-generated | Recording adapter with unexpected-but-valid bytes changes submitted + graded artifacts; comment-only bytes change digest but NOT behavior |
| A2 | A proposal drives work | Distinct selected target dispatched; `stop`/refused ownership → zero dependent calls |
| A3 | Learner sees real experience | Successive packets carry actual diagnostics, failed hypothesis, remaining budget + real charter (never `unmeasured` seed / `{}`) |
| A4 | Acquired ≠ relabeled seed | Outside-menu executable supplied via the model seam, seed fallback disabled for the control, exact retained bytes execute in a new process |
| A5 | No caller bypass | Public CLI un-monkeypatched; doubles ONLY at the configured adapter seam |
| A6 | Costs measured | Nonuniform receipts + shared op + failure + unknown liability reconstruct cell/phase/campaign exports from durable rows |
| A7 | Resume keeps learning | Kill-before-dispatch vs kill-after-receipt vs uninterrupted: same pending/ops/caps/X_t/repertoire/use; invented claims refuse |
| A8 | Repair rows ↔ calls 1:1 | Parseable-but-profile-invalid source reaches repair with its failure; every attempt row maps to its own admitted call |
| A9 | I/R differ at selection | Same world + opportunity set; I proposal changes selection, R curriculum governs; shared learner after |
| A10 | Blockers stay open | Cross-lane issues open until the integrated consumer proves them; report asserts no more than proven |

### Task graph (machine: 2 CPU / 7 GB — max 2 PG-heavy lanes; serial merges)

| ID | Req | Branch / worktree / DB | Owned paths | Depends on | Output + gate |
|---|---|---|---|---|---|
| B-MAP | §4 map+matrix | coordinator, integration branch | `reports/PLAN.md` (this section) | — | committed before split (this commit) |
| B-EXEC | EC02 child path + entry | `wt/b-exec` / `.worktrees/bexec` / `ec02test_bexec` | `entry.py`, `controller.py` (child seam only), `tests/test_bexec_child.py` (new) | B-MAP + read `experiments/team01/solver.py`, `experiments/representation/acquire/` | Shared admitted child dispatch (S/A/F/L), retained-source A, entry wiring; A1/A2/A5 |
| B-AUTH | op projection + budgets + resume | `wt/b-auth` / `.worktrees/bauth` / `ec02test_bauth` (+sentinel) | `schemas_evidence.py`, `experience.py` (ledger/campaign/acquire paths), `tests/test_bauth_evidence.py` (new) | B-MAP | Store-derived unions, durable campaign root, eligible-repair acquisition, preserved raw/bytes export; A6/A7/A8 |
| B-INIT | AD01 packet + I/R + CLI | `wt/b-init` / `.worktrees/binit` / `ec02test_binit` | `ad01/trajectory.py` (packet/dispatch/resume), `ad01/cli.py`, `tests/test_binit_action.py` (new) | B-MAP | Operative actions, real packets, CLI run/resume; A3/A9 (+A5 CLI half) |
| B-ACQ | AD01 construction + repertoire + use | `wt/b-acq` / `.worktrees/bacq` / `ec02test_bacq` | `ad01/trajectory.py` (construct/retain/use paths — COORDINATED with B-INIT, merged serially), `ad01/records.py`, `tests/test_bacq_method.py` (new) | B-MAP + representation profile (read-only) | Outside-menu construction, versioned repertoire, fresh-process use; A4 |
| B-VERIF | independent C1 + challenges | `wt/b-verif` / `.worktrees/bverif` / `ec02test_bverif` | `tests/test_bverif_public.py` (new), `reports/workstreams/bverif.md` | merged B-EXEC+B-AUTH (+B-INIT/B-ACQ for cross checks) | A1–A10 on the integrated public path; frozen-study replay; receipt reconstruction |
| B-SLOP x3+ | delete-first passes | coordinator post-merge | each merged diff | lane merge | net-negative-or-justified per lane |
| B-BUG x3+ | falsification swarms | coordinator/reviewer | integrated tip | C1 merge; pre-C2; pre-handback | competing-hypothesis hunts per ECA/EAR/AD |

Shared-file rule: `ad01/trajectory.py` has TWO writers (B-INIT packet/
dispatch, B-ACQ construct/use) — split by function region, coordinator
merges serially, second lane rebases on the first merge. `entry.py` sole
B-EXEC; `schemas_evidence.py`/`experience.py` sole B-AUTH. No lane edits
`reviews/probes/` (characterization evidence, never inverted), existing
`tests/test_coord02_*` / `test_ad01_*` (preserved, never weakened), or
another lane's paths.

Gates: C1 (B-VERIF on merged B-EXEC+B-AUTH) → C2 authorized outcome
(eligible repairs under existing authority OR one concrete blocked-
remainder request; bounded honest fallback; NO new 96-cell panel, NO
144 learned cells) → C3 (B-INIT+B-ACQ integrated, 6 trajectories + 72
use records on labeled doubles) → C4 (separate allocation: 1 trace +
review, then 3 paired worlds) → C5 (EC02/AD01 reports + PLAN + roadmap
+ review request, full EAR/ECA/AD/C matrix). Live-ask (single, this
batch): C2 repair remainder (2 calls spent, 0 repairs run — request the
finite repair/validation delta under the recorded grant) + C4 caps
(input/output tokens, model calls, witness queries, sandbox/source
work, wall time). No live spend on discovery alone.



B-EXEC+B-INIT MERGED (`78864c5`): B-INIT `846a991` merged clean; B-EXEC
`0c0245e` merged with ONE trajectory.py conflict — B-EXEC branched before
B-INIT merged, so its stale copy would have reverted slice 1. Resolved by
keeping the B-INIT side (verified `charter=charter` + `dispatch_admitted_child`
both present post-merge). Post-merge gate: lane batteries 3/3 green;
existing exec+traj 23 green with the 2 known stale-shape exec failures
(`arm_child_factory` deleted API; proposal-shaped double now honestly
refused) carried for B-VERIF to update, not worked around.

B-AUTH+B-ACQ MERGED (`27400bf` over `5f1ff62`): both fast-forwarded clean
(disjoint files). Post-merge gate: 4 lane batteries 5/5 green; neighbors
74/75 with ONE pre-existing M2 failure
(`test_m2_ec06_integration_join_and_failed_join` expects
`join-failed-terminal`, gets `submit-refused`) — confirmed failing on the
unmerged base too (stashed lanes, still red), so NOT a lane regression.
Carried for B-VERIF: with the stamp channel deleted, inert-fixture cells
now refuse at submit (honest) instead of joining failed trees.

C1 GATE (`af74233`): 42-test core (5 lane + exec/state/M2) green; 90-test
neighbor sweep (traj/env/M3/M4/verif, non-DB) green; 4 DB-backed green.
VERIF follow-up repaired the 7 stale verif tests in place: repair-shaped
doubles at the child seam, stamp-deletion locks replacing stamp-presence
assertions, probe-deltas retired to a channel-deletion lock (the old
characterization probe file stays byte-frozen, never inverted). C1 PASS:
A1 (model bytes reach submitted+graded artifacts, comments-only negative
control in B-EXEC), A2 (accepted target dispatched; stop/refusal zero
dependent work), A5 (public CLI un-monkeypatched; doubles at the adapter
seam), A6 unit (store-derived cost union), A3/A4/A9 (dispatch/retention/
selection slices green).

C2 DECISION (blocked remainder, one concrete request): the durable ledger
(`ec02test_c2live6`) holds 2 live init ops, 0 repair ops — the eligible
profile-failure repairs EAR-04 requires were never run. No live grant env
is present in this session (`EC02_LIVE_GRANT_*`, gateway key/model all
unset), so no further live construction can run without a new allocation,
and the review grants no extra calls. Per §2 the remainder is preserved
exactly, not spent around:
REQUEST: a finite C2 repair allocation — 2 construction calls (the
unspent repair half of the 2-lineage × init+repair ceiling, same model +
endpoint as the recorded inits), plus validation-episode cover for
revalidate-only work on the repaired bytes. No new lineages, no new
campaign root, no eval/transfer panels (none-selection stands until a
repair validates). C4 still needs its SEPARATE AD01 allocation (trajectory
maximums in the cap sheet + aggregate token/wall/source/sandbox ceilings).
Deterministic C3 work proceeds now; live C2/C4 run automatically when
their allocations arrive.

C3 STATUS (deterministic qualification, live C4 pending): the integrated
trajectory now honors `stop` (zero-episode termination proven), routes
accepted development targets (proven), threads the real charter (no more
`{}`), and executes outside-menu retained bytes in use (A4). Default
(no-propose) campaigns still walk the task loop with seeded diagnostics —
that default is the deterministic qualification harness, NOT the autonomy
claim; the claim rests on the propose-driven paths (B-INIT/B-ACQ batteries
+ causal controls). Remaining C3: 6 deterministic trajectories + 72 use
records via the public CLI with labeled doubles demonstrating success /
rejection / no-candidate / divergent I-vs-R decisions — queued next.

C3 QUALIFIED (`73bb80c`): 6 deterministic trajectories (3 worlds × I/R)
through the public entry with labeled recording doubles + 72 use records
(12/world), all checker-clean, committed in `evidence-ad01/c3-trajectories/`
with the driver `experiments/ad01/run_c3_qualification.py`. Coverage:
success (retained), no-candidate (zero-budget boundary → explicit
incumbent use), divergent I-vs-R dispatch (I reorders, R follows the
frozen rotation). Benefit rule recomputed per arm (unchanged rule):
no-benefit on doubles, as expected — the doubles prove the path, not a
learning gain. Per-action `max_queries` threading added to `_run_boundary`
(regression-clean). C4 (live) awaits its separate allocation.

## INTEGRATION FINISH (handoff `WORKER-EC02-AD01-INTEGRATION-FINISH.md`, review `reviews/EC02-AD01-BDF12D5-REVIEW.md`, base `4e36a9a`, branch `codex/implementation-executable-coordination-02`)

Prior C1 PASS / C3 QUALIFIED labels retired until the handoff demonstrations
pass on the connected public path. Single coordinator-owned serial
integration; no parallel lanes until a unit contract fixes disjoint seams.

### Units (each: rejecting test, fix, public-path rerun on the merged result)

| ID | Obligation | Rejecting check | Status |
|---|---|---|---|
| BDR-01 | Candidate execution outside the trusted host | `tests/test_bdr01_host_boundary.py`: pollution canary, import refusal, wall-clock bound, attributed fallback | landed (`5af6384` red, `55b164f` green; 56-test AD01 battery green) |
| BDR-02 | Durable child/revision identity, two children + rework, resume without duplicate calls | distinct accepted identities, real responses, restart makes no duplicate calls | landed (`aec2fdd` + carried through merged tip) |
| BDR-03 | Admission validates full target (world/phase/split/arm); protected/cross-world/unauthorized refuse with zero dependent work | protected target refused pre-effect; legitimate dev target succeeds | landed (`aabdd48`) |
| EC02-ACCT | `costs_for_operations` wired at the public callers; no constant/synthetic costs | nonuniform + shared + failed + unknown reconstruct from durable rows | landed (`d2e3a78`) |
| EC02-ACQ | Eligible-repair orchestration: profile-invalid parseable program reaches repair with concrete feedback; missing repair has no row | every attempt row maps to its own admitted call | landed (`8521349`; live repairs remain grant-blocked) |
| AD01-LEARN | Broker-backed construction + live learner/constructor from the public CLI; recording adapters at the same seams | TBD: outside-menu program reaches later execution; fresh-process use loads frozen bytes | landed (C3 requalified `bfe1006`: 6 trajectories / 72 use, acquired members retained, accounting exports carry acquisition queries; C4 live blocked externally) |

### Decision trail

- BDR-01 (`55b164f`, tested rev `55b164f`): 56 passed (`test_bdr01_host_boundary` 4 + `test_bacq_method` 1 + `test_binit_action` + `test_ad01_env` + `test_ad01_traj`). Exclusions: live gateway, PG-backed EC02 paths (untouched). New module `experiments/ad01/method_exec.py` (subprocess child, stdio oracle-query channel, host authoritative checker + budget, AST gate mirrored from retention, fail-closed framing). Trusted-host `exec` deleted from `trajectory._run_member`. Note: `git stash` in this shared repo pulled a foreign owner's stash entry (`wt/ecr2-evid`) into a conflict on an untouched file; restored via `git restore --source=HEAD`, foreign stash left intact. Never stash here; use `git diff > file` to shelter work.

- BDR-02 (`aec2fdd`, tested rev `aec2fdd`): 3 passed (`test_bdr02_child_identity`: decompose pair carries `plan:r1:w{1,2}:work:model`, rework gets `:r2:` fresh identity through the public run_cell, resume makes no duplicate call). Regressions: `test_bexec_child`, `test_bverif_public`, `test_coord02_exec`, `test_coord02_m2_qualification`, `test_coord02_m3_acquisition`, `test_ec02ad_verif` — 59 passed, 1 stale lock updated to the new scheme. Exclusions: live gateway. Factory protocol: identity is a call argument derived at the `_submit_missing` call site from `team.child_operation`, never a closure. Receipt-first guard in `dispatch_admitted_child` (broker redispatch already dedupes; the guard states resume intent at the seam). `reviews/probes/ad01_bdf12d5_review.py` stays frozen, pinned to pre-fix behavior.

- BDR-03 (`aabdd48`, tested rev `aabdd48`): 6 passed (`test_bdr03_target_admission`: protected/cross-world/unknown/off-curriculum refuse with queries==0 and seed observation retained; curriculum item dispatches; legitimate dev target succeeds). Regressions: `test_ad01_traj` + `test_ad01_env` 50 passed; C3 driver reproduces all 19 committed `evidence-ad01/c3-trajectories/` JSONs byte-identical through the connected code. One `_target_refusal(world/arm/seq)` predicate enforced at admission and at dispatch; R defaults walk the rotation. Frozen `reviews/probes/ad01_bdf12d5_review.py` now errors at its single-identity factory probe (pinned to pre-fix behavior; assertions 1/3/5 intentionally superseded, C3-replay portion verified manually above).

- EC02-ACCT (`d2e3a78`, tested rev `d2e3a78`): 6 passed (`test_acct_store_costs`: measured nonuniform sums incl. rework calls, simulated zero+liability, union==trial reconstruction, shared-op counted once, strict raise). Regressions: `test_bauth_evidence`, `test_bexec_child`, `test_bverif_public`, `test_bdr02_child_identity`, `test_coord02_exec`, `test_coord02_m2_qualification`, `test_coord02_m3_acquisition`, `test_coord02_state`, `test_coord02_experiment`, `test_coord02_workload`, `test_ec02ad_verif` (28), `test_coord02_m4_frozen` (8) green. Exclusions: live gateway; broker suites needing SETTLEMENT_TEST_DSN skip at base (no shared settlement DB on this host). Root causes fixed, not wired around: broker stamps model_calls (old rows stay unknown), simulated usage projects as unmeasured, union unknown-rule narrowed to model effect (sandbox usage-None is normal). Migrated with justification: stale `arm_child_factory` reference (deleted in 0c0245e, red since), m4 declined scaffolding, verif union semantics. Frozen probes `ad01_bdf12d5_review.py` (asserts `_cell_costs(..)==100`) and `ec02_ad01_completion_review.py` (if asserting constants) stay pinned to pre-fix behavior.

- EC02-ACQ (`8521349`, tested rev `8521349`): 3 passed (`test_eacq_repair`: profile-invalid init repaired with stage feedback, clean init leaves no repair row, 3 admitted calls for 3 attempt rows, validation child work submits model bytes). Regressions: `test_coord02_learning`, `test_coord02_m3_acquisition` (28) green. Fixture batteries keep labeled constructors; only the live driver path changed. Incidental root-cause fix in blast radius: `publish_package_version` idempotent on same-version-same-bytes (the `test_frozen_package_use_and_retention` failure reproduces on clean base `4e36a9a` in a detached worktree — pre-existing, now green). Model inference ops now carry their team attempt id end to end.

- C5 integration batch (`repair/ec02-acquire-continuity`, tip `bfe1006`): grant enforcement landed (`666cc07` — preflight refuses construction demand below `EC02_LIVE_GRANT_CALLS`, budget/ledger/allocator bound to the declared grant capped by the four-call study ceiling); construction prompt contract fixed to carry the `--selftest` guard the profile check enforces (root cause of both live profile failures on `ec02test_c2live6`); AD01 diagnostic accounting closed (`7a4f9eb` — graph diagnostics charge the trajectory budget, executed diagnostics retained on cap refusal, fresh-process acquisition queries reconstructed from durable boundary spend); four stale test contracts migrated to the d2e3a78 rules plus grader `-I -S` containment fix and `select_candidate` empty-input none-selection (`dfc78af`, `b69c3b1`, `f3a1830`). C3 requalified at merged tip: 6 trajectories / 72 fresh-process use records, acquired members retained, acquisition queries in every export (`bfe1006`, evidence in `evidence-ad01/c3-trajectories-merged/`). Full serial suite on disposable DBs: 1216 passed, 1 xfailed, 1 pre-existing runsc-shim timing flake deselected (green in isolation and in-file; files untouched this batch). `ec02test_live` receipts remain 16. C5 reports rewritten with per-obligation dispositions. Live C2 repair + C4 allocations remain requested, not granted; gateway reachable and key valid (one health probe, no spend); inference auth is not a grant. No push before this handback is accepted.

# Investigation 01 implementation batch

Handoff: `123c21138b0f15c39303805abf1ca2d1addd7fec` (`origin/codex/investigation-transition-review`).
Reviewed baseline contained in handoff: `84d2094`.
Integration branch: `codex/implementation-investigation-01` (coordinator merges serially here).
Worktree: `.worktrees/investigation-01` (coordinator). Specialist worktrees below.
Historical plan above preserved unchanged.

## Lanes (disjoint ownership)

| Lane | Scope | Owner worktree/branch | Owned paths | Depends on | Checks |
|---|---|---|---|---|---|
| A | Honest baseline: C5 corrections, evidence export, retry/lineage reconciliation | `.worktrees/inv-a` / `wt/inv-a-baseline` | `reports/`, `evidence/**` (additive only) | design briefs | replay of committed evidence reconciles |
| B1 | Contracts/domain interfaces: task/tool semantics, context materialization, contract rendering | `.worktrees/inv-b1` / `wt/inv-b1-contracts` | contract/domain adapter modules + tests | A (claims to honor) | public-entry agreement tests |
| B2 | Shared state/resource continuation: one learner/action/result loop, single resource envelope, kill/resume | `.worktrees/inv-b2` / `wt/inv-b2-state` | state/resource/loop modules + tests | B1 contracts | envelope + kill/resume tests |
| C | Independent qualification: recording doubles, acquired program, replay boundary | `.worktrees/inv-c` / `wt/inv-c-qualify` | qualification harness + tests | B1+B2 merged | full C-lane gate through public entry |
| E | Reviewed integration: merged checks, replay, bottleneck report | coordinator worktree | merges only | A+B1+B2+C | affected + final suites, remote equality |

Lane D (live qualification) runs only on granted authorization; otherwise one cap-sheet request.

## Assignment status

| Item | Status |
|---|---|
| A. Honest baseline | merged (`b9f5480`, gate `reviews/probes/inv_a_baseline_gaps.py` 17-0) |
| B. Shared investigation path | B1/B2/B4/B3 merged; AG01 prerequisite merged (37-0, 24 prior failures were missing CREATEDB) |
| C. Qualification | merged (`dab3005`, gate 9-0, all 5 lane gates 40-0 on tip) |
| D. Live qualification | cap sheet drafted, token floor corrected to 17383, one authorization request pending human grant |
| E. Reviewed integration | both reviews merged (accept with findings); full suite running; delivery pending suite |

# Investigation 01 completion (base `cd7e156`, baseline `44f1f7c`)

Integration branch: `codex/implementation-investigation-01-completion` (coordinator only).
Worktree: `.worktrees/inv-completion`. Historical S0-S3 plan above is preserved.

Live authorization: no grant in environment (`SETTLEMENT_GATEWAY_ENDPOINT`/`KEY` absent).
Finish M1-M6 implementation plus deterministic qualification first, then one concrete request.

| ID | Milestone | Owner branch / worktree | Owned paths | Depends on | Gates (real infra marked *) | Status |
|---|---|---|---|---|---|---|
| C0 | coordinator setup | integration / `.worktrees/inv-completion` | `reports/PLAN.md`, shared interfaces, final reports | — | worktree at `cd7e156`, PG online, PLAN committed | in progress |
| C1 | M1 integrated lifecycle + M4 executable interfaces (merged `2ab42ba`; authority wired `96fe67f`) | `wt/inv-c1-lifecycle` / `.worktrees/inv-c1` | `experiments/ad01/**`, `tests/test_invc1_*.py`, `reports/workstreams/inv-c1.md` | C0 interfaces | real CLI with doubles only at provider/launcher seams*; shared-consumer swap changes/refuses both domains*; independent legal method runs through child process* | pending |
| C2 | M2 one authority + M3 feedback/recovery (merged `2b16800`, 31 gates green on tip) | `wt/inv-c2-authority` / `.worktrees/inv-c2` | `src/settlement/**`, `tests/test_invc2_*.py`, `reports/workstreams/inv-c2.md` | C0 interfaces | parent exhaustion refuses init/repair/use*; fresh-DB rerun refuses new allocation*; kill after diagnostic and after validation resumes without redo* | pending |
| C3 | M5 trace/export/replay + M6 runnable study (merged `a851392`; 7 gates green on tip; recording pilot rerun by coordinator) | `wt/inv-c3-study` / `.worktrees/inv-c3` | `scripts/inv01_study.py` (new), `experiments/doubles.py`, `experiments/ad01/records.py`, `experiments/ad01/cli.py`, `tests/test_invc3_*.py`, `reports/workstreams/inv-c3.md` | C1+C2 merged | offline replay of actual export refuses hidden-future/mismatch*; recording-provider study recomputed in fresh process* | pending |

Rules: lanes use disposable databases (`inv_c1_*`, `inv_c2_*`, `inv_c3_*`); never touch
shared `ec02test_*` databases. No test weakening. Contract changes need justification.
Coordinator merges serially with `--no-ff` and reruns affected gates.

| D1 | mid-validation dispatch reclaim plus public kill tests (merged `591ceb6`, 24 dispatch gates green on tip) | - | - | done |
| D2 | unbilled settle at measured usage (merged `9b7d079` plus view fix `45a35ba`) | - | - | done |
| D3 | prompt envelope guard plus B3 refusal pin (merged `3881b64`, 13 envelope gates green on tip) | - | - | done |
| C4 | independent re-review accepts M1-M6 (merged `a1565f3`; all prior findings closed) | `wt/inv-rereview` / `.worktrees/inv-rereview` | reviewer verdict | M1-M6 gates | pending |
| N2/N3 | ledger counts receipt-less held exposure; export caps already persisted (no change) | integration | authority.py, invc2 test | merged |

# Study readiness (base `77b4c62`, baseline `7941ab4`)

Integration branch: `codex/implementation-investigation-01-study-readiness` (coordinator only).
Worktree: `.worktrees/inv-readiness`. Earlier plans above are preserved.

Live configuration: endpoint plus local key saved in context-mode memory
(source `live-gateway-config`); endpoint serves 143 models with a free bench.
Effort high is acceptable to the human. Model survey plus live-path proof run
as lane R0. No keys in Git.

| ID | Slice | Owner branch / worktree | Owned paths | Depends on | Gates (real infra marked *) | Status |
|---|---|---|---|---|---|---|
| R0 | model survey (done: 9 working free models; pilot `nvidia/nemotron-3-ultra-550b-a55b:free`, fallback `nvidia/nemotron-3-super-120b-a12b:free`; adapter surface `/v1/responses` proven by `google/gemma-4-31b-it:free`) | none (report-back only) | config read plus probes | working free-model list with keys redacted | done |
| R1 | S1 resumable study entry (merged `e879ec1`, 13 gates green on tip with verifier active) | `wt/inv-r1-entry` / `.worktrees/inv-r1` | `scripts/inv01_study.py`, `migrations/0016_study_run.sql` (new), `tests/test_invr1_*.py`, `reports/workstreams/inv-r1.md` | R0 model list | controlled-HTTP live response traced to effect*; missing creds refuse without fallback*; restart keeps one root plus deadline*; exhausted/expired use does zero effects* | done |
| R2 | S2 interrupted decision meaning (merged `46d03a0`, 18 gates green on tip) | `wt/inv-r2-resume` / `.worktrees/inv-r2` | `experiments/ad01/agenda_policy.py`, `experiments/ad01/trajectory.py` (boundary checkpoint only), `tests/test_invr2_*.py`, `reports/workstreams/inv-r2.md` | — | kill before correction resumes into same target*; kill after diagnostic reuses observation with zero new queries*; validation recovery stays green* | done |
| R3 | S3 complete export plus verify (merged `68145a3`, 15 gates green on tip incl. CLI) | `wt/inv-r3-export` / `.worktrees/inv-r3` | `experiments/ad01/records.py`, `tests/test_invr3_*.py`, `reports/workstreams/inv-r3.md` | — | correction ops in transitions*; tamper set fails named*; reviewer recomputes without producer summary* | done |

Rules: disposable databases (`inv_r1_*`, `inv_r2_*`, `inv_r3_*`); never touch
shared `ec02test_*` or other owners' `inv_*` databases. No test weakening.
Coordinator merges serially with `--no-ff`, reruns affected gates, owns
`reports/PLAN.md` and the final live run.

Integration fix (coordinator, uncommitted R1 fallout found by full-shape
recording pilot): the use-phase gate checked root free, which is zero after
six 100k subdivisions carve an exact-fit 600k grant, so the first full run
refused at use with `insufficient-authority`. `_v1_admit` now accepts an
explicit funding allocation and the use gate passes the campaign child that
`_fresh_use` actually spends. First full pilot rc 0 with 6 exports, 24 use
records, 75 operations; recompute rc 0 with 39 model calls and 12
construction calls against the 360/24 ceilings. Completed-study rerun still refuses
with zero new operations (safe). A broader trajectory-gate change was tried
and reverted: it let a completed rerun proceed and double-count witness
queries in the run row, so the trajectory gate stays on root free. Full
suite at `d0a5c29`: 849 passed, 592 skipped, 2 setup errors in
`tests/test_broker_dbos.py` from unset `SETTLEMENT_TEST_DSN` only; the same
file gives 3 passed with URL-form DSN, so the tip is green.

Live qualification (human grant this session, report
`reports/workstreams/inv-live.md`): bounded pilot rc 0 on `inv_r1_live`
(ultra, high effort, 7 ops, real token usage, zero charge); full study
rc 0 on `inv_r1_livefull2` (6 trajectories, 6 exports, 24 uses, 47 ops,
recompute rc 0, 0 charge). The first full attempt caught a real defect
at the `verify_study` gate (reported 3 vs ledger 4 construction calls);
fixed at the source in `construct.py` with a red-first regression
(committed `a9cd159`), and the rerun above is post-fix green.

# Stage 8 closeout plus stage 9 start (base `4b25d0c`, branch
# `codex/implementation-stage-08-close-stage-09-start`, worktree
# `.worktrees/stage89`). Original live evidence in `evidence_inv01_live/`
# stays byte-identical except nothing; no rewrite is authorized.

| ID | Slice | Owner branch / worktree | Owned paths | Depends on | Gates (real infra marked *) | Status |
|---|---|---|---|---|---|---|
| A1 | executable method contract (merged `1590979`, 41 gates green on tip) | `wt/s89-a1-contract` / `.worktrees/s89-a1` | `experiments/ad01/packet.py`, `experiments/ad01/method_exec.py`, `tests/test_s89a1_*.py`, `reports/workstreams/s89-a1.md` | — | independently-written candidate calls each advertised op through child path*; nearby construct/traj suites* | done |
| A2 | archived failure diagnostics (merged `d6fa877`, post-fix rerun green, 51 gates on tip) | `wt/s89-a2-diagnostic` / `.worktrees/s89-a2` | `scripts/s89_diagnose.py` (new), `tests/test_s89a2_*.py`, `reports/workstreams/s89-a2.md` | A1 merged | 4 archived candidates re-executed unedited*; attempt classification table; no model calls | done |
| A3 | closeout verify plus report (merged `7179140`, 19 gates green on tip) | coordinator, integration tree | `reports/STAGE-08-CLOSEOUT.md`, full suite | A1+A2 merged | full public path with doubles at model boundary*; honest rejection path*; full suite* | done |
| B1 | grounding plus alternatives (merged `ea584d6`, lane branch `wt/s89-b1`) | `wt/s89-b1` / `.worktrees/s89-b1` | `reports/workstreams/s89-b1.md` (read-only elsewhere) | Phase A findings | both domain paths traced; two alternatives with usage, ownership, cost | done (preliminary pick alt 1, pending Phase A) |
| B2 | learning cycle spec (merged `e53ebef`, alt 1 confirmed) | `wt/s89-b2` / `.worktrees/s89-b2` | `docs/design/STAGE-09-ARCHITECTURE.md` (draft), `reports/STAGE-09-FEASIBILITY.md` (draft), `reports/workstreams/s89-b2.md` | B1 | contracts with transitions, identities, failure outcomes | done |
| B3 | feasibility plus next experiment | coordinator | `reports/STAGE-09-FEASIBILITY.md`, small probes | B1+B2 | risky-assumption probes*; ranked hypotheses; one experiment | pending |
| B4 | consolidation package | coordinator | `docs/design/STAGE-09-ARCHITECTURE.md`, roadmap | B1-B3 | independent review verdict | pending |

Rules: lanes use disposable `s89_*` databases and drop what they create;
never touch `ec02test_*`, `inv_r1_*`/`inv_r2_*`/`inv_r3_*` or other owners'
`inv_*`. No test weakening. Coordinator merges serially with `--no-ff`.
Live evidence stays unchanged; A2 diagnostics use separate resources.

Full suite at `257ac3c` (delegate run, real Postgres): 869 passed, 592
skipped, 0 failed, 2 setup errors in `tests/test_broker_dbos.py` from
unset `SETTLEMENT_TEST_DSN` only; the same file gives 3 passed with
URL-form DSN, so effective totals are 872 passed, 0 failed. Tree left
clean, lane databases dropped.

## Stage 9 consolidation M0-M7 (base 9984baf, branch codex/implementation-stage-09-consolidation, worktree .worktrees/s09c)

Baseline 9984baf holds implementation 1d90c2e plus review 0e142be plus contract. Stage 8 gates green here: 19 passed (s89a1, s89a2 extract, s89a2 rerun, s89a3 closeout). Live evidence evidence_inv01_live/ untouched, still no-retention. Contract docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md governs; architecture draft is historical input only.

Concrete N1-N6 pins:

N1 durable ownership: investigation id inv-<study>-<seq> independent of world/arm/schedule. State fields map to storage: objective plus visible evidence plus open questions plus active policy artifact plus scoped method bindings plus pending accepted action plus policy-private state plus revision lineage plus remaining authority. Pending accepted action persists as journal row before effects; resume reconciles same operation id without duplicate effects or renewed limits. Attempt identities: att-<cid>-<seq>; retry reuses identity, intentional revision gets new attempt. Serial first: one active policy plus at most one assessment candidate per lineage.

N2 policy ABI: STEP(view,state) JSON-in JSON-out, versioned ad01-policy-step-v1. View holds permitted task content, visible observations, unresolved questions, last action result or refusal, eligible method identities, remaining resources, contract versions. State is bounded JSON opaque to driver. Artifact holds kind, source digest, entry ABI, dependency plus instrument identities, origin (authored control, model-acquired bytes, fixture stand-in), parent digest, applicability. Child executes acquired source outside host with CPU, wall, output, state limits via method_exec child machinery. Driver validates every action; admission, evaluation, budgets stay trusted. Actions: diagnose, construct-check method, use scoped method, request model reasoning, propose revision, stop. Model request is a broker effect; response returns as next-step observation.

N3 feedback versus assessment: roles are development, operational feedback, sealed assessment. Operational-use failure opens revision. Sealed content never enters constructors. Exposure retires batch for descendants. AD01 protected-task guard stays under original protocol; new feedback uses versioned protocol. Matched arms get isolated state plus identical declared inputs; hidden-output perturbation must not change pre-assessment construction inputs.

N4 revision plus bind: proposal persists parent artifact, motivating evidence, scope, allocation, protocol. Candidates build through broker with returned-bytes validation plus one bounded repair. Freeze before assessment. Compare under fixed protocol on matched fresh opportunities with finite limits; costs include construction plus repair amortized separately. Outcomes are reject, inconclusive, retain scoped alternative, or bind active for declared scope. Bind is atomic against expected current version; parent plus rejection evidence preserved. Selection consults active eligible binding, not first family match. Execution ids bind investigation, logical action, active policy, method version.

N5 pilot: keep 28-prefix replay as conformance only. Prospective P0 frozen incumbent, P1 constructed without experience, P2 constructed with permitted experience; same interface plus allowance; candidates from returned model bytes when labeled live. At most 4 development episodes (2 per domain), 1 candidate plus 1 repair each for P1/P2 (4 construction calls max). Assessment is 12 policy episodes (2 fresh worlds per domain times 3 arms) with bounded opportunities plus 2 sealed use tasks each (in-scope plus structural variation). Per-episode caps are 6 policy steps plus 6 model calls; at most one method lineage plus one repair per episode. Ceiling is 100 new model calls; stop, unknown, no-candidate never authorizes replacement. Freeze identities, order, metric plus resource rules, config, ceilings, study root before exposing assessment. Missing candidates are unavailable arms, not rebranded baselines.

N6 migration plus acceptance: one current investigation driver; CLI and study callers become clients. Reuse broker, journal, artifacts, context, capability facilities only where real contracts fit. Domain adapter supplies content, operations, result interpretation; driver never decodes world or task-name conventions. Map old campaign state, pending decisions, checkpoints, selection, use ids to new semantics; preserve completed reproduction; pending legacy work needs lossless versioned resume proof. Public acceptance runs full deterministic cycle with doubles only at provider boundary plus fresh-process continuation plus offline verifier.

| milestone | scope | owner worktree and branch | owned paths | depends | acceptance command | status |
|---|---|---|---|---|---|
| M0 | plan plus concrete contracts | coordinator .worktrees/s09c | reports/PLAN.md, docs/design/STAGE-09-ARCHITECTURE.md, reports/workstreams/s09-m0.md | none | 19 stage-8 gates green; reviewer challenges plan vs contract | in-progress |
| M1 | persistent driver plus checkpoints | wt/s09-m1 .worktrees/s09-m1 | experiments/ad01/driver plus trajectory plus agenda_policy consolidation, migrations, checkpoint manifest | M0 | public run plus resume with interruption after acceptance and after effect, no duplicate effects | pending |
| M2 | versioned policy artifacts | wt/s09-m2 .worktrees/s09-m2 | policy ABI, child policy execution, model constructor lineage | M0, M1 driver ABI | two authored policies diverge through public entry; restart consistent; model bytes path validated | pending |
| M3 | feedback versus assessment | wt/s09-m3 .worktrees/s09-m3 | visibility boundary, exposure tracking, protected-task guard | M0 | operational failure opens proposal; hidden-answer probe leaves provider request unchanged; protected refs refused | pending |
| M4 | assess plus bind revision | wt/s09-m4 .worktrees/s09-m4 | frozen assessment, atomic bind, selection by binding | M1-M3 | full deterministic cycle plus rejection cycle, fresh-process revised bytes | pending |
| M5 | prospective pilot plus verifier | wt/s09-m5 .worktrees/s09-m5 | pilot episodes, offline verifier, evidence exports | M1-M4 | deterministic pilot plus verifier green; live only on fresh grant with exact command | pending |
| M6 | independent review | reviewer worktree | isolated DB plus worktree, own candidate | M5 | own policy challenges execution, feedback, identity, selection, resume, evidence | pending |
| M7 | deliver plus cleanup | coordinator .worktrees/s09c | reports/STAGE-09-CONSOLIDATION.md, roadmap, public command, evidence | M6 | gates pass, evidence_inv01_live unchanged, remote SHA verified | pending |

Rules: coordinator alone writes integration branch; lanes own disjoint paths and push only own wt branches; serial --no-ff merges with affected reruns. Disposable DB prefix s09_ only; never touch ec02test_*, inv_*, or other owners. No live inference without fresh human grant; spent grants never reused. Probe scripts committed and runnable from fresh checkout.

## M0R1 corrections (supersede M0 rows where they differ; reviewer F1-F11)

Storage map (F1): investigation row investigations holds id, objective, scope, obligations, sponsor, origin, disposition; revisions hold objective history. Visible evidence lives in observations plus attempt_observations plus context_views sources. Open questions live in development_opportunities plus context_views limitations plus public claims. Active policy artifact lives in artifact_versions digest plus artifact_refs plus capability_versions artifact_digest. Scoped bindings live in capability_releases versions plus scope plus disposition plus fallback plus policy_version, pinned per attempt in attempt_capability_pins. Pending accepted action lives in command_journal plus operations dispatch_state plus trajectory.record_decision. Policy-private state plus assessment exposure retirements are the only justified additions in migrations/0017_s09_state.sql: s09_policy_state (bounded JSON by attempt) and s09_assessment_exposure (batch, exposed_to, retired_at). Lineage reuses capability_versions reference_version plus artifact_refs plus investigation_revisions. Remaining authority reuses allocations plus reservations plus grants.

ABI in code (F2): experiments/ad01/policy_step.py now holds POLICY_STEP_VERSION plus VIEW_REQUIRED plus ACTION_KINDS plus ACTION_REQUIRED plus STATE_LIMIT_BYTES with pure validate_view, validate_state, validate_action. M2 imports the constant and adds the STEP child runner; no lane restates the version string.

Executor ownership (F3): STEP execution owner is M2, in method_exec.py STEP region plus policy_step.py. The M0 annex claim is corrected: ENTRY exists, STEP is M2 new work reusing child machinery.

Binding ownership (F4): selection consults capability_releases disposition default or limited plus fallback. M1 extracts trajectory._select_member plus run_use selection into experiments/ad01/selection.py (subtract first, no dual truth). M4 implements binding-aware select plus atomic bind against capability_releases.

Exposure record (F5): s09_assessment_exposure in 0017 plus claims and artifact_versions access_label hidden or evaluator plus trial_assignments blind_key. M3 owns exposure tracking and retirement; M4 consumes the retired flag, never invents lineage.

Migration map (F6): current public driver is experiments/ad01/cli.py main with run, resume, use through trajectory.ensure_campaign, _run_boundary, resume_campaign, record_decision. run_c3_qualification.py becomes a client of the driver, not a parallel driver. Old to new: investigations plus attempts plus operations plus receipts plus artifact_versions plus observations keep historical reproduction; pending legacy work drains unless a lossless versioned resume proof lands in M1.

Lane regions, waves, gates (F7, F8): wave 1 is M1 driver plus selection extraction plus 0017. Wave 2 after M1 merges is M2, M3M4, M5 in parallel.

| lane | branch | owned paths (exclusive) | tests | DB prefix | acceptance command |
|---|---|---|---|---|---|
| M1 driver | wt/s09-m1 | experiments/ad01/trajectory.py driver regions plus cli.py plus selection.py extraction plus migrations/0017_s09_state.sql plus checkpoint manifest | tests/test_s09m1_*.py | s09_m1_ | public run plus kill after acceptance and after effect, fresh resume reconciles same op, no duplicate effects |
| M2 policy exec | wt/s09-m2 | experiments/ad01/policy_step.py executor region plus method_exec.py STEP region plus construct.py lineage region plus agenda_policy.py version region | tests/test_s09m2_*.py | s09_m2_ | two authored policies diverge via public entry, restart consistent, model-bytes lineage validated |
| M3M4 visibility plus bind | wt/s09-m34 | experiments/ad01/records.py plus learner.py visibility region plus packet.py context region plus selection.py binding region plus capability_releases use | tests/test_s09m34_*.py | s09_m34_ | hidden-answer probe leaves provider request unchanged, protected refs refused, atomic bind selects revised bytes fresh-process |
| M5 pilot | wt/s09-m5 | scripts/s09_pilot*.py plus verifier plus evidence exports only (no shared runtime) | tests/test_s09m5_*.py | s09_m5_ | deterministic pilot plus offline verifier green, missing arms stay missing |

M2 depends on M1 selection.py plus 0017 merged tip. M3M4 depends on M1. M5 depends on M1-M4 for live panel but its skeleton may start in wave 2 on the M1 tip. N5 panel specifics plus token, query, runtime, wall ceilings freeze in M5. Stage 8 19-gate count is carried as coordinator-measured, M6 reruns it on the final tip.

M1 merged 1e60bb3 (lane 3cbbd10): driver persists accept before effects, selection extracted, 0017 adds s09_policy_state plus s09_assessment_exposure. Tip gates 25 passed (m1 6 plus stage-8 19). Wave 2 opens on this tip.

M2 merged eb1c6df (lane 0497c21): bounded STEP child execution plus policy constructor with lineage plus one repair. Tip gates 39 passed (m2 14 plus m1 6 plus stage-8 19). M34 plus M5 continue on disjoint paths.

M34 merged 527eb01 (lane ab2d28d): sealed filtering at packet plus learner boundary with exposure retirement plus atomic binding-aware selection. Tip gates 50 passed (m34 11 plus m2 14 plus m1 6 plus stage-8 19). M5 continues on scripts only.

M5 merged 037d176 (lane 2abfffe): prospective P0/P1/P2 pilot plus offline verifier plus doubled-r1 bundle (3 of 100 calls, P2 unavailable arm proven). Tip gates 58 passed (m5 8 plus m34 11 plus m2 14 plus m1 6 plus stage-8 19) plus verifier pass with documented PYTHONPATH. All implementation lanes merged.

M6FIX merged 5b7fd8a (lane f77f495): F1 run_use routes through binding-aware selector with dsn plus release_id; F2 use operations mint versioned identity. Tip gates 62 passed (m6fix 4 plus 58) plus verifier pass. M6 findings closed; M7 delivery opens.

Suite regression R1 fixed: M1 execute_pending dropped the journal, so the s09 resume path never consulted the diagnostic checkpoint and redid diagnostics. Fix passes journal dsn plus cid into _run_boundary; re-record skipped since accepted is present. tests/test_invr2_diagnostic.py green. tests/test_invr2_correction.py fails identically on base 9984baf, pre-existing, ledgered minor, out of scope.

Full suite on final tip: 900 passed, 12 failed, 592 skipped, 2 errors. 10 failures are test_invr3_export missing-database environmental. 1 is the pre-existing invr2_correction base failure. 1 was the R1 diagnostic regression, now fixed with 63 gates green plus verifier pass. 2 dbos errors are empty-DSN environmental, 3 passed on URL-form rerun. No sums across runs claimed as one suite.

## Completion C0-C6 (base ef36a27, branch codex/implementation-stage-09-completion, worktree .worktrees/s09cp)

Base ef36a27 holds implementation efe73a3 plus assessment with S9R-01-04 plus probe plus Jev example. Stage 8 stays closed. evidence_inv01_live untouched. Doubled bundle evidence_s09pilot/doubled-r1 stays historical apparatus evidence.

S9R verdicts (confirmed on base, no rebuttals): S9R-01 pilot builds task methods with no STEP consumer and live mode keeps recording gateways. S9R-02 probe repeats 3 preparations from a 1-call allowance with empty next-boundary state; use_method maps to development; propose_revision stops with metadata. S9R-03 bind_revision accepts caller versions with optional protocol/evaluator and no assessment gate. S9R-04 active_binding_for without release scans globally for newest; CLI exposes no release flag.

Shared meanings: investigation ad01-w<world>-<arm>-<seq>; attempt att-<cid>-<seq>; policy source_digest plus POLICY_STEP_VERSION; STEP state bounded JSON in s09_policy_state; accepted action in s09 row; pending effect in operations row; method artifact in artifact_versions; revision proposal in journal with parent digest plus scope; assessment as frozen bytes plus protocol plus evaluator verdict; active binding as capability_releases disposition default or limited plus fallback. Feedback consumers are learner prompts; STEP bytes come from construct_policy; promotion qualifies in selection bind path only.

Action map: diagnose runs run_diagnostic; construct_method runs broker construction; use_method must resolve plus execute bound method bytes; request_model routes broker op with text as next observation; propose_revision enters records revision lifecycle or durable refusal; stop ends the episode. Each persists policy identity, state transition, pending action before effects.

| lane | branch | owned paths (exclusive) | tests | DB | acceptance |
|---|---|---|---|---|---|
| C1 continuity | wt/s09-c1 | agenda_policy.py decide plus step-loop region, policy_step.py persistence region | tests/test_s09c1_*.py | s09_c1_ | allowance 1 plus repeated requests prepares once; state survives boundary plus restart; restart never redraws model text |
| C2 actions plus bind | wt/s09-c2 | agenda_policy.py proposal region, selection.py bind gate, cli.py release flag, trajectory.py release threading | tests/test_s09c2_*.py | s09_c2_ | use_method executes bytes never constructs; propose_revision reaches lifecycle or named refusal; bind refuses absent, failed, stale, wrong scope or source; two studies never cross-select; CLI release selects exact bytes fresh-process |
| C3 experiment | wt/s09-c3 | scripts/s09_pilot*.py, controlled HTTP provider, exports | tests/test_s09c3_*.py | s09_c3_ | STEP arms diverge via driver; controlled HTTP proves live adapter distinct; disconnect yields no candidate; verifier names deleted record |
| C4 live | coordinator | evidence_s09completion_live/, grant records | panel gates | s09-completion-live-01 | one bounded run on frozen spec, honest negatives kept |
| C5 review | reviewer | read-only | isolated | s09_rv_ | own bytes falsify C1-C4 plus causal sensitivity |
| C6 deliver | coordinator | reports/STAGE-09-COMPLETION.md, roadmap, plan | suite | none | matrix plus commands plus Jev record plus SHA |

Waves: C1 plus C2 in parallel after C0 review (disjoint regions of agenda_policy). C3 after C1 plus C2 merge. C4 after C3 plus Jev pre-live. Rules: serial merges, affected reruns, disposable s09_ DBs, no live inference before C4, no spent-grant reuse.

C0R1 (Jev c0-challenge): effects covered weakly, isolation insufficient. C1 acceptance now requires pending STEP action identity persisted before broker effects with reconcile gates and no model-text redraw. Isolation stands on PLAN M0R1 plus C3 freeze, missing-arm, verifier gates; C3 freezes panel specifics. Binding residual risk stays under the C2 cross-study gate. No question was rephrased.

C0R2 (plan review findings 1-5, all accepted, no rebuttals).

Action map with functions plus evidence: diagnose runs trajectory.run_diagnostic, evidence study_phases diagnostic row plus observation. construct_method runs construct.construct_method for task methods, evidence broker ops plus artifact_versions plus method record. STEP construction runs construct.construct_policy for learning policies, evidence lineage plus response digests plus repair record. use_method resolves plus executes bound method bytes through the bound executor, evidence use records plus receipts. request_model routes the broker model op in agenda_policy 380-440, evidence operations plus receipts plus settled text. propose_revision enters the records revision lifecycle or a durable named refusal, evidence journal proposal plus freeze plus assessment. stop ends the episode, evidence boundary record.

Waves replace parallel C1 plus C2 inside agenda_policy. Wave 1a: C1 owns agenda_policy.py decide plus step loop plus broker request path plus limits plus state, and policy_step.py persistence. Wave 1a parallel: C2B owns selection.py bind gate plus records.py revision records plus cli.py release flag plus trajectory.py release threading. Wave 1b on the merged tip: C2A owns agenda_policy.py _step_proposal 290-323 plus propose_revision branch 543-569 with failing-first gates. One writer per file per wave.

C2 bind gate strengthened: refuse empty protocol, empty evaluator, empty evidence references; bind exact frozen bytes only; caller labels never authorize a release; stale, failed, wrong-scope, wrong-source refused.

C3 treatment named: P0 is the frozen incumbent STEP policy; P1 plus P2 are constructed STEP policies through the same driver; executed digests must equal returned bytes; no substitution of unavailable arms; no post-outcome panel change; panel freeze owned by C3. C3 wires StepPolicyConsumer at agenda_policy.py:347 into the trajectory boundary that defaults at trajectory.py:464-476.

Public fallback closed: CLI use requires the release flag or the public path refuses; first-match fallback at selection.py:156-160 retires; two studies of one family prove mutual non-selection; resumed use resolves identical bytes or records precise refusal.

C1 merged bafe47c (lane bd116de): durable STEP state plus cumulative limits from durable counts. Tip gates 26 green. C2B continues on disjoint paths.

C0R3 (strict-refusal overreach): retiring all release-less selection broke four neighboring suites doing single-study repertoire use with digest-verified members. Corrected scope: global newest store scan stays retired; repertoire-scoped selection within the caller-passed members is restored with zero store access; CLI still requires --release; binding path unchanged. S9R-04 threat was cross-study store selection, never explicit repertoire passing.
