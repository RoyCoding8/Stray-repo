# Stage 09 failure census

Source: `/tmp/full-suite.log`, the first full run since N-415.
`127 failed, 3964 passed, 14 skipped, 2 xfailed, 2 errors, 4093 tests, 3:54:07`.

Nothing here was re-run. Every message below is quoted from the log. The
parser that produced the table is described in [Reproducing this](#reproducing-this).

The log's short-summary section names 127 `FAILED` and 2 `ERROR` lines, and the
report bodies above it carry the exception. Joining the two by test name yields
**129 rows across 50 files**, which reconciles exactly: 127 + 2.

Two things the log does not support, stated up front because they change how the
rest reads. First, exception class does not group these failures. 63 of the 129
are `AssertionError`, spread over 39 files, and no two of them mean the same
thing. Second, the previous estimate of "~64 across 40+ files, each its own
cause" is roughly right on the file count and wrong on the grouping: the 65
outside the two known files break into nine causes, not 65.

## The complete table

129 rows: file, test, terminal exception class, and one line of the actual
message.

| # | File | Test | Terminal exception | Verbatim message |
|---|---|---|---|---|
| 1 | `tests/test_ag01_experiment.py` | `test_positive_control_R` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w28v0_r_t0" in connection info string |
| 2 | `tests/test_ag01_experiment.py` | `test_positive_control_Q` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w28v0_q_t0" in connection info string |
| 3 | `tests/test_ag01_experiment.py` | `test_q_losing_world_reports_honestly` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w23v3_r_t0" in connection info string |
| 4 | `tests/test_ag01_experiment.py` | `test_cross_arm_discovery_replay_refused` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_arma_2798084" in connection info string |
| 5 | `tests/test_ag01_experiment.py` | `test_admit_without_grant_refused` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_nogrant_2798084" in connection info string |
| 6 | `tests/test_ag01_experiment.py` | `test_dispatch_without_launcher_awaits` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_nolaunch_2798084" in connection info string |
| 7 | `tests/test_ag01_experiment.py` | `test_rotated_grant_refuses_dispatch` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_revoke_2798084" in connection info string |
| 8 | `tests/test_ag01_experiment.py` | `test_branch_cap_reset_refused` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_cap_2798084" in connection info string |
| 9 | `tests/test_ag01_experiment.py` | `test_duplicate_outoforder_wakeup_single_effect` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_wake_2798084" in connection info string |
| 10 | `tests/test_ag01_experiment.py` | `test_stale_select_admit_refused` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_scratch_stale_2798084" in connection info string |
| 11 | `tests/test_ag01_experiment.py` | `test_resume_continues_saved_progress` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w25v1_r_t0" in connection info string |
| 12 | `tests/test_ag01_experiment.py` | `test_replay_verify_detects_tampering` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_dev00_r_t0" in connection info string |
| 13 | `tests/test_ag01_experiment.py` | `test_diagnostic_useful_continuation` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_dev02_r_t0" in connection info string |
| 14 | `tests/test_ag01_experiment.py` | `test_diagnostic_wasteful_split` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_dev03_r_t0" in connection info string |
| 15 | `tests/test_ag01_experiment.py` | `test_diagnostic_premature_stopping_cost` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_dev02_r_t0" in connection info string |
| 16 | `tests/test_ag01_experiment.py` | `test_agreement_durable_deterministic` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_dev00_r_t0" in connection info string |
| 17 | `tests/test_ag01_experiment.py` | `test_productless_probe_completes` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w11v3_r_t0" in connection info string |
| 18 | `tests/test_ag01_experiment.py` | `test_fence_admits_brain_selections` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_dev00_r_t0" in connection info string |
| 19 | `tests/test_ag01_experiment.py` | `test_checker_accepts_and_rejects` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w28v0_r_t0" in connection info string |
| 20 | `tests/test_ag01_experiment.py` | `test_checker_pair_membership` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w28v0_r_t0" in connection info string |
| 21 | `tests/test_ag01_experiment.py` | `test_prepared_operation_resumed_without_receipt` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w25v1_r_t0" in connection info string |
| 22 | `tests/test_ag01_experiment.py` | `test_duplicate_effect_decisions_charged` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w08v0_r_t0" in connection info string |
| 23 | `tests/test_ag01_experiment.py` | `test_receipt_timing_matches_declared_clock` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w25v1_r_t0" in connection info string |
| 24 | `tests/test_ag01_experiment.py` | `test_checker_rejects_gate_mutations` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/agenda01_w28v0_r_t0" in connection info string |
| 25 | `tests/test_invr3_export.py` | `test_correction_exports_both_requests_and_counts_both` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 26 | `tests/test_invr3_export.py` | `test_construction_repair_exports_both_attempts` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 27 | `tests/test_invr3_export.py` | `test_export_binds_delivered_request_and_pinned_identities` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 28 | `tests/test_invr3_export.py` | `test_valid_pilot_verifies_from_independent_identities` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 29 | `tests/test_invr3_export.py` | `test_missing_use_record_fails_for_named_reason` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 30 | `tests/test_invr3_export.py` | `test_missing_transition_pair_fails_for_named_reason` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 31 | `tests/test_invr3_export.py` | `test_duplicate_use_record_fails_for_named_reason` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 32 | `tests/test_invr3_export.py` | `test_altered_query_totals_fail_for_named_reason` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 33 | `tests/test_invr3_export.py` | `test_omitted_correction_receipt_fails_for_named_reason` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 34 | `tests/test_invr3_export.py` | `test_missing_study_trajectory_fails_for_named_reason` | `OperationalError` | psycopg.OperationalError: connection failed: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL: database "inv_r3_export" does not exist |
| 35 | `tests/test_coord02_m3_acquisition.py` | `test_acquire_reentry_reuses_campaign_operations[empty-response]` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-reentry-l-1-init-1 |
| 36 | `tests/test_coord02_m3_acquisition.py` | `test_acquire_rejects_changed_campaign_before_work[changed0]` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-bound-l-1-init-1 |
| 37 | `tests/test_coord02_m3_acquisition.py` | `test_acquire_rejects_changed_campaign_before_work[changed1]` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-bound-l-1-init-1 |
| 38 | `tests/test_coord02_m3_acquisition.py` | `test_acquire_rejects_changed_campaign_before_work[changed2]` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-bound-l-1-init-1 |
| 39 | `tests/test_coord02_m3_acquisition.py` | `test_acquire_recovers_after_episode_before_checkpoint` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-episode-crash-l-1-init-1 |
| 40 | `tests/test_coord02_m3_acquisition.py` | `test_construct_both_lineages_init_and_repair` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-l-1-init-1 |
| 41 | `tests/test_coord02_m3_acquisition.py` | `test_end_to_end_none_disposition` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-l-1-init-1 |
| 42 | `tests/test_ag01_state.py` | `test_outcome_links_durable_receipt_only` | `AssertionError` | AssertionError: DispatchStatus(operation_id='ag01:state-traj:probe:1', dispatch_state='dispatching', reconcile_state='none', cancel_state='none', settled=False, sent_this_call=False, next_decision='needs-reconciliation') |
| 43 | `tests/test_ag01_state.py` | `test_outcome_refusals` | `AssertionError` | AssertionError: DispatchStatus(operation_id='ag01:state-traj:probe:1', dispatch_state='dispatching', reconcile_state='none', cancel_state='none', settled=False, sent_this_call=False, next_decision='needs-reconciliation') |
| 44 | `tests/test_ag01_state.py` | `test_outcome_future_epoch_and_bad_value_refused` | `AssertionError` | AssertionError: DispatchStatus(operation_id='ag01:state-traj:probe:1', dispatch_state='dispatching', reconcile_state='none', cancel_state='none', settled=False, sent_this_call=False, next_decision='needs-reconciliation') |
| 45 | `tests/test_ag01_state.py` | `test_stale_dependency_invalidates_receipt` | `AssertionError` | AssertionError: DispatchStatus(operation_id='ag01:state-traj:probe:1', dispatch_state='dispatching', reconcile_state='none', cancel_state='none', settled=False, sent_this_call=False, next_decision='needs-reconciliation') |
| 46 | `tests/test_ag01_state.py` | `test_continuation_useful_and_refused` | `AssertionError` | AssertionError: DispatchStatus(operation_id='ag01:state-traj:probe:1', dispatch_state='dispatching', reconcile_state='none', cancel_state='none', settled=False, sent_this_call=False, next_decision='needs-reconciliation') |
| 47 | `tests/test_ag01_state.py` | `test_cursor_tick_and_budget_reconstruct` | `AssertionError` | AssertionError: DispatchStatus(operation_id='ag01:state-traj:probe:1', dispatch_state='dispatching', reconcile_state='none', cancel_state='none', settled=False, sent_this_call=False, next_decision='needs-reconciliation') |
| 48 | `tests/test_s09o_pilot.py` | `test_bound_policy_releases_drive_the_covered_domain` | `AssertionError` | AssertionError: assert 'unavailable' == 'available' |
| 49 | `tests/test_s09o_pilot.py` | `test_p0_has_no_release_and_uncovered_domains_refuse` | `KeyError` | KeyError: 'domain' |
| 50 | `tests/test_s09o_pilot.py` | `test_one_candidate_per_arm_and_experience_is_the_only_request_difference` | `AssertionError` | assert 0 == 2 |
| 51 | `tests/test_s09o_pilot.py` | `test_rejected_arm_is_incomplete_and_not_relabelled` | `AssertionError` | AssertionError: assert 'unavailable' == 'rejected' |
| 52 | `tests/test_s09o_pilot.py` | `test_controlled_http_adapter_carries_bound_policy_bytes` | `AssertionError` | assert 0 == 2 |
| 53 | `tests/test_s09o_pilot.py` | `test_export_verifies_offline_without_database_or_provider` | `AssertionError` | AssertionError: assert 'e3b0c44298fc...5991b7852b855' == '' |
| 54 | `tests/test_ec02ad_verif.py` | `test_verif_ad01_sigkill_resume_same_campaign_no_dup_spend` | `FileNotFoundError` | FileNotFoundError: [Errno 2] No such file or directory: '/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif' |
| 55 | `tests/test_ec02ad_verif.py` | `test_verif_ad01_resume_spend_equals_direct_run` | `FileNotFoundError` | FileNotFoundError: [Errno 2] No such file or directory: '/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif' |
| 56 | `tests/test_ec02ad_verif.py` | `test_verif_fresh_checkout_premises_tracked_no_scratch_deps` | `FileNotFoundError` | FileNotFoundError: [Errno 2] No such file or directory: '/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif' |
| 57 | `tests/test_ec02ad_verif.py` | `test_verif_fresh_clone_import_and_collect` | `AssertionError` | AssertionError: fatal: repository '/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif' does not exist |
| 58 | `tests/test_ec02ad_verif.py` | `test_verif_original_probe_retired_stamp_channel_deleted` | `AssertionError` | AssertionError: original probe file missing from tip |
| 59 | `tests/test_ag01_demo.py` | `test_demo_journey` | `AssertionError` | AssertionError: Traceback (most recent call last): |
| 60 | `tests/test_ag01_demo.py` | `test_demo_deterministic_rerun` | `AssertionError` | AssertionError: Traceback (most recent call last): |
| 61 | `tests/test_ag01_demo.py` | `test_stale_decline_refused` | `AssertionError` | AssertionError: assert 2 == 0 |
| 62 | `tests/test_ag01_demo.py` | `test_forged_receipt_observe_refused` | `AssertionError` | AssertionError: assert 2 == 0 |
| 63 | `tests/test_gateway_usage_unknown.py` | `test_malformed_usage_preserves_partial_evidence_and_reservation[chat]` | `AssertionError` | AssertionError: assert 'failure' == 'unknown' |
| 64 | `tests/test_gateway_usage_unknown.py` | `test_malformed_usage_preserves_partial_evidence_and_reservation[responses]` | `AssertionError` | AssertionError: assert 'failure' == 'unknown' |
| 65 | `tests/test_gateway_usage_unknown.py` | `test_noncanonical_scale_does_not_settle_provider_charge[chat]` | `AssertionError` | AssertionError: assert 'failure' == 'unknown' |
| 66 | `tests/test_gateway_usage_unknown.py` | `test_noncanonical_scale_does_not_settle_provider_charge[responses]` | `AssertionError` | AssertionError: assert 'failure' == 'unknown' |
| 67 | `tests/test_broker_dbos.py` | `test_record_step_replay_is_idempotent` | `AssertionError` | AssertionError: assert {} == {'n1': 'op:att1:n1'} |
| 68 | `tests/test_broker_dbos.py` | `test_attempt_workflow_runs_two_ops_to_completion` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "postgres" in connection info string |
| 69 | `tests/test_broker_dbos.py` | `test_duplicate_workflow_id_never_resends` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "postgres" in connection info string |
| 70 | `tests/test_coord02_learning.py` | `test_empty_response_kept_and_counted` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-l-1-init-1 |
| 71 | `tests/test_coord02_learning.py` | `test_lineage_two_exposure_manifest` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-exposure-l-1-init-1 |
| 72 | `tests/test_coord02_learning.py` | `test_repair_carries_lineage_and_concrete_failure` | `ConstructionBudgetExhausted` | experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-repair-failure-l-1-init-1 |
| 73 | `tests/test_dev01_compare.py` | `test_dev06_abc_affordances_and_accounting` | `AssertionError` | AssertionError: assert False |
| 74 | `tests/test_dev01_compare.py` | `test_dev09_use_failure_fallback_and_unknown_routing` | `SettlementError` | settlement.common.SettlementError: expenditure requires a durable operation_id |
| 75 | `tests/test_dev01_compare.py` | `test_dev10_rejected_episode_inspectable` | `SettlementError` | settlement.common.SettlementError: expenditure requires a durable operation_id |
| 76 | `tests/test_r03_flow.py` | `test_r03_database_prerequisite_explicit` | `Failed` | psycopg.ProgrammingError: missing "=" after "/postgres" in connection info string |
| 77 | `tests/test_r03_flow.py` | `test_restore_rebinds_dbos_workflow_inputs` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/postgres" in connection info string |
| 78 | `tests/test_r03_flow.py` | `test_restore_refuses_mixed_recovery_set` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/postgres" in connection info string |
| 79 | `tests/test_s09_persist_execution.py` | `test_store_read_record_carries_the_digests_it_read` | `IndexError` | IndexError: list index out of range |
| 80 | `tests/test_s09_persist_execution.py` | `test_admitted_action_is_on_the_saved_record` | `IndexError` | IndexError: list index out of range |
| 81 | `tests/test_s09_persist_execution.py` | `test_a_genuine_execution_reads_as_a_copy_in_the_preserved_bundle` | `AssertionError` | assert {False, True} == {True} |
| 82 | `tests/test_settle_actual.py` | `test_receipt_actual_cost_settles_partial` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 83 | `tests/test_settle_actual.py` | `test_success_without_actual_cost_consumes_full_reservation` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 84 | `tests/test_settle_actual.py` | `test_overcharge_preserves_receipt_and_holds_liability` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 85 | `tests/test_ui_views.py` | `test_overview_renders_from_durable_records_with_gateway_down` | `AssertionError` | assert ('w1' in '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>settlement operator</title>\n<link rel="sty...air"><input name="request_id" placeholder="request id"><button>repair scan</button> |
| 86 | `tests/test_ui_views.py` | `test_investigation_view_escapes_generated_content` | `AssertionError` | assert ('w1' in '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>settlement operator</title>\n<link rel="sty...\n<h2>versions</h2>\n<ul><li>r1: &lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;</l |
| 87 | `tests/test_ui_views.py` | `test_gets_never_mutate_domain_state` | `AssertionError` | AssertionError: assert 404 == 200 |
| 88 | `tests/test_bdr01_host_boundary.py` | `test_store_backed_use_attributes_sandbox_operations` | `AssertionError` | assert 0 == 1 |
| 89 | `tests/test_bdr01_host_boundary.py` | `test_failed_member_falls_back_with_attribution` | `AssertionError` | AssertionError: assert 'refused' == 'bdr01-pollution-canary' |
| 90 | `tests/test_broker_prepare.py` | `test_model_exposure_scales_with_retries` | `KeyError` | KeyError: 'exposure' |
| 91 | `tests/test_broker_prepare.py` | `test_sandbox_prepare_reserves_hard_ceiling` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 92 | `tests/test_dev01_ops.py` | `test_learning_view_inspects_episode_phase_lineage_and_costs` | `SettlementError` | settlement.common.SettlementError: expenditure requires a durable operation_id |
| 93 | `tests/test_dev01_ops.py` | `test_episode_gets_never_mutate_domain_state` | `SettlementError` | settlement.common.SettlementError: expenditure requires a durable operation_id |
| 94 | `tests/test_dev02_context.py` | `test_resume_carries_working_state` | `AssertionError` | AssertionError: assert set() >= {'ctx10-t_b8c09476-op'} |
| 95 | `tests/test_dev02_context.py` | `test_revalidate_catches_working_state_change` | `AssertionError` | assert True is False |
| 96 | `tests/test_eng_close1.py` | `test_contradictory_late_receipt_flagged_for_reconciliation` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 97 | `tests/test_eng_close1.py` | `test_matching_late_receipt_not_flagged` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 98 | `tests/test_m4_clean_baseline.py` | `test_the_live_path_now_dispatches_and_settles` | `ValueError` | ValueError: model route preflight refused: gateway credentials are not configured |
| 99 | `tests/test_m4_clean_baseline.py` | `test_a_settled_receipt_is_joined_to_its_operation` | `ValueError` | ValueError: model route preflight refused: gateway credentials are not configured |
| 100 | `tests/test_ui_commands.py` | `test_pause_resume_cancel_cycle_with_external_unknown` | `AssertionError` | assert 'accepted' in '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>settlement operator</title>\n<link rel="sty...0cf</p>\n<p>detail: unknown operation op1</p>\n\n\n<p><a href="/">back to over |
| 101 | `tests/test_ui_commands.py` | `test_cancel_forwards_to_gateway` | `AssertionError` | assert 'accepted' in '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>settlement operator</title>\n<link rel="sty...ef3</p>\n<p>detail: unknown operation op1</p>\n\n\n<p><a href="/">back to over |
| 102 | `tests/test_agenda_repair.py` | `test_repair_scan_converges_advanced_unsent` | `AssertionError` | AssertionError: assert 'op2' in [] |
| 103 | `tests/test_alee_learner.py` | `test_cli_run_doubled_and_use_fresh_process` | `AssertionError` | AssertionError: assert 'refused' == 'acquired-sw-alee01' |
| 104 | `tests/test_bacq_method.py` | `test_run_use_executes_outside_menu_member_bytes` | `AssertionError` | AssertionError: assert 'refused' == 'acquired-sw-greedy-r1' |
| 105 | `tests/test_conftest_isolation.py` | `test_pinned_seams_are_reported_rather_than_worked_around` | `KeyError` | KeyError: 'ec02test_bauth' |
| 106 | `tests/test_eacq_repair.py` | `test_validation_child_work_comes_from_the_model` | `AssertionError` | AssertionError: validation child work never reached the model |
| 107 | `tests/test_eng_invb_dispatch.py` | `test_from_settings_honors_responses_shape` | `AttributeError` | AttributeError: 'GatewayError' object has no attribute 'text' |
| 108 | `tests/test_inva_recovery.py` | `test_receipt_identity_bound_to_operation` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 109 | `tests/test_invc3_export.py` | `test_byte_identity_at_receipt_validation_retention_and_use` | `AssertionError` | AssertionError: {'checked': 4, 'problems': ['use-without-retained ad01-w0-I-13-I-ad01-w0-dev-sw-00']} |
| 110 | `tests/test_invc3_study.py` | `test_complete_study_on_recordings_with_recompute` | `AssertionError` | assert False |
| 111 | `tests/test_invd2_settle.py` | `test_unbilled_model_call_settles_at_measured_tokens` | `AssertionError` | assert (2485, 0) == (10, 0) |
| 112 | `tests/test_invr1_study_entry.py` | `test_restart_keeps_single_root_and_consumption` | `AssertionError` | assert 2 == 0 |
| 113 | `tests/test_m1_shared_executor.py` | `test_default_method_fallback_reports_selected_identity` | `AssertionError` | assert False is True |
| 114 | `tests/test_r01_deadline_ui.py` | `test_shared_next_decision_matches_single_path` | `AssertionError` | AssertionError: assert 'idle' == 'dispatch-bulk-op1' |
| 115 | `tests/test_r02_explearn.py` | `test_deterministic_run_reports_acquisition_and_estimates` | `AssertionError` | AssertionError: assert 'provider rec...lling measure' == 'token-length...etary ceiling' |
| 116 | `tests/test_rec_checkpoint.py` | `test_checkpoint_writes_consistent_recovery_set` | `AssertionError` | AssertionError: assert ['0001_schema...nce.sql', ...] == ['0001_schema...nce.sql', ...] |
| 117 | `tests/test_rpr01_db.py` | `test_lane_database_is_real_postgresql_16` | `AssertionError` | AssertionError: assert False |
| 118 | `tests/test_rpr07_resume.py` | `test_fresh_database_is_not_resume` | `ProgrammingError` | psycopg.ProgrammingError: missing "=" after "/settlement_cb01exec_fresh" in connection info string |
| 119 | `tests/test_rpr13_endtoend.py` | `test_no_candidate_path` | `AssertionError` | AssertionError: ['score-without-oracle-evidence B-gr-eva-00', 'score-without-oracle-evidence B-gr-eva-01', 'score-without-oracle-evide...e-evidence B-gr-eva-03', 'score-without-oracle-evidence B-gr-eva-04', 'score-withou |
| 120 | `tests/test_s09_merged_tip_regression.py` | `test_campaign_test_file_set_is_exact` | `AssertionError` | AssertionError: campaign test file set moved. added=['test_s09_a7_a8_study_admission.py', 'test_s09_a8_adoption.py', 'test_s09_a8_production_adoption.py', 'test_s09_c11_reported_spend.py', 'test_s09_controls.py', 'test_s |
| 121 | `tests/test_s09_store_cleanup.py` | `test_c_the_study_admission_path_has_no_production_caller[experiments]` | `AssertionError` | AssertionError: production code under experiments/ now reaches the study-call path, so the LIKE fallback is a live second source of truth and removing it would be wrong: ['experiments/ad01/e3_ladder.py'] |
| 122 | `tests/test_s09_swe_experiment.py` | `test_paired_comparisons_pair_the_same_instance_across_representations` | `AssertionError` | AssertionError: a panel this size produces pairs |
| 123 | `tests/test_s09_test_db_safety.py` | `test_the_hazard_has_not_grown` | `AssertionError` | AssertionError: ['test_c14_live_already_spent_source.py'] |
| 124 | `tests/test_s09c3_policy_pilot.py` | `test_controlled_http_full_study_freezes_and_verifies_public_path` | `AssertionError` | assert False |
| 125 | `tests/test_s09m5_pilot.py` | `test_doubled_pilot_verifies_green` | `AssertionError` | AssertionError: assert 'unavailable' == 'available' |
| 126 | `tests/test_s3_trials.py` | `test_matched_expenditure_adds_up` | `SettlementError` | settlement.common.SettlementError: expenditure requires a durable operation_id |
| 127 | `tests/test_state_operations.py` | `test_restart_reconciliation_reports_registry` | `AssertionError` | AssertionError: assert [{'id': 'opA'...on': 1, ...}}] == [{'id': 'opA'...': 'exec-v3'}] |
| 128 | `tests/test_steward_leases.py` | `test_lease_expiry_refuses_stale_dispatch_and_fulfill_but_keeps_observation` | `AssertionError` | AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'> |
| 129 | `tests/test_team_live.py` | `test_live_planner_falls_back_honestly_on_gateway_error` | `AssertionError` | AssertionError: assert 'fallback-gateway-error' == 'fallback-timeout' |

## Groups

Nine causes account for all 129. Each states its size, the shared signature
quoted from the log, and whether it is one cause or coincidental. A group of 12
sharing an exception is a cause. A file with three unrelated assertions in it is
not, and is listed as three.

### G1. `urlparse` on a conninfo string (29)

Signature, all 29 identical in form:
`psycopg.ProgrammingError: missing "=" after "/agenda01_w28v0_r_t0" in connection info string`

Producers, per `9493f12`: `experiments/agenda01/runner.py:34` `swap_dbname` (27),
`scripts/agenda01.py:483` `_scratch_dsn` (2), `tests/test_r03_flow.py` (3). Three
further sites carried the same defect without yet failing.

**Classification: already fixed, commit `9493f12`.** Verified, not inferred. A
libpq conninfo string is not a URL, so `urlparse` puts the whole string in
`.path`; every helper that read a database name that way returned the DSN, and
every swap built a string with no `dbname=` for psycopg to parse. The commit
message records zero `psycopg.ProgrammingError` remaining across the six touched
files.

The 29 split 24 in `tests/test_ag01_experiment.py` and 5 elsewhere
(`test_r03_flow.py` 2, `test_rpr07_resume.py` 1, `test_broker_dbos.py` 2). The
commit's headline of 32 counts three sites that carried the same defect without
yet failing, which is why the log shows fewer.

### G2. `init_dbos` handed a conninfo to SQLAlchemy (2)

Signature: `psycopg.ProgrammingError: missing "=" after "postgres" in connection info string`

Both are setup-phase, so pytest reports them as `ERROR` rather than `FAILED`.
Same root as G1, different boundary: `init_dbos` passed a conninfo straight into
`DBOSConfig.database_url`, which `sqlalchemy.make_url` validates and refuses.

**Classification: already fixed, commit `6fb883d`.** The conversion landed in
`db.database_url` beside the `connect` it sits next to, and settlement's own
dialect stays the conninfo.

### G3. ag01 experiment, receipts with no adapter (18, behind G1)

Signature in the log: `dispatch_state='dispatching'`,
`next_decision='needs-reconciliation'`, `sent_this_call=False`.

The brief described these as `needs-reconciliation`, and that is what the broker
reports. It is a symptom. The store refuses with
`settlement/store.py:1836: raise SettlementError("observation receipt needs its adapter")`,
and `AgendaProbeLauncher` had been minting `observation`, `dud` and
`product-claims` receipts without the field.

**Classification: in flight and landed, commit `060d223`.** The store rule is
correct, so the producer was fixed rather than the rule. The commit reports the file going
from 24 failures to 18 once G1 is removed, and those 18 are this group. So none
of the 18 appears in this log: they are what the file looked like underneath the
conninfo error. The log's own 24 rows are all G1.

This is the one place where the log's own description was wrong in a way that
mattered. A reading of "`needs-reconciliation` means unresolved liability" would
send the next lane to look at reconciliation. Nothing was unresolved. One field
was missing from a receipt.

### G4. `inv_r3_export` hardcoded database name (10)

Signature, all 10 byte-identical:
`psycopg.OperationalError: connection failed: ... FATAL: database "inv_r3_export" does not exist`

`tests/test_invr3_export.py:15-17` reads `os.environ.get(...)` with
`"dbname=inv_r3_export host=..."` as the default, so the file asks for a named
database on a shared cluster.

**Classification: environmental, and addressed by `060d223` for 3 of the 10.**
The scanner counted a seam only when the file both mentioned and spelled like the
25 names already converted, so this one was invisible twice over. The commit takes
the file to 7 remaining, which are four further defects this lane did not own.

### G5. `invalid_input` from three distinct guards (9)

Nine rows across 6 files share one signature:
`AssertionError: assert <ResultCode.I...nvalid_input'> == <ResultCode.A...ED: 'applied'>`

`store._code` maps a plain `SettlementError` to `ResultCode.INVALID_INPUT` and
`transact` puts the message in `result.detail`, which the tests never read. The
exception text never reaches the assertion, so all nine read identically. Reading
the product code splits them into three unrelated causes. This is the clearest
case in the run where grouping by exception class would have been wrong.

**G5a. A receipt admitted for an operation that was never dispatched (6).**
`src/settlement/store.py:1780-1781`:
`raise SettlementError(f"operation {op['id']} was not dispatched")`, behind the
guard `if op.get("dispatch_state") == "prepared"`. Measured: `test_settle_actual.py`
and `test_eng_close1.py` contain zero calls to `advance_dispatch`, so their
operations are still `prepared` when the receipt arrives.

Hits `test_settle_actual.py` (3), `test_eng_close1.py` (2, both via the
`_settled_op` helper), `test_inva_recovery.py` (1, where `op1` is dispatched at
line 36 but `op2` at line 35 is not, and the failing leg is the replay).

The tests pass `{"kind": "model"}` and `{"kind": "close1-probe"}` as the
operation body, which sets no `effect` key. Every guard below line 1781 is keyed
on `effect`, so the provenance and adapter checks are never reached. That rules
out the four hypotheses the signature suggests.

**Classification: pre-existing product defect.** Whether the store should refuse
a receipt for a prepared operation is a real design question the log cannot
settle, but the refusal is deliberate and named, so the tests are the thing that
predates it.

**G5b. `prepare_operation` omits the attempt's bound allocation (1).**
`src/settlement/store.py:374-376`:
`raise ConflictPayload(f"attempt {attempt_id} requires its bound allocation")`.

`test_steward_leases.py` acquires the attempt with `allocation_id="a1"` through
`_work`, then calls `prepare_operation` passing only `operation_id` and
`attempt_id`. `ConflictPayload.code` is `INVALID_INPUT`, and an inner
`except SettlementError` at `store.py:293` converts it to a result before the
outer handler can re-raise it, so the test sees a code and never a message.

**Classification: pre-existing product defect, and the test is the thing that is
wrong.** The store is refusing a genuinely inconsistent call.

**G5c. `retries` is refused by the broker (2).**
`src/settlement/broker.py:262-267` returns, not raises:
`detail="retries must be zero; use distinct operation identities"` with
`INVALID_INPUT`, short-circuiting before `prepare_operation` runs.
`test_broker_prepare.py:67` passes `retries=1`.

**This one is a contradiction between two tests in the same file, and it cannot
be resolved by fixing either alone.** `test_model_exposure_scales_with_retries`
at line 51 passes `retries=2` and asserts `result.data["exposure"] == 51`, which
requires the broker to multiply exposure by `retries + 1`. The same file's
`_sandbox_exposure` helper still does that multiply. The broker refuses the
argument the test relies on, so these two assertions cannot both hold. The second
row, `KeyError: 'exposure'` on the same test, is the same cause: the call returns
an empty `data` dict before exposure is computed.

**Classification: pre-existing product defect with an unresolved contract
question.** A hard refusal and a multiplier both live in the code. Someone has to
decide which is right before this clears, and that decision is not derivable from
a log.

### G6. `record_expenditure` refuses without an `operation_id` (5)

Signature, identical in all 5:
`settlement.common.SettlementError: expenditure requires a durable operation_id`

`src/settlement/trials.py:209`. Files: `test_dev01_compare.py` (2),
`test_dev01_ops.py` (2), `test_s3_trials.py` (1).

**Classification: pre-existing product defect, one cause.** Unlike G5 this one
leaks its message, so the cause is legible from the log alone: five test files
call `trials.record_expenditure` without the `operation_id` the function
requires. The rule is new enough that the callers were never updated.

### G7. Construction budget held by unresolved effects (10) — CLEARED

Signature, all 10:
`experiments.coord02.experience.ConstructionBudgetExhausted: construction budget exhausted: four calls maximum: unresolved effects hold construction capacity: coord02-L-construct-...-init-1`

Files: `test_coord02_m3_acquisition.py` (7), `test_coord02_learning.py` (3).

**Original classification: pre-existing product defect, one cause.** A test makes a call
whose effects never reconcile, and every later call in the same ledger is refused
because capacity is held. The shared substring is the same allocation id
(`...-init-1`) in 8 of the 10, which is the tell: these are cascading from one
unreconciled first call, not ten independent failures. Fixing the first call in
each file would clear the rest.

**Correction (lane Z1).** The one-cause cascade was right; the location was
not, and this entry's advice would have sent a lane into the test files. The
first call did not fail to reconcile. `broker._send_model` filed a `success`
receipt for an empty gateway response, `store._validate_receipt` refused that
receipt and threw it away, and the operation was left `dispatching` with no
receipt and a `reserved` reservation the ledger then read as an unresolved
effect. The hold in `ConstructionLedger` is correct and unchanged; the broker's
producer was what reached it. Fixed in `src/settlement/broker.py` by filing a
decided `failure` receipt. See the commit for the measurement.

### G8. Pilot construction arms report `unavailable` (8)

Signature: `AssertionError: assert 'unavailable' == 'available'`

Measured: 8 rows, in `test_s09o_pilot.py` (6), `test_s09m5_pilot.py` (1),
`test_s09c3_policy_pilot.py` (1). Related, and distinct in message:
`test_s09o_pilot.py` `test_one_candidate_per_arm_...` (`assert 0 == 2`),
`test_controlled_http_adapter_carries_bound_policy_bytes` (`assert 0 == 2`),
`test_p0_has_no_release_and_uncovered_domains_refuse` (`KeyError: 'domain'`),
`test_export_verifies_offline...` (a digest compared against the empty string).

**Classification: pre-existing product defect, one cause behind several
assertions.** Two arms' construction never ran, so `calls` is 0 and no `domain`
key exists. Each test asserts a different property of the same empty result, so
the 6 rows in `test_s09o_pilot.py` are one cause observed six ways, not six
defects.

### G9. A missing worktree at an absolute path (5)

Signature:
`FileNotFoundError: [Errno 2] No such file or directory: '/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif'`
and `AssertionError: fatal: repository '/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif' does not exist`

`tests/test_ec02ad_verif.py` hardcodes `AD01_ROOT` and `VERIF_ROOT` to that path
at lines 923 and 1023. Measured: 3 rows are `FileNotFoundError` and 2 are
`AssertionError` naming the same missing repository, so all 5 are the one cause.

**Classification: environmental.** Measured: the directory does not exist on
this machine. These tests cannot pass here regardless of product state.

### G10. Tests that cannot fail (6)

Six failures are not product defects at all. Each is classified in the next
section with its `file:line`.

### Singletons that are genuinely distinct (13)

Thirteen rows across 13 files, each its own cause. Grouping them would be a
lie, so they are listed individually. None is environmental except where noted.

| File | Test | Message | Note |
|---|---|---|---|
| `test_gateway_usage_unknown.py` | `test_malformed_usage_preserves_partial_evidence_and_reservation[chat]` and `[responses]` | `assert 'failure' == 'unknown'` | one cause, two parametrisations |
| `test_gateway_usage_unknown.py` | `test_noncanonical_scale_does_not_settle_provider_charge[chat]` and `[responses]` | `assert 'failure' == 'unknown'` | same, so 4 rows one cause |
| `test_broker_dbos.py` | `test_record_step_replay_is_idempotent` | `assert {} == {'n1': 'op:att1:n1'}` | |
| `test_dev01_compare.py` | `test_dev06_abc_affordances_and_accounting` | `assert False` | |
| `test_s09_persist_execution.py` | `test_store_read_record_carries_the_digests_it_read`, `test_admitted_action_is_on_the_saved_record` | `IndexError: list index out of range` | one cause, two tests |
| `test_s09_persist_execution.py` | `test_a_genuine_execution_reads_as_a_copy_in_the_preserved_bundle` | `assert {False, True} == {True}` | |
| `test_ag01_demo.py` | `test_demo_journey`, `test_demo_deterministic_rerun` | `AssertionError: Traceback (most recent call last):` | subprocess demo |
| `test_ag01_demo.py` | `test_stale_decline_refused`, `test_forged_receipt_observe_refused` | `assert 2 == 0` | exit code, one cause |
| `test_m4_clean_baseline.py` | `test_the_live_path_now_dispatches_and_settles`, `test_a_settled_receipt_is_joined_to_its_operation` | `ValueError: model route preflight refused: gateway credentials are not configured` | **environmental**: no live gateway configured |
| `test_dev02_context.py` | `test_resume_carries_working_state` | `assert set() >= {'ctx10-t_b8c09476-op'}` | |
| `test_dev02_context.py` | `test_revalidate_catches_working_state_change` | `assert True is False` | |
| `test_ui_views.py` | `test_overview_renders_from_durable_records_with_gateway_down`, `test_investigation_view_escapes_generated_content`, `test_gets_never_mutate_domain_state` | HTML content and `assert 404 == 200` | **environmental**: the HTML names "settlement operator", a different UI's content |
| `test_ui_commands.py` | `test_pause_resume_cancel_cycle_with_external_unknown`, `test_cancel_forwards_to_gateway` | `assert 'accepted' in '<!DOCTYPE html>...unknown operation op1'` | same cause as the UI views rows |
| `test_r01_deadline_ui.py` | `test_shared_next_decision_matches_single_path` | `assert 'idle' == 'dispatch-bulk-op1'` | |
| `test_r02_explearn.py` | `test_deterministic_run_reports_acquisition_and_estimates` | `assert 'provider rec...lling measure' == 'token-length...etary ceiling'` | |
| `test_eng_invb_dispatch.py` | `test_from_settings_honors_responses_shape` | `AttributeError: 'GatewayError' object has no attribute 'text'` | **environmental**: same missing gateway |
| `test_invc3_export.py` | `test_byte_identity_at_receipt_validation_retention_and_use` | `{'checked': 4, 'problems': ['use-without-retained ...']}` | |
| `test_invc3_study.py` | `test_complete_study_on_recordings_with_recompute` | `assert False` | |
| `test_invd2_settle.py` | `test_unbilled_model_call_settles_at_measured_tokens` | `assert (2485, 0) == (10, 0)` | |
| `test_invr1_study_entry.py` | `test_restart_keeps_single_root_and_consumption` | `assert 2 == 0` | |
| `test_m1_shared_executor.py` | `test_default_method_fallback_reports_selected_identity` | `assert False is True` | |
| `test_rec_checkpoint.py` | `test_checkpoint_writes_consistent_recovery_set` | `assert ['0001_schema...'] == ['0001_schema...']` | stale pin, see G11 |
| `test_rpr01_db.py` | `test_lane_database_is_real_postgresql_16` | `assert False` | fixed by `9493f12` |
| `test_rpr13_endtoend.py` | `test_no_candidate_path` | `['score-without-oracle-evidence B-gr-eva-00', ...]` | |
| `test_team_live.py` | `test_live_planner_falls_back_honestly_on_gateway_error` | `assert 'fallback-gateway-error' == 'fallback-timeout'` | |
| `test_agenda_repair.py` | `test_repair_scan_converges_advanced_unsent` | `assert 'op2' in []` | |
| `test_alee_learner.py` | `test_cli_run_doubled_and_use_fresh_process` | `assert 'refused' == 'acquired-sw-alee01'` | |
| `test_bacq_method.py` | `test_run_use_executes_outside_menu_member_bytes` | `assert 'refused' == 'acquired-sw-greedy-r1'` | |
| `test_eacq_repair.py` | `test_validation_child_work_comes_from_the_model` | `validation child work never reached the model` | |
| `test_conftest_isolation.py` | `test_pinned_seams_are_reported_rather_than_worked_around` | `KeyError: 'ec02test_bauth'` | fixed by `060d223` |

## Tests that cannot fail

Six failures assert something no change to the product can falsify. Each would
still pass if every function it imports returned `undefined`. This project has
already found five of these shapes. These are six more instances.

They are not one regression. Three distinct groups, and saying otherwise would
be the exact error this census exists to prevent. Five failed on pin drift, one
failed on a fixture that could never pass, and one fired on a true positive.

| `file:line` | Shape | Why it cannot fail |
|---|---|---|
| `tests/test_s09_swe_experiment.py:208` | fixture too small to exercise the property | The worst of the six. It calls `matrix.run_matrix(splits=("held_out",), lineages=matrix.supported_lineages()[:1], ...)` and then asserts `pairs` is non-empty, with the message "a panel this size produces pairs". `supported_lineages` filters to `representation_kind == PYTHON_STEP`, and `paired_comparisons` emits a pair only when `left.representation_kind != right.representation_kind`. One lineage yields one row per task and an empty inner loop, so the panel yields exactly zero comparisons no matter how many instances exist. The assertion cannot pass as written, and no product change affects that. |
| `tests/test_s09_test_db_safety.py:79` | constant pin, stale direction | `HAZARD_CEILING = 0` at line 34 and the body is `assert len(others) <= HAZARD_CEILING`. The docstring says the census "is a measurement, not a frozen number" and that "a fall is not a failure worth a red build", then pins zero, so the only direction it can move is red. It fired on `['test_c14_live_already_spent_source.py']`, which is a genuine literal `DROP DATABASE` at line 185, so the finding is a true positive and the assertion is still unfalsifiable in the direction the docstring claims it cares about. |
| `tests/test_s09_merged_tip_regression.py:339` | constant pin | `EXPECTED_CAMPAIGN_TEST_FILES` is a hand-maintained `frozenset` of 96 filenames from line 66. The actual side is derived (`(ROOT / "tests").glob("test_s09*.py")` minus `NON_CAMPAIGN_HELPERS`), so the scan half is sound. The equality half is a snapshot that must be hand-edited whenever a campaign test is added, and five were added. It cannot detect a campaign module changing behaviour. |
| `tests/test_rec_checkpoint.py:69` | constant pin, stale | `assert manifest["migrations"] == ["0001_schema.sql", ..., "0014_team_runtime.sql"]`. The product side is real: `scripts/checkpoint.py:115` runs `SELECT name FROM schema_migrations ORDER BY name`. Measured: `migrations/` now holds 18 files, so the literal is four short and the first missing entry is `0015_study_authority.sql`. The rest of the test, including the sha256 and the tar member, is genuine artifact verification; only this line is a pin. |
| `tests/test_state_operations.py:127` | constant pin, stale projection | `assert state["execution_versions"] == [{"id": "opA", "execution_version": "exec-v3"}]`. The test does call `store.restart_reconciliation(dsn)` at line 122, so the observed side is real and the expected value is a literal, not self-referential. `store.py:2394` now selects `o.payload` as well, added by `a3df674` to record an unresolved-terminal disposition, so the row gained a key the literal does not have. A projection-specific assertion over `(id, execution_version)` would survive it. |
| `tests/test_s09_store_cleanup.py:421` | tree-fact ratchet | Different in kind from the five above. It asserts a fact about the tree, not a return value, and the `ast.walk` is real evidence. Verified: `experiments/ad01/e3_ladder.py:366` and `:782` are genuine calls, `granted = authority.admit_study_call(`. The test's premise held when written and the product has since grown a caller, so this is a **true positive**, not a pin that drifted. It is listed here because the fact it pins, that no production caller exists, can only ever be satisfied by deleting a caller, never by a product change. |

## Where the counts stand

Every row is assigned to exactly one group below. The groups sum to 129.

| Group | Count | Classification |
|---|---|---|
| G1 conninfo via `urlparse` | 29 | already fixed, `9493f12` |
| G2 `init_dbos` conninfo to SQLAlchemy | (in G1's 2 broker_dbos rows) | already fixed, `6fb883d` |
| G3 ag01 receipts with no adapter | 0 in this log, 18 after G1 | landed, `060d223` |
| G4 `inv_r3_export` hardcoded name | 10 | environmental, 3 addressed by `060d223` |
| G5 `invalid_input`, three guards | 9 | pre-existing product defect |
| G6 `record_expenditure` without `operation_id` | 5 | pre-existing product defect |
| G7 construction budget held | 10 | pre-existing product defect |
| G8 pilot arms `unavailable` | 8 | pre-existing product defect |
| G9 missing worktree path | 5 | environmental |
| G10 tests that cannot fail | 6 | test defect |
| Singletons | 47 | mixed, itemised below |

Two accounting facts a reader needs before trusting any number here. G2's 2 rows
are physically inside G1's 29, because both are `test_broker_dbos.py`
`ProgrammingError` rows and the exception class cannot tell the two causes apart.
They are listed separately because the commits are, and counted once. G3's 18 do
not appear in this log at all: the log's 24 `test_ag01_experiment.py` rows are
every one of them the conninfo error, and the 18 only surface once that is
removed. Counting them would double the total.

The nine groups above sum to 82, and the singleton table below is 47. 82 + 47
is 129, which is the whole run. Nothing is unassigned.

So of 129 rows: **29 already fixed** by the two conninfo commits, and **100
remaining** after them. Of those 100, `060d223` claims 21, **8 are environmental**,
**6 cannot fail**, and the rest are pre-existing product defects.

The previous estimate said 95 remain. It is 100 by this count, and the
difference is 8 environmental rows and 6 unfalsifiable tests, neither of which
was a defect for anyone to fix.

## The top three

Ranked by failures cleared per unit of work, not by group size.

**1. G7, the construction budget held by unresolved effects. Clears 10. DONE
in `codex/implementation-investigation-learning-02`.**
The signature gave away the cascade but not the cause. Ten rows, and 8 of them
name the same allocation id, `coord02-L-construct-...-init-1`, which means one
call per campaign was holding capacity for everything after it — that part held
up. The second call in each ledger is *not* what needed fixing, and neither is
the first `request_call` in the test body: the tests were calling the API as
written. The broker filed a `success` receipt for an empty response, the store
refused it, and the receipt was discarded. The fix is one branch in
`src/settlement/broker.py`, not one edit per file. The margin here was real but
it was in the product, not the tests.

**2. G6, `record_expenditure` without an `operation_id`. Clears 5.**
This is the only group whose cause is fully legible in the log, because it is the
only one that leaks its own message:
`settlement.common.SettlementError: expenditure requires a durable operation_id`.
Five test files call the function without the required argument. The rule at
`trials.py:209` is new; the callers were never updated. The work is mechanical
and each file is independent, so it parallelises across five lanes with no shared
state.

**3. G5b and G5c, the two single-cause `invalid_input` rows. Clears 3.**
Ranked third despite being small because both are unambiguous, and G5c in
particular is a contract contradiction that blocks a decision rather than needing
one. G5b is a test passing an incomplete `prepare_operation`. G5c has the broker
refusing `retries` while the same file's helper still multiplies exposure by
`retries + 1`, so two assertions in one file cannot both hold and someone has to
choose which contract is real. Small, but each is a decision rather than a
mechanical edit.

Deliberately not in the top three. G1 and G2 are already fixed and clearing them
again is re-verification, not work. G3 and G4 belong to `060d223`. G5a is 6 rows
of genuine contract ambiguity, so it is the largest remaining single group and I
still rank it fourth, because deciding whether the store should refuse a receipt
for a prepared operation is a design question whose answer could invalidate the
fix. G8's 9 rows share a cause but the cause is an empty construction phase whose
origin the log does not show. G9 and the 5 gateway rows are environmental and
clear by configuration, not by code, so they are the cheapest of all and rank
nowhere because they are not defects.

## What the log could not tell me

Four things, and what would settle each.

**Whether the store should refuse a receipt for a prepared operation (G5a, 6
rows).** The refusal at `store.py:1781` is named and deliberate, so this is a
contract question rather than a bug hunt, and the log carries no evidence either
way. Reading the design intent would settle it; so would one call to
`admit_receipt` on a prepared operation with the exception un-swallowed, which
puts the message in `result.detail`.

**Whether the G5c contract is the broker's refusal or the helper's multiplier.**
Two assertions in one file cannot both hold. The answer is a decision, and no
amount of reading the log produces it.

**How the pilot construction arms came out `unavailable` (G8, 9 rows).** Two
arms' construction never ran, so `calls` is 0 and no `domain` key exists. The
bundle is built in a fixture and the log shows only the downstream assertions.
The pilot's own output directory would show whether the construction phase
refused or was skipped.

**Whether the `ec02ad_verif` and `ec02test_verif` databases were destroyed or
never created.** Four tests fail on a missing directory at an absolute path, and
a fifth, `test_rpr01_db.py`, fails on `assert False` for
`test_lane_database_is_real_postgresql_16`. The answer is in the PostgreSQL
server log, not in this run's log.

Two further items the log could have settled and did not, noted so a later reader
does not re-derive them. The `urlparse` and adapter causes in G1 and G3 were
identified by reading the commits, not from the log, and both commit messages
report their own before-and-after counts. Neither was verified here, because this
lane does not re-run tests.

## Reproducing this

The table is generated, not typed. The parser reads the log once, joins each
short-summary line to its report body by test name, and takes the terminal
exception from the body's closing `path:line: Exception` footer.

Two parsing notes, both of which cost a wrong count before they were fixed. The
report headers are `_`-delimited and pytest narrows the underscore run to 2 or 3
characters for long test names, so a header regex requiring 5 or more silently
drops six bodies and the table appears to join but has no message. And the
terminal exception is not always an `E`-prefixed line; an `assert` line carries
it instead, so the extraction has to fall through to the body footer.

Run it with:

```
python3 scripts/census_failures.py /tmp/full-suite.log
```
