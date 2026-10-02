# Lane B13b — the E2 method is resolved per family, and the gate's red is not mine

Branch `wt/b13b-replseed`, base `a6687d6`. Files touched:
`experiments/ad01/e2_replication.py`, `tests/test_inv_b13b_replseed.py`,
this report. Nothing under `reports/evidence/` was read into or written to.

## The finding that changes the brief

The brief says three tests fail on absolute magnitudes of 2.0 and 1.0, and that
the previous lane's diagnosis of those was right. **At this HEAD, 25 tests
fail, and they are not the magnitude tests.** I measured the cause rather than
accepting the framing, and the cause is a different lane's repair:

`method_exec.run_step_out_of_process` requires a `dsn`, an `allocation_id` and
an `operation_id`, and refuses without all three (`method_exec.py:1412`).
`s09_e2_scored._execute` calls it with none of them
(`s09_e2_scored.py:466`). So `Score.measure` returns
`unscored: execute: …` for **every** policy on **every** family, and every test
that needs a real reading fails.

Proof by isolation. I swapped only `method_exec.py` for its version at
`1e0dd44^`, leaving `s09_e2_scored.py` and all three test files byte-identical,
and reran:

| source | result |
|---|---|
| HEAD `method_exec.py` | 25 failed, 59 passed |
| `1e0dd44^` `method_exec.py` | **4 failed, 80 passed** |

One file, one refusal, 21 of the 25 failures. The remaining 4 are the genuine
magnitude tests.

A2's report (`reports/workstreams/a2-nodsn.md`) claims "every `trajectory` call
site that reaches these executors already passes a dsn". That census is false
for the `s09_e2_scored` path: five callers pass no authority at all —
`learner.py:866`, `s09_bound_use_proof.py:260`, `experience_axis_run.py:332`,
`improve_channel.py:1013`, and `s09_causal_proof.py:654`. A2's own
`tests/test_inv_a_no_dsn_execution.py` passes (7 passed here), so the seam is
closed and the callers are the gap. **I did not repair it.** The fix belongs to
A2 or to the campaign that owns the durable route; adding a second execution
path inside a qualification gate would delete A2's recorded repair, which is
the standing rule in AGENTS.md.

## Defect 1 — the replication leg hardcodes the software seed

Four authored policies in `e2_replication` named `seed-sw-ddmin` in their own
bytes, while `CONTROL_PREFIX` already maps `{"software": "seed-sw-",
"graph": "seed-gr-"}`. A graph target was asked for a method absent from its
own repertoire and `assessment_profile.dispatch` refused the action. Each
policy now takes its method from the view's own `eligible_methods`, which
`eligible_for` fills through `control_candidates` — the single reader of
`CONTROL_PREFIX`. No second lookup.

Measured through real brokered child execution, not asserted from a docstring:

| policy | graph target | software target |
|---|---|---|
| `READS_THE_VERDICT` | `seed-gr-ddmin` | `seed-sw-ddmin` |
| `PROMPTED_SHAPE_READER` | `seed-gr-ddmin` | `seed-sw-ddmin` |
| `ECHOES_WITHOUT_READING` | `seed-gr-ddmin` | `seed-sw-ddmin` |
| `IGNORES_THE_VIEW` | `seed-gr-ddmin` | `seed-sw-ddmin` |

Under flipped verdicts `PROMPTED_SHAPE_READER` names `seed-gr-greedy`, so the
read reaches the method rather than a fixed constant. A software method on a
graph target is still refused: `dispatch` returns `accepted=False` with no
candidate for `seed-sw-ddmin`, and `accepted=True` with a candidate for
`seed-gr-ddmin` in the same test.

## Defect 2 — `READS_THE_VERDICT` indexed `ops` unconditionally

A graph task carries `edges` and no `ops`. The reader now reads whichever unit
list the family carries.

**A third defect sat behind it, and B13's own fix did not repair it.** B13's
repair called `marker.get("id")` on every unit. A graph edge is a `[u, v]`
pair, so `.get` is an `AttributeError` inside the child and the reading came
back `unscored` again, for a third time and under a different message. The
evidence is a real receipt: `outcome: "failure"`, `error:
"AttributeError: 'list' object has no attribute 'get'"`. My `_marker` helper
reads a dict's `id`/`key` and joins a pair as `"u-v"`. Measured markers:
graph `"0-1"`, software `"c"`.

## Stale or regression — the ruling

**Both, and the split is not the one the brief drew.** The 4 magnitude failures
are stale; the 21 others are a live regression in `s09_e2_scored`'s call
contract, not in this lane's code.

