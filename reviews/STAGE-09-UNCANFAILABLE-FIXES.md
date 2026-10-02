# The six unfailable tests, and what each one now detects

`reports/STAGE-09-FAILURE-CENSUS.md` listed six tests that could not fail or
could not pass. The census named the mechanism for each and prescribed no fix.
This records the fix, the reasoning, and the mutation that proves each one is
falsifiable.

Every fix below is a change to a test. No product file was modified. Each
mutation was made, the red was read, and the product file was restored with
`git checkout --` and confirmed clean with `git status --porcelain`.

## First: there are five defects, not six

The dispatch listed item 6 as "a literal that stops at `0014` when 18 exist",
separate from item 4. It is the same line.

```
$ grep -rn "0014_team_runtime" --include=*.py .
tests/test_rec_checkpoint.py:80:                                      "0014_team_runtime.sql"]
```

One occurrence in the whole repository. There is no second defect to fix and
none was manufactured.

Separately, the census's own table has **six rows** at lines 420-425, and its
sixth row is a different test:

| `file:line` | What it actually is |
|---|---|
| `tests/test_s09_merged_tip_regression.py:339` | constant pin (item 3) |
| `tests/test_rec_checkpoint.py:69` | constant pin, stale (item 4) |
| `tests/test_state_operations.py:127` | constant pin, stale projection (item 5) |
| `tests/test_s09_store_cleanup.py:421` | **tree-fact ratchet** |

`test_c_the_study_admission_path_has_no_production_caller[experiments]` is
still red, and it is still a true positive: `experiments/ad01/e3_ladder.py`
has gained a real call to `authority.admit_study_call(`. The census
classifies it as different in kind, and it is - it asserts a fact about the
tree rather than a return value, and the fact it pins can only be satisfied by
deleting a caller. It is out of scope for this dispatch, it is not a pin that
drifted, and it should not be made green. Verified still red:

```
FAILED tests/test_s09_store_cleanup.py::test_c_the_study_admission_path_has_no_production_caller[experiments]
1 failed, 92 passed in 104.06s (0:01:44)
```

## 1. `test_s09_swe_experiment.py` - the paired-comparison test

### What was wrong

`supported_lineages()[:1]` yields one `python-step` lineage.
`paired_comparisons` emits a pair only when the two sides differ in kind, so
one lineage per task means the inner loop never runs and `assert pairs` can
never pass. The property at the old line 211 was unreachable.

### The rejected fix, and why

The dispatch offered two options: widen the panel to two kinds, or build the
test differently. **Widening to two *supported* kinds is not available**, and
this is the load-bearing measurement:

```
$ .venv/bin/python -c "from experiments.ad01 import s09_swe_experiment as m; \
    print(m.supported_lineages(m.TYPED_AST), m.supported_lineages(m.ACTION_GRAPH))"
() ()
$ .venv/bin/python -c "...; print(m.support()['supported_representations'])"
['python-step']
```

Every `typed-ast` and `action-graph` lineage has `built_ok=False`, and always
has: the AST cell records a frozen-validator refusal and the action-graph cell
records a world-binding refusal. `support()` says so in the product's own
words. So `supported_lineages(kind)` returns empty for both other kinds, and
"widen to two supported kinds" is a description of a panel that does not
exist. The panel was widened the other way instead.

`run_matrix` reports an unbuilt cell as a row per instance with
`outcome="refused"` and the build refusal as its text. A refusal is a row
like any other, so it pairs. The panel is now one `python-step`, two
`typed-ast`, one `action-graph`, and pairing is computed over what the run
actually produced - one cell builds, two do not, and the result says so.

### What this detects that it did not before

- That `paired_comparisons` pairs the *same* instance and never a different
  task.
- That it refuses to pair two lineages of the same kind. The two
  `typed-ast` lineages are in the panel specifically so a same-kind row pair
  exists to reject; with one lineage per kind the filter would never execute
  and a mutation removing it would pass. The test asserts `same_kind > 0` so
  it cannot silently stop covering that branch.
