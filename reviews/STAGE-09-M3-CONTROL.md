# M3-2: the control arm is deleted, and the gap it leaves is written down

Answers defect M3-2. The defect was that the repository had no M3 control arm
while three tests read as if it did. The fix is not a working arm. The fix is
that the dead function is gone, the label tests are gone, and the gap is
stated here in the terms a control arm would have to satisfy.

Every number below was measured on this branch at `558d6ac`. Nothing under
`reports/evidence/` was read for anything but the two control member sources,
and nothing there was modified.

## 1. The decision, and why not the other one

Wiring was the obvious move and it does not survive contact with the code.
Four blockers, each measured rather than read.

**The study's selector cannot drive a control arm of two members.**
`_v1_use_policy_fallback` builds the STEP policy the use phase runs. It
refuses a family claimed by more than one member, by design, and a control
repertoire has two members per family. Executed through
`method_exec.run_step_out_of_process` against the repertoire the deleted
function returned:

```
eligible: ['seed-sw-ddmin', 'seed-sw-greedy']
selector RAISED MethodExecutionError step-failed: {'worker': {'status': 'error', 'data': {}, 'error': "ValueError: no single repertoire member is scoped to 'software' among ['software']"}, 'timed_out': False, 'wall_ms': 59}
```

A control arm needs a selector that chooses between the two authored methods.
Writing one is a new selection problem, and it is the C15 problem again: the
choice between ddmin and greedy is the thing the arm exists to isolate, and a
selector that picks `eligible[0]` picks by position rather than by anything
the world said.

**A `seed-` capability id never runs the member's own bytes.**
`trajectory._run_member` looks a member's `capability_id` up in
`seeds.SEED_CAPABILITIES` and, on a hit, calls `seeds.run_seed` in the host
and returns. The member's `method_source` is never staged. Demonstrated with a
member whose source raises if it is ever executed:

```
executed_source = 'ddmin'  queries = 4
the member source raised nothing: the host substituted run_seed
```

So the ids the deleted function used would have made the arm measure the
host's dispatch table rather than anything in its repertoire, and the record's
`executed_source` would be the method name rather than the bytes. This is the
verified-versus-executed-bytes defect again, in a new place. Any control arm
must carry capability ids the child will not shadow, which means the ids stop
being `seed-` ids, which means `seeds.SEED_CAPABILITIES` is not the roster it
was written to select from.

**The budget does not fit.** `run_study_v1` runs the use phase over three
worlds by two arms, six tasks each, and admits against hard-coded ceilings in
`_v1_admit`:

```
use combos 6 tasks per combo {0: 6, 1: 6, 2: 6}
acquired only      witness_queries   576 / 960 OK   execution_units   3996 / 5328 OK
with a control arm witness_queries  1152 / 960 OVER  execution_units   7992 / 5328 OVER
```

The acquired arm already spends 60 percent of the witness budget. A control
arm on every combination does not fit, and the ceilings are the study's, not
a per-run knob. Fitting it means halving the use tasks or raising the sheet,
which is a study-design decision with an owner, not a repair.

**Nothing would read the control record.** `task_utility_verdict` in
`experiments/ad01/s09_verdict.py` finds the authored arm through
`freeze["policy_identities"][arm]["artifact"]["origin"]`, and the study writes
no `policy_identities` at all. Against the last run's own `freeze.json`:

```
study freeze top-level keys: ['policy', 'repertoires']
has policy_identities: False
arms_by_origin(authored-control) -> ()
arms_by_origin(model-acquired)  -> ()
```

A control arm added to `run_study_v1` would produce records that no consumer in
this repository pairs against anything. `control_distinct` would accept the
records, if they existed, but no code calls it with them.

Any one of these would justify not wiring on its own. Together they mean the
arm needs a selector, a new id namespace, a budget change and a freeze schema,
and each of those is a decision for whoever owns the next study rather than a
defect repair.

## 2. What was deleted, and what it would have done

`_v1_control_repertoire` and `_v1_family_world` are removed from
`scripts/inv01_study.py`. Between them they were forty lines and one
production caller, which was zero. The function had three separate faults,
and each is now measured by a test rather than by prose:

The `method_source` named a symbol the child does not have. Staged and
executed, it fails:

```
RAISED MethodExecutionError member-failed: {'worker': {'status': 'error', 'data': {}, 'error': "NameError: name 'run_seed' is not defined"}, 'timed_out': False, 'wall_ms': 107}
```

