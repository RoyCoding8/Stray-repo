# E1's path fork: the recorded cause is wrong, and fixing it buys no cell

Lane U3, branch `codex/implementation-investigation-learning-02`. Read-only. No dispatch.

throughput checkpoint: n/a, read-only investigation.

**Verdict.** The three options in the brief are all aimed at the wrong thing. The blocker on
`typed-ast` and `action-graph` is not the view contract. It is that neither representation's
executor has a SWE world binding. Resolving the view fork would make a SWE arm *admissible* and
still leave both cells empty, because the executors would refuse every action the moment the
episode began.

The prior lane's own record already says this and then concludes the opposite. Its
`path_fork()` docstring says the projection cost is that the arm "would pass the harness unable to
attempt the task" (`experiments/ad01/s09_swe_experiment.py:1640-1643`), and the same file then
records `evidence_favours: normalise_swe` (`s09_swe_experiment.py:1677`). The two statements
contradict each other. This lane checked which is true.

---

## 1. What the fork actually is, measured

`s09_swe_world.SweSession.policy_view()` publishes twelve fields
(`experiments/ad01/s09_swe_world.py:154`, `:240`). `admit_world_view` compares that set for
**equality** against eight required names (`experiments/ad01/s09_arm_parity.py:314-318`). Measured
at this tip:

```
missing_from_swe = ['hypothesis_class', 'max_queries', 'observed']
extra_in_swe     = ['entry', 'last_effect', 'max_budget', 'public_tests',
                    'source', 'structure', 'symptom']
```

That much is as recorded. Three things after it are not.

### 1.1 The budget cannot be projected without inventing a scalar

`admit_world_view` requires `type(max_queries) is int` (`s09_arm_parity.py:320-323`) and requires
`action_schema.budget.max_queries` to equal it (`s09_arm_parity.py:332-343`). SWE publishes a
five-key budget dict, `{'inspect': 4, 'test': 2, 'localize': 2, 'probe': 303, 'edit': 1}`
(`s09_swe_world.py:29`, `:172`). There is no `max_queries` key at all. Any eight-field view is
therefore forced to collapse five denominations into one integer, and the two existing worlds
have exactly one denomination to collapse. The record's cost note names only `source` as the price
of normalisation. The price is also a fabricated denominator, and a fabricated one is worse than a
dropped one: it is a number the arm will budget against.

### 1.2 The view is not what the two executors are missing

This is the finding that changes the recommendation. The AST executor's field table has six
entries and no `source` (`experiments/ad01/boolean_ast_policy.py:47-54`). But the field table is
not the wall. The AST re-nests the harness's own six-field contract view back into the eight it
wants, and does so before the missing check can fail
(`experiments/ad01/boolean_ast_policy.py:584-612`):

```python
nested = public_state.get("public_world")
if missing == ["hypothesis_class", "max_queries", "split"] \
        and isinstance(nested, dict) \
        and all(key in nested for key in missing):
    public_state = {**public_state, **nested}
```

So the AST already tolerates the contract view the common path hands every arm. The recorded
reason, `node set refuses view.source: unknown view field 'source'`, describes a limitation that
only exists if the view keeps the twelve-field shape. Under a projection the AST would not hit it.

The wall is on the other side. The AST's action validator handles `probe`, `construct` and `stop`
and refuses everything else (`experiments/ad01/boolean_ast_policy.py:643-665`). SWE needs `use` to
apply a repair (`s09_swe_world.py:466`), and `observe` and `check` to run tests
(`s09_swe_world.py:426-445`). The action graph's binding is the same shape and worse:
`ORDERING_WORLD.allowed_kinds` is `{probe, construct, stop}`
(`experiments/ad01/ordering_graph_policy.py:182-183`), its `observation_paths` are
`{left, right, earlier}` (`ordering_graph_policy.py:194`), and its `make_view` is the Boolean
world's `_shared_view` (`ordering_graph_policy.py:198`).

