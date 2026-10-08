-- RSI layer: genome lineage. Bytes live in artifact_versions (scope rsi-genome);
-- this table records identity, harness and the parent edge.
CREATE TABLE rsi_genomes (
  digest     text PRIMARY KEY REFERENCES artifact_versions (digest),
  parent     text REFERENCES rsi_genomes (digest),
  harness    text NOT NULL,
  origin     jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rsi_genomes_parent ON rsi_genomes (parent);

-- One agent-run of a genome on a task. The operation row holds the budget
-- and receipt; this row is the RSI view of it.
CREATE TABLE rsi_episodes (
  operation_id      text PRIMARY KEY REFERENCES operations (id),
  genome            text NOT NULL REFERENCES rsi_genomes (digest),
  task              text NOT NULL,
  status            text NOT NULL CHECK (status IN
                      ('completed', 'failed', 'infra_failed', 'timeout', 'over_budget')),
  tokens            jsonb,
  seconds           double precision NOT NULL,
  trajectory        text NOT NULL REFERENCES artifact_versions (digest),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rsi_episodes_genome_task ON rsi_episodes (genome, task);
