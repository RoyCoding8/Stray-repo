# W1 SWE executor capability — measurement and repair

Lane: `w1-swe-executor`. Branch `wt/w1-swe-executor`. Host: Windows, CPython 3.13.14,
no POSIX `resource` module.

## The claim under test

`reports/cap-sheets/w1-e1-cap.md:75` records the typed-AST SWE cell as
**"missing — executor cannot read a file, run a test, or return a value"**.

Nothing in the repository had measured those three against the code. This lane
measured them.

## Result per capability

All three are **PRESENT**, in `experiments/ad01/s09_swe_world.py`, the executor
every SWE arm runs through:

| Capability | Verdict | Evidence |
|---|---|---|
| (a) read a file | **PRESENT** | `s09_swe_world.py:212-213` publishes `source` as `{"line", "text"}` per line; `SweSession.policy_view` at `:240-250` re-derives it from the live line buffer, so it tracks every applied edit. `SweSession.inspect` at `:308-315` serves metered line reads. |
| (b) run a test | **PRESENT** | `SweSession.run_public_test` at `:293-294` runs a named public test and returns expected/actual/kind; `run_all_public` at `:296-306`. Reached through the action boundary at `apply_action` `:432-444`, so a policy reaches it as `observe/test.run`. |
| (c) return a value | **PRESENT** | Every public operation returns a concrete result: `localize` `:317-327` returns coverage evidence, `try_edit` `:329-351` returns a pass count, `repair` `:353-384` returns the post-edit tally, `score` `:391-395` returns the final report. |

Measured values from the real path, held-out instance
`swe-held_out-count-tail-sum-1fdc31`:

```
view.source[0]          {'line': 1, 'text': 'def tail_sum(body, n):'}
run_public_test(case-01) {'test': 'case-01', 'expected': 76, 'actual': 121, 'kind': 'value'}
run_all_public()        {'passed': 0, 'total': 2, 'observed': ['case-01', 'case-02']}
```

The typed-AST arm returns a value too. Driving the frozen interpreter's own
`_execute_document` on a real view returns an `observe` action whose `test`
input is `case-01`, a name the world published. It is contingent on the
observation, not a committed table.

## CONFIRMED or REFUTED

**REFUTED, with one correction that matters.**

The executor was never missing. The genuine limit is narrower and belongs to
the frozen *node set*, not the executor: `boolean_ast_policy._VIEW_TYPES`
(`boolean_ast_policy.py:47-54`) publishes no field carrying the program under
repair, so a typed-AST document reading it is refused by the loader with
`unknown view field 'source'`. The node set has no string-building op either,
so it cannot compose replacement source text.

That is a **representation** limit, already recorded in
`s09_swe_ast.missing_cells()` and `expressivity()`. The cap sheet reported it as
an **executor** limit. The two must not be conflated: a representation that
cannot express a repair is a finding about the grammar; an executor that cannot
run is a finding about the host, and it would invalidate every arm rather than
one column.

The repository's own docstring already said so at `s09_swe_experiment.py:28-36`,
which means the cap sheet and the code disagreed before this lane ran.

## What was actually broken

The cap sheet's claim was wrong, but the SWE arm was still producing
**misleading numbers**, from three defects on the path the "supported" cell
takes:

1. **`boolean_policy.py:83` staged the policy source in text mode.** On Windows
   `write_text` translates each `\n` to `\r\n`, so the staged bytes were not the
   bytes the digest was taken over. The step refused *itself* with
   `refused: staged policy source digest mismatch` before any child existed.
   This is the same defect class HEAD commit `0a17ca9` fixed in
   `method_exec._stage_text`; that seam had simply not been held to its own rule.
   Now written in binary.

2. **The STEP driver swallowed every executor exception into a bare
   `world.stop_action()`.** A bare stop is indistinguishable from a policy that
   decided it was finished, so a host that never spawned a child produced an
   `unrepaired` row with a one-turn trace. The matrix reports repair rates; this
   made it report the host. The STEP cell now records the shared
   `bridge_refusal` the AST and graph cells already used, and `_row` carries it
   onto the row and `lineage_ledger` counts it as a refusal rather than an
   attempt.

3. **`boolean_policy.py:114-116` discarded `LaunchOutcome.refused_reason`.** A
   pre-dispatch refusal has no receipt, so `read_result` returned nothing and the
   step reported `policy-step-failed: {}` — a status token with no cause. Now
   raised as `refused: <reason>`.

Defects 1 and 2 are what made the arm look like it "could not read, run or
return". With 1 fixed, the true blocker became legible for the first time.

## Honest blocker: this host cannot run the bounded child

