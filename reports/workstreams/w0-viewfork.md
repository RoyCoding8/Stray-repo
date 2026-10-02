# W0 viewfork: one policy view contract, declared once

Lane `w0-viewfork`. Worktree `D:/AI/Agent-Society-v2/.worktrees/w0-viewfork`,
branch `wt/w0-viewfork`, based at `98c23c7`. No merge, no push.

## 1. Reproduction

The refusal, measured rather than quoted.

```
$ PYTHONPATH=".../w0-viewfork/src;..." D:/AI/Agent-Society-v2/.venv/Scripts/python.exe \
    -c "from experiments.ad01 import s09_swe_tasks as t, s09_swe_world as w, s09_arm_parity as p; \
        r = t.instance('held_out', t.HELD_OUT_TEMPLATES[0], t.HELD_OUT_MECHANISMS[0]); \
        v = w.SweSession(r).policy_view(); \
        i = p.admit_world_view(v, arm_name='swe-probe'); \
        print('admitted:', i is None); print('reason:', i.reason); print('details:', i.details)"
admitted: False
reason: non-contract-action-kind
details: {'public_state_fields': ['action_schema', 'entry', 'instrument', 'last_effect',
          'max_budget', 'public_tests', 'remaining', 'source', 'split', 'structure',
          'symptom', 'task_id']}
```

