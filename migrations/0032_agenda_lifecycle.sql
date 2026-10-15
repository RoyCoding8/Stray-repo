ALTER TABLE rsi_agendas
  DROP CONSTRAINT rsi_agendas_status_check;

ALTER TABLE rsi_agendas
  ADD CONSTRAINT rsi_agendas_status_check
  CHECK (status IN ('active', 'complete', 'stopped', 'suspended'));
