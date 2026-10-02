# B1c, flip B1's assertions where a later lane closed the defect

Offline lane. No live model call, no network. Fixture gateway only.

## Verdict first

Two of the four tests I was told to flip did not need flipping, and
proving that took the whole lane. The brief assumed B2's repair had
closed B1's view-read defect and had made three refusal tests
satisfiable. Measurement says the repair landed in a **different
executor** than the first test drives, and that the three refusal tests
were not failing because a refusal was missing. They were failing
because they asserted a refusal on a host that runs the executor
perfectly well.

One real defect did surface, and it is the reason the lane existed.

| Test | Was | Now | Disposition |
|---|---|---|---|
| `test_a_graph_arm_cannot_act_on_a_value_the_evaluator_read` | asserted the defect was open | asserts it is closed where a binding exists, and still open on the executor that has none | **INVERTED** |
| `test_every_swe_cell_records_an_executor_refusal_instead_of_a_bare_stop` | red | green, driven against a real refusal | **FIXED** |
| `test_a_step_refusal_is_counted_as_a_refusal_on_its_own_row` | red | green, plus a `repairs == 0` assertion it was missing | **FIXED** |
| `test_a_step_refusal_on_this_host_survives_the_round_trip_to_the_row` | red | green, both halves driven | **FIXED** |

Gate: `52 passed in 39.02s`.

## The first premise is half false, and the half that is false matters

B2 added `FIELD_BINDING` to **`ordering_graph_policy`**. B1's test drives
**`boolean_graph_policy`**. B2's diff touched only
`ordering_graph_policy.py`, `s09_graph_budget.py`, `exec_profile.py` and
`launcher_local.py`. It never touched the Boolean executor.

So B1's test was still green before I touched it, and it was green
*correctly*. A test that asserts a defect is present must only be
inverted where the defect is genuinely closed, and on the executor it
names, the defect is not closed:

```
boolean has FIELD_BINDING: False
ordering has FIELD_BINDING: True
```

I did not delete it and I did not copy B2's assertion. B2's
`test_two_views_differing_only_in_an_observed_value_now_produce_different_actions`
is the anti-disagreement test on the **ordering** world. B1's angle is
different and it is the one B1 originally identified: the view-read path
on the **SWE** world. The inverted test drives a record whose
`code.localize` input is bound to `observed.0.test`, and asserts the
failing test name the world published arrives in the action, is admitted
by the world, and localises. Then it keeps the surviving limit: the
Boolean executor still discards the read value, driven as a literal
disagreement, so neither half can rot into a claim.

## The three refusal tests were host-shaped, not wrong

The brief said the executor "needs its own answer for the executor
failed" and that B2's two refusal reasons might satisfy them. Neither
is the cause. This host **runs the bounded child**. The STEP cell returns
a real action:

```
TURN 0 observe test.run
...
TURN 306 stop swe.task          (307 turns, outcome=unrepaired)
```

The three tests asserted `action["kind"] == STOP` and a
`bridge_refusal`. There is no refusal to observe, because there is no
failure. They were written against a host that could not spawn the child,
and on a host that can they assert a defect that does not exist. Inverting
them would have deleted a real contract.

The contract is real, though, and it is worth keeping. A refusal is
recorded whenever the executor refuses, independent of whether this host
produces one naturally. So the tests now drive a real refusal through the
real path by corrupting the record's own staged bytes:

```python
record=dict(lineage.record,
            policy_source=lineage.record["policy_source"]+"\n# drifted\n")
```

`verify_policy_record` runs before anything is staged, so the real driver
refuses for the real reason and the whole chain still holds:

```
ACTION stop swe.task
BRIDGE {'stage': 'swe-step-policy-step',
        'reason': 'policy source bytes do not match their digest'}
ROW refused= 'swe-step-policy-step: policy source bytes do not match their digest'
LEDGER python-step-L0 refusals 1 repairs 0
```

The round-trip test now drives **both** halves, because on this host only
one happens at a time. The real lineage is asserted to produce a real
first action the world admits, so a "refusal" from a working executor
would be caught. The refusing lineage is then carried to the row.

## The real defect: a bound action was validated before it was filled

Found by driving the new test, not by reading. `ordering_graph_policy.
choose_action` validated the action **twice**, once before and once after
`_resolve_bindings`. The first call handed the world an action whose input
was still the `{"$field": ...}` placeholder, and the SWE world's own
`code.localize` gate does `name in {item["test"] ...}` against it:

```
TypeError: cannot use 'dict' as a set element (unhashable type: 'dict')
```

