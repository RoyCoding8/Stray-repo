# R1b — R01-003 / R01-004 / R01-S02 fulfillment and dispatch-fencing fixes

Branch: `codex/review01-r01-admit` (built on `cbc2770`, R1a intact).
Owned paths only: `src/settlement/store.py`, `src/settlement/broker.py`,
`src/settlement/steward.py` (lease sharing + fulfillment delegation),
`tests/test_r01_fulfill.py` (+ this report).

## What changed

R01-003 (`store.fulfill_investigation`, TX-6/RUN-4): one transition now
validates attempt identity first (`attempt.investigation_id` must equal the
fulfilled investigation; unrelated completed attempts at the same revision
are refused), then mandatory revision, completion authority, evidence epoch,
and obligations pins. Every authority/identity field is mandatory: a missing
`attempt_id`, `ownership_generation`, `revision`, `authority_version`,
`evidence_epoch`, or `obligations` is refused, and a changed obligations
snapshot is `STALE_REVISION`. Duplicate fulfillment for the revision stays
refused. `store.fulfill_investigation_override` is the only bypass: it needs
an explicit `operator` + `override_reason`, emits a distinct
`commitment.fulfilled_override` event, and is refused without attribution.
`steward.fulfill_investigation[_override]` stay thin delegates.

R01-004 (`store.advance_dispatch`/`reset_dispatch`, `broker`, EFF-2/EFF-5):
admission stamps a durable `_dispatch_generation` (+1 per admission) and
`_admitted_launcher` into the operation payload — no schema change. The
replay branch re-runs the full R1a admission checks, so a second
`_advance` is a genuine revalidation. Every send path (`_send_model`,
`_send_sandbox`, `_run_inline`) now admits, revalidates just before the
send, and backs off without sending on anything but a current replay;
`ALREADY_APPLIED` is never send permission on any path. `_finish_send`
compares the admitted generation with the live one and records a fenced
`unknown` receipt (exposure retained, never `observed`) when reset or
re-admission superseded it. `broker.reconcile` no longer resets
`dispatching` to `prepared` on negative launcher evidence: uncertain
history — including a fresh empty run directory and repeated recoveries —
stays `unresolved-liability`. `store.reset_dispatch` remains as the
explicit operator path; it accepts an optional `expected_generation`
(`STALE_REVISION` on mismatch) and always bumps the generation, fencing
in-flight prior senders. The admitted generation travels to launchers on
`BrokerOp.dispatch_generation`.

R01-001 follow-up: the replay gate covers `_send_sandbox`/`_run_inline`;
`test_concurrent_dispatch_spawns_exactly_once` still passes (in the full
suite below).

R01-S02 (`steward._lease_terms`): one TTL/expiry policy (default
`_LEASE_DEFAULT_TTL_MS`, positivity validation, `expires_at` computation)
shared by `issue_lease` and `reacquire_lease`; each keeps its distinct
eligibility checks and events.

## Test results (real PostgreSQL 16)

`tests/test_r01_fulfill.py`: 21 passed. Red-first: with `src/` stashed,
13 of 14 selected new tests fail (the 14th, stale-authority refusal,
already held pre-fix); the pause tests fail there for lack of the
revalidation seam.

Full `tests/` on `settlement_r01admit`: 256 passed, 7 failed — every
failure asserts behavior this assignment explicitly supersedes (see
contract requests). `test_broker_dbos.py` + `test_s0_gateway.py`: 19
passed on alias DB `settlement_t1broker` (pre-existing environment
constraint, as in R1a).

Ruff: repo is not ruff-clean at base (42 hits in the three owned src
files); this change nets -2 there. The new test file carries only the
4 `UP017` hits that match the surrounding `timezone.utc` idiom.

## Contract requests (other owners' files, not touched)

- `tests/test_r01_authority.py::test_r01_001_replayed_advance_sends_zero_gateway`:
  its mock counts exactly 2 `_advance` calls; send paths now admit +
  revalidate (2 calls per dispatch). Keep its intent by answering
  `APPLIED` once and `ALREADY_APPLIED` thereafter and asserting exactly
  one send.
- `tests/test_state_investigations.py` (2 tests),
  `tests/test_adv_budget.py::test_fulfill_once_per_revision`,
  `tests/test_s2_evidence.py::test_stale_admissibility_loses_against_fulfillment_order`:
  expect `APPLIED` for payloads the new contract refuses. Migrate to the
  full fulfill payload or to `fulfill_investigation_override` with an
  explicit operator + reason.
- `tests/test_reconcile_reset.py::test_advanced_but_unsent_resets_and_redispatches_once`,
  `tests/test_agenda_repair.py::test_repair_scan_converges_advanced_unsent`
  (+ `scripts/scheduler.py`, agenda repair scan): they rely on
  reconcile auto-reset to `prepared` plus resend. Use explicit
  `store.reset_dispatch` with `expected_generation` and design an
  explicit scheduler re-dispatch; reconcile itself stays non-sendable.
- `src/settlement/launcher_local.py`: make the filesystem claim and
  `prove_never_sent` generation-aware using the now-threaded
  `BrokerOp.dispatch_generation`, so a pause *inside* the launcher claim
  is also fenced (broker-side checks cover everything before it).
- Standing R1a notes unchanged: `reviews/probes/test_review_01.py`
  probe 2 stays superseded (probes 1/3/4 untouched); `run.py` composition
  authority is still preflight-only.

## Invalidated review probes

Review answer 2 ("never-sent reset with stable run directory") described
the removed behavior: an empty directory, intact or recreated, no longer
returns anything to `prepared`. `test_reconcile_reset.py`'s
`needs-prepare` case and the scheduler repair case above encode the old
proof and are superseded by the `unresolved-liability` tests here.

## Open risks

- A dispatcher paused inside `LocalLauncher.dispatch` (after the
  broker's final revalidation) can still spawn under a superseded
  admission; the post-send fence records `unknown`/`unresolved` but
  cannot un-spawn. Closes with the launcher-side claim above.
- A fenced in-flight receipt landing after a newer admission marks the
  operation `unresolved` (safe direction; exposure retained) rather than
  attributing per generation.
- `test_launchers.py::test_timeout_kills_whole_process_group`
  (untouched path, direct launcher call) flakes in heavy custom file
  orderings via its `pgrep -f "sleep 30"` orphan check; green in
  isolation and in the default-order full suite.
- Fake gateways/adapters stand in for provider semantics; journal grows
  one row per admit and one per revalidation by design (unique advance
  identity, R1a convention).
