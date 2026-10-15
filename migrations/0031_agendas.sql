CREATE TABLE rsi_agendas (
  agenda_id TEXT PRIMARY KEY,
  charter JSONB NOT NULL,
  charter_digest TEXT NOT NULL,
  revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
  turns INT NOT NULL DEFAULT 0 CHECK (turns >= 0),
  source_epoch BIGINT NOT NULL DEFAULT 0 CHECK (source_epoch >= 0),
  memory_revision BIGINT NOT NULL DEFAULT 0 CHECK (memory_revision >= 0),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'complete', 'stopped')),
  flight JSONB,
  last_result JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
