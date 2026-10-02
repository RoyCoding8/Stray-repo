# Workstream L-EP: D2A-001..003, cost union, live preflights

Branch: `codex/d02live-episode` (base `cf43e63` on
`codex/implementation-development-02`).
Lane DB: `settlement_d2liveep` (real PostgreSQL, per-test truncate via
`migrated_db`; `SETTLEMENT_TEST_DSN='dbname=settlement_d2liveep
host=/var/run/postgresql'`). Doubles only at model-inference seams.

## Dispositions

- D2A-001 CLOSED. One canonical file ABI (`METHOD_ABI` in
  `src/settlement/development.py`) states entry/staging (`method.py` +
  `broken.py`), invocation (`python method.py <in-dir>/broken.py
  <out-dir>/fixed.py`, read `fixed.py`), `--selftest` typed-JSON
  contract, sandbox-only effects, and procedure-not-function shape.
  `construct` sends that ABI as the packet `invocation` contract and as
  an explicit `file_abi` prompt block; the diagnose/construct prompts
  carry `response_contract` taken from the same
  `context._OUTPUT_CONTRACTS` object the packet renders, plus a declared
  `RESPONSE_FORMAT` policy. `_OUTPUT_CONTRACTS["diagnose"]` now declares
  the `intervention` the consumer (`development.diagnose`) requires
  (one-shape surgical edit in `src/settlement/context.py`, see limits).
  Envelope policy, shared by both phases: strict JSON first, else exactly
  one bare ```json fence, else honest invalid output; schema-validated;
  code is never extracted from prose. Staged `--selftest` must exit 0
  with typed-JSON worker `status ok`, so a bare repaired function can no
  longer pass construction. Evidence: `test_diagnose_contract_declares_
  intervention`, `test_construct_prompt_states_file_abi`,
  `test_envelope_policy_on_exact_production_responses`,
  `test_live_diagnose_bytes_diagnose_through_production_path` (recorded
  live pilot bytes diagnose end to end),
  `test_live_construct_bytes_stay_honest_invalid_output` (recorded live
  pilot prose+fence stays invalid, slot consumed),
  `test_bare_function_fails_procedure_selftest`,
  `test_constructed_procedure_survives_consumer` (consumer
  `_invoke_method` applies the built procedure to held-out
  `panel-triangular` and reproduces its reference fix),
  `test_abstention_consumes_no_slot`.
- D2A-002 CLOSED. `collect_experience` now UPDATEs the episode
  `trigger_refs` with each task's `claim_id` in the same transaction
  that emits `development.experience_collected` (same event kind, so the
  episode trace contract is unchanged), and returns the enriched refs.
  `context._claim_candidates` therefore resolves collected claims into
  diagnose bundles with no other writer touching trigger refs. Evidence:
  `test_collect_links_claims_into_trigger_refs` (DB refs + event),
  `test_diagnose_prompt_carries_collected_material` (bundle proposition
  equals the stored broken/cases/outcome/model_text; the actual outgoing
  prompt carries the `return sum(range(n))` sentinel, the attempt
  outcome, model/grade op refs and attempt text).
- D2A-003 CLOSED. `run_use.py` accepts `--disposition-json`
  `{released: {family: version_id}, router_policies: {family: policy},
  trial: bool}` and forwards it; `run_subsequent_use` resolves ordinary
  selection exclusively from that disposition through the normal
  `capabilities.route` path. Released + routed-match + eligible +
  in-scope + bytes-available selects the version as ordinary `selected`
  use; anything else (no release, no policy, router refusal/divergence,
  unknown/quarantined version, wrong scope, missing bytes) falls back to
  the incumbent with the reason recorded on the result and the domain
  event. `trial: true` invokes the bound candidate as an explicitly
  labeled `trial` record, never as ordinary use. The entry builds the
  disposition from the real post-comparison releases
  (`_use_disposition`) and passes it to the fresh `run_use.py` process.
  Evidence: `test_unreleased_binding_falls_back_to_incumbent`,
  `test_wrong_family_task_falls_back_with_reason`,
  `test_released_version_resolves_via_router`,
  `test_trial_invocation_is_labeled`,
  `test_quarantined_release_falls_back_to_incumbent`,
  `test_missing_bytes_fall_back_to_incumbent`,
  `test_run_use_disposition_json_plumbing` (fresh process + bad-JSON
  refusal), `test_use_disposition_builds_from_releases`.
- D2A-004/005 NOT TOUCHED (L-CTX owns them; no claim made here).
- Cost union CLOSED. `experiment.episode_cost_union` exports the
  whole-episode unique-operation union over collection, diagnosis,
  construction, checks, comparison-shared, comparison-A/B/C and
  subsequent-use phases, with per-phase sums, shared-op listing,
  token estimates and preserved `unresolved_exposure`. The entry wires
  it into the report as `episode_costs`; the comparison-harness totals
  stay under `accounting` now explicitly labeled by `accounting_scope`
  (`harness-only ...`). Evidence:
  `test_episode_cost_union_covers_all_phases` (coverage, uniqueness,
  shared-op detection, independent `_op_accounting` recomputation,
  arm splits, beyond-harness operations),
  `test_cost_union_preserves_unsettled_exposure` (open reservation
  survives the union), migrated fixture end-to-end asserting
  `accounting_scope`, `episode_costs` scope/phases in the entry record.

## Probe correspondence (probes never edited)

`uv run pytest -q reviews/probes/test_development_02_acceptance.py`:
2 failed, 3 passed (was 5 passed at assessment).

- `test_constructor_declares_selftest_without_normal_file_interface`
  now FAILS: the emitted contract carries the file ABI and the prompt
  names `fixed.py`/`input_path` (intended; closed by the D2A-001 tests
  above).
- `test_subsequent_use_invokes_unreleased_out_of_family_binding` now
  FAILS: the same call resolves to incumbent (intended; closed by the
  D2A-003 tests above).
- `test_collected_claim_is_not_resolved_for_diagnosis` still passes:
  `build_packet` over synthetic *unlinked* refs still yields no bundles,
  which remains true; production linkage is proven by the D2A-002 tests
  above on the real collect->diagnose path.
- `test_ready_budget_fallback_removes_counterexample_body` and
  `test_packet_binding_accepts_unrelated_operation_without_reading_input`
  still pass: D2A-004/005 belong to L-CTX and are untouched by this lane.

## Modified paths

- `src/settlement/development.py` (owned): `METHOD_ABI`,
  `RESPONSE_FORMAT`, `_single_fence`, `_parse_envelope`; diagnose and
  construct prompts carry response contract + format; envelope-tolerant
  parsing in both phases; construct packet invocation contract carries
  the file ABI; staged selftest requires typed-JSON worker `ok`;
  `collect_experience` links claim ids into trigger refs (UPDATE +
  existing event, enriched return).
- `src/settlement/experiment.py` (use/cost regions only):
  `_resolve_use_selection`, disposition-aware `run_subsequent_use`
  (new `reason`/`trial`/`disposition` fields), `episode_cost_union`.
  `_invoke_method`/`_run_sandbox` untouched.
- `experiments/run_dev_episode.py` (owned): `_use_disposition`,
  `_episode_phase_ops`, disposition passed to the fresh use process,
  `episode_costs` + `accounting_scope` + use reason/trial/disposition in
  the entry report.
- `experiments/run_use.py` (owned): `--disposition-json` with refusal
  on malformed input.
- `src/settlement/context.py` (shared, one shape only): diagnose
  `response_shape` gains `intervention: {action: str}` exactly as
  `development.diagnose` consumes it. No other line touched; L-CTX owns
  the file otherwise and must take this hunk at integration.
- `tests/test_d02live_episode.py` (new, 20 tests): probe-correspondence
  header + regressions above; embedded live-pilot responses are
  byte-exact copies of
  `reports/evidence/development-02-prompt-pilot/results.json` used as
  fixed test vectors (no live inference).
- Migrated expectations for intentionally changed contracts (CHECK
  pre-authorization): `tests/test_dev02_episode.py`
  (`test_subsequent_use_invokes_selected_version` and
  `test_fresh_process_use_records_receipts` now supply a real router
  policy + released disposition and use the in-scope panel task),
  `tests/test_dev01_ops.py` (fixture end-to-end use phase is now honest
  incumbent with reason, plus `accounting_scope`/`episode_costs`
  assertions). No other committed test needed changes.

## Checks

- `uv sync --extra test`: ok.
- Lane DB: `SETTLEMENT_TEST_DSN='postgresql://ubuntu@/settlement_d2liveep
  ?host=/var/run/postgresql'` (URL form; the keyword form breaks the
  sibling-DB fixtures in `test_r01_recovery.py`/`test_r02_authority.py`,
  which URL-split the DSN — 8 setup errors on the first full run were
  that harness artifact, not a product failure).
