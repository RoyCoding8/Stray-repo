# E3 post-fix: the selection ladder

The committed `reports/evidence/inv_r1_e3_selection/e3-crossover.json` was written at
`02ce64b` and never regenerated. This directory is the post-fix ladder, in its own
namespace, with the historical evidence tree left unchanged.

Source: `experiments/ad01/e3_ladder.py`. Gate: `tests/test_s09_e3_ladder.py` —
**22 passed, 0 failed** at `03:33 UTC`, 195 s, 0 skipped, on an isolated disposable
database per test. Raw numbers: `e3-postfix-ladder.json`.

## What the committed ladder was describing

`s09_e3_selection.crossover()` builds one policy instance per (budget, policy) and reuses
it across all three worlds. Both policies are stateful — `AgendaPolicy` pops from `_untried`
and accumulates `_live`, `FixedPolicy` advances `_step` — so world 1's trajectory decided
what world 2 was permitted to pick, and the three worlds a row summed were not three
independent runs.

**The defect is still in the code.** Running `crossover()` at this tip reproduces the
committed file byte for byte (sha256 `40dba4d6de15e16a…`), so this is not an artifact that
drifted away from its source.

The roadmap credits `52235a6` with fixing `crossover()`'s sharing. It did not: the fix
landed in `sever_control()`, which builds a fresh policy per cell. `crossover()`'s inner
loop is byte-identical across `02ce64b`, `52235a6` and `254f43e`, verified by `git show`
at each ref.

## What the sharing cost

42 of 48 measures moved when each cell got its own policy: 10 of 12 `held_out_reduction`,
9 of 12 `retained_behaviors`, 12 of 12 `diagnoses_correct`, 11 of 12 `resources_used`.

| budget | agenda ret / diag / held-out | control ret / diag / held-out | res (a/c) | agenda ahead on ret | held | diag |
|---|---|---|---|---|---|---|
| 8  | 0 / 0 / 0.000000  | 0 / 3 / 0.000000  | 21 / 18  | no  | tie | no |
| 14 | 3 / 0 / 0.083721  | 0 / 3 / 0.000000  | 42 / 36  | yes | yes | no |
| 20 | 3 / 0 / 0.083721  | 0 / 3 / 0.000000  | 42 / 57  | yes | yes | no |
| 30 | 6 / 6 / 0.111748  | 2 / 5 / 0.111111  | 84 / 81  | yes | yes | yes |
| 40 | 9 / 9 / 0.144745  | 5 / 8 / 0.359281  | 108 / 108 | yes | no  | yes |
| 60 | 15 / 15 / 0.205876 | 8 / 11 / 0.391007 | 165 / 138 | yes | no  | yes |

One policy per cell, three worlds summed. `diagnoses_correct` is scored once per charged
candidate, so at budgets 8, 14 and 20 the control's higher count is a count of more
episodes run, not better diagnoses. The module records the sign per budget and names no
verdict, because reading one column would be a selection of the result in either direction.

## The verdict is INACTIVE on held-out quality

The agenda leads on retention at 5 of 6 budgets and on diagnoses at 3 of 6. It leads on
held-out quality at 3 of 6 — 14, 20, 30 — and the control leads at 8, 40 and 60, by
margins that grow with the envelope (0.359 and 0.391 at 40 and 60 against the agenda's
0.145 and 0.206).

**This is not a benefit, and the direction reverses with the envelope.** The post-fix
sever control had already found the same shape and the roadmap's saturation explanation
for the control's earlier apparent plateau is contradicted by it. That question — whether
the agenda chooses *better* or only *more* — is unanswered by this evidence, and this run
sharpens rather than settles it: the agenda retains 15 behaviours to the control's 8 at
budget 60 and still loses on held-out quality.

The treatment itself is **ACTIVE**: the two policies are not following one schedule. See
below.

## The divergence case

The handoff requires a case where the policies demonstrably choose different
investigations. The census is stronger than one case: **18 of 18** (3 worlds × 6 budgets)
cells diverge, and in every one the first choice already differs, so no cell is a stall
rather than a choice.

