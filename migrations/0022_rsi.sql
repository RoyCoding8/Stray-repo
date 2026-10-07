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
