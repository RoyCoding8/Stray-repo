CREATE TABLE worker_leases (
  attempt_id TEXT PRIMARY KEY REFERENCES attempts (id),
  holder TEXT NOT NULL DEFAULT '',
  ownership_generation INT NOT NULL CHECK (ownership_generation > 0),
  state TEXT NOT NULL DEFAULT 'active'
    CHECK (state IN ('active', 'expired', 'revoked')),
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
