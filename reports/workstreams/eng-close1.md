# ENG-CLOSE1 — closure repair lane report

Base `b9d27be`. Branch `codex/eng-close1`, worktree `/tmp/asv2-close1`
(single writer; no other agent in this worktree). Code commit `c53049a`
(pushed). Test DB `settlement_close1` + only-own siblings
(`settlement_close1_wfshape`, `settlement_close1_dbos`,
`settlement_close1_close1sib`); dropped at end. Real PostgreSQL 16 +
real subprocesses throughout. Doubles only at model seams, labeled
(`FakeGatewayAdapter`, `ScriptedDouble` with `simulated: True`). No live
inference in this lane (deterministic only).

## Fixes (code + red-capable regressions in `tests/test_eng_close1.py`)

| ID | Change | Red evidence | Green evidence |
|---|---|---|---|
| ENG-INVA-03 | `store.seed_allocation` validates app-side mirroring `subdivide_allocation`: `authorized > 0`, `amount_scale > 0`, `max_occupancy >= 0`, else bounded `INVALID_INPUT` (`src/settlement/store.py`) | New test fails on base sources (raw `CheckViolation` escapes; zero-authorized applies) | `test_seed_allocation_refuses_nonpositive_inputs` passes; positive seed still `APPLIED` |
| ENG-INVA-04 | `store.admit_receipt` flags a post-settlement contradictory terminal receipt under a new identity: receipt row still stored, plus `receipt_conflicts` row, `reconcile_state='conflict'`, `operation.receipt_conflict` event — same shape as the INVA-01 fix (`src/settlement/store.py`) | New test fails on base (`reconcile_state` stays `none`) | `test_contradictory_late_receipt_flagged_for_reconciliation` passes; matching-outcome late receipt still unflagged (`test_matching_late_receipt_not_flagged`, passes both) |
| ENG-INVA-05 | `run.validate_composition` enforces `_depth(root) <= max_depth`; `broker.attempt_workflow` entry routes through `validate_composition` (`src/settlement/run.py`, `src/settlement/broker.py`) | New tests fail on base (depth-6 validates; workflow admits) | Depth-5 refused, depth-4 accepted, custom `max_depth` honored; resume paths (`heartbeat`, `wf_consume`, `wf_record`) untouched so persisted work still resumes |
| ENG-INVA-08 | `tests/test_r02_authority.py` fixture rewritten: `_conn_params` parses keyword and URL DSNs, `_sibling_dsn` preserves form (explicit `scheme:///name` rebuild for empty-netloc URLs instead of `urlunsplit` path surgery), `_make_database` connects via param-derived admin DSN, `dbos_sys_dsn` skips with reason only when the DSN is not URL-form (DBOS `database_url` is SQLAlchemy-parsed: truly unbuildable) | Base helpers fail on keyword DSN (`/settlement_close1_wfshape`, `ProgrammingError: missing "="`, `_base_name` returns whole string; scratch `/tmp/reddsn/red_dsn.py`) | Keyword DSN: 15 passed + 2 skipped (DBOS, reasoned); URL DSN: 17 passed |
| ENG-INVB-11 | No code change after re-examination (see below); added executable pin `test_broker_admission_refuses_unadmitted_cwd_key`: `ensure_operation` with `cwd` returns `INVALID_INPUT` and stores nothing | n/a (refusal predates; test passes both) | Passes; committed `tests/test_eng_invb_dispatch.py` cwd-honoring tests still green (20 passed together) |
| ENG-INVB-13 | Deleted dead `HttpGatewayAdapter._decode` (no callers; `_decode_body` serves all paths) (`src/settlement/gateway_http.py`) | n/a (deletion; zero references verified by grep) | Gateway suites green |
| INVC-12 `check_use` | `evidence.check_use` refuses any epoch mismatch (`!=` instead of `<`): a future epoch is impossible-honest against a monotonic DB counter, so refusal rejects only buggy/cross-DB input, per TX-4 revalidation (`src/settlement/evidence.py`) | New test fails on base (future epoch returns snapshot) | `test_check_use_refuses_future_epoch` passes; stale-epoch refusals unchanged (epoch suites green) |
| INVC-12 `doubles` | `ScriptedDouble.infer` returns `GatewayError(protocol, ...)` naming arm/task instead of raw `KeyError` on unknown tasks, matching the two `GatewayError` returns above it (`experiments/doubles.py`) | New test errors on base (`KeyError: 'nope'`) | Passes |

