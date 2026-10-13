CREATE TABLE rsi_memory_clock (
  id SMALLINT PRIMARY KEY CHECK (id = 1),
  revision BIGINT NOT NULL CHECK (revision >= 0)
);
INSERT INTO rsi_memory_clock (id, revision) VALUES (1, 0);

CREATE TABLE rsi_memory_experiences (
  observation_id BIGINT PRIMARY KEY REFERENCES attempt_observations (id),
  revision BIGINT NOT NULL UNIQUE CHECK (revision > 0),
  source_digest TEXT NOT NULL,
  scope JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(scope) = 'object'),
  visibility TEXT NOT NULL CHECK (visibility = 'learner')
);

CREATE TABLE rsi_memory_claim_versions (
  claim_id TEXT NOT NULL,
  version INT NOT NULL CHECK (version > 0),
  revision BIGINT NOT NULL UNIQUE CHECK (revision > 0),
  kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN
    ('untested', 'supported', 'challenged', 'withdrawn', 'superseded')),
  text TEXT NOT NULL,
  scope JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(scope) = 'object'),
  support JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(support) = 'array'),
  opposition JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(opposition) = 'array'),
  derived_from JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(derived_from) = 'array'),
  supersedes JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(supersedes) = 'array'),
  PRIMARY KEY (claim_id, version)
);
