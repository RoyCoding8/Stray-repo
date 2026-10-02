# Verification

## Current closure checkpoint — 2026-09-30

Environment: WSL Ubuntu, Python 3.12.14, PostgreSQL 18.6, real child
processes and fixture gateways. No live inference or Jev calls ran. Historical
live artifacts and uncertain reservations were preserved.

The coordinator observed these separate checks; they are not a combined suite:

| Check | Observed result | Boundary |
|---|---|---|
| Merged learner acquisition at `4be0de6` | 81 passed | Admission, replay, caps, route identity, response/source attribution and unknown response with real PostgreSQL; model transport doubled |
| Historical exposure and budget units | 53 passed | Offline audit against committed evidence and current ledger; no historical store changes |
| Portable Linux runtime baseline | 96 passed, 16 skipped | Platform/database skips remain explicit; not deployment or full-suite qualification |

Final integrated acceptance on `cae712b`: **281 passed, zero failures and skips,
in 534.47 seconds**. This covers the 28 named affected files below, not the whole
repository suite. Only documentation and this raw diagnostic export changed
after the tested source tip. The 90-second faulthandler printed a PostgreSQL
commit wait during the controlled HTTP pilot; it was diagnostic output, not a
test failure. The prior complete
run on `7327a14` gave 278 passed and three failures, all in a control test helper
omitting the required view contract version. The fix uses the canonical view
builder, with assertions and runtime guards preserved. A separate earlier run
was interrupted by the coordinator after 148 passes; it is not acceptance.

Exact affected-gate command, run in WSL Ubuntu from the repository root after
creating the owned `s09c_checkpoint` database:

```sh
S09ISO_DISABLE=1 \
SETTLEMENT_TEST_DSN="dbname=s09c_checkpoint user=root host=/var/run/postgresql" \
SETTLEMENT_TEST_TRUNCATE_DSN="dbname=s09c_checkpoint user=root host=/var/run/postgresql" \
S09ISO_ADMIN_DSN="dbname=postgres user=root host=/var/run/postgresql" \
EC02_AD01C_DSN="dbname=s09c_checkpoint user=root host=/var/run/postgresql" \
INV_F2_DSN="dbname=s09c_checkpoint user=root host=/var/run/postgresql" \
PYTHONPATH="$PWD:$PWD/src" PYTHONUNBUFFERED=1 \
/tmp/asv2-closure-env/bin/python -u -m pytest -q -p no:cacheprovider \
  -o faulthandler_timeout=90 \
  tests/test_s09_learner_revision_accounting.py \
  tests/test_s09_learner_revision.py \
  tests/test_s09_e4_qualification.py \
  tests/test_s09rev_acquisition.py \
  tests/test_s09rev_boundary.py \
  tests/test_evidence_ceiling_diagnostic.py \
  tests/test_s09c_policy_boundary.py \
  tests/test_s89a3_closeout.py \
  tests/test_s09_run_use_policy.py \
  tests/test_inv01_control_arm_in_study.py \
  tests/test_inv_r1_use_policy.py \
  tests/test_s09m6fix_bind.py \
  tests/test_s09c3_policy_pilot.py \
  tests/test_s09m1_driver.py \
  tests/test_s09m34_cycle.py \
  tests/test_s09m2_policy.py \
  tests/test_s09m34_bind.py \
  tests/test_s09m34_visibility.py \
  tests/test_aleb_construct.py \
  tests/test_ad01_live_acquired_ddmin.py \
  tests/test_s09m5_pilot.py \
  tests/test_s09_exposure_ledger.py \
  tests/test_s09cs01_budget_denominations.py \
  tests/test_s09_older_reconciliation.py \
  tests/test_s09_reservation_operation_fk.py \
  tests/test_invl02_accounting.py \
  tests/test_s09_policy_governance.py \
  tests/test_inv_f2_loop.py
```

