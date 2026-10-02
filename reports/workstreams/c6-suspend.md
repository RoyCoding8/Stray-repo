# C6 — suspend and resume on the mission entry

Lane C6 of the milestone-C build. Base `c8c58bf`, branch `wt/c6-suspend`.
Offline, no live model calls, no network, fixture gateway only.

## The property this lane exists for

An operation that crosses a restart keeps the program identity and the input
identity it was admitted under. Not a recomputed one, not a default.

Before this, nothing recorded either. `s09_policy_state.accepted_action` held
the admitted decision, so a restart knew *what* to run and not *under which
program*. A resumed boundary therefore executed the accepted decision under
whatever program the restarting process happened to hold, and the study's rows
showed a clean run of a program it no longer ran. That is how a study ends up
measuring a different thing than it claims, with no record that anything was
substituted.

## One resume owner

**There is now exactly one resume owner: the mission entry's `in_flight`
column on `investigations`**, written only by `experiments/ad01/mission.py`.

The three that answered "what is in flight and how does it resume" are routed
at it rather than left beside it:

| Before | Now |
|---|---|
| `s09_policy_state.accepted_action` (what to run, never which program) | `admit_operation` records the program digest and input identity at admission, before any effect runs |
| `context.resume_package` → `continuation_docs` (a parallel continuation document with its own `unresolved_ops`) | `resume_package` reports `in_flight` from the entry; `continuation` is still the composition's *position*, which is what it is for, but it can no longer overtake the entry |
| `run.suspend_for_barrier` (suspended an attempt, named no operation) | records the barrier against the entry's in-flight operation, and refuses when there is none |

`tests/test_inv_c6_suspend_resume.py` pins this structurally rather than by
count: `information_schema` shows `in_flight` carried by exactly one table,
`resume_package` reports the operation with **no** continuation document present
at all, and a continuation document claiming a different `unresolved_ops` list
does not move it.

## What suspend and resume do

- `mission.admit_operation` — at admission, before the effect runs. Required
  program digest; a caller naming no program gets the seed program's digest,
  which is what will actually execute the decision, not a convenient default.
  Idempotent on `(seq, attempt_id)`.
- `run.suspend_for_barrier` — marks the operation `suspended` with its
  `barrier_ref`, then suspends the attempt. Refuses an attempt with no admitted
  operation, leaving it `running`.
- `mission.resume_operation` — reads identities back and marks them `restored`.
  **Executes nothing and writes no effect record.** `restored_at` is stamped
  once, so restoring twice is one restoration.
- `trajectory.resume_campaign` — restores first, then runs, and reports
  `resumed_in_flight`: what crossed the restart and under which program.

The restore-before-run split is the part that matters. Restoration is a read
of recorded identity; execution is what marks work done. A resume that
executed the work would be re-running it, which is how a crash believed
recovered becomes a double-counted effect.

## Migration 0020