Not closed. The remaining blocker is a platform limit, and it is the one that
keeps the E1 SWE arm unassessable here.

```
$ uv run python -c "from experiments.ad01 import s09_swe_experiment as ex; ..."
refused: child-limit-unavailable: child limit(s) cpu_seconds cannot be enforced
on Windows: CPython refuses preexec_fn, so the child cannot limit itself
before exec. Run on a supported Linux host or record this deployment
limitation. The child was NOT run unbounded.
```

Raised by `settlement/launcher_local.py:849-877` (`child_limits_unsupported_reason`)
and `boolean_ast_policy.child_limit_support()` at `:74-107`.

This is the containment machinery behaving correctly. It refuses rather than
running a child unbounded, and it must not be relaxed. The remaining work is a
supported Linux host, or WSL with a working `resource` module; the cap sheet
already notes the Landlock read-denial precondition is also NOT MET and needs
bare metal. **No code change on this host closes it.**

The typed-AST cell additionally cannot run here for a second, independent
reason: even with a spawnable child, its node set has no view field for the
program, so it observes and localizes but cannot repair. That one is a real
grammar limit, recorded and correctly reported.

## Test result

```
43 passed, 2 deselected in 23.75s
  tests/test_s09_swe_executor_capability.py   (new, 15)
  tests/test_s09swe_world.py
  tests/test_s09swe_interface.py
```

The two deselected tests are a pre-existing hang on this host, **not** an
effect of this change. Verified by reverting both source files to HEAD and
running each test alone: both time out at exit 124 on pristine HEAD.

- `test_a_searching_policy_repairs_some_but_not_every_instance`
- `test_a_candidate_edit_that_never_exits_is_refused_not_run`

Both drive an exhaustive candidate search over the held-out panel, which is the
cost the repo's own `test_the_matrix_runs_every_lineage_and_records_every_outcome`
documents ("the real in-process search over this panel did not finish in 280
seconds"). Neither touches the code path this lane changed. Flagging for the
coordinator; not fixed here because it is outside the capability gap.

The full suite was not run, per lane constraints. `tests/_heavy_archived`
(spawns real children) was not included.

## Deliberate-break proof

Each fix was reverted and the suite re-run, then restored and re-run green.

**Break 1 — restore the text-mode write** (`boolean_policy.py:83`):

```
FAILED test_staged_policy_bytes_are_the_bytes_the_digest_was_taken_from
AssertionError: the step refused before dispatch, so the staged bytes were
never observed; the source is written in text mode, which translates every
newline and makes the on-disk digest disagree with the one the record carries
1 failed, 14 passed
```

**Break 2 — restore the bare `stop_action`** (`s09_swe_experiment.py`):

```
FAILED test_every_swe_cell_records_an_executor_refusal_instead_of_a_bare_stop
FAILED test_a_step_refusal_is_counted_as_a_refusal_on_its_own_row
FAILED test_a_step_refusal_on_this_host_survives_the_round_trip_to_the_row
KeyError: 'bridge_refusal'
3 failed, 12 passed
```

**Break 3 — drop the launcher's `refused_reason`** (`boolean_policy.py:114`):

```
FAILED test_every_swe_cell_records_an_executor_refusal_instead_of_a_bare_stop
AssertionError: the refusal reason is a status token with no cause in it:
'policy-step-failed: {}'
1 failed, 14 passed
```

Break 3 initially did **not** turn the suite red — the original assertion only
checked the reason was non-empty, and `policy-step-failed: {}` is non-empty.
The test was rewritten to assert the reason names a cause before the break was
accepted as a valid red proof. Recording this because it is the case where a
green test would have shipped alongside the defect.

After restoring: `15 passed`, and both source files byte-identical to the fixed
backup.

## Files changed

- `experiments/ad01/boolean_policy.py` — binary staging; refuse reason preserved.
- `experiments/ad01/s09_swe_experiment.py` — `_step_refusal`; `_row` carries the
  refusal; `lineage_ledger` counts it; module docstring corrected.
- `tests/test_s09_swe_executor_capability.py` — new, 15 tests.

`boolean_policy.py` is outside `experiments/ad01/`'s SWE-only reading, but the
defect is in the shared step executor the SWE arm calls, and it also affects the
Boolean and representation-matrix arms. Flagging for the coordinator.

## Recommendation for the cap sheet

Replace the SWE typed-AST row with two separate facts:

- **Executor:** all three capabilities present, verified in `s09_swe_world.py`.
- **Typed-AST representation:** cannot repair; no view field for the program and
  no node that builds source text. Witness is the frozen loader's refusal.
- **Host:** the bounded child does not run on Windows, for every arm. Name it
  once as a deployment precondition rather than per cell.
