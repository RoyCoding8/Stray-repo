ALTER TABLE trial_assignments
  ADD COLUMN candidate_digest TEXT NOT NULL DEFAULT '',
  ADD COLUMN evaluator_id TEXT NOT NULL DEFAULT '',
  ADD COLUMN evaluator_version TEXT NOT NULL DEFAULT '',
  ADD COLUMN evaluation_op TEXT NOT NULL DEFAULT '';

ALTER TABLE trial_protocols
  ADD COLUMN supported_scope JSONB NOT NULL DEFAULT '{}';