- That the matrix still builds lineages for all three representations.
- That a built cell actually runs, so the panel is not pure refusal
  bookkeeping.

### Cost

The old construction used `in_process_driver_factory`, the real search. Over
this panel that did not finish in 280 seconds. The test now uses a driver that
stops immediately, so it measures pairing and not scoring, and runs in **3.08
seconds**. The `@slow` marker was dropped with the subprocess dependency that
justified it. The rows still come from `run_matrix` through its normal path
and the refusal text is still the build's own.

### Red before

The test could not pass as written; the failure was a standing red. A
one-kind panel now fails legibly:

```
>       assert not missing, (
E       AssertionError: the matrix no longer builds a lineage for ['typed-ast', 'action-graph'], so a panel
E       cannot span the kinds this property needs
```

### Red after, three mutations

Same-kind filter removed from `paired_comparisons`:

```
>           assert pair.left.representation_kind != pair.right.representation_kind
E           assert 'typed-ast' != 'typed-ast'
1 failed in 2.79s
```

Pairing no longer grouped by task:

```
>           assert pair.left.task_id == pair.right.task_id
E           AssertionError: assert 'swe-held_out...en-sum-2df52d' == 'swe-held_out...en-sum-347fcb'
1 failed in 3.38s
```

All cells collapsed to one kind:

```
>       assert not missing, (
E       AssertionError: the matrix no longer builds a lineage for ['typed-ast', 'action-graph'], ...
1 failed in 1.38s
```

**No test was deleted.**

## 2. `test_s09_test_db_safety.py` - `HAZARD_CEILING`

### What the ceiling should be, and why

**1, not 0.** The measurement is one real file:

```
$ .venv/bin/python -c "from experiments.ad01 import s09_test_db_safety as s; print(s.census()['files_with_literal_drops'])"
['test_c14_live_already_spent_source.py', 'test_s09_test_db_safety.py']
```

Excluding this file, the hazard is one file. Pinning 0 while the docstring
says "the hazard may shrink, it may never grow" is what made the assertion
unreadable: a ceiling of 0 can only ever move red, so the direction the
docstring claims to care about did not exist.

The finding is a true positive and is now visible rather than suppressed.
`test_c14_live_already_spent_source.py` names `ad01-campaign-invl02-live-e0`
in a literal and drops a database in the same file. It predates the
conversion, it creates the database it drops, and the drop is scoped to
`v3_c14_spend_source`, a name only that file knows. It is named in
`ACCEPTED_FINDINGS`, and the census checks that the flagged set and the
accepted list agree in both directions.

So the ceiling expresses a bound, and the accepted-findings list expresses
the judgement. Keeping them separate is what makes adding to the hazard an
explicit act rather than something that happens because a file appeared.

### Red after, both directions

A new hazard file planted in `tests/`:

```
>       assert len(others) <= HAZARD_CEILING, others
E       AssertionError: ['test_c14_live_already_spent_source.py', 'test_uncf_planted_hazard.py']
E       assert 2 <= 1
>       assert set(others) <= set(ACCEPTED_FINDINGS), (
E       AssertionError: accepted findings and the flagged set disagree; unlisted=['test_uncf_planted_hazard.py'] ...
3 failed, 5 passed in 0.90s
```

The fall direction, which is the one the old pin could not express: with the
accepted finding removed from the tree and the ceiling deliberately left at 1,
the hazard drops to 0 and the suite stays green.

```
........                                                                 [100%]
8 passed in 0.78s
```

**No test was deleted.** One test was added (`test_a_fall_in_the_census_is_not_a_failure`)
and one (`test_the_findings_are_still_visible`).

## 3. `test_s09_merged_tip_regression.py` - the 96-name snapshot

### Does the equality half earn its place?

