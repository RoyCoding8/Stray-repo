# B18 — the contract view already carried what the guard reads

Offline lane. No live model call, no network, no fixture gateway. Every
child driven here is a real `LocalLauncher` dispatch on this host.

## The brief's blocker was misdiagnosed, and the correction changed the repair

The brief said `contract_view` returns six keys and none of them is
`symptom`, so a graph guard reads an empty observation table. **The key it
does not publish is `symptom`, but it already publishes the field the guard
reads.** Measured on the unmodified base:

```
policy_view  -> symptom.observed = [{"test": "case-01", "expected": 76,
                                     "actual": 121, "kind": "value"}]
contract_view -> observed       = the same list, item for item
admit_shared_view(cv) -> None
```

The guard field is `observed.0.kind` (`swe_graph_record`'s first arm), and
the contract view publishes `observed`. So option **(a), widen the contract
to carry `symptom`, was never the question**, and neither was (c).

The actual emptying was one layer down. `project_swe_view` reads
`public_state["symptom"]["observed"]`, and handed a parity state it finds no
`symptom`, so its `.get` default of `[]` is written **over** a populated
`observed`. The guard then resolves `{}["0"]`, raises, and the executor's own
catch answers with a `stop` refusal. Measured both ways, same record:

| input to the projection | `observed` it receives | what `observed.0.kind` does |
|---|---|---|
| raw `policy_view()` | `{"0": {..., "kind": "value"}}` | returns `"value"` |
| `_ordering_state_from_view(contract_view(...))` | `{}` (overwritten) | raises `KeyError: '0'` |

So the honest repair is **(b), the guard reading a field the contract
already publishes** — the projection now reads the `observed` the caller
actually sent, falling back to the nested path for the raw world view. That
is three lines in one function. `contract_view`, `admit_shared_view` and
`policy_action.view_contract()` are untouched, so the exact six-field check
stays exact and passing; no key was added to the contract, so the strict
equality in `admit_shared_view` was never at risk.

## A second defect was stacked under the first, and I did not repair it

Fixing the projection exposed a shape conflict one layer lower, which is
what still holds the cell:

```
contract_view -> remaining = 1            (int, by declared read ("remaining","test"))
swe.admits    -> remaining.get("inspect", 0)   AttributeError on an int
```

`swe.admits` reads `remaining` as the world's per-dimension mapping
(`{"edit","inspect","localize","probe","test"}`), and the contract publishes
the scalar `admit_shared_view` requires for its `0 <= remaining <=
max_queries` check. The turn the guard now reaches is refused with
`'int' object has no attribute 'get'`.

I left it, because every way to close it is a widening rather than a
repair, and that is the standing rule:

- republishing a mapping under `remaining` breaks `admit_shared_view`'s
  scalar check, which would be weakening a contract to look green;
- rebuilding the map from `action_schema.budget` does not work, measured:
  the schema holds the **ceiling** (`test: 2`) while the live count is
  already spent (`test: 1`, `0` after a second run), so a projection would
  hand the world a budget the world never published.

So the graph cell is a **recorded disposition**, and the record now names
the budget's shape with its measured refusal text rather than the closed
observation view. `support()["comparable_through_compare_arms"]` stays
`False`, correctly.

## What `compare_arms` does now

Still `incomparable`, and the graph arm is no longer among the reasons:

```
status: incomparable
records: ['b18-ast', 'b18-graph']
graph issues: []          <- was the blocker; now carries none
graph turns: 1
  driver-factory-failed ('b18-step',) "lineage_driver() got an unexpected
                                      keyword argument 'timeout_ms'"
  world-action-refused  ('b18-ast',)  "stop target must be swe.task"
```

The graph arm produces a record and **zero** incompatibilities. What holds
the comparison is the other two arms: the STEP driver factory takes no step
budget argument, and the typed AST emits a `boolean.task` stop target the
SWE world refuses. Neither is this lane's, and neither moved.

## Field reconciliation

Unchanged from C1's inventory, because I touched no published field. The
contract still consumes 8 of the SWE world's 12 and `max_budget` is still a
verbatim duplicate of `action_schema.budget`. **No field became surplus by
my change, and none stopped being one.** `symptom` remains a declared world
field read only *derived* through `observed`; it is no longer the thing the
projection fails to find, which is a different statement from being
surplus.

## Verification

```
wsl -d Ubuntu -u ubuntu -- bash -lc '... pytest tests/test_inv_b18_view_contract.py
  tests/test_inv_b9_graph_driver.py tests/test_inv_b1_swe_view.py
  tests/test_inv_b2_graph_child.py tests/test_s09_swe_binding.py
  tests/test_s09_swe_executor_capability.py tests/test_view_contract_swe.py
  tests/test_s09_representation_matrix.py tests/test_s09_arm_parity.py
  tests/test_ordering_graph_policy.py tests/test_boolean_graph_arm.py
  -q -p no:cacheprovider'

134 passed in 74.35s (0:01:14)
S09ISO: dropped 13 database(s) for this run
```

**Trained TDD.** The three view tests were written first and watched fail
on the defect: `assert {} == {'0': {...}}` on the projection, and
`KeyError: '0'` out of `_field_value` through the real child. One test in
that file failed for a reason my own expectation was wrong rather than the
code's: I had double-projected the view, so the child's `make_view` ran
twice over a list-shaped `observed`. The seam now driven is
`_action_graph_factory`'s own `decide`, which is what `_run_arm` calls per
turn.

**The regression was watched failing in both directions.** Reverting the
projection to its old form makes exactly the three view tests fail
(`3 failed, 4 passed`) with `KeyError: '0'`; restoring it returns 7 passed.
A green run against a defect that was never installed would prove nothing,
so the revert was run rather than assumed.

**Pre-existing, reproduced not chased.** `tests/test_s09step_arm.py` (6) and
`tests/test_s09_e4_channel.py` (3) give `9 failed, 59 passed` alongside
`test_frontier_atomicity.py`, `test_s09m1_state.py` and
`test_s09_durable_state.py`. All nine share the one documented cause,
`method_exec` refusing a policy source with no execution authority. The
identical nine ids fail on a clean extract of the base `160f8e4`
(`9 failed, 17 passed`), so none is mine.

`git diff --name-only 160f8e4 HEAD -- reports/evidence/` is empty.

## Files

- `experiments/ad01/s09_swe_binding.py` (**not my path** — see below)
- `experiments/ad01/s09_swe_experiment.py` (**not my path** — the record)
- `tests/test_inv_b18_view_contract.py` (new, mine alone)

I touched two production files outside my ownership, and say so plainly
rather than claiming the lane was clean. The brief anticipated this
("Touch a production file ONLY if the honest repair is elsewhere, and say
so explicitly") and the honest repair was elsewhere both times:
`project_swe_view` is the projection that emptied the field, and
`support()` is the disposition the brief told me to keep honest. Neither
change is reachable from a file I own. Both are additive at their own
boundary and neither weakens a gate.

## What I did not do

I did not widen the contract to carry `symptom`, because the field the
guard reads was already published and the emptying was a projection bug.
I did not add a second view, a second contract or a shim. I did not repair
the `remaining` shape conflict, for the two reasons measured above, and I
did not touch `s09_arm_parity.py`, `s09_swe_world.py` or the world itself. I
did not run a whole-suite sweep, per the resource policy.

## Final process count

Zero. `ps -eo pid,args | grep -c '[p]ytest'` returns 0, and the base
extract used for the clean-baseline comparison is deleted.

Co-Authored-By: Claude Code <noreply@anthropic.com>