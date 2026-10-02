# T7 validation / recovery / adversarial checks — task report

- Base: `df96e39` (branch `codex/task-s0-validate` start, per assignment).
- Tip: this commit (see `git log` on the branch).
- Worktree: `/home/ubuntu/AI/Agent-Society-v2-s0-validate` only. No other checkout touched.
- Env: worktree venv via `uv sync --extra test`; PostgreSQL 16.15 local socket;
  `SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_t0validate?host=/var/run/postgresql`;
  restore-fence DB `settlement_restore_probe` (used ONLY for restore tests).

## Owned paths (only these)

- `scripts/checkpoint.py` (new, REC-1/REC-2)
- `scripts/restore.py` (new, REC-3/REC-4)
- `tests/test_adv_budget.py`, `tests/test_adv_broker.py`,
  `tests/test_adv_isolation.py` (new, §15 map)
- `tests/test_rec_checkpoint.py`, `tests/test_rec_restore.py` (new, REC-1..4)
- This report.

Shared contracts, `src/`, `migrations/`, existing tests, `pyproject.toml`,
`uv.lock`, `reports/PLAN.md`, `templates/`, `experiments/` untouched
(experiments were RUN, not modified). One defect found was recorded, not fixed
(it needs a coordinator-approved store transition outside owned paths).

## Outcomes

- Full suite: **235 passed** (` settlement_t0validate` DSN) plus 2 pre-existing
  `test_broker_dbos.py` errors that assume the `settlement_t1broker` DSN name;
  that file passes **3/3** under its own DSN. A `test_launchers` timeout test
  failed once under full-suite load and passes alone (unreproduced flake, §5).
- New coverage: 33 tests (7 budget/state-machine, 9 broker crash/recovery,
  10 isolation/evaluator/quarantine, 7 checkpoint/restore).
- `scripts/checkpoint.py` writes pg_dump custom-format (peer-auth socket,
  password DSNs refused, no credential on any command line), `manifest.json`
  (source commit SHA, `schema_migrations` rows, control epochs, per-table row
  counts, artifact sha256+size manifest), and a deterministic `artifacts.tar`;
  fsyncs outputs; prints digests.
- `scripts/restore.py` refuses source-DB-name and source-artifact-root targets
  and non-fresh targets, replays via pg_restore, verifies migrations, control
  epochs, row counts, and every artifact digest; any mismatch exits nonzero
  with the mismatch list (never partial success). Unfinished operations are
  listed for REC-4 reconciliation, never replayed.
- Independent §11 reproduction (`/tmp/repro_abc.py`, not committed) over the
  same 8 fault tasks and `ScriptedDouble` competence shape as T5: panel-C
  observed-gain 3–1, panel-B observed-gain 2–1, transfer arms inconclusive,
  3 broker invocations + 2 abstentions, matched caps equal, every cell
  `simulated=True`. Matches T5 verdicts.

## Per-check evidence (§16 split)

