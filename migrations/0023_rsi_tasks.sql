-- Task bytes and split membership are content-addressed, outside agent workspaces.
CREATE TABLE rsi_tasks (
  digest            text PRIMARY KEY REFERENCES artifact_versions (digest),
  name              text NOT NULL,
  split             text NOT NULL CHECK (split IN ('dev', 'val', 'anchor')),
  evaluator_version text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rsi_tasks_split ON rsi_tasks (split, name);

-- Historical T4 episodes used synthetic task digests. New episode admission
-- requires a published task; preserve historical rows instead of fabricating tasks.
CREATE TABLE rsi_verdicts (
  episode           text NOT NULL REFERENCES rsi_episodes (operation_id),
  evaluator_version text NOT NULL,
  operation_id      text NOT NULL UNIQUE REFERENCES operations (id),
  solution          text NOT NULL REFERENCES artifact_versions (digest),
  status            text NOT NULL CHECK (status IN ('passed', 'failed', 'timeout', 'infra_failed')),
  passed            boolean,
  detail            jsonb NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (episode, evaluator_version),
  CHECK ((status = 'passed' AND passed IS TRUE)
      OR (status = 'failed' AND passed IS FALSE)
      OR (status IN ('timeout', 'infra_failed') AND passed IS NULL))
);
