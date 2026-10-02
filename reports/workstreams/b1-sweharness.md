# B1, repair the SWE harness fork, not the DSL

Offline lane. No live model call, no network. Fixture gateway only.

## Verdict first

The assignment's premise does not survive contact with the tree. Two of its
three factual claims are false of `f03db5b`, and the lane was pointed at the
wrong work as a result. Acceptance was either three comparable representation
kinds or a new refusal with a concrete witness per unsupported cell. The second
outcome is what happened, but not for the reason the inventory gave, and one of
the two recorded refusals was itself false and is now corrected.

| Representation kind on the SWE world | Before | After | Disposition |
|---|---|---|---|
| `python-step` | supported | supported | keep |
| `typed-ast` | supported, recorded as unable to write source text | supported, recorded as unable to read the program | repair the record |
| `action-graph` | refused | refused | repair the harness |

All three cells build and run through their own real executors. None is
comparable with the others through `compare_arms` yet, and the three
blockers are named below. Acceptance was therefore outcome (b): a refusal
with a concrete witness per cell, not three comparable kinds.

The typed-AST cell's recorded reason was wrong and is now right. That is a
repair of the study's claim, not a new capability. **No notation was added.**
The DSL is untouched.

## The premise, measured

**Claim: the view contract has seven fields and the fork is open.** False.
`VIEW_CONTRACT_FIELDS["software-fault-repair-v1"]` declares twelve, the SWE
world publishes twelve, and `path_fork()` reports `common_path_usable: true`,
`missing_from_swe: []`, `extra_in_swe: []`. The per-world view contract landed
in `d17b5a7`, which replaced the old eight-field equality check with an exact
per-world declaration. Extending the contract as instructed would have been
work against a repair someone else already made, and would have widened a
declared surface rather than fixed a defect.

**Claim: `s09_swe_ast.py:303-335` holds `ordering_graph_policy._parse_action`.**
False. `_parse_action` lives in `ordering_graph_policy.py:261` and has never
lived in the SWE AST module (`git log -S` finds only a removal of the
witness *strings*). Lines 303-335 hold `missing_cells`, which describes the
defect rather than implementing it.

**Claim: both refusals are harness and view-field defects, so repair the
harness.** Half true. The graph defect is real and is a harness defect. The
typed-AST refusal was not a defect at all; it was a false statement about the
executor, and the correct repair was to correct it.

## What the typed-AST cell can actually do

The recorded missing cell claimed two limits. One is false.

`frozen._load` accepts a document whose edit payload is assembled by `obj` and
`list` nodes rather than spelled as raw JSON; the SWE world admits the
resulting `use/code.repair`; `SweSession.apply_action` runs the edit and
reports `repaired.edited == [3]`. The node set builds replacement source text.
`tests/test_inv_b1_swe_view.py::
test_the_typed_ast_cell_builds_replacement_source_text_and_the_world_runs_it`
drives all three steps.

The old witness was also citing a validator the arm never calls. It quoted
`frozen._validate_action` refusing with `action 'use' is not available in the
Boolean world`, but `s09_swe_ast._validate_action` delegates to
`swe.admits`, and the SWE world admits a repair. The refusal being recorded was
the Boolean world's rule, surfaced by a validator that is not on this arm's
path.

The real remaining limit is narrower and now recorded as such: `_VIEW_TYPES`
publishes no field carrying the program, so an edit line cannot be chosen from
what the arm observed. The cell writes edits at a line its record names and
cannot localize that line from the program. `missing_cells()["typed-ast"]
["builds_source_text"]` is now `True` and says so in data, and
`expressivity()` reports writing under `can` and reading under `cannot`.

## The three remaining blockers, each with a witness

These are what stops `compare_arms` reaching `comparable` on the SWE world. Each
is a named input and a named reason, driven by the real executor in
`test_compare_arms_on_the_swe_world_reports_each_arms_own_named_refusal`.