World 1 at budget 14, from `divergence_survey`:

```
agenda   seed-sw-ddmin/2, seed-sw-greedy/2     "untried capability ddmin in the software line"
control  seed-gr-ddmin/1, seed-sw-ddmin/1      "pre-committed graph/ddmin step 1 of 1"
```

Across all 18 cells the agenda's rationales never contain the word "pre-committed" and
the control's always do, so the two arms are distinguishable by the reason they record,
not only by the work they name.

## Decisions reached real admitted operations

Verified by SELECT, not copied from an artifact. Per arm, summed over the 6 store cells
on world 0:

| arm | operations | settled | success receipts | carrying a decision |
|---|---|---|---|---|
| agenda  | 42 | 42 | 42 | 42 |
| control | 42 | 42 | 42 | 42 |

84 operations and 84 receipts, every one settled, every one carrying a decision, and every
receipt's payload equal to its operation's payload. They arrive by two paths: 42 through
`authority.admit_study_call` under the study's own allocation, and 42 through
`selection.DecisionRecorder`, which seeds its own parentless allocation. The second
finding below is about why the store's own contamination scanner can only see the first
42.

Every decision this run admits goes through `authority.admit_study_call` under the
study's allocation and is settled by `broker.dispatch_operation`. The counts are taken
by two independent reads and both are published: the durable name prefix over
`operations`, and the recursive allocation-parentage walk
`s09_run_isolation._persisted_operations` uses. The walk finds 42 and the prefix finds
84, and the gap is the finding rather than a defect in either query.

Counting is by this study's own durable name prefixes, never `count(*)` over the table,
so a foreign lane's row cannot be credited to this run. That is ledger **N-301**, which
the coordinator's R2 review recorded against the pre-fix witness while this run was in
flight; `test_a_foreign_rows_row_is_not_counted` pins the difference by writing a row
belonging to nobody and showing the count does not move.

**This closes N-79 by regeneration, not by annotation.** The store witness and the
admitted-operations artifact disagreed because the witness predates the fix; the
post-fix count is 42/42 with receipts, read from the store.

## Exposure

| | |
|---|---|
| provider dispatches | **0** |
| model calls | **0** |
| gateway probe | 1 completion, `max_tokens: 8`, recorded |
| study units | 84, bound as `authorized: 100000` with `max_operations: 84`, `max_development: 84` |
| owner | `authority.authorize_study` → `authority.admit_study_call` → `broker.dispatch_operation` |

Zero provider dispatches is the honest figure, not a round number. Every portfolio
candidate is a `SEED_CAPABILITIES` id, so `trajectory.run_diagnostic` and
`trajectory.dev_episode` resolve in process through `seeds.run_seed` and no model is
called. The one gateway call is the recorded availability probe, outside the matrix.

**The gateway was not reached.** `SETTLEMENT_GATEWAY_KEY` is absent from this process, so
the probe recorded `no-credential` and no route was contacted. A provider outage does not
block source review or offline recomputation, and nothing here depended on it.

Cap sheet: 12 store cells × 7 decisions (the widest cell) = 84, derived from the ladder
before any store effect. `experiments/ad01/e3_ladder.py:cap_sheet`.

## Three defects found while measuring

### `max_model_calls: 0` refuses every operation

`store._study_operation_counts` increments `model_calls` only for an operation whose
stored effect is `model-inference`. A `domain-command` operation never increments it, so
the counter is always 0 and the check `used + 1 > limit` fails for `limit = 0` on the
first decision of any kind:

```
study e3ladder-root ceiling max_model_calls=0 reached at 0
```

This is a live defect in `src/settlement/store.py`, not a property of this study. A cap
sheet that reads as "no model calls" is a cap sheet that forbids the study, and on a
summary line it is indistinguishable from a study that made no model calls. The same
zero ceiling admits a zero-operation study and refuses a 42-operation one, so a cap sheet
cannot distinguish a study that did nothing from a study the cap forbade.