The fresh [evidence diagnostic](evidence/project-inventory-2026-09-30/evidence-headroom.json)
contains 150 unique truth tables, disjoint from the old E4 cohort. The coordinator
independently recomputed the mean difference from raw rows: informed versus
blind eight-query procedures gain 0.1875 in overall accuracy. Both are authored
controls; this establishes observation-sensitive headroom, not acquired learning,
transfer, learner improvement or statistical significance. Its three tests
include direct truth-table scoring independent of the instrument's scorer.

Reproduce this diagnostic from the repository root with the project environment:

```sh
PYTHONPATH="$PWD:$PWD/src" python -m experiments.ad01.evidence_ceiling_diagnostic
```

Full-suite, provider, deployment and containment qualification were not attempted
as this checkpoint's acceptance condition. Earlier runs below retain their
original scope and are not current-tip results.

## REVIEW-01 fix cycle (tested code revision `c827942`; report commit `4884d24`)

Full-suite command (real PostgreSQL 16, real subprocesses, fake/simulated models only):

```
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_integration?host=/var/run/postgresql" \
  uv run pytest tests/ -q --ignore=tests/test_broker_dbos.py --ignore=tests/test_s0_gateway.py
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_t1broker?host=/var/run/postgresql" \
  uv run pytest tests/test_broker_dbos.py tests/test_s0_gateway.py -q
```

Result: **329 passed + 19 passed = 348 passed, 0 failed** (~6.5 minutes for the
main body). The DBOS/gateway files require the DSN database name to contain
`settlement_t1broker` (pre-existing environment constraint, unchanged).
Per-finding regression evidence lives in `reports/workstreams/R1a.md`,
`R1b.md`, `R1c1.md`, `R1c2.md`, `R2.md`, `R3.md`, `R4a.md`, `R4b.md`,
`R4c.md`, `R5.md` (each: red-first where applicable, real-PG counts,
commit SHAs). The four REVIEW-01 defect probes now fail as designed —
they assert the fixed bugs — and are preserved uncollected at
`reviews/probes/historical_test_review_01.py` (verified 4 failed;
superseding tests named in its header).

Ruff (configured in `pyproject.toml`, no CI gate): 140 errors at review base
`381346a`; new fix code added no new violation classes (same RUF100/SIM117/
PLW1510 drift). Dead `noqa` directives introduced by fix code were removed
(`2efcb1f`).

## REVIEW-02 fix cycle (tested revision `72cfa11`)

Worker-reported full suite **418 passed, 0 failed** (record reconstructed
from the R02 lane reports; the R02 per-file evidence was not re-run here).

## REVIEW-03 fix cycle (tested code revision `42caa1e`)

Full-suite command (real PostgreSQL 16.15, real subprocesses, shim docker
runtime for launcher paths, fake/simulated models only; DBOS/gateway files
need the DSN name `settlement_t1broker`):

```
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_t1broker?host=/var/run/postgresql" \
PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests \
  python -m pytest tests/ reviews/probes/ -q
```

Result: **456 passed, 0 failed** (~13.5 minutes). Python 3.12.3 (venv),
psycopg 3.3.5, Linux, no Docker/runsc daemon. Lane-area evidence:
W-DATA on `settlement_r03data`, W-EVAL on `settlement_r03eval`, W-FLOW on
`settlement_r03flow` (see `reports/workstreams/r03-{data,sup,eval,flow}.md`);
W-SUP shared the integration DB. All 12 review probes are migrated to
fixed contracts (11 in `reviews/probes/test_review_03.py`, whose header
logs the correspondence) except R03-011/R03-012, retired with named
real-DB replacements (`test_fulfill_artifact_claim_requires_root_and_bytes`,
`test_overcharge_preserves_receipt_and_holds_liability`).

