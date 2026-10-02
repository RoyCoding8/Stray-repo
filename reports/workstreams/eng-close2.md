# ENG-CLOSE2: bounded live baseline smoke lane

Branch: `codex/eng-close2`, worktree `/tmp/asv2-close2`, base `b9d27be`.
Lane: WORKER-ENGINEERING-CLOSURE.md §2 (closure prompt `/tmp/closure.md` §2).
Historical inputs read but never modified: `reports/workstreams/eng-solv.md`,
`reports/evidence/eng-solv/smoke_result.json` (+ `run_smoke.py` as template).

## A. Preflight (no live inference cost; observed 2026-09-11)

- Endpoint `http://localhost:6446`: REACHABLE (`GET /v1/models` → HTTP 200,
  8 models listed, both with and without key).
- Key: `$META_API_KEY` is set (43 chars; value never printed, never committed).
- Prior-smoke authorized model: still served in the `/v1/models` list
  (factual id recorded inside evidence artifacts only, not in commit messages).
- Gateway adapter (`src/settlement/gateway_http.py`): constructs with
  `HttpGatewayAdapter(endpoint, api_key, api="responses")`;
  `check_discovery` = `GET {endpoint}/models`, `check_auth` requires key.
  (Merged tree carries no `APIS` class attr; the run used `api="responses"`.)
- Finite-grant seeding path: `store.seed_grant` / `store.seed_allocation`
  present; runner asserts APPLIED/ALREADY_APPLIED before proceeding.
- Local-process execution profile: `LocalLauncher` present
  (`launcher_id local-1`); uncontained local runs are explicitly labeled
  (same LS-01 shape as the historical smoke). No shim containment claimed.
- Smoke databases: no stale `settlement_close2*` / `settlement_engsolv` DBs
  present (`psql -lqt` clean). PostgreSQL 16 online.
- Preflight verdict: GATEWAY/GRANT/PROFILE AVAILABLE. Zero inference calls
  spent (model enumeration only).

## B. Repairs gate: OPEN (repaired tree merged by coordinator)

- `git log --oneline -3` → `35c3fef` merge on top of `2764ebc`: repaired
  coordinator tree present (INVA-03/04/05/06/08, INVB-11/13, check_use,
  doubles fixes + reconciled matrix). This lane merged nothing itself.
- Runner API re-probe on the merged tree (project venv, zero live cost):
  `panel-triangular` present; `experiment._arm_prompt`,
  `run_subsequent_use`, `_op_accounting`, `SOLVER_SOURCE_CONTRACT`,
  `model_token_budget` present; `store.seed_grant/seed_allocation/
  admit_commitment/allocation_status` present; `LocalLauncher.profile`
  = `local-process`; `db.apply_migrations(dsn, migrations_dir)` unchanged.
- Tree clean at run (`git status --short` empty; `.venv/` gitignored);
  no stale `settlement_close2*` DBs; `SETTLEMENT_MODEL_TOKENS=8192`
  (same cap as the historical smoke).

## C. Recorded smoke: RUN once on 35c3fef (2026-09-11) — success

- Command: `SETTLEMENT_MODEL=<authorized-id> SETTLEMENT_MODEL_TOKENS=8192
  .venv/bin/python reports/evidence/eng-close2/run_smoke.py` (key from
  `$META_API_KEY` at runtime only). Single attempt, zero retries, no tuning,
  visible-regression `panel-triangular` only, finite grant 2,000,000 units,
  local-process uncontained profile (explicit LS-01 label).
- Path exercised: inference → validation → source staging → grading →
  settlement/reporting via `run_subsequent_use` with the live Responses-API
  adapter. Gateway `REACHABLE` / `AUTHENTICATED` at run.
- Outcome: `solver_status=ok` (parseable Python), `grade_class=pass`
  (3/3 cases), `outcome=success`. Model usage 172 in / 605 out tokens,
  `billed=false, charge 0`: conservative settlement, no billing claim.
