-- Pin model output before qualification so interrupted checks reuse its bytes.
CREATE TABLE rsi_synthesis_outputs (
  operation_id text PRIMARY KEY REFERENCES operations (id),
  parent text NOT NULL REFERENCES rsi_genomes (digest),
  evidence text NOT NULL REFERENCES artifact_versions (digest),
  trajectory text NOT NULL REFERENCES artifact_versions (digest),
  output text REFERENCES artifact_versions (digest)
);
