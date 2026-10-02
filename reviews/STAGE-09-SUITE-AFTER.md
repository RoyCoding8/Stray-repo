# Stage 09 suite, measured at this tip

Branch `codex/implementation-investigation-learning-02`, at `c810c7e`. All 50
files of the 129-row failure census are measured here. This supersedes the
previous revision of this document, which covered 49 of them and left
`tests/test_s09_swe_experiment.py` unmeasured.

Runs are per-group under `scripts/run_bounded.py`, which blocks in `wait` and
returns the child's own status. A timeout is `124` and says "this is not a
pass" in as many words. No group in this measurement polled.

## 1. The number

**53 failed across 29 of the 50 census files.** 618 passed, 1 skipped.

The void figures stay void. `135 failed / 3701 passed` predates N-415.
`127 failed, 3964 passed, 2 errors in 3:54:07` is a whole-suite run, not this
50-file subset, so it is not comparable. Neither is used.

Per file, failing rows only; every file not listed is green:

| Failed | File |
|---|---|
| 7 | `tests/test_invr3_export.py` |
| 5 | `tests/test_ec02ad_verif.py` |
| 4 | `tests/test_bdr01_host_boundary.py` |
| 4 | `tests/test_gateway_usage_unknown.py` |
| 4 | `tests/test_invc3_export.py` |
| 2 | `tests/test_ag01_experiment.py` |
| 2 | `tests/test_broker_prepare.py` |
| 2 | `tests/test_conftest_isolation.py` |
| 2 | `tests/test_dev02_context.py` |
| 2 | `tests/test_m4_clean_baseline.py` |
| 1 | `tests/test_agenda_repair.py` |
| 1 | `tests/test_alee_learner.py` |
| 1 | `tests/test_bacq_method.py` |
| 1 | `tests/test_broker_dbos.py` |
| 1 | `tests/test_dev01_compare.py` |
| 1 | `tests/test_eacq_repair.py` |
| 1 | `tests/test_eng_invb_dispatch.py` |
| 1 | `tests/test_inva_recovery.py` |
| 1 | `tests/test_invc3_study.py` |
| 1 | `tests/test_invd2_settle.py` |
| 1 | `tests/test_invr1_study_entry.py` |
| 1 | `tests/test_m1_shared_executor.py` |
| 1 | `tests/test_r01_deadline_ui.py` |
| 1 | `tests/test_r02_explearn.py` |
| 1 | `tests/test_rpr01_db.py` |
| 1 | `tests/test_rpr13_endtoend.py` |
| 1 | `tests/test_s09_store_cleanup.py` |
| 1 | `tests/test_steward_leases.py` |
| 1 | `tests/test_team_live.py` |

**Nothing is excluded.** Every one of the 50 is measured.

## 2. The census comparison

The census table parses to **exactly 129 rows across 50 files, with no
duplicate `file::test` pair**. That matters, because the previous revision of
this document claimed an 8-row excess and attributed it to "a naming artefact
in the census table". There is no artefact. The join is exact:

| | Rows |
|---|---|
| Closed — a fix landed | 84 |
| Still open | 45 |
| **Total** | **129** |

The previous revision said 83 closed and excluded one row as "not measured".
That row, `test_s09_swe_experiment.py::test_paired_comparisons_pair_the_same_instance_across_representations`,
is measured here and **passes** (1 passed in 2.38s), which is what promotes
the closed count from 83 to 84.

**Zero census rows were newly broken.** The nine tests the previous revision
called "newly broken" are all absent from the 129, so they are not rows that
moved — they are rows that were never there. Section 3 separates them.

## 3. Newly broken: 9 tests, 1 defect, already repaired

All nine are absent from the census, verified by joining each against the
parsed 129. They split cleanly:

**Genuinely introduced by this stage — 3 tests, one defect, repaired at
`362d144`.** `tests/test_dev01_ops.py`:
`test_deterministic_episode_passes_end_to_end`,
`test_record_carries_source_revision`,
`test_fixture_record_pins_effective_caps_and_bundle`.

