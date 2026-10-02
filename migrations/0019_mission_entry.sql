-- The mission entry: one row per investigation holding six things.
--
-- This EXTENDS `investigations` (migrations/0001_schema.sql), the table that
-- already owns an investigation's identity and its objective. It does not add
-- a table beside `s09_policy_state`: that table is keyed
-- (investigation_id, seq) and answers "what did boundary N decide", so a
-- mission placed there is reachable only at some seq, which is a second owner
-- answering "what is this investigation trying to do" -- the duplicate
-- authority this entry removes.
--
-- All six live in one row, so no field needs a join to read another:
--
--   frontier              what is still open, and what counts as done
--   permitted_experience  what the mission is allowed to have learned
--   active_program        the program currently authorised to act
--   acquired_artifacts    artifacts this mission acquired
--   retained_use          which retained artifact is in use, and where
--   improvement_mode      whether the mission is operating or improving
--
-- `objective` and `scope` already exist on the row; the entry's declaration
-- reads them rather than restating them. `improvement_mode` is constrained so
-- an unrecognised mode is a refusal rather than a silently inert mission.
ALTER TABLE investigations
  ADD COLUMN frontier JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN permitted_experience JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN active_program JSONB,
  ADD COLUMN acquired_artifacts JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN retained_use JSONB,
  ADD COLUMN improvement_mode TEXT NOT NULL DEFAULT 'operate'
    CHECK (improvement_mode IN ('operate', 'improve'));