Neither executor has a SWE `World` value. This is what the matrix already records as
`no swe World value exists` in its `action-graph` reason, and the AST reason's own
`loader accepted a repair in the frozen grammar` clause. The `missing_cells` reasons and the
`path_fork` block disagree about which is the cause.

### 1.3 Measured: an honest projection is admitted and still yields zero cells

I built the projection the record asks for, without lying. `observed` is re-nested from
`symptom.observed`, `hypothesis_class` declares the bounded catalogue that genuinely exists,
`source` is dropped, and `max_queries` is the sum of the five denominations, which is stated as a
denomination sum rather than a per-action ceiling. Result:

```
projected fields: 8
admit_world_view(proj) -> None        # admitted
AST _VIEW_TYPES lacks 'source'        # True   (no longer reached)
AST validator handles 'use'           # False  (still refuses)
graph allowed_kinds                   # ['construct', 'probe', 'stop']
```

Admitted, and both representations still refuse every turn. The fork is real and it is not the
binding constraint.

---

## 2. The three options, costed from the code

| Option | What it changes | Cost, measured | Verdict |
|---|---|---|---|
| 1. Bind a SWE `World` value | New `World(...)` with SWE `allowed_kinds`, SWE `observation_paths`, SWE `field_types`, and a SWE `validate_action` | The only option that produces cells. `use`/`observe`/`check` need real semantics in three places the executors currently hard-code Boolean and ordering rules. Days, and it is a new executor not a fix. | **This is the work.** |
| 2. Widen `admit_world_view` to a superset | `:314-318` equality becomes `required <= set(...)` | Cheapest edit, worst outcome. It admits a view the executors still cannot act on, so it converts a loud refusal into a silent zero. Nothing in `src/` calls it, but `tests/test_s09_swe_experiment.py:490-503` and `:660-675` assert the refusal, and `boolean_rule.PUBLIC_VIEW_KEYS` (`:193`) and `s09_instruments.view_keys` (`:229`, `:247`) describe the eight-field shape as the worlds' contract. | Rejected. Widening a contract to make a comparison fit is the error the brief warns about. |
| 3. Narrow the claim | Record SWE as out of scope for the three-representation comparison | Zero code. Forfeits the E1 milestone. | Rejected as a primary, kept as a fallback. |

### Does anything depend on the eight-field contract?

Yes, but only as documentation, and the AST already does not depend on it. Measured:

- **No product code.** `admit_world_view`, `contract_view` and `admit_shared_view` appear nowhere
  under `src/`. They are experiment-harness surface only.
- **`s09_instruments.py:229`, `:247`** declare `view_keys` as the eight names for both worlds.
  Read by one test (`tests/test_s09instr_support.py:150-152`).
- **`boolean_rule.PUBLIC_VIEW_KEYS`** (`:193`) is a nine-name set including `instruction` and
  `committed`. Read by one test (`tests/test_m3_rule_instrument.py:82`).
- **`boolean_ast_policy._shared_view`** (`:584-612`) re-nests the six-field contract view, so the
  AST arm survives on the common path today without ever seeing the eight.

So the contract is real but soft. Nothing enforces it that a projection would break. That is why
option 2 is *available*. It is still the wrong choice, because the executors, not the contract, are
what produce zero cells.

---

## 3. Recommendation

**Option 1. Do not touch `admit_world_view`. Build a SWE `World` value and let the two
representations run on the world's own driver, the way the ordering pilot does at
`s09_representation_matrix.py:490-500`.**

One sentence: the fork is recorded as a normaliser problem and is actually a missing
`World` binding, so the fix is `s09_swe_world` supplying `allowed_kinds`, `observation_paths`,
`field_types` and `validate_action` the way `ordering_graph_policy.ORDERING_WORLD` does
(`ordering_graph_policy.py:176-199`), with the twelve-field view left intact.

