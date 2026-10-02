> **INVALID RESULT - 2026-09-27.** The matrix in this directory was produced by a
> harness that deduplicated candidates on `candidate.strip()` and appended the
> stripped form, so every candidate for a line inside a function was an
> `IndentationError` and `code.try` scored 0 of 2 even for the correct repair.
> Two full 156-episode runs read as a clean zero before this was caught, and
> `run_program` caught only `SyntaxError`, so a malformed candidate crashed the
> harness instead of scoring zero. **The 0-of-24 repair rate here is a defect
> artifact and must not be cited as a capability result.** The probe-reach
> analysis below is a measurement of a broken run and is retained only to show
> what a clean run must still re-measure. The re-run lives in
> `../inv_r1_e1_swe_ceiling/`.

# E1 on the SWE world: wiring and qualification are done; the matrix is NOT

Instrument: `software-fault-repair-v1`, `experiments/ad01/s09_swe_world.py`.
Driver: `experiments/ad01/s09_swe_experiment.py`.
Machine-readable evidence: `matrix.json` in this directory.

> **STATUS: the matrix in `matrix.json` is NOT a valid result and must not
> be read as one.** It reports 468 rows and zero repairs, and that zero is
> an artifact of a candidate generator that produced syntactically broken
> edits (§4). A later corrected run reached 13/39 in-process, but the
> instrument was being rewritten by another lane while that run was in
> flight — its `probe` budget changed 60 → 268 → 11 → 303 across four
> minutes — so no completed full-matrix run exists against a stable
> instrument. What follows separates what is *established* from what is
> *blocked*.

**Read this first.** The comparison in this directory is *one
representation wide, not three*, and it ran on the *world's own driver,
not the common harness path*. Both facts are load-bearing and neither is
a caveat. Two of the three representations have a measured, recorded
missing cell, and the third ran alone. There is no three-way comparison
here and no result should be read as one.

---

## 1. The path fork, stated before any number

Every E1 result in this directory was produced by
`s09_swe_world.run_episode`, not by `s09_arm_parity.compare_arms`.

The common harness hands every arm a `contract_view`, and
`admit_world_view` (`s09_arm_parity.py:298-366`) demands a public state
whose field set is *exactly* eight. The two incumbent worlds publish
those eight. The SWE world publishes twelve:

| | fields |
|---|---|
| harness requires | `action_schema`, `hypothesis_class`, `instrument`, `max_queries`, `observed`, `remaining`, `split`, `task_id` |
| SWE publishes | those minus `hypothesis_class`, `max_queries`, `observed`, plus `entry`, `last_effect`, `max_budget`, `public_tests`, `source`, `structure`, `symptom` |

`admit_world_view` therefore returns `non-contract-action-kind` for every
SWE view. This is pinned by
`test_a_swe_arm_is_refused_by_the_harness_view_normaliser`, and it is
reported in the evidence itself under `path_fork`, not only here.

**What this means for the numbers.** They are comparable *within* this
driver and *across* the four `python-step` lineages. They are **not**
comparable with the boolean or ordering worlds, which ran under the
common path. Any table that puts a SWE number next to a boolean number
is comparing two different execution paths and is wrong.

**The fork, with both readings.** The evidence favours normalising the
harness, for a reason that is about the task rather than about taste.

* *Widen the harness* so `admit_world_view` accepts a superset, and have
  every world publish `max_queries` and `hypothesis_class`. Cost: the
  SWE world has a bounded catalogue, not a hypothesis space, so
  `hypothesis_class` would have to be fabricated. `boolean_ast_policy`
  reads `_VIEW_TYPES` from that field, so a fabricated one is not inert;
  it becomes a typed input the node set believes in.
* *Normalise the SWE world* by projecting twelve fields to eight. Cost:
  the projection must drop `source`, and `source` is the program under
  repair. An arm holding an eight-field SWE view has no program and
  cannot attempt the task, so the cell would pass the harness by being
  unable to do the work.

