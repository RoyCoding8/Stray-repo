# Verification

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

Still unverified: live model run (no endpoint/key/grant in this
environment), empirical learning comparison, real runsc containment,
PostgreSQL 18.
