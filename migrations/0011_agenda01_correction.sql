CREATE TABLE agenda_traj_state (
  trajectory TEXT PRIMARY KEY,
  refused JSONB NOT NULL DEFAULT '[]',
  admitted_fx JSONB NOT NULL DEFAULT '{}',
  tick INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE agenda_outcomes ADD COLUMN scored BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE agenda_disposition_events ADD COLUMN decided_by JSONB;