I did neither. Both change files outside this lane's ownership, and doing
either quietly would make this run look like a common-path comparison
when it is not. The fork is a coordinator decision.

**World-addressability, separately.** `swe` is now registered in
`s09_arm_parity._WORLDS` (`s09_arm_parity.py:39-48`) and
`episode_runner("swe")` returns `s09_swe_world.run_episode`. The
instrument is genuinely addressable by name; the tests that pin it fail
if the registration is removed. Separately, `run_episode` now publishes a
`queried` spend record, which is what `_run_arm` reads before it will
score an arm (`s09_arm_parity.py:764-769`); without it the harness
refused the world for a second, independent reason. Those two changes are
what move the world from "unaskable" to "addressable but not comparable
under the common normaliser". They do not make it comparable.

---

## 2. Requirement by requirement

| # | Handoff requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Small executable program | **met** | `s09_swe_tasks.py:546-556` compiles and `exec`s the candidate; 9 real Python programs across 3 structures |
| 2 | Public failure symptoms | **met** | `s09_swe_world.py:167-196`; `_observe` returns `{test, expected, actual, kind}` |
| 3 | Bounded tools for inspection, test choice, localization, repair | **met** | `inspect`/`localize`/`try_edit`/`repair` at `s09_swe_world.py:198-263`; budgets `{inspect:4, test:2, localize:2, probe:60, edit:1}` enforced in `_spend` (`:156-159`) |
| 4 | Policy chooses actions from observations | **met** | the STEP lineage branches on `view["symptom"]`; pinned by `test_the_search_policy_really_is_observation_driven` and `test_a_row_never_carries_the_fault_label_into_the_policy_view` |
| 5 | No fault label to the policy | **met** | view is 12 allowlisted fields (`s09_swe_world.py:94-112`); `tasks.FAULT_LABEL_KEYS` disjoint; verified live |
| 6 | No hidden patch | **met** | `patch` absent from the view; the reference line is *not* in the view — the identical-looking string that is present is the **faulty** line, which is public source by design |
| 7 | No protected test answers | **met** | protected name, args and expected all absent; `test_the_protected_test_is_never_accepted_as_a_public_test_name` |
| 8 | No helper that chooses the repair | **met** | `repair` applies only what the policy supplies and refuses otherwise (`s09_swe_world.py:243-251`); `test_repair_refuses_to_act_without_a_policy_supplied_edit` |
| 9 | Multiple program structures | **met** | 3: `counting`, `state_machine`, `accumulator` (`s09_swe_tasks.py:32`); structurally distinct per `test_the_three_program_structures_are_structurally_distinct` |
| 10 | Multiple fault mechanisms | **met** | 8 mechanisms over 4 roles (`:37-57`) |
| 11 | Templates separated across dev/assessment | **met** | dev `{count-lead-sum, scan-depth, token-width}`, held-out the other 6 (`:393-397`); disjoint, pinned |
| 12 | Fault families separated across dev/assessment | **met** | dev `{inverted_guard, off_by_one, stale_accumulator}`, held-out the other 5 (`:61-62`); disjoint, pinned |
| 13 | ≥4 distinct task families | **met** | 15 (structure × mechanism) pairs in held-out; 3 structures × 5 mechanisms is the full cross |
| 14 | ≥24 held-out instances | **met** | **30**, exceeding the bar |
| 15 | All held-out instances distinct and solvable | **met** | 30 distinct faulty programs, 30 distinct public-arg sets, 30/30 repaired by restoring the reference, 30/30 fail while faulty |
| 16 | ≥4 independent acquisition lineages per supported cell | **met for the one supported cell** | 4 `python-step` lineages, four distinct record digests (`b9b74fb5`, `c46e341e`, `e19a15fb`, `f3fc436c`); independence asserted on record bytes, not names |
| 17 | Bounded development-only repairs | **met** | all budget enforcement is in `_spend`; the repair path is a single `edit` spend |
| 18 | Report every lineage including failures | **met** | all 12 lineages appear in `matrix.json` under `lineages`; the 8 refused ones appear as `refused` rows with their refusal text, not as absence |
| 19 | No replication by replay or relabelling | **met** | each episode gets a fresh driver closure; lineage identity is the record digest; `test_a_lineage_never_reuses_another_lineages_episode_state` |
| 20 | Paired comparisons | **partially met** | `paired_comparisons` pairs the same instance across representations, and is exercised. **But with one supported cell there are no cross-representation pairs to form** — every produced pair is `python-step` vs a refused cell, i.e. a pairing of a run against a refusal. Reported, not inflated. |
| 21 | Per-family tables, no pooling of a failure | **met** | `per_family_table` keys on (structure, mechanism) and keeps zero-repair families; `test_a_failed_family_is_reported_rather_than_dropped` |
| 22 | 3 representations | **NOT met** | 1 supported, 2 with demonstrated missing cells (§3) |
| 23 | If a representation is inexpressive, demonstrate with a concrete attempted behaviour, record the missing cell, continue the matrix | **met** | §3; each missing cell records the actual loader/validator refusal text, and the graph absence claim is *checked* against the live `World` value |