- New file: 20 passed on real PostgreSQL + real subprocesses.
- Touched files: `test_dev02_episode.py` 13 passed;
  `test_dev01_episode.py` + `test_dev01_ops.py` 21 passed.
- Full suite: 512 passed, 0 failed, 0 errors (728s) with the URL DSN.
  (First full run: 501 passed / 3 failed / 8 errors under the
  keyword-form DSN; the 8 errors were the sibling-DB fixture artifact
  above and the 3 failures did not reproduce — clean on the URL-DSN
  rerun.)
- Probes: 2 failed / 3 passed as documented above (intended).
- `py_compile` on all touched files: ok. `ruff` is configured
  (`line-length = 100`) but not installed in the venv, so it could not
  run; over-length lines in the new file are only the byte-exact live
  response fixtures.

## Exact live blocker (no live gateway in this environment)

All of endpoint/key/grant/model unset (verified: no `SETTLEMENT_*` in
the environment). No live inference is claimed anywhere; doubles used
are labeled simulated.

- `uv run python experiments/run_dev_episode.py --dsn
  'dbname=settlement_d2liveep host=/var/run/postgresql' --allocation
  noop --artifacts-root /tmp/d02live-preflight-artifacts --gateway live
  --model claude-opus-4-6-thinking --launcher runsc --runsc-image
  sha256:pinned`
  -> `live dev episode blocked: missing SETTLEMENT_GATEWAY_ENDPOINT,
  SETTLEMENT_GATEWAY_KEY, SETTLEMENT_GRANT_UNITS; live dev episode
  blocked: set SETTLEMENT_GATEWAY_ENDPOINT, SETTLEMENT_GATEWAY_KEY, and
  SETTLEMENT_GRANT_UNITS (monetary grant cap)`, exit 2.