No. It could only be repaired by hand, and thirty-one genuine campaign tests
had been added to the tree with the gate left red against them. The count
drifted because nobody edits a snapshot on every add, and nothing prompted a
reconciliation. It also could not express the property that matters: it said
nothing about whether a campaign module still had a test reaching it.

It is replaced by three derived properties.

| Property | Replaces |
|---|---|
| `test_a_committed_campaign_test_still_exists` | the deletion half, read from the git index rather than from a typed list |
| `test_every_campaign_test_file_is_a_real_assertion_bearing_test` | the `has_real_assertions` parametrisation, walked from the tree |
| `test_every_campaign_module_is_reached_by_a_campaign_test` | nothing; this is the new direction |

Deletion detection needed the git index rather than the working tree: a
deleted file is simply not there to be compared, so the tree cannot answer
"was one removed".

The 16 files with no import edge are declared in `NO_IMPORT_EDGE`. This was
measured, not guessed. Each of the fourteen non-subprocess entries imports
only the shared `settlement` layer:

```
$ grep -nE "^(from|import) " tests/test_s09_n200_capability.py
from settlement import broker, launcher_local, store
from settlement.broker import BrokerOp
```

so they have no edge by construction. `test_s09_probe_route_ordering.py`
imports `e3_ladder`, which is not in `CAMPAIGN_GLOBS`. The two subprocess
files name campaign modules as strings.

### The finding this surfaced

The module-reachability property immediately failed on **five campaign
modules with no test at all**:

```
E       AssertionError: campaign modules no campaign test reaches: ['experiments.ad01.s09_e1_fork_probe',
E         'experiments.ad01.s09_e1_gates_probe', 'experiments.ad01.s09_e1_world_fit_probe',
E         'experiments.ad01.s09_m2_join', 'experiments.ad01.s09_m2_reload_proof'].
```

A repo-wide grep confirms no importer of any of the five exists outside the
module itself. This is a real coverage gap that the snapshot could not see,
and it is declared in `UNTESTED_CAMPAIGN_MODULES` so the gate is green and
the finding stays legible. The assertion is exact in both directions, so a
sixth untested module fails the gate.

**Two bugs were found in the new test while proving it**, both mine, both
caught before commit. Seeding `reachable_modules` with `set(campaign)` made
`unreached` always empty, so the test passed for a reason unrelated to
coverage; and `campaign_test_intersection()` returns repo-relative *paths*
while the edge map is keyed on dotted *module names*, so the join never
matched. Both are fixed, and the corrected version is what found the five.

### Red after, three mutations

Committed campaign test deleted from the tree:

```
E       AssertionError: campaign test files committed but absent: ['test_s09_verdict.py']
FAILED tests/test_s09_merged_tip_regression.py::test_a_committed_campaign_test_still_exists
```

Campaign test emptied of its assertions:

```
E           AssertionError: test_s09_verdict.py contains no assert at all: a green file that checks nothing
E           assert 0 > 0
```

A new campaign module with no test:

```
E       AssertionError: campaign module coverage moved. newly untested=['experiments.ad01.s09_uncf_newmodule'] newly covered=[].
E       Land the test and drop the entry, or add the module and accept it.
```

**No test was deleted.** Two were replaced by three.

## 4. `tests/test_rec_checkpoint.py` - the `0014` pin

The manifest side is real (`scripts/checkpoint.py:115` runs
`SELECT name FROM schema_migrations ORDER BY name`) and everything else in
the test is genuine artifact verification. Only the fourteen-name literal was
a pin, and it could only be repaired by typing the four new names in.

It now derives the expectation from `migrations/`. This is not a tautology:
the manifest's side is what the database recorded, and the derived side is
what the repository contains. It says the checkpoint recorded exactly this
repo's migrations, in name order. The sha256, the tar member, the control
epochs and the row counts are untouched.