---

## 3. The two missing cells, demonstrated

Neither is asserted. Each records what the real loader or validator said.

### typed-ast — a world binding and a missing view, **not** a grammar limit

The single most important correction in this lane. My first probe
reported the node set as refusing a repair, and that was **my probe
being malformed**, not a limit of the notation. `return_action` requires
`inputs` to be an *object* node and `evidence_refs` /
`requested_resources` to be raw JSON, not nodes. With the correct shape:

```
loader accepted a repair in the frozen grammar, so the limit is the
world binding and the view, not the node set
```

So the node set **can** write the repair. What is missing is:

* the frozen validator has no `use` action —
  `action 'use' is not available in the Boolean world`
  (`boolean_ast_policy.py:628-668`);
* `_VIEW_TYPES` exposes no field carrying the program —
  `unknown view field 'source'`, and the same for `symptom`,
  `public_tests`, `coverage`.

This matches the precedent in `ordering_ast_policy`, where the same
refusal turned out to be a world binding and the AST got a second-world
arm. Pinned by
`test_the_ast_cell_is_a_world_binding_and_not_a_node_set_limit` and
`test_the_recorded_ast_lineage_states_the_corrected_reason`. **A reviewer
who reads only the earlier framing of this cell should re-read this
paragraph.**

### action-graph — no SWE `World` value exists

The guard vocabulary is per-world, carried in
`ordering_graph_policy.World`. Two refusals are driven, and one absence
is checked:

* `action 'use' is not available in the ordering world`
* `guard references unknown field 'observed.0.actual'`
* a SWE observation is `{test, expected, actual, kind}`, which names
  none of the admitted paths `['earlier', 'left', 'right']`, and `use`
  is not among the admitted kinds.

The third is an absence, so it is made checkable rather than asserted:
`test_the_graph_cell_records_two_refusals_and_one_measured_absence` will
fail if a SWE observation field ever becomes readable, which is exactly
when the cell must be revisited. Building a SWE `World` would be a new
*binding*, not a test of the representation, so I did not build one.

---

## 4. Two defects found by running it, and the finding that governs every rate

### 4a. An instrument defect: a bad candidate crashed the harness

`run_program` (`s09_swe_tasks.py:546`) caught only `SyntaxError` from the
module-level `exec`. A single-line candidate promoted out of the function
body — `width = 0` at module scope — *compiles*, then raises
`NameError: name 'body' is not defined`. That escaped `try_edit`,
escaped `run_episode`, and killed the episode.

This is why my first full run reported **156 unrepaired rows and zero
crashes**: every supported episode had died, and the scorer read a dead
episode as an unrepaired one. That is the worst possible reading of the
same event, and it is worth stating plainly because a reader of that run
alone would have concluded the solver never works.

