-- Remove the five mission columns that no production code reads.
--
-- Migration 0019 put six things on the `investigations` row: the five below plus
-- `improvement_mode`. Five of them had no production reader anywhere in the
-- tree, and two of those facts are load-bearing rather than stylistic.
--
-- `retained_use` had no WRITER either, anywhere: not in `experiments/`, not in
-- `scripts/`, not in `src/`. The module named for retained use,
-- `experiments/representation/acquire/run.py`, builds its own retention record
-- against its own tables and never touched this column.
--
-- `permitted_experience` also disagreed with its own module. 0019 declared it
-- `DEFAULT '[]'`, a JSON list, while `mission._JSON_TYPES` required `dict`, and
-- `read_mission` laundered the disagreement with `dict(row[...] or {})` rather
-- than resolving it. Deleting the column deletes the disagreement, the coercion
-- and the two shapes that produced it.
--
-- The only writer of any of the five was `experiments/ad01/twodomain.py`, which
-- has zero production callers, no CLI and no `__main__`, and which wrote to a
-- disposable database S09ISO dropped at the end of the run. The production live
-- path, `scripts/invl02_live.py:1924`, records the charter and `improvement_mode`
-- and nothing else, so every real `investigations` row in a durable store holds
-- these columns at their 0019 defaults: `'{}'`, `'[]'`, `NULL`, `'[]'`, `NULL`.
-- Dropping them destroys no measurement that anything ever recorded.
--
-- A column nobody reads is not a record, it is a claim. The content these five
-- name is not lost: what is still open, what the mission may have learned,
-- which program is authorised to act, what it acquired and what it retains are
-- all read from the JSON document that actually owns them today, and the
-- program that admits an operation records its own identity in `in_flight`
-- (migration 0020) under a `FOR UPDATE` that `mission` and `run.py` both hold.
--
-- This is a forward correction rather than an edit to 0019. `apply_migrations`
-- records each file by name in `schema_migrations`, so a store that already
-- applied 0019 would keep the old definition while a fresh store got a new one
-- under the same name. Rewriting history would leave two schemas both claiming
-- to be the schema.
--
-- `in_flight` and `improvement_mode` stay, and `test_s09_policy_state_has_no_
-- competing_mission_columns` still holds: `investigations` remains the only
-- table carrying either of them.
ALTER TABLE investigations
  DROP COLUMN frontier,
  DROP COLUMN permitted_experience,
  DROP COLUMN active_program,
  DROP COLUMN acquired_artifacts,
  DROP COLUMN retained_use;