Real vs doubled, by finding: R03-001 real launcher + scripted interleave,
shim-runtime end-to-end; R03-002 real orchestration + shim runtime, module
Popen doubles only where the fixed stop sequence needs the docker CLI;
R03-003 real staging + shim/local execution; R03-004 real validators,
unrelated-process double; R03-005 real subprocess for the baseline
contract, source trace for the discarded-result finding; R03-006
source/spec pass + real-DB freeze/bind/release tests; R03-007 real DB +
scripted DBOS-shaped executor progress (no live executor); R03-008
scheduler-subprocess restart + delayed receipt (DBOS launch deferred if
unavailable); R03-009 real broker/database release path; R03-010 real
loopback socket + real psycopg connect code (no PG server); R03-011/012
real-DB fulfillment/admission.

Still unverified: live DBOS-executor backup interleaving, real runsc
containment (writable output/scratch limits), live inference and paid
billing, PostgreSQL 18, empirical learning comparison (inconclusive
accepted by design).

## S0–S3 baseline (tested revision `c3906a0`)

Full-suite command (real PostgreSQL 16, real subprocesses, fake/simulated models only):

```
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_t1broker?host=/var/run/postgresql" \
  uv run pytest -q
```

Result: **244 passed, 0 failed, 0 skipped** in ~4 minutes (the DBOS tests require
the DSN database name to contain `settlement_t1broker`; they create and use
`settlement_t1broker_dbos`, dropped and recreated per run).

## Static / unit (no external services)

| Requirement | Check | Real / fake | Result |
|---|---|---|---|
| S0 manifest shape | `tests/test_s0_manifest.py` | real (reads `uv.lock`, live PG version query, `runsc` probe) | pass |
| Gateway adapter units | `tests/test_s0_gateway.py` (in-process stub HTTP server) | fake transport | pass |
| Composition goldens | `tests/test_run_compose.py` | fake | pass |
| Trial verdict math | `tests/test_s3_*` pure-math cases | fake | pass |

## Real PostgreSQL 16 (deployment target PG18 stays unverified, D-001)

| Requirement | Check | Real / fake | Result |
|---|---|---|---|
| TX-1..6, §15 races | `tests/test_tx_*.py`, `tests/test_state_*.py`, `tests/test_settle_actual.py` | real PG, threads + Hypothesis | pass |
| Epoch-atomic invalidation | `tests/test_evidence_epoch.py` | real PG | pass |
| Release re-verification | `tests/test_learning_review.py` | real PG | pass |
| Adversarial budget/journal | `tests/test_adv_budget.py`, `tests/test_adv_broker.py` | real PG + Hypothesis | pass |
| Concurrent dispatch ×8 | `tests/test_broker_review.py` (caught T3-R07/R08 pre-merge) | real PG + threads | pass |

## Real sandbox (local-process profile, explicitly NOT containment)

| Requirement | Check | Real / fake | Result |
|---|---|---|---|
| EFF-7 spawn/kill/framing | `tests/test_launchers.py`, `tests/test_broker_dispatch.py` | real subprocesses | pass |
| Broker death at every boundary | `tests/test_broker_dispatch.py`, T7 `test_adv_broker.py` | real PG + real subprocesses | pass |
| Worker isolation probe | `tests/test_adv_isolation.py` (env reachability, quotas, unknown effects) | real subprocesses | pass |
| gVisor containment | `tests/test_r01_runsc.py` (probe gating, argv/resource/deadline plumbing, recovery) | no `runsc`/Docker on this host | IMPLEMENTED but UNVERIFIED live (refusal path tested; actual containment needs a runsc host, R01-005) |

## Live gateway (UNVERIFIED — no endpoint, key, or grant)

| Requirement | Check | Real / fake | Result |
|---|---|---|---|
| §14 S0 live row (discovery/auth/inference vs real endpoint) | — | no endpoint | UNVERIFIED |
| §11 live A/B/C | `tests/test_r01_experiment.py` (deterministic doubles end-to-end, broker-routed costs, grant refusal, exit 2) | no endpoint/key/grant | IMPLEMENTED but UNVERIFIED live (R01-011/012; same path runs live when inputs exist) |