The two members carried one byte-identical source, differing only in a
`params.method` field. `control_distinct` reads executed policy ids, the
strategy token in the body, and the returned candidate. On the recorded
`control-sw.json` bytes it finds no strategy at all:

```
control_distinctness._strategy_of({'method_source': <recorded source>}) == ''
```

An empty strategy on both arms reads as one strategy on both arms, which is
the E1 finding reproduced exactly.

The `source_digest` was the sha256 of the capability id, not of the source it
declared, so no digest in the record was a digest of the bytes.

## 3. The tests, and what each one can fail on

`tests/test_inv_r1_authored_control.py` keeps its filename and loses all three
label assertions. Each replacement was mutated to confirm it goes red.

| Test | Property | Mutation | Result |
|---|---|---|---|
| `test_an_authored_control_member_executes_under_the_child_contract` | the bytes run and reduce | member returns the task instead of reducing it | 3 failed |
| `test_the_two_control_members_are_byte_distinct_and_measure_differently` | distinct bytes and a visible difference | one source with two method values, the C15 shape | 2 failed |
| `test_the_distinctness_gate_reads_two_real_control_records_as_distinct` | the gate reads executed evidence | one source with two method values | 2 failed |
| all four | any of the above | member names `run_seed`, the recorded defect | 4 failed |

The budget is asserted against literals, not against the constant that chose
it. A member run at `max_queries=4` on `ad01-w0-within-sw-00` reduces to
8 ops under greedy and 3 under ddmin; at budgets 0 and 1 both strategies
return the same unreduced program, so a test that asserted only
`queries == BUDGET` would pass on a control that measured nothing. That
mutation initially passed all six tests and is why the candidate sizes are
pinned.

`test_the_current_control_repertoire_bytes_are_what_the_gate_refuses` keeps
the committed `control-sw.json` and shows the defect as a red gate: both of
its members raise `NameError` when executed, and the gate returns
`distinct: False` with a refusal. Nothing under `reports/evidence/` was
modified to make this true.

`test_the_seed_capabilities_are_authored_and_cover_both_families` keeps the
one label test that was accurate about the seeds themselves, and adds the
host-substitution measurement from section 1, so the reason a `seed-` id
cannot carry a control arm is in the test rather than only here.

## 4. The gap this leaves, in the terms a fix must meet

A control arm for `run_study_v1` is still the right thing to build, and the
argument in the deleted docstring was not wrong. Run 8's three acquired
executions with no baseline is a real reason to want one. What is now on
record is what building one costs.

1. Two members whose capability ids the child will not shadow, so their bytes
   are what runs. `trajectory._run_member`'s seed shortcut is the thing to
   route around, and the ids stop being `seed-` ids.
2. Two byte-distinct members per family, each naming its strategy in its own
   body, so `control_distinct` can read a strategy from each. The
   `method='ddmin'` form above satisfies this and executes on both families
   with matching digests.
3. A selector that chooses between them on something other than list position.
   The existing fallback refuses the case by design.
4. Budget for a second arm, from the sheet rather than from the current
   ceilings, or a narrower use-task set.
5. A `policy_identities` block, or another consumer, or the control records
   are written and never read.

Items 1 and 2 are demonstrated working in the tests in this commit. Items 3
to 5 are the study-design decisions that make it an arm rather than a
repertoire.

## 5. What was not touched, and one thing that moved under us

`experiments/ad01/control_distinctness.py` is not in this lane's diff.
`menu.open` is `True` and `defaulting_strategy` is empty both before and
after, so the regex at line 329 was not pressured.

The gate's full output did change during this lane, and not from anything in
this commit. Another live lane is rewriting `menu_answers_nothing` to read the
wrapper's own signature instead of the rendered prose, and its change moved
one field:

```
menu field              before                          after
open                    True                            True
defaulting_strategy     []                              []
defaulting_priority     ['ddmin_reduce', 'greedy_reduce']  []
wrappers_build          True                            True
bound                   identical                        identical
host_only               identical                        identical
```

`defaulting_priority` is the informational list, not a refusal, and the
`open` field that gates every live study is unchanged. It is recorded here
because a reader diffing the gate output across this commit will see it and
should know the cause. The rewrite itself is that lane's work and is not
assessed here.

`method_exec.py`, `seeds.py`, `trajectory.py` and everything under
`src/settlement/` are unchanged by this lane. `reports/evidence/` is
read-only throughout.