**1. The STEP arm never starts. Harness signature, not a policy defect.**
`_run_arm` calls `arm.driver_factory(record, **step_budget)` and
`s09_swe_experiment.lineage_driver(lineage)` takes no such keyword.
Witness: `driver-factory-failed` /
`TypeError: lineage_driver() got an unexpected keyword argument 'timeout_ms'`.
The STEP cell is otherwise the supported one.

**2. The typed-AST arm is refused by the world at turn time.** It reaches the
world and is refused with `stop target must be swe.task`
(`s09_swe_world.py:431`), because the frozen Boolean interpreter's own step
contract wants `boolean.task` and the SWE arm does not rename it. Different
from the refusal the inventory recorded.

**3. No graph arm reaches a world turn at all, on any world.** The parity
harness runs graph arms in a bounded child (`s09_graph_budget`) so all three
representations answer under one compute bound. That child receives the
repository root as `sys.argv[1]` and puts it on `sys.path`, but the package it
imports lives under `src/`. The child dies with
`ModuleNotFoundError: No module named 'settlement'` before any graph is loaded,
and the harness reports the symptom as `GraphBudgetRefused: graph step failed in
child: no receipt`. This is the largest of the three and it is not in this
lane's files.

## The tests, and what each proves

All in `tests/test_inv_b1_swe_view.py`, 11 tests.

| Test | Proves |
|---|---|
| `test_the_swe_view_contract_is_declared_and_the_world_is_admitted_whole` | the fork is closed; 12 declared, 12 published, no missing, no extra |
| `test_the_typed_ast_cell_builds_replacement_source_text_and_the_world_runs_it` | the false recorded limit is false: loader accepts, world admits, edit runs |
| `test_the_typed_ast_cells_remaining_limit_is_reading_the_program` | the real limit, measured by the loader's refusal, and the stale clause is gone |
| `test_a_graph_arm_cannot_act_on_a_value_the_evaluator_read` | two views differing only on the guard's field yield byte-identical actions |
| `test_the_graph_child_cannot_import_settlement_so_no_graph_arm_reaches_a_turn` | the largest blocker, named at the cause |
| `test_the_swe_world_admits_a_localize_that_reads_the_failing_test_it_observed` | the gate a repaired graph arm would have to pass already admits at turn time |
| `test_compare_arms_on_the_swe_world_reports_each_arms_own_named_refusal` | all three arms named with their own reason |
| `test_the_graph_cell_records_its_own_witness_on_the_lineage` | the unfillable cell stays recorded and names the executor |
| `test_the_swe_action_vocabulary_admits_all_five_kinds_the_cell_uses` | the world offers every shared kind but `probe` |
| `test_support_names_all_three_representations_and_why_they_are_not_comparable` | the study's own support record, corrected and still honest |
| `test_every_declared_lineage_builds_for_all_three_cells` | 4 lineages per cell, 12 building, so a zero repair rate is not a dead arm |

## The graph view-read defect

Proved offline on the Boolean world as asked, and it is real.
`ordering_graph_policy._parse_action` (`ordering_graph_policy.py:261`) deep-copies
the raw action node, so the value `_evaluate_guard` read is discarded and the
emitted action is the literal the record spelled.

The proof is by disagreement rather than by reading. A record whose guard reads
`observed.0.y.0` is handed two views that differ only in that field. If the read
value reached the action the two emitted actions could not be byte-identical.
They are byte-identical. See
`test_a_graph_arm_cannot_act_on_a_value_the_evaluator_read`.

**This is B2's work and it is outside my paths.** `ordering_graph_policy.py` is
not mine. I proved the defect and left it open rather than fixing it, and the
test asserts it is still open so a future repair turns the test red instead of
making the record silent. `path_fork` names B2 as following B1, which is the
right order for a separate owner.

## Changes outside my declared paths

Five files, all recorded rather than silently made.