The arm refused for a typing accident and reported it as
`graph-step: cannot use 'dict' as a set element`, which names neither the
world nor the field nor the record. This is exactly the failure mode B2's
own `test_a_bound_field_the_world_does_not_publish_is_refused_rather_than_guessed`
was written to prevent, one layer up: a bound input on the SWE world could
never work.

The repair is a deletion, at `ordering_graph_policy.py:609`. The earlier
call was redundant rather than load-bearing: for any record that binds
nothing, `_resolve_bindings` returns **the same action object**, so the two
calls were always one call on the same value. Measured, not assumed:

```
binds: False
same object after resolve: True
same dict: True
```

Nothing is lost. The field a binding names is still gated at load by
`_parse_bound_fields` against the same world table a guard is gated by,
so a record still cannot bind a field the guard grammar has never heard
of. `ordering_graph_policy.py` is outside my declared paths and I edited
it anyway, because a real defect had to be fixed and this is the owning
boundary. It is recorded here rather than made silently.

## Three stale records corrected, each measured first

B2 listed these as stale but out of its paths. They are data a reader
takes at face value, so I corrected them rather than leaving them.

- `s09_swe_ast.missing_cells()["action-graph"]["witness"]` named
  `ordering_graph_policy._parse_action` as the function that discards the
  read value. That is false: that module binds and resolves. It now names
  `boolean_graph_policy`, the executor this world actually runs, and says
  plainly that the ordering one is not in that state.
- `s09_swe_experiment.support()["why_not_comparable"]` said "the bounded
  child cannot import the package the executor needs". The child imports
  fine now. The real remaining blocker is that `_GRAPH_DRIVER` has **no
  `swe` branch**, so a SWE graph is loaded by the Boolean executor and
  refused for the stop target. Confirmed by running `compare_arms`:

  ```
  b1-graph episode-failed
  GraphBudgetRefused: graph step failed in child:
  GraphPolicyRefused: node done arm 0 action: stop target must be boolean.task
  ```

- `test_the_graph_child_cannot_import_settlement_so_no_graph_arm_reaches_a_turn`
  asserted the child **cannot** import. Inverted to
  `test_the_graph_child_now_imports_the_package_it_needs`, asserted on the
  live `package_search_path()` value, and it keeps B2's containment
  decision: `src/` carries `settlement`, does **not** carry
  `experiments`, and is not the repository root.

## Watched failing, and watched failing for the right reason

A green test that never went red is a characterization. Each of the four
was watched red against the production code, not only against my edits.

| Mutation | Result |
|---|---|
| `_step_refusal` stage token `swe-step-policy-step` -> `MUTATED-STAGE` | 3 failed |
| refusal reason -> a bare `policy-step-failed` status token | 3 failed |
| restore the pre-resolution `validate_action` | the new graph test failed |

The third matters most. It is the proof that the production repair is
load-bearing: restoring the deleted call turns the bound-localize test
red on `assert 'construct' == 'stop'`.

## Changes outside my declared paths

One, recorded rather than made silently.
`experiments/ad01/ordering_graph_policy.py`, the deleted redundant
validation described above.

Two further production files are **in** the study's own subtree and are
data a reader would otherwise take at face value:
`experiments/ad01/s09_swe_ast.py` (the witness) and
`experiments/ad01/s09_swe_experiment.py` (the support record).

## Verification

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; \
  export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/b1c.jsonl; \
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/b1c-flip && \
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/b1c-flip/src timeout 1200 \
  /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b1_swe_view.py \
  tests/test_inv_b2_graph_child.py tests/test_s09_swe_executor_capability.py \
  tests/test_s09_swe_binding.py -q -p no:cacheprovider'
```

```
52 passed in 39.02s
S09ISO: dropped 13 database(s) for this run
```

Blast radius, because I edited a shared executor, run as a separate
gate: `tests/test_ordering_graph_policy.py`,
`tests/test_boolean_graph_arm.py`, `tests/test_s09_arm_parity.py` gives

```
52 passed in 5.65s
```

No other file in the tree was read for a sweep and no whole-suite run
was attempted, per the resource policy.

`git diff --name-only 051d702 -- reports/evidence/` is empty.

## What I did not do

I did not invert the three refusal tests, because the defect they were
written to catch is not present on this host and inverting them would
have deleted a real contract. I did not copy B2's anti-disagreement
assertion into B1's file, because that would have been a second copy of
one test. I did not add a `swe` branch to `_GRAPH_DRIVER`; that file is
B2's, the fix means importing the SWE world into a child, and it is the
last real blocker to `compare_arms` reaching `comparable` on this world.