Fixed in `run_program` and `trace_lines` (both in
`experiments/ad01/s09_swe_tasks.py`, inside my ownership), with
`test_a_candidate_that_fails_at_module_scope_is_a_refusal_not_a_crash`
and `test_a_candidate_that_fails_at_module_scope_traces_as_no_coverage`
pinning it. A candidate is untrusted input, so every way the module body
can fail is an error kind rather than an exception.

### 4b. Two driver defects, and why two full runs read as a clean zero

**The one that mattered: candidates lost their indentation.** My STEP
source's `rewrites` deduplicated on `candidate.strip()` and then appended
that stripped form. A candidate for a line inside the function came out
as `total = total + contribution` with no leading space, which is an
`IndentationError` — so `code.try` reported **0 of 2 for the correct
repair**. Measured directly:

```
OLD candidate try_edit: {'line': 10, 'public_passed': 0, 'public_total': 2}
NEW reference try_edit: {'line': 10, 'public_passed': 2, 'public_total': 2}
```

The search could not win on any instance, for any lineage, ever. Two
full 156-episode runs reported **zero repairs and zero crashes** — the
most credible-looking wrong result available. Fixed in
`experiments/ad01/s09_swe_experiment.py` and pinned by
`test_a_generated_candidate_keeps_the_indentation_of_its_line`, which
also asserts the true repair is generated and scores a full pass.

**The suspect ranking pointed away from the fault.** `suspects` ranked
with `sorted(clean)` — by line number. On a program whose last line is
the `return`, that puts the injected fault *last*, and `MAX_SUSPECTS = 4`
then dropped it before a single candidate on it was dry-run. Fixed to
rank by depth as `s09_swe_policy.suspects` does, pinned by
`test_the_step_suspect_ranking_reaches_the_fault_line`. The ranking
exists twice, once inside the STEP source (the child forbids imports)
and once at module scope (what the driver measures with);
`test_the_module_level_risk_key_agrees_with_the_step_source` fails if
they ever disagree.

**The general lesson, stated because it nearly cost the whole lane.**
Three separate defects presented as the same clean zero, and each time
the zero looked like a *result* rather than a *failure*. A zero across
every cell of every lineage is not a measurement; it is a refusal the
scorer is reporting as an outcome. Any future zero in this evidence
should be treated the same way until the cause is named.

### 4c. The finding that still governs every repair rate

`probe_reach` measures how often the `code.try` budget of 60 reaches
the injected fault line, walking suspects in rank order. Exact figures
are in `probe_budget_reach` in `matrix.json`; the shape is stable across
the fixes: `double_count` is reached on every instance because its
faulty line ranks first, and the other families are reached on a
minority.

**This is what the repair rate measures.** A solver that never dry-runs
the faulty line cannot repair it, so a minority repair rate across a
family is a statement about the budget and the ranking, not about solver
quality. The instrument as configured cannot distinguish a good search
from a bad one on the families the budget never reaches.

A second, independent limit: the candidate generator produces no
*guard repair*. It does not generate `marker = 0 if seen == 0 else 1`
from the faulty `marker = 1 if seen == 0 else 0`, so the `dropped_guard`
family is unreachable for a reason the budget does not explain.
`s09_swe_policy._guard_rewrites` exists for exactly this shape and is
not reachable from the import-free STEP source, so wiring it in is real
work rather than a flag. `inverted_guard` *is* repaired, because that
direction happens to be a literal perturbation.

Two options for the budget, neither taken unilaterally, both outside
this lane's ownership: raise `probe` in `BUDGET_LIMITS`
(`s09_swe_world.py:29-30`), or make the ranking put the fault line
first. Either changes the instrument and needs its own test.

---

## 5. What is and is not supported

**Supported.**

* The instrument is a real, executable, public-symptom fault-repair
  world with bounded tools, and it clears the handoff's diversity bar on
  paper *and* under measurement: 3 structures, 8 mechanisms, 15 families,
  30 held-out instances, 30 distinct faulty programs, 30/30 solvable.
* Templates and fault families are separated across dev and assessment
  on both axes.