`e3_ladder.study_ceilings` does not bind it, and
`test_a_zero_model_call_ceiling_refuses_a_domain_command` pins the behaviour. The repair
belongs to the store: either count `model_calls` only when a non-model effect is present,
or refuse a zero ceiling at `authorize_study` rather than at the first operation. Not
repaired here — `src/` is outside this lane's ownership.

### A parentage walk cannot see an allocation seeded outside the study

`selection.DecisionRecorder._authorize` calls `store.seed_allocation`, which opens its
own transaction and commits. The allocation it creates is **parentless** — not a child
of anything — so `s09_run_isolation._persisted_operations`, the store's own contamination
scanner, resolves it by walking parentage upward and finds no `study_authority` row. Its
42 operations are real, settled, receipted, and invisible to the scanner.

The first version of this run's verification used exactly that query shape and reported
`per_path: {admit_study_call: 0, decision_recorder: 42}` on a run where every decision had
gone through `admit_study_call`. A count taken that way under-reports by half and reads
as a smaller study rather than a broken query.
There is no settlement command that re-parents a run under a study — `store.py` has no
adoption command — so the gap is not closable from the experiment side. This run's own
accounting therefore goes through `admit_study_call` exclusively, and the recorder's
tree is counted, published and labelled separately in `per_path`. Repair belongs in the
store: a `DecisionRecorder` seeded with a study root should seed its allocation as a
child of that root.

A narrower failure sits underneath it: even a walk that could see the row would miss one
seeded in the same session, because a row written by a committed transaction is invisible
to a later statement's scan of `allocations` under PostgreSQL's default `READ COMMITTED`
snapshot.

Both reads are in the artifact. `walk_agrees_with_prefix` is `false` and `walk_missed` is
populated, which is the expected state: the walk sees the study subtree and not the
recorder's. `test_the_store_count_is_read_both_ways_and_both_are_published` and
`test_the_recorder_writes_a_second_tree_the_walk_cannot_see` hold the shape in place.

### `count(*)` over the whole table is not a count of the run

This is ledger **N-301**, filed by the coordinator's R2 review against the pre-fix
witness while this run was in flight. `s09_e3_selection._operation_count` is
`SELECT count(*) FROM operations` taken before and after the run with no scoping, so a row
written by a concurrent lane is credited to E3, and the artifact's phrase "written by the
run itself" does not describe what the number measures.

This run's counts are filtered by this study's own durable name prefixes, and the verdict
records `every_counted_operation_is_this_study` and the method in
`counting_method`. `test_a_foreign_rows_row_is_not_counted` pins the difference by writing
a well-formed row under a foreign allocation and showing that neither the count nor the
parentage walk moves. The fix for the pre-fix path is a one-line scoping change in
`s09_e3_selection.py`, outside this lane's ownership.

## Cross-check

Every world-0 cell of this fresh ladder equals the post-fix sever control's connected
arm exactly, at all four shared budgets, on all four measures to the sixth decimal:

| arm | budget | sever control held-out | fresh ladder held-out |
|---|---|---|---|
| agenda  | 14 | 0.084656 | 0.084656 |
| agenda  | 20 | 0.084656 | 0.084656 |
| agenda  | 40 | 0.145057 | 0.145057 |
| agenda  | 60 | 0.206063 | 0.206063 |
| control | 14 | 0.000000 | 0.000000 |
| control | 20 | 0.000000 | 0.000000 |
| control | 40 | 0.317460 | 0.317460 |
| control | 60 | 0.367725 | 0.367725 |

Two artifacts built on fresh-per-cell policies agree to the digit, and the committed
ladder agrees with neither. This also resolves the ledger's open discrepancy that
`e3-divergence.json` and `e3-sever-control.json` disagree in the fourth decimal on the
same policy, world and budget: they do not, once each is read off a cell that was never
shared.

## What this does not establish

Bounded autonomous investigation management, and nothing wider. No open-ended scientific
discovery. No claim that the agenda is better than a fitted fixed allocation: on held-out
quality at the two largest budgets it is worse, and that is a result, not a gap.

Three worlds, one substrate, six budgets, no independent replication namespace. The
policy contrast is between two authored rules over a synthetic portfolio; neither policy
was acquired by the model.
