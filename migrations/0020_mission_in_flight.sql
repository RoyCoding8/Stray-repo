-- In-flight work on the mission entry: what is admitted, under which program,
-- and held for what reason.
--
-- This EXTENDS `investigations` alongside migration 0019's six fields, and for
-- the same reason. Three places could answer "what is in flight and how does
-- it resume": `s09_policy_state.accepted_action` held the admitted decision but
-- named neither the program that admitted it nor the inputs it was admitted
-- under, `continuation_docs` held a parallel continuation document with its own
-- key and its own `unresolved_ops`, and the settlement-side barrier suspended
-- an attempt while recording nothing about the operation it suspended.
--
-- The consequence was the one this program cannot afford. A restart reads the
-- admitted decision and knows what to run, but not WHICH PROGRAM admitted it or
-- under WHICH INPUTS. So a resumed boundary executes the accepted action under
-- whatever program the restarting process happens to hold, and the study
-- measures a different thing than it claims with no record that anything was
-- substituted. `in_flight` is where the program digest, the input identity and
-- the barrier go, so a restart reads the identity the operation was admitted
-- under rather than recomputing one.
--
-- It is a list, not a scalar, because an investigation may hold more than one
-- admitted operation at a time and each was admitted under its own program.
-- Each entry is keyed by its attempt id and is written whole by `mission`, so
-- the list is one field with one owner rather than a second table beside it.
ALTER TABLE investigations
  ADD COLUMN in_flight JSONB NOT NULL DEFAULT '[]';

-- The in-flight list, indexed for containment queries over its entries. The
-- column's reason for existing is the paragraph above: a restart must read the
-- identity an operation was admitted under rather than recompute one. A
-- barrier used to be a reason to hold work and needed an operation named to
-- resume at, which is what this column was introduced to provide; nothing
-- writes `barrier_ref` a second time now, so it is indexed as the recorded
-- state of an investigation rather than as a barrier's private channel.
CREATE INDEX investigations_in_flight_idx ON investigations
  USING gin (in_flight jsonb_path_ops);