`experiments/run_use.py` anchored `sys.path` to `experiments/` and `src/` but
not to the worktree root, while all three imports it performs inside `main()`
are `experiments.*`. Run as a script — which is how `run_dev_episode.py`
invokes it, `subprocess.run` with no `env` and no `cwd` — each raised
`ModuleNotFoundError: No module named 'experiments'` and the process exited
3. The tests saw `assert 3 == 0`. The repair adds `str(WORKTREE)` to the
anchor tuple. **Re-verified at this tip: `tests/test_dev01_ops.py` is 13
passed.** These three are counted as closed, not open.

**Not newly broken — 6 tests, 0 defects.** Each is a sibling in a file the
census already carries, failing for a reason its siblings already failed:

| Test | File | Why it is not new |
|---|---|---|
| `test_export_emits_doubles_transitions` | `test_invc3_export.py` | same `_fresh_db` prefix assertion as its 3 siblings |
| `test_replay_refuses_mismatches_from_export` | `test_invc3_export.py` | same |
| `test_cli_export_and_offline_replay` | `test_invc3_export.py` | same |
| `test_acquired_execution_uses_broker_profile` | `test_bdr01_host_boundary.py` | same `query_trace` replay difference as its sibling |
| `test_broker_query_count_survives_replay` | `test_bdr01_host_boundary.py` | same |
| `test_cap_sheet_derived_and_billing_split_and_no_replenish` | `test_invr1_study_entry.py` | file's other row is a census row; the ceiling assertion went stale |

These six are counted once, under the per-file table in section 1. They are
listed here only so the 9 reconciles against the previous revision.

## 4. Defects found and root-caused this run

Six real defects, each reproduced in isolation. None was named in the brief's
list of what to hunt for.

**4.1 `tests/conftest_isolation.py:_pin_kind` does not detect
`.startswith()`.** The scan reports `no assertion pins this name` for
`inv_c3_export`, `inv_c3_study` and `inv_r3_export`, so the harness redirects
them and derives `s09iso_<token>_inv_c3_export`.
`tests/test_invc3_export.py:33` asserts
`dsn.split("dbname=")[1].split()[0].startswith("inv_c3_")`, which no derived
name can ever satisfy. All 4 tests in that file fail in 0.26s on that
assertion, before any test body runs. The detector handles `==` and `in` only
(`conftest_isolation.py:211-221`); the `startswith` case is unreachable by
construction. This is the same `startswith` shape the harness's own docstring
at `conftest_isolation.py:194-205` reasons about for other names — the rule
was written for `==` and `in` and never extended. *Owner:* isolation harness.
*Smallest change:* treat an `ast.Call` to `.startswith`/`.endswith` with the
name as receiver as pinned, and let `SuitePlan.env_for` report the blocker
rather than redirecting into a name that cannot satisfy it.

**4.2 `broker.ensure_operation` refuses `retries != 0`, so its own exposure
schedule is unreachable.** `src/settlement/broker.py:263-269` returns
`INVALID_INPUT` for any non-zero `retries` with "use distinct operation
identities" (added in `59a10df`). But `exposure_schedule` at `:137-157` still
multiplies by `retries + 1`, and `tests/test_broker_prepare.py` has two tests
asserting exactly that scaling — `test_model_exposure_scales_with_retries`
(`KeyError: 'exposure'`) and `test_sandbox_prepare_reserves_hard_ceiling`
(`invalid_input` instead of `applied`). The refusal and the schedule are two
readings of the same field, and only one survived. *Owner:* broker prepare.
*Smallest change:* decide whether retry scaling is live; if it is not, delete
the `retries` parameter from `exposure_schedule` and its two tests, since a
ceiling nothing can reach is not a bound.

**4.3 `from_settings` builds an adapter that can never `infer`.**
`src/settlement/gateway_http.py:484-502` defaults `route_mode="free"`, and
`_pre_dispatch_route_error` at `:765-770` refuses every dispatch with
"expected free route is required" when `expected_route is None` and the mode
is not `"paid"`. Reproduced directly:

```
RESULT TYPE: GatewayError
kind= GatewayErrorKind.PROTOCOL message= expected free route is required
route_error= GatewayRouteError.EXPECTED_ROUTE
```

