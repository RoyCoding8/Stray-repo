-- P01 continuation state is a one-to-one extension of the kernel objective.
-- The kernel investigation/revision remains the sole objective authority.
CREATE TABLE rsi_investigations (
  investigation_id TEXT PRIMARY KEY REFERENCES investigations (id),
  objective_revision INT NOT NULL CHECK (objective_revision > 0),
  revision INT NOT NULL DEFAULT 0 CHECK (revision >= 0),
  status TEXT NOT NULL DEFAULT 'ready'
    CHECK (status IN ('ready', 'pending', 'suspended', 'completed', 'unresolved')),
  domain TEXT NOT NULL,
  config JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(config) = 'object'),
  policy JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(policy) = 'object'),
  allocation_id TEXT NOT NULL REFERENCES allocations (id),
  open_questions JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(open_questions) = 'array'),
  artifact_refs JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(artifact_refs) = 'object'),
  pending_decision_id TEXT REFERENCES rsi_decisions (id),
  pending_attempt_id TEXT REFERENCES attempts (id),
  last_observation JSONB CHECK (last_observation IS NULL OR jsonb_typeof(last_observation) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (investigation_id, objective_revision)
    REFERENCES investigation_revisions (investigation_id, revision),
  CHECK ((pending_decision_id IS NULL) = (pending_attempt_id IS NULL)),
  CHECK ((status IN ('pending', 'suspended')) OR pending_decision_id IS NULL)
);

ALTER TABLE attempt_observations
  ADD COLUMN decision_id TEXT REFERENCES rsi_decisions (id);
CREATE INDEX attempt_observations_decision_idx
  ON attempt_observations (decision_id) WHERE decision_id IS NOT NULL;
