# R02 probe triage — task report

The review probes in `reviews/probes/test_review_02.py` mixed live R02
pins with white-box probes coupled to superseded R01 internals. Each was
triaged against the R02-001..012 contract and the maintained suite.

## Migrated (encoded the bug, fix verified, probe inverted)

- `test_http_usage_without_billing_becomes_zero_actual_cost`
  → `test_http_usage_without_billing_retains_unknown_cost`.
  R02-011. Now asserts `billed is False` and `actual_cost is None`.
- `test_slow_response_headers_outlive_total_deadline`
  → `test_slow_response_headers_respect_total_deadline`.
  R02-012. Now asserts TIMEOUT with `elapsed < 0.8` (observed 0.20 s).
- `test_release_scope_can_drop_a_supported_constraint`
  → `test_release_scope_cannot_drop_a_supported_constraint`.
  R02-009. Now asserts `broadening release refused`.
- `test_candidate_reads_protected_fixture_answers_from_repository`
  → `test_candidate_cannot_read_protected_fixture_answers`.
  R02-007. Oracle now fails every case with `FileNotFoundError` inside
  the isolated grader child; the probe asserts `passed == 0` plus the
  `fault_tasks` path in the failure text.
- `test_checkpoint_accepts_mutation_after_barrier_verification`
  (kept name; it pins plumbing, not the refusal).
  Now also mocks the pause-release step and asserts the current
  barrier → state → dump → verify → manifest → verify → release order.
  The real refusal path is pinned by the new committed test below.

## Retired (superseded internals, requirement pinned in-suite)

- `test_sender_ignores_changed_dispatch_generation`: identical scenario
  lives as `tests/test_r02_authority.py::test_stale_generation_sender_never_sends`
  against current internals. The probe's mocks can no longer reach the
  send path without a database.
- `test_fulfillment_accepts_copied_but_unproved_obligations`: the code
  now raises `MissingEvidence`, pinned in-suite by
  `tests/test_evidence_epoch.py` and `tests/test_r01_fulfill.py`.
- `test_delayed_success_is_not_consumed_by_workflow`: mocks return None
  from `wf_consume`, which the current workflow loop dereferences; the
  late-outcome requirement is pinned in-suite by
  `test_stale_worker_completion_refused_observation_open`,
  `test_cancel_while_dispatched_keeps_charges_late_receipt_admitted`
  and `test_lost_response_retains_exposure_and_never_resends`
  (all in `tests/test_adv_broker.py`).

## Added

- `tests/test_rec_checkpoint.py::test_checkpoint_refuses_and_releases_on_concurrent_write`:
  a concurrent admission between barrier and dump makes `run_checkpoint`
  `SystemExit` with `barrier violated`, and the dispatch pause is still
  released. Previously uncovered.

## Checks with outcomes

- `reviews/probes/test_review_02.py`: 6 passed.
- New checkpoint refusal test passes; full verification in the
  integration suite run.