Red run on base sources: 7 failed / 3 passed (guards + fixture tests, which
were red-checked separately against the base fixture). Green run on fix:
10 passed. An in-progress edit that removed launcher `cwd` honoring was
reverted before commit when the committed `tests/test_eng_invb_dispatch.py`
pin (cwd honored direct-call, traversal-safe fallback) was found: the broker
validator is the admission boundary, the launcher mechanism is test-pinned,
and same-uid execution crosses no new boundary. No test was rewritten to fit
a change.

## Justifications (no code change, contract-backed)

- ENG-INVB-10 (responses billing): deliberately unchanged per D-ENG-02, now
  with direct evidence. Probe on final tree: a responses body carrying
  `charge_units: 50` decodes to `billed=False, charge_units=0`
  (`gateway_http.py:457-464`); the resulting unbilled op settles its full
  reservation with `billed=False, provider_charge_units=None`
  (`experiment.py:487-505`). Per EFF-8 unknown usage retains conservative
  exposure: nothing is silently under-settled, and parsing unobserved
  charge fields against no billing oracle would risk the verified cost
  union. Fail-visible, not fail-silent.
- ENG-INVB-12 (runsc liveness): unchanged per D-ENG-03, verified. Probe:
  stale `.container` track with no daemon → `live_ids` lists it (assume
  alive, `launcher_runsc.py:302`), `stop` returns `False` (no false success).
  Exposure retained, reconcile defers; flipping to assume-dead risks
  duplicate sends.
- ENG-INVC-10 (familyless release matching): no production caller exists
  (`releases_for_scope` referenced only by tests); semantics pinned by
  `tests/test_s3_capabilities.py:136-139` (empty-family query returns all;
  family query selects its own). A familyless scope constrains nothing, so
  match-all is the symmetric reading. No contract decides otherwise; no
  change.
- ENG-INVC-11 (direct `record_result`): unreachable for promotion.
  `record_result` stamps `origin: direct-caller-outcome` (`trials.py:178`);
  the release gate refuses any receipt with origin in `SYNTHETIC_ORIGINS`
  plus requires evaluator-invocation binding
  (`capabilities.py:206-208,370-386`); production `_close_assignment` uses
  exclusively the bound `submit/bind/receipt` path
  (`experiment.py:1284-1320`). Rebutted for production with exact gates.
- INVC-12 `save_continuation` orphan bytes: ART-2 explicitly permits an
  orphan file on crash before registration with reclaim under retention;
  digest-addressed writes make retry idempotent. No change.
- INVC-12 `amend_protocol` frozen window: crash between the freeze txn and
  the separate `UPDATE ... frozen=TRUE` leaves the new protocol unfrozen,
  and the INVC-02 gate refuses assignments on unfrozen protocols
  (fail-closed, visible). Folding `supersedes` into `freeze_protocol` would
  reshape its API; not taken. No change.
- INVC-12 `register_observation` attestation: model workers have no path —
  admitted domain commands are `("note",)` and observation adapters
  `("clock",)` with broker-computed content (`broker.py:29-30,470-495`);
  only trusted `development.py:406-411` attests (`dev-batch-grade:{op}`).
  Empty identity is stored as an unauthenticated note per IF-3. No change.
- INVC-12 `operator_token` stdout fallback: UI-5 binds the interface to
  local/tunneled access; the print goes to the operator's own console,
  labeled one-process (`api.py:42-53`). No persistence. No change.
- INVC-12 `investigation_data` view bounds: bounded diagnostic (`LIMIT
  100/200/500`); underlying support stays inspectable via
  `current_support`/`check_use` (IF-3); no durable effect. No change.
- INVC-12 `verdict` on empty protocol: LEARN-5 labels plus LEARN-4
  every-assigned-case — zero cases yields `inconclusive`, the intended
  non-claim (`trials.py:248-267`). No change.
- INVC-12 `freeze_protocol` duplicates: refused in-txn (`SettlementError`
  → bounded `INVALID_INPUT`, `trials.py:48-51`); idempotent-by-refusal. No
  change.