```
$ .venv/bin/python -c "import os; print(len([f for f in os.listdir('migrations') if f.endswith('.sql')]))"
18
```

### Red after

Filter `001*` out of the manifest migration list in `checkpoint.py`:

```
>       assert manifest["migrations"] == migrations
E       AssertionError: assert ['0001_schema...nce.sql', ...] == ['0001_schema...nce.sql', ...]
E
E       Right contains 9 more items, first extra item: '0010_agenda01.sql'
1 failed in 3.32s
```

**No test was deleted.**

## 5. `tests/test_state_operations.py` - the stale projection

`a3df674` added `payload` to the `execution_versions` select so an
unresolved-terminal disposition is recorded. A full-row literal could only be
repaired by deleting the new key from the expectation, which is the opposite
of a check.

Two changes, and the second one matters. Projecting to
`(id, execution_version)` is not enough on its own. With the original single
operation at `exec-v3`, a product that pinned the column to a constant
returned exactly what the test expected, so the projection was still
unfalsifiable on value. `opA` now carries `exec-v9`, a version no other
operation in the file uses.

### Red after

Constant in place of the column, mutation verified present before and after
the run:

```
PRE-RUN mutation present:
1
>       assert versions == [("opA", "exec-v9")]
E       AssertionError: assert [('opA', 'exec-BOGUS')] == [('opA', 'exec-v9')]
E
E       At index 0 diff: ('opA', 'exec-BOGUS') != ('opA', 'exec-v9')
FAILED tests/test_state_operations.py::test_restart_reconciliation_reports_registry
1 failed, 5 passed in 12.81s
POST-RUN mutation still present:
1
```

And the survivability check, the change that originally broke it: dropping
`payload` from the select leaves the file green, which is the point of a
projection.

```
PRE-RUN payload dropped:
1
......                                                                   [100%]
6 passed in 13.13s
```

**No test was deleted.**

## A note on mutation discipline

One earlier mutation run returned green while a mutation was provably in the
file, because a concurrent lane reverted `src/settlement/store.py` mid-run.
That evidence was void and was redone. Every mutation above is now verified
present in the file *before* and *after* the test run, and every restore is
`git checkout --` followed by `git status --porcelain` confirming clean. A
`cp` from a backup can restore a backup taken mid-mutation; the git checkout
cannot.

Two things this caught that would otherwise have shipped:

- A test that passed for a reason unrelated to the property it names.
- A "fix" that reproduced the fixture's own constant and therefore tested the
  fixture.

## Test counts that changed

| File | Before | After | Why |
|---|---|---|---|
| `test_s09_test_db_safety.py` | 5 passed, 1 failed | 8 passed, 0 failed | two tests added for #2; the failing one now green |
| `test_s09_merged_tip_regression.py` | 125 passed, 1 failed | 32 passed, 1 skipped | 3 tests replaced 2; the 96-case `parametrize` is now one tree walk |
| `test_rec_checkpoint.py` | 3 passed, 1 failed | 4 passed, 0 failed (with `test_state_operations`) | pin derived from `migrations/` |
| `test_state_operations.py` | 5 passed, 1 failed | 6 passed, 0 failed (counted above) | projection, plus a distinct version so it is falsifiable on value |
| `test_s09_swe_experiment.py` (this test only) | 1 failing, unrunnable | 1 passed in 3.08s | rewired; `@slow` dropped with the subprocess dependency |

Nothing else changed. The four files in the first four rows total
**8 + 33 + 10 = 51 passed, 1 skipped**, and the SWE test is the 51st.

`tests/test_s09_store_cleanup.py` was run and is **92 passed, 1 failed**: the
failure is the census's separate tree-fact ratchet, described above, and it is
pre-existing. `tests/test_eng_close1.py`, `tests/test_settle_actual.py`,
`tests/test_ui_commands.py` and `tests/test_ui_views.py` were modified in the
working tree by other lanes during this dispatch. None is mine and none was
touched.
