# Representation 01 — live3 campaign report (R-LIVE)

Branch `codex/implementation-cognitive-batch-02`. Lane R-LIVE, independent of
Team 01. Design: `docs/design/REPRESENTATION-01-IMPLEMENTATION.md`; prior
report `reports/REPRESENTATION-01.md` (whose live campaign was never run —
this report closes that gap with a real gateway execution, not a recycled
no-gateway note).

## 1. Configuration (LIVE-01)

- Gateway: `HttpGatewayAdapter`, `api="responses"`,
  endpoint `http://localhost:6446/v1`, authenticated inference verified
  (discovery alone was not accepted).
- Model: `muse-spark-1.3-contributor-free`, `reasoning_effort="low"`
  (high-effort B/C slots exhausted the 8192-token output cap and timed out;
  low effort fixed this; effort is frozen into the retention record).
- Call bounds: 16384 input / 8192 output tokens per call, 300s deadline,
  0 retries. Budget: 12 model calls (per arm: 2 source + 2 transfer).
- Runner: `experiments/representation/acquire/experiment.py:run_experiment`
  (`--tag live3 --phases evaluation,disposition,use`), core logic reused,
  no provider hardening, no key committed.

## 2. Campaign (LIVE-02)

- Manifest: `experiments/representation/evidence-live3/campaign/live3.json`
  (protocol `rpr-acq-C`, tag `live3`).
- Spent: 12/12 model calls, 63498 input / 42950 output tokens,
  0 of 171948 grant units. Disposition: `complete`.
- Retention: `retention-live3.json` freezes A/B/C source+transfer selections
  with the effective model/API configuration, token limits, source SHA and
  grant profile. Invalid retained procedures are recorded as refusals with
  reasons (`run.py:bind_retention`), never raised past the binder — one live
  evaluation hard error caused this change, with a regression test.
- Held-out comparison: 48 arm-task records under
  `evidence-live3/eval-live3/arm_task/`; 12 controls pass 12/12; 4 use
  records (gr/sw supported + out-of-scope) prove selected bytes drove the
  evaluator and fresh-process use.

## 3. Outcome: null result, checker-clean

Independent checker
(`experiments/representation/experiment/checker.py --evidence-root
experiments/representation/evidence-live3/eval-live3`, re-run by the
coordinator on the merged tree): **clean true, 48 records, 0 problems,
promising false**.

Failing clauses (`disposition.json`): `valid-delivery` false,
`transfer-gain-0.10-vs-A/B` false, `resources-within-1.25x` false.
Held clauses: all 12 controls, `software-within-0.05-vs-B`.
`release_eligible` false. No candidate qualified, so no selected-use branch
beyond the supported-scope probes was exercised; nothing was swapped in to
manufacture a win.

## 4. Representation live disposition

LIVE-01 closed (real broker/gateway inference with usage). LIVE-02 closed
(acquisition -> frozen retention -> held-out comparison -> disposition ->
fresh-process use, full no-candidate accounting preserved). The scaffolded
acquisition space (closed-vocabulary A, ddmin/greedy B, retained C) produced
no held-out benefit on this pilot: learning benefit not demonstrated, reported
as-is per the batch rules.

## 5. Recomputation

- Replay: `experiments/representation/experiment/replay.py` over
  `evidence-live3/`; freeze check `experiment/freeze.py --check`.
- Raw evidence committed: campaign JSONs (live1/live2/live3 + retentions),
  48 eval records, controls, attribution, disposition, index.