- Accepted source `==` model receipt text (verbatim-source contract holds);
  staged-source sha256
  `d777e666f69ad5ea3c257ebb8e1c3606ddfe2192bea97001415e11f44c35c962`
  (bytes preserved verbatim in `smoke_close2.json`).
- Accounting over 2 unique operations: model op reserved/settled 8344/8344,
  grade op reserved/settled 111/111, both `unresolved=0`, reservation rows
  `settled`; allocation consumed 0 → 8455 (delta 8455 = settled sum 8455 =
  expenditure ledger sum 8455). `reconciled=true`.
- Bundle `reports/evidence/eng-close2/`: `smoke_close2.json`,
  `reconciliation.json`, `PROVENANCE.md` (new) + `run_smoke.py`,
  `check_reconcile.py`, `NOTE-historical-smoke.md` (phase-A).
  Secrets check: key value and `Bearer` absent from all 4 files
  (boolean probe only; env-var names only in bundle). Raw transport
  distinguished from logical output text by explicit note.
- `settlement_close2` dropped by the runner after bundle verification;
  post-run `psql -lqt` shows no `settlement_close2*` DBs (other lanes'
  DBs untouched). Historical `reports/evidence/eng-solv/smoke_result.json`
  and `reports/workstreams/eng-solv.md` untouched (status shows only the
  3 new bundle files).

## D. Prepared bundle assembler + checker (verified without live cost)

- `reports/evidence/eng-close2/run_smoke.py`: refuses on missing key,
  missing `SETTLEMENT_MODEL`, unserved model, or dirty tree; writes
  `smoke_close2.json` (config, prompt, receipts, staged-source identity,
  grade, per-op accounting, reservation rows, expenditure ledger rows,
  allocation before/after), `reconciliation.json` (unique-operation
  reread + historical 8344/111/111/8455 annotation), `PROVENANCE.md`;
  verifies bundle files parse, then drops `settlement_close2`.
  No secrets in bundle (env-var names only); raw transport distinguished
  from logical output text by explicit note.
- `reports/evidence/eng-close2/check_reconcile.py`: stdlib-only verifier
  (uniqueness, settled+unresolved==reserved, consumed delta==settled sum).
- `reports/evidence/eng-close2/NOTE-historical-smoke.md`: phase-E
  annotation (earlier-lane-state status, base+dirty provenance,
  discrepancy arithmetic, integrated reread expectation).
- Observed checks: `py_compile` on both scripts OK; checker probe on
  synthetic consistent bundle → exit 0 reconciled=true; on synthetic
  historical-shape bundle (8344/0/0 + 111/111, delta 8455) → exit 1
  reconciled=false with the exact flag pattern; runner guard probe on
  the current dirty tree → refused before any network use, exit 1,
  zero live spend.

## E. Spend accounting

Live inference calls this lane: 1 (one recorded smoke; transport-flake
retries: 0). No campaign, no tuning on protected tasks.

## F. Reconciliation: historical 8344/111/111/8455 under integrated accounting

- Historical lane state (annotated only; original preserved): model
  reservation 8344, grade reservation/settlement 111, per-op settled sum
  111, consumed delta 8455. Old code debited the released model reservation
  to consumed without a settled charge (its per-op record read settled 0 /
  unresolved 0), so 8455 == 8344 + 111 while the per-op settled sum was 111.
- Integrated reread on `35c3fef` (this run): model op settles its full 8344
  reservation, grade op settles 111; consumed delta 8455 equals the settled
  sum over unique operations, and the independent stdlib checker
  (`check_reconcile.py`) exits 0 with `reconciled=true`, `parts_ok=true`,
  `delta_ok=true`, no duplicates.
- Lane close-out: bundle written BEFORE any deletion; lane DB dropped by
  the runner after bundle verification; no `settlement_close2*` DBs remain.
  Nothing else to delete. Lane done; no further live calls planned.