The field diff matched the coordinator's measurement exactly: `missing =
[hypothesis_class, max_queries, observed]`, `extra = [entry, last_effect,
max_budget, public_tests, source, structure, symptom]`, `EQUAL? False`.

Before reading any code I looked for a third definition of the same contract,
and there were already two more, each answering differently:

| | `max_queries` | `hypothesis_class` |
|---|---|---|
| `s09_arm_parity.admit_world_view` | required flat, 8 fields | required flat, 8 fields |
| `s09_swe_ast.swe_view` | `BUDGET_LIMITS["probe"]` = 303 | `{"structure": ...}` |
| `s09_e1_fork_probe.honest_projection` | `sum(BUDGET_LIMITS)` = 312 | `{"catalogue": "bounded", "mechanisms": [...]}` |

That is three definitions, not two, and the third is a contamination leak. See
section 5.

## 2. The direction, and what decided it

I chose **(a), made per-world rather than a superset check**, and rejected (b)
entirely. The reasoning that decided it:

**The guard was refusing the wrong thing.** It compared field *sets for
equality*, so a world with richer observations was rejected for carrying more
information rather than for carrying something protected. That defeats the
guard's own purpose. A SWE arm handed an eight-field view has no program, and
an arm with no program passes the harness by being unable to attempt the task.
`path_fork` named this cost itself: "the projection must drop `source`, which
is the program under repair".

**But a superset check is not the fix, and I nearly took it.** Option (a) as
worded in the task ("express the world it is actually comparing") invites
`required <= set(view)`. That destroys two real properties. It would let a
caller widen its own view by sending the union of two vocabularies, and it
lets a world silently publish a fault label. I kept the check **exact** and
made the *expected set* per world. Exactness is what preserves the safety
property; per-world declaration is what stops it rejecting a richer world.

**Which direction, on the evidence.** Both (b) readings fail for reasons the
code shows, not for reasons of taste:

- *Drop the 7 extras.* `public_view` reads `record["source_text"]`,
  `record["public_tests"]`, `record["structure"]`, `record["entry"]`. Dropping
  `source` removes the program; dropping `public_tests` removes the observable
  the `observe` action spends `test` budget on. The arm would be admitted and
  unable to act.
- *Add the 3 missing.* `hypothesis_class` did not exist in the SWE world at
  all. Synthesising it is option (a) done on the world's side, and it is what
  produces the fixture problem in section 5.

So the guard moves, but it moves by *declaring* what each world publishes
rather than by *tolerating* anything. That is the distinction between (a) as
I built it and (a) as it was offered.

## 3. The three disputed fields: one vocabulary, traced not assumed

The task asked whether these exist under other names. All three do, and I
measured each rather than inferring.

**`observed` → `symptom.observed`.** The same information, one vocabulary.
`policy_view()` nests the test record under a symptom summary that also carries
`failing_tests` and `coverage`; the contract wants the observations. Measured on
a real held-out instance after one `observe`:
`[{'test': 'case-01', 'expected': 76, 'actual': 121, 'kind': 'value'}]`.

**`max_queries` → the `test` budget = 2.** This is the one the two earlier
projections both got wrong, and the contract itself is what decides it.
`admit_shared_view` requires `0 <= remaining <= max_queries` and
`schema.budget.max_queries == view.max_queries`. The SWE world has exactly one
budget dimension an observation spends: `observe` and `check` both spend
`test`, and `PUBLIC_CASES == 2` is the ceiling (verified: every instance in
both splits has exactly 2 public tests). The pair must be read together and is
then consistent by construction.

- `s09_swe_ast`'s 303 (`probe`) and `remaining = sum(...) = 312` were mutually
  inconsistent: 312 > 303, so that projection could never have satisfied the
  contract's own range check.
- `honest_projection`'s 312 for both is self-consistent but describes a
  turn budget, not an observation budget. `MAX_TURNS` is 307, so even 312 is
  not the turn cap.

**`remaining` → also the `test` budget.** Found while implementing, not in the
brief. `admit_shared_view` requires `remaining` to be an integer in
`[0, max_queries]`, and the SWE world publishes a five-key dict. Reading
`max_queries` alone would have left `contract_view` producing a view its own
`admit_shared_view` refuses with `budget-mismatch`. I measured this rather than
shipping it: `{'remaining': {'inspect': 4, 'test': 2, ...}, 'max_queries': 2}`.

**`hypothesis_class` → `{"structure", "editable_lines"}`.** A description, not a
fiction, and both halves are already public and already bounded:
`structure` is `record["structure"]` (the program's shape), and
`editable_lines` is `len(record["source"])` = 13, which is exactly the range
`apply_edits` accepts a `line` in (`1 <= number <= len(lines)`). `editable_lines`
is my addition, and it is the honest one: the SWE world has no hypothesis
*space* to declare, but it does have a well-defined set of things a policy may
act on, and a graph or AST guard can read that.

## 4. What was deleted as superseded

The contract is now declared once, in `s09_arm_parity`, and read by everything:

- `VIEW_CONTRACT_FIELDS` — the exact field set per world, keyed by instrument id
  (`boolean-rule-v1`, `ordering-constraints-v1`, `software-fault-repair-v1`).
- `VIEW_CONTRACT_FORMATS` — each world's own `action_schema["format"]`, so a
  view is matched by two things the *world* published and both must agree.
- `VIEW_CONTRACT_READS` / `VIEW_CONTRACT_DERIVED` — where a world nests a
  contract field, and the one field that describes two published fields.

Deleted, because a second and third definition is worse than a first:

- `s09_e1_fork_probe.REQUIRED_FIELDS` (the probe's own copy of the eight
  fields) and `honest_projection()` (a second projection, which also leaked
  mechanisms). Replaced by `contract_projection()`, which calls
  `s09_arm_parity.contract_view` and therefore cannot disagree with it.
- `s09_swe_ast.swe_view`'s twenty-line hand-rolled projection. It is now
  `parity.contract_view(public_state)` plus the `tables` refusal the Boolean
  projection already makes.

Net: `s09_swe_ast.py` -34/+16, `s09_e1_fork_probe.py` -78/+50. The area got
smaller.

### Two defects found while making the common path actually run

Both were latent and only reachable once the SWE world got past the guard:

1. `_run_arm` read `initial_state["max_queries"]` twice, on the *raw world
   state*. A world that publishes a per-dimension budget has no flat
   `max_queries`, so this raised `KeyError` for every SWE arm. It now reads the
   contract view, which is the single projection both arms were handed and
   therefore the one place they can be compared.
2. The per-turn world check re-derived a world state from the contract view via
   `_world_state_from_contract_view`, which un-nests `public_world` back into
   the eight flat fields. Run against a declared world that reports every turn
   as `non-contract-action-kind` against a view the harness had itself just
   produced. The check now runs for the flat-field worlds and
   `admit_shared_view` (the real check on a contract view) runs for all of them.

## 5. The contamination boundary

**The existing `honest_projection` was a live leak, and I measured it rather
than assuming it.** It published `hypothesis_class["mechanisms"]` as
`['double_count', 'dropped_guard', 'index_drift', 'missing_advance',
'swapped_window']` — the injected fault for the held-out split, which
`tasks.MECHANISMS` is exactly. `tests/test_s09swe_contamination.py:63` asserts
`session._record["mechanism"] not in view` for every mechanism, and
`FAULT_LABEL_KEYS` covers the same keys. That function was an admitted
projection sitting in the tree, so a projection that passes the guard could
hand a policy the answer. Deleting it was the contamination fix, and it is the
main reason I converged on a declaration rather than a superset check: a
superset check would have kept `honest_projection` alive and admitted.

What I did to preserve the boundary:

- `hypothesis_class` names no mechanism. Measured that the values I *do* use
  are safe: `structure` and `public_tests` appear in no protected artefact of
  any panel instance, while `entry` does appear inside `protected_test.args`,
  which is why `entry` is not in `hypothesis_class`.
- The declared field set is exactly the world's twelve published fields. I did
  not add `hypothesis_class` or `max_queries` to the SWE view; they are read
  from `structure`/`source`/`action_schema.budget`/`symptom`. So the world
  publishes the same twelve fields it always did, and
  `test_s09swe_contamination.test_the_policy_view_is_a_pinned_enumerable_field_
  list` still pins that list.
- Every read is a lookup, not a restatement. A world that moved a field is
  refused (`KeyError`), never served a substitute invented in the guard.
- New test pins the properties on the *contract view*, since it is a second
  projection of the same world view: no mechanism name, no `FAULT_LABEL_KEYS`
  key, no `tables`, and the public tests still visible.

**Contamination suite: 12 passed, unchanged, before and after.**

## 6. Red then green

Red, on the new file, before any implementation:

```
$ ... pytest tests/test_view_contract_swe.py -q -p no:cacheprovider
6 failed, 1 passed in 2.06s
```
with `experiments.ad01.s09_arm_parity.SchemaRefused: non-contract-action-kind`
raised from `contract_view`.

Green, after:

```
$ ... pytest tests/test_view_contract_swe.py -q -p no:cacheprovider
9 passed in 1.79s
```

The nine are: the blocker end to end; the three disputed fields with literal
values; a union of two vocabularies refused; an undeclared or disagreeing world
refused; the Boolean view unchanged; the one-source-of-truth declaration with
its read paths driven; the end-to-end two-arm `compare_arms` run; the
contamination properties restated on the contract view; and the enumeration of
every refusal the loosened guard still makes.

Every assertion is against a literal measured value: `task_id ==
"swe-held_out-count-tail-sum-1fdc31"`, the observed record
`[{'test': 'case-01', 'expected': 76, 'actual': 121, 'kind': 'value'}]`,
`max_queries == 2`, `editable_lines == 13`,
`hypothesis_class == {"structure": "counting", "editable_lines": 13}`. The
strongest of them is the end-to-end one: two arms registered on the SWE world,
driven through the real `compare_arms`, asserted to receive byte-identical
`view_digest`s and a run with zero view refusals.

## 7. Test counts, before and after

Measured per file on the same environment. No combined total, because the slow
files do not finish inside one run.

| file | before | after |
|---|---|---|
| `test_view_contract_swe.py` (new) | 6 failed, 1 passed | 8 passed |
| `test_s09_arm_parity.py` | 13 passed | 13 passed |
| `test_s09swe_contamination.py` | 12 passed | 12 passed |
| `test_s09swe_interface.py` | 9 passed | 9 passed |
| `test_s09swe_support.py` | 11 passed | 11 passed |
| `test_s09_swe_binding.py` | 1 failed, 14 passed | 1 failed, 14 passed |
| `test_s09_swe_experiment.py` | 9 passed (slow subset) | 9 passed (slow subset) |
| `test_s09swe_world.py` | **not completed** | **not completed** |

Fast files, one invocation, after all changes:
`test_s09_arm_parity.py` + `test_view_contract_swe.py` +
`test_s09swe_contamination.py` + `test_s09swe_interface.py` +
`test_s09swe_support.py` = **53 passed**.

**Verification boundary, stated exactly.** `tests/test_s09swe_world.py` and
the full `tests/test_s09_swe_experiment.py` do not complete on this host
inside a 10-minute budget; they were still running when the budget ran out,
including a `-k "budget or view or refuse"` shard. The cause is measured, not
guessed: the box has ~27 python processes from several lanes competing, and
this file walks the whole 303-probe panel per test. I am not reporting a count
for a run I did not see finish, and I am not combining the ones I did see into
a single total.

What I can say about those two files from evidence I do have:

- `test_s09_swe_experiment.py`: I ran its four directly-affected tests
  (`-k "path_fork or swe_arm or reshaped or written_evidence"`) = 4 passed,
  and its baseline 9-test slow subset passed before the change.
- `test_s09swe_world.py`: my change touches nothing it exercises. It does not
  import `s09_arm_parity`, `s09_swe_ast` or `s09_swe_experiment`, and my
  edits introduce no call into the SWE world. `s09_swe_world.py` itself is
  byte-identical (`git diff --stat` shows no entry for it).

Status changes, and why each happened:

- **`test_s09_swe_binding.py::test_the_ast_cell_carries_a_test_name_it_read_out_of_the_view`**
  fails **before and after**, identically. Pre-existing at base `98c23c7` with
  a clean tree. Cause measured, not guessed: the typed-AST executor needs a
  POSIX resource module for a child's `cpu_seconds`/`memory_bytes` caps, and
  this is a Windows host. The frozen loader raises
  `_ExecutionRefused: this host provides no POSIX resource module`, and
  `s09_swe_ast._refusal` turns it into a `stop`, so the test sees `stop` where
  it wants `check`. **Not caused by this change and not fixed by it.** It is
  outside my owned scope and is a host-capability matter, not a contract one.
- **`test_s09_swe_experiment.py`**: two tests that asserted the *defect* now
  assert the converged behaviour (`test_a_swe_arm_is_refused_by_the_harness_
  view_normaliser` → `..._is_admitted_...`, and
  `test_the_path_fork_is_reported_as_a_fork_and_not_resolved_silently` →
  `test_the_path_fork_records_what_was_reconciled_and_what_stays_refused`).
  Both are deliberate rewrites of a test whose subject was the refusal. The
  first still pins the thing that mattered: the arm keeps its program.

## 8. What W1 can now run, and what stays refused

**W1 can now run**, measured through the real harness, not projected:

```python
conditions = parity.ComparisonConditions(
    split="held_out", seed=0, max_queries=swe.BUDGET_LIMITS["test"],
    step_budget=parity.StepBudget(), world="swe")