| # | Check | Exact command | Rev | Real vs fake | Outcome | Evidence |
|---|---|---|---|---|---|---|
| 1 | Budget conservation incl. subdivided children | `pytest tests/test_adv_budget.py::test_budget_state_machine` | tip | real PG16 `settlement_t0validate` | pass (12 Hypothesis examples, invariant holds) | test file |
| 2 | Last-units race | `pytest tests/test_adv_budget.py::test_last_units_race` | tip | real PG, 8 threads × 5 on 10 units | 2 applied / 6 insufficient, balances (10,10,0) | test file |
| 3 | Settle-once, no duplicate spend/fulfillment | `...::test_settle_once_and_no_duplicate_spend`, `...::test_fulfill_once_per_revision` | tip | real PG | pass | test file |
| 4 | Journal replay consistency | `...::test_journal_replay_consistency` | tip | real PG | same-payload `already_applied`, different-payload `ConflictPayload`, reserved unchanged | test file |
| 5 | Outbox exactly-once delivery effects | `...::test_outbox_exactly_once_delivery_effects` | tip | real PG | claim idempotent read; double `record_delivery` → `already_applied`; scan drains | test file |
| 6 | Epoch monotonicity, cursor completeness | `...::test_epoch_monotonicity_and_cursor` | tip | real PG | ordered unique epochs; 3-row pages equal full scan | test file |
| 7 | Broker death before advance | `pytest tests/test_adv_broker.py::test_death_before_advance_redispatches_exactly_once` | tip | real PG + real LocalLauncher | `dispatch_pending` redispatches once, spawns=1 | test file |
| 8 | Broker death after send | `...::test_death_after_send_never_resends`, `...::test_kill_restart_after_send_reconciles_without_resend` | tip | real PG + real launcher; driver script under `/tmp` (uncommitted), committed tests use in-process `_crash_after_send` hook | no resend; `dispatch_pending`/reconcile admits receipt, outbox drains, spawns=1 | test file |
| 9 | Kill/restart before advance (subprocess) | `...::test_kill_restart_before_advance_dispatches_once` | tip | real subprocess driver (`/tmp`, real DSN) | prepared → observed, exactly one send | test file |
| 10 | Duplicate/conflicting receipt after commit | `...::test_duplicate_receipt_after_commit_settles_once` | tip | real PG | conflict preserved, `reconcile_state=conflict`, consumed unchanged | test file |
| 11 | Lost response | `...::test_lost_response_retains_exposure_and_never_resends` | tip | real PG + scripted lost launcher | `unresolved`, exposure retained, 1 send, reconcile → `unresolved-liability` | test file |
| 12 | Stale worker lease | `...::test_stale_worker_completion_refused_observation_open` | tip | real PG | stale dispatch/completion refused, observation stays open | test file |
| 13 | Cancel while dispatched + late receipt | `...::test_cancel_while_dispatched_keeps_charges_late_receipt_admitted` | tip | real PG + real launcher | confirmed cancel, late receipt admitted, observed | test file |
| 14 | Unknown effect / unsupported runtime | `pytest tests/test_adv_isolation.py::test_unknown_effect_rejected`, `...::test_unsupported_runtime_never_falls_back` | tip | real PG + real RunscLauncher probe | `invalid_input`, no op row; `incompatible-profile`, no send, no fallback | test file |
| 15 | Worker credential reachability | `...::test_worker_credential_reachability` | tip | real PG + real subprocess worker, live env Poisoned with fake secrets | worker env == PATH/LANG/SETTLEMENT_OPERATION only; secret values absent | test file |
| 16 | Over-quota output capped | `...::test_over_quota_output_capped` | tip | real PG + real worker writing 200 KB, cap 1024 | `truncated=True`, stdout ≤ 1024 | test file |
| 17 | Evaluator always-pass swap | `...::test_evaluator_always_pass_swap_refused` | tip | real PG | package-pin and protocol-pin refusals; ghost invocation refused | test file |
| 18 | Hidden-answer leakage | `...::test_hidden_answers_withheld_from_candidate` | tip | real PG, public APIs | candidate scope raises `Unauthorized`; evaluator sees answers; candidate view clean | test file |
| 19 | Quarantine end to end | `...::test_quarantine_effective_for_pinned_attempt` | tip | real PG, public `run.check_eligibility` + `capabilities.route` | pinned attempt ineligible; router abstains | test file |
| 20 | Artifact publish/retire race | `...::test_artifact_publish_retire_reference_race` | tip | real PG + real fs | referenced retire → kept bytes, unavailable for new refs; unref → removed | test file |
| 21 | Retraction vs release/fulfillment | `...::test_retraction_races_release_and_fulfillment` | tip | real PG | support flips; stale-epoch use/fulfill refused (`missing_evidence`) | test file |
| 22 | Candidate cannot mint receipt | `...::test_candidate_cannot_mint_receipt` | tip | real PG | submission stored, `receipts` stays empty | test file |
| 23 | Checkpoint writes recovery set | `pytest tests/test_rec_checkpoint.py` | tip | real PG16 + `pg_dump` 16 + real fs | dump/manifest/tar verified; digests re-hash; password DSN refused | test file |
| 24 | Restore verifies into fence | `pytest tests/test_rec_restore.py` (fence `settlement_restore_probe`) | tip | real `pg_restore` 16 into fenced DB + dir | roundtrip ok; source/non-fresh refused; tampered manifest → `ok:false` + digest mismatch; pre-effect restore shows pre-effect fence while primary converges | test file |
| 25 | Simulated §11 A/B/C reproduction | `.venv/bin/python /tmp/repro_abc.py $SETTLEMENT_TEST_DSN` | tip | SIMULATED (ScriptedDouble) + real PG + real local-process sandbox | panel-C observed-gain 3–1; panel-B observed-gain 2–1; transfers inconclusive; all cells `simulated=True` | §2 |
| 26 | Live A/B/C | `uv run python experiments/run_live_abc.py --dsn … --allocation live-abc --artifacts-root …` | tip | UNVERIFIED (no endpoint/grant) | exit 2, live-blocker message | §4 |
| 27 | gVisor isolation | `probe_gvisor()` via `settlement.exec_profile` | tip | UNVERIFIED (no runsc/docker host) | `available=False`, explicit `IncompatibleVersion` path only | §4 |
| 28 | PG18 deployment | `SHOW server_version` on test host | tip | UNVERIFIED (host runs PG 16.15) | SQL uses no PG18-only features per T2, but PG18 deployment itself unrun | §4 |

