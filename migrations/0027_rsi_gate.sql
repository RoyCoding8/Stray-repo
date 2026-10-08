CREATE TABLE rsi_gate_epochs (
  digest text PRIMARY KEY,
  tasks jsonb NOT NULL,
  budget jsonb NOT NULL,
  policy text NOT NULL,
  execution text NOT NULL CHECK (execution IN ('contained', 'benchmark')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rsi_gate_runs (
  id text PRIMARY KEY,
  epoch text NOT NULL REFERENCES rsi_gate_epochs (digest),
  parent text NOT NULL REFERENCES rsi_genomes (digest),
  candidate text NOT NULL REFERENCES rsi_genomes (digest),
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Exposure is spent before an anchor is run. An epoch reset cannot refund it.
CREATE TABLE rsi_anchor_uses (
  identity text PRIMARY KEY,
  task text NOT NULL REFERENCES rsi_tasks (digest),
  gate text NOT NULL REFERENCES rsi_gate_runs (id),
  created_at timestamptz NOT NULL DEFAULT now()
);
