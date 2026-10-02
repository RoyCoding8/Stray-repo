# Workstream dev01-ops — D-OPS operator/entry lane (DEV-11/DEV-12)

Branch: `codex/dev01-ops`, base `c4ec6f7`. DB: `settlement_dev01ops` (disposable).
Python: `/tmp/asv2-dev01-impl/.venv/bin/python`,
`PYTHONPATH=<worktree>/src:<worktree>/experiments:<worktree>/tests`.

## Dispositions

- DEV-11 done. `src/settlement/api.py` gains read-only `episode_data` /
  `_episode_summary` grouped by protocol prefix: phase, next decision,
  per-protocol arms/outcomes/verdicts, expenditure, lineage
  (`capability_versions`), releases, router policies, simulated flag from
  `evaluator_receipts`. `learning_data` carries `episodes`; `learning.html`
  renders the bounded episode section; `investigation.html` links to
  `/learning`. No new route, no separate app, no schema change.
- DEV-12 done. `experiments/run_dev_episode.py` runs the full episode
  through the committed `experiment.run_abcs` contract and reports all nine
  §4 phases with revision/environment/result detail. `--gateway fixture`
  (default) runs the deterministic ScriptedDouble; `--gateway live`
  requires endpoint/key/grant/model plus an admitted containment profile
  and refuses otherwise (exit 2 missing inputs naming each absent variable,
  exit 3 refused profile/discovery/auth). A/B/C arms plus the no-op
  ablation stay visible in stdout and in
  `<artifacts-root>/<prefix>-episode.json`.
- Deterministic fixture run passes end-to-end (exit 0): B shows
  observed-gain on the panel from textual lessons, C is inconclusive under
  the scripted double, disposition is `fixture-only` with incumbent
  `baseline-v0` fallback. Negative/inconclusive fixture evidence is
  reported as such.

## Verification

Focused plus area suites, all green on `settlement_dev01ops`:

- `tests/test_dev01_ops.py` (new, 8 tests): fixture end-to-end incl.
  record-file equality, live-refusal exact-input naming, uncontained-profile
  refusal, episode UI phase/lineage/costs, investigation link, pending
  state, read-only GETs, source-revision reporting.
- `tests/test_ui_views.py` + `test_operator_review.py` +
  `test_learning_review.py` + `test_ui_commands.py`: 24 passed.

## Live run (blocked: no live inputs supplied)

```
uv run python experiments/run_dev_episode.py --dsn $SETTLEMENT_DSN \
  --allocation <allocation> --artifacts-root $ARTIFACT_ROOT \
  --gateway live --model <model> --launcher runsc --runsc-image sha256:<pinned>
```

Missing: `SETTLEMENT_GATEWAY_ENDPOINT` (or `SETTLEMENT_GATEWAY_URL`),
`SETTLEMENT_GATEWAY_KEY`, `SETTLEMENT_GRANT_UNITS`, `--model`
(or `SETTLEMENT_MODEL`), and a containment profile (`--runsc-image`, or
`--launcher local --allow-uncontained`).

## Residual risks

- Fixture C never succeeds (double returns broken code for the C arm), so
  the deterministic path cannot demonstrate executable-method gain; it
  proves integration only. Live evidence is still required for any
  promotable claim.
- One database holds one full task-panel run: hidden answers are
  task-scoped and the command journal binds request identity to payload,
  so a repeat run needs a fresh database or a new task set.

## Coordinator change requests

- `experiment.run_abcs` binds hidden answers per task ID with no episode
  prefix, and operation/request IDs derive from the protocol prefix, so a
  second episode over the same tasks on the same database is refused
  (duplicate hidden answers; journal identity reuse). Request: episode- or
  prefix-scoped hidden answers, or a documented one-run-per-database rule
  for the integrated entry point. No lane file was changed for this.
- Reuse note: `run_dev_episode.py` imports `_bind_grant_cap`,
  `_parse_ids`, `_select_launcher` from `experiments/run_live_abc.py`
  (same snapshot) to keep one copy of the grant/containment conventions.
- Integration note: the runner consumes `run_abcs` only and does not
  depend on the sibling `development.py` episode table; the operator view
  reads committed trial/ledger/capability rows, so both lanes' records
  surface there once merged.
