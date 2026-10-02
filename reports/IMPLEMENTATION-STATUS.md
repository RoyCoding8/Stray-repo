# Implementation status (S0-S3)

Base commit: `be7956d`. Integration branch: `codex/implementation-s0-s3`.

## Slices

- S0 (environment, gateway, profiles, boot): implemented, merged (T1 + review).
- S1 (durable state, broker/execution, operator/agenda): implemented, merged
  (T2, T3, T6 + review). Trial/release views wired to T5 tables.
- S2 (artifacts, evidence, continuity): implemented, merged (T4 + review).
- S3 (capabilities, trials, evaluation, A/B/C harness): implemented, merged
  (T5 + integration). Arms run simulated; live run blocked (see §11 below).
- Validation/recovery (REC, adversarial map): implemented, merged (T7 + R1c2).
- REVIEW-01 fix cycle: all 17 findings addressed and merged (R1a/R1b/R1c1/R1c2
  admission-recovery, R2 runsc launcher, R3 evidence, R4a/R4b/R4c
  evaluator-release-experiment, R5 deadlines-UI). Full suite 348 passed;
  `reports/VERIFICATION.md` (fix-cycle section), `reports/DECISIONS.md`
  (D-003..D-009), per-finding evidence in `reports/workstreams/R*.md`.
- REVIEW-02 fix cycle: all findings addressed and merged (`72cfa11`).
  Full suite 418 passed.
- REVIEW-03 fix cycle: all 12 specification findings confirmed and fixed,
  merged as W-DATA (`9134c7b`: store deadlines, artifact byte reverification,
  overcharge receipt/liability), W-SUP (`4de32e7`: final pre-send generation
  fence, fail-closed supervision, verified-stop retention, declared stop/settle
  exposure), W-EVAL (`27afd88`: launcher staging interface, digest-bound
  evaluation, honest A/B/C with no-op ablation, version-bound selection and
  gated release/reuse), W-FLOW (`56aeaa2`: quiesced backup with pause
  ownership, durable workflow wakeup, bounded retry accounting); integration
  fixes in `42caa1e`. Full-suite count in `reports/VERIFICATION.md` (R03
  section); per-finding evidence in `reports/workstreams/r03-{data,sup,eval,flow}.md`;
  probe correspondence in `reviews/probes/test_review_03.py` header. Remaining
  open gates: live DBOS-executor backup interleaving, real runsc containment
  (writable output/scratch limits), live inference billing, PG18.
- DEVELOPMENT-01 episode: durable lifecycle (`development.py`, migration
  `0007`), broker-routed constructor, apply-then-grade check, frozen
  splits, honest A/B/C, release/reject paths, operator view, one entry
  point driving the lifecycle with the bound candidate injected into the
  comparison (C invokes the exact bound bytes). Deterministic slice
  proven end-to-end (fresh and repeat DB runs); live run blocked on model
  access. Evidence in `reports/DEVELOPMENT-01.md`; decisions D-018..D-020.
  Full-suite count in `reports/VERIFICATION.md` (Development-01 section).

## Entry points

- Package: `src/settlement/` — `common` (envelope), `gateway` (adapter ABC),
  `gateway_http` (HTTP adapter), `exec_profile` (profiles), `boot` (startup
  validation), `db` + `config`, `store` (durable transitions), `broker`
  (dispatch), `launcher_local` / `launcher_runsc`, `run` (compositions),
  `artifacts`, `evidence`, `context`, `capabilities`, `trials`, `evaluation`,
  `experiment`, `steward`, `agenda`, `api` (operator UI).
- Setup: `uv sync --extra test`; per-task databases
  `postgresql://ubuntu@/settlement_<task>?host=/var/run/postgresql`.
- Run/test: `SETTLEMENT_TEST_DSN=<dsn> uv run pytest` (full suite; the DBOS
  tests require the DSN database name to contain `settlement_t1broker`).
- UI: `SETTLEMENT_DSN=... OPERATOR_TOKEN=... uv run uvicorn settlement.api:app
  --host 127.0.0.1 --port 8101` (binds loopback only; prints a one-process
  token when OPERATOR_TOKEN is unset).
- Manifest: `uv run python scripts/manifest.py`.
- Live A/B/C (blocked): `uv run python experiments/run_live_abc.py --dsn
  $SETTLEMENT_DSN --allocation live-abc --artifacts-root $ARTIFACT_ROOT`
  with `SETTLEMENT_GATEWAY_ENDPOINT`, `SETTLEMENT_GATEWAY_KEY`,
  `SETTLEMENT_GRANT_UNITS` set.

## Environment limitations

- PostgreSQL 16 locally (deployment target PG18, see D-001).
- No Docker/`runsc` on this host: gVisor profile reports incompatible (D-002).
- No live inference endpoint: gateway checks pass discovery/auth/inference
  separation only with fake/stub adapters; live gate unverified.