`tests/test_eng_invb_dispatch.py:184` surfaces this as
`AttributeError: 'GatewayError' object has no attribute 'text'` — `infer`
returned an error where a `ModelResponse` was expected, and the test reads
`.text` off it. The exception names the wrong thing. *Owner:* gateway HTTP.
*Smallest change:* either have `from_settings` default `route_mode="paid"`, or
have it require an `expected_route` rather than constructing one that refuses
at first use.

**4.4 `query_trace` differs between a first call and its replay.**
`experiments/ad01/method_exec.py:1131` sets `result["query_trace"] = None`
when a durable receipt replays a settled operation, while the first execution
returns the observed list. `f1d8ada` made that change deliberately — the
docstring says an absent walk is not an empty walk. It breaks the two
`test_bdr01_host_boundary.py` replay-idempotence assertions
(`{'query_trace': None} != {'query_trace': []}`), which predate it. This is a
deliberate semantic change meeting an older test, not a regression in either
direction. *Owner:* whoever owns the use-phase replay contract. *Smallest
change:* decide which claim is wanted — idempotent replay, or an honest
absent trace — and move the other; they cannot both hold.

**4.5 `test_invc3_export.py`'s four failures are 4.1**, not three separate
assertion failures. Counting them separately would triple the apparent size of
one cause.

