# Workstream report: DEVELOPMENT-02-LIVE integration (D2A-001..D2A-005 + cost union)

Branch: `codex/implementation-development-02`.
Integrates `codex/d02live-episode` (`5867da6`, L-EP: D2A-001..003 + cost
union) and `codex/d02live-context` (`556467f`, L-CTX: D2A-004/005) at merge
`3cb7346`, plus integration commit `8221d35` (probe migration below).
Lane reports `d02live-ep.md` / `d02live-ctx.md` stand for lane-internal
detail; this file records the merge, the count reconciliation, the probe
migration, and the definitive suite outcome.

## Merge correspondence

- L-EP touched `src/settlement/development.py` (METHOD_ABI /
  RESPONSE_FORMAT / envelope policy / collect-claim linkage),
  `src/settlement/experiment.py` (use-selection + cost-union regions
  only), `experiments/run_dev_episode.py`, `experiments/run_use.py`,
  `tests/test_d02live_episode.py` (new, 20), `tests/test_dev02_episode.py`
  + `tests/test_dev01_ops.py` (migrated expectations only).
- L-CTX touched `src/settlement/context.py`, `migrations/0009_*`,
  `tests/test_d02live_context.py` (new, 5), `tests/test_dev02_context.py`
  + `tests/test_rec_checkpoint.py` (migrated expectations only).
- Overlap: exactly one hunk — L-EP added `intervention: {action: str}`
  to the diagnose `response_shape` in `context.py`, the shape
  `development.diagnose` consumes. Kept as-is; L-CTX owns the file
  otherwise. No semantic conflict: L-EP prompts read the shape object,
  L-CTX defines it.
- Shared-file review: `development.py` L-CTX-untouched; `experiment.py`
  L-CTX-untouched outside use/cost regions (`_invoke_method` /
  `_run_sandbox` untouched by both); `run_dev_episode.py` L-CTX-untouched.

## Count reconciliation

- Base `56f7bba` -> merge: per-file `def test` counts identical for
  every pre-existing file under `tests/` (verified by diff); only
  in-place expectation migrations for intentionally changed contracts.
  New defs: +20 `test_d02live_episode.py`, +5
  `test_d02live_context.py`, +6 `reviews/probes/`
  (probe file postdates the base). 478 -> 509 defs, exactly +31.
- The two lane full-suite numbers compose exactly with the merge:
  merged `tests/` collects 517 = 512 (L-EP branch full suite) + 5
  (L-CTX `test_d02live_context.py`) = 497 (L-CTX branch full suite:
  481 + 16 `test_s0_gateway.py`) + 20 (L-EP
  `test_d02live_episode.py`). Verified by collection on the merge.
- Merged collection: 517 (`tests/`) + 6 (acceptance probes) = 523.
  (Base "509 passed" in `a1d2525` is not bridged def-by-def here —
  collection flags may have differed; what is proven is zero
  add/remove/rename in pre-existing files plus the +31 new defs.)

## Probe migration (`8221d35`, supersedes both lanes' probe notes)

L-EP's "2 failed / 3 passed (intended)" and L-CTX's "reviewer probes
not inverted" were both branch-local truths. After the merge, 4 of the
5 acceptance probes failed — each asserting a reviewed limitation that
a merged lane intentionally fixed:

- `test_constructor_declares_selftest_without_normal_file_interface`
  -> `test_constructor_declares_normal_file_interface` (D2A-001: file
  ABI in contract + prompt; stale `intervention`-absent pin dropped —
  L-CTX deliberately added `intervention` to the diagnose shape).
- `test_subsequent_use_invokes_unreleased_out_of_family_binding`
  -> `test_subsequent_use_refuses_unreleased_out_of_family_binding`
  (D2A-003: bindings-only resolves incumbent with reason, no router
  call, no pin, no invoke; disposition recorded).
- `test_ready_budget_fallback_removes_counterexample_body`
  -> `test_budget_overrun_keeps_counterexample_body_and_stages_gap`
  (D2A-005: over-budget stages `needs_information` with a budget gap;
  nothing stripped — mirrors `test_budget_overrun_keeps_opposition_and_stages`).
- `test_packet_binding_accepts_unrelated_operation_without_reading_input`
  -> `test_packet_binding_records_input_digest_for_model_inference` +
  `test_packet_binding_refuses_non_inference_operation` (D2A-004:
  payload read, effect gate, input digest; Cursor double extended with
  the operations-row branch + `fetchall`).
- `test_collected_claim_is_not_resolved_for_diagnosis` untouched
  (synthetic-unlinked-refs yield no bundles — still true).

All 6 pass mock-only in <1s (`reviews/probes/`
`test_development_02_acceptance.py`: 6 passed).

## Definitive suite (tested code revision `8221d35`)

Command (real PostgreSQL 16, real subprocesses, fake/simulated models
only; URL-form DSN — the keyword form breaks the sibling-DB fixtures
per `d02live-ep.md`):

```
SETTLEMENT_TEST_DSN="postgresql://ubuntu@/settlement_t1d02live?host=/var/run/postgresql" \
  uv run pytest tests/ -q -p no:cacheprovider
```

Result: **1 failed, 516 passed in 743.72s** = 517 collected
(517 = 512 L-EP + 5 L-CTX, see above). Plus the 6 acceptance probes
**6 passed** separately (mock-only, <1s). Total gate: 522/523 green.

The single failure is `tests/test_launchers.py::test_timeout_kills_whole_process_group`
— a timing-shaped flake in a file neither lane touched (per-file test
counts identical to base): it asserts via `pgrep -f "sleep 30"` that no
orphan survives the kill grace window, which races under full-suite
load. Evidence: passes in isolation (1.42s) and file-level
(`test_launchers.py`: 8 passed) on the same revision and DB; same
load-flake pattern as L-EP's mid-lane "3 failures did not reproduce".
Not re-run at full-suite level: the failure is outside every D2A
workstream path and green at both narrower scopes.

Boundaries: `ruff` configured (`line-length = 100`) but not installed
in the venv — could not run (same as lane note). No live inference,
provider smoke, runsc containment, PG18, or held-out transfer use
(superior live gates from both lane reports stand).
