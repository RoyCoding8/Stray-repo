CREATE TABLE rsi_proposals (
  operation_id text PRIMARY KEY REFERENCES operations (id),
  parent       text NOT NULL REFERENCES rsi_genomes (digest),
  evidence     text NOT NULL REFERENCES artifact_versions (digest),
  status       text NOT NULL CHECK (status IN ('completed','failed','infra_failed','timeout','over_budget','invalid')),
  child        text REFERENCES rsi_genomes (digest),
  trajectory   text NOT NULL REFERENCES artifact_versions (digest),
  detail       text NOT NULL DEFAULT '',
  created_at   timestamptz NOT NULL DEFAULT now(),
  CHECK ((status = 'completed' AND child IS NOT NULL) OR (status <> 'completed' AND child IS NULL))
);
-- A settled proposal has one output, even if recording is interrupted.
CREATE UNIQUE INDEX rsi_genomes_proposal_origin ON rsi_genomes ((origin->>'origin'))
  WHERE origin->>'origin' LIKE 'proposal:%';