This is cheap to say and expensive to do, and the record should stop claiming otherwise. Three
consequences follow, and all three are unhedged:

1. **`normalise_swe` is wrong as a recommendation.** Its own cost text says the projection makes
   the arm unable to attempt the task. A recommendation that removes the task is not a
   recommendation. The block at `s09_swe_experiment.py:1663-1677` should be annotated, not
   deleted, since it is the honest record of a real measurement.
2. **SWE stays off the common path even after the fix.** The projection I built is admitted by
   `admit_world_view`, but the AST's field table and action validator are per-world, and
   `_shared_view` hard-codes the three fields it re-nests. Running all three representations on
   SWE means running them on SWE's driver and recording that, which is what the current evidence
   already does honestly. The milestone line "unify the view, then a full 3-representation SWE
   matrix" is not achievable as written.
3. **A 3-representation SWE matrix is a new executor, not a new run.** It is the same class of
   work as M2's ordering pilot, and `WORKER-STAGE-09-CONNECTED-STUDY.md:47` puts SWE outside M2's
   pilot scope, so this is E1-only and does not close M2.

---

## 4. The INVALID banner

`reports/evidence/inv_r1_e1_swe/RESULT.md:1-9` records a candidate generator that deduplicated on
`candidate.strip()` and appended the stripped form, so every in-function candidate was an
`IndentationError` and `code.try` scored 0 of 2 for the correct repair. Two full 156-episode runs
read as a clean zero. The banner is correct and should stay. It does **not** block a new run,
because the replacement is not the same artifact: `inv_r1_e1_swe_ceiling/RESULT.md:1-14` reports
five separate defects fixed, and its matrix shows `python-step` at 124 repaired of 156 with the
two other representations at 156 refusals each.

That matrix is 0.8 MB and the ceiling is a real signal, but it is one representation wide, and the
per-representation breakdown I measured is:

```
python-step    n=156  repaired=124  unrepaired=32  refused=0
typed-ast      n=156  refused=156
action-graph   n=156  refused=156
```

A fresh run on today's tip is therefore not blocked by the banner. It is blocked by option 1 not
having been done.

---

## 5. The unattested control column

N-77 was half right. Both halves verified at this tip.

**The acquired column is backed.** `evidence-ad01/c3-trajectories-merged/use-w1-I.json` is a list
of records; the three software records carry `final_measure` 5, 10, 8 with `initial_measure` 8,
13, 11, and `normalized_reduction` 0.375 on the first. The executed policy is
`acquired-sw-58d90427`, whose body calls `reducers.reduce_software(..., method="greedy")`.

**The control column is backed by nothing.** `grep -rl ddmin evidence-ad01/` returns zero files.
`evidence-ad01/c3-authored/use-w1-I.json` carries `final_measure=3` on all three software records
with `initial_measure` 8, 13, 11, and every record has `"selected": "seed-sw-greedy"` and
`"executed": "seed-sw-greedy"`. That is the greedy policy, not ddmin. The recorded control column
of `6, 9, 8` appears in no file under `evidence-ad01/`.

**The two columns are not two policies, which is worse than an unattested one.** The acquired
policy's own body is
`reduxers.reduce_software(task, oracle, method="greedy", max_queries=max_queries)`, verified by
the probe's `acquired_policy_body_calls_the_control_reducer`. So the acquired arm and the control
arm ran the same reducer, the acquired one through an acquired wrapper and the control one
directly. The 23-against-23 tie is not a tie between two methods. It is a tie between a wrapper
around greedy and greedy, on different task sets, with the control arm's own triple recorded
nowhere.

Note the path. These files are at the **repository root** under `evidence-ad01/`, not under
`reports/evidence/`. A search of the latter finds nothing and would wrongly read as "no data".