The stale ones. `d17b5a7` deleted the `QUALITY` constant, and with it every
score of exactly 1.0 or 2.0. On the replica's target `ad01-w0-within-sw-00`
the initial measure is 10, `seed-sw-ddmin` returns 3 and `seed-sw-greedy`
returns 5, so the maximum reachable reduction is exactly 0.7 and the maximum
reachable score is 1.7. I measured this by running the world's own seed
capabilities rather than restating the number. Under the pre-gate instrument
`qualify_instrument` returns reader 1.7, blind 0.7, echoer 0.7, prompted-shape
reader 1.7. Separation holds at 1.7 against 0.7; the absolute magnitudes are
unreachable. **I did not restate these four contracts.** Correcting a stale
magnitude in `test_s09_e2_replication.py` and `test_ad01_experience_axis.py`
is a contract change outside this lane's owned paths, and while they were red
for the magnitude reason they are red for the authority reason first. They go
green the moment `_execute` carries authority, and a test that pins 1.7 in the
meantime would encode today's unreachable value — exactly the mistake that
reverted B13. So my tests assert the reachable magnitudes directly
(`ddmin` 0.7, `greedy` 0.5, max 0.7) and leave those four alone.

## The single-valued-constant finding

The brief predicted `graph:dev+transfer` would arm a single-valued constant.
**Measured, that prediction is wrong on the stream and right on the
predicate.**

The stream is not constant. Across all six powered graph clusters and both
methods, every stream holds both verdicts: the union is
`["not_preserved", "preserved"]`, 12 of 12 streams varying. The brief's
"preserved on every source task" holds for `ad01`, not for the panel.

The predicate is vacuous anyway, which is the finding that matters. On
`panel-w0-dev-gr-00` with ddmin, the membership test
`"not_preserved" in verdicts` is **True under both exposures** — scored True,
alternate True, moved **False**. Counting losses does move: **7 scored against
1 alternate** on `panel-w0-dev-gr-00`, and **5 against 3** on
`panel-w0-transfer-gr-01`. So `PROMPTED_SHAPE_READER` would read nothing on
`panel-w0-dev-gr-00` or `panel-w0-transfer-gr-01`, and
`panel_variation.COUNT_READS_THE_VERDICTS` is the predicate that survives.
Those two panels are in `graph:dev+transfer`, the smallest of the **three**
powered panels; the vacuity measured here is a property of those two rows, not
of powered panels in general, and this lane measured nothing about
`graph:within+transfer` or `graph:dev+within+transfer`. **Not fixed.** `panel_variation` is another lane's
record and repairing it inside a qualification gate would delete it. Recorded
in `test_the_membership_reader_is_vacuous_on_the_powered_graph_panel`.

## The predicate defect recorded, not fixed

`panel_variation.COUNT_READS_THE_VERDICTS` at `panel_variation.py:523-533`
counts losses (`losses * 2 >= len(rows)`) where
`e2_replication.PROMPTED_SHAPE_READER` asks for membership. On a stream that
already holds both verdicts the membership test is constant under either
exposure and reads nothing, which is the vacuity measured above. The repair is
that lane's to make, on the record that reports the panel. Left alone, as
instructed. Adding a third copy of the policy to a qualification gate would
only add a reader to keep in step.

## Gate

    wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/b13b-full2.jsonl; cd /mnt/d/AI/Agent-Society-v2/.worktrees/b13b-replseed && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b13b-replseed/src timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b13b_replseed.py tests/test_s09_e2_scored.py tests/test_s09_e2_replication.py tests/test_ad01_experience_axis.py -q -p no:cacheprovider'

    25 failed, 71 passed in 53.14s (0:00:53)

My own file: **12 passed**. The 25 failures are the pre-existing authority
defect, identical by id to the clean base at `a6687d6` — I diffed the failure
sets and they match exactly, so this lane introduces no regression.

New tests, written first and watched fail:

| source | result |
|---|---|
| my file, `a6687d6` source (both defects present) | 6 failed, 6 passed |
| my file, B13's fix only (no `_marker`) | 5 failed, 7 passed |
| my file, my source | **12 passed** |

That middle row is why the `_marker` helper exists: B13's fix alone leaves five
red, including the graph method literal and both unit-shape tests.

## What the next lane inherits

21 of the 25 red tests clear when `s09_e2_scored._execute` passes a `dsn`, an
`allocation_id` and an `operation_id` down to `run_step_out_of_process`, the
way `construct.py:404` already does. That is one boundary, in a file this lane
does not own, and it is a live regression rather than a stale contract. I have
not touched it. The four magnitude tests then need their literals corrected to
1.7 and 0.7, and that correction should be made in the same change so nobody
reads the authority repair as a magnitude fix.

I could not run the wider suite: the resource policy caps this lane at one
pytest process on a named file list, so nothing outside the four gate files
was measured, and I am not claiming it.