## Recovery (REC-1..4)

| Requirement | Check | Real / fake | Result |
|---|---|---|---|
| Checkpoint set | `tests/test_rec_checkpoint.py` (`scripts/checkpoint.py`) | real PG + real filesystem | pass |
| Restore into fenced DB | `tests/test_rec_restore.py` (`scripts/restore.py` into `settlement_restore_probe`) | real PG | pass |
| Restored-DB-predates-effect | T7 adversarial restore test | real PG | pass |
| Scheduler converge loop | `tests/test_agenda_repair.py`, `tests/test_reconcile_reset.py` | real PG + real subprocesses | pass |

## Learning (simulated arms only)

| Requirement | Check | Real / fake | Result |
|---|---|---|---|
| §11 A/B/C mechanics | simulated harness (T5 run + T7 reproducibility re-run), every cell `simulated=True`, finite-panel verdicts | scripted model doubles | pass (mechanics only; no learning claim) |
| Evaluator-swap detection | S3 + adversarial evaluator tests | fake | pass |
| Hidden-answer boundary | candidate-scope retrieval tests | real PG | pass |

## Known flakes (under load, unreproduced in isolation)

- Process-group kill timing (`test_launchers.py` timeout case): 2 sightings total
  across the program under parallel load; passes alone and in full-suite reruns.
- 3rd sighting: `test_timeout_kills_whole_process_group` failed once in the
  DEVELOPMENT-02-LIVE full suite (`8221d35`, 1 failed / 516 passed in
  743.72s); green in isolation (1.42s) and file-level (8 passed) on the
  same revision and DB. `pgrep -f "sleep 30"` raced the kill grace window
  under full-suite load. File untouched by both D2A lanes. No open defect.
- T6 reported one full-suite-only failure it could not reproduce; same signature
  family (timing under load), no open defect.
- `test_stop_uses_kill_fallback_and_clears_tracking`: failed once in the
  Development-01 full-suite run; 4/4 passes in isolation. Timing-sensitive
  kill fallback under parallel load; no open defect.

## Development-01 episode (tested code revision `5a2ed91`)

Full-suite command (real PostgreSQL 16.15, real subprocesses, shim docker
runtime for launcher paths, fake/simulated models only):

```
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_t1broker?host=/var/run/postgresql" \
PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests \
  .venv/bin/python -m pytest tests/ reviews/probes/ -q
```

Result: **484 passed, 0 failed** (no `lastfailed`; warnings summary printed
at end of session, so the run completed). The 2 failures seen on `f3318f8`
are both resolved: the kill-fallback load flake (green in this run) and the
stale 0007 manifest pin (fixed in `5a2ed91`). Targeted greens on the final
tree: `test_dev01_episode.py` 12 passed, `test_dev01_ops.py` +
`test_s3_evaluation.py` 13 passed. Deterministic entry proven end-to-end on
scratch DBs: fresh `devep-run-01` and repeat `devep-int-05` on a used DB;
bound episode ids refuse re-run.

Wall-time anatomy (~11 min serial): single process, no xdist (the shared
truncate fixture assumes one DB); real PostgreSQL round-trips per test with
per-test migration re-runs in the newer files; real subprocesses and real
sleeps on timeout/kill paths. Sampled: `tests/test_r02_exec.py`, 16 passed
in 6.71s, slowest `test_supervisor_terminates_container_after_broker_death`
4.78s (real process supervision). Follow-up: shard the suite across
disposable DBs so truncate fixtures parallelize.

## Development-02 episode (tested code revision `56f7bba`)

Same full-suite command and environment as Development-01.