**What it means for a fresh E1 run.** The 23-against-23 tie cannot be regenerated, because the run
left no record of the control arm. It can be annotated and not rebuilt. Concretely, any new run
must satisfy one condition that the last one did not: **the control arm's per-record output must
be written to a committed file inside the same run, with the executed policy id and the selection
recorded per row, and a post-run assertion that the control column's executed policy id differs
from the acquired column's.** Without that assertion the same substitution recurs silently, because
the failure mode is that `selected` names one policy while the comparison table is built from
another. The three `c3-authored` software records show the substitution already happened once,
with `fallback_reason` empty and `verdict: preserved`.

A generator that emits the use-record and the comparison table from the same executed value is the
fix. Two tables built from two reads of a selection are what let this survive.

`experiments/ad01/s09_e1_fork_probe.py` recomputes section 5 from the two files, and recomputes
sections 1 and 2 as well:

```
./.venv/bin/python -m experiments.ad01.s09_e1_fork_probe
```

It dispatches nothing, opens no database and writes nothing.

---

## 6. Cost of this lane

No dispatch. No gateway call. No database created or touched. The gateway was reachable and
authorised and the analysis did not need it: the blocker is in the repository, and a run against
today's tip would have spent live dispatches to reproduce the 156 refusals already recorded.

---

## 7. What a correct E1 close looks like

1. Annotate `path_fork` at `s09_swe_experiment.py:1663-1677` and the N-58 row. The eight-versus-
   twelve measurement is correct. The `evidence_favours` conclusion and the two `missing_cells`
   reasons are not, and they name the view where the cause is the executor binding.
2. Build the SWE `World` value. `s09_swe_world` supplies `field_types` for its twelve fields,
   `observation_paths` for `{test, expected, actual, kind}`, `allowed_kinds` of
   `{observe, check, use, construct, stop}`, and a `validate_action` that delegates to the existing
   `apply_action` refusal at `s09_swe_world.py:426-472`.
3. Extend the AST and graph executors to that binding, and record each extension with its measured
   effect, as `WORKER-STAGE-09-CONNECTED-STUDY.md:47` already requires for the ordering pilot.
4. Then, and only then, run the 3-representation matrix, with the control arm's record committed
   per section 5.
5. If step 2 or 3 is not funded, close E1 as option 3 and say plainly that the three-representation
   SWE comparison was not run. That is a complete result. The current state, where the artifact
   records a fork and recommends the option that removes the task, is not.

---

## Files cited

- `reports/STAGE-09-E1-FORK.md` is the report. Every measurement in it is recomputed by
  `experiments/ad01/s09_e1_fork_probe.py`.
- `experiments/ad01/s09_arm_parity.py:307, 314-318, 320-323, 332-343, 377-378, 698, 737`
- `experiments/ad01/s09_swe_world.py:29, 154, 172, 204, 240, 401, 426-472, 531`
- `experiments/ad01/boolean_ast_policy.py:47-54, 584-612, 628, 643-665, 773`
- `experiments/ad01/ordering_graph_policy.py:176-199`
- `experiments/ad01/boolean_rule.py:193`
- `experiments/ad01/s09_instruments.py:229, 247`
- `experiments/ad01/s09_representation_matrix.py:458, 490-500`
- `experiments/ad01/s09_swe_experiment.py:1613-1677`
- `tests/test_s09_swe_experiment.py:490-503, 660-675`
- `tests/test_s09_instr_support.py:150-152`, `tests/test_m3_rule_instrument.py:82`
- `reports/evidence/inv_r1_e1_swe/RESULT.md:1-9`
- `reports/evidence/inv_r1_e1_swe_ceiling/RESULT.md:1-14`, `.../matrix.json` `path_fork`, `rows`
- `reviews/STAGE-09-FINDINGS.md:154` (N-58)
- `reports/STAGE-09-MILESTONE-GAPS.md:99-118`
- `WORKER-STAGE-09-CONNECTED-STUDY.md:47`
- `evidence-ad01/c3-trajectories-merged/use-w1-I.json`, `evidence-ad01/c3-authored/use-w1-I.json`