- `uv run python experiments/run_use.py --dsn ... --artifacts-root ... --allocation noop --investigation noop --episode noop --use-task dev-sum --gateway live --launcher runsc --runsc-image sha256:pinned --model claude-opus-4-6-thinking`
  -> same refusal, exit 2.

Runnable live commands once access exists (coordinator captures the
refusal; record kept here):

- `uv run python experiments/run_dev_episode.py --dsn $SETTLEMENT_DSN
  --allocation <allocation> --artifacts-root $ARTIFACT_ROOT --gateway
  live --model claude-opus-4-6-thinking --launcher runsc --runsc-image
  sha256:<pinned> [--use-task <id>]`
  with `SETTLEMENT_GATEWAY_ENDPOINT`, `SETTLEMENT_GATEWAY_KEY`,
  `SETTLEMENT_GRANT_UNITS` (positive integer) set.
- Fresh use afterwards: `uv run python experiments/run_use.py --dsn
  $SETTLEMENT_DSN --artifacts-root $ARTIFACT_ROOT --allocation
  <run-allocation> --investigation <inv> --episode <ep> --use-task
  <id> --disposition-json '<entry-reported disposition>' --gateway live
  --model claude-opus-4-6-thinking --launcher runsc --runsc-image
  sha256:<pinned>`.

## Limits

- Shared-file touch: the one-shape `context.py` hunk needs L-CTX
  awareness at integration (file otherwise untouched).
- No live inference, provider smoke, or generated-code execution beyond
  the sandbox profile was possible here; the live episode remains an
  exact-blocker record above.
- Fixture end-to-end use is now incumbent by construction (synthetic
  evidence stays non-promotable); ordinary `selected` use is proven on
  real release-shaped dispositions, not on a live release.
- `run_abcs`-internal synthesis (`_synthesize_method`) untouched; worker
  acquisition still flows through doubled inference labeled simulated.
- Lane DB `settlement_d2liveep` and `/tmp/d02live-preflight-artifacts`
  left in place for coordinator inspection; temp worktree is this lane's
  own checkout, no other worktree touched.
