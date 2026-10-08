-- Retire the study layer. Core execution, accounting and RSI records remain.
DROP TABLE IF EXISTS
  agenda_attempt_links,
  agenda_cursors,
  agenda_decisions,
  agenda_disposition_events,
  agenda_option_revisions,
  agenda_options,
  agenda_outcomes,
  agenda_traj_state,
  agenda_wake_log,
  attempt_capability_pins,
  candidate_submissions,
  capability_releases,
  capability_versions,
  claims,
  consolidation_proposals,
  context_packets,
  context_views,
  continuation_docs,
  derivation_premises,
  derivations,
  development_episodes,
  development_opportunities,
  evaluator_packages,
  evaluator_receipts,
  evidence_relations,
  expenditure_ledger,
  inferential_gates,
  inv_r1_study_runs,
  observations,
  oppositions,
  packet_invocations,
  quarantine_registry,
  retractions,
  router_policies,
  s09_assessment_exposure,
  s09_policy_state,
  store_identity,
  study_authority,
  study_corrections,
  study_phases,
  support_cache,
  team_joins,
  team_outputs,
  team_plans,
  team_snapshots,
  team_submissions,
  trial_assignments,
  trial_protocols,
  trial_results
CASCADE;

-- Backfill durable holds for already published RSI records.
WITH held AS (
  INSERT INTO artifact_refs (digest, holder_kind, holder_id)
  SELECT digest, 'release', 'rsi-genome:' || digest FROM rsi_genomes
  UNION ALL SELECT digest, 'evidence', 'rsi-task:' || digest FROM rsi_tasks
  UNION ALL SELECT trajectory, 'attempt', 'rsi-episode:' || operation_id FROM rsi_episodes
  UNION ALL SELECT solution, 'evidence', 'rsi-verdict:' || episode FROM rsi_verdicts
  ON CONFLICT (digest, holder_kind, holder_id) DO NOTHING RETURNING digest
), counts AS (SELECT digest, count(*) AS n FROM held GROUP BY digest)
UPDATE artifact_versions a SET protection_count = a.protection_count + c.n
FROM counts c WHERE a.digest = c.digest;