Result: **509 passed, 0 failed** in 686.79s (explicit terminal summary).
First run on `8648d8e` was 508 passed, 1 failed: the new operator packet
region pushed `test_overview_uses_bounded_projection` from 6 to 7 DB
connections. Fixed in `56f7bba` by folding the table check into the single
packet query (`recent_packets` returns `[]` on a missing table); the exact
red test plus packet/UI neighbors re-run green (33 passed), then the full
suite re-ran green end to end. Targeted greens on the final tree:
`test_dev02_episode.py` 13 passed, `test_dev02_context.py` 12 passed,
`test_dev01_episode.py` 12 passed, `test_dev01_ops.py` 9 passed (incl. the
full fixture CLI end to end asserting the fresh-process use phase from
receipts). The four characterization probes
(`test_development_01_readiness.py`) were retired to
`reviews/probes/historical_test_development_01_readiness.py` with
per-probe correspondence after the repaired contracts made three of them
fail (stale harnesses) and the fourth's property moved into the maintained
suite.

Still unverified: live finite-panel comparison with held-out groups, live
model conditioning, real runsc containment, PostgreSQL 18.
disposable DBs so truncate fixtures parallelize.

Still unverified: live model run (no endpoint/key/grant in this
environment), empirical learning comparison, real runsc containment,
PostgreSQL 18.

## DEVELOPMENT-02-LIVE integration (tested code revision `8221d35`)

Merges L-EP (`5867da6`: D2A-001 file-ABI constructor + envelope policy,
D2A-002 collect-claim linkage, D2A-003 disposition-gated use, cost
union) and L-CTX (`556467f`: D2A-004 inference-only binding +
input digest, D2A-005 nothing-stripped budget staging) at `3cb7346`,
plus `8221d35` migrating 4 stale limitation-probes to fixed-behavior
gates. Lane detail in `reports/workstreams/d02live-ep.md`,
`d02live-ctx.md`; merge record in `reports/workstreams/
d02live-integration.md` (count reconciliation, overlap hunk, probe
correspondence).

Full-suite command (real PostgreSQL 16, real subprocesses,
fake/simulated models only; URL-form DSN):

```
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_t1d02live?host=/var/run/postgresql" \
  uv run pytest tests/ -q -p no:cacheprovider
```

Result: **1 failed, 516 passed in 743.72s** (517 collected = 512 L-EP
+ 5 L-CTX; per-file test counts prove zero add/remove/rename in
pre-existing files, +25 new-file defs). Acceptance probes separately:
**6 passed** (mock-only). The single failure is the known
process-group-kill load flake (3rd sighting above; green in isolation
and file-level on the same revision). `ruff` not installed in the
venv — could not run (no CI gate).

Still unverified: live finite-panel comparison, provider smoke, real
runsc containment, PG18, held-out transfer use. No live inference
claimed anywhere; recorded live-pilot bytes are fixed test vectors.

## ENGINEERING-REVIEW audit (tested code revision `46427f4` + template fix; this section committed on top without code changes)

Full-suite command (real PostgreSQL 16, real subprocesses,
fake/simulated models only; host-param URL DSN — keyword `dbname=` DSN
breaks the pre-existing `_swap_db` urlunsplit fixture and SQLAlchemy
sibling-DB paths in `test_broker_dbos.py`, `test_r02_authority.py`,
`test_r03_flow.py`, `test_r01_recovery.py`; environmental, identical on
base, not code):

```
SETTLEMENT_TEST_DSN="postgresql://localhost/settlement_fullsuite?host=/var/run/postgresql" \
  .venv/bin/python -m pytest tests/ -q -p no:cacheprovider -rfE --tb=short
```

Result: **579 passed, 0 failed, 0 errors in 820.86s** (13:40). An
earlier run under keyword DSN showed 2 failed + 8 errors, every one
reproduced as DSN-form environmental and green in isolation under the
correct DSN; no code fix needed. Per-lane gates rerun post-merge by the
coordinator on scratch DBs (dropped after): PROV 33, INV-A 77+17,
INV-C 85, INV-B 24+145+3, UI wire-up 7 (new test red-checked).

Still unverified: live finite-panel comparison, provider smoke
(zero releases; selected-method transfer unexercised), real runsc
containment (shim only), PG18. Responses-path billing semantics
deliberately unchanged (ENG-INVB-10: no live billing oracle to validate
against). No live inference claimed; recorded live-pilot bytes are fixed
test vectors.

