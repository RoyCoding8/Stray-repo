# Workstream report: D02LIVE lane L-CTX (D2A-004, D2A-005)

Branch `codex/d02live-context`, base `cf43e63`. No live gateway in this
environment: deterministic work only, no live inference claimed.

## Disposition

- D2A-004 (CTX-05/06 linkage): closed at the packet layer with two scoped,
  evidenced qualifications (§Limits L-CTX-1, L-CTX-2). `bind_packet_invocation`
  (frozen signature) now reads the actual operation row, refuses operations
  declaring a non-model effect, records the sha256 of the stored input payload
  in new column `packet_invocations.input_digest` (migration 0009), and refuses
  conflicting second-operation linkage while true redelivery and journal
  idempotency keep working.
- D2A-005 (CTX-04 opposition under budget): closed. `_render_text` always
  renders full opposition bodies (the slim renderer is deleted, not bypassed);
  over-budget packets return `needs_information` with a stage/narrow proposal
  instead of ready-with-omissions. Ordered reading (mandatory first) kept.
  The maintained budget test now pins the intended contract; correspondence
  recorded in both test file headers. Reviewer probes not inverted.

## Modified paths

- `src/settlement/context.py`: effect gate + input digest + conflict gate in
  `bind_packet_invocation`; full-only `_render_text`; budget block stages
  instead of stripping; `_bundle_view`/`budget_cut` deleted.
- `migrations/0009_packet_input_binding.sql` (new): `input_digest` column.
- `tests/test_d02live_context.py` (new): 5 real-DB regressions.
- `tests/test_dev02_context.py`: `test_budget_stages_and_refuses` now pins
  never-strip/stage (intended contract change) + header correspondence.
- `tests/test_rec_checkpoint.py`: recovery manifest lists 0009 (mechanical).

## Checks

- `uv sync --extra test`: ok.
- New tests on real PostgreSQL `settlement_d2livectx`: 5 passed, no doubles
  (broker admission prepares rows without dispatch; no gateway needed).
- Existing files touched, same DB: `test_dev02_context.py` 12 passed,
  `test_s2_context.py` + `test_rec_checkpoint.py` passed.
- Sibling integration (read-only run, not owned): `test_dev02_episode.py`
  13 passed, incl. the 24k-budget challenge packet and packet-bound
  construction. Changed paths invoke no subprocesses, so no subprocess
  coverage applies to this lane.
- Full suite on final source, same DB: 481 passed
  (`tests/ --ignore=tests/test_s0_gateway.py`), plus `test_s0_gateway.py`
  16 passed separately (local stub server, no live gateway): 497 total, 0
  failures.

## Limits

- L-CTX-1: operations with no declared effect marker (legacy direct-prepared
  rows, e.g. the pinned ctx06 fixture) are still accepted. Every production
  operation is broker-created and always declares its effect, so the gate
  coincides with require-model-inference on all reachable shapes. Strict
  refusal would red the pinned keep-green set; filed here instead of worked
  around.
- L-CTX-2: a second operation binding is refused only when that operation's
  stored input does not reference the packet. Blanket refusal broke the pinned
  construct-revision pattern (`development.py` reuses one packet across
  per-slot model ops that genuinely embed it; observed red in
  `test_revision_consumes_a_candidate_slot`, green after this scoping).
  Conflicting/replayed linkage is refused; true redelivery is recorded.
- Caller envelope duty: `token_estimate` stays `chars`-labeled by design.
  Callers must measure their final wrapper: the episode lane enforces its own
  prompt bound separately at `_packet_for`/inference time. Over-budget
  packets now surface as `needs_information`, so undersized caller budgets
  fail loudly instead of silently stripping opposition.
