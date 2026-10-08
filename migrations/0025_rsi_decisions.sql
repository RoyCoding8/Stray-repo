-- Attribution and replay of choices, outside the editable genome.
CREATE TABLE rsi_decisions (
  id         text PRIMARY KEY,
  kind       text NOT NULL,
  actor      text NOT NULL CHECK (actor IN ('ai', 'fixed')),
  subject    text NOT NULL,
  data       jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
