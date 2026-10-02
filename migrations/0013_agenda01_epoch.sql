-- 0013: agenda paid-epoch starts at zero so due dates equal
-- pre-decision epoch plus delay with no tick-zero anomaly.
ALTER TABLE agenda_cursors ALTER COLUMN epoch SET DEFAULT 0;