* The contamination properties hold against the live view, not only
  against a description of it.
* One representation (`python-step`) is genuinely runnable on this world
  through the shared bounded child, with four independent lineages.
* The typed AST's limit is a world binding plus a missing view field,
  **not** a limit of the notation.

**Not supported.**

* **No valid repair rate is reported here.** The matrix in `matrix.json`
  is zero because of a broken candidate generator (§4b), and the
  corrected run that reached 13/39 used one lineage against a budget
  that has since changed twice. Neither is a result.
* **No three-representation comparison exists.** One cell ran. The
  matrix is one wide, and that will not change while the other two cells
  are refused.
* **No cross-world comparison with boolean or ordering.** Different
  execution path; see §1.
* **The instrument cannot currently measure search quality**, because the
  budget that decides it is being derived and rewritten (§6).
* **No cross-representation pairs exist** to report, because there is one
  supported cell (§2 row 20).
* Nothing here supports a claim about which *representation* is better
  for software repair. It supports a claim about what two frozen
  executors can and cannot bind to on this world, which is a different
  and smaller thing.

---

## 6. What is blocked, and why

* **No completed full-matrix run against a stable instrument.** The
  instrument's `probe` budget, `MAX_TURNS` and `SUSPECT_CAP` were
  derived and rewritten by another lane during this work — `probe` read
  60, then 268, then 11, then 303 within four minutes, and at one point
  `s09_swe_world` did not import at all (`NameError: name 'search' is
  not defined` in `worst_case_probe_cost`). Every repair rate is a
  function of that budget, so no rate I measured is a rate of a fixed
  instrument. **This is the single blocker and it needs a file-ownership
  decision, not more work from me.**
* **The full 156-episode child-process run takes 45-70 minutes** at the
  measured ~29s per episode, so a single stable re-run is feasible but
  not something to attempt against a file that is moving.
* **The corrected in-process run reached 13/39**, with
  `inverted_guard` fully repaired (3/3) and `double_count`, `index_drift`
  and `swapped_window` partially repaired, and `dropped_guard`,
  `missing_advance`, `off_by_one` and `stale_accumulator` at zero. That
  number is real but is **not** a full-matrix result: it used one lineage,
  the in-process driver, and a budget that has since changed twice.

## 7. What I could not determine

* **Jev review was unavailable.** The coordinator recorded it as finding
  N-53: `typesafe-ai/jev` returns `403 RestrictedModelsError` on the
  free tier. Every judgement in this lane is unreviewed by dissent. The
  decisions that would have gone to Jev, in the order I would have put
  them:
  1. **The path fork itself** (§1) — whether a world-driver run is a
     legitimate result when the common harness refuses the world, and
     which side should move. Highest-value question in the lane.
  2. **Whether normalise-harness or widen-harness is right** (§1),
     including whether a fabricated `hypothesis_class` is acceptable
     given `_VIEW_TYPES` would read it.
  3. **Whether the probe budget is a fixture or a finding** (§4) — and
     now, whether deriving it from the panel is sound at all, since the
     derivation changed four times in an hour.
  4. **Whether my own correction to the AST cell (§3) is correct**, since
     I found my own error there and a second reader may find a third.
* **Whether the guard-repair gap is closable inside the import-free STEP
  language.** `s09_swe_policy._guard_rewrites` does it with the `ast`
  module, which the bounded child forbids. I did not attempt a
  string-only rewrite of that generator.
* **Whether the three failing tests added to my test file by the
  concurrent lane** (`test_a_fault_line_is_reachable_within_the_configured
  _probe_budget`, `test_the_probe_budget_is_derived_from_the_panel_and
  _not_typed_in`, `test_a_search_that_finds_the_repair_before_its_probes
  _run_out_applies_it`) pass once the budget settles. At the moment I
  stopped, the gate was 38 passed / 3 failed, and the three failures were
  all budget-dependent.
* **Any claim about which representation is better for software repair.**
  Nothing in this lane supports one, and after the two missing cells it
  never will: there is one supported cell.
