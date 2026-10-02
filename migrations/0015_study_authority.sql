CREATE TABLE store_identity (
  id INT PRIMARY KEY CHECK (id = 1),
  fingerprint UUID NOT NULL DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO store_identity (id) VALUES (1);

CREATE TABLE study_authority (
  study_root TEXT PRIMARY KEY,
  allocation_id TEXT NOT NULL REFERENCES allocations (id),
  authorized BIGINT NOT NULL CHECK (authorized > 0),
  ceilings JSONB NOT NULL DEFAULT '{}',
  correction_budget INT NOT NULL DEFAULT 2 CHECK (correction_budget >= 0),
  store_fingerprint UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE study_corrections (
  study_root TEXT NOT NULL REFERENCES study_authority (study_root),
  decision_key TEXT NOT NULL,
  used INT NOT NULL DEFAULT 0 CHECK (used >= 0),
  failure JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (study_root, decision_key)
);

CREATE TABLE study_phases (
  study_root TEXT NOT NULL REFERENCES study_authority (study_root),
  decision_id TEXT NOT NULL,
  phase TEXT NOT NULL CHECK (phase IN ('diagnostic', 'validation')),
  operation_id TEXT NOT NULL REFERENCES operations (id),
  ref_digest TEXT NOT NULL DEFAULT '',
  detail JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (study_root, decision_id, phase)
);