## Defects found (repro + requirement IDs; code left untouched)

- **T7-F01 (EFF-2/EFF-5 boundary, limitation):** an operation whose advance
  committed but whose launcher died *before* the actual send parks as
  `unresolved-liability` with exposure retained, and has no redispatch path:
  `reconcile()` never consults `launcher.prior_send()`, and there is no
  store transition back to `prepared`. Repro:
  `test_death_after_advance_before_send_parks_unresolved` (advance commits,
  `FlakyLauncher` raises, run dir stays empty, `reconcile` →
  `unresolved-liability`). Parking is EFF-5-conformant, but the §15 "broker
  dies before send" case only converges when death precedes advance; a
  coordinator-approved transition (or a `prior_send`-aware reconcile rule) is
  needed for the advanced-but-unsent case. Recorded, not fixed: the fix lies
  in `src/settlement/*` outside owned paths.
- **Flake (not a defect, recorded):** `tests/test_launchers.py::
  test_timeout_kills_whole_process_group` failed once under the 4-minute
  full-suite load and passes alone (`1 passed` on re-run). T6 reported a
  similar unreproduced flake. No action taken.

## Verified contract clarifications (no change needed)

`claim_outbox` is an idempotent read (repeat claim returns `applied` with
identical payload, not `already_applied`); `dispatch_operation` never resends
or reconciles a non-`prepared` op (recovery is `reconcile` /
`dispatch_pending` / `heartbeat(repair_due=True)` / `recover`); ownership
checks bind only attempt-linked ops (T2-R04 seam); second settle of a settled
reservation returns `already_applied`; releasing a settled reservation is
refused `invalid_input` ("already settled"); fulfillment needs a completed
attempt and a second fulfill is refused ("already fulfilled"); retirement
makes an artifact unavailable for new references while GC keeps referenced
bytes (ART-3 as designed).

## Explicitly unverified (§16 gates with blockers)

- **Live-gateway checks (IF-5gw model inference, live A/B/C):** no endpoint or
  grant exists. `run_live_abc.py` exits 2 with
  `live A/B/C blocked: set SETTLEMENT_GATEWAY_ENDPOINT, SETTLEMENT_GATEWAY_KEY,
  and SETTLEMENT_GRANT_UNITS (monetary grant cap)`; zero `SETTLEMENT_GATEWAY*`
  vars are set in this environment.
- **gVisor isolation check:** `runsc`/`docker` are absent on this host
  (`probe_gvisor` → `available=False`); only the explicit
  `IncompatibleVersion` path is exercised (check 14).
- **PG18 deployment check:** test host runs PostgreSQL 16.15; migrations use
  no PG18-only features, but deployment against PG18 was not run.
- **DBOS executor-kill mid-workflow** remains as T3 reported (recorded-result
  dedup tested; live executor kill not performed here).