`migrations/0020_mission_in_flight.sql` (number verified unused by listing the
directory; 0019 was lane C1's).

`ALTER TABLE investigations ADD COLUMN in_flight JSONB NOT NULL DEFAULT '[]'`,
plus a GIN index on `jsonb_path_ops`.

**Extended `investigations`, did not add a table.** Same reasoning as C1's
0019, and the same reason `s09_policy_state` is the named rival: it is keyed
`(investigation_id, seq)`, so a mission there is reachable only at some seq.
A list rather than a scalar because an investigation may hold several admitted
operations, each admitted under its own program. One column, one owner — not a
fourth aggregate.

Lane C1's migration and C2's freeze are untouched.

## What I did NOT build, and why

**A guard that refuses a task/capability substitution in `execute_pending`.** I
built one, and it broke three inherited tests (`test_s09m1_state`,
`test_s09m34_cycle`) that admit a decision naming a *transfer* target and
execute against the dev task. That is deliberate: the boundary's own fence
refuses a protected transfer target, and that refusal is the attributable,
recorded result a study needs. Refusing earlier would replace it with an
unattributable error raised before any effect was attempted — strictly worse
evidence. So the program digest is recorded at admission, checked for shape,
and copied into the effect record, and the run itself is not second-guessed.

## Tests

`tests/test_inv_c6_suspend_resume.py`, mine alone. 6 passed.

| Test | Proves |
|---|---|
| `test_the_asserted_digests_are_the_real_ones` | the literals are derived from the bytes, so a later edit cannot leave a stale identity asserted |
| `test_pending_retains_program_identity_across_restart` | phase A admits and `os._exit(0)`s; phase B is a **separate interpreter** that resumes. Program digest, input identity and decision digest all match literals, then survive into the effect record |
| `test_resume_restores_pending_not_yet_effects` | status stays `accepted`, `effect_record` stays `NULL`, zero boundary observations, and a second restore is one restoration |
| `test_the_continuation_document_is_no_longer_a_resume_owner` | one carrier table; the package answers with no document present; a conflicting document does not move it |
| `test_suspend_for_barrier_routes_at_the_mission_entry` | the barrier lands on the entry with its ref, the attempt suspends, identity unchanged, and an unheld attempt is refused with the attempt left `running` |
| `test_resume_refuses_a_campaign_it_did_not_mint` | the id-mismatch guard still fires (see the inherited test below) |

Every program byte is this lane's own. No other lane's fixture is reused.

## One inherited test now fails, and I did not paper over it

`tests/test_p2c_ad01_resweep.py::test_resume_campaign_id_mismatch_refuses`.

It calls `resume_campaign` with `"dbname=ec02test_p2c_unused"` — a database
that does not exist — to prove the id-mismatch guard raises `unexpected
campaign`. A resume that restores from the mission entry must read a real
store, so the restore raises `OperationalError` first.

The guard is **not weakened and not removed**; it still raises
`ValueError: resumed unexpected campaign`, now pinned against a store that
exists in `test_resume_refuses_a_campaign_it_did_not_mint`. The inherited test
is left failing and visible rather than `xfail`ed, `skipped`, or rewritten:
its stand-in "a store" is no longer a store, and that is a real consequence of
this change that a reviewer should see.

## Gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/c6.jsonl; \
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/c6-suspend && \
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/c6-suspend/src \
  timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_inv_c6_suspend_resume.py -q -p no:cacheprovider'

......                                                                   [100%]
6 passed in 7.38s
S09ISO: dropped 13 database(s) for this run
```

## Blast radius

13 files touching `mission`, `trajectory`, `context` and `run`:

```
143 passed in 223.45s (0:03:43)
```

Included: `test_mission_entry.py` (C1's deliverable), `test_s2_context.py`,
`test_dev02_episode.py`, `test_evidence_epoch.py`, `test_ad01_traj.py`,
`test_inv_a_chain.py`, `test_inv_a_counterexamples.py` (A5's seven tamper
cases, including the pending-resume case this lane had to satisfy),
`test_s09m1_driver.py`, `test_s09m1_state.py`, `test_s09o_cycle.py`,
`test_p3e_entry.py`, `test_invc1_lifecycle.py`.

A second sweep over the `run`/composition callers: 4 failed, 81 passed. Three
of the four are **pre-existing**, each verified by running the same test in
the clean main worktree at `c8c58bf`:

- `test_alee_learner.py::test_cli_run_doubled_and_use_fresh_process`
- `test_s09m34_cycle.py::test_full_deterministic_cycle_with_provider_double_only`
- `test_s09_run_use_policy.py::test_a_real_decision_consumer_is_refused_not_guessed_at`

The first two carry the documented literal
`refused: execution needs explicit authority and identity`
(`method_exec.py:1413`), caused by `improve_channel.py:1013` forwarding no
`dsn` and no `allocation_id` — A5's deferred obligation, and `improve_channel.py`
is another lane's file. The fourth asserts `2 == 1` on operation count at base.

The fourth failure in that sweep is the `p2c` test above, which is mine.

Ids recorded rather than chased, as instructed.

## Files

- `migrations/0020_mission_in_flight.sql` (new)
- `experiments/ad01/mission.py` (modified — `InFlightOperation`,
  `admit_operation`, `read_in_flight`, `held_operation`, `resume_operation`,
  `release_operation`, `seed_program_digest`)
- `experiments/ad01/trajectory.py` (modified — `accept_action`,
  `_admitting_program_digest`, `execute_pending`, `_s09_mark_incorporated`,
  `mission_held`, `resume_campaign`, `_settled_attempts`)
- `src/settlement/context.py` (modified — `resume_package`, `mission_in_flight`,
  `_s_next_decision`)
- `src/settlement/run.py` (modified — `suspend_for_barrier`,
  `_attempt_investigation`, `_hold_on_mission_entry`)
- `tests/test_inv_c6_suspend_resume.py` (new, mine alone)

`git diff --name-only c8c58bf HEAD -- reports/evidence/` is **empty**.

TDD throughout: five tests written and watched fail first, one more added when
the inherited `p2c` test surfaced the store dependency. Two real defects behind
them — a resume whose restore ran after `run_campaign` and so could not report
what was pending, and a task-identity guard that replaced attributable
boundary refusals with unattributable ones.