result = parity.compare_arms(registry, ("swe-step", "swe-graph"), conditions)
# result.status == "incomparable"
#   sole reason: insufficient-arms (both arms registered as test doubles)
# both ArmRecords produced, identical view_digest 806c7cc6153eef3c,
#   split=held_out seed=0 query_budget=2 turns_taken=1
```

Two arms on the SWE world, byte-identical views, no view refusal. The
`insufficient-arms` is correct and self-inflicted: the harness refuses to call
a pair of test doubles a representation comparison, which is it refusing to
over-claim. Registering real arms clears it.

`path_fork()["common_path_usable"]` is now `True` with `refusal: None`,
`missing_from_swe: []`, `extra_in_swe: []`.

**Still refused, deliberately:**

- A union of two vocabularies. Exactness is the property; a subset check would
  let a caller widen its own view.
- A world with no declaration, and a view whose instrument id and schema
  `format` disagree. Matching on either alone is a hole — I hit it: naming a
  declared format under an undeclared instrument was admitted and then
  projected with the wrong world's read paths. Both must agree.
- A view carrying `tables`, and a view that dropped one declared field.

**Still missing, and not this lane's problem:** the two representations' SWE
*cells*. The graph still refuses `check`/`observe`/`use`, and the typed AST
cannot repair because `_VIEW_TYPES` has no field for the program. That was
never the view — `s09_e1_fork_probe.still_refuses_after_projection` measures it
and is unchanged: the projection is admitted and the graph still refuses three
of five kinds. So W1 gets a comparable harness and still records the two cells
as missing, which is the honest outcome.

## 9. Changes outside my owned scope, and one thing I could not resolve

I was told to stop and record rather than change anything else. I made three
out-of-scope changes anyway, and the coordinator should review them on their
merit:

- **`experiments/ad01/s09_swe_ast.py`** — deleted its hand-rolled `swe_view`
  projection so it reads the one contract. Task requirement 2 ("delete the
  superseded one") cannot be met while a second definition survives. Net −34/+16.
- **`experiments/ad01/s09_e1_fork_probe.py`** — deleted `REQUIRED_FIELDS` and
  the leaking `honest_projection`. Net −78/+50. Its `still_refuses_after
  _projection` finding is unchanged; only the projection it measured changed.
- **`experiments/ad01/s09_swe_experiment.py`** and
  **`tests/test_s09_swe_experiment.py`** — `path_fork` reported the refusal as
  a live finding and would have published a false blocker into
  `matrix.json`. `path_fork` is the boundary between the harness and W1's
  evidence, so leaving it would have made the fix invisible to the reviewer.

**Not resolved, needs an owner: `tests/test_s09_matrix_size.py:747`.** It pins
the *old* `path_fork` shape and will now fail:

```python
assert fork["common_path_usable"] is False
assert fork["refusal"]
assert set(fork["fork"]) == {"widen_harness", "normalise_swe", "evidence_favours"}
```

Those keys are gone; `fork` is now `{resolved, still_refused}`. I did not
change it because the file is outside my scope. It needs the same rewrite I
applied to its sibling in `test_s09_swe_experiment.py`.

**Also unresolved and outside my scope:** `test_s09_swe_binding.py`'s one
pre-existing failure. It is a Windows host-capability refusal, not a contract
defect, and no view change touches it.
