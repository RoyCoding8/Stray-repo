# E1 lane AA1: the graph cell is a binding, the AST cell is not

`inv_r1_aa1_e1_world_fit`. Zero live dispatches. Machine-readable
evidence: `world_fit.json`, and `result.json` for the gate re-run.
Generator: `experiments/ad01/s09_e1_world_fit_probe.py`.

## Verdict, and a correction to this lane's own first answer

A `World` value **does** carry SWE into the graph executor, and the graph
cell is a binding rather than a re-shape. A `World` value cannot reach the
AST executor at all. Those are two different answers and reporting one for
both is what made the first version of this record wrong.

The first version concluded that no `World` value could carry SWE, on the
strength of a `KeyError: 'observed'` raised by the guard evaluator. That
error was an artifact of the probe. `swe.public_state` takes a
`SweSession` and returns its policy view unaltered, so it projects
nothing, and the probe had filled the world's `make_view` with it. The
executor calls `world.make_view(public_state)` at line 501 before it
evaluates any guard, and `make_view` is a `World` field. A value that
projects the view into the shape the evaluator reads closes the cell, and
that is the finding. The unprojected result is retained in the payload as
`field_resolution.unprojected_make_view` so the mistake stays visible
rather than being quietly corrected.

With a projecting `make_view`, over all 30 held-out instances:

```
field_resolution.observed.0.actual
  loader_admits      = True
  policy_admitted    = True      (the real load_policy)
  guard_evaluated    = True      (the real _evaluate_guard)
  chosen_action      = construct/code.inspect
closes_across_held_out: 30 of 30 held-out instances, 0 failures
```

30 of 30 is the 6 templates × 5 mechanisms grid the ceiling matrix ran, so
the closure generalises across the held-out panel rather than holding for
one instance.

## The gates, run first

Unchanged from lane W1's committed run, and re-run here byte-for-byte
identical.

```
menu_answers_nothing   open=True  bound=8  defaulting_strategy=[]  wrappers_build=True
control_distinct       distinct=False
  refused: control is not distinct from the acquired arm: 6 task(s) ran one
  strategy on both arms; 6 task(s) ran one executed policy id on both arms;
  6 task(s) returned a byte-identical candidate on both arms
experience_varies     varies=False  72 observations, 1 distinct verdict ['preserved']
```

The `control_distinct` refusal is more specific than "6 software tasks
greedy-against-greedy, 6 graph tasks running the same incumbent". The two
failure sets are **disjoint**, and each is caught by its own leg:

| tasks | executed ids | legs that catch it |
|---|---|---|
| 6 software (`*-sw-*`) | `seed-sw-greedy` vs `acquired-sw-58d90427` | `same_strategy` |
| 6 graph (`*-gr-*`) | `incumbent` vs `incumbent` | `same_executed_policy` + `same_candidate` |

The software ids differ and the strategies are one, so the id check passes
them and the strategy leg refuses. The graph ids are identical and the
candidates are byte-identical, so two legs fire there.

**The gates, not the World shape, are what decide E1's claim.** They
refuse independently of the SWE cells, so the graph binding being closable
does not rescue the milestone. That is the whole argument for narrowing,
and it does not depend on the executor question at all.

## What the two representations cost, measured

**The graph is a value.** A `World` carrying SWE's own constants, with a
`make_view` that re-exposes `symptom.observed` as the dotted
`observed.<N>.<key>` the evaluator walks, is admitted by the real
`load_policy` and steers a real arm. No executor change. `allowed_kinds`
is a `World` field and already accepts all five SWE kinds, so the
action-vocabulary shape was never a blocker for this cell.

**The AST is not a value.** `boolean_ast_policy` takes no `World`
parameter, so nothing a caller writes reaches it. What decides the cost is
how a second world is reached today, and that is measured rather than
assumed: `ordering_ast_policy` is 421 lines against 894, imports
`boolean_ast_policy` **as `frozen`**, and calls `frozen._load`. It
**delegates** to the frozen loader, executor and node set while supplying
its own view projection and action rules. So a SWE AST arm costs a
projection, which is the same shape of work the ordering arm already did,
not a third copied module. The first version of this record claimed the
opposite and was wrong.

**The three named targets are not the blocker.** `probe_target` and
`construct_target` are declared and assigned and **never read** anywhere in
production; only `stop_target` is read, and it is read from the module
global rather than from the world, because `_validate_ordering_action`
takes no `world` at all.

**`observation_paths` is live, and the regex still never fires.** Measured
by calling rather than by reading the source: the ordering world resolves
`observed.0.left` to `"string"` with its paths, and to `None` with the
paths withheld, so the check is real. It is simply never reached for a SWE
key, because the regex is tested first and its key alternation
`left|right|earlier` is fixed at module scope. So the brief's "falls back
to the regex regardless of `observation_paths`" is wrong in its mechanism
and right in its conclusion.

One limit the value cannot remove: a guard names the index it reads, and
`derived_fields` is consulted by the evaluator but not by the loader
(`derived_fields_reach_the_loader: False`), so a policy can only guard on an
observation index the world publishes at load time.

## The 156/156

Unchanged. Reproduced in seconds, no dispatch:

```
action-graph   n=156  repaired=0  unrepaired=0  refused=156
typed-ast      n=156  repaired=0  unrepaired=0  refused=156
python-step    n=156  repaired=124  unrepaired=32  refused=0   (carried)
```

**The 156 is not 156 independent tasks.** Recounted from the committed
ceiling's own rows: 156 rows are **39 distinct task_ids × 4 lineages**, 9
dev tasks and 30 held-out tasks. The 30 held-out instances are 6 templates
× 5 fault mechanisms, matching the recorded
`distinct_faulty_programs: 30`. That clears E1's floor of 4 families and
24 instances, but the headline is a task-by-lineage product and should not
be quoted as an instance count.

## What E1 can and cannot claim

It **can** claim: three representations qualified on the worlds they
support, with `python-step` carrying a real SWE cell of 124 repaired and 32
unrepaired out of 156; a real SWE instrument with bounded tools for
inspection, test choice, localization and repair, and no injected fault
label, hidden patch or protected answers in the policy view; and, new here,
a demonstrated path to the missing `action-graph` cell that is a value
rather than an executor change.

It **cannot** claim: that the comparison is between two distinct methods,
because `control_distinct` refuses it; that experience carried more than
one outcome, because `experience_varies` refuses the column; that the
recorded control column of `6, 9, 8` is attested, because no file under
`evidence-ad01/` contains it and no file names `ddmin`; that three
representations ran across three worlds, because `typed-ast` still has no
SWE cell; or that the 156 are 156 independent instances.

## Open, and not this lane's to fix

Closing the `action-graph` cell means writing the SWE `World` value into
the study, and closing `typed-ast` means a SWE AST arm. Neither is
attempted here, because neither changes the gates' verdict and the
milestone's binding constraint is upstream of both. The structural defect
that is worth a lane of its own: `World.field_type` and
`World.observation_at` are reachable only for the ordering world's own
layout, so a second world's guard vocabulary is a matter of what
`make_view` publishes rather than what the executor can read.

## Reproducing

```
.venv/bin/python -m experiments.ad01.s09_e1_gates_probe    --out <dir>
.venv/bin/python -m experiments.ad01.s09_e1_world_fit_probe
```

Neither dispatches, opens a database, or reaches the gateway. The SWE
world is a local oracle.
