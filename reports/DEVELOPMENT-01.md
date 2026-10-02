# DEVELOPMENT-01 — first development episode (deterministic slice)

Coordinator branch: `codex/implementation-development-01`. Design tip
`7c3d380` merged as `c4ec6f7`. Lane merges: D-EP `87f2e88`
(`5b7918f`), D-CMP `36259a2` (`9d0d6f4`), D-OPS `960f278` (`3498cbf`),
all conflict-free (disjoint files). Integration fixes in `f3318f8`.

Live model access is absent (no `SETTLEMENT_GATEWAY_ENDPOINT` /
`SETTLEMENT_GATEWAY_KEY` / `SETTLEMENT_GRANT_UNITS` in the environment),
so no live run is claimed. The deterministic slice is complete and
proven: `experiments/run_dev_episode.py --gateway fixture` runs the full
nine-phase episode against real PostgreSQL and real subprocesses.

## What was built

- Durable episode lifecycle (`src/settlement/development.py`, migration
  `0007_dev_episodes.sql`): observe → propose → admit with trigger refs,
  reference version, access policy, finite allocation and seed ceilings
  (≤2 explanations, ≤1 probe, ≤2 candidates enforced in state), then
  diagnose → construct → check → freeze → select → bind with
  comparison-feedback fencing (construction retry refused after bind).
- Model-backed constructor through broker-routed inference
  (`_infer_via_broker`; gateway adapter live, scripted doubles
  deterministic); scripted responses carry `simulated: True` receipts.
- Development check applies the claimed intervention to development
  batch inputs (invoke procedure per task, grade repaired outputs) —
  the direct-grade form could never pass for the specified procedure
  shape and was replaced during integration.
- Frozen source-group splits, digest-bound evaluation with tallies,
  honest A/B/C (labeled exact-lookup baseline, no-op control,
  inconclusive valid), release/reject paths with incumbent fallback,
  rejected-episode inspectability, per-arm acquisition/use accounting.
- One entry point (`experiments/run_dev_episode.py`) driving the durable
  lifecycle, injecting the bound candidate into the comparison through
  `synthesize` with `fixer_version` set to the bound version id, so the
  C arm invokes the exact bound bytes (no twin version; proven in the
  episode record). Repeat episodes on one DB work (answer setup is
  idempotent on identical content, refusing divergent re-assertion);
  re-running a bound episode id refuses on identity.
- Operator episode view (phase, next decision, hypotheses, lineage,
  comparison, costs) linked from the investigation/learning views.

## Verification

- New lane tests: `tests/test_dev01_episode.py` (12),
  `tests/test_dev01_compare.py` (11), `tests/test_dev01_ops.py`
  (extended with episode-state, version-identity and answer-idempotency
  assertions). Deterministic doubles only; every broker/sandbox effect
  is real.
- Full suite on `settlement_t1broker`: see `reports/VERIFICATION.md`
  (Development-01 section).
- Deterministic end-to-end runs on scratch DBs, including a repeat run
  on one DB and a same-DB second episode.

## Open gates (need live inputs)

Live model access (endpoint, key, funded grant, run profile), then the
prompt's runnable command. Empirical learning comparison stays
out-of-scope until a funded live run exists; no learning claim is made.
Multi-family episodes share one `fixer_version` stem today (seed episode
is single-family).