## Final integrated suite (closure source, after CLOSE-1/2 + coordinator fixes)

Same command and DSN form as above, solo run on a quiet host, log saved.
Result: **590 passed, 0 failed, 0 errors in 838.45s** (13:58). The 11
tests over the earlier 579 are the CLOSE-1 regressions, the cancel-forward
regression and the read-timeout mechanism test. No reruns; no flakes.

## Closure live baseline smoke (recorded run on repaired tree `35c3fef`, clean)

One bounded run, panel-triangular, local-process uncontained profile,
finite grant, responses API via local gateway. Outcome: success —
solver ok, grade 3/3 passed, 2 unique operations, reserved == settled per
operation (model 8344, grade 111), allocation consumed 0 → 8455,
settled sum == ledger sum == 8455, reconciled. Bundle:
`reports/evidence/eng-close2/` (smoke_close2.json, reconciliation.json,
PROVENANCE.md, NOTE-historical-smoke.md, run_smoke.py,
check_reconcile.py). Historical `eng-solv/smoke_result.json` preserved
untouched; its 8344/111/111/8455 lane-state reading is annotated, not
recomputed. No live inference beyond this run; no campaign; protected
tasks untouched. This smoke does not establish acquired-method benefit,
held-out transfer, or provider monetary charges.

## Agenda 01 (branch `codex/implementation-agenda-01`)

Full suite **653 passed, 0 failed** on real PostgreSQL 16
(`SETTLEMENT_TEST_DSN="postgresql://ubuntu@/agenda01_exp?host=/var/run/postgresql" .venv/bin/python -m pytest tests/ -q`;
agenda slice 63: state 14, policy 27, experiment 18, demo 4). Frozen
experiment: manifest `a52f3ed7`, 128/128 trajectories complete, checker
`ok=True`, 0 violations; verdict and pair table in `reports/AGENDA-01.md`,
traces in `experiments/agenda01/results/`. Post-freeze touchdown: one
freeze-test cleanup fix, re-verified standalone (experiment file 18/18) with
the frozen manifest byte-intact.

## Investigation Learning 02 final handback

Source tip: `f73127fa02a50ba456be92e0f68a5d9aaf1f26d6`. Date: 2026-09-24. This section records the current report handback. It does not change source or evidence.

### Full-suite runs stall in the coord02 family, and that predates this work

A full `pytest` run at this tip does not reach a summary. It stalls in `psycopg.connect` and
the per-test timeout fires. The visible symptom is a stall in `ep_poll` on a loopback socket
with no CPU and no output, which reads as a hang.

The mechanism was measured directly rather than inferred. At the moment of a stall the
server shows a client backend for the test's database in state **`idle in transaction`**
whose last statement was `COMMIT`: a connection opened a transaction, sent `COMMIT`, and
never closed. That leaked transaction holds locks, so the test's next `psycopg.connect`
blocks. The backend disappears when the process dies, which is why it is invisible to any
check run afterwards, and each stalled run leaves another behind to poison the next.

Two pre-existing conditions allow it. `_fresh_db()` at `tests/test_acct_store_costs.py:46`
truncates every table in a *shared* database, so any concurrent connection blocks it. And
`db.connect` at `src/settlement/db.py:17` sets neither `connect_timeout` nor
`lock_timeout`, so a blocked call waits indefinitely instead of failing.

This is not a regression from the INVL02 work. `tests/test_acct_store_costs.py`,
`tests/test_bdr02_child_identity.py`, `src/settlement/broker.py`, `src/settlement/db.py`
and all of `experiments/coord02/` are byte-identical between `2d12d56` and `5148bb0`.
Running `tests/test_acct_store_costs.py::test_trial_costs_equal_measured_receipt_usage` at
`2d12d56` reproduces the same stall. 114 of the 220 test files touch this family; the
remaining 106 contain no reference to `coord02`, `LocalLauncher` or a real database.