- ENG-INVC-13/14: verified closed on the final tree (fixes predate base:
  `b1dece4`, `46427f4`). `asyncio` occurs 0 times in `pyproject.toml`;
  `none recorded` occurs 0 times in `templates/learning.html`.
- ENG-INVA-06/07/09: outside the CLOSE-1 item list; left ledgered for the
  coordinator, untouched.

## Matrix rows

- Entry points: `experiments/run_tests.py` assessed end to end on final
  tree — evaluator-side grader, per-case transient child (`-I`, scrubbed
  env, private cwd), typed-JSON verdicts, absolute 1e-9 float closeness,
  per-case budget slicing, cases file unlinked after load, every case
  counted (live run: 2 passed / 1 failed / 3 total on a float+wrong-answer
  fixture). Docstring scopes isolation to the outer sandbox step; accurate.
  PROV records complete: `run_dev_episode.py`, `run_use.py`,
  `run_live_abc.py` all pin `_source_fingerprint` (exact revision + dirty
  bytes digest) and `_effective_config` (adapter/launcher/model/grant) into
  entry records (ENG-PROV `c0fd039` lineage, verified by read on final
  tree). No change needed.
- Tests/probes: live `reviews/probes/test_*.py` (4 files) run green, 27
  passed; historical files (`context_policy_pilot.py`,
  `development_02_prompt_pilot.py`, `historical_*`) are intentionally
  uncollected (27 collected, headers declare supersession). Final suite
  count below (coordinator reconciles).
- EVID-01: verified closed on final tree by direct probe —
  `validate_solver_output` classifies missing/non-text (transport),
  length/incomplete stop (truncated), empty/syntax-error/fenced-prose
  (format), parseable source (ok) with the source bytes preserved verbatim
  for staging under `SOLVER_SOURCE_CONTRACT` (`experiment.py:150-197`).
- EVID-02: verified closed on final tree by direct probe — unbilled usage
  settles `reserved` with `billed=False, provider_charge_units=None`;
  verified billed usage settles the charge with `billed=True`
  (`experiment.py:464-505`); plus committed
  `test_unbilled_usage_settles_full_reservation`, green under both DSN
  forms in the runs above.

## Checks run (observed)

- New `tests/test_eng_close1.py`: 10 passed (fix); 7 failed / 3 passed on
  base-source overlay (red-capable); base-fixture DSN failure reproduced
  via `/tmp/reddsn/red_dsn.py`.
- `tests/test_r02_authority.py`: keyword DSN 15 passed + 2 skipped
  (reasoned DBOS skip); URL DSN 17 passed.
- Neighbors on fix (URL DSN): store/evidence/run 77 passed;
  broker/gateway/launchers 106 passed; trials/release/checkpoint/exec 76
  passed; `test_eng_invb_dispatch.py` 10 passed with close1 file (20).
- Live probes: 27 passed. Entry/EVID probes: all green
  (`/tmp/close1_probes.py`, `/tmp/close1_probe2.py`, kept out of repo).
- Ruff: not installed in this venv; no configured gate (matches prior
  lanes). No new config added.
- Full integrated suite `tests/ reviews/probes/`: PENDING (running at
  report time; result to be appended before handoff).
- Files I must not touch were not touched: `docs/design/*`,
  `reports/ENGINEERING-REVIEW.md`, `VERIFICATION.md`, `DECISIONS.md`,
  `IMPLEMENTATION-STATUS.md`, `reviews/REQUEST.md`,
  `REFINEMENT-ROADMAP.md`, other lanes' branches.

## Coordinator instructions (explicit requests)

1. In `reports/ENGINEERING-REVIEW.md`: mark fixed+verified at `c53049a` —
   INVA-03, INVA-04, INVA-05, INVA-08, INVB-13, INVC-12-`check_use`,
   INVC-12-`doubles`; record INVB-11 justification (admission refusal +
   test-pinned launcher mechanism); close INVC-13/14, entry-points,
   tests/probes, EVID-01/02 per the evidence above.
2. In `reports/VERIFICATION.md`: append the CLOSE-1 full-suite section
   (command + count from this lane's final run).
3. Carryover left open deliberately: INVA-06/07/09 (outside CLOSE-1 items);
   keyword-DSN fixtures in `test_broker_dbos.py`, `test_r03_flow.py`,
   `test_r01_recovery.py` (outside edit scope; canonical URL DSN per
   D-ENG-05 covers them).
