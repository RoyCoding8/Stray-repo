# ENG-ACCT workstream report: EVID-02 unbilled-settlement reporting

Base: `f478143c520977da179cef3da309824a996a42cb`
Product commit: `d5eb1564b094c59b7a4e5af972b5e24a3ab210b8`
Branch: `codex/eng-acct` (worktree `/tmp/asv2-eng-acct`)

## Finding ledger

### ENG-ACCT-01: unbilled settled reservation vanishes from the report
- Trigger: settled 1000-unit reservation with broker-shaped unbilled receipt
  (`usage={charge_units: 0, billed: False}`, `actual_cost=None`).
- Expected: report reconciles with the durable debit (allocation `consumed=1000`).
- Actual (before fix): `_op_accounting` returned `settled=0, unresolved=0`.
- Root cause: `src/settlement/experiment.py:381` reported receipt
  `charge_units` whenever present, ignoring `billed=False` and the settled
  reservation debit. Settlement itself was correct (`store._settle_amount`
  consumes the full reservation when `actual_cost is None`; broker passes
  `None` for unbilled usage at `broker.py:458`).
- Callers affected: `_settle_costs` (ledger entries), `episode_cost_union`
  totals, `run_abcs` per-op/per-arm/budget accounting, `development` episode view.
- Fix: settled now reports the durable debit — the verified billed charge when
  `billed` is true and `0 <= charge_units <= reserved`, else the full reserved
  amount. New per-op fields `billed` (bool) and `provider_charge_units`
  (int | None): provider monetary billing displays as unknown unless decoded
  and verified. `tokens` unchanged and separate. No change to settlement,
  broker, store, gateway, union aggregation, or ledger recording logic.
- Verification: real-PG repro `/tmp/engacct-repro.py` went RED before
  (`settled=0/unresolved=0` vs `consumed=1000`) and GREEN after
  (`settled=1000`, `billed=False`, `provider_charge_units=None`);
  adversarial billed probe settles exactly (`settled=42=consumed`,
  `billed=True`); committed tests below.

## Modified paths
- `src/settlement/experiment.py` (`_op_accounting` only, lines 356-395)
- `tests/test_r02_exec.py` (appended 2 real-DB accounting tests + seed helpers)
- `reviews/probes/test_live_evidence_controls.py` (migrated doubled
  `test_unbilled_receipt_is_reported_as_zero_despite_settled_reservation` to
  `test_unbilled_receipt_reports_conservative_debit_with_unknown_billing`;
  added doubled `test_billed_receipt_reports_verified_charge_exactly`)

## Check outcomes (real PostgreSQL, worktree venv)
- `pytest tests/test_r02_exec.py tests/test_s0_gateway.py reviews/probes/test_live_evidence_controls.py`
  with `SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_engacct_verify?host=/var/run/postgresql`:
  **51 passed** (x3 consecutive clean runs).
- `pytest tests/test_settle_actual.py`: **7 passed** (store semantics untouched).
- `pytest tests/test_d02live_episode.py -k "cost_union or unsettled_exposure"`: **2 passed**.
- `pytest tests/test_dev01_compare.py::test_dev06_abc_affordances_and_accounting`: **1 passed**.
- `pytest tests/test_r01_experiment.py`: **1 failed / 3 passed** — expected
  contract fallout, see contract request below.

## Contract request (shared-contract change, not applied)
- `tests/test_r01_experiment.py::_db_settled` (line 64) mirrors the old buggy
  rule (returns receipt `charge_units` for unbilled scripted-double ops:
  `assert 545 == 170`). It needs migration to the EVID-02 contract
  (durable debit; scripted doubles are unbilled so report exposure, not the
  unverified charge). Owned by the R01/coordinator lane; this lane was
  forbidden from touching it.

## Limits
- `settlement_engacct` (assigned env DB) is concurrently truncated by another
  runner (`/tmp/asv2-engcoord` pytest with the same DSN), which caused
  intermittent mid-test row disappearance; gates above ran on exclusive
  `settlement_engacct_verify` (3/3 deterministic). Recommend one DB per runner.
- `test_stop_uses_kill_fallback_and_clears_tracking` is timing-flaky
  independent of this change (fails intermittently in isolation on base code
  paths this lane did not touch); all three gate runs above passed it.
- Ruff config exists but ruff is not installed in the worktree venv, so no
  lint gate was runnable. No live inference performed; no credentials recorded.
