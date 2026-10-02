# Workstream M-CTX — bounded decision-context packets (CTX-01..CTX-07, CTX-09)

Branch `codex/dev02-context`, base `b7d7c85`. Lane DB `settlement_dev02ctx`
(real PostgreSQL over the local socket; DSN
`postgresql://ubuntu@/settlement_dev02ctx?host=/var/run/postgresql`).
Deterministic only: no live gateway exists here, no live claims made.

## Pinned seam (implemented exactly)

`context.build_packet(dsn, cmd, *, decision, artifacts_root=None) ->
CommandResult`. The trailing optional `artifacts_root` only enables
byte-verification; the `(dsn, cmd, *, decision)` call shape M-EP codes
against is unchanged. `decision` carries `decision_kind`,
`purpose`, `required_inputs`, `allowed_actions`, `access`,
`budget: {input_chars, output_reserve}`, `current_versions`,
`investigation_id`, `episode_id`. Result `data` carries `packet_id`,
`outcome: ready | needs_information | stale`, `rendered`,
`rendered_digest`, `mandatory_content`, `evidence_bundles`, `gaps`,
`footprint`, `omissions`, `token_estimate: {chars, labeled:
"chars-not-tokens"}`. Binding table
`packet_invocations(packet_id, operation_id, rendered_digest)`; packet
identity + digest are what M-EP records in the episode row / gateway
receipt. `policy_version` is `d02-seed-v1`.

## CTX coverage (all proven in `tests/test_dev02_context.py`, 12 tests)

- CTX-01: per-kind required contracts are data (`_REQUIRED`), pairwise
  distinct; unknown kinds / unknown slot names / non-positive budgets raise
  `SettlementError`. Bare unknown ids yield `needs_information`, never
  `ready` (`test_kind_contracts_differ_and_empty_refs_never_ready`).
  Caller `required_inputs` extras are unioned in and enforced.
- CTX-02: experience resolves through existing stores (episode trigger
  refs, attempt observations, receipts + allocation costs, capability
  rows). Hidden-claim propositions never render at `candidate` scope while
  permitted public material does; scope labels come from the authoritative
  `claims.access_label`, never model text.
- CTX-03: per-kind declared output/invocation contracts ship in
  `mandatory_content`; pinned capability invocation/effect/resource are
  byte-exact from `capability_versions`; resume carries pending operations
  (live reconciliation), merged obligations and the continuation next
  decision (`test_resume_carries_working_state`).
- CTX-04: `total = len(wire_json) + output_reserve <= input_chars`, where
  the wire envelope (schemas + wrapper) is measured, not guessed. Oversize
  optional detail is cut with an `evidence-detail` omission carrying
  dropped-item counts and char estimates; oversize mandatory content
  downgrades to `needs_information` with a stage/narrow proposal, never a
  silent drop. Estimates are labeled `chars-not-tokens` throughout.
- CTX-05: `bind_packet_invocation` requires a stored `ready` packet with
  matching recomputed digest plus an existing operation row; unknown
  packets, non-ready packets and unknown operations are refused
  (`INVALID_INPUT`), so metadata-only context cannot pass. Repeat binds
  are `ALREADY_APPLIED`.
- CTX-06: defeat / retraction / quarantine / retired-or-missing bytes /
  unknown pins produce `stale` (invalidation) rather than silent reuse;
  unwarranted references produce `needs_information` gaps. Multi-group
  warrants keep serving through the surviving route with the block
  recorded as a qualification. `revalidate_packet` rechecks routes,
  opposition, eligibility, bytes and pending-operation sets before
  consequential use, and reports failover notes when an alternative route
  takes over.
- CTX-07: `test_fresh_process_reconstructs_without_rebuild` builds a
  packet in a real child process, SIGKILLs it, then `load_packet` +
  `revalidate_packet` in the test process confirm identical bytes and a
  valid packet with no reconstruction. Packet builds are idempotent per
  `request_id` (journal `ALREADY_APPLIED`, same `packet_id`).
- CTX-09: `overview_data` gains a `packets` region (decision, purpose,
  source/transform versions, qualifications, `rendered_digest`, gaps,
  omissions, derived next action); empty when the table is absent. Inert
  rendering is proven by rendering region values through an autoescaping
  Jinja environment: `<script>` payloads come out escaped.

Out of lane scope: CTX-08, CTX-10 (M-EP).

## Modified paths (owned only)

- `src/settlement/context.py` — packet builder appended after the
  existing `build_context`/`save_continuation`/`resume_package` (untouched):
  decision validation, 21 data-driven slot resolvers, evidence-bundle
  assembly with route selection, budget packing, persistence,
  `bind_packet_invocation`, `revalidate_packet`, `load_packet`,
  `recent_packets`.
- `migrations/0008_context_packets.sql` (new) — `context_packets`,
  `packet_invocations`. Applies cleanly on a fresh database.
- `tests/test_dev02_context.py` (new) — 12 tests. Existing test files
  untouched.
- `src/settlement/api.py` — `overview_data` body only (local import +
  `packets` region guarded by `table_present`); nothing else in the file
  read or changed.

## Checks

- `uv sync --extra test` — clean.
- `SETTLEMENT_TEST_DSN=.../settlement_dev02ctx... uv run pytest
  tests/test_dev02_context.py` — 12 passed.
- Same DSN: `test_s2_context.py + test_ui_views.py +
  test_operator_review.py + test_ui_commands.py` — 20 passed;
  `test_s2_evidence.py + test_s2_artifacts.py + test_evidence_epoch.py` —
  25 passed.
- Ruff is not a repo gate: untouched `evidence.py`/`store.py`/
  `artifacts.py` carry 32 findings of the same classes; new code follows
  house style.

## Limits and notes for the coordinator / M-EP

- Fixture setup uses direct SQL only where no public setter exists
  (episode explanations/candidates, capability rows, quarantine,
  outcome receipts); every exercised path is a real entry point on real
  PostgreSQL, plus real `LocalLauncher`-free subprocesses for the
  kill-process test. No model doubles were needed (no inference on these
  paths).
- Without `artifacts_root`, artifact-backed support routes are refused
  (recorded as gaps/qualifications, mirroring `check_use_verified`);
  byte status otherwise comes from the availability flag and is labeled
  `available-unverified`. `bind_packet_invocation(..., artifacts_root)`
  additionally verifies pinned bytes when given.
- Staleness at build time is invalidation-driven (defeat, retraction
  collapse, quarantine, byte loss, unknown pins); epoch drift alone only
  triggers rechecks inside `revalidate_packet`.
- Templates were not touched (outside owned paths): packet display in
  HTML awaits a template pass or coordinator direction; the data region
  and its inertness proof are in place.
- Characterization probes in `reviews/probes/` were not modified per
  lane rules; correspondence: D02-001 (unresolved refs) is answered by
  mandatory materialized content (`test_diagnose_ready...`), D02-004
  (pinning labeled use) by digest-bound invocation records
  (`test_bind_...`). Migrating the probes themselves is coordinator work.