**4.6 `test_invr1_study_entry.py:473` pins a ceiling that `02cdc83` made
derived.** The test asserts `sheet["study"]["max_witness_queries"] == 960`;
`scripts/inv01_study.py:694` now computes
`acquisition + use + margin` and yields 2106. `02cdc83` ("A budget with no
headroom is a race, and the control arm lost it") is the change that made it
derived, and it did not update this assertion. *Owner:* INV-R1 study entry.
*Smallest change:* one line, assert the derived relation rather than the
literal.

## 5. Environmental, not defects

**`tests/test_ec02ad_verif.py`, all 5 rows — environmental.** The file
hardcodes two absolute paths to a worktree that no longer exists:
`AD01_ROOT` and `VERIF_ROOT` at `tests/test_ec02ad_verif.py:923` and `:1023`,
both `/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif`. `.worktrees/` is
empty and `git worktree list` does not name it. The failures are
`FileNotFoundError` on that path, `git clone` exiting 128 with "repository
does not exist", and "original probe file missing from tip". The pinned
`VERIF_TIP = "3d697b8"` still resolves as a commit, so the intent is intact
and only the location is gone. *Smallest change:* point both constants at a
live checkout, or derive them, and the battery becomes runnable. These five
will not pass on any machine until that is done — they are not measuring
anything about the product.

**`tests/test_invr3_export.py` is no longer environmental — it was.** The
census recorded all 10 rows as `OperationalError: database "inv_r3_export"
does not exist`. The isolation harness now redirects that seam, so the store
exists and 7 tests reach their real assertions, where all 7 fail at
`tests/test_invr3_export.py:193` on `assert 'refused' == 'incumbent'`. The
reason is read directly from the record:

```
selected= refused  status= refused
fallback_reason= use ran with no policy: the method identity must come from
an admitted policy action
```

`run_use` is called with `policy=None` and an empty repertoire. Under
`trajectory._use_policy_action` (`:1379`) a missing policy raises
`_UsePolicyRefused`, which `run_use` turns into a refusal record whose
`selected` is the string `"refused"` (`:1483`). The test expects the
incumbent, which is what the empty repertoire used to produce. The refusal is
working as designed; the design and the test disagree about what an empty
repertoire means. *Owner:* INV-R3 export contract. *Smallest change:* one
decision — whether an empty repertoire falls back to the incumbent or refuses
— then update the one side that is wrong. Six other tests follow from it.

**10 rows are gateway-credential-gated**, in
`test_inva_recovery.py`, `test_invc3_study.py`, `test_invd2_settle.py`,
`test_m4_clean_baseline.py` and `test_invc3_export.py`: all
`ValueError: model route preflight refused: gateway credentials are not
configured`, raised at `scripts/invl02_live.py:192`. Neither
`SETTLEMENT_GATEWAY_KEY` nor `SETTLEMENT_GATEWAY_ENDPOINT` is set in this
environment. These measure nothing until credentials exist.

**`tests/test_conftest_isolation.py`, 2 rows — a scoped-scan artifact.** Its
two failures assert on the *real* suite's seam list
(`assert 0 >= 20`, `assert 'INV_R3_DSN' in {}`). Measured against the real
`tests/` scan the file is **14 passed**. The scoped log is kept as
`.s09suite/g17.log.scoped-ARTIFACT` and is not a product failure.

## 6. Still open, with an owner

**SUPERSEDED 2026-09-29.** Twelve lanes worked this table. Nine of the
eleven rows are closed and the table below says how; two are not closed
and say why. The ordering this table used -- "smallest change" -- was
wrong in at least one place, and that is recorded rather than quietly
corrected: the `_pin_kind` prescription would have pointed a
**truncating** test at a database another battery also truncates.

| Rows | File | Cause | Status |
|---|---|---|---|
| 7 | `test_invr3_export.py` | empty repertoire refuses instead of falling back | **DONE** `c544cc5`. Decided: refuse. `77001fc` made the method identity something only an admitted policy action can supply and deleted the incumbent path an empty repertoire reached. Fixing the test moved 6 rows and exposed the 7th as a real defect — `verify_byte_chain` read every non-incumbent record as one that *executed*, so a refused use phase was reported `use-without-retained`. Fixed at `records.py`. |
| 5 | `test_ec02ad_verif.py` | hardcoded dead worktree path | **DONE, and only 3 of the 5 were this.** `ef9d9e8`. One was `assert ... or True` — unfailable, it passed against a worktree that did not exist. The other two were a different cause: the CLI refuses to seed without agenda authority, so the run died before it could be SIGKILLed. A fourth thing surfaced under those: a filter on `claimed_ops`, deleted in `ff65b2a`, so the assertion was arithmetic on a fabricated list. |
| 4 | `test_invc3_export.py` | `startswith` seam not detected | **3 of 4 DONE, prescription STRUCK** `b35e441`. Teaching `_pin_kind` about `.startswith` would have marked the seam pinned, redirecting a **truncating** test at the shared `inv_c3_export`. The old guard also *admitted* `inv_c3_study` and `inv_c3_live`, both present on this cluster. Replaced with a refusal of the three shared stores by name. `_pin_kind` left unchanged, after measuring that a general rule would wrongly pin 3 working refusal guards. |
| 4 | `test_bdr01_host_boundary.py` | replay `query_trace` semantics | **DONE** `821b92f`. Honest absence, not idempotent replay. The receipt does not carry the walk, so no replay count can reconstruct it. The adversarial argument is in `reviews/STAGE-09-OPEN-CAUSES.md`: under replay the adversary controls the **first** run, so the check would authenticate a self-consistent story rather than a true one. 2 of the 4 rows were this; the other 2 were `policy=None` asserting on a refusal record. |
| 4 | `test_gateway_usage_unknown.py` | `outcome` is `failure`, test wants `unknown` | **DONE** `821b92f`. The product is right: `failure` came from `59a10df`, and the tests predate it. Measured, not assumed: both cases, both APIs, `(consumed, reserved) == (0, 9)`, `actual_cost` unset. |
| 2 | `test_ag01_experiment.py` | N-74 signature: dispatch parks, never settles | **NOT ADDRESSED, and not this stage's.** Pre-existing. `agenda01` makes no reference to any path this stage touched and `git log --since` on that directory is empty for this session. Carried forward, not claimed. |
| 2 | `test_broker_prepare.py` | retry-scaling gate | **DONE** `821b92f`. Retry scaling is dead code: every live caller passes `RETRIES = 0`, and the one that means to retry uses distinct operation identities and never passes `retries` to `ensure_operation`. `test_broker_route_recovery.py:513` already asserts the refusal. The tests guarded a removed feature. |
| 2 | `test_conftest_isolation.py` | scoped-scan artifact | **NO ACTION** — green on the real scan, as this row said. |
| 2 | `test_dev02_context.py` | resume working-state, `assert set() >= {...}` | **DONE** `0ebf0c8`, and **this row's premise was wrong.** The source asserts a real set relation; the `set()` in the traceback was the *runtime* left operand, and `set() >= {x}` is `False`. Actual cause: both tests called `prepare_operation`/`advance_dispatch` and **discarded the results**. Neither passed `allocation_id`, so `_attempt_allocation` raised `ConflictPayload` and the operation was never inserted. Both rows asserted against a fixture that did not exist. |
| 2 | `test_m4_clean_baseline.py` | gateway credentials | **NOT FIXED, and ``needs credentials`` is wrong.** The credential is present and `preflight_route` succeeds. The cause is that `_live_baseline` never calls `_load_live_environment`, so `Settings.from_env` reads an empty environ. Fixing it would make a *test* spend real budget through a live proxy at `localhost:4000`. **That is a coordinator decision, not a repair.** The right shape is a recording double: `run_output` takes an injected `gateway`, `run_output_live` does not. |
| 1 | `test_invr1_study_entry.py` | stale literal ceiling | **DONE** `e34bbba`, and it exposed a second row. The literal was the arithmetic of three run bugs, not a hand-set value. The relation is `>` not `>=` — a ceiling sized at exactly the sum the run spends falls back on the last phase. Separately, `67bb8c6` re-bound the compared value in `_v1_ensure_run` to a *derived* quantity, so the grant guard at `inv01_study.py:807` is unreachable and a raised `--agenda-authorized` returns 0, not 2. **That guard is dead; the deadline guard is not.** Owner: `scripts/inv01_study.py`. |

### The 18 single-row files

Closed: `test_invr2`, `test_eacq_repair`, `test_rpr13`, `test_rpr01_db`,
`test_eng_invb`, `test_invd2`, `test_inva`, `test_steward`,
`test_broker_dbos`, `test_agenda_repair`, `test_m1_shared`,
`test_team_live`, `test_bacq`, `test_alee`, `test_dev01`,
`test_r01`, `test_r02`, `test_s09_store_cleanup`.

**Two of those eighteen were not stale tests, and both are worth more than a
green row.** `test_team_live``: a fake carried the literal operation id
`op-x`, and a later identity fence filed it as an identity failure, so the
timeout path the test was written to exercise was **unreachable**. `test_s09_store_cleanup`:
its premise expired — it pinned the *absence* of a caller, and callers
appeared the next day. The tripwire was re-aimed at the caller set rather
than deleted.

**Still open from that group:** one row in `test_invc3_export.py` (the CLI
`use` passes no `--policy-source`, so `_use_policy` returns `None` and
`run_use` refuses — deliberate in `a60798d`, six days after the test).
What a policy-free use record should be is a design question, not a line in
a test file.

## 7. Measurement notes

**`test_s09_swe_experiment.py` is genuinely slow and must be chunked.** All
57 tests pass. It is on `run_bounded.py`'s slow-file list for a stated reason:
"compute-bound on in-process generated-source execs under a 100k-step alarm".
Two 15-test invocations both hit the 280s bound at 3 and 5 tests through.
Split into 12 chunks of 3-4, plus 3 for the one chunk that still overran,
every test completes inside the bound. The two timed-out invocations are kept
as `.s09suite/g21a.log` and `.s09suite/g22a.log`; their 3 and 5 partial dots
are re-measured by the chunks, so nothing is double-counted.

**`test_rpr13_endtoend.py` cannot run whole under the bound.** `g6` timed out
on it at 280s. Its 7 tests are measured individually across `g8`-`g11`
(6 passed, 1 failed) and the per-test ids account for all 7 — verified by set
difference against a fresh collection. Group 6's remaining two files,
`test_settle_actual.py` and `test_dev01_compare.py`, were re-measured
directly.

**Databases.** Every run used `S09ISO_TOKEN`, so the harness gave each run its
own store and dropped it. Three of this lane's runs were killed by the bound
and leaked their stores: tokens `a11ce001`, `a11ce002` and `d11ce007`, 38
databases each. All 114 were dropped by token; `probe_bp` from a manual
repro was dropped too. The 398 `s09iso_*` databases still on the server carry
other lanes' tokens and were left alone.

**The `r03flow_*` databases are 0 and that is correct**, fixed at `25b316f`.
The name `settlement_r03flow` cited in `reports/PLAN.md` does not exist on
the server. Full account in `.s09suite/INCIDENT-r03flow.md`.