- `experiments/ad01/s09_swe_experiment.py` — the module docstring repeated the
  false source-text claim, and `support()` still reported one supported
  representation. Both corrected. The docstring is a comment; the `support()`
  dict is data a reader would otherwise take at face value.
- `tests/test_s09_swe_experiment.py` — asserted the witness carries
  `"not available in the Boolean world"`, quoting a validator the arm never
  calls. Replaced with the loader clause that is on the path. The
  `view.source` refusal assertion is untouched, so nothing was relaxed.
- `tests/test_s09_swe_binding.py` and
  `tests/test_s09_swe_executor_capability.py` — docstrings only. Both repeated
  the false claim; neither asserted it.

I did not fix any of the three harness blockers. Each lives in
`s09_graph_budget.py`, `s09_swe_experiment.lineage_driver`, or the frozen
interpreter's stop-target contract, and each is a coordinator call about which
boundary owns the rename.

## Baseline correction

The coordinator's known-baseline note named one pre-existing failure. The gate
actually showed **13** on a tree with zero edits of mine. All thirteen are
environmental and share one cause: `/tmp/settlement-claims` is root-owned, so
every bounded child that needs a durable claim ledger refuses with
`claim-not-durable` (`launcher_local.py:879`). Setting
`SETTLEMENT_CLAIM_LEDGER` to a writable path clears all thirteen and the
baseline becomes 58 passed. Worth recording, because every lane that runs
bounded children on this host will see it and misread it as its own breakage.

The command below includes the override. Without it the gate reports 13
failures that have nothing to do with this lane.

## Verification

```
wsl -d ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/b1-sweharness && \
  SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claim-ledger-b1/claims.jsonl PYTHONPATH=src:. \
  timeout 2400 /home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_inv_b1_swe_view.py tests/test_s09_arm_parity.py tests/test_s09step_arm.py \
  tests/test_ordering_graph_policy.py -q -p no:cacheprovider'
```

Summary line:

```
69 passed in 43.58s
```

Two contract corrections outside my declared files are covered above. The
verification section's prose about them is superseded by the "Changes outside
my declared paths" section, which lists all five files.

**A regression I did not fix, verified as pre-existing.** Three tests in
`tests/test_s09_swe_executor_capability.py` fail
(`test_every_swe_cell_records_an_executor_refusal_instead_of_a_bare_stop`,
`test_a_step_refusal_is_counted_as_a_refusal_on_its_own_row`,
`test_a_step_refusal_on_this_host_survives_the_round_trip_to_the_row`). They
expect the STEP cell to record a refusal stop on this host and get a
`construct` instead. I checked these five files out at the base commit
`f03db5b` with my work removed and re-ran the three: they fail identically.
They are not mine and I did not chase them. Whether they are correct is a
question about this host's bounded child, and resolving it is another lane's
call.

Regression tests were watched failing before the fix. Two failed: the
`missing_cells` assertion caught the false source-text claim, and the graph-child
assertion caught my own bad assumption about how the child's path is passed,
which I corrected. The first green run was nine passes with no change to
production code, which meant the file was characterizing rather than
constraining; the assertions added after it are what made it a regression
test.

## Recommendation to the coordinator

Three repairs, in this order, none of them a DSL.

1. **`s09_graph_budget` child path.** Add `src/` to the child's `sys.path`
   alongside the root. This unblocks the graph cell on every world and is the
   single highest-value fix in the set.
2. **`lineage_driver` signature.** Accept and honour the step budget
   keywords, or have the SWE STEP arm register through a factory that does.
3. **Boolean stop-target rename on the SWE AST path.** The frozen interpreter's
   step contract wants `boolean.task`; the SWE arm needs `swe.task`. A rename at
   the arm boundary, not a change to the frozen executor.

With 1 and 2 landed the STEP and graph cells become comparable on the SWE world
through `compare_arms`, and the typed-AST cell is one rename away. I did not
build that machinery because all three live outside my paths and each is a
coordinator call about which boundary owns the rename.