That 106-file subset was run at this tip: **962 passed, 267 skipped, 8 failed** in 57s. The
8 failures are in `tests/test_r01_deadline_ui.py` (4, all deadline/cancel timing) and
`tests/test_s09o_prelive.py` (4, all study-guard cost refusals, e.g.
`test_guard_raises_for_nonzero_usage_cost` reporting `DID NOT RAISE StudyGuardRefusal`).
Both files were left untouched by this work, and both produce **the identical 8 failed,
4 passed, 6 skipped** at `2d12d56`, so the changes to `src/settlement/gateway.py` and
`src/settlement/gateway_http.py` introduced no failure here. They are pre-existing.

With the leaked backends cleared, the underlying stall failure surfaces immediately and is
an ordinary assertion, not a stall: `settlement.common.SettlementError: join undecided: check
plan_...:r1:check has no observed receipt`. That defect is real, predates this work, and is
untouched here. The seven live-study gate files have no reference to the affected family
and pass in about nine seconds.

### Final affected gate

The recorded worker aggregate of **616 passed, 32 skipped** is not reproducible from the cited affected list. The corrected affected result is **135 passed, 16 skipped** with the DSN variables unset. The exact live-study gate separately passed **233** tests. The recorded environment had `SETTLEMENT_TEST_DSN` and `INV_B1_DSN` unset. The exact affected test list from the final repair wave was:

```text
tests/test_ag01_demo.py
tests/test_ag01_experiment.py
tests/test_broker_dbos.py
tests/test_final_provenance.py
tests/test_frontier_atomicity.py
tests/test_inv_b1_contracts.py
tests/test_m2_frontier_inherit.py
tests/test_provenance_authority.py
```

The 32 skips belong to the stale worker aggregate and are not a database-qualified result. Current test database safety requires explicit `SETTLEMENT_TEST_DSN`, a matching `SETTLEMENT_TEST_TRUNCATE_DSN` for destructive fixtures, and explicit `INV_B1_DSN` for the INV-B1 contract gate.

The final frontier evidence worktree gate for the selected frontier gate passed **430** tests with **0 skipped**. This is separate from the corrected **135 passed, 16 skipped** affected result and the **233 passed** live-study gate at `f73127f`. A separate 15-minute full-suite attempt at `f73127f` used disposable DSNs and timed out before pytest printed a summary. It is not a pass, a failure, or a green full-suite result.

### Live and evidence boundary

Fresh route discovery at `f73127f` accepted the 550B route. Evidence: `reports/evidence/invl02-route-discovery-550b-r3/route-discovery.json`, SHA-256 `b41189edd87a28b782cdd723f61f716b0b526f22cbc862e49243bf2897e0904a`.

Fresh output freeze is `reports/evidence/invl02-output-shape-550b-r3/freeze.json` with SHA-256 `5ebc5cfad4a10b8ab912bed36c33c140c6416b4613ac57dfe78f57217a2ef4e1`. Fresh preflight is `reports/evidence/invl02-output-shape-550b-r3/preflight.json` with SHA-256 `0ed8adde9160e909384487ab8b1b2f215509744bac774037cf27b9de0f9a4fc1`.

The earlier pre-live attempt at `f73127f` was refused before dispatch because a fresh human grant was required, and no model inference occurred in that attempt. The 2026-09-24 run then bound the standing authorization to the frozen r3 study, dispatched once, and stopped on the first-route-mismatch rule. The live study is closed unavailable at the route boundary. Historical E0 limitations remain unchanged and retention-only. Historical E12 limitations remain unchanged and incomplete. E3 remains unavailable and unrun. No utility, transfer, or recursive-improvement claim is supported.

The systematic-repair workflow artifact is `/home/ubuntu/.agents/skills/parallel-bugfix/SKILL.md`. It is a workflow record, not